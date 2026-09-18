"""
The recommender - backed by Neo4j.
"""

from dataclasses import dataclass
from .selectors import get_movie, get_movies_by_slugs, NeoMovie
from moviegraph.neo4j import get_db

SOURCE_FOR_YOU = "FOR_YOU"
SOURCE_BECAUSE_YOU_WATCHED = "BECAUSE_YOU_WATCHED"
SOURCE_SIMILAR_TO = "SIMILAR_TO"
SOURCE_TRENDING = "TRENDING"


@dataclass
class Recommendation:
    movie: NeoMovie
    score: float
    reason: str
    source: str
    seed_movie: NeoMovie = None

    @property
    def match_percent(self) -> int:
        return int(round(self.score * 100))

    def as_dict(self):
        return {
            "id": "{}:{}:{}".format(
                self.source,
                self.seed_movie.slug if self.seed_movie else "none",
                self.movie.slug,
            ),
            "movie": self.movie.as_dict(),
            "score": round(self.score, 2),
            "reason": self.reason,
            "source": self.source,
            "seedMovieId": self.seed_movie.slug if self.seed_movie else None,
        }


@dataclass
class RecommendationSet:
    id: str
    title: str
    source: str
    subtitle: str = ""
    seed_movie: NeoMovie = None
    items: list = None
    
    def __post_init__(self):
        if self.items is None:
            self.items = []

    def __bool__(self) -> bool:
        return bool(self.items)

    def as_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle or None,
            "source": self.source,
            "seedMovieId": self.seed_movie.slug if self.seed_movie else None,
            "items": [item.as_dict() for item in self.items],
        }


def for_you(library, limit=10) -> RecommendationSet:
    watched_slugs = library.watched_slugs
    if not watched_slugs:
        # Fallback to random popular movies if no history
        query = """
        MATCH (m:Movie)
        RETURN m.id AS slug, "Popular right now" AS reason, 1.0 AS score
        ORDER BY m.rating DESC LIMIT $limit
        """
        db = get_db()
        results = db.run(query, limit=limit)
        items = []
        for r in results:
            m = get_movie(r["slug"])
            if m:
                items.append(Recommendation(movie=m, score=r["score"], reason=r["reason"], source=SOURCE_FOR_YOU))
        return RecommendationSet(
            id="for-you",
            title="Recommended for you",
            subtitle="Popular picks to start you off",
            source=SOURCE_FOR_YOU,
            items=items,
        )

    # Use Cypher to compute recommendations based on watched history
    query = """
    MATCH (seed:Movie) WHERE seed.id IN $watched_slugs
    
    // Find candidates via similarities, actors, directors, genres
    MATCH (seed)-[:SIMILAR_TO|ACTED_BY|DIRECTED_BY|HAS_GENRE]-(shared)-[:SIMILAR_TO|ACTED_BY|DIRECTED_BY|HAS_GENRE]-(candidate:Movie)
    WHERE NOT candidate.id IN $watched_slugs
    
    WITH candidate, seed, count(shared) AS shared_count
    ORDER BY shared_count DESC, candidate.rating DESC
    
    WITH candidate, collect({seed: seed, count: shared_count})[0] AS best_match
    
    RETURN candidate.id AS slug, 
           best_match.seed.id AS seed_slug, 
           best_match.seed.title AS seed_title,
           best_match.count AS score
    ORDER BY score DESC, candidate.rating DESC
    LIMIT $limit
    """
    
    db = get_db()
    results = db.run(query, watched_slugs=watched_slugs, limit=limit)
    
    items = []
    for r in results:
        candidate = get_movie(r["slug"])
        seed_movie = get_movie(r["seed_slug"])
        if candidate and seed_movie:
            score = min(0.98, 0.6 + (r["score"] * 0.05))
            items.append(
                Recommendation(
                    movie=candidate,
                    score=score,
                    reason=f"Because you watched {r['seed_title']}",
                    source=SOURCE_FOR_YOU,
                    seed_movie=seed_movie
                )
            )
            
    return RecommendationSet(
        id="for-you",
        title="Recommended for you",
        subtitle="Ranked from what you've watched",
        source=SOURCE_FOR_YOU,
        items=items,
    )


def because_you_watched(seed: NeoMovie, limit=8, exclude=()) -> RecommendationSet:
    if not seed:
        return None
        
    query = """
    MATCH (seed:Movie {id: $seed_slug})
    MATCH (seed)-[:SIMILAR_TO|ACTED_BY|DIRECTED_BY|HAS_GENRE]-(shared)-[:SIMILAR_TO|ACTED_BY|DIRECTED_BY|HAS_GENRE]-(candidate:Movie)
    WHERE NOT candidate.id IN $exclude_slugs AND candidate.id <> $seed_slug
    WITH candidate, count(shared) AS shared_count
    ORDER BY shared_count DESC, candidate.rating DESC
    LIMIT $limit
    RETURN candidate.id AS slug, shared_count AS score
    """
    db = get_db()
    results = db.run(query, seed_slug=seed.slug, exclude_slugs=list(exclude), limit=limit)
    
    items = []
    for r in results:
        candidate = get_movie(r["slug"])
        if candidate:
            score = min(0.95, 0.7 + (r["score"] * 0.05))
            items.append(
                Recommendation(
                    movie=candidate,
                    score=score,
                    reason=f"Connected to {seed.title}",
                    source=SOURCE_BECAUSE_YOU_WATCHED,
                    seed_movie=seed
                )
            )
            
    return RecommendationSet(
        id=f"because-you-watched-{seed.slug}",
        title=f"Because you watched {seed.title}",
        subtitle="Connected through directors, cast and genre",
        source=SOURCE_BECAUSE_YOU_WATCHED,
        seed_movie=seed,
        items=items,
    )


def related(movie: NeoMovie, limit=8) -> RecommendationSet:
    if not movie:
        return None
        
    query = """
    MATCH (seed:Movie {id: $seed_slug})
    MATCH (seed)-[r:SIMILAR_TO]->(candidate:Movie)
    RETURN candidate.id AS slug, r.position AS pos
    ORDER BY pos ASC
    LIMIT $limit
    """
    db = get_db()
    results = db.run(query, seed_slug=movie.slug, limit=limit)
    
    items = []
    for i, r in enumerate(results):
        candidate = get_movie(r["slug"])
        if candidate:
            items.append(
                Recommendation(
                    movie=candidate,
                    score=0.95 - (i * 0.05),
                    reason=f"Similar to {movie.title}",
                    source=SOURCE_SIMILAR_TO,
                    seed_movie=movie
                )
            )
            
    return RecommendationSet(
        id=f"related-{movie.slug}",
        title="Related movies",
        subtitle=f"Connected to {movie.title}",
        source=SOURCE_SIMILAR_TO,
        seed_movie=movie,
        items=items,
    )


def trending(limit=8) -> RecommendationSet:
    # Query Neo4j for highly rated movies
    query = """
    MATCH (m:Movie)
    RETURN m.id AS slug
    ORDER BY m.rating DESC
    LIMIT $limit
    """
    db = get_db()
    results = db.run(query, limit=limit)
    
    items = []
    for r in results:
        m = get_movie(r["slug"])
        if m:
            items.append(
                Recommendation(
                    movie=m,
                    score=0.99,
                    reason="Top rated this week",
                    source=SOURCE_TRENDING,
                )
            )
            
    return RecommendationSet(
        id="trending",
        title="Trending this week",
        subtitle="What everyone on MovieGraph is watching",
        source=SOURCE_TRENDING,
        items=items,
    )

"""
The read layer over the catalog — backed by Neo4j.
"""

from dataclasses import dataclass
from django.urls import reverse
from moviegraph.neo4j import get_db

ALL_GENRES = "All"

SORT_OPTIONS = [
    ("rating", "Top rated"),
    ("year", "Newest first"),
    ("title", "A-Z"),
]
SORT_KEYS = {key for key, _ in SORT_OPTIONS}
DEFAULT_SORT = "rating"


@dataclass
class NeoMovie:
    """A duck-typed replacement for the Django Movie model."""
    slug: str
    title: str
    year: int
    rating: float
    runtime: int
    tagline: str
    description: str
    poster: str
    backdrop: str
    genre_names: list
    actor_names: list
    director_name: str
    similar_to_slugs: list

    @property
    def pk(self):
        return self.slug

    @property
    def primary_genre(self):
        return self.genre_names[0] if self.genre_names else ""

    def get_absolute_url(self) -> str:
        return reverse("catalog:movie_detail", args=[self.slug])

    def as_dict(self):
        return {
            "id": self.slug,
            "title": self.title,
            "year": self.year,
            "rating": float(self.rating) if self.rating else 0.0,
            "runtime": self.runtime,
            "tagline": self.tagline or None,
            "description": self.description,
            "poster": self.poster,
            "backdrop": self.backdrop or None,
            "genres": self.genre_names,
            "director": self.director_name,
            "actors": self.actor_names,
            "similarTo": self.similar_to_slugs,
        }


def _record_to_movie(record):
    m = record["m"]
    return NeoMovie(
        slug=m.get("id"),
        title=m.get("title"),
        year=m.get("year"),
        rating=m.get("rating"),
        runtime=m.get("runtime"),
        tagline=m.get("tagline"),
        description=m.get("description"),
        poster=m.get("poster"),
        backdrop=m.get("backdrop"),
        genre_names=record.get("genres", []),
        actor_names=record.get("actors", []),
        director_name=record.get("director", ""),
        similar_to_slugs=record.get("similarTo", [])
    )


def get_movies():
    """Returns all movies, but typically you should use browse() to limit."""
    query = """
    MATCH (m:Movie)
    OPTIONAL MATCH (m)-[rg:HAS_GENRE]->(g:Genre)
    OPTIONAL MATCH (m)-[ra:ACTED_BY]->(a:Person)
    OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
    OPTIONAL MATCH (m)-[rs:SIMILAR_TO]->(s:Movie)
    RETURN m, 
           // Order genres, actors, and similar by position
           [x IN collect(DISTINCT {name: g.name, pos: rg.position}) | x] AS gList,
           [x IN collect(DISTINCT {name: a.name, pos: ra.position}) | x] AS aList,
           d.name AS director,
           [x IN collect(DISTINCT {id: s.id, pos: rs.position}) | x] AS sList
    ORDER BY m.rating DESC, m.title ASC
    """
    db = get_db()
    results = db.run(query)
    
    movies = []
    for record in results:
        # Sort lists by position
        gList = sorted([x for x in record["gList"] if x["name"]], key=lambda k: k.get("pos") or 0)
        aList = sorted([x for x in record["aList"] if x["name"]], key=lambda k: k.get("pos") or 0)
        sList = sorted([x for x in record["sList"] if x["id"]], key=lambda k: k.get("pos") or 0)
        
        row = {
            "m": record["m"],
            "genres": [x["name"] for x in gList],
            "actors": [x["name"] for x in aList],
            "director": record["director"] or "",
            "similarTo": [x["id"] for x in sList]
        }
        movies.append(_record_to_movie(row))
    return movies


def get_movie(slug):
    query = """
    MATCH (m:Movie {id: $slug})
    OPTIONAL MATCH (m)-[rg:HAS_GENRE]->(g:Genre)
    OPTIONAL MATCH (m)-[ra:ACTED_BY]->(a:Person)
    OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
    OPTIONAL MATCH (m)-[rs:SIMILAR_TO]->(s:Movie)
    WITH m, g, rg, a, ra, d, s, rs
    ORDER BY rg.position, ra.position, rs.position
    RETURN m, 
           collect(DISTINCT g.name) AS genres,
           collect(DISTINCT a.name) AS actors,
           d.name AS director,
           collect(DISTINCT s.id) AS similarTo
    """
    db = get_db()
    result = db.run(query, slug=slug).single()
    if not result:
        return None
    return _record_to_movie(result)


def get_movies_by_slugs(slugs):
    if not slugs:
        return []
    
    query = """
    MATCH (m:Movie) WHERE m.id IN $slugs
    OPTIONAL MATCH (m)-[rg:HAS_GENRE]->(g:Genre)
    OPTIONAL MATCH (m)-[ra:ACTED_BY]->(a:Person)
    OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
    OPTIONAL MATCH (m)-[rs:SIMILAR_TO]->(s:Movie)
    WITH m, g, rg, a, ra, d, s, rs
    ORDER BY rg.position, ra.position, rs.position
    RETURN m, 
           collect(DISTINCT g.name) AS genres,
           collect(DISTINCT a.name) AS actors,
           d.name AS director,
           collect(DISTINCT s.id) AS similarTo
    """
    db = get_db()
    results = db.run(query, slugs=slugs)
    
    # Keep the original order
    by_slug = {record["m"]["id"]: _record_to_movie(record) for record in results}
    return [by_slug[slug] for slug in slugs if slug in by_slug]


@dataclass
class NeoGenre:
    name: str
    slug: str

def get_genres():
    query = "MATCH (g:Genre) RETURN g.name AS name ORDER BY g.name"
    db = get_db()
    results = db.run(query)
    return [NeoGenre(name=r["name"], slug=r["name"].lower().replace(' ', '-')) for r in results]


def resolve_genre(name):
    if name and name != ALL_GENRES:
        query = "MATCH (g:Genre {name: $name}) RETURN count(g) AS count"
        db = get_db()
        count = db.run(query, name=name).single()["count"]
        if count > 0:
            return name
    return ALL_GENRES


def resolve_sort(key):
    return key if key in SORT_KEYS else DEFAULT_SORT


def browse(genre=ALL_GENRES, sort=DEFAULT_SORT):
    # Base match
    if genre == ALL_GENRES:
        match_clause = "MATCH (m:Movie)"
    else:
        match_clause = "MATCH (m:Movie)-[:HAS_GENRE]->(:Genre {name: $genre})"
        
    # Sort mapping
    if sort == "year":
        order_clause = "ORDER BY m.year DESC, m.rating DESC, m.title ASC"
    elif sort == "title":
        order_clause = "ORDER BY m.title ASC"
    else:
        order_clause = "ORDER BY m.rating DESC, m.title ASC"
        
    query = f"""
    {match_clause}
    OPTIONAL MATCH (m)-[rg:HAS_GENRE]->(g:Genre)
    OPTIONAL MATCH (m)-[ra:ACTED_BY]->(a:Person)
    OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
    OPTIONAL MATCH (m)-[rs:SIMILAR_TO]->(s:Movie)
    WITH m, g, rg, a, ra, d, s, rs
    ORDER BY rg.position, ra.position, rs.position
    RETURN m, 
           collect(DISTINCT g.name) AS genres,
           collect(DISTINCT a.name) AS actors,
           d.name AS director,
           collect(DISTINCT s.id) AS similarTo
    {order_clause}
    """
    
    db = get_db()
    results = db.run(query, genre=genre)
    return [_record_to_movie(record) for record in results]


def get_similar_movies(movie, limit=8):
    """
    -[:SIMILAR_TO]-> edges, topped up with movies that share a genre.
    """
    # 1. Get explicit SIMILAR_TO edges
    related = get_movies_by_slugs(movie.similar_to_slugs)
    if len(related) >= limit:
        return related[:limit]
        
    # 2. Top up with shared genres
    seen_ids = [movie.slug] + [m.slug for m in related]
    
    query = """
    MATCH (m:Movie)-[:HAS_GENRE]->(g:Genre)
    WHERE g.name IN $seed_genres AND NOT m.id IN $seen_ids
    WITH m, count(DISTINCT g) AS shared
    ORDER BY shared DESC, m.rating DESC, m.title ASC
    LIMIT $limit
    
    OPTIONAL MATCH (m)-[rg:HAS_GENRE]->(gx:Genre)
    OPTIONAL MATCH (m)-[ra:ACTED_BY]->(a:Person)
    OPTIONAL MATCH (m)-[:DIRECTED_BY]->(d:Person)
    OPTIONAL MATCH (m)-[rs:SIMILAR_TO]->(s:Movie)
    WITH m, shared, gx, rg, a, ra, d, s, rs
    ORDER BY shared DESC, m.rating DESC, m.title ASC, rg.position, ra.position, rs.position
    RETURN m, 
           collect(DISTINCT gx.name) AS genres,
           collect(DISTINCT a.name) AS actors,
           d.name AS director,
           collect(DISTINCT s.id) AS similarTo
    """
    db = get_db()
    results = db.run(query, seed_genres=movie.genre_names, seen_ids=seen_ids, limit=limit-len(related))
    
    candidates = [_record_to_movie(record) for record in results]
    return (related + candidates)[:limit]


def search_movies(query, limit=12):
    q = (query or "").strip().lower()
    if not q:
        return []
        
    # We can do this purely in Neo4j or python. Let's replicate python for accuracy.
    scored = []
    for movie in get_movies():
        score = _search_score(movie, q)
        if score:
            scored.append((score, float(movie.rating) if movie.rating else 0.0, movie))

    scored.sort(key=lambda row: (-row[0], -row[1], row[2].title))
    return [movie for _, _, movie in scored[:limit]]


def _search_score(movie, q):
    title = movie.title.lower()
    if title == q:
        return 100
    if title.startswith(q):
        return 80
    if q in title:
        return 60
    if q in movie.director_name.lower():
        return 40
    if any(q in name.lower() for name in movie.actor_names):
        return 30
    if any(q in name.lower() for name in movie.genre_names):
        return 20
    if str(movie.year) == q:
        return 15
    return 0

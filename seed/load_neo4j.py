import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Add the parent directory to sys.path to import from moviegraph
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moviegraph.neo4j import get_driver

def load_data():
    data_path = Path(__file__).resolve().parent / "catalog.json"
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    driver = get_driver()
    
    with driver.session() as session:
        # Clear existing data
        print("Clearing database...")
        session.run("MATCH (n) DETACH DELETE n")
        
        # Create constraints
        print("Creating constraints...")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (m:Movie) REQUIRE m.id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (g:Genre) REQUIRE g.name IS UNIQUE")
        
        print("Loading movies, genres, and people...")
        for movie in data.get("movies", []):
            # Create movie
            session.run(
                """
                MERGE (m:Movie {id: $id})
                SET m.title = $title,
                    m.year = $year,
                    m.rating = $rating,
                    m.runtime = $runtime,
                    m.poster = $poster,
                    m.backdrop = $backdrop,
                    m.tagline = $tagline,
                    m.description = $description
                """,
                id=movie["id"],
                title=movie["title"],
                year=movie.get("year"),
                rating=movie.get("rating"),
                runtime=movie.get("runtime"),
                poster=movie.get("poster", ""),
                backdrop=movie.get("backdrop", ""),
                tagline=movie.get("tagline", ""),
                description=movie.get("description", "")
            )
            
            # Create genres and relationships
            for position, genre_name in enumerate(movie.get("genres", [])):
                session.run(
                    """
                    MATCH (m:Movie {id: $movie_id})
                    MERGE (g:Genre {name: $genre_name})
                    MERGE (m)-[r:HAS_GENRE]->(g)
                    SET r.position = $position
                    """,
                    movie_id=movie["id"],
                    genre_name=genre_name,
                    position=position
                )
            
            # Create director
            director_name = movie.get("director")
            if director_name:
                session.run(
                    """
                    MATCH (m:Movie {id: $movie_id})
                    MERGE (p:Person {name: $director_name})
                    MERGE (m)-[:DIRECTED_BY]->(p)
                    """,
                    movie_id=movie["id"],
                    director_name=director_name
                )
            
            # Create actors
            for position, actor_name in enumerate(movie.get("actors", [])):
                session.run(
                    """
                    MATCH (m:Movie {id: $movie_id})
                    MERGE (p:Person {name: $actor_name})
                    MERGE (m)-[r:ACTED_BY]->(p)
                    SET r.position = $position
                    """,
                    movie_id=movie["id"],
                    actor_name=actor_name,
                    position=position
                )
        
        print("Creating SIMILAR_TO relationships...")
        for movie in data.get("movies", []):
            for position, target_id in enumerate(movie.get("similarTo", [])):
                session.run(
                    """
                    MATCH (source:Movie {id: $source_id})
                    MATCH (target:Movie {id: $target_id})
                    MERGE (source)-[r:SIMILAR_TO]->(target)
                    SET r.position = $position
                    """,
                    source_id=movie["id"],
                    target_id=target_id,
                    position=position
                )
        
    print("Data load complete!")

if __name__ == "__main__":
    load_data()

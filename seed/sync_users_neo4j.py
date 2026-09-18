import os
import sys
import django
from pathlib import Path

# Setup Django environment
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moviegraph.settings")
django.setup()

from django.contrib.auth.models import User
from library.models import LibraryEntry, Profile
from moviegraph.neo4j import get_db
from dotenv import load_dotenv

# Load .env file for Neo4j credentials
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def sync_users_to_neo4j():
    db = get_db()
    
    # Get all watched entries
    entries = LibraryEntry.objects.filter(kind=LibraryEntry.WATCHED, user__isnull=False).select_related('user', 'movie')
    
    print("Syncing Users and WATCHED edges to Neo4j...")
    for entry in entries:
        username = entry.user.username
        movie_slug = entry.movie.slug
        
        # Get handle if exists
        profile = Profile.objects.filter(user=entry.user).first()
        name = profile.handle if profile else username
        
        db.run(
            """
            MERGE (u:User {username: $username})
            SET u.name = $name
            
            WITH u
            MATCH (m:Movie {id: $movie_slug})
            MERGE (u)-[:WATCHED]->(m)
            """,
            username=username,
            name=name,
            movie_slug=movie_slug
        )
        print(f"Synced: {name} WATCHED {movie_slug}")
            
    print("Done!")

if __name__ == "__main__":
    sync_users_to_neo4j()

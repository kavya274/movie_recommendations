import os
import sys
import requests
import django
from pathlib import Path

# Setup Django environment
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "moviegraph.settings")
django.setup()

from moviegraph.neo4j import get_db
from django.conf import settings
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

OMDB_API_KEY = os.environ.get("OMDB_API_KEY")

def fetch_and_save_image(url, save_path):
    if url == "N/A" or not url:
        return False
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception as e:
        print(f"Failed to download image: {e}")
    return False

def update_movie_images():
    if not OMDB_API_KEY:
        print("ERROR: OMDB_API_KEY is not set in .env file.")
        return

    db = get_db()
    posters_dir = Path(settings.BASE_DIR) / "static" / "posters"
    posters_dir.mkdir(parents=True, exist_ok=True)

    # Get all movies
    result = db.run("MATCH (m:Movie) RETURN m.id AS slug, m.title AS title, m.year AS year")
    movies = result.data()

    print(f"Found {len(movies)} movies. Fetching posters from OMDB...")

    for movie in movies:
        slug = movie['slug']
        title = movie['title']
        year = movie['year']

        # Call OMDB API
        api_url = f"http://www.omdbapi.com/?t={title}&y={year}&apikey={OMDB_API_KEY}"
        res = requests.get(api_url).json()

        if res.get("Response") == "True":
            poster_url = res.get("Poster")
            if poster_url and poster_url != "N/A":
                # Download image
                file_name = f"{slug}.jpg"
                save_path = posters_dir / file_name
                
                if fetch_and_save_image(poster_url, save_path):
                    # Update Neo4j
                    new_poster_path = f"/static/posters/{file_name}"
                    db.run(
                        "MATCH (m:Movie {id: $slug}) SET m.poster = $poster, m.backdrop = $poster",
                        slug=slug,
                        poster=new_poster_path
                    )
                    print(f"Updated poster for: {title}")
                else:
                    print(f"Failed to download poster for: {title}")
            else:
                print(f"No poster found on OMDB for: {title}")
        else:
            print(f"OMDB Error for {title}: {res.get('Error')}")

    print("Done! Refresh your Django website to see the new posters.")

if __name__ == "__main__":
    update_movie_images()

"""
Load the catalog from `seed/catalog.json`.

The JSON is the prototype's fixtures converted verbatim, so the Django app
serves exactly the same 31 films. Idempotent: re-running updates rows in place
rather than duplicating them, which makes it safe to use as a "reset the demo"
command during development.

    python manage.py seed_catalog
    python manage.py seed_catalog --demo-user   # also builds a signed-in demo
"""

import json
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import (
    ColdStartPick,
    Credit,
    EditorialPick,
    Genre,
    Movie,
    MovieGenre,
    Person,
    Similarity,
    TrendingEntry,
)
from library.models import LibraryEntry
from library.services import ensure_profile

DEMO_USERNAME = "alex"
DEMO_PASSWORD = "moviegraph"


def slugify_name(name):
    """"Denis Villeneuve" -> "denis-villeneuve"."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")


class Command(BaseCommand):
    help = "Load genres, movies, people and recommendation seeds from seed/catalog.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=str(Path(settings.BASE_DIR) / "seed" / "catalog.json"),
            help="Seed file to load.",
        )
        parser.add_argument(
            "--demo-user",
            action="store_true",
            help="Create the 'alex' demo account with a pre-filled library.",
        )
        parser.add_argument(
            "--flush",
            action="store_true",
            help="Delete the existing catalog first instead of updating in place.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError("Seed file not found: {}".format(path))

        data = json.loads(path.read_text(encoding="utf-8"))
        self._people = {}

        if options["flush"]:
            self.stdout.write("Flushing existing catalog...")
            LibraryEntry.objects.all().delete()
            Similarity.objects.all().delete()
            Credit.objects.all().delete()
            MovieGenre.objects.all().delete()
            EditorialPick.objects.all().delete()
            ColdStartPick.objects.all().delete()
            TrendingEntry.objects.all().delete()
            Movie.objects.all().delete()
            Person.objects.all().delete()
            Genre.objects.all().delete()

        genres = self._load_genres(data["genres"])
        movies = self._load_movies(data["movies"], genres)
        self._load_similarities(data["movies"], movies)
        self._load_rails(data, movies)

        if options["demo_user"]:
            self._load_demo_user(data.get("user"), movies)

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded {} movies, {} genres, {} people.".format(
                    Movie.objects.count(), Genre.objects.count(), Person.objects.count()
                )
            )
        )

    # -- Nodes ------------------------------------------------------------

    def _load_genres(self, rows):
        genres = {}
        for position, row in enumerate(rows):
            genre, _ = Genre.objects.update_or_create(
                name=row["name"],
                defaults={"slug": row["slug"], "position": position},
            )
            genres[row["name"]] = genre
        return genres

    def _person(self, name):
        """
        Get-or-create a (Person), memoised so one name is one row.

        The cache is per-run, not a default argument — a second run in the same
        process (tests, --flush) must not reuse ids from a deleted table.
        """
        cached = self._people.get(name)
        if cached is not None:
            return cached
        person, _ = Person.objects.get_or_create(
            name=name, defaults={"slug": slugify_name(name)}
        )
        self._people[name] = person
        return person

    def _load_movies(self, rows, genres):
        movies = {}
        for row in rows:
            director = self._person(row["director"]) if row.get("director") else None

            movie, _ = Movie.objects.update_or_create(
                slug=row["id"],
                defaults={
                    "title": row["title"],
                    "year": row["year"],
                    "rating": row["rating"],
                    "runtime": row.get("runtime"),
                    "tagline": row.get("tagline") or "",
                    "description": row["description"],
                    # The prototype's paths were served from /public; here the
                    # same files live under STATIC_URL.
                    "poster": self._asset(row["poster"]),
                    "backdrop": self._asset(row.get("backdrop")),
                    "director": director,
                },
            )
            movies[row["id"]] = movie

            # Rewrite the ordered edges rather than diffing them — cheap at this
            # size and it keeps `position` honest when the seed order changes.
            movie.movie_genres.all().delete()
            for position, name in enumerate(row.get("genres", [])):
                genre = genres.get(name)
                if genre is None:
                    genre, _ = Genre.objects.get_or_create(
                        name=name,
                        defaults={"slug": slugify_name(name), "position": 99},
                    )
                    genres[name] = genre
                MovieGenre.objects.create(movie=movie, genre=genre, position=position)

            movie.credits.all().delete()
            for position, name in enumerate(row.get("actors", [])):
                Credit.objects.create(
                    movie=movie, person=self._person(name), position=position
                )

        return movies

    def _asset(self, path):
        """"/posters/dune.svg" -> "posters/dune.svg", left alone if absolute."""
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return path.lstrip("/")

    def _load_similarities(self, rows, movies):
        """Second pass: every target movie exists by now."""
        for row in rows:
            source = movies[row["id"]]
            source.similar_edges.all().delete()
            for position, target_slug in enumerate(row.get("similarTo") or []):
                target = movies.get(target_slug)
                if target is None or target.pk == source.pk:
                    continue
                Similarity.objects.create(source=source, target=target, position=position)

    # -- Rails ------------------------------------------------------------

    def _load_rails(self, data, movies):
        ColdStartPick.objects.all().delete()
        for row in data.get("forYou", []):
            movie = movies.get(row["movieId"])
            if movie:
                ColdStartPick.objects.create(
                    movie=movie, score=row["score"], reason=row["reason"]
                )

        TrendingEntry.objects.all().delete()
        for row in data.get("trending", []):
            movie = movies.get(row["movieId"])
            if movie:
                TrendingEntry.objects.create(
                    movie=movie, score=row["score"], reason=row["reason"]
                )

        # One active hero. Highest-rated film unless the seed names one.
        EditorialPick.objects.all().delete()
        featured = movies.get(data.get("featured", "interstellar"))
        if featured is None:
            featured = Movie.objects.order_by("-rating").first()
        if featured:
            EditorialPick.objects.create(movie=featured)

    # -- Demo account -----------------------------------------------------

    def _load_demo_user(self, seed_user, movies):
        if not seed_user:
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={"first_name": "Alex", "last_name": "Rivera"},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        ensure_profile(user)

        LibraryEntry.objects.filter(user=user).delete()
        # Reversed so the seed's first entry ends up newest — "Because you
        # watched" reads the most recent WATCHED edge.
        for slug in reversed(seed_user.get("watched", [])):
            movie = movies.get(slug)
            if movie:
                LibraryEntry.objects.create(
                    user=user, movie=movie, kind=LibraryEntry.WATCHED
                )
        for slug in reversed(seed_user.get("watchlist", [])):
            movie = movies.get(slug)
            if movie:
                LibraryEntry.objects.create(
                    user=user, movie=movie, kind=LibraryEntry.WATCHLIST
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo account ready: {} / {}".format(DEMO_USERNAME, DEMO_PASSWORD)
            )
        )

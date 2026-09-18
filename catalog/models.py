"""
The catalog graph.

The Next.js prototype modelled this as a property graph and flattened it into
fixtures. Here the same shape is relational, with a through-model wherever the
edge carries data (billing order, genre order, similarity rank):

    (Movie) -[:HAS_GENRE]->    (Genre)     -> MovieGenre.position
    (Movie) -[:DIRECTED_BY]->  (Person)    -> Movie.director
    (Movie) -[:ACTED_BY]->     (Person)    -> Credit.position
    (Movie) -[:SIMILAR_TO]->   (Movie)     -> Similarity.position

`Movie.slug` is the public id ("blade-runner-2049") and is what every URL uses,
so the routes match the prototype's `/movies/:id` exactly.
"""

from django.db import models
from django.urls import reverse


class Genre(models.Model):
    """A (Genre) node. `position` fixes the order the filter chips render in."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "name"]

    def __str__(self) -> str:
        return self.name


class Person(models.Model):
    """A (Person) node — reached as a director or through a billing credit."""

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=120, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "people"

    def __str__(self) -> str:
        return self.name


class MovieQuerySet(models.QuerySet):
    def with_edges(self):
        """Prefetch every edge the card and detail templates walk."""
        return self.select_related("director").prefetch_related(
            "movie_genres__genre", "credits__person"
        )

    def in_genre(self, genre_name):
        if not genre_name or genre_name == Movie.ALL_GENRES:
            return self
        return self.filter(movie_genres__genre__name=genre_name).distinct()

    def sorted_by(self, key):
        """`rating` | `year` | `title` — the three Discover sort options."""
        if key == "year":
            return self.order_by("-year", "-rating", "title")
        if key == "title":
            return self.order_by("title")
        return self.order_by("-rating", "title")


class Movie(models.Model):
    """A (Movie) node."""

    ALL_GENRES = "All"

    slug = models.SlugField(max_length=80, unique=True, help_text="Public id used in URLs.")
    title = models.CharField(max_length=200)
    year = models.PositiveSmallIntegerField()
    rating = models.DecimalField(max_digits=3, decimal_places=1, help_text="Out of 10.")
    runtime = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Minutes.")
    tagline = models.CharField(max_length=250, blank=True)
    description = models.TextField()
    poster = models.CharField(max_length=300, help_text="Path under STATIC_URL, or an absolute URL.")
    backdrop = models.CharField(max_length=300, blank=True)

    director = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="directed",
        null=True,
        blank=True,
    )
    genres = models.ManyToManyField(Genre, through="MovieGenre", related_name="movies")
    actors = models.ManyToManyField(Person, through="Credit", related_name="acted_in")
    similar_to = models.ManyToManyField(
        "self",
        through="Similarity",
        through_fields=("source", "target"),
        symmetrical=False,
        related_name="similar_from",
    )

    objects = MovieQuerySet.as_manager()

    class Meta:
        ordering = ["-rating", "title"]
        indexes = [models.Index(fields=["-rating"]), models.Index(fields=["-year"])]

    def __str__(self) -> str:
        return "{} ({})".format(self.title, self.year)

    def get_absolute_url(self) -> str:
        return reverse("catalog:movie_detail", args=[self.slug])

    # -- Ordered edge accessors -------------------------------------------
    # Templates and the recommender read these instead of the raw M2M managers,
    # so the through-model ordering is always respected.

    @property
    def genre_names(self):
        return [mg.genre.name for mg in self.movie_genres.all()]

    @property
    def actor_names(self):
        return [credit.person.name for credit in self.credits.all()]

    @property
    def primary_genre(self):
        names = self.genre_names
        return names[0] if names else ""

    @property
    def director_name(self):
        return self.director.name if self.director else ""

    def as_dict(self):
        """The JSON shape the prototype's `types/index.ts` describes."""
        return {
            "id": self.slug,
            "title": self.title,
            "year": self.year,
            "rating": float(self.rating),
            "runtime": self.runtime,
            "tagline": self.tagline or None,
            "description": self.description,
            "poster": self.poster,
            "backdrop": self.backdrop or None,
            "genres": self.genre_names,
            "director": self.director_name,
            "actors": self.actor_names,
            "similarTo": [edge.target.slug for edge in self.similar_edges.all()],
        }


class MovieGenre(models.Model):
    """-[:HAS_GENRE]-> , ordered so the first genre is the one cards print."""

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="movie_genres")
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE, related_name="movie_genres")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["movie", "genre"], name="unique_movie_genre")
        ]

    def __str__(self) -> str:
        return "{} -> {}".format(self.movie.title, self.genre.name)


class Credit(models.Model):
    """-[:ACTED_BY]-> , ordered by billing."""

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="credits")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="credits")
    character = models.CharField(max_length=120, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["movie", "person"], name="unique_movie_credit")
        ]

    def __str__(self) -> str:
        return "{} -> {}".format(self.movie.title, self.person.name)


class Similarity(models.Model):
    """-[:SIMILAR_TO]-> , directed, ordered by how strong the link is."""

    source = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="similar_edges")
    target = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="similar_to_edges")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["source", "target"], name="unique_similarity"),
            models.CheckConstraint(
                condition=~models.Q(source=models.F("target")),
                name="similarity_not_self",
            ),
        ]

    def __str__(self) -> str:
        return "{} ~ {}".format(self.source.title, self.target.title)


class EditorialPick(models.Model):
    """
    The hero slot on the home page.

    The prototype hardcoded `FEATURED_MOVIE_ID`; here it is a row an editor can
    change from the admin. The most recent active pick wins.
    """

    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="editorial_picks")
    eyebrow = models.CharField(max_length=60, default="Featured today")
    kicker = models.CharField(
        max_length=200, default="Explore movies connected to what you love."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return "Featured: {}".format(self.movie.title)


class ColdStartPick(models.Model):
    """
    "Recommended for you" before there is anything to personalise on.

    Once a visitor has a single WATCHED edge the recommender computes the rail
    from the graph instead and this table stops being consulted.
    """

    movie = models.OneToOneField(Movie, on_delete=models.CASCADE, related_name="cold_start_pick")
    score = models.FloatField(default=0.0)
    reason = models.CharField(max_length=120)

    class Meta:
        ordering = ["-score"]

    def __str__(self) -> str:
        return "{} - {}".format(self.movie.title, self.reason)


class TrendingEntry(models.Model):
    """
    The "Trending this week" rail — global, not personalised.

    Kept as a table rather than a query so the ordering stays editorial, which
    is what the prototype's `data/recommendations.ts` fixture encoded.
    """

    movie = models.OneToOneField(Movie, on_delete=models.CASCADE, related_name="trending_entry")
    score = models.FloatField(default=0.0)
    reason = models.CharField(max_length=120)

    class Meta:
        ordering = ["-score"]
        verbose_name_plural = "trending entries"

    def __str__(self) -> str:
        return "{} - {}".format(self.movie.title, self.reason)

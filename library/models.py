"""
The per-user side of the graph:

    (User) -[:WATCHED]->     (Movie)
    (User) -[:WATCHLISTED]-> (Movie)

Both edges live in one table, `LibraryEntry`, discriminated by `kind`. That
keeps "move from watchlist to watched" a single-row update and lets one query
load both lists.

Anonymous visitors get a library too: the owner is then the session key rather
than a user row, and `services.merge_session_library` folds it into the account
the moment they sign up or sign in. Nobody hits an empty demo.
"""

from django.conf import settings
from django.db import models

from catalog.models import Movie


class Profile(models.Model):
    """Display data for a (User) node — the handle shown in the profile menu."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    handle = models.CharField(max_length=40, unique=True)

    def __str__(self) -> str:
        return self.handle

    @property
    def display_name(self) -> str:
        full = self.user.get_full_name()
        return full or self.user.username

    @property
    def initials(self) -> str:
        """"Alex Rivera" -> "AR" — the avatar fallback."""
        parts = [part for part in self.display_name.split(" ") if part][:2]
        return "".join(part[0].upper() for part in parts) or "?"


class LibraryEntryQuerySet(models.QuerySet):
    def watched(self):
        return self.filter(kind=LibraryEntry.WATCHED)

    def watchlist(self):
        return self.filter(kind=LibraryEntry.WATCHLIST)

    def for_owner(self, user, session_key):
        """
        Scope to whoever is browsing.

        Signed in: the user rows. Anonymous: the rows keyed to this session.
        An anonymous request with no session yet matches nothing.
        """
        if user is not None and user.is_authenticated:
            return self.filter(user=user)
        if session_key:
            return self.filter(user__isnull=True, session_key=session_key)
        return self.none()

    def with_movie(self):
        """
        Pull every edge the recommender walks from a watched movie in one go —
        it scores the whole catalog against each seed, so a lazy `genre_names`
        here would be an N+1 per row.
        """
        return self.select_related("movie", "movie__director").prefetch_related(
            "movie__movie_genres__genre",
            "movie__credits__person",
            "movie__similar_edges",
        )


class LibraryEntry(models.Model):
    """One WATCHED or WATCHLISTED edge."""

    WATCHED = "watched"
    WATCHLIST = "watchlist"
    KIND_CHOICES = [(WATCHED, "Watched"), (WATCHLIST, "Watchlist")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="library_entries",
        null=True,
        blank=True,
    )
    session_key = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="Owner when nobody is signed in.",
    )
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="library_entries")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = LibraryEntryQuerySet.as_manager()

    class Meta:
        # Newest first: the home page seeds "Because you watched" from the most
        # recent WATCHED edge, and My Movies lists recent additions first.
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "library entries"
        constraints = [
            # A movie is in at most one list per owner. Two constraints because
            # `user` is null for anonymous owners, and NULLs never collide.
            models.UniqueConstraint(
                fields=["user", "movie"],
                condition=models.Q(user__isnull=False),
                name="unique_user_movie",
            ),
            models.UniqueConstraint(
                fields=["session_key", "movie"],
                condition=models.Q(user__isnull=True),
                name="unique_session_movie",
            ),
        ]
        indexes = [models.Index(fields=["user", "kind"])]

    def __str__(self) -> str:
        owner = self.user.username if self.user else "session:{}".format(self.session_key[:8])
        return "{} -[{}]-> {}".format(owner, self.kind.upper(), self.movie.title)

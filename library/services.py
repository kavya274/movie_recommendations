"""
The write layer for the WATCHED / WATCHLISTED edges.

Views (HTML and JSON alike) go through these functions rather than touching
`LibraryEntry` directly, so the rules below live in exactly one place:

  * marking something watched removes it from the watchlist — you don't still
    intend to watch what you've watched;
  * an anonymous visitor's library is keyed to their session and is merged into
    their account on sign-up / sign-in.
"""

from django.db import transaction

from catalog.models import Movie

from .models import LibraryEntry, Profile


class Library:
    """
    A request's view of its own library.

    Built once per request by `get_library`, then read by the views and the
    recommender. `watched_slugs` / `watchlist_slugs` are evaluated eagerly
    because every template on the page asks the same "is this watched?"
    question for dozens of cards.
    """

    def __init__(self, user, session_key):
        self.user = user if (user is not None and user.is_authenticated) else None
        self.session_key = session_key or ""
        entries = list(LibraryEntry.objects.for_owner(user, session_key).with_movie())
        self._entries = entries
        self.watched_slugs = [e.movie.slug for e in entries if e.kind == LibraryEntry.WATCHED]
        self.watchlist_slugs = [e.movie.slug for e in entries if e.kind == LibraryEntry.WATCHLIST]

    def __contains__(self, slug) -> bool:
        return slug in self.watched_slugs or slug in self.watchlist_slugs

    def is_watched(self, slug) -> bool:
        return slug in self.watched_slugs

    def is_in_watchlist(self, slug) -> bool:
        return slug in self.watchlist_slugs

    @property
    def watched_count(self) -> int:
        return len(self.watched_slugs)

    @property
    def watchlist_count(self) -> int:
        return len(self.watchlist_slugs)

    @property
    def last_watched_slug(self):
        """Seeds the "Because you watched X" rail. Entries are newest-first."""
        return self.watched_slugs[0] if self.watched_slugs else None

    def movies(self, kind):
        """The movies in one list, newest addition first."""
        return [e.movie for e in self._entries if e.kind == kind]

    def favourite_genres(self, limit=3):
        """Derived from watch history — the genres the ranker leans on."""
        counts = {}
        for entry in self._entries:
            if entry.kind != LibraryEntry.WATCHED:
                continue
            for name in entry.movie.genre_names:
                counts[name] = counts.get(name, 0) + 1
        ranked = sorted(counts.items(), key=lambda row: (-row[1], row[0]))
        return [name for name, _ in ranked[:limit]]


def get_session_key(request):
    """
    The session key to own anonymous rows.

    Django only writes a session cookie once something is stored in it, so an
    untouched anonymous request has no key. We create one lazily here — this is
    called on the write path, not on every read.
    """
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def get_library(request) -> Library:
    """Read-only access — never creates a session for a passing visitor."""
    return Library(request.user, request.session.session_key)


def _owner_kwargs(request):
    if request.user.is_authenticated:
        return {"user": request.user, "session_key": ""}
    return {"user": None, "session_key": get_session_key(request)}


from moviegraph.neo4j import get_db

def _sync_edge_to_neo4j(user, movie_slug, kind):
    """Sync the watch edge to Neo4j for visualization."""
    if not user or not user.is_authenticated:
        return
        
    db = get_db()
    username = user.username
    profile = Profile.objects.filter(user=user).first()
    name = profile.handle if profile else username
    
    # First remove any existing edge
    db.run(
        "MATCH (u:User {username: $username})-[r:WATCHED|WATCHLIST]->(m:Movie {id: $movie_slug}) DELETE r",
        username=username,
        movie_slug=movie_slug
    )
    
    if kind is not None:
        rel_type = "WATCHED" if kind == LibraryEntry.WATCHED else "WATCHLIST"
        db.run(
            f"""
            MERGE (u:User {{username: $username}})
            SET u.name = $name
            WITH u
            MATCH (m:Movie {{id: $movie_slug}})
            MERGE (u)-[:{rel_type}]->(m)
            """,
            username=username,
            name=name,
            movie_slug=movie_slug
        )

@transaction.atomic
def set_entry(request, movie: Movie, kind):
    """
    Put `movie` in one of the lists (or neither, when `kind` is None).

    Returns the kind now in effect, so callers can report the new state back to
    the UI without a second query.
    """
    owner = _owner_kwargs(request)
    existing = LibraryEntry.objects.filter(movie=movie, **owner).first()
    user = request.user

    if kind is None:
        if existing:
            existing.delete()
        _sync_edge_to_neo4j(user, movie.slug, None)
        return None

    if existing:
        if existing.kind != kind:
            existing.kind = kind
            existing.save(update_fields=["kind"])
        _sync_edge_to_neo4j(user, movie.slug, kind)
        return kind
# This is control database
# I am using SQLITE and Neo4j
# SQLITE for authenticatin and data storage handling
# Neo4j for Movie graph and recommendation handling
    LibraryEntry.objects.create(movie=movie, kind=kind, **owner)
    _sync_edge_to_neo4j(user, movie.slug, kind)
    return kind


def toggle_watched(request, movie: Movie):
    """
    Flip the WATCHED edge.

    Marking watched also clears the watchlist edge, because `set_entry` moves
    the single row rather than creating a second one.
    """
    library = get_library(request)
    if library.is_watched(movie.slug):
        return set_entry(request, movie, None)
    return set_entry(request, movie, LibraryEntry.WATCHED)


def toggle_watchlist(request, movie: Movie):
    """Flip the WATCHLISTED edge."""
    library = get_library(request)
    if library.is_in_watchlist(movie.slug):
        return set_entry(request, movie, None)
    return set_entry(request, movie, LibraryEntry.WATCHLIST)


@transaction.atomic
def merge_session_library(user, session_key):
    """
    Hand an anonymous library to the account that just signed in or up.

    `session_key` must be the key captured *before* `login()` ran: Django cycles
    the key on login to prevent session fixation, so by the time the view has a
    user the anonymous rows are filed under a key that no longer exists on the
    request. Entries the account already has win.
    """
    if not session_key:
        return 0

    anonymous = LibraryEntry.objects.filter(user__isnull=True, session_key=session_key)
    if not anonymous.exists():
        return 0

    owned_movie_ids = set(
        LibraryEntry.objects.filter(user=user).values_list("movie_id", flat=True)
    )

    moved = 0
    for entry in anonymous:
        if entry.movie_id in owned_movie_ids:
            entry.delete()
            continue
        entry.user = user
        entry.session_key = ""
        entry.save(update_fields=["user", "session_key"])
        moved += 1
    return moved


def ensure_profile(user) -> Profile:
    """Every account gets a handle; derived from the username on first use."""
    profile = Profile.objects.filter(user=user).first()
    if profile:
        return profile

    base = "@{}".format(user.username.lower().replace(" ", ""))
    handle = base
    suffix = 2
    while Profile.objects.filter(handle=handle).exists():
        handle = "{}{}".format(base, suffix)
        suffix += 1
    return Profile.objects.create(user=user, handle=handle)

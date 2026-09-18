"""The viewer's own state, needed by the header on every page."""

from .services import ensure_profile, get_library


def viewer(request):
    """
    `library` drives the watched badge and watchlist toggle on every card, and
    the counts in the profile menu.

    Admin and static requests have no `user` attribute set up the way the site
    expects, so this stays defensive — a missing library must never 500 a page.
    """
    if not hasattr(request, "user"):
        return {}

    try:
        library = get_library(request)
    except Exception:  # pragma: no cover - defensive; DB not ready, etc.
        library = None

    profile = None
    if request.user.is_authenticated:
        profile = ensure_profile(request.user)

    return {"library": library, "profile": profile}

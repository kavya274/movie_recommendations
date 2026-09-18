"""
My Movies, the WATCHED / WATCHLISTED mutations, and authentication.

Every mutation is a POST and every POST works twice over:

  * without JavaScript it is a plain form submit that redirects back to where
    you were, so the site is fully usable with scripting off;
  * with JavaScript `static/js/app.js` sends the same POST via fetch, reads the
    JSON body and updates the button in place.

The two paths share one view — the only difference is what gets returned.
"""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme

from catalog.models import Movie

from .models import LibraryEntry
from .services import (
    ensure_profile,
    get_library,
    merge_session_library,
    toggle_watched,
    toggle_watchlist,
)


def my_movies(request):
    """The two lists — watched and watchlist — as tabs on one page."""
    library = get_library(request)
    tab = request.GET.get("tab")
    if tab not in (LibraryEntry.WATCHED, LibraryEntry.WATCHLIST):
        tab = LibraryEntry.WATCHED

    return render(
        request,
        "library/my_movies.html",
        {
            "nav_section": "my-movies",
            "active_tab": tab,
            "movies": library.movies(tab),
            "watched_count": library.watched_count,
            "watchlist_count": library.watchlist_count,
            "favourite_genres": library.favourite_genres(),
        },
    )


# -- Mutations ------------------------------------------------------------


@require_POST
def toggle_watched_view(request, slug):
    """POST /library/watched/<slug>/ — flip (User)-[:WATCHED]->(Movie)."""
    movie = get_object_or_404(Movie, slug=slug)
    kind = toggle_watched(request, movie)
    return _respond(request, movie, kind, removed_kind=LibraryEntry.WATCHED)


@require_POST
def toggle_watchlist_view(request, slug):
    """POST /library/watchlist/<slug>/ — flip (User)-[:WATCHLISTED]->(Movie)."""
    movie = get_object_or_404(Movie, slug=slug)
    kind = toggle_watchlist(request, movie)
    return _respond(request, movie, kind, removed_kind=LibraryEntry.WATCHLIST)


def _respond(request, movie, kind, removed_kind):
    """JSON for fetch callers, a redirect back for plain form posts."""
    library = get_library(request)

    if _wants_json(request):
        return JsonResponse(
            {
                "id": movie.slug,
                "watched": kind == LibraryEntry.WATCHED,
                "watchlist": kind == LibraryEntry.WATCHLIST,
                "watchedCount": library.watched_count,
                "watchlistCount": library.watchlist_count,
            }
        )

    if kind is None:
        messages.success(request, "Removed {} from your {}.".format(movie.title, removed_kind))
    elif kind == LibraryEntry.WATCHED:
        messages.success(request, "Marked {} as watched.".format(movie.title))
    else:
        messages.success(request, "Added {} to your watchlist.".format(movie.title))

    return redirect(_safe_next(request, fallback=movie.get_absolute_url()))


def _wants_json(request):
    return (
        request.headers.get("X-Requested-With") == "fetch"
        or "application/json" in request.headers.get("Accept", "")
    )


def _safe_next(request, fallback):
    """
    Honour `?next=` / the form's hidden field, but only for our own URLs —
    an open redirect here would be a phishing gift.
    """
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_secure=request.is_secure()
    ):
        return candidate
    return fallback


# -- Authentication -------------------------------------------------------


def login_view(request):
    """
    Sign in, then adopt whatever the visitor built up while anonymous.

    The session key is read before `login()` because Django cycles it on
    success — see `services.merge_session_library`.
    """
    if request.user.is_authenticated:
        return redirect("catalog:home")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        anonymous_key = request.session.session_key
        user = form.get_user()
        login(request, user)
        ensure_profile(user)
        moved = merge_session_library(user, anonymous_key)
        if moved:
            messages.success(
                request, "Welcome back — we kept the {} movies you saved.".format(moved)
            )
        return redirect(_safe_login_redirect(request))

    return render(request, "registration/login.html", {"form": form})


def signup_view(request):
    """Create an account, keeping the anonymous library."""
    if request.user.is_authenticated:
        return redirect("catalog:home")

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        anonymous_key = request.session.session_key
        user = form.save()
        login(request, user)
        ensure_profile(user)
        merge_session_library(user, anonymous_key)
        messages.success(request, "Welcome to MovieGraph.")
        return redirect(_safe_login_redirect(request))

    return render(request, "registration/signup.html", {"form": form})


@require_POST
def logout_view(request):
    """POST only — a GET logout would let any page sign you out."""
    logout(request)
    messages.success(request, "Signed out.")
    return redirect("catalog:home")


def _safe_login_redirect(request):
    candidate = request.POST.get("next") or request.GET.get("next")
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_secure=request.is_secure()
    ):
        return candidate
    return resolve_url("catalog:home")


# -- JSON API -------------------------------------------------------------


def api_me(request):
    """GET /api/me/ — the viewer's edges, in the prototype's `User` shape."""
    library = get_library(request)
    profile = ensure_profile(request.user) if request.user.is_authenticated else None

    return JsonResponse(
        {
            "id": request.user.pk if request.user.is_authenticated else None,
            "name": profile.display_name if profile else "Guest",
            "handle": profile.handle if profile else "",
            "isAuthenticated": request.user.is_authenticated,
            "watched": library.watched_slugs,
            "watchlist": library.watchlist_slugs,
            "favoriteGenres": library.favourite_genres(),
            "urls": {
                "login": reverse("library:login"),
                "myMovies": reverse("library:my_movies"),
            },
        }
    )

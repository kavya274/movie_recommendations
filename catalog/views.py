"""
The catalog pages.

Everything server-rendered: filtering, sorting and search all happen here rather
than in the browser, so the pages work without JavaScript and every state has a
URL you can share. The JS in `static/js/app.js` only adds the niceties (the
search palette, rail arrows, optimistic library toggles).
"""

from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from library.services import get_library

from . import recommendations, selectors
from .models import EditorialPick


def home(request):
    """Hero + the three recommendation rails + browse by genre."""
    library = get_library(request)

    pick = EditorialPick.objects.filter(is_active=True).first()
    featured = selectors.get_movie(pick.movie.slug) if pick else (selectors.get_movies()[0] if selectors.get_movies() else None)

    seed = library.movies("watched")[0] if library.watched_slugs else None
    because = recommendations.because_you_watched(
        seed, limit=8, exclude=library.watched_slugs
    ) if seed else None

    # Browse-by-genre is the same filtered query Discover runs, capped.
    genre = selectors.resolve_genre(request.GET.get("genre"))
    browse_results = selectors.browse(genre=genre, sort="rating")
    browse_total = len(browse_results)

    return render(
        request,
        "catalog/home.html",
        {
            "nav_section": "home",
            "featured": featured,
            "featured_eyebrow": pick.eyebrow if pick else "Featured today",
            "featured_kicker": pick.kicker if pick else "Explore movies connected to what you love.",
            "for_you": recommendations.for_you(library, limit=10),
            "because_you_watched": because,
            "trending": recommendations.trending(limit=8),
            "browse_genre": genre,
            "browse_movies": browse_results[:12],
            "browse_total": browse_total,
            "browse_has_more": browse_total > 12,
        },
    )


def discover(request):
    """The whole catalog, filtered by genre and sorted."""
    genre = selectors.resolve_genre(request.GET.get("genre"))
    sort = selectors.resolve_sort(request.GET.get("sort"))
    results = list(selectors.browse(genre=genre, sort=sort))

    return render(
        request,
        "catalog/discover.html",
        {
            "nav_section": "discover",
            "movies": results,
            "result_count": len(results),
            "active_genre": genre,
            "active_sort": sort,
            "sort_options": selectors.SORT_OPTIONS,
        },
    )


def movie_detail(request, slug):
    """One movie, its credits, and the -[:SIMILAR_TO]-> rail."""
    movie = selectors.get_movie(slug)
    if movie is None:
        raise Http404("No movie with that id.")

    return render(
        request,
        "catalog/movie_detail.html",
        {
            "nav_section": "discover",
            "movie": movie,
            "related": recommendations.related(movie, limit=8),
        },
    )


def search(request):
    """
    Full-page search results.

    The header palette calls `api_search` for its live list; this is the
    no-JavaScript destination behind the same query.
    """
    query = request.GET.get("q", "")
    results = selectors.search_movies(query, limit=24)
    return render(
        request,
        "catalog/search.html",
        {
            "nav_section": "discover",
            "query": query,
            "movies": results,
            "result_count": len(results),
        },
    )


# -- JSON API -------------------------------------------------------------
# Plain `JsonResponse` rather than a framework: these are read-only endpoints
# over the same selectors the pages use, and the shapes match the prototype's
# `types/index.ts` so an existing client can point straight at them.


@require_GET
def api_movies(request):
    """GET /api/movies/?genre=&sort=&limit="""
    genre = selectors.resolve_genre(request.GET.get("genre"))
    sort = selectors.resolve_sort(request.GET.get("sort"))
    queryset = selectors.browse(genre=genre, sort=sort)

    limit = _int_param(request.GET.get("limit"), default=None, maximum=200)
    if limit:
        queryset = queryset[:limit]

    return JsonResponse({"results": [movie.as_dict() for movie in queryset]})


@require_GET
def api_movie(request, slug):
    """GET /api/movies/<slug>/ — the movie plus its related rail."""
    movie = selectors.get_movie(slug)
    if movie is None:
        return JsonResponse({"detail": "Not found."}, status=404)

    return JsonResponse(
        {
            "movie": movie.as_dict(),
            "related": recommendations.related(movie, limit=8).as_dict(),
        }
    )


@require_GET
def api_genres(request):
    """GET /api/genres/"""
    return JsonResponse(
        {
            "results": [
                {"id": genre.slug, "name": genre.name, "slug": genre.slug}
                for genre in selectors.get_genres()
            ]
        }
    )


@require_GET
def api_search(request):
    """GET /api/search/?q= — what the header palette calls as you type."""
    query = request.GET.get("q", "")
    limit = _int_param(request.GET.get("limit"), default=10, maximum=50)
    movies = selectors.search_movies(query, limit=limit)

    library = get_library(request)
    return JsonResponse(
        {
            "query": query,
            "results": [
                {
                    "id": movie.slug,
                    "title": movie.title,
                    "year": movie.year,
                    "rating": float(movie.rating),
                    "poster": movie.poster,
                    "genre": movie.primary_genre,
                    "url": movie.get_absolute_url(),
                    "watched": library.is_watched(movie.slug),
                }
                for movie in movies
            ],
        }
    )


@require_GET
def api_recommendations(request):
    """GET /api/recommendations/ — every rail the home page renders."""
    library = get_library(request)
    seed = library.movies("watched")[0] if library.watched_slugs else None

    rails = [recommendations.for_you(library, limit=10)]
    if seed:
        rails.append(
            recommendations.because_you_watched(seed, limit=8, exclude=library.watched_slugs)
        )
    rails.append(recommendations.trending(limit=8))

    return JsonResponse({"sets": [rail.as_dict() for rail in rails if rail]})


def _int_param(raw, default=None, maximum=100):
    """Parse a query-string integer, clamped — never trust the caller's limit."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < 1:
        return default
    return min(value, maximum)

from django.views.decorators.http import require_POST
import json
from .chatbot import process_chat

@require_POST
def api_chat(request):
    """POST /api/chat/ — handles GraphRAG chatbot requests."""
    try:
        data = json.loads(request.body)
        query = data.get("query", "")
        if not query:
            return JsonResponse({"error": "No query provided"}, status=400)
            
        reply = process_chat(query)
        return JsonResponse({"reply": reply})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

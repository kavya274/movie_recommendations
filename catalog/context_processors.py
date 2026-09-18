"""Catalog data every page's chrome needs."""

from .selectors import get_genres


def navigation(request):
    """
    Genre chips for the search dialog and the mobile nav.

    Deliberately lazy: `get_genres()` returns a queryset, so a template that
    never mentions `genres` costs nothing.
    """
    return {"genres": get_genres()}

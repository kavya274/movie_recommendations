"""
Display helpers — the Django port of the prototype's `lib/format.ts`.

Formatting lives here rather than in the views so a movie renders identically
whichever page it appears on.
"""

from urllib.parse import urlencode

from django import template
from django.urls import reverse

register = template.Library()


@register.filter
def runtime(minutes):
    """169 -> "2h 49m"."""
    if not minutes:
        return "—"
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return "—"
    if minutes <= 0:
        return "—"

    hours, mins = divmod(minutes, 60)
    if not hours:
        return "{}m".format(mins)
    if not mins:
        return "{}h".format(hours)
    return "{}h {}m".format(hours, mins)


@register.filter
def rating(value):
    """8 -> "8.0" — always one decimal, so the rail's numbers line up."""
    try:
        return "{:.1f}".format(float(value))
    except (TypeError, ValueError):
        return "—"


@register.filter
def match(score):
    """0.97 -> "97% match"."""
    try:
        return "{}% match".format(int(round(float(score) * 100)))
    except (TypeError, ValueError):
        return ""


@register.filter
def initials(name):
    """"Alex Rivera" -> "AR"."""
    parts = [part for part in str(name or "").split(" ") if part][:2]
    return "".join(part[0].upper() for part in parts) or "?"


@register.filter
def under(index, count):
    """
    `forloop.counter0|under:priority_count` — true for the first N items.

    Django has no numeric comparison in `{% if %}` against a filtered value, and
    the rails need "load the first four posters eagerly".
    """
    try:
        return int(index) < int(count)
    except (TypeError, ValueError):
        return False


@register.simple_tag
def discover_url(genre=None, sort=None):
    """
    Builds `/discover?genre=&sort=` without emitting empty params.

    Used by the genre chips, so the current sort survives a genre change.
    """
    params = {}
    if genre and genre != "All":
        params["genre"] = genre
    if sort and sort != "rating":
        params["sort"] = sort
    base = reverse("catalog:discover")
    query = urlencode(params)
    return "{}?{}".format(base, query) if query else base

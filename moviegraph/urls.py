"""
URL map.

Pages live at the same paths the Next.js prototype used (`/`, `/discover`,
`/movies/<id>`, `/my-movies`, `/login`) so existing links keep working, and the
JSON API is mounted under `/api/`.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from catalog import urls as catalog_urls
from library import urls as library_urls

api_patterns = catalog_urls.api_urlpatterns + library_urls.api_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include((api_patterns, "api"), namespace="api")),
    path("", include(library_urls)),
    path("", include(catalog_urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / "static")

# 404 / 500 fall through to Django's default handlers, which render
# `templates/404.html` and `templates/500.html`.

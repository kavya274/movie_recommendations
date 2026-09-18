"""
Admin for the catalog.

The through-models are inlines so an editor can reorder a movie's genres, cast
and similar-to edges from one page — ordering is meaningful here, it drives
what the cards and rails print.
"""

from django.contrib import admin

from .models import (
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


class MovieGenreInline(admin.TabularInline):
    model = MovieGenre
    extra = 1
    autocomplete_fields = ["genre"]


class CreditInline(admin.TabularInline):
    model = Credit
    extra = 1
    autocomplete_fields = ["person"]


class SimilarityInline(admin.TabularInline):
    model = Similarity
    fk_name = "source"
    extra = 1
    autocomplete_fields = ["target"]
    verbose_name = "similar movie"
    verbose_name_plural = "similar movies"


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ["title", "year", "rating", "director", "genre_list"]
    list_filter = ["year", "movie_genres__genre"]
    search_fields = ["title", "slug", "director__name", "credits__person__name"]
    prepopulated_fields = {"slug": ["title"]}
    autocomplete_fields = ["director"]
    inlines = [MovieGenreInline, CreditInline, SimilarityInline]

    def get_queryset(self, request):
        return super().get_queryset(request).with_edges()

    @admin.display(description="genres")
    def genre_list(self, obj):
        return ", ".join(obj.genre_names)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "position", "movie_count"]
    prepopulated_fields = {"slug": ["name"]}
    search_fields = ["name"]
    ordering = ["position"]

    @admin.display(description="movies")
    def movie_count(self, obj):
        return obj.movies.count()


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ["name", "directed_count", "acted_count"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}

    @admin.display(description="directed")
    def directed_count(self, obj):
        return obj.directed.count()

    @admin.display(description="acted in")
    def acted_count(self, obj):
        return obj.credits.count()


@admin.register(EditorialPick)
class EditorialPickAdmin(admin.ModelAdmin):
    """The home page hero. The newest active row wins."""

    list_display = ["movie", "eyebrow", "is_active", "created_at"]
    list_filter = ["is_active"]
    autocomplete_fields = ["movie"]


@admin.register(TrendingEntry)
class TrendingEntryAdmin(admin.ModelAdmin):
    list_display = ["movie", "score", "reason"]
    autocomplete_fields = ["movie"]
    ordering = ["-score"]


@admin.register(ColdStartPick)
class ColdStartPickAdmin(admin.ModelAdmin):
    """Shown as "Recommended for you" until a visitor has watch history."""

    list_display = ["movie", "score", "reason"]
    autocomplete_fields = ["movie"]
    ordering = ["-score"]

"""Admin for the per-user edges."""

from django.contrib import admin

from .models import LibraryEntry, Profile


@admin.register(LibraryEntry)
class LibraryEntryAdmin(admin.ModelAdmin):
    list_display = ["owner", "movie", "kind", "created_at"]
    list_filter = ["kind", "created_at"]
    search_fields = ["user__username", "movie__title", "session_key"]
    autocomplete_fields = ["movie"]
    raw_id_fields = ["user"]
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "movie")

    @admin.display(description="owner")
    def owner(self, obj):
        if obj.user:
            return obj.user.username
        return "guest ({}...)".format(obj.session_key[:8])


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ["handle", "user", "watched_count"]
    search_fields = ["handle", "user__username"]
    raw_id_fields = ["user"]

    @admin.display(description="watched")
    def watched_count(self, obj):
        return obj.user.library_entries.filter(kind=LibraryEntry.WATCHED).count()

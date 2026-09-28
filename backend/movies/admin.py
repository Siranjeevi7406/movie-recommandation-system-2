from django.contrib import admin
from .models import MovieViewLog, RecommendationEvent, SearchLog, UserMovieRating, WatchlistItem


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ["query_label", "genre", "year", "language", "minimum_rating", "result_count", "user", "searched_at"]
    list_filter = ["searched_at", "language", "year", "genre"]
    search_fields = ["query", "user__username", "ip_address"]
    readonly_fields = [field.name for field in SearchLog._meta.fields]
    date_hierarchy = "searched_at"
    list_per_page = 50

    @admin.display(description="Query")
    def query_label(self, obj):
        return obj.query or "Browse movies"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MovieViewLog)
class MovieViewLogAdmin(admin.ModelAdmin):
    list_display = ["title", "tmdb_id", "user", "ip_address", "viewed_at"]
    list_filter = ["viewed_at"]
    search_fields = ["title", "tmdb_id", "user__username", "ip_address"]
    readonly_fields = [field.name for field in MovieViewLog._meta.fields]
    date_hierarchy = "viewed_at"
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RecommendationEvent)
class RecommendationEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "title", "tmdb_id", "algorithm", "score", "user", "created_at"]
    list_filter = ["event_type", "algorithm", "created_at"]
    search_fields = ["title", "tmdb_id", "user__username"]
    readonly_fields = [field.name for field in RecommendationEvent._meta.fields]
    date_hierarchy = "created_at"
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

admin.site.register(WatchlistItem)
admin.site.register(UserMovieRating)

admin.site.site_header = "CinePick Administration"
admin.site.site_title = "CinePick Admin"
admin.site.index_title = "Users, watchlists, ratings and analytics"

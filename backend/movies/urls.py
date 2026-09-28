from django.urls import path
from .views import admin_analytics, analytics_export, current_user, genres, health_check, movie_detail, movies, recommendation_event, recommendations, register, user_rating, watchlist, watchlist_item

urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("genres/", genres, name="genres"),
    path("movies/", movies, name="movies"),
    path("movies/<int:movie_id>/", movie_detail, name="movie-detail"),
    path("auth/register/", register, name="register"),
    path("auth/me/", current_user, name="current-user"),
    path("watchlist/", watchlist, name="watchlist"),
    path("watchlist/<int:tmdb_id>/", watchlist_item, name="watchlist-item"),
    path("ratings/<int:tmdb_id>/", user_rating, name="user-rating"),
    path("recommendations/", recommendations, name="recommendations"),
    path("recommendations/events/", recommendation_event, name="recommendation-event"),
    path("admin/analytics/", admin_analytics, name="admin-analytics"),
    path("admin/analytics/export/", analytics_export, name="analytics-export"),
]

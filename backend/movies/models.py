from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WatchlistItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="watchlist")
    tmdb_id = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    poster_url = models.URLField(blank=True)
    year = models.CharField(max_length=4, blank=True)
    genre_ids = models.JSONField(default=list, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "tmdb_id"], name="unique_user_movie")]
        ordering = ["-added_at"]


class UserMovieRating(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="movie_ratings")
    tmdb_id = models.PositiveIntegerField()
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    genre_ids = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "tmdb_id"], name="unique_user_rating")]


class SearchLog(models.Model):
    query = models.CharField(max_length=255, blank=True, db_index=True)
    genre = models.CharField(max_length=30, blank=True, db_index=True)
    year = models.CharField(max_length=4, blank=True, db_index=True)
    language = models.CharField(max_length=20, blank=True, db_index=True)
    minimum_rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    result_count = models.PositiveIntegerField(default=0)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="search_logs")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    searched_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-searched_at"]
        indexes = [
            models.Index(fields=["searched_at", "query"], name="movies_sea_time_query_idx"),
            models.Index(fields=["searched_at", "result_count"], name="movies_sea_time_result_idx"),
        ]

    def __str__(self):
        return self.query or "Browse movies"


class MovieViewLog(models.Model):
    tmdb_id = models.PositiveIntegerField(db_index=True)
    title = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="movie_views")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-viewed_at"]
        indexes = [models.Index(fields=["viewed_at", "tmdb_id"], name="movies_view_time_movie_idx")]

    def __str__(self):
        return self.title or f"TMDB {self.tmdb_id}"


class RecommendationEvent(models.Model):
    EVENT_CHOICES = [("impression", "Impression"), ("click", "Click")]
    ALGORITHM_CHOICES = [
        ("popular", "Popular fallback"),
        ("content", "Content based"),
        ("collaborative", "Collaborative"),
        ("hybrid", "Hybrid"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recommendation_events",
    )
    tmdb_id = models.PositiveIntegerField(db_index=True)
    title = models.CharField(max_length=255, blank=True)
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES, db_index=True)
    algorithm = models.CharField(max_length=20, choices=ALGORITHM_CHOICES, default="hybrid", db_index=True)
    score = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at", "event_type"], name="movies_rec_time_event_idx"),
            models.Index(fields=["user", "tmdb_id", "event_type"], name="movies_rec_user_movie_idx"),
        ]

    def __str__(self):
        return f"{self.event_type}: {self.title or self.tmdb_id}"

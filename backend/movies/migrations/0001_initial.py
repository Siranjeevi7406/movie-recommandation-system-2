from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="WatchlistItem", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("tmdb_id", models.PositiveIntegerField()), ("title", models.CharField(max_length=255)), ("poster_url", models.URLField(blank=True)), ("year", models.CharField(blank=True, max_length=4)), ("genre_ids", models.JSONField(blank=True, default=list)), ("added_at", models.DateTimeField(auto_now_add=True)), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="watchlist", to=settings.AUTH_USER_MODEL))], options={"ordering": ["-added_at"]}),
        migrations.CreateModel(name="UserMovieRating", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("tmdb_id", models.PositiveIntegerField()), ("rating", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)])), ("genre_ids", models.JSONField(blank=True, default=list)), ("updated_at", models.DateTimeField(auto_now=True)), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="movie_ratings", to=settings.AUTH_USER_MODEL))]),
        migrations.AddConstraint(model_name="watchlistitem", constraint=models.UniqueConstraint(fields=("user", "tmdb_id"), name="unique_user_movie")),
        migrations.AddConstraint(model_name="usermovierating", constraint=models.UniqueConstraint(fields=("user", "tmdb_id"), name="unique_user_rating")),
    ]

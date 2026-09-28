from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import UserMovieRating, WatchlistItem


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name"]
    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class WatchlistSerializer(serializers.ModelSerializer):
    class Meta:
        model = WatchlistItem
        fields = ["id", "tmdb_id", "title", "poster_url", "year", "genre_ids", "added_at"]
        read_only_fields = ["id", "added_at"]


class RatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMovieRating
        fields = ["tmdb_id", "rating", "genre_ids", "updated_at"]
        read_only_fields = ["updated_at"]

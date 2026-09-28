from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserMovieRating, WatchlistItem


class AccountAndLibraryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="viewer", password="StrongPass123!")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}")

    def test_watchlist_add_and_list(self):
        payload = {"tmdb_id": 550, "title": "Fight Club", "poster_url": "", "year": "1999", "genre_ids": [18]}
        self.assertEqual(self.client.post("/api/watchlist/", payload, format="json").status_code, 201)
        self.assertEqual(self.client.get("/api/watchlist/").json()[0]["tmdb_id"], 550)
        self.assertEqual(WatchlistItem.objects.count(), 1)

    def test_rating_is_updated_not_duplicated(self):
        self.client.put("/api/ratings/550/", {"rating": 8, "genre_ids": [18]}, format="json")
        self.client.put("/api/ratings/550/", {"rating": 9, "genre_ids": [18]}, format="json")
        self.assertEqual(UserMovieRating.objects.get().rating, 9)
        self.assertEqual(UserMovieRating.objects.count(), 1)

    def test_anonymous_watchlist_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get("/api/watchlist/").status_code, 401)


class PublicApiTests(TestCase):
    @patch("movies.views.TMDBClient.genres", return_value={"genres": [{"id": 18, "name": "Drama"}]})
    def test_genres(self, _mock):
        with self.settings(TMDB_API_TOKEN="token"):
            self.assertEqual(self.client.get("/api/genres/").status_code, 200)

    def test_health(self):
        self.assertEqual(self.client.get("/api/health/").json()["status"], "ok")

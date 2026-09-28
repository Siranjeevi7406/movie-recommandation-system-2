from datetime import date
import socket

import urllib3.util.connection as urllib3_connection


# Some Windows networks reset TMDB connections made over IPv6 even though
# IPv4 works correctly. Configure urllib3 before importing requests.
def force_ipv4():
    return socket.AF_INET


urllib3_connection.allowed_gai_family = force_ipv4

import requests  # noqa: E402
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class TMDBConfigurationError(RuntimeError):
    """Raised when the TMDB client is missing required configuration."""


class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
    BACKDROP_BASE_URL = "https://image.tmdb.org/t/p/w1280"
    CONNECT_TIMEOUT = 10
    READ_TIMEOUT = 20

    ALLOWED_SORTS = {
        "popularity.desc",
        "vote_average.desc",
        "primary_release_date.desc",
        "revenue.desc",
    }

    def __init__(self, token):
        token = (token or "").strip()
        if not token:
            raise TMDBConfigurationError(
                "TMDB_API_TOKEN is missing. Add the API Read Access Token "
                "to backend/.env and restart Django."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "CinePick-College-Project/1.0",
            }
        )

        retry_policy = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        self.session.mount("https://", adapter)

    def _get(self, endpoint, params=None):
        response = self.session.get(
            f"{self.BASE_URL}{endpoint}",
            params=params or {},
            timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _positive_int(value, default=1, maximum=500):
        if not value:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Page must be a number.") from exc
        return max(1, min(parsed, maximum))

    @staticmethod
    def _rating(value):
        if value in (None, ""):
            return 0.0
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Rating must be a number between 0 and 10.") from exc
        if not 0 <= parsed <= 10:
            raise ValueError("Rating must be between 0 and 10.")
        return parsed

    def genres(self):
        return self._get("/genre/movie/list", {"language": "en"})

    def movies(
        self,
        query="",
        genre="",
        year="",
        language="",
        rating="",
        sort="",
        page="",
    ):
        page_number = self._positive_int(page)
        minimum_rating = self._rating(rating)

        if year:
            try:
                year_number = int(year)
            except (TypeError, ValueError) as exc:
                raise ValueError("Year must be a number.") from exc
            if not 1874 <= year_number <= date.today().year + 5:
                raise ValueError("Year is outside the supported range.")

        if query:
            params = {
                "query": query,
                "page": page_number,
                "include_adult": "false",
                "language": "en-US",
            }
            if year:
                params["primary_release_year"] = year
            payload = self._get("/search/movie", params)
        else:
            params = {
                "page": page_number,
                "include_adult": "false",
                "include_video": "false",
                "language": "en-US",
                "sort_by": (
                    sort if sort in self.ALLOWED_SORTS else "popularity.desc"
                ),
                "vote_count.gte": 50 if minimum_rating else 0,
            }
            if genre:
                params["with_genres"] = genre
            if year:
                params["primary_release_year"] = year
            if language:
                params["with_original_language"] = language
            if minimum_rating:
                params["vote_average.gte"] = minimum_rating
            payload = self._get("/discover/movie", params)

        results = payload.get("results", [])

        # TMDB title search does not support every discover filter, so those
        # filters are applied to the current result page after searching.
        if query:
            if genre:
                results = [
                    movie
                    for movie in results
                    if str(genre) in map(str, movie.get("genre_ids", []))
                ]
            if language:
                results = [
                    movie
                    for movie in results
                    if movie.get("original_language") == language
                ]
            if minimum_rating:
                results = [
                    movie
                    for movie in results
                    if float(movie.get("vote_average") or 0) >= minimum_rating
                ]

        return {
            "page": payload.get("page", page_number),
            "total_pages": min(payload.get("total_pages", 1), 500),
            "total_results": payload.get("total_results", len(results)),
            "results": [self._normalize(movie) for movie in results],
        }

    def movie_detail(self, movie_id):
        movie = self._get(
            f"/movie/{movie_id}",
            {
                "language": "en-US",
                "append_to_response": (
                    "credits,videos,recommendations,external_ids,watch/providers"
                ),
            },
        )

        videos = movie.get("videos", {}).get("results", [])
        youtube_videos = [
            video for video in videos if video.get("site") == "YouTube"
        ]
        trailer = next(
            (
                video
                for video in youtube_videos
                if video.get("type") == "Trailer" and video.get("official")
            ),
            None,
        )
        trailer = trailer or next(
            (
                video
                for video in youtube_videos
                if video.get("type") == "Trailer"
            ),
            None,
        )
        trailer = trailer or (youtube_videos[0] if youtube_videos else None)

        crew = movie.get("credits", {}).get("crew", [])
        director = next(
            (person.get("name") for person in crew if person.get("job") == "Director"),
            None,
        )

        cast = []
        for person in movie.get("credits", {}).get("cast", [])[:12]:
            profile_path = person.get("profile_path")
            cast.append(
                {
                    "id": person.get("id"),
                    "name": person.get("name"),
                    "character": person.get("character"),
                    "profile_url": (
                        f"{self.IMAGE_BASE_URL}{profile_path}"
                        if profile_path
                        else None
                    ),
                }
            )

        recommendations = [
            self._normalize(item)
            for item in movie.get("recommendations", {}).get("results", [])[:10]
        ]

        imdb_id = movie.get("external_ids", {}).get("imdb_id")
        imdb_rating = self._get_imdb_rating(imdb_id)
        region = getattr(settings, "OTT_REGION", "IN")
        provider_data = (
            movie.get("watch/providers", {}).get("results", {}).get(region, {})
        )

        providers = []
        seen_providers = set()
        for group in ("flatrate", "free", "ads", "rent", "buy"):
            for provider in provider_data.get(group, []):
                provider_key = (group, provider.get("provider_id"))
                if provider_key in seen_providers:
                    continue
                seen_providers.add(provider_key)
                logo_path = provider.get("logo_path")
                providers.append(
                    {
                        "id": provider.get("provider_id"),
                        "name": provider.get("provider_name"),
                        "type": group,
                        "logo_url": (
                            f"{self.IMAGE_BASE_URL}{logo_path}"
                            if logo_path
                            else None
                        ),
                    }
                )

        poster_path = movie.get("poster_path")
        backdrop_path = movie.get("backdrop_path")
        release_date = movie.get("release_date") or ""

        return {
            "id": movie.get("id"),
            "title": movie.get("title"),
            "tagline": movie.get("tagline") or "",
            "overview": movie.get("overview") or "No overview available.",
            "release_date": release_date,
            "year": release_date[:4] or "—",
            "runtime": movie.get("runtime") or 0,
            "rating": round(float(movie.get("vote_average") or 0), 1),
            "vote_count": movie.get("vote_count") or 0,
            "language": (movie.get("original_language") or "").upper(),
            "status": movie.get("status"),
            "genres": movie.get("genres") or [],
            "director": director,
            "poster_url": (
                f"{self.IMAGE_BASE_URL}{poster_path}" if poster_path else None
            ),
            "backdrop_url": (
                f"{self.BACKDROP_BASE_URL}{backdrop_path}"
                if backdrop_path
                else None
            ),
            "trailer": (
                {
                    "name": trailer.get("name"),
                    "youtube_key": trailer.get("key"),
                    "url": f"https://www.youtube.com/watch?v={trailer.get('key')}",
                }
                if trailer
                else None
            ),
            "imdb_rating": imdb_rating,
            "imdb_url": (
                f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None
            ),
            "ott": {
                "region": region,
                "link": provider_data.get("link"),
                "providers": providers,
            },
            "cast": cast,
            "recommendations": recommendations,
        }

    def _get_imdb_rating(self, imdb_id):
        api_key = getattr(settings, "OMDB_API_KEY", "")
        if not imdb_id or not api_key:
            return None

        try:
            response = self.session.get(
                "https://www.omdbapi.com/",
                params={"apikey": api_key, "i": imdb_id},
                timeout=(self.CONNECT_TIMEOUT, self.READ_TIMEOUT),
            )
            response.raise_for_status()
            payload = response.json()
            rating = payload.get("imdbRating")
            return rating if rating not in (None, "N/A") else None
        except (requests.RequestException, ValueError):
            # Movie details should still load when OMDb is unavailable.
            return None

    def _normalize(self, movie):
        release_date = movie.get("release_date") or ""
        poster_path = movie.get("poster_path")
        backdrop_path = movie.get("backdrop_path")

        return {
            "id": movie.get("id"),
            "title": movie.get("title") or movie.get("original_title"),
            "overview": movie.get("overview") or "No overview available.",
            "year": release_date[:4] or "—",
            "release_date": release_date,
            "language": (movie.get("original_language") or "").upper(),
            "rating": round(float(movie.get("vote_average") or 0), 1),
            "vote_count": movie.get("vote_count") or 0,
            "genre_ids": movie.get("genre_ids") or [],
            "poster_url": (
                f"{self.IMAGE_BASE_URL}{poster_path}" if poster_path else None
            ),
            "backdrop_url": (
                f"{self.BACKDROP_BASE_URL}{backdrop_path}"
                if backdrop_path
                else None
            ),
        }

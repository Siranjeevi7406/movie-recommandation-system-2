import csv
import requests
from io import StringIO

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Avg, Count
from django.db.models.functions import Lower, TruncDate
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
from requests import RequestException
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .tmdb import TMDBClient, TMDBConfigurationError
from .ml import rank_candidates, user_profile
from .models import MovieViewLog, RecommendationEvent, SearchLog, UserMovieRating, WatchlistItem
from .serializers import RatingSerializer, RegisterSerializer, WatchlistSerializer


@api_view(["GET"])
def health_check(request):
    return Response({"status": "ok", "message": "CinePick API is running"})


def tmdb_error_response(exc):
    if isinstance(exc, TMDBConfigurationError):
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"detail": "The movie service is temporarily unavailable."}, status=status.HTTP_502_BAD_GATEWAY)


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@api_view(["GET"])
def genres(request):
    try:
        return Response(TMDBClient(settings.TMDB_API_TOKEN).genres())
    except (TMDBConfigurationError, RequestException) as exc:
        return tmdb_error_response(exc)


@api_view(["GET"])
def movies(request):
    allowed = {"query", "genre", "year", "language", "rating", "sort", "page"}
    filters = {key: request.query_params.get(key, "").strip() for key in allowed}
    try:
        data = TMDBClient(settings.TMDB_API_TOKEN).movies(**filters)
        has_search_or_filter = any(
            filters.get(key)
            for key in ("query", "genre", "year", "language", "rating")
        )
        if filters.get("page", "1") in ("", "1") and has_search_or_filter:
            minimum_rating = filters.get("rating") or None
            SearchLog.objects.create(
                query=filters.get("query", "")[:255],
                genre=filters.get("genre", "")[:30],
                year=filters.get("year", "")[:4],
                language=filters.get("language", "")[:20],
                minimum_rating=minimum_rating,
                result_count=data.get("total_results", 0),
                user=request.user if request.user.is_authenticated else None,
                ip_address=get_client_ip(request),
            )
        return Response(data)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except (TMDBConfigurationError, RequestException) as exc:
        return tmdb_error_response(exc)


@api_view(["GET"])
def movie_detail(request, movie_id):
    try:
        data = TMDBClient(settings.TMDB_API_TOKEN).movie_detail(movie_id)
        MovieViewLog.objects.create(
            tmdb_id=movie_id,
            title=(data.get("title") or "")[:255],
            user=request.user if request.user.is_authenticated else None,
            ip_address=get_client_ip(request),
        )
        return Response(data)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return Response({"detail": "Movie not found."}, status=status.HTTP_404_NOT_FOUND)
        return tmdb_error_response(exc)
    except (TMDBConfigurationError, RequestException) as exc:
        return tmdb_error_response(exc)


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    return Response({"id": user.id, "username": user.username, "email": user.email}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Return the signed-in user's role for frontend routing."""
    return Response({
        "id": request.user.id,
        "username": request.user.username,
        "email": request.user.email,
        "is_staff": request.user.is_staff,
        "is_superuser": request.user.is_superuser,
    })


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def watchlist(request):
    if request.method == "GET":
        return Response(WatchlistSerializer(request.user.watchlist.all(), many=True).data)
    serializer = WatchlistSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    item, created = WatchlistItem.objects.update_or_create(user=request.user, tmdb_id=serializer.validated_data["tmdb_id"], defaults=serializer.validated_data)
    return Response(WatchlistSerializer(item).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def watchlist_item(request, tmdb_id):
    deleted, _ = WatchlistItem.objects.filter(user=request.user, tmdb_id=tmdb_id).delete()
    return Response(status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def user_rating(request, tmdb_id):
    rating = UserMovieRating.objects.filter(user=request.user, tmdb_id=tmdb_id).first()
    if request.method == "GET":
        return Response(RatingSerializer(rating).data if rating else {"tmdb_id": tmdb_id, "rating": None})
    if request.method == "DELETE":
        if rating: rating.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    payload = {**request.data, "tmdb_id": tmdb_id}
    serializer = RatingSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    rating, _ = UserMovieRating.objects.update_or_create(user=request.user, tmdb_id=tmdb_id, defaults=serializer.validated_data)
    return Response(RatingSerializer(rating).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def recommendations(request):
    _, genre_scores, _ = user_profile(request.user)
    preferred = [key for key, value in sorted(genre_scores.items(), key=lambda pair: pair[1], reverse=True) if value > 0][:3]
    try:
        client = TMDBClient(settings.TMDB_API_TOKEN)
        data = client.movies(genre="|".join(preferred)) if preferred else client.movies()
        ranked, model = rank_candidates(request.user, data.get("results", []))
        data["results"] = ranked[:20]
        data["based_on_genres"] = preferred
        data["model"] = model
        RecommendationEvent.objects.bulk_create([
            RecommendationEvent(
                user=request.user,
                tmdb_id=movie["id"],
                title=(movie.get("title") or "")[:255],
                event_type="impression",
                algorithm=movie.get("recommendation_algorithm", "hybrid"),
                score=movie.get("ml_score", 0),
            )
            for movie in data["results"]
        ])
        return Response(data)
    except (TMDBConfigurationError, RequestException) as exc:
        return tmdb_error_response(exc)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def recommendation_event(request):
    if request.data.get("event_type") != "click":
        return Response({"detail": "Only click events are accepted."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        tmdb_id = int(request.data.get("tmdb_id"))
    except (TypeError, ValueError):
        return Response({"detail": "A valid tmdb_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    algorithm = request.data.get("algorithm", "hybrid")
    valid_algorithms = {choice[0] for choice in RecommendationEvent.ALGORITHM_CHOICES}
    if algorithm not in valid_algorithms:
        algorithm = "hybrid"
    RecommendationEvent.objects.create(
        user=request.user,
        tmdb_id=tmdb_id,
        title=str(request.data.get("title", ""))[:255],
        event_type="click",
        algorithm=algorithm,
        score=float(request.data.get("score") or 0),
    )
    return Response({"recorded": True}, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_analytics(request):
    now = timezone.now()
    today = timezone.localdate()
    try:
        days = int(request.query_params.get("days", 30))
    except ValueError:
        days = 30
    days = days if days in {7, 30, 90, 365} else 30
    thirty_days_ago = now - timedelta(days=days)
    fourteen_days_ago = now - timedelta(days=13)

    recent_searches = SearchLog.objects.filter(searched_at__gte=thirty_days_ago)
    recent_views = MovieViewLog.objects.filter(viewed_at__gte=thirty_days_ago)
    recent_recommendations = RecommendationEvent.objects.filter(created_at__gte=thirty_days_ago)

    top_queries = list(
        recent_searches.exclude(query="")
        .annotate(label=Lower("query"))
        .values("label")
        .annotate(count=Count("id"))
        .order_by("-count", "label")[:10]
    )
    top_genres = list(
        recent_searches.exclude(genre="")
        .values("genre")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    top_languages = list(
        recent_searches.exclude(language="")
        .values("language")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    top_years = list(
        recent_searches.exclude(year="")
        .values("year")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    top_movies = list(
        recent_views.values("tmdb_id", "title")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    daily_searches = list(
        SearchLog.objects.filter(searched_at__gte=fourteen_days_ago)
        .annotate(day=TruncDate("searched_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    daily_views = list(
        MovieViewLog.objects.filter(viewed_at__gte=fourteen_days_ago)
        .annotate(day=TruncDate("viewed_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    user_growth = list(
        User.objects.filter(date_joined__gte=fourteen_days_ago)
        .annotate(day=TruncDate("date_joined"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    rating_distribution = list(
        UserMovieRating.objects.values("rating").annotate(count=Count("id")).order_by("rating")
    )
    top_watchlisted = list(
        WatchlistItem.objects.values("tmdb_id", "title")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    top_rated = list(
        UserMovieRating.objects.values("tmdb_id")
        .annotate(count=Count("id"), average=Avg("rating"))
        .filter(count__gte=1)
        .order_by("-average", "-count")[:10]
    )
    title_map = {
        row["tmdb_id"]: row["title"]
        for row in MovieViewLog.objects.exclude(title="").values("tmdb_id", "title")
    }
    for item in top_rated:
        item["title"] = title_map.get(item["tmdb_id"], f"TMDB {item['tmdb_id']}")
        item["average"] = round(item["average"], 1)

    recommendation_impressions = recent_recommendations.filter(event_type="impression").count()
    recommendation_clicks = recent_recommendations.filter(event_type="click").count()
    recommendation_ctr = round(recommendation_clicks / recommendation_impressions * 100, 1) if recommendation_impressions else 0
    successful_searches = recent_searches.filter(result_count__gt=0).count()
    search_success_rate = round(successful_searches / recent_searches.count() * 100, 1) if recent_searches.exists() else 0
    active_user_ids = set(recent_searches.exclude(user=None).values_list("user_id", flat=True))
    active_user_ids.update(recent_views.exclude(user=None).values_list("user_id", flat=True))
    returning_users = (
        recent_views.exclude(user=None).values("user_id").annotate(total=Count("id")).filter(total__gte=2).count()
    )

    latest = SearchLog.objects.select_related("user")[:20]
    recent_activity = [
        {
            "id": item.id,
            "query": item.query or "Browse movies",
            "genre": item.genre,
            "year": item.year,
            "language": item.language,
            "minimum_rating": item.minimum_rating,
            "result_count": item.result_count,
            "username": item.user.username if item.user else "Guest",
            "searched_at": item.searched_at,
        }
        for item in latest
    ]

    return Response(
        {
            "summary": {
                "total_searches": SearchLog.objects.count(),
                "searches_today": SearchLog.objects.filter(searched_at__date=today).count(),
                "searches_30_days": recent_searches.count(),
                "zero_result_searches": recent_searches.filter(result_count=0).count(),
                "movie_views_30_days": recent_views.count(),
                "registered_users": User.objects.count(),
                "watchlist_items": WatchlistItem.objects.count(),
                "ratings_count": UserMovieRating.objects.count(),
                "average_user_rating": round(
                    UserMovieRating.objects.aggregate(value=Avg("rating"))["value"] or 0,
                    1,
                ),
                "active_users": len(active_user_ids),
                "new_users": User.objects.filter(date_joined__gte=thirty_days_ago).count(),
                "returning_users": returning_users,
                "search_success_rate": search_success_rate,
                "recommendation_impressions": recommendation_impressions,
                "recommendation_clicks": recommendation_clicks,
                "recommendation_ctr": recommendation_ctr,
                "date_range_days": days,
            },
            "top_queries": top_queries,
            "top_genres": top_genres,
            "top_languages": top_languages,
            "top_years": top_years,
            "top_movies": top_movies,
            "daily_searches": daily_searches,
            "daily_views": daily_views,
            "user_growth": user_growth,
            "rating_distribution": rating_distribution,
            "top_watchlisted": top_watchlisted,
            "top_rated": top_rated,
            "recent_activity": recent_activity,
        }
    )


@api_view(["GET"])
@permission_classes([IsAdminUser])
def analytics_export(request):
    report = request.query_params.get("report", "searches")
    output = StringIO()
    writer = csv.writer(output)
    if report == "recommendations":
        writer.writerow(["Date", "User", "Movie ID", "Title", "Event", "Algorithm", "Score"])
        for item in RecommendationEvent.objects.select_related("user")[:10000]:
            writer.writerow([item.created_at.isoformat(), item.user.username if item.user else "Guest", item.tmdb_id, item.title, item.event_type, item.algorithm, item.score])
    else:
        writer.writerow(["Date", "User", "Query", "Genre", "Year", "Language", "Minimum rating", "Results"])
        for item in SearchLog.objects.select_related("user")[:10000]:
            writer.writerow([item.searched_at.isoformat(), item.user.username if item.user else "Guest", item.query, item.genre, item.year, item.language, item.minimum_rating or "", item.result_count])
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="cinepick-{report}.csv"'
    return response

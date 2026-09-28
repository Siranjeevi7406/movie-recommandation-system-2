"""Small, explainable hybrid recommender for a college project.

It combines content preference weights with user-user collaborative filtering.
No paid service or separate model server is required.
"""

from collections import defaultdict
from math import sqrt

from .models import UserMovieRating


def cosine_similarity(left, right):
    common = set(left) & set(right)
    if not common:
        return 0.0
    numerator = sum(left[item] * right[item] for item in common)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def user_profile(user):
    genre_scores = defaultdict(float)
    language_scores = defaultdict(float)
    ratings = {}

    for entry in user.movie_ratings.all():
        ratings[entry.tmdb_id] = float(entry.rating)
        weight = max(float(entry.rating) - 5.0, -3.0)
        for genre_id in entry.genre_ids:
            genre_scores[str(genre_id)] += weight

    for entry in user.watchlist.all():
        for genre_id in entry.genre_ids:
            genre_scores[str(genre_id)] += 2.5

    for entry in user.search_logs.exclude(language="")[:100]:
        language_scores[entry.language.lower()] += 1.0
    for entry in user.search_logs.exclude(genre="")[:100]:
        genre_scores[str(entry.genre)] += 1.0

    return ratings, genre_scores, language_scores


def collaborative_predictions(user, own_ratings):
    by_user = defaultdict(dict)
    for row in UserMovieRating.objects.exclude(user=user).values("user_id", "tmdb_id", "rating"):
        by_user[row["user_id"]][row["tmdb_id"]] = float(row["rating"])

    weighted = defaultdict(float)
    similarity_total = defaultdict(float)
    neighbours = 0
    for ratings in by_user.values():
        similarity = cosine_similarity(own_ratings, ratings)
        if similarity <= 0:
            continue
        neighbours += 1
        for movie_id, rating in ratings.items():
            if movie_id not in own_ratings:
                weighted[movie_id] += similarity * rating
                similarity_total[movie_id] += similarity

    predictions = {
        movie_id: weighted[movie_id] / similarity_total[movie_id]
        for movie_id in weighted
        if similarity_total[movie_id]
    }
    return predictions, neighbours


def rank_candidates(user, candidates):
    own_ratings, genre_scores, language_scores = user_profile(user)
    collaborative, neighbour_count = collaborative_predictions(user, own_ratings)
    seen = set(own_ratings) | set(user.watchlist.values_list("tmdb_id", flat=True))
    max_genre = max([abs(value) for value in genre_scores.values()] or [1.0])
    max_language = max(language_scores.values() or [1.0])
    ranked = []

    for movie in candidates:
        movie_id = movie.get("id")
        if not movie_id or movie_id in seen:
            continue
        genres = [str(item) for item in movie.get("genre_ids", [])]
        content = sum(genre_scores.get(item, 0) for item in genres) / max_genre
        language = language_scores.get(str(movie.get("language", "")).lower(), 0) / max_language
        community = collaborative.get(movie_id, 0) / 10.0
        quality = float(movie.get("rating") or 0) / 10.0
        score = 0.48 * content + 0.12 * language + 0.25 * community + 0.15 * quality

        has_content = content > 0 or language > 0
        has_collaboration = movie_id in collaborative
        algorithm = "hybrid" if has_content and has_collaboration else "collaborative" if has_collaboration else "content" if has_content else "popular"
        reason = "Popular with CinePick users"
        if has_content and has_collaboration:
            reason = "Matches your tastes and similar users"
        elif has_content:
            reason = "Matches your preferred genres and languages"
        elif has_collaboration:
            reason = "Liked by users with similar ratings"

        ranked.append({
            **movie,
            "ml_score": round(score, 4),
            "recommendation_algorithm": algorithm,
            "recommendation_reason": reason,
        })

    ranked.sort(key=lambda item: (item["ml_score"], item.get("rating") or 0), reverse=True)
    return ranked, {
        "algorithm": "hybrid-content-collaborative-v1",
        "neighbours_used": neighbour_count,
        "ratings_used": len(own_ratings),
        "genre_signals": len(genre_scores),
        "language_signals": len(language_scores),
    }

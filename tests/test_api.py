from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backend.app import create_app
from backend.recommender import DatasetError, MovieRecommender


@pytest.fixture
def movie_data(tmp_path: Path) -> Path:
    movies = pd.DataFrame(
        [
            (1, "Space Journey (2001)", "Adventure|Sci-Fi"),
            (2, "Space Explorers (2002)", "Adventure|Sci-Fi"),
            (3, "Funny Neighbours (2003)", "Comedy"),
            (4, "Space Drama (2004)", "Drama|Sci-Fi"),
            (5, "Forest Adventure (2005)", "Adventure|Fantasy"),
            (6, "Quiet Romance (2006)", "Romance|Drama"),
        ],
        columns=["movieId", "title", "genres"],
    )
    ratings = pd.DataFrame(
        [
            (user_id, movie_id, rating, 1_700_000_000 + user_id)
            for movie_id in range(1, 7)
            for user_id, rating in [(1, 5.0), (2, 4.0), (3, 3.0)]
        ],
        columns=["userId", "movieId", "rating", "timestamp"],
    )
    tags = pd.DataFrame(
        [
            (1, 1, "space travel"),
            (2, 1, "space travel"),
            (1, 2, "space travel"),
            (3, 3, "neighbours"),
            (2, 4, "space travel"),
        ],
        columns=["userId", "movieId", "tag"],
    )
    movies.to_csv(tmp_path / "movies.csv", index=False)
    ratings.to_csv(tmp_path / "ratings.csv", index=False)
    tags.to_csv(tmp_path / "tags.csv", index=False)
    return tmp_path


@pytest.fixture
def client(movie_data: Path):
    app = create_app(
        data_dir=movie_data,
        download_if_missing=False,
        minimum_rating_count=2,
    )
    app.config["TESTING"] = True
    return app.test_client()


def test_dataset_loads_actual_csv_statistics(movie_data: Path) -> None:
    recommender = MovieRecommender(
        movie_data, download_if_missing=False, minimum_rating_count=2
    )
    movie = recommender.movie_details(1)
    assert recommender.dataset_status["movie_count"] == 6
    assert movie is not None
    assert movie["average_rating"] == 4.0
    assert movie["rating_count"] == 3
    assert movie["genres"] == ["Adventure", "Sci-Fi"]


def test_missing_dataset_is_reported(movie_data: Path, tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="files are missing"):
        MovieRecommender(tmp_path / "missing", download_if_missing=False)


def test_health_remains_available_when_dataset_is_missing(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "missing", download_if_missing=False)
    client = app.test_client()
    health = client.get("/api/health")
    movies = client.get("/api/movies")
    assert health.status_code == 200
    assert health.json["dataset"]["loaded"] is False
    assert movies.status_code == 503
    assert movies.json["error"]["code"] == "dataset_unavailable"


def test_health_endpoint_reports_loaded_dataset(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["dataset"]["loaded"] is True


def test_optional_flask_frontend_serves_relative_standalone_assets(client) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert b'href="style.css"' in page.data
    assert b'src="movies-data.js"' in page.data
    for asset in ("style.css", "script.js", "movies-data.js"):
        assert client.get(f"/{asset}").status_code == 200


def test_movie_search_and_pagination(client) -> None:
    response = client.get("/api/movies?search=space&page=1&page_size=1")
    assert response.status_code == 200
    assert response.json["total_results"] == 3
    assert response.json["total_pages"] == 3
    assert len(response.json["results"]) == 1
    assert "Space" in response.json["results"][0]["title"]


def test_genre_filter_uses_dataset_values(client) -> None:
    response = client.get("/api/movies?genre=Sci-Fi")
    assert response.status_code == 200
    assert all("Sci-Fi" in movie["genres"] for movie in response.json["results"])
    assert client.get("/api/genres").json["genres"] == [
        "Adventure",
        "Comedy",
        "Drama",
        "Fantasy",
        "Romance",
        "Sci-Fi",
    ]


def test_movie_details_include_real_rating_count(client) -> None:
    response = client.get("/api/movies/1")
    assert response.status_code == 200
    assert response.json["movie_id"] == 1
    assert response.json["year"] == 2001
    assert response.json["average_rating"] == 4.0
    assert response.json["rating_count"] == 3


def test_recommendations_are_similarity_ranked_and_exclude_selected_movie(client) -> None:
    response = client.get("/api/recommend/1?limit=5")
    assert response.status_code == 200
    results = response.json["recommendations"]
    assert 1 <= len(results) <= 5
    assert all(movie["movie_id"] != 1 for movie in results)
    assert all(movie["similarity"] > 0 for movie in results)
    assert results[0]["movie_id"] == 2
    assert results[0]["matching_genres"] == ["Adventure", "Sci-Fi"]
    assert all("explanation" in movie for movie in results)


def test_invalid_movie_ids_return_json_404(client) -> None:
    assert client.get("/api/movies/9999").status_code == 404
    response = client.get("/api/recommend/9999")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "movie_not_found"


def test_empty_search_returns_empty_page(client) -> None:
    response = client.get("/api/movies?search=title-that-does-not-exist")
    assert response.status_code == 200
    assert response.json["results"] == []
    assert response.json["total_results"] == 0
    filtered_response = client.get(
        "/api/movies?search=title-that-does-not-exist&genre=Adventure&sort=rating"
    )
    assert filtered_response.status_code == 200
    assert filtered_response.json["results"] == []
    assert filtered_response.json["total_results"] == 0


def test_invalid_parameters_are_clear_json_errors(client) -> None:
    response = client.get("/api/movies?page=0")
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_parameter"
    assert client.get("/api/recommend/1?limit=21").status_code == 400
    assert client.get("/api/movies?genre=Not-A-Genre").status_code == 400


def test_stats_include_popularity_and_minimum_rating_threshold(client) -> None:
    response = client.get("/api/stats")
    assert response.status_code == 200
    assert response.json["dataset"]["rating_count"] == 18
    assert response.json["average_rating"] == 4.0
    assert response.json["minimum_rating_count"] == 2
    assert response.json["highly_rated"]
    assert response.json["genre_counts"]["Sci-Fi"] == 3

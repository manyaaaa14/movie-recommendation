"""CineMatch REST API and local development server."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from backend.recommender import DatasetError, MovieRecommender

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = ROOT_DIR / "data"


def create_app(
    data_dir: Path | str | None = None,
    *,
    download_if_missing: bool = True,
    minimum_rating_count: int = 50,
) -> Flask:
    """Create the app and load the dataset once before serving requests."""
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="/static",
    )
    app.config["JSON_SORT_KEYS"] = False
    try:
        recommender = MovieRecommender(
            data_dir or DATA_DIR,
            download_if_missing=download_if_missing,
            minimum_rating_count=minimum_rating_count,
        )
        dataset_error = None
    except DatasetError as error:
        recommender = None
        dataset_error = str(error)
        app.logger.error("MovieLens dataset is unavailable: %s", error)
    app.extensions["movie_recommender"] = recommender
    app.extensions["dataset_error"] = dataset_error

    def error_response(
        message: str, code: str, status: int
    ) -> tuple[Any, int]:
        return jsonify({"error": {"code": code, "message": message}}), status

    def require_recommender() -> MovieRecommender | tuple[Any, int]:
        loaded = app.extensions["movie_recommender"]
        if loaded is None:
            return error_response(
                app.extensions["dataset_error"] or "The dataset is unavailable.",
                "dataset_unavailable",
                503,
            )
        return loaded

    def integer_parameter(
        name: str, default: int, minimum: int, maximum: int
    ) -> int | tuple[Any, int]:
        raw = request.args.get(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            return error_response(
                f"'{name}' must be a whole number.",
                "invalid_parameter",
                400,
            )
        if not minimum <= value <= maximum:
            return error_response(
                f"'{name}' must be between {minimum} and {maximum}.",
                "invalid_parameter",
                400,
            )
        return value

    @app.get("/")
    def index() -> Any:
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.get("/<path:asset_name>")
    def frontend_asset(asset_name: str) -> Any:
        if asset_name not in {"style.css", "script.js", "movies-data.js"}:
            return error_response(
                "The requested frontend asset was not found.", "not_found", 404
            )
        return send_from_directory(FRONTEND_DIR, asset_name)

    @app.get("/api/health")
    def health() -> Any:
        loaded = app.extensions["movie_recommender"]
        return jsonify(
            {
                "status": "ok",
                "dataset": (
                    loaded.dataset_status
                    if loaded is not None
                    else {
                        "loaded": False,
                        "name": "MovieLens Latest Small",
                        "error": app.extensions["dataset_error"],
                    }
                ),
            }
        )

    @app.get("/api/genres")
    def genres() -> Any:
        loaded = require_recommender()
        if isinstance(loaded, tuple):
            return loaded
        return jsonify({"genres": loaded.genres})

    @app.get("/api/movies")
    def list_movies() -> Any:
        loaded = require_recommender()
        if isinstance(loaded, tuple):
            return loaded

        page = integer_parameter("page", 1, 1, 1_000_000)
        if isinstance(page, tuple):
            return page
        page_size = integer_parameter("page_size", 20, 1, 100)
        if isinstance(page_size, tuple):
            return page_size
        sort = request.args.get("sort", "title")
        if sort not in {"title", "rating", "year", "popular"}:
            return error_response(
                "'sort' must be one of: title, rating, year, popular.",
                "invalid_parameter",
                400,
            )
        genre = request.args.get("genre", "").strip()
        if genre and genre not in loaded.genres:
            return error_response(
                f"'{genre}' is not a genre in the MovieLens dataset.",
                "invalid_genre",
                400,
            )
        result = loaded.list_movies(
            search=request.args.get("search", request.args.get("q", "")),
            genre=genre,
            sort=sort,
            page=page,
            page_size=page_size,
        )
        return jsonify(result)

    @app.get("/api/movies/<int:movie_id>")
    def movie_details(movie_id: int) -> Any:
        loaded = require_recommender()
        if isinstance(loaded, tuple):
            return loaded
        movie = loaded.movie_details(movie_id)
        if movie is None:
            return error_response(
                f"No MovieLens movie has ID {movie_id}.", "movie_not_found", 404
            )
        return jsonify(movie)

    @app.get("/api/recommend/<int:movie_id>")
    def recommend(movie_id: int) -> Any:
        loaded = require_recommender()
        if isinstance(loaded, tuple):
            return loaded
        limit = integer_parameter("limit", 5, 1, 20)
        if isinstance(limit, tuple):
            return limit
        results = loaded.recommendations(movie_id, limit)
        if results is None:
            return error_response(
                f"No MovieLens movie has ID {movie_id}.", "movie_not_found", 404
            )
        return jsonify(
            {
                "movie_id": movie_id,
                "limit": limit,
                "count": len(results),
                "recommendations": results,
                "method": "TF-IDF content features with cosine similarity",
            }
        )

    @app.get("/api/stats")
    def stats() -> Any:
        loaded = require_recommender()
        if isinstance(loaded, tuple):
            return loaded
        return jsonify(loaded.stats())

    @app.errorhandler(404)
    def not_found(error: Any) -> Any:
        if request.path.startswith("/api/"):
            return error_response("The requested API endpoint was not found.", "not_found", 404)
        return error

    @app.errorhandler(500)
    def server_error(error: Any) -> Any:
        app.logger.exception("Unhandled CineMatch server error: %s", error)
        if request.path.startswith("/api/"):
            return error_response(
                "An unexpected server error occurred. Check the backend terminal for details.",
                "internal_server_error",
                500,
            )
        return error

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    application = create_app()
    application.run(host="127.0.0.1", port=5000, debug=False)

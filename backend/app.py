"""CineMatch REST API and local development server."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from flask import Flask, jsonify, request, send_from_directory
from pymongo.errors import PyMongoError

from backend.database import MongoWatchlistStore
from backend.recommender import DatasetError, MovieRecommender

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = ROOT_DIR / "data"


def create_app(
    data_dir: Path | str | None = None,
    *,
    download_if_missing: bool = True,
    minimum_rating_count: int = 50,
    watchlist_store: Any | None = None,
) -> Flask:
    """Create the app and load the dataset once before serving requests."""
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="/static",
    )
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
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
    mongo_uri = os.environ.get("MONGODB_URI", "").strip()
    mongo_error = None
    if watchlist_store is None and mongo_uri:
        try:
            watchlist_store = MongoWatchlistStore(
                mongo_uri,
                os.environ.get("MONGODB_DATABASE", "cinematch"),
            )
        except PyMongoError as error:
            mongo_error = "MongoDB connection failed. Check the Render database settings."
            app.logger.error("MongoDB is unavailable: %s", error)
    app.extensions["watchlist_store"] = watchlist_store
    app.extensions["mongo_error"] = mongo_error

    configured_origins = {
        origin.strip().rstrip("/")
        for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }
    if os.environ.get("NETLIFY_SITE_URL"):
        configured_origins.add(os.environ["NETLIFY_SITE_URL"].strip().rstrip("/"))
    allowed_origins = configured_origins | {
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    }

    @app.after_request
    def configure_cors(response: Any) -> Any:
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, PUT, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers.add("Vary", "Origin")
        return response

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

    def require_watchlist_store() -> Any | tuple[Any, int]:
        store = app.extensions["watchlist_store"]
        if store is None:
            message = app.extensions["mongo_error"] or (
                "Cloud watchlists are not configured. The browser watchlist remains available."
            )
            return error_response(message, "database_unavailable", 503)
        return store

    def normalized_client_id(raw_client_id: str) -> str | None:
        try:
            return str(UUID(raw_client_id))
        except (ValueError, AttributeError):
            return None

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
        if asset_name not in {
            "config.js",
            "model.js",
            "movies-data.js",
            "ratings-data.js",
            "script.js",
            "style.css",
        }:
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
                "watchlist_database": {
                    "configured": app.extensions["watchlist_store"] is not None,
                    "connected": app.extensions["watchlist_store"] is not None,
                },
            }
        )

    @app.route(
        "/api/watchlist/<client_id>",
        methods=["GET", "PUT", "OPTIONS"],
    )
    def watchlist(client_id: str) -> Any:
        normalized_id = normalized_client_id(client_id)
        if normalized_id is None:
            return error_response(
                "The watchlist ID must be a valid UUID.",
                "invalid_client_id",
                400,
            )
        if request.method == "OPTIONS":
            return "", 204

        store = require_watchlist_store()
        if isinstance(store, tuple):
            return store
        if request.method == "GET":
            try:
                movie_ids = store.get_movie_ids(normalized_id)
            except PyMongoError as error:
                app.logger.error("Could not load a MongoDB watchlist: %s", error)
                return error_response(
                    "Cloud watchlist could not be loaded. Your local watchlist is unchanged.",
                    "database_error",
                    503,
                )
            return jsonify({"movie_ids": movie_ids})

        if not request.is_json:
            return error_response(
                "The watchlist request must use application/json.",
                "invalid_content_type",
                415,
            )
        body = request.get_json()
        movie_ids = body.get("movie_ids") if isinstance(body, dict) else None
        if not isinstance(movie_ids, list):
            return error_response(
                "'movie_ids' must be a JSON array.",
                "invalid_watchlist",
                400,
            )
        if len(movie_ids) > 500:
            return error_response(
                "A watchlist may contain at most 500 movies.",
                "watchlist_too_large",
                400,
            )
        if any(
            isinstance(movie_id, bool)
            or not isinstance(movie_id, int)
            or movie_id < 1
            for movie_id in movie_ids
        ):
            return error_response(
                "Every watchlist movie ID must be a positive integer.",
                "invalid_movie_id",
                400,
            )
        unique_movie_ids = list(dict.fromkeys(movie_ids))
        recommender = app.extensions["movie_recommender"]
        if recommender is None:
            return error_response(
                "MovieLens data is unavailable, so movie IDs cannot be validated.",
                "dataset_unavailable",
                503,
            )
        unknown_ids = [
            movie_id
            for movie_id in unique_movie_ids
            if recommender.movie_details(movie_id) is None
        ]
        if unknown_ids:
            return error_response(
                f"Movie IDs are not present in MovieLens: {unknown_ids[:10]}.",
                "unknown_movie_id",
                400,
            )
        try:
            store.save_movie_ids(normalized_id, unique_movie_ids)
        except PyMongoError as error:
            app.logger.error("Could not save a MongoDB watchlist: %s", error)
            return error_response(
                "Cloud watchlist could not be saved. Your local watchlist is unchanged.",
                "database_error",
                503,
            )
        return jsonify({"movie_ids": unique_movie_ids, "saved": True})

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

    @app.errorhandler(400)
    def bad_request(error: Any) -> Any:
        if request.path.startswith("/api/"):
            return error_response(
                "The request is malformed or contains invalid JSON.",
                "bad_request",
                400,
            )
        return error

    @app.errorhandler(413)
    def payload_too_large(error: Any) -> Any:
        if request.path.startswith("/api/"):
            return error_response(
                "The request body exceeds the 16 KB limit.",
                "payload_too_large",
                413,
            )
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

"""Optional MongoDB persistence for browser watchlists."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import MongoClient


class MongoWatchlistStore:
    """Small MongoDB store for MovieLens IDs; no names or ratings are stored."""

    def __init__(self, uri: str, database_name: str = "cinematch") -> None:
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.client.admin.command("ping")
        self.collection = self.client[database_name]["watchlists"]
        self.collection.create_index("updated_at", expireAfterSeconds=60 * 60 * 24 * 365)

    def get_movie_ids(self, client_id: str) -> list[int]:
        document = self.collection.find_one({"_id": client_id}, {"movie_ids": 1})
        if document is None:
            return []
        return [int(movie_id) for movie_id in document.get("movie_ids", [])]

    def save_movie_ids(self, client_id: str, movie_ids: list[int]) -> None:
        self.collection.update_one(
            {"_id": client_id},
            {
                "$set": {
                    "movie_ids": movie_ids,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    def close(self) -> None:
        self.client.close()

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import pandas as pd

from tools.build_browser_data import build_bundle


def test_browser_bundle_contains_actual_ratings_and_profile_summary(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    pd.DataFrame(
        [
            (1, "Space Journey (2001)", "Adventure|Sci-Fi"),
            (2, "Space Explorers (2002)", "Adventure|Sci-Fi"),
            (3, "Funny Neighbours (2003)", "Comedy"),
            (4, "Quiet Romance (2006)", "Romance|Drama"),
        ],
        columns=["movieId", "title", "genres"],
    ).to_csv(data_dir / "movies.csv", index=False)
    ratings = pd.DataFrame(
        [
            (user_id, movie_id, rating, 1_700_000_000 + user_id)
            for movie_id, rating in [(1, 5.0), (2, 4.5), (3, 2.0), (4, 3.5)]
            for user_id in [1, 2, 3]
        ],
        columns=["userId", "movieId", "rating", "timestamp"],
    )
    ratings.to_csv(data_dir / "ratings.csv", index=False)
    pd.DataFrame(
        [(1, 1, "space"), (2, 2, "space")],
        columns=["userId", "movieId", "tag"],
    ).to_csv(data_dir / "tags.csv", index=False)

    output = tmp_path / "frontend" / "movies-data.js"
    assert build_bundle(data_dir, output) == 4

    movie_bundle = output.read_text(encoding="utf-8")
    movie_data = json.loads(movie_bundle.split("window.CINEMATCH_DATA = ", 1)[1].rstrip(";\n"))
    assert movie_data["dataset"]["rating_count"] == 12
    assert movie_data["movies"][0]["average_rating"] == 5.0
    assert movie_data["profile_users"][0]["rating_count"] == 4
    assert (output.parent / "ratings-data.js").is_file()

    ratings_bundle = (output.parent / "ratings-data.js").read_text(encoding="utf-8")
    encoded = json.loads(
        ratings_bundle.split("window.CINEMATCH_RATINGS = ", 1)[1].rstrip(";\n")
    )
    binary = base64.b64decode(encoded["encoded"])
    assert encoded["count"] == 12
    assert len(binary) == encoded["count"] * 5
    first_user, first_movie, first_half_rating = struct.unpack_from("<HHB", binary)
    assert first_user == 1
    assert first_movie == 0
    assert first_half_rating == 10

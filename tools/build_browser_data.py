"""Build the standalone browser data bundle from official MovieLens CSV files."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import struct

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]


def build_bundle(data_dir: Path, output_path: Path) -> int:
    """Aggregate MovieLens CSV records and write the local browser data script."""
    required_files = ("movies.csv", "ratings.csv", "tags.csv")
    missing = [filename for filename in required_files if not (data_dir / filename).is_file()]
    if missing:
        raise FileNotFoundError(
            f"MovieLens files are missing from {data_dir}: {', '.join(missing)}"
        )

    movies = pd.read_csv(data_dir / "movies.csv")
    ratings = pd.read_csv(data_dir / "ratings.csv")
    tags = pd.read_csv(data_dir / "tags.csv")
    links_path = data_dir / "links.csv"
    links = pd.read_csv(links_path) if links_path.is_file() else None

    movies["movieId"] = movies["movieId"].astype(int)
    ratings["movieId"] = ratings["movieId"].astype(int)
    ratings["timestamp"] = ratings["timestamp"].astype(int)
    rating_stats = ratings.groupby("movieId")["rating"].agg(
        average_rating="mean", rating_count="count"
    )
    movies = movies.merge(rating_stats, left_on="movieId", right_index=True, how="left")
    movies["rating_count"] = movies["rating_count"].fillna(0).astype(int)
    movies["year"] = pd.to_numeric(
        movies["title"].str.extract(r"\((\d{4})\)\s*$", expand=False),
        errors="coerce",
    )
    movies["display_title"] = movies["title"].str.replace(
        r"\s*\(\d{4}\)\s*$", "", regex=True
    )
    movies["genre_list"] = movies["genres"].map(
        lambda value: [
            genre
            for genre in value.split("|")
            if genre and genre != "(no genres listed)"
        ]
    )

    tags["movieId"] = pd.to_numeric(tags["movieId"], errors="coerce")
    tags = tags.dropna(subset=["movieId", "tag"]).copy()
    tags["movieId"] = tags["movieId"].astype(int)
    tags_by_movie = tags.groupby("movieId")["tag"].agg(
        lambda values: sorted(
            {str(value).strip().lower() for value in values if str(value).strip()}
        )
    )
    movies["tag_list"] = movies["movieId"].map(tags_by_movie).map(
        lambda values: values if isinstance(values, list) else []
    )

    if links is not None and {"movieId", "imdbId"}.issubset(links.columns):
        links["movieId"] = pd.to_numeric(links["movieId"], errors="coerce")
        links = links.dropna(subset=["movieId"]).copy()
        links["movieId"] = links["movieId"].astype(int)
        movies = movies.merge(
            links[["movieId", "imdbId"]].drop_duplicates("movieId"),
            on="movieId",
            how="left",
        )
    else:
        movies["imdbId"] = None

    records = []
    for movie in movies.itertuples(index=False):
        imdb_id = movie.imdbId
        records.append(
            {
                "movie_id": int(movie.movieId),
                "title": str(movie.display_title),
                "year": int(movie.year) if pd.notna(movie.year) else None,
                "genres": movie.genre_list,
                "average_rating": (
                    round(float(movie.average_rating), 2)
                    if pd.notna(movie.average_rating)
                    else None
                ),
                "rating_count": int(movie.rating_count),
                "imdb_id": (
                    str(int(imdb_id)).zfill(7)
                    if pd.notna(imdb_id) and int(imdb_id)
                    else None
                ),
                "tags": movie.tag_list,
            }
        )

    movie_indices = {
        int(movie_id): index for index, movie_id in enumerate(movies["movieId"])
    }
    ratings["userId"] = pd.to_numeric(ratings["userId"], errors="coerce")
    ratings["rating"] = pd.to_numeric(ratings["rating"], errors="coerce")
    ratings = ratings.dropna(subset=["userId", "rating", "movieId"]).copy()
    ratings["userId"] = ratings["userId"].astype(int)
    ratings["movieId"] = ratings["movieId"].astype(int)
    ratings["movie_index"] = ratings["movieId"].map(movie_indices)
    ratings = ratings.dropna(subset=["movie_index"]).copy()
    if (
        (ratings["userId"] < 1).any()
        or (ratings["userId"] > 65535).any()
        or len(records) > 65535
    ):
        raise ValueError("The compact browser rating format supports up to 65,535 users and movies.")
    half_star_ratings = ratings["rating"] * 2
    if not half_star_ratings.mod(1).eq(0).all() or not half_star_ratings.between(1, 10).all():
        raise ValueError("MovieLens ratings must be in half-star increments from 0.5 to 5.")
    binary_ratings = bytearray(len(ratings) * 5)
    for row_index, (user_id, movie_index, rating) in enumerate(
        ratings[["userId", "movie_index", "rating"]].itertuples(
            index=False, name=None
        )
    ):
        struct.pack_into(
            "<HHB",
            binary_ratings,
            row_index * 5,
            int(user_id),
            int(movie_index),
            int(round(float(rating) * 2)),
        )
    latest_timestamp = int(ratings["timestamp"].max())
    recent_cutoff = latest_timestamp - 365 * 24 * 60 * 60
    recent_ratings = ratings.loc[ratings["timestamp"] >= recent_cutoff]
    if recent_ratings.empty:
        recent_ratings = ratings
    recent_counts = recent_ratings.groupby("movieId").size().to_dict()
    trending = sorted(
        records,
        key=lambda movie: (
            -recent_counts.get(movie["movie_id"], 0),
            -movie["rating_count"],
            movie["title"].casefold(),
        ),
    )
    popular = sorted(
        records,
        key=lambda movie: (
            -movie["rating_count"],
            -(movie["average_rating"] or 0),
            movie["title"].casefold(),
        ),
    )
    highly_rated = sorted(
        (movie for movie in records if movie["rating_count"] >= 50),
        key=lambda movie: (
            -(movie["average_rating"] or 0),
            -movie["rating_count"],
            movie["title"].casefold(),
        ),
    )
    genre_counts: dict[str, int] = {}
    for movie in records:
        for genre in movie["genres"]:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1

    payload = {
        "dataset": {
            "name": "MovieLens Latest Small",
            "movie_count": len(records),
            "rating_count": int(len(ratings)),
            "unique_users": int(ratings["userId"].nunique()),
            "average_rating": round(float(ratings["rating"].mean()), 2),
            "minimum_rating_count": 50,
            "trending_basis": "Rating activity in the latest 365 days recorded in MovieLens.",
        },
        "profile_users": [
            {"user_id": int(user_id), "rating_count": int(count)}
            for user_id, count in ratings.groupby("userId").size().nlargest(30).items()
        ],
        "genres": sorted(genre_counts, key=str.casefold),
        "genre_counts": genre_counts,
        "trending": [
            {
                **movie,
                "recent_rating_count": int(recent_counts.get(movie["movie_id"], 0)),
            }
            for movie in trending[:6]
        ],
        "popular": popular[:6],
        "highly_rated": highly_rated[:10],
        "movies": records,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "// Generated from the official MovieLens Latest Small CSV files. "
        "See README.md for attribution.\n"
        "window.CINEMATCH_DATA = "
        + json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    ratings_output = output_path.with_name("ratings-data.js")
    ratings_output.write_text(
        "// MovieLens Latest Small ratings packed as little-endian uint16 user ID, "
        "uint16 movie index, uint8 half-star rating.\n"
        "window.CINEMATCH_RATINGS = {"
        f'"count":{len(binary_ratings) // 5},'
        f'"encoded":"{base64.b64encode(binary_ratings).decode("ascii")}"'
        "};\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(ratings):,} MovieLens ratings to {ratings_output}")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=ROOT_DIR / "data", help="Folder with MovieLens CSVs"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT_DIR / "frontend" / "movies-data.js",
        help="Path for the standalone browser data bundle",
    )
    args = parser.parse_args()
    movie_count = build_bundle(args.data_dir, args.output)
    print(f"Wrote {movie_count:,} MovieLens movies to {args.output}")


if __name__ == "__main__":
    main()

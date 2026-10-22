"""Load MovieLens data and build content-based movie recommendations."""

from __future__ import annotations

import io
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DATASET_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
REQUIRED_FILES = ("movies.csv", "ratings.csv", "tags.csv")
OPTIONAL_FILES = ("links.csv",)
DATASET_NAME = "MovieLens Latest Small"


class DatasetError(RuntimeError):
    """Raised when the official dataset cannot be downloaded or loaded."""


class MovieRecommender:
    """In-memory MovieLens catalogue, statistics, and sparse TF-IDF features."""

    def __init__(
        self,
        data_dir: Path | str,
        *,
        download_if_missing: bool = True,
        minimum_rating_count: int = 50,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.minimum_rating_count = minimum_rating_count
        self._ensure_dataset(download_if_missing)
        self._load_dataset()

    def _ensure_dataset(self, download_if_missing: bool) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if all((self.data_dir / filename).is_file() for filename in REQUIRED_FILES):
            return
        if not download_if_missing:
            missing = [
                filename
                for filename in REQUIRED_FILES
                if not (self.data_dir / filename).is_file()
            ]
            raise DatasetError(f"MovieLens files are missing: {', '.join(missing)}")

        archive_data = None
        request = urllib.request.Request(
            DATASET_URL, headers={"User-Agent": "Mozilla/5.0 CineMatch student project"}
        )
        try:
            try:
                import certifi
                ssl_context = ssl.create_default_context(cafile=certifi.where())
            except Exception:
                ssl_context = ssl.create_default_context()
            with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
                archive_data = response.read()
        except Exception as initial_error:
            try:
                unverified_context = ssl._create_unverified_context()
                with urllib.request.urlopen(request, timeout=30, context=unverified_context) as response:
                    archive_data = response.read()
            except Exception as download_error:
                curl = shutil.which("curl.exe") or shutil.which("curl")
                if curl is None:
                    raise DatasetError(
                        "Could not download MovieLens Latest Small. Check your internet connection. "
                        f"Details: {download_error}"
                    ) from download_error
                try:
                    with tempfile.TemporaryDirectory(dir=self.data_dir) as temporary_dir:
                        archive_path = Path(temporary_dir) / "movielens.zip"
                        result = subprocess.run(
                            [
                                curl,
                                "--fail",
                                "--location",
                                "--insecure",
                                "--silent",
                                "--show-error",
                                "--retry",
                                "3",
                                "--connect-timeout",
                                "15",
                                "--max-time",
                                "90",
                                "--output",
                                str(archive_path),
                                DATASET_URL,
                            ],
                            capture_output=True,
                            text=True,
                            timeout=120,
                            check=False,
                        )
                        if result.returncode != 0:
                            raise DatasetError(
                                "MovieLens download failed using both Python HTTPS and curl. "
                                f"Python: {download_error}; curl: {result.stderr.strip()}"
                            )
                        archive_data = archive_path.read_bytes()
                except (OSError, subprocess.TimeoutExpired) as curl_error:
                    raise DatasetError(
                        "MovieLens download failed using both Python HTTPS and curl. "
                        f"Python: {download_error}; curl: {curl_error}"
                    ) from curl_error

        try:
            with tempfile.TemporaryDirectory(dir=self.data_dir) as temporary_dir:
                with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
                    extracted: set[str] = set()
                    for member in archive.infolist():
                        path = PurePosixPath(member.filename)
                        if (
                            len(path.parts) != 2
                            or path.parts[0] != "ml-latest-small"
                            or path.name not in REQUIRED_FILES + OPTIONAL_FILES
                        ):
                            continue
                        destination = Path(temporary_dir) / path.name
                        destination.write_bytes(archive.read(member))
                        extracted.add(path.name)
                missing = set(REQUIRED_FILES) - extracted
                if missing:
                    raise DatasetError(
                        "The MovieLens archive is missing: "
                        + ", ".join(sorted(missing))
                    )
                for filename in extracted:
                    (Path(temporary_dir) / filename).replace(self.data_dir / filename)
        except (OSError, zipfile.BadZipFile) as error:
            raise DatasetError(
                "Could not extract MovieLens Latest Small. "
                f"Check the archive and data folder permissions. Details: {error}"
            ) from error

    def _load_dataset(self) -> None:
        try:
            movies = pd.read_csv(self.data_dir / "movies.csv")
            ratings = pd.read_csv(self.data_dir / "ratings.csv")
            tags = pd.read_csv(self.data_dir / "tags.csv")
            links_path = self.data_dir / "links.csv"
            links = pd.read_csv(links_path) if links_path.is_file() else None
        except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as error:
            raise DatasetError(f"Could not read MovieLens CSV files: {error}") from error

        expected_columns = {
            "movies.csv": (movies, {"movieId", "title", "genres"}),
            "ratings.csv": (ratings, {"userId", "movieId", "rating", "timestamp"}),
            "tags.csv": (tags, {"movieId", "tag"}),
        }
        for filename, (frame, required_columns) in expected_columns.items():
            missing = required_columns - set(frame.columns)
            if missing:
                raise DatasetError(
                    f"{filename} is missing required columns: {', '.join(sorted(missing))}"
                )

        movies["movieId"] = pd.to_numeric(movies["movieId"], errors="coerce")
        ratings["movieId"] = pd.to_numeric(ratings["movieId"], errors="coerce")
        ratings["rating"] = pd.to_numeric(ratings["rating"], errors="coerce")
        ratings["timestamp"] = pd.to_numeric(ratings["timestamp"], errors="coerce")
        movies = movies.dropna(subset=["movieId", "title", "genres"]).copy()
        ratings = ratings.dropna(subset=["movieId", "rating", "timestamp"]).copy()
        movies["movieId"] = movies["movieId"].astype(int)
        ratings["movieId"] = ratings["movieId"].astype(int)
        ratings["timestamp"] = ratings["timestamp"].astype(int)

        rating_stats = ratings.groupby("movieId")["rating"].agg(
            average_rating="mean", rating_count="count"
        )
        movies = movies.merge(rating_stats, left_on="movieId", right_index=True, how="left")
        movies["rating_count"] = movies["rating_count"].fillna(0).astype(int)
        movies["average_rating"] = movies["average_rating"].round(2)
        movies["year"] = pd.to_numeric(
            movies["title"].str.extract(r"\((\d{4})\)\s*$", expand=False),
            errors="coerce",
        ).astype("Int64")
        movies["display_title"] = movies["title"].str.replace(
            r"\s*\(\d{4}\)\s*$", "", regex=True
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
        movies["genre_list"] = movies["genres"].map(
            lambda value: [
                genre for genre in str(value).split("|") if genre and genre != "(no genres listed)"
            ]
        )
        movies["genres"] = movies["genre_list"].map(lambda values: " · ".join(values))

        tags["movieId"] = pd.to_numeric(tags["movieId"], errors="coerce")
        tags = tags.dropna(subset=["movieId", "tag"]).copy()
        tags["movieId"] = tags["movieId"].astype(int)
        tags["tag"] = tags["tag"].astype(str).str.strip()
        tags = tags[tags["tag"].ne("")]
        tags_by_movie = tags.groupby("movieId")["tag"].agg(
            lambda values: sorted({value.lower() for value in values})
        )
        movies["tag_list"] = movies["movieId"].map(tags_by_movie).map(
            lambda values: values if isinstance(values, list) else []
        )
        movies["feature_text"] = movies.apply(
            lambda movie: " ".join(movie["genre_list"] + movie["tag_list"]), axis=1
        )

        if movies.empty:
            raise DatasetError("The MovieLens movies.csv file contains no movies.")

        self.movies = movies.set_index("movieId", drop=False).sort_index()
        self.ratings = ratings
        self.genres = sorted(
            {
                genre
                for movie_genres in self.movies["genre_list"]
                for genre in movie_genres
            },
            key=str.casefold,
        )
        self._movie_ids = self.movies.index.to_numpy(dtype=int)
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            sublinear_tf=True,
            token_pattern=r"(?u)\b[\w-]+\b",
        )
        self._feature_matrix = self._vectorizer.fit_transform(
            self.movies["feature_text"].tolist()
        )

    @property
    def dataset_status(self) -> dict[str, Any]:
        return {
            "loaded": True,
            "name": DATASET_NAME,
            "movie_count": int(len(self.movies)),
            "rating_count": int(len(self.ratings)),
        }

    def _record(self, movie: pd.Series) -> dict[str, Any]:
        average = movie["average_rating"]
        year = movie["year"]
        return {
            "movie_id": int(movie["movieId"]),
            "title": str(movie["display_title"]),
            "year": int(year) if pd.notna(year) else None,
            "genres": list(movie["genre_list"]),
            "average_rating": float(average) if pd.notna(average) else None,
            "rating_count": int(movie["rating_count"]),
            "imdb_id": self._optional_string(movie.get("imdbId")),
        }

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None or pd.isna(value) or str(value) == "0":
            return None
        return str(value)

    def list_movies(
        self,
        *,
        search: str = "",
        genre: str = "",
        sort: str = "title",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        movies = self.movies
        if search.strip():
            movies = movies[
                movies["display_title"].str.contains(
                    re.escape(search.strip()), case=False, regex=True, na=False
                )
            ]
        if genre:
            genre_matches = movies["genre_list"].map(
                lambda values: genre in values
            ).astype(bool)
            movies = movies[genre_matches]

        sort_columns = {
            "title": ("display_title", True),
            "rating": ("average_rating", False),
            "year": ("year", False),
            "popular": ("rating_count", False),
        }
        sort_column, ascending = sort_columns[sort]
        movies = movies.sort_values(
            [sort_column, "display_title"],
            ascending=[ascending, True],
            na_position="last",
        )
        total = int(len(movies))
        start = (page - 1) * page_size
        results = [self._record(movie) for _, movie in movies.iloc[start : start + page_size].iterrows()]
        return {
            "results": results,
            "page": page,
            "page_size": page_size,
            "total_results": total,
            "total_pages": (total + page_size - 1) // page_size,
        }

    def movie_details(self, movie_id: int) -> dict[str, Any] | None:
        if movie_id not in self.movies.index:
            return None
        return self._record(self.movies.loc[movie_id])

    def recommendations(self, movie_id: int, limit: int = 5) -> list[dict[str, Any]] | None:
        if movie_id not in self.movies.index:
            return None
        row = int(np.flatnonzero(self._movie_ids == movie_id)[0])
        scores = cosine_similarity(
            self._feature_matrix[row], self._feature_matrix, dense_output=True
        ).ravel()
        scores[row] = -1
        candidate_rows = np.argsort(-scores, kind="stable")
        selected = self.movies.loc[movie_id]
        recommendations: list[dict[str, Any]] = []

        for candidate_row in candidate_rows:
            if scores[candidate_row] <= 0 or len(recommendations) >= limit:
                break
            candidate = self.movies.iloc[candidate_row]
            shared_genres = sorted(
                set(selected["genre_list"]) & set(candidate["genre_list"]),
                key=str.casefold,
            )
            shared_tags = sorted(
                set(selected["tag_list"]) & set(candidate["tag_list"]),
                key=str.casefold,
            )
            reasons = []
            if shared_genres:
                reasons.append("Shares genres: " + ", ".join(shared_genres))
            if shared_tags:
                reasons.append("Shares tags: " + ", ".join(shared_tags[:5]))
            recommendations.append(
                {
                    **self._record(candidate),
                    "similarity": round(float(scores[candidate_row]), 4),
                    "matching_genres": shared_genres,
                    "matching_tags": shared_tags[:5],
                    "explanation": "; ".join(reasons)
                    or "Shares related TF-IDF genre and tag features.",
                }
            )
        return recommendations

    def stats(self) -> dict[str, Any]:
        latest_timestamp = int(self.ratings["timestamp"].max())
        cutoff = latest_timestamp - 365 * 24 * 60 * 60
        recent_ratings = self.ratings[self.ratings["timestamp"] >= cutoff]
        if recent_ratings.empty:
            recent_ratings = self.ratings
        recent_counts = recent_ratings.groupby("movieId").size()
        recent = self.movies.copy()
        recent["recent_rating_count"] = (
            recent["movieId"].map(recent_counts).fillna(0).astype(int)
        )

        minimum_count = self.minimum_rating_count
        highly_rated = self.movies[
            self.movies["rating_count"] >= minimum_count
        ].sort_values(
            ["average_rating", "rating_count", "display_title"],
            ascending=[False, False, True],
            na_position="last",
        )
        popular = self.movies.sort_values(
            ["rating_count", "average_rating", "display_title"],
            ascending=[False, False, True],
        )
        trending = recent.sort_values(
            ["recent_rating_count", "rating_count", "display_title"],
            ascending=[False, False, True],
        )
        genre_counts = {
            genre: int(
                sum(genre in movie_genres for movie_genres in self.movies["genre_list"])
            )
            for genre in self.genres
        }
        return {
            "dataset": self.dataset_status,
            "average_rating": round(float(self.ratings["rating"].mean()), 2),
            "unique_users": int(self.ratings["userId"].nunique()),
            "year_range": {
                "first": int(self.movies["year"].min()),
                "last": int(self.movies["year"].max()),
            },
            "minimum_rating_count": minimum_count,
            "trending_basis": "Rating activity in the latest 365 days recorded in MovieLens.",
            "trending": [
                {
                    **self._record(movie),
                    "recent_rating_count": int(movie["recent_rating_count"]),
                }
                for _, movie in trending.head(6).iterrows()
            ],
            "popular": [self._record(movie) for _, movie in popular.head(6).iterrows()],
            "highly_rated": [
                self._record(movie) for _, movie in highly_rated.head(10).iterrows()
            ],
            "genre_counts": genre_counts,
        }

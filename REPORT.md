# Movie Recommendation System Using Machine Learning

**CineMatch — 3rd Semester CSE Minor Project**
**Programme:** AI for Youth Program
**Project type:** Standalone frontend application with an optional Flask API
**Technologies:** HTML5, CSS3, vanilla JavaScript, Python, Flask, Pandas, NumPy, scikit-learn

## Abstract

CineMatch is a locally runnable browser application for exploring films and discovering titles with similar content. It uses records from the official MovieLens Latest Small dataset for movie titles, release years, genres, user-supplied tags, and rating aggregates. The bundled browser data is derived from the official CSV files; the full rating rows are not included. The browser builds TF-IDF vectors and uses cosine similarity to rank movies with related genres and tags. The interface provides search, genre filtering, sorting, pagination, movie details, explanations, and a watchlist stored in browser local storage. An optional Flask API is also included, but the website does not require it.

The implemented algorithm is **content-based similarity**. It does not train a supervised predictive model and is not classification, regression, or clustering. The project name and educational context do not imply otherwise.

## Problem statement

Movie catalogues contain many titles, and browsing by title alone does not help a viewer discover films with similar themes or categories. The project explores how a small, explainable content-based recommender can rank related films using available movie metadata, while showing the actual MovieLens rating evidence separately from the similarity score.

## Objectives

1. Use an authentic, locally cached movie dataset rather than invented catalogue records or ratings.
2. Provide a responsive browser interface that runs from a local HTML file without a server.
3. Compute movie-to-movie content similarity from genres and tags.
4. Explain recommendations using shared features and show numerical similarity scores.
5. Calculate average ratings and rating counts from `ratings.csv`.
6. Test data processing, validation, and API behavior.
7. Document the algorithm, source data, limitations, and possible extensions honestly.

## Dataset description

The system downloads **MovieLens Latest Small** from the official GroupLens dataset page:

- `movies.csv`: MovieLens `movieId`, title, and pipe-separated genre labels.
- `ratings.csv`: user ID, movie ID, rating on the dataset's five-star scale, and Unix timestamp.
- `tags.csv`: user-applied tag text associated with a movie.
- The archive may also contain `links.csv`, which provides IMDb identifiers for poster lookups; movie posters are not part of this project dataset.

The optional API downloads and extracts CSV files under `data\` only when required files are missing; this raw data directory is ignored by Git. The standalone browser bundle, `frontend\movies-data.js`, is generated from those authentic CSV files by `tools\build_browser_data.py`. It contains catalogue metadata, available tags, and aggregates, but not the full rating rows. Average movie ratings and rating counts come from the actual rating rows. Movie records, features, and ratings are not manually authored.

## Data preprocessing

1. Load the three CSV files with Pandas and check their required columns.
2. Convert IDs, ratings, timestamps, and release years to appropriate numeric types; discard rows with unusable required values.
3. Aggregate ratings by movie ID to calculate mean rating and count. Movies without ratings remain in the catalogue with a zero count and no average.
4. Parse a four-digit year from a trailing parenthetical title year and retain the display title without that suffix.
5. Split MovieLens genre strings on `|`; the original labels, including `Sci-Fi`, are retained for filtering.
6. Normalize available user tags for feature documents, remove duplicate per-movie tags, and combine them with the movie's genres.
7. Keep the TF-IDF matrix sparse. Recommendations compute only the requested movie's similarity vector.

## Recommendation method

### TF-IDF

For every movie, the text document contains its actual genre labels and available MovieLens tags. The browser tokenizes this text, ignores common English stop words, considers one- and two-word terms, and applies sublinear term frequency. If a term occurs frequently in one movie document but across many documents, its contribution is adjusted by inverse document frequency. The resulting sparse, normalized vector represents that movie's descriptive content. The optional API implements the same content-based method using scikit-learn's `TfidfVectorizer`.

### Cosine similarity

For the selected movie vector \(x\) and another movie vector \(y\), similarity is:

\[
\operatorname{cosine}(x,y)=\frac{x \cdot y}{\|x\|_2\|y\|_2}
\]

The result is a score from 0 (no shared vector direction/features) toward 1 (very similar feature vectors). The browser uses an inverted feature index to score only candidates that share a feature, excludes the selected movie ID, and returns up to five results. The optional API accepts a configurable limit. Explanations list shared genres and tags where available. Similarity is not a predicted user rating.

This is a content-based information-retrieval/ranking approach. It does **not** perform:

- **Classification:** assigning a movie to a learned target class.
- **Regression:** predicting a numeric target such as a user's rating.
- **Clustering:** fitting groups of movies without a selected query item.

If a course rubric specifically requires one of those methods, it should be added as a separate, clearly named and evaluated experiment. For example, a future rating-prediction extension could use a train/test split and a rating model; a genre classifier would need a defined target and validation. Neither should be represented as the current recommender.

## System architecture

```text
Standalone (open frontend\index.html)
    ├── frontend\movies-data.js: MovieLens-derived catalogue and aggregates
    └── frontend\script.js: browser search, TF-IDF, cosine scoring, and UI

Optional API (python -m backend.app)
    ├── Flask REST endpoints
    ├── Pandas: CSV loading and rating aggregation
    └── scikit-learn / NumPy: TF-IDF and cosine scoring
             │
             ▼
        MovieLens CSV files in data\
```

The primary website runs without a web server: open `frontend\index.html`, and the relative script, style, and data files load from the same folder. The browser prepares sparse recommendation features and calculates similarities locally. Optionally, Flask serves a REST API on `http://127.0.0.1:5000`; its dataset is loaded and features are precomputed once per application start. API validation returns clear JSON errors for invalid filters, pagination, recommendation limits, and unknown movie IDs.

## Implementation

- **Movie browse API:** searches movie titles, filters using real genre labels, sorts by title, rating, year, or rating count, and returns bounded pages.
- **Movie details API:** returns MovieLens movie ID, display title, release year, genres, average rating, and number of rating rows.
- **Standalone frontend:** searches, filters, sorts, paginates, and displays MovieLens-derived movie records without API requests. It calculates TF-IDF/cosine recommendations and shows shared-feature explanations, similarity percentages, activity-based trends, and rating-thresholded titles.
- **Optional REST API:** exposes health, movie, genre, statistics, and recommendation endpoints for backend demonstrations and tests.
- **Watchlist:** saves selected MovieLens movie IDs in browser local storage.
- **Artwork:** MovieLens does not include poster assets. The frontend uses movie IMDb IDs to request posters from the Metahub image service and falls back to a decorative title card made from real title/year/genre data if an image is unavailable. Loading remote posters requires an internet connection; the catalogue and recommendations still work offline.

The highly rated list uses a configurable-in-code default minimum of 50 rating rows per movie to reduce the influence of titles with very few ratings. “Trending” means movies with the most rating activity in the most recent 365-day window relative to the latest timestamp recorded in the dataset. It does not claim to represent current real-world trends.

## Testing and results

Run `.\.venv\Scripts\python.exe -m pytest -q` from the project root to test the optional API. The tests use small temporary CSV fixtures and do not depend on network access. They cover dataset loading and missing-file reporting, actual rating aggregates, title search, genre filtering, movie detail lookup, cosine-ranked recommendations, exclusion of the selected movie, invalid IDs and parameters, health status, empty results, and dataset statistics. The standalone HTML page and its search, filtering, recommendations, watchlist, and mobile layout were also checked directly in a browser without running Flask.

The raw MovieLens rating rows are not checked into the repository. The optional API downloads them on demand; the standalone app uses a compact browser bundle containing real movie metadata, tags, and calculated rating aggregates.

## Limitations

- Content similarity depends on the available genres and user-generated tags; tags may be sparse or inconsistent.
- The recommender does not personalize to a viewer's watch/rating history and may have a cold-start problem for items with few descriptive features.
- Cosine similarity measures feature overlap, not quality, preference, causality, or a predicted rating.
- MovieLens Latest Small is a research/educational dataset and is not a comprehensive or real-time catalogue.
- Poster images are provided by an external image service and require an internet connection; MovieLens does not include poster assets.
- The watchlist is local to one browser and is not synchronized or backed up.
- Trending uses dataset timestamps and can be historically dated.
- This system is not a production deployment and does not include accounts, moderation, or a database.

## Future scope

- Add a separately evaluated collaborative-filtering experiment using user–item ratings.
- If required by a course rubric, add a distinct supervised classification or regression module with appropriate targets, train/test splits, and metrics; do not mislabel content similarity as one of those methods.
- Add clustering as an optional exploratory analysis, with a separately documented feature representation and cluster evaluation.
- Compare content-based and collaborative approaches using precision/recall at \(k\), coverage, and a held-out temporal or user split.
- Add richer licensed metadata and poster artwork from an appropriately attributed source.
- Add persistent user accounts or a database only if the project scope and privacy requirements permit them.

## References

1. F. M. Harper and J. A. Konstan, “The MovieLens Datasets: History and Context,” *ACM Transactions on Interactive Intelligent Systems*, vol. 5, no. 4, Article 19, 2015. https://doi.org/10.1145/2827872
2. GroupLens Research, “MovieLens Latest Small Dataset,” https://grouplens.org/datasets/movielens/latest/
3. Scikit-learn developers, “TfidfVectorizer,” https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html
4. Scikit-learn developers, “cosine_similarity,” https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html

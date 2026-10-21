# CineMatch — Movie Recommendation System

CineMatch is an educational movie recommendation app built from the official **MovieLens Latest Small** dataset. The website runs directly in a browser: it does **not** need Flask, Python, a terminal, or an API server. Movie data and the TF-IDF/cosine-similarity recommendation algorithm are included in the frontend. Internet access is needed to load real poster images and externally hosted fonts/backgrounds.

## Run the website without a backend

1. In VS Code, open the `frontend` folder.
2. Open `index.html`.
3. Choose **Reveal in File Explorer** and double-click `index.html`, or right-click it and choose **Open with Live Server** if you have that VS Code extension.

For the standalone version, keep `index.html`, `style.css`, `script.js`, and `movies-data.js` together in `frontend\`. No package installation or setup commands are required. The bundled MovieLens data, recommendations, and locally generated title-card fallback work offline. The watchlist is kept in browser local storage when that browser allows local-file storage.

## Data and recommendation algorithm

`frontend\movies-data.js` contains movie records and rating aggregates generated from the official MovieLens CSV files, not invented sample entries. It includes MovieLens titles, years, genres, available tags, average ratings, and rating counts. The original ratings rows are not bundled.

The browser builds sparse, normalized TF-IDF feature vectors from each movie's genre and tag text, then uses an inverted feature index to calculate cosine similarity for a selected title. It excludes that title from its recommendations and displays the shared features. No backend or prewritten recommendation lists are used.

The current algorithm is **content-based similarity**. It is not classification, regression, clustering, or a trained predictive model. Trending and rating statistics are calculated from the dataset; trending is based on its recorded rating timestamps, not current real-world activity.

MovieLens does not include poster files. For movies that have an IMDb ID, the site displays the corresponding poster from the free, keyless Metahub image service (`images.metahub.space`). If a poster is missing or unavailable, it falls back to a decorative title card using the real movie name and catalogue details.

## Refresh the bundled data

The standalone app continues to work from its existing `movies-data.js` bundle. To refresh it from the official dataset, install the optional Python dependencies, download/extract the official MovieLens archive into `data\`, and run this command from the project root:

```powershell
.\.venv\Scripts\python.exe tools\build_browser_data.py
```

The bundle is derived movie metadata, tags, and rating aggregates; it does not include the full ratings rows. The optional Flask API can download the archive into `data\` if it is not already present.

## Optional Flask API

The project also retains a Flask REST API for coursework demonstrations and automated endpoint tests. **The browser app does not call it and does not need it to run.**

From the project root, in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m backend.app
```

The API is available at `http://127.0.0.1:5000/api/`. It downloads the official MovieLens archive into `data\` only when the CSV files are missing. If you want to open the frontend through Flask, the browser can open `http://127.0.0.1:5000/`.

Run the backend tests from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

API endpoints include `/api/health`, `/api/movies`, `/api/movies/<movie_id>`, `/api/recommend/<movie_id>?limit=5`, `/api/genres`, and `/api/stats`.

## Project structure

```text
backend/                 Optional Flask API and Python recommender
data/                    Downloaded CSV data for the optional API; Git-ignored
frontend/
  index.html             Open this file to run without a backend
  style.css              Responsive cinematic styling
  script.js              Search, filters, watchlist, and browser TF-IDF
  movies-data.js         MovieLens-derived, standalone browser data bundle
tools/
  build_browser_data.py  Refresh the browser data bundle from MovieLens CSVs
tests/                   Optional backend API and data tests
README.md                Run instructions and attribution
REPORT.md                Academic report and methodology
```

## Dataset attribution

The source is [MovieLens Latest Small](https://grouplens.org/datasets/movielens/latest/) from GroupLens Research. Keep this attribution with the project and follow the dataset's usage terms. Reference: F. M. Harper and J. A. Konstan, “The MovieLens Datasets: History and Context,” *ACM Transactions on Interactive Intelligent Systems*, vol. 5, no. 4, Article 19, 2015, https://doi.org/10.1145/2827872.

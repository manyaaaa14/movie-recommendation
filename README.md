# CineMatch — Movie Recommendation System

CineMatch is a MovieLens recommendation application with a real browser-trained matrix-factorization model. It can still run as a standalone site, and can optionally sync browser watchlists to MongoDB through a Flask API deployed on Render.

## Run locally without a backend

1. Open `frontend\index.html` in a browser or use VS Code Live Server.
2. Keep `index.html`, `config.js`, `style.css`, `script.js`, `model.js`, `movies-data.js`, and `ratings-data.js` together.
3. Wait for the model to train, then choose a MovieLens demo user.

The ML model trains in the browser from real MovieLens rating data and shows held-out RMSE and MAE. No server is required for movie search, recommendations, or a local watchlist. Poster images need an internet connection; a local fallback is used when images are unavailable.

## Deploy the full-stack version

This setup uses **Netlify for the static site, Render for Flask, and MongoDB Atlas for watchlist persistence**. No database password or other secret belongs in Git or frontend code.

### 1. Create a MongoDB Atlas database

1. Create a free Atlas cluster and database named `cinematch`.
2. Create a database user with a strong password and access only to the `cinematch` database.
3. In Network Access, allow the Render service to reach the cluster. Render's free/shared outbound IPs may change; for a student demo, Atlas may require allowing `0.0.0.0/0`. Use a unique strong database password, keep the URI secret, and do not store personal information in this anonymous demo watchlist.
4. Copy the Atlas **Drivers** connection string and replace its password placeholder. URL-encode special characters in the password.

The backend stores only a random browser UUID, MovieLens movie IDs, and an update timestamp. It does not store names, emails, user ratings, or authentication credentials. This is demo persistence, **not a private account system**: anyone who obtains a browser's UUID can access that browser's watchlist. CORS limits normal browser origins but is not authentication.

### 2. Deploy the API to Render

1. Push the project to the GitHub repository and ensure the current code is on your deployment branch.
2. In Render, choose **New → Blueprint**, connect the repository, and let Render read [`render.yaml`](./render.yaml).
3. In the Render service's **Environment** settings, set:
   - `MONGODB_URI`: the Atlas connection string (mark/store it as a secret; never commit it).
   - `MONGODB_DATABASE`: `cinematch` (the blueprint supplies this).
   - `CORS_ALLOWED_ORIGINS`: your exact Netlify site origin, for example `https://your-site-name.netlify.app` (no path or trailing slash).
4. Deploy. Render downloads MovieLens when required CSVs are missing. Verify:
   - `https://YOUR-RENDER-SERVICE.onrender.com/api/health`
   - Health JSON reports `"loaded": true` for the dataset and `"connected": true` for MongoDB.

The Blueprint runs one Gunicorn worker with threads, checks `/api/health`, and uses `backend/requirements.txt`. The free Render service may sleep when idle, so its first request after inactivity can take longer.

### 3. Deploy the site to Netlify

1. In Netlify, choose **Add new site → Import an existing project** and select the same GitHub repository.
2. Keep the repository root as the base directory; [`netlify.toml`](./netlify.toml) sets the publish folder to `frontend`.
3. In the site's **Environment variables**, set:
   - `CINEMATCH_API_BASE_URL`: `https://YOUR-RENDER-SERVICE.onrender.com/api`
4. Deploy. The Netlify build generates `frontend/config.js` with that public API URL. The API URL is public configuration, not a secret.
5. Set the exact deployed Netlify origin in Render's `CORS_ALLOWED_ORIGINS`, then redeploy the Render service if needed.

The browser keeps the watchlist locally first, then syncs it to MongoDB when the deployed API is reachable. If MongoDB or Render is unavailable, the local watchlist continues to work. This initial integration intentionally uses anonymous browser IDs without login.

### Run locally with the optional API and MongoDB

In PowerShell, from the project root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:MONGODB_URI = "YOUR_ATLAS_CONNECTION_STRING"
$env:MONGODB_DATABASE = "cinematch"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:5500"
.\.venv\Scripts\python.exe -m backend.app
```

With Live Server on port 5500, `frontend\config.js` defaults to `/api`, so set `window.CINEMATCH_CONFIG.apiBaseUrl` to `http://127.0.0.1:5000/api` for that local frontend. The standalone `file://` version deliberately skips cloud sync and works without secrets or a backend.

## Refresh the bundled MovieLens data

The standalone site includes its movie catalogue and compact training ratings. To rebuild the bundles from official CSV files:

```powershell
.\.venv\Scripts\python.exe tools\build_browser_data.py
```

The bundle includes actual MovieLens user/movie/rating triples (no timestamps) so the ML model can train offline. The full raw dataset in `data\` remains Git-ignored.

## Machine-learning method

The main recommender is collaborative-filtering matrix factorization, trained by stochastic gradient descent on MovieLens explicit ratings. It uses a deterministic 85% training / 15% holdout split, predicts ratings for unseen movies, and reports RMSE/MAE alongside a global-mean baseline. “More Like This” is a separate genre/tag TF-IDF feature, not the trained rating-prediction model. See [REPORT.md](./REPORT.md) for the method, evaluation, and limitations.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node .\tests\test_model.js
```

The Flask API also exposes `/api/health`, `/api/movies`, `/api/movies/<movie_id>`, `/api/recommend/<movie_id>`, `/api/genres`, `/api/stats`, and `/api/watchlist/<client_uuid>`.

## Project structure

```text
backend/                 Optional Flask API, MovieLens recommender, MongoDB store
data/                    Downloaded raw dataset; Git-ignored
frontend/                Netlify static site and bundled browser ML model
tests/                   API, bundle, and JavaScript model tests
tools/                   MovieLens bundle and Netlify config generators
render.yaml              Render Blueprint
netlify.toml              Netlify build/publish configuration
README.md                 Local and deployment instructions
REPORT.md                 Academic methodology and results
```

## Dataset and artwork attribution

Dataset: [MovieLens Latest Small](https://grouplens.org/datasets/movielens/latest/), GroupLens Research. Reference: F. M. Harper and J. A. Konstan, “The MovieLens Datasets: History and Context,” *ACM Transactions on Interactive Intelligent Systems*, vol. 5, no. 4, Article 19, 2015, https://doi.org/10.1145/2827872. MovieLens does not provide posters; images are loaded by IMDb ID from the keyless Metahub image service, with a local generated title-card fallback.

# Movie Recommendation System Using Machine Learning

**CineMatch — 3rd Semester CSE Minor Project**
**Programme:** AI for Youth Program
**Project type:** Standalone browser ML application with an optional Flask API
**Technologies:** HTML5, CSS3, JavaScript, Python, Flask, Pandas, NumPy, scikit-learn

## Abstract

CineMatch is a movie recommender built from the official MovieLens Latest Small dataset. Its primary application runs directly in a web browser without a backend. The browser trains an explicit-feedback collaborative-filtering model on MovieLens user ratings and predicts ratings for movies a selected anonymized user has not rated. The application displays the top predicted films and validates the model using a separate held-out rating set, reporting root mean squared error (RMSE) and mean absolute error (MAE). It also provides movie search, genre filtering, movie details, data-derived rating statistics, a local watchlist, and a separate content-based “More Like This” feature. An optional Flask API remains available for endpoint demonstrations.

The primary recommendation engine is **machine learning**: user and movie latent factors and rating biases are learned from observed ratings using stochastic gradient descent. It is collaborative filtering, not genre classification, rating regression as a separate supervised task, or clustering. The held-out metrics evaluate rating predictions by this factorization model.

## Problem statement

Finding movies suited to a viewer's taste is difficult when a large catalogue is ordered only by popularity or title. Movie ratings contain signals about which titles different viewers appreciate. This project uses those observed ratings to learn user and movie representations and predict which unseen movies a sample user's preferences may favor.

## Objectives

1. Use authentic movie metadata, tags, and user ratings from GroupLens MovieLens Latest Small.
2. Train a real collaborative-filtering model on the rating data.
3. Recommend movies by predicting a selected user's ratings for unseen titles.
4. Evaluate rating prediction using a deterministic train/holdout split, RMSE, MAE, and a mean-only baseline.
5. Make the main application easy to run without Python or a server.
6. Keep a separate, clearly labeled content-based similarity feature.
7. Document data handling, evaluation, limitations, and future experiments.

## Dataset

The application uses the official [MovieLens Latest Small](https://grouplens.org/datasets/movielens/latest/) files:

- `movies.csv`: MovieLens movie IDs, titles, and genre labels.
- `ratings.csv`: anonymized user IDs, movie IDs, ratings from 0.5 to 5 stars, and timestamps.
- `tags.csv`: MovieLens user-supplied tags.
- `links.csv`, when present: IMDb identifiers used to look up poster images.

The data bundles in `frontend\movies-data.js` and `frontend\ratings-data.js` are reproducibly built by `tools\build_browser_data.py`. The browser rating bundle contains 100,836 actual user/movie/rating triples in compact binary-encoded form; timestamps are omitted. The rating triples are included because they are the training data needed for an offline model. The original CSVs are kept in the ignored `data\` directory rather than uploaded as duplicate raw files. Movie titles, genres, tags, and per-film rating aggregates are derived from the official dataset.

## Data preprocessing

1. Read MovieLens CSVs and validate their structure.
2. Parse title years and retain real MovieLens genre labels.
3. Calculate each movie's mean rating and rating count from `ratings.csv`.
4. Normalize and deduplicate user tags for the separate content-based feature.
5. Map the catalogue's movie IDs to compact zero-based indices for matrix-factorization lookups.
6. Encode each rating as a little-endian 16-bit user ID, 16-bit movie index, and 8-bit half-star rating. The encoding preserves the actual 0.5-star increments without retaining the timestamp column.
7. Create a seeded random 85% training / 15% validation split when the model is trained. Only training ratings update the model; validation ratings are held out for metrics.

## Machine-learning method: collaborative-filtering matrix factorization

Let \(r_{ui}\) be the observed rating by user \(u\) for movie \(i\). The model predicts:

\[
\hat r_{ui} = \mu + b_u + b_i + p_u^\top q_i
\]

where \(\mu\) is the mean training rating; \(b_u\) and \(b_i\) are learned user and movie biases; and \(p_u\) and \(q_i\) are learned 16-dimensional user and movie latent-factor vectors. The latent factors capture rating patterns inferred from the user–movie ratings matrix.

Training iterates over observed training ratings for 12 epochs using stochastic gradient descent. For each observed rating, the prediction error is used to update the user and movie factors and biases. L2 regularization discourages unnecessarily large parameters. The random seed and split are fixed so repeated browser runs are reproducible. The factors are initialized deterministically. Predictions are clipped to the MovieLens rating range of 0.5–5.0.

After training, the app selects one of the dataset's anonymized example users, excludes every title that user rated, predicts scores for the remaining catalogue, and shows the five highest-scored titles. The displayed personalized values are **model predictions**, not observed ratings.

### Evaluation

For held-out ratings, the app computes:

\[
\operatorname{RMSE} =
\sqrt{\frac{1}{N}\sum_{(u,i)\in H}(r_{ui}-\hat r_{ui})^2}
\qquad
\operatorname{MAE} =
\frac{1}{N}\sum_{(u,i)\in H}|r_{ui}-\hat r_{ui}|
\]

Here \(H\) is the validation set and \(N\) is its number of ratings. CineMatch also shows a **global-mean baseline RMSE**, using only the mean of training ratings. Comparing the learned model to this baseline indicates whether learned user/movie effects improve held-out rating predictions on this split. The numeric result is computed in the browser on startup; it is not a hand-entered score.

With the shipped MovieLens Latest Small bundle and current deterministic settings, the browser trained on **85,711 ratings** and evaluated on **15,125 held-out ratings**. The observed results were **RMSE 0.860**, **MAE 0.662**, and **global-mean baseline RMSE 1.039**. These figures describe this seeded random split only; they are not a guarantee of future or real-world performance.

## Content-based feature (separate from the ML recommender)

The “More Like This” movie-detail action uses a separate TF-IDF feature representation made from actual genres and tags and ranks similar items using cosine similarity. This feature provides a simple item-similarity comparison; it is not the user-rating matrix-factorization model and is not used to claim supervised prediction. The two recommendation methods are distinguished in the UI and this report.

## System architecture

```text
Open frontend\index.html directly in a browser
    ├── movies-data.js: MovieLens catalogue and rating aggregates
    ├── ratings-data.js: compact, authentic MovieLens rating triples
    ├── model.js: seeded train/validation split and matrix-factor SGD
    └── script.js: search, ratings, user-profile picker, and predicted picks

Optional:
    Python / Flask API → Pandas CSV loader → TF-IDF content recommender
```

The standalone app downloads no movie or rating API data, makes no backend calls, and stores no profile information on a server. Its rating model trains locally from the included bundle. Real poster artwork is loaded from an external image service when online; a title-card fallback is shown when artwork is unavailable.

## Implementation

- **Local model training:** deterministic split, biases, 16-dimensional latent vectors, regularized SGD, and progress updates.
- **Evaluation:** validation RMSE and MAE plus a global-mean baseline RMSE, computed from the held-out ratings.
- **Personalized recommendations:** actual anonymized MovieLens user profiles, unseen-film filtering, and ranking by predicted rating.
- **Movie exploration:** paginated title search, actual genres, sorting, movie details, mean ratings, and rating counts.
- **Statistics:** trending and popular sections derived from MovieLens rating data; highly rated titles require a minimum rating count.
- **Additional similarity feature:** genre/tag TF-IDF and cosine similarity, labeled separately from collaborative filtering.
- **Watchlist:** browser local storage; no account or registration.
- **Optional Flask API:** retains the REST API and its content-based recommendation endpoint for backend demonstrations.

## Testing and results

Python tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

JavaScript model smoke test:

```powershell
node .\tests\test_model.js
```

Tests cover MovieLens bundle generation and rating encoding; model training on a fixture; prediction bounds; recommendation of only unseen titles; data loading and rating aggregation; API search, genres, details, recommendations, empty results, validation, and health. The trained model's actual held-out metrics appear in the running UI and can vary only if the configured training split or model parameters are changed.

## Limitations

- MovieLens Latest Small is an educational dataset, not a real-time catalogue.
- The model learns from the available ratings; users or movies with little rating history have less reliable factor estimates.
- Random holdout metrics do not measure temporal generalization or guarantee that the top recommendations will suit a real viewer.
- The selected MovieLens profile IDs are anonymized dataset IDs, not the current viewer's personalized account.
- The standalone rating bundle includes actual user/movie/rating observations without timestamps because those observations are needed to train the model. The raw CSV files remain Git-ignored.
- Content-based tags may be sparse and user-generated.
- Movie posters are not included in MovieLens; artwork relies on an external image service and requires internet access.
- Browser local storage may be unavailable in some private/local-file browsing modes.

## Future scope

- Compare matrix factorization against a tuned global/user/movie-bias baseline and use multiple or temporal holdouts.
- Add ranking metrics such as Precision@K, Recall@K, and catalog coverage in addition to rating-error metrics.
- Explore implicit-feedback matrix factorization or hybrid recommendations using movie genres/tags.
- Add a Python/scikit-learn training and evaluation notebook if an instructor requests a Python ML implementation; keep its split, metrics, and methodology consistent with the browser model.
- Add licensed poster assets or a local artwork cache if redistribution terms permit.
- Add explicit user profiles only with consent and a suitable privacy design.

## References

1. F. M. Harper and J. A. Konstan, “The MovieLens Datasets: History and Context,” *ACM Transactions on Interactive Intelligent Systems*, vol. 5, no. 4, Article 19, 2015. https://doi.org/10.1145/2827872
2. GroupLens Research, “MovieLens Latest Small Dataset,” https://grouplens.org/datasets/movielens/latest/
3. R. Salakhutdinov and A. Mnih, “Probabilistic Matrix Factorization,” *Advances in Neural Information Processing Systems 20*, 2008.

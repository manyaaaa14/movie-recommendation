// All movie data and calculations are local; this page does not call a backend.
const dataset = window.CINEMATCH_DATA;
const PAGE_SIZE = 20;
const WATCHLIST_KEY = "cinematch-watchlist-v1";
const CLIENT_ID_KEY = "cinematch-cloud-client-id-v1";
const API_BASE_URL = String(window.CINEMATCH_CONFIG?.apiBaseUrl || "").replace(/\/+$/, "");
const genreFilter = document.querySelector("#genre-filter");
const movieGrid = document.querySelector("#movie-grid");
const watchlistGrid = document.querySelector("#watchlist-grid");
const dialog = document.querySelector("#movie-dialog");
const movies = dataset?.movies || [];
const moviesById = new Map(movies.map(movie => [movie.movie_id, movie]));
let currentPage = 1;
let totalPages = 1;
let browseTimer;
let featureVectors = [];
let featurePostings = new Map();

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
}

function fallbackPosterData(movie) {
  const palette = ["#493a78", "#24416d", "#5c355d", "#234e51", "#643d35", "#35436b"];
  const colour = palette[Math.abs(Number(movie.movie_id)) % palette.length];
  const title = escapeHTML(movie.title || "Movie");
  const genre = escapeHTML((movie.genres || []).slice(0, 2).join(" · ") || "MOVIELENS");
  const year = movie.year || "CINEMATCH";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 700"><defs><linearGradient id="a" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${colour}"/><stop offset="1" stop-color="#0a0d18"/></linearGradient><radialGradient id="b"><stop stop-color="#a78bfa" stop-opacity=".42"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></radialGradient></defs><rect width="500" height="700" fill="url(#a)"/><circle cx="360" cy="190" r="230" fill="url(#b)"/><path d="M0 540Q150 440 500 520V700H0Z" fill="#080a13" fill-opacity=".52"/><text x="40" y="562" fill="#c3aeff" font-family="Arial,sans-serif" font-size="19" letter-spacing="5">CINEMATCH</text><foreignObject x="40" y="580" width="420" height="82"><div xmlns="http://www.w3.org/1999/xhtml" style="color:#fff;font:700 25px Arial,sans-serif;line-height:1.15">${title}</div></foreignObject><text x="40" y="681" fill="#c7c5d2" font-family="Arial,sans-serif" font-size="14">${escapeHTML(year)}  ·  ${genre}</text></svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function posterData(movie) {
  const imdbId = String(movie.imdb_id || "");
  return /^(?:tt)?\d+$/.test(imdbId)
    ? `https://images.metahub.space/poster/medium/tt${imdbId.replace(/^tt/, "")}/img`
    : fallbackPosterData(movie);
}

function posterImageMarkup(movie, className = "") {
  const fallback = fallbackPosterData(movie).replace(/&/g, "&amp;").replace(/'/g, "&#39;");
  return `<img class="${className}" src="${posterData(movie)}" alt="Movie poster for ${escapeHTML(movie.title)}" loading="lazy" onerror="this.onerror=null;this.src='${fallback}'">`;
}

function loadWatchlist() {
  try {
    const parsed = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]");
    return Array.isArray(parsed)
      ? [...new Set(parsed.filter(id => Number.isInteger(id) && moviesById.has(id)))]
      : [];
  } catch (error) {
    console.warn("Browser storage is unavailable; this watchlist will last only until this tab closes.", error);
    return [];
  }
}

let watchlist = loadWatchlist();

function saveWatchlist() {
  try {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(watchlist));
  } catch (error) {
    console.error("Could not save the watchlist.", error);
    showToast("Watchlist could not be saved in this browser.");
  }
  syncWatchlistToCloud();
}

function getCloudClientId() {
  try {
    let clientId = localStorage.getItem(CLIENT_ID_KEY);
    if (clientId) return clientId;
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map(byte => byte.toString(16).padStart(2, "0")).join("");
    clientId = `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    localStorage.setItem(CLIENT_ID_KEY, clientId);
    return clientId;
  } catch (error) {
    console.error("Could not create a browser-only cloud sync ID.", error);
    return null;
  }
}

function showToast(message) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<span class="toast-symbol" aria-hidden="true">✦</span><span>${escapeHTML(message)}</span>`;
  document.querySelector("#toast-region").append(toast);
  window.setTimeout(() => toast.remove(), 3000);
}

function loadingMarkup(label = "Loading MovieLens movies...") {
  return `<div class="loading-state"><span class="spinner" aria-hidden="true"></span><span>${escapeHTML(label)}</span></div>`;
}

function ratingMarkup(movie) {
  return movie.average_rating == null
    ? "Not rated"
    : `★ ${Number(movie.average_rating).toFixed(2)} <span class="rating-count">(${Number(movie.rating_count).toLocaleString()} ratings)</span>`;
}

function cardMarkup(movie, { recommendation = false } = {}) {
  const saved = watchlist.includes(movie.movie_id);
  const genre = movie.genres?.[0] || "Uncategorised";
  const score = movie.predicted_rating != null
    ? `<span class="prediction-rating">Predicted ★ ${Number(movie.predicted_rating).toFixed(2)} / 5</span>`
    : recommendation
      ? `<span class="similarity-score">${(Number(movie.similarity) * 100).toFixed(1)}% match</span>`
      : "";
  return `<article class="movie-card" data-movie-id="${movie.movie_id}">
    <div class="poster-wrap">
      ${posterImageMarkup(movie)}
      <span class="poster-title-overlay" aria-hidden="true">${escapeHTML(movie.title)}</span>
      <span class="poster-rating">${movie.average_rating == null ? "NEW" : `★ ${Number(movie.average_rating).toFixed(1)}`}</span>
      <button class="watch-toggle ${saved ? "saved" : ""}" type="button" data-action="watch" data-id="${movie.movie_id}" aria-label="${saved ? "Remove" : "Add"} ${escapeHTML(movie.title)} ${saved ? "from" : "to"} watchlist" aria-pressed="${saved}">${saved ? "♥" : "♡"}</button>
    </div>
    <div class="movie-info">
      <h3 title="${escapeHTML(movie.title)}">${escapeHTML(movie.title)}</h3>
      <div class="movie-meta"><span>${movie.year ?? "Year unknown"}</span><span class="meta-dot">•</span><span>${escapeHTML(genre)}</span></div>
      <div class="movie-rating-line">${ratingMarkup(movie)}</div>
      ${score}
      <div class="card-actions">
        <button class="card-details" type="button" data-action="details" data-id="${movie.movie_id}">Movie details</button>
        <button class="card-heart ${saved ? "saved" : ""}" type="button" data-action="watch" data-id="${movie.movie_id}" aria-label="${saved ? "Remove" : "Add"} ${escapeHTML(movie.title)} ${saved ? "from" : "to"} watchlist" aria-pressed="${saved}">${saved ? "♥" : "♡"}</button>
      </div>
    </div>
  </article>`;
}

function renderCards(target, items, options = {}) {
  target.innerHTML = items.map(movie => cardMarkup(movie, options)).join("");
}

function tokenizeFeatures(movie) {
  const text = [...movie.genres, ...movie.tags].join(" ").toLowerCase();
  const words = text.match(/[\p{L}\p{N}]+/gu) || [];
  const stopWords = tokenizeFeatures.stopWords;
  const tokens = words.filter(word => word.length > 1 && !stopWords.has(word));
  const terms = [...tokens];
  for (let index = 0; index < tokens.length - 1; index += 1) {
    terms.push(`${tokens[index]} ${tokens[index + 1]}`);
  }
  return terms;
}
tokenizeFeatures.stopWords = new Set([
  "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
  "into", "is", "it", "of", "on", "or", "that", "the", "this", "to", "with"
]);

// Build sparse, normalized TF-IDF vectors and an inverted index for fast query-time scoring.
function buildFeatureIndex() {
  const documents = movies.map(tokenizeFeatures);
  const documentFrequency = new Map();
  documents.forEach(terms => {
    for (const term of new Set(terms)) {
      documentFrequency.set(term, (documentFrequency.get(term) || 0) + 1);
    }
  });

  featureVectors = documents.map((terms, movieIndex) => {
    const termCounts = new Map();
    terms.forEach(term => termCounts.set(term, (termCounts.get(term) || 0) + 1));
    const weightedTerms = [];
    let squaredLength = 0;
    for (const [term, count] of termCounts) {
      const frequency = documentFrequency.get(term);
      const inverseDocumentFrequency = Math.log((movies.length + 1) / (frequency + 1)) + 1;
      const weight = (1 + Math.log(count)) * inverseDocumentFrequency;
      weightedTerms.push([term, weight]);
      squaredLength += weight * weight;
    }
    const length = Math.sqrt(squaredLength) || 1;
    const vector = weightedTerms.map(([term, weight]) => [term, weight / length]);
    vector.forEach(([term, weight]) => {
      if (!featurePostings.has(term)) featurePostings.set(term, []);
      featurePostings.get(term).push([movieIndex, weight]);
    });
    return vector;
  });
}

function movieById(id) {
  return moviesById.get(Number(id)) || null;
}

function findSimilarMovies(selectedMovie, limit = 5) {
  const movieIndex = movies.findIndex(movie => movie.movie_id === selectedMovie.movie_id);
  if (movieIndex < 0) return [];
  const scores = new Map();
  for (const [term, selectedWeight] of featureVectors[movieIndex]) {
    for (const [candidateIndex, candidateWeight] of featurePostings.get(term) || []) {
      if (candidateIndex === movieIndex) continue;
      scores.set(candidateIndex, (scores.get(candidateIndex) || 0) + selectedWeight * candidateWeight);
    }
  }
  const selectedGenres = new Set(selectedMovie.genres);
  const selectedTags = new Set(selectedMovie.tags);
  return [...scores.entries()]
    .filter(([, similarity]) => similarity > 0)
    .sort((first, second) =>
      second[1] - first[1] ||
      movies[first[0]].movie_id - movies[second[0]].movie_id
    )
    .slice(0, limit)
    .map(([index, similarity]) => {
      const movie = movies[index];
      const matchingGenres = movie.genres.filter(genre => selectedGenres.has(genre));
      const matchingTags = movie.tags.filter(tag => selectedTags.has(tag)).slice(0, 5);
      const reasons = [];
      if (matchingGenres.length) reasons.push(`Shares genres: ${matchingGenres.join(", ")}`);
      if (matchingTags.length) reasons.push(`Shares tags: ${matchingTags.join(", ")}`);
      return {
        ...movie,
        similarity,
        matching_genres: matchingGenres,
        matching_tags: matchingTags,
        explanation: reasons.join("; ") || "Shares related TF-IDF genre and tag features."
      };
    });
}

// Filter the bundled data in the browser and return one page of actual movie records.
function loadMovies() {
  const search = document.querySelector("#movie-search").value.trim().toLowerCase();
  const genre = genreFilter.value;
  const sort = document.querySelector("#sort-filter").value;
  let results = movies.filter(movie =>
    movie.title.toLowerCase().includes(search) &&
    (!genre || movie.genres.includes(genre))
  );
  const comparators = {
    popular: (first, second) =>
      second.rating_count - first.rating_count ||
      (second.average_rating || 0) - (first.average_rating || 0) ||
      first.title.localeCompare(second.title),
    rating: (first, second) =>
      (second.average_rating || 0) - (first.average_rating || 0) ||
      second.rating_count - first.rating_count ||
      first.title.localeCompare(second.title),
    year: (first, second) =>
      (second.year || 0) - (first.year || 0) || first.title.localeCompare(second.title),
    title: (first, second) => first.title.localeCompare(second.title)
  };
  results.sort(comparators[sort] || comparators.popular);

  const total = results.length;
  totalPages = Math.ceil(total / PAGE_SIZE);
  const start = (currentPage - 1) * PAGE_SIZE;
  const page = results.slice(start, start + PAGE_SIZE);
  renderCards(movieGrid, page);
  document.querySelector("#results-count").textContent =
    `${total.toLocaleString()} ${total === 1 ? "movie" : "movies"}`;
  document.querySelector("#search-empty").classList.toggle("hidden", page.length > 0);
  document.querySelector("#pagination").hidden = totalPages <= 1;
  document.querySelector("#pagination").classList.toggle("hidden", totalPages <= 1);
  document.querySelector("#page-label").textContent =
    `Page ${currentPage} of ${Math.max(totalPages, 1)}`;
  document.querySelector("#previous-page").disabled = currentPage <= 1;
  document.querySelector("#next-page").disabled = currentPage >= totalPages;
}

function renderStatMovie(movie, index, trending = false) {
  const statistic = trending
    ? `${Number(movie.recent_rating_count).toLocaleString()} recent ratings · ${ratingMarkup(movie)}`
    : `${movie.year ?? "Year unknown"} · ${ratingMarkup(movie)}`;
  return `<button class="trending-card" type="button" data-action="details" data-id="${movie.movie_id}" style="background-image:url('${posterData(movie)}')">
    <span class="trending-number">0${index + 1}</span>
    <span class="trending-info"><h3>${escapeHTML(movie.title)}</h3><span>${statistic}</span></span>
  </button>`;
}

function renderStats() {
  const stats = dataset;
  document.querySelector("#stat-movies").textContent = stats.dataset.movie_count.toLocaleString();
  document.querySelector("#stat-ratings").textContent = stats.dataset.rating_count.toLocaleString();
  document.querySelector("#stat-users").textContent = stats.dataset.unique_users.toLocaleString();
  document.querySelector("#stat-average").textContent = `${stats.dataset.average_rating.toFixed(2)} / 5`;
  document.querySelector("#hero-dataset-caption").textContent =
    `${stats.dataset.movie_count.toLocaleString()} MOVIES · ${stats.dataset.rating_count.toLocaleString()} RATINGS`;
  document.querySelector("#trending-row").innerHTML = stats.trending
    .map((movie, index) => renderStatMovie(movie, index, true)).join("");
  document.querySelector("#popular-row").innerHTML = stats.popular
    .map((movie, index) => renderStatMovie(movie, index)).join("");
  document.querySelector("#rating-threshold").textContent =
    `At least ${stats.dataset.minimum_rating_count} ratings per movie`;
  renderCards(document.querySelector("#top-rated-grid"), stats.highly_rated);
  if (stats.popular[0]) {
    document.querySelector("#featured-copy").textContent =
      `${stats.popular[0].title} is one of the most-rated films in the dataset, with ${stats.popular[0].rating_count.toLocaleString()} community ratings.`;
    document.querySelector("#featured-button").dataset.id = stats.popular[0].movie_id;
  }
  document.querySelectorAll(".genre-pill").forEach(pill => {
    const count = stats.genre_counts[pill.dataset.genre] || 0;
    pill.title = `${count.toLocaleString()} movies`;
  });
}

function showDetails(movie) {
  if (!movie) return;
  if (!dialog.open) dialog.showModal();
  document.querySelector("#dialog-content").innerHTML = `<div class="dialog-layout">
    ${posterImageMarkup(movie, "dialog-poster")}
    <div class="dialog-body">
      <span class="section-kicker">MOVIELENS MOVIE #${movie.movie_id}</span>
      <h2 id="dialog-title">${escapeHTML(movie.title)}</h2>
      <div class="dialog-meta">
        <span>${movie.year ?? "Year unknown"}</span>
        <span>${ratingMarkup(movie)}</span>
        <span>${escapeHTML(movie.genres.join(" · ") || "No genres listed")}</span>
      </div>
      <p>Movie details and ratings come directly from the local MovieLens Latest Small dataset.</p>
      ${movie.imdb_id ? `<p>IMDb ID: ${escapeHTML(movie.imdb_id)}</p>` : ""}
      <div class="dialog-actions">
        <button class="button button-primary" type="button" data-action="watch" data-id="${movie.movie_id}">${watchlist.includes(movie.movie_id) ? "♥ In Watchlist" : "♡ Add to Watchlist"}</button>
        <button class="button button-ghost" type="button" data-action="recommend" data-id="${movie.movie_id}">Find Similar Movies <span aria-hidden="true">→</span></button>
      </div>
    </div>
  </div>`;
}

async function findSimilar(id) {
  const section = document.querySelector("#recommendations");
  const note = document.querySelector("#recommendation-note");
  const reference = document.querySelector("#recommendation-reference");
  const grid = document.querySelector("#recommendation-grid");
  const selected = movieById(id);
  if (!selected) return;

  section.classList.remove("hidden");
  reference.textContent = `Inspired by ${selected.title}${selected.year ? ` (${selected.year})` : ""} · MovieLens #${id}`;
  note.textContent = "Calculating content similarity from the local MovieLens genre and tag features.";
  grid.innerHTML = loadingMarkup("Finding movies with similar content...");
  section.scrollIntoView({ behavior: "smooth", block: "start" });

  await new Promise(resolve => window.requestAnimationFrame(resolve));
  const recommendations = findSimilarMovies(selected, 5);
  if (!recommendations.length) {
    note.textContent = "No other movies share enough genre or tag features to recommend.";
    grid.innerHTML = "";
    return;
  }
  note.textContent = "Ranked by cosine similarity; explanations show shared genres and available user tags.";
  renderCards(grid, recommendations, { recommendation: true });
  recommendations.forEach((movie, index) => {
    const explanation = document.createElement("p");
    explanation.className = "recommendation-explanation";
    explanation.textContent = movie.explanation;
    grid.children[index].querySelector(".movie-info")
      .insertBefore(explanation, grid.children[index].querySelector(".card-actions"));
  });
}

function renderWatchlist() {
  document.querySelector("#watchlist-count").textContent = watchlist.length;
  document.querySelector("#watchlist-heading-count").textContent = watchlist.length;
  document.querySelector("#watchlist-empty").classList.toggle("hidden", watchlist.length > 0);
  renderCards(watchlistGrid, watchlist.map(movieById).filter(Boolean));
}

let watchlistSyncQueue = Promise.resolve();

function cloudSyncEnabled() {
  return Boolean(API_BASE_URL) && window.location.protocol !== "file:";
}

function updateCloudSyncStatus(message, state = "") {
  const status = document.querySelector("#cloud-sync-status");
  status.textContent = message;
  status.classList.toggle("connected", state === "connected");
  status.classList.toggle("sync-error", state === "error");
}

function syncWatchlistToCloud() {
  if (!cloudSyncEnabled()) return;
  const clientId = getCloudClientId();
  if (!clientId) {
    updateCloudSyncStatus("Local only — browser storage unavailable", "error");
    return;
  }
  const savedIds = [...watchlist];
  watchlistSyncQueue = watchlistSyncQueue
    .catch(() => {})
    .then(async () => {
      updateCloudSyncStatus("Syncing watchlist…");
      const endpoint = `${API_BASE_URL}/watchlist/${clientId}`;
      const response = await fetch(endpoint, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ movie_ids: savedIds })
      });
      if (!response.ok) {
        const result = await response.json().catch(() => null);
        throw new Error(result?.error?.message || `Cloud sync failed (${response.status}).`);
      }
      updateCloudSyncStatus("Synced to MongoDB", "connected");
    })
    .catch(error => {
      updateCloudSyncStatus("Local watchlist — cloud unavailable", "error");
      console.warn("Could not sync watchlist to the cloud; local storage remains active.", error);
    });
}

async function restoreCloudWatchlist() {
  if (!cloudSyncEnabled()) {
    updateCloudSyncStatus("Local watchlist");
    return;
  }
  const clientId = getCloudClientId();
  if (!clientId) {
    updateCloudSyncStatus("Local only — browser storage unavailable", "error");
    return;
  }
  updateCloudSyncStatus("Checking MongoDB…");
  try {
    const response = await fetch(`${API_BASE_URL}/watchlist/${clientId}`, {
      headers: { Accept: "application/json" }
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(result?.error?.message || `Cloud sync failed (${response.status}).`);
    }
    const cloudIds = Array.isArray(result.movie_ids)
      ? result.movie_ids.filter(id => Number.isInteger(id) && movieById(id))
      : [];
    watchlist = [...new Set([...cloudIds, ...watchlist])];
    try {
      localStorage.setItem(WATCHLIST_KEY, JSON.stringify(watchlist));
    } catch (error) {
      console.error("Could not update the local watchlist cache.", error);
    }
    renderWatchlist();
    syncWatchlistToCloud();
  } catch (error) {
    updateCloudSyncStatus("Local watchlist — cloud unavailable", "error");
    console.warn("Could not restore watchlist from MongoDB; local storage remains active.", error);
  }
}

const ratingModel = globalThis.CineMatchModel?.createModel();

function renderPersonalizedRecommendations() {
  const select = document.querySelector("#profile-select");
  const userId = Number(select.value);
  const grid = document.querySelector("#ml-recommendation-grid");
  const emptyState = document.querySelector("#ml-empty");
  const reference = document.querySelector("#ml-reference");
  if (!ratingModel || !ratingModel.hasRated(userId)) return;
  const user = dataset.profile_users.find(profile => profile.user_id === userId);
  const recommendations = ratingModel.recommend(userId, movies, 5);
  reference.textContent =
    `MovieLens demo user #${userId} · ${user.rating_count.toLocaleString()} real ratings used as profile context`;
  if (!recommendations.length) {
    grid.innerHTML = "";
    emptyState.classList.remove("hidden");
    return;
  }
  emptyState.classList.add("hidden");
  renderCards(grid, recommendations);
  recommendations.forEach((movie, index) => {
    const explanation = document.createElement("p");
    explanation.className = "recommendation-explanation";
    explanation.textContent =
      "Predicted from learned user and movie rating patterns; this is not an observed rating.";
    grid.children[index].querySelector(".movie-info")
      .insertBefore(explanation, grid.children[index].querySelector(".card-actions"));
  });
}

async function trainRatingModel() {
  const status = document.querySelector("#model-status");
  const progress = document.querySelector("#model-progress");
  const profileSelect = document.querySelector("#profile-select");
  const generateButton = document.querySelector("#generate-recommendations");
  if (!ratingModel || !globalThis.CINEMATCH_RATINGS) {
    status.textContent = "Rating data unavailable";
    progress.textContent =
      "The local ratings-data.js or model.js file is missing. Keep all frontend files together and reload.";
    return;
  }
  try {
    const metrics = await ratingModel.train(
      globalThis.CINEMATCH_RATINGS.encoded,
      globalThis.CINEMATCH_RATINGS.count,
      movies.length,
      update => {
        status.textContent = update.message;
        progress.innerHTML = `${escapeHTML(update.message)} <progress max="100" value="${update.progress}">${update.progress}%</progress>`;
      }
    );
    document.querySelector("#stat-rmse").textContent =
      metrics.validation_rmse.toFixed(3);
    document.querySelector("#stat-rmse").title =
      `Holdout MAE: ${metrics.validation_mae.toFixed(3)} · Global-mean baseline RMSE: ${metrics.baseline_rmse.toFixed(3)}`;
    status.textContent = "Trained model ready";
    status.classList.add("ready");
    progress.textContent =
      `${metrics.algorithm} · ${metrics.training_ratings.toLocaleString()} training ratings · ` +
      `${metrics.validation_ratings.toLocaleString()} held-out ratings · ` +
      `RMSE ${metrics.validation_rmse.toFixed(3)} · MAE ${metrics.validation_mae.toFixed(3)} · ` +
      `global-mean baseline RMSE ${metrics.baseline_rmse.toFixed(3)}.`;
    profileSelect.innerHTML = dataset.profile_users
      .filter(profile => ratingModel.hasRated(profile.user_id))
      .map(profile =>
        `<option value="${profile.user_id}">MovieLens user #${profile.user_id} · ${profile.rating_count.toLocaleString()} ratings</option>`
      ).join("");
    profileSelect.disabled = profileSelect.options.length === 0;
    generateButton.disabled = profileSelect.disabled;
    if (profileSelect.options.length) renderPersonalizedRecommendations();
  } catch (error) {
    status.textContent = "Model training failed";
    progress.textContent = error.message;
    console.error("Could not train the MovieLens rating model.", error);
  }
}

function toggleWatchlist(id) {
  const movie = movieById(id);
  if (!movie) return;
  const adding = !watchlist.includes(id);
  watchlist = adding ? [...watchlist, id] : watchlist.filter(item => item !== id);
  saveWatchlist();
  renderWatchlist();
  loadMovies();
  showToast(adding ? `${movie.title} added to your watchlist.` : `${movie.title} removed from your watchlist.`);
  if (dialog.open) showDetails(movie);
}

function resetFilters() {
  document.querySelector("#movie-search").value = "";
  genreFilter.value = "";
  document.querySelector("#sort-filter").value = "popular";
  document.querySelectorAll(".genre-pill").forEach(pill => pill.classList.remove("active"));
  currentPage = 1;
  loadMovies();
}

document.addEventListener("click", event => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const action = button.dataset.action;
  const id = Number(button.dataset.id);
  if (action === "details") showDetails(movieById(id));
  if (action === "watch") toggleWatchlist(id);
  if (action === "recommend") {
    dialog.close();
    findSimilar(id);
  }
  if (action === "genre") {
    genreFilter.value = genreFilter.value === button.dataset.genre ? "" : button.dataset.genre;
    document.querySelectorAll(".genre-pill").forEach(pill =>
      pill.classList.toggle("active", pill.dataset.genre === genreFilter.value)
    );
    currentPage = 1;
    loadMovies();
    document.querySelector("#explore").scrollIntoView({ behavior: "smooth" });
  }
});

genreFilter.addEventListener("change", () => {
  document.querySelectorAll(".genre-pill").forEach(pill =>
    pill.classList.toggle("active", pill.dataset.genre === genreFilter.value)
  );
  currentPage = 1;
  loadMovies();
});
document.querySelector("#sort-filter").addEventListener("change", () => {
  currentPage = 1;
  loadMovies();
});
document.querySelector("#movie-search").addEventListener("input", () => {
  window.clearTimeout(browseTimer);
  currentPage = 1;
  browseTimer = window.setTimeout(loadMovies, 150);
});
document.querySelector("#reset-filters").addEventListener("click", resetFilters);
document.querySelector("#empty-reset").addEventListener("click", resetFilters);
document.querySelector("#previous-page").addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage -= 1;
    loadMovies();
  }
});
document.querySelector("#next-page").addEventListener("click", () => {
  if (currentPage < totalPages) {
    currentPage += 1;
    loadMovies();
  }
});
document.querySelector("#hero-search-form").addEventListener("submit", event => {
  event.preventDefault();
  document.querySelector("#movie-search").value = document.querySelector("#hero-search").value;
  genreFilter.value = "";
  currentPage = 1;
  loadMovies();
  document.querySelector("#explore").scrollIntoView({ behavior: "smooth" });
});
document.querySelector("#featured-button").addEventListener("click", () => {
  const movie = movieById(document.querySelector("#featured-button").dataset.id);
  if (movie) showDetails(movie);
  else document.querySelector("#explore").scrollIntoView({ behavior: "smooth" });
});
document.querySelector("#close-recommendations").addEventListener("click", () => {
  document.querySelector("#recommendations").classList.add("hidden");
});
document.querySelector("#generate-recommendations").addEventListener(
  "click",
  renderPersonalizedRecommendations
);
document.querySelector("#profile-select").addEventListener(
  "change",
  renderPersonalizedRecommendations
);
document.querySelector("#retry-button").addEventListener("click", () => window.location.reload());
document.querySelector("#dialog-close").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", event => {
  if (event.target === dialog) dialog.close();
});
document.querySelector("#menu-toggle").addEventListener("click", event => {
  const menu = document.querySelector("#nav-links");
  const open = menu.classList.toggle("open");
  event.currentTarget.setAttribute("aria-expanded", String(open));
  event.currentTarget.setAttribute("aria-label", open ? "Close navigation menu" : "Open navigation menu");
});
document.querySelectorAll("#nav-links a").forEach(link => link.addEventListener("click", () => {
  document.querySelector("#nav-links").classList.remove("open");
  document.querySelector("#menu-toggle").setAttribute("aria-expanded", "false");
}));

function initialize() {
  if (!dataset || !Array.isArray(dataset.movies) || !dataset.movies.length) {
    document.querySelector("#api-banner-message").textContent =
      "The local MovieLens data file is missing. Keep movies-data.js beside index.html and reload.";
    document.querySelector("#api-banner").hidden = false;
    movieGrid.innerHTML = "";
    return;
  }

  document.querySelector("#api-banner").hidden = true;
  movieGrid.innerHTML = loadingMarkup("Preparing local movie catalogue...");
  document.querySelector("#hero-dataset-caption").textContent =
    `LOADING ${dataset.dataset.movie_count.toLocaleString()} LOCAL MOVIES...`;
  document.querySelector("#genre-pills").innerHTML = dataset.genres.map(genre =>
    `<button class="genre-pill" type="button" data-action="genre" data-genre="${escapeHTML(genre)}">${escapeHTML(genre)}</button>`
  ).join("");
  genreFilter.insertAdjacentHTML(
    "beforeend",
    dataset.genres.map(genre => `<option value="${escapeHTML(genre)}">${escapeHTML(genre)}</option>`).join("")
  );
  buildFeatureIndex();
  renderStats();
  renderWatchlist();
  loadMovies();
  restoreCloudWatchlist();
  trainRatingModel();
}

initialize();

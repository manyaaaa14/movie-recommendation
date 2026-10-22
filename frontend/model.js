// Explicit-feedback matrix factorization trained with stochastic gradient descent.
(function attachMovieLensModel(global) {
  const FACTORS = 16;
  const EPOCHS = 12;
  const LEARNING_RATE = 0.012;
  const REGULARIZATION = 0.04;
  const HOLDOUT_FRACTION = 0.15;
  const ROW_BYTES = 5;

  function randomGenerator(seed = 2026) {
    let state = seed >>> 0;
    return () => {
      state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
      return state / 4294967296;
    };
  }

  function decodeRatings(encoded, count) {
    const binary = atob(encoded);
    if (binary.length !== count * ROW_BYTES) {
      throw new Error("The bundled MovieLens rating data is incomplete or invalid.");
    }
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    const view = new DataView(bytes.buffer);
    const users = new Uint16Array(count);
    const movies = new Uint16Array(count);
    const ratings = new Float32Array(count);
    for (let row = 0; row < count; row += 1) {
      const offset = row * ROW_BYTES;
      users[row] = view.getUint16(offset, true);
      movies[row] = view.getUint16(offset + 2, true);
      ratings[row] = view.getUint8(offset + 4) / 2;
    }
    return { users, movies, ratings };
  }

  function createModel() {
    let factorsByUser;
    let factorsByMovie;
    let userBias;
    let movieBias;
    let globalMean = 0;
    let seenByUser;
    let ratedByUser;
    let ready = false;

    function predict(userId, movieIndex) {
      const userFactors = factorsByUser[userId];
      const movieFactors = factorsByMovie[movieIndex];
      let estimate = globalMean + userBias[userId] + movieBias[movieIndex];
      for (let factor = 0; factor < FACTORS; factor += 1) {
        estimate += userFactors[factor] * movieFactors[factor];
      }
      return Math.max(0.5, Math.min(5, estimate));
    }

    async function train(encodedRatings, ratingsCount, movieCount, onProgress = () => {}) {
      ready = false;
      featureMessage(onProgress, "Decoding the MovieLens rating data...", 0);
      const { users, movies, ratings } = decodeRatings(encodedRatings, ratingsCount);
      let maxUserId = 0;
      for (const userId of users) maxUserId = Math.max(maxUserId, userId);

      const indices = new Uint32Array(ratingsCount);
      for (let index = 0; index < ratingsCount; index += 1) indices[index] = index;
      const random = randomGenerator();
      for (let index = ratingsCount - 1; index > 0; index -= 1) {
        const swapIndex = Math.floor(random() * (index + 1));
        [indices[index], indices[swapIndex]] = [indices[swapIndex], indices[index]];
      }
      const holdoutCount = Math.floor(ratingsCount * HOLDOUT_FRACTION);
      const trainingCount = ratingsCount - holdoutCount;
      const trainingIndices = indices.subarray(0, trainingCount);
      const validationIndices = indices.subarray(trainingCount);

      let ratingTotal = 0;
      for (const index of trainingIndices) ratingTotal += ratings[index];
      globalMean = ratingTotal / trainingCount;

      factorsByUser = Array.from(
        { length: maxUserId + 1 },
        () => new Float32Array(FACTORS)
      );
      factorsByMovie = Array.from(
        { length: movieCount },
        () => new Float32Array(FACTORS)
      );
      userBias = new Float32Array(maxUserId + 1);
      movieBias = new Float32Array(movieCount);
      seenByUser = Array.from({ length: maxUserId + 1 }, () => new Set());
      ratedByUser = Array.from({ length: maxUserId + 1 }, () => new Set());

      for (let index = 0; index < ratingsCount; index += 1) {
        ratedByUser[users[index]].add(movies[index]);
      }
      for (const index of trainingIndices) {
        seenByUser[users[index]].add(movies[index]);
      }

      for (const vectors of [factorsByUser, factorsByMovie]) {
        for (const vector of vectors) {
          for (let factor = 0; factor < FACTORS; factor += 1) {
            vector[factor] = (random() - 0.5) * 0.1;
          }
        }
      }

      let squaredError = 0;
      for (const index of validationIndices) {
        const error = ratings[index] - globalMean;
        squaredError += error * error;
      }
      const baselineRmse = Math.sqrt(squaredError / holdoutCount);

      for (let epoch = 0; epoch < EPOCHS; epoch += 1) {
        for (let position = trainingIndices.length - 1; position > 0; position -= 1) {
          const swapIndex = Math.floor(random() * (position + 1));
          [trainingIndices[position], trainingIndices[swapIndex]] =
            [trainingIndices[swapIndex], trainingIndices[position]];
        }
        for (const index of trainingIndices) {
          const userId = users[index];
          const movieIndex = movies[index];
          const userFactors = factorsByUser[userId];
          const movieFactors = factorsByMovie[movieIndex];
          let estimate = globalMean + userBias[userId] + movieBias[movieIndex];
          for (let factor = 0; factor < FACTORS; factor += 1) {
            estimate += userFactors[factor] * movieFactors[factor];
          }
          const error = ratings[index] - estimate;
          userBias[userId] += LEARNING_RATE * (error - REGULARIZATION * userBias[userId]);
          movieBias[movieIndex] += LEARNING_RATE * (error - REGULARIZATION * movieBias[movieIndex]);
          for (let factor = 0; factor < FACTORS; factor += 1) {
            const oldUserFactor = userFactors[factor];
            const oldMovieFactor = movieFactors[factor];
            userFactors[factor] += LEARNING_RATE * (
              error * oldMovieFactor - REGULARIZATION * oldUserFactor
            );
            movieFactors[factor] += LEARNING_RATE * (
              error * oldUserFactor - REGULARIZATION * oldMovieFactor
            );
          }
        }
        featureMessage(
          onProgress,
          `Training rating model — epoch ${epoch + 1} of ${EPOCHS}`,
          Math.round(((epoch + 1) / EPOCHS) * 100)
        );
        await new Promise(resolve => global.setTimeout(resolve, 0));
      }

      let validationSquaredError = 0;
      let validationAbsoluteError = 0;
      let evaluableCount = 0;
      for (const index of validationIndices) {
        const userId = users[index];
        const movieIndex = movies[index];
        if (!seenByUser[userId].has(movieIndex)) {
          const prediction = Math.max(
            0.5,
            Math.min(5, globalMean + userBias[userId] + movieBias[movieIndex])
          );
          const error = ratings[index] - prediction;
          validationSquaredError += error * error;
          validationAbsoluteError += Math.abs(error);
          evaluableCount += 1;
          continue;
        }
        const error = ratings[index] - predict(userId, movieIndex);
        validationSquaredError += error * error;
        validationAbsoluteError += Math.abs(error);
        evaluableCount += 1;
      }

      ready = true;
      featureMessage(onProgress, "Trained and evaluated on held-out MovieLens ratings.", 100);
      return {
        algorithm: "User–movie latent factor matrix factorization trained with SGD",
        factors: FACTORS,
        epochs: EPOCHS,
        training_ratings: trainingCount,
        validation_ratings: evaluableCount,
        validation_rmse: Math.sqrt(validationSquaredError / evaluableCount),
        validation_mae: validationAbsoluteError / evaluableCount,
        baseline_rmse: baselineRmse,
        users: maxUserId
      };
    }

    function recommend(userId, catalogue, limit = 5) {
      if (!ready) throw new Error("The rating model is still training.");
      if (!Number.isInteger(userId) || userId < 1 || userId >= factorsByUser.length) {
        throw new Error("Choose a valid MovieLens demo user.");
      }
      const userRatings = seenByUser[userId];
      const scored = [];
      for (let movieIndex = 0; movieIndex < catalogue.length; movieIndex += 1) {
        if (ratedByUser[userId].has(movieIndex) || userRatings.size === 0) continue;
        scored.push({
          ...catalogue[movieIndex],
          predicted_rating: predict(userId, movieIndex)
        });
      }
      return scored
        .sort((first, second) =>
          second.predicted_rating - first.predicted_rating ||
          second.rating_count - first.rating_count ||
          first.movie_id - second.movie_id
        )
        .slice(0, limit);
    }

    function hasRated(userId) {
      return ready && Number.isInteger(userId) && seenByUser[userId]?.size > 0;
    }

    return { train, recommend, hasRated };
  }

  function featureMessage(callback, message, progress) {
    callback({ message, progress });
  }

  global.CineMatchModel = { createModel };
})(globalThis);

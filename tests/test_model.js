const assert = require("node:assert/strict");
const path = require("node:path");

require(path.join(__dirname, "..", "frontend", "model.js"));

function encodeRatings(rows) {
  const data = Buffer.alloc(rows.length * 5);
  rows.forEach(([user, movie, halfStars], index) => {
    data.writeUInt16LE(user, index * 5);
    data.writeUInt16LE(movie, index * 5 + 2);
    data.writeUInt8(halfStars, index * 5 + 4);
  });
  return data.toString("base64");
}

async function main() {
  const model = globalThis.CineMatchModel.createModel();
  const ratings = [
    [1, 0, 10], [1, 1, 9], [1, 2, 8],
    [2, 0, 9], [2, 1, 10], [2, 3, 8],
    [3, 0, 2], [3, 2, 3], [3, 3, 4],
    [4, 1, 2], [4, 2, 4], [4, 3, 5]
  ];
  const catalogue = Array.from({ length: 4 }, (_, index) => ({
    movie_id: index + 1,
    title: `Movie ${index + 1}`,
    rating_count: 10
  }));
  const metrics = await model.train(encodeRatings(ratings), ratings.length, catalogue.length);
  assert.equal(metrics.training_ratings, 11);
  assert.equal(metrics.validation_ratings, 1);
  assert.ok(Number.isFinite(metrics.validation_rmse));
  assert.ok(Number.isFinite(metrics.validation_mae));
  assert.equal(metrics.factors, 16);
  assert.equal(model.hasRated(1), true);
  const recommendations = model.recommend(1, catalogue);
  assert.equal(recommendations.length, 1);
  assert.equal(recommendations[0].movie_id, 4);
  assert.ok(recommendations[0].predicted_rating >= 0.5);
  assert.ok(recommendations[0].predicted_rating <= 5);
  assert.throws(() => model.recommend(99, catalogue), /valid MovieLens demo user/);
  console.log(
    `Matrix-factorization test passed (RMSE ${metrics.validation_rmse.toFixed(3)}).`
  );
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

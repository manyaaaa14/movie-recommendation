const fs = require("node:fs");
const path = require("node:path");

const rootDir = path.join(__dirname, "..");
const frontendDir = path.join(rootDir, "frontend");
const distDir = path.join(rootDir, "dist");

console.log("Building CineMatch frontend for deployment...");

// Ensure dist directory exists and is clean
if (fs.existsSync(distDir)) {
  fs.rmSync(distDir, { recursive: true, force: true });
}
fs.mkdirSync(distDir, { recursive: true });

// Copy all static frontend files
const filesToCopy = [
  "index.html",
  "style.css",
  "script.js",
  "model.js",
  "movies-data.js",
  "ratings-data.js",
];

for (const file of filesToCopy) {
  const sourcePath = path.join(frontendDir, file);
  const destPath = path.join(distDir, file);
  if (fs.existsSync(sourcePath)) {
    fs.copyFileSync(sourcePath, destPath);
    console.log(`✓ Copied ${file}`);
  } else {
    console.warn(`! File not found: ${file}`);
  }
}

// Generate production config.js
const defaultApiUrl = "https://movie-recommendation-dzws.onrender.com/api";
const configuredUrl = (process.env.CINEMATCH_API_BASE_URL || defaultApiUrl).trim();
const apiBaseUrl = configuredUrl.replace(/\/+$/, "");

const configContent =
  "// Auto-generated production configuration for CineMatch frontend\n" +
  `window.CINEMATCH_CONFIG = ${JSON.stringify({ apiBaseUrl }, null, 2)};\n`;

fs.writeFileSync(path.join(distDir, "config.js"), configContent, "utf8");
console.log(`✓ Generated config.js with API URL: ${apiBaseUrl}`);

// Generate _headers file for Netlify caching and security
const headersContent = `
/movies-data.js
  Cache-Control: public, max-age=3600
/ratings-data.js
  Cache-Control: public, max-age=3600
/*.js
  X-Content-Type-Options: nosniff
`.trim() + "\n";

fs.writeFileSync(path.join(distDir, "_headers"), headersContent, "utf8");
console.log("✓ Generated Netlify _headers");

console.log("\nSuccess! Frontend dist directory ready at: " + distDir);

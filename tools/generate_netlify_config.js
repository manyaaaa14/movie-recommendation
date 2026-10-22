const fs = require("node:fs");
const path = require("node:path");

const configuredUrl = (process.env.CINEMATCH_API_BASE_URL || "/api").trim();
let apiBaseUrl = configuredUrl.replace(/\/+$/, "");

if (apiBaseUrl !== "/api") {
  let parsed;
  try {
    parsed = new URL(apiBaseUrl);
  } catch {
    throw new Error("CINEMATCH_API_BASE_URL must be an absolute HTTPS URL or /api.");
  }
  if (parsed.protocol !== "https:" && parsed.hostname !== "localhost" && parsed.hostname !== "127.0.0.1") {
    throw new Error("CINEMATCH_API_BASE_URL must use HTTPS outside local development.");
  }
  apiBaseUrl = `${parsed.origin}${parsed.pathname}`.replace(/\/+$/, "");
}

const configPath = path.join(__dirname, "..", "frontend", "config.js");
const configSource =
  "// Generated from the Netlify CINEMATCH_API_BASE_URL environment variable.\n" +
  `window.CINEMATCH_CONFIG = ${JSON.stringify({ apiBaseUrl })};\n`;

fs.writeFileSync(configPath, configSource, "utf8");
console.log(`Configured CineMatch frontend API: ${apiBaseUrl || "(disabled)"}`);

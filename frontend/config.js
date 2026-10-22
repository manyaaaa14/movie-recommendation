const isLocalDevServer =
  typeof window !== "undefined" &&
  (window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1");
const isFlaskPort = typeof window !== "undefined" && window.location.port === "5000";

window.CINEMATCH_CONFIG = {
  apiBaseUrl:
    isLocalDevServer && !isFlaskPort
      ? "http://127.0.0.1:5000/api"
      : "/api"
};

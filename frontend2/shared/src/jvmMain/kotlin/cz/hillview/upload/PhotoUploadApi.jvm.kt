package cz.hillview.upload

// Dev mapping: the backend hands out the Caddy origin
// (https://hillview.dev4.local/worker) whose local CA the JVM doesn't trust;
// the worker container is directly reachable over plain http. Override with
// HILLVIEW_WORKER, or the known dev origin falls back to localhost:8056.
// Proper fix is a backend-URL setting (settings/sources phase).
actual fun mapWorkerUrl(url: String): String {
    System.getenv("HILLVIEW_WORKER")?.let { return it }
    if (url.startsWith("https://hillview.dev4.local/worker")) {
        return "http://localhost:8056"
    }
    return url
}

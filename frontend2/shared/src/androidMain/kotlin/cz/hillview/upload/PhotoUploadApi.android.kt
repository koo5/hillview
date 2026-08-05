package cz.hillview.upload

// Dev mappings, mirroring the jvm actual: the emulator reaches the host at
// 10.0.2.2, and the Caddy dev origin's local CA isn't trusted in the app.
// Proper fix is a backend-URL setting (settings/sources phase).
actual fun mapWorkerUrl(url: String): String {
    if (url.startsWith("https://hillview.dev4.local/worker")) {
        return "http://10.0.2.2:8056"
    }
    return url
        .replace("://localhost", "://10.0.2.2")
        .replace("://127.0.0.1", "://10.0.2.2")
}

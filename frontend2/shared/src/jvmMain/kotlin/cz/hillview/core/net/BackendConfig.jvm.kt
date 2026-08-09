package cz.hillview.core.net

// HILLVIEW_BACKEND, when set, must be the full API URL (…/api).
actual fun defaultBackendConfig(): BackendConfig =
    BackendConfig(apiUrl = System.getenv("HILLVIEW_BACKEND") ?: "http://localhost:8055/api")

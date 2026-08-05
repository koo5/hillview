package cz.hillview.core.net

// 10.0.2.2 = host loopback from the Android emulator, matching the old app's
// dev convention. On a physical device this must become a user setting
// (settings/sources) — planned, not yet built.
actual fun defaultBackendConfig(): BackendConfig =
    BackendConfig(apiUrl = "http://10.0.2.2:8055/api")

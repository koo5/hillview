package cz.hillview.core.net

import io.ktor.client.HttpClient
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

/**
 * [apiUrl] is always the FULL API URL (…/api) — project convention: the app
 * never assembles it by stripping/appending path segments on a host URL.
 */
data class BackendConfig(val apiUrl: String)

/**
 * Platform default: emulator loopback on Android, localhost on desktop.
 * Becomes a user setting (settings/sources) in a later phase.
 */
expect fun defaultBackendConfig(): BackendConfig

val backendJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
}

/**
 * expectSuccess stays false — API services classify status codes themselves
 * (transient vs definitive failures drive the session state machine).
 */
fun createHttpClient(engine: HttpClientEngine? = null): HttpClient {
    val config: io.ktor.client.HttpClientConfig<*>.() -> Unit = {
        expectSuccess = false
        install(ContentNegotiation) {
            json(backendJson)
        }
    }
    return if (engine != null) HttpClient(engine, config) else HttpClient(config)
}

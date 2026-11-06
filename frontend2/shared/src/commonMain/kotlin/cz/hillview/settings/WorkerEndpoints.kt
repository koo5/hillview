package cz.hillview.settings

import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/*
 * Worker URLs the user can upload to INSTEAD of the one the server names
 * (user, 2026-11-05: "like we have the settings field to override api server
 * url, i want to also be able to override worker url. The catch is that it
 * may need to be a self-signed or http url").
 *
 * A divergence from the Tauri app, which has no such setting: there the worker
 * is always whatever authorize-upload returns. Unlike the API URL this needs
 * no restart — the upload stack reads the override per photo
 * (shared-kt WorkerOverride.kt).
 *
 * A self-signed worker is trusted by PINNING the certificate it presents, not
 * by switching verification off: see WorkerOverride.kt for why.
 */

/** A pinned certificate, as the dialog shows it and the upload stack trusts it. */
@Serializable
data class CertificatePin(
    /** Base64 DER — what the upload stack builds its trust anchor from. */
    val derBase64: String,
    /** SHA-256, "AB:CD:…", for the user to compare against the server's. */
    val fingerprint: String,
    val subject: String,
    /** When the pinned certificate expires, as text; re-pin after it. */
    val notAfter: String,
)

@Serializable
data class WorkerEndpoint(
    /** The worker's base URL — what `/ready` and `/upload_async` hang off. */
    val url: String,
    /** Null: the platform's own CAs decide, as for any https site. */
    val pin: CertificatePin? = null,
)

val WorkerEndpoint.isHttps: Boolean get() = url.startsWith("https://", ignoreCase = true)

/**
 * The typed text as a worker URL, or null when it is not one: http or https,
 * a host, no trailing slash (a stored slash doubles up in "$url/ready").
 */
fun normalizeWorkerUrl(text: String): String? {
    val url = text.trim().trimEnd('/')
    val scheme = listOf("https://", "http://").firstOrNull { url.startsWith(it, ignoreCase = true) }
        ?: return null
    val rest = url.substring(scheme.length)
    if (rest.isEmpty() || rest.startsWith("/") || rest.any { it.isWhitespace() }) return null
    return url
}

/** The endpoint uploads go to, or null for "as the server says". */
val UploadSettings.activeWorker: WorkerEndpoint?
    get() = workerOverrideUrl?.let { url -> workerEndpoints.firstOrNull { it.url == url } }

/** Adds [url] (once) and selects it — adding one is almost always to use it. */
fun UploadSettings.withWorkerAdded(url: String): UploadSettings = copy(
    workerEndpoints = if (workerEndpoints.any { it.url == url }) workerEndpoints
    else workerEndpoints + WorkerEndpoint(url),
    workerOverrideUrl = url,
)

/** Removing the selected one falls back to the server's worker. */
fun UploadSettings.withWorkerRemoved(url: String): UploadSettings = copy(
    workerEndpoints = workerEndpoints.filterNot { it.url == url },
    workerOverrideUrl = workerOverrideUrl?.takeIf { it != url },
)

/** Null selects the server's worker. */
fun UploadSettings.withWorkerSelected(url: String?): UploadSettings = copy(
    workerOverrideUrl = url?.takeIf { u -> workerEndpoints.any { it.url == u } },
)

fun UploadSettings.withWorkerPin(url: String, pin: CertificatePin?): UploadSettings = copy(
    workerEndpoints = workerEndpoints.map { if (it.url == url) it.copy(pin = pin) else it },
)

private val endpointListSerializer = ListSerializer(WorkerEndpoint.serializer())
private val endpointJson = Json { ignoreUnknownKeys = true }

fun encodeWorkerEndpoints(list: List<WorkerEndpoint>): String =
    endpointJson.encodeToString(endpointListSerializer, list)

/** A stored list that no longer parses is dropped, not a crash at startup. */
fun decodeWorkerEndpoints(json: String?): List<WorkerEndpoint> =
    json?.let { runCatching { endpointJson.decodeFromString(endpointListSerializer, it) }.getOrNull() }
        ?: emptyList()

/**
 * The certificate [url] presents, for the user to pin. Never completes a
 * connection to it (shared-kt fetchPresentedCertificate). Throws with the
 * reason when there is nothing to pin.
 */
expect suspend fun fetchWorkerCertificate(url: String): CertificatePin

/** The upload's own preflight against [endpoint], as one line for the dialog. */
expect suspend fun testWorker(endpoint: WorkerEndpoint): String

/** The last contact with any worker, as one line, or null if there was none. */
expect fun lastWorkerContact(): String?

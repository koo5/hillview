package cz.hillview.plugin

import android.content.SharedPreferences
import android.util.Base64
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.ByteArrayInputStream
import java.security.KeyStore
import java.security.MessageDigest
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

/*
 * A worker to upload to INSTEAD of the one authorize-upload names (frontend2,
 * 2026-11-05: "like we have the settings field to override api server url, i
 * want to also be able to override worker url ... it may need to be a
 * self-signed or http url").
 *
 * frontend2's settings write the two keys below into hillview_upload_prefs;
 * the Tauri app never writes them, so there the override is always absent and
 * nothing changes. Read per upload, so a change applies to the next photo with
 * no restart: the worker URL is per-request already (it arrives in every
 * authorize response), and the JWT the worker checks is the same either way.
 *
 * A self-signed worker is trusted by PINNING, never by switching verification
 * off: the user fetches the certificate the worker presents, sees its
 * fingerprint, and that one certificate becomes the only trust anchor for
 * requests to that worker. Proper chain validation still runs against it, so a
 * different server on the same address is refused. Not "trust all": that
 * would hand the upload JWT and the photos to anyone on the path, and Google
 * Play rejects apps whose TrustManager accepts everything — this source ships
 * in the Tauri app too.
 */

const val PREF_WORKER_URL_OVERRIDE = "worker_url_override"

/** Base64 DER of the pinned trust anchor; absent = the platform's own CAs. */
const val PREF_WORKER_PINNED_CERT = "worker_pinned_cert"

data class WorkerOverride(val url: String, val pinnedCertDer: ByteArray?) {
    // By content: the client cache in PhotoUploadLogic keys on this.
    override fun equals(other: Any?): Boolean =
        other is WorkerOverride && other.url == url &&
            java.util.Arrays.equals(other.pinnedCertDer, pinnedCertDer)

    override fun hashCode(): Int = url.hashCode() * 31 + (pinnedCertDer?.contentHashCode() ?: 0)
}

fun readWorkerOverride(prefs: SharedPreferences): WorkerOverride? {
    val url = prefs.getString(PREF_WORKER_URL_OVERRIDE, null)?.trim()?.trimEnd('/')
        ?.takeIf { it.isNotEmpty() } ?: return null
    val pin = prefs.getString(PREF_WORKER_PINNED_CERT, null)
        ?.takeIf { it.isNotEmpty() }
        // android.util, not java.util: minSdk is 24, java.util.Base64 is 26+.
        ?.let { Base64.decode(it, Base64.NO_WRAP) }
    return WorkerOverride(url, pin)
}

fun parseCertificate(der: ByteArray): X509Certificate =
    CertificateFactory.getInstance("X.509")
        .generateCertificate(ByteArrayInputStream(der)) as X509Certificate

/** "AB:CD:…" — SHA-256 over the DER, the form browsers show. */
fun certificateFingerprint(der: ByteArray): String =
    MessageDigest.getInstance("SHA-256").digest(der)
        .joinToString(":") { "%02X".format(it.toInt() and 0xff) }

/**
 * [base] trusting ONLY [anchorDer]: a TrustManagerFactory over a key store
 * holding that one certificate, so the platform's own chain validation runs
 * with it as the root (Android's documented "unknown CA" recipe).
 *
 * The hostname check is the platform's, plus one case: a server presenting
 * exactly the pinned certificate as its leaf. A home-made self-signed
 * certificate often names no host (or not the IP it is reached by), and
 * matching it byte for byte already says it is the server the user pinned.
 */
fun pinnedClient(base: OkHttpClient, anchorDer: ByteArray): OkHttpClient {
    val anchor = parseCertificate(anchorDer)
    val store = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
        load(null, null)
        setCertificateEntry("pinned-worker", anchor)
    }
    val tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
    tmf.init(store)
    val trust = tmf.trustManagers.filterIsInstance<X509TrustManager>().first()
    val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(trust), null) }
    // OkHttp's own verifier (the one every other request here uses) — not
    // HttpsURLConnection's default, which on a desktop JVM refuses everything.
    val platformHosts: HostnameVerifier = base.hostnameVerifier
    return base.newBuilder()
        .sslSocketFactory(ssl.socketFactory, trust)
        .hostnameVerifier { host, session ->
            platformHosts.verify(host, session) ||
                (session.peerCertificates.firstOrNull()?.encoded?.contentEquals(anchorDer) == true)
        }
        .build()
}

/**
 * What a worker presents, for the user to pin: the TOPMOST certificate of the
 * chain it sends. For a home-made self-signed certificate that is the
 * certificate itself; for a local CA (Caddy's `tls internal`) it is the
 * intermediate, which outlives the short-lived leaf — pinning the leaf would
 * break within the day.
 *
 * The probe NEVER completes a connection: its trust manager records the chain
 * and then refuses it, so nothing is sent to a server nobody has vetted yet.
 */
fun fetchPresentedCertificate(base: OkHttpClient, url: String): X509Certificate {
    var seen: Array<X509Certificate>? = null
    val recorder = object : X509TrustManager {
        override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) =
            throw CertificateException("client certificates are not checked here")

        override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
            seen = chain
            throw CertificateException("certificate recorded for pinning; connection refused")
        }

        override fun getAcceptedIssuers(): Array<X509Certificate> = emptyArray()
    }
    val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(recorder), null) }
    val probe = base.newBuilder()
        .sslSocketFactory(ssl.socketFactory, recorder)
        .build()
    try {
        probe.newCall(Request.Builder().url(url.trimEnd('/') + "/ready").get().build())
            .execute().close()
    } catch (e: java.io.IOException) {
        // Expected: the recorder refuses every chain. Only "no chain" is a failure.
        seen?.let { return it.last() }
        throw e
    }
    throw IllegalStateException("$url did not present a certificate (is it https?)")
}

// ---- status: what the upload-status page and the settings dialog show ----
// (user, 2026-11-05: "we'll need some status/logging to debug this in the UI")

const val PREF_LAST_WORKER_AT = "last_worker_at"
const val PREF_LAST_WORKER_URL = "last_worker_url"
const val PREF_LAST_WORKER_RESULT = "last_worker_result"
const val PREF_LAST_WORKER_FAILED = "last_worker_failed"

/**
 * The last contact with each worker URL, as a JSON object keyed by URL
 * (2026-11-09). One slot for every worker made the screens contradict
 * themselves: an SSL failure against one URL sat beside "HTTP 200" from
 * another, and nothing said which line was about which (user: "we've created
 * a total mess"). Written by the uploads AND by the Test button, so a URL's
 * line is always its newest news, whoever made it.
 */
const val PREF_WORKER_CONTACTS = "worker_contacts"

/** The worker authorize-upload last named — "as the server says", made concrete. */
const val PREF_SERVER_WORKER_URL = "server_worker_url"

//data class WorkerContact(val url: String, val atMs: Long, val outcome: String, val failed: Boolean)
/**
 * [busy]: the worker answered 503, queue full — backpressure, not an error
 * (user, 2026-11-09: "the screens still show 503 as an error"). Never both
 * busy and failed.
 */
data class WorkerContact(
    val url: String, val atMs: Long, val outcome: String, val failed: Boolean, val busy: Boolean = false,
)

// The drain and a Test can record at once; read-modify-write the map under one lock.
private val workerContactsLock = Any()

/** The last contact with a worker, whichever it was and however it went. */
//fun recordWorkerContact(prefs: SharedPreferences, url: String, outcome: String, failed: Boolean) {
fun recordWorkerContact(
    prefs: SharedPreferences, url: String, outcome: String, failed: Boolean, busy: Boolean = false,
) {
    val now = System.currentTimeMillis()
    synchronized(workerContactsLock) {
        val all = runCatching { org.json.JSONObject(prefs.getString(PREF_WORKER_CONTACTS, null) ?: "{}") }
            .getOrElse { org.json.JSONObject() }
        // Keyed without a trailing slash, the form the settings store URLs in.
        all.put(url.trimEnd('/'), org.json.JSONObject().put("at", now).put("outcome", outcome).put("failed", failed).put("busy", busy))
        prefs.edit()
            .putLong(PREF_LAST_WORKER_AT, now)
            .putString(PREF_LAST_WORKER_URL, url)
            .putString(PREF_LAST_WORKER_RESULT, outcome)
            .putBoolean(PREF_LAST_WORKER_FAILED, failed)
            .putString(PREF_WORKER_CONTACTS, all.toString())
            .apply()
    }
}

/** Every worker URL's last contact (see [PREF_WORKER_CONTACTS]). */
fun readWorkerContacts(prefs: SharedPreferences): Map<String, WorkerContact> {
    val all = runCatching { org.json.JSONObject(prefs.getString(PREF_WORKER_CONTACTS, null) ?: "{}") }
        .getOrNull() ?: return emptyMap()
    return all.keys().asSequence().mapNotNull { url ->
        val c = all.optJSONObject(url) ?: return@mapNotNull null
        url to WorkerContact(url, c.optLong("at"), c.optString("outcome", ""), c.optBoolean("failed"), c.optBoolean("busy"))
    }.toMap()
}

/** Remember the worker the server named, so "as the server says" can show which one that is. */
fun recordServerWorkerUrl(prefs: SharedPreferences, url: String) {
    if (prefs.getString(PREF_SERVER_WORKER_URL, null) != url) {
        prefs.edit().putString(PREF_SERVER_WORKER_URL, url).apply()
    }
}

/**
 * An exception as a diagnosis: its class and message, then each cause's.
 * The TLS failures are only legible that way — an SSLHandshakeException says
 * little, while the CertPathValidatorException inside it says "Trust anchor
 * for certification path not found", which is the actual news (the pin
 * changed, or the worker never had one).
 */
fun describeFailure(e: Throwable): String {
    val parts = mutableListOf<String>()
    var t: Throwable? = e
    while (t != null && parts.size < 4) {
        val line = "${t::class.java.simpleName}: ${t.message ?: ""}".trimEnd(' ', ':')
        if (parts.none { it == line }) parts += line
        t = t.cause?.takeIf { it !== t }
    }
    return parts.joinToString(" ← ")
}

/**
 * The upload's own preflight, run by hand: GET `<url>/ready` through the same
 * client an upload would use (the pinned one when there is a pin). One line,
 * for the settings dialog's Test button.
 */
fun checkWorker(base: OkHttpClient, url: String, pinnedCertDer: ByteArray?): String =
    checkWorkerResult(base, url, pinnedCertDer).line

/**
 * A Test's answer: the line, and whether it counts as a failure (anything but
 * 200, 404 from an older worker, or 503 — which is [busy], the worker full).
 */
data class WorkerCheck(val line: String, val failed: Boolean, val busy: Boolean = false)

fun checkWorkerResult(base: OkHttpClient, url: String, pinnedCertDer: ByteArray?): WorkerCheck {
    val http = if (pinnedCertDer != null) pinnedClient(base, pinnedCertDer) else base
    val started = System.currentTimeMillis()
    return try {
        http.newCall(Request.Builder().url(url.trimEnd('/') + "/ready").get().build()).execute().use { r ->
            val ms = System.currentTimeMillis() - started
            WorkerCheck(
                when (r.code) {
                    200 -> "Ready — HTTP 200 in ${ms} ms"
                    404 -> "Reachable, but no /ready (an older worker?) — HTTP 404 in ${ms} ms"
                    503 -> "Reachable, queue full — HTTP 503 in ${ms} ms"
                    else -> "Answered HTTP ${r.code} in ${ms} ms"
                },
                //failed = r.code != 200 && r.code != 404,
                failed = r.code != 200 && r.code != 404 && r.code != 503,
                busy = r.code == 503,
            )
        }
    } catch (e: Exception) {
        WorkerCheck("Failed after ${System.currentTimeMillis() - started} ms — ${describeFailure(e)}", failed = true)
    }
}

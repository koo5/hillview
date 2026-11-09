package cz.hillview.settings

import android.content.Context
import android.util.Base64
import cz.hillview.plugin.PREF_LAST_WORKER_AT
import cz.hillview.plugin.PREF_LAST_WORKER_FAILED
import cz.hillview.plugin.PREF_LAST_WORKER_RESULT
import cz.hillview.plugin.PREF_LAST_WORKER_URL
import cz.hillview.plugin.certificateFingerprint
import cz.hillview.plugin.checkWorker
import cz.hillview.plugin.fetchPresentedCertificate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import org.koin.core.context.GlobalContext
import java.util.concurrent.TimeUnit

// Short timeouts: these answer a person waiting on a dialog, not a drain.
private val probeClient: OkHttpClient by lazy {
    OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .build()
}

actual suspend fun fetchWorkerCertificate(url: String): CertificatePin = withContext(Dispatchers.IO) {
    val cert = fetchPresentedCertificate(probeClient, url)
    val der = cert.encoded
    CertificatePin(
        derBase64 = Base64.encodeToString(der, Base64.NO_WRAP),
        fingerprint = certificateFingerprint(der),
        subject = cert.subjectX500Principal.name,
        notAfter = cert.notAfter.toString(),
    )
}

actual suspend fun testWorker(endpoint: WorkerEndpoint): String = withContext(Dispatchers.IO) {
    checkWorker(probeClient, endpoint.url, endpoint.pin?.let { Base64.decode(it.derBase64, Base64.NO_WRAP) })
}

actual fun lastWorkerContact(): String? {
    val context: Context = GlobalContext.get().get()
    val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
    val at = prefs.getLong(PREF_LAST_WORKER_AT, 0L).takeIf { it > 0 } ?: return null
    val ago = (System.currentTimeMillis() - at) / 1000
    val failed = prefs.getBoolean(PREF_LAST_WORKER_FAILED, false)
    return "${if (failed) "✗" else "✓"} ${ago}s ago · ${prefs.getString(PREF_LAST_WORKER_URL, "?")} · " +
        (prefs.getString(PREF_LAST_WORKER_RESULT, "?") ?: "?")
}

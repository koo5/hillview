package cz.hillview.settings

// Desktop has no upload stack (see UploadDiagnostics.jvm.kt), so there is no
// worker to pin or test; the dialog still renders, and says so.

actual suspend fun fetchWorkerCertificate(url: String): CertificatePin =
    throw UnsupportedOperationException("Not on this platform — uploads are the Android app's.")

actual suspend fun testWorker(endpoint: WorkerEndpoint): String = "Not on this platform."

actual fun lastWorkerContact(): String? = null

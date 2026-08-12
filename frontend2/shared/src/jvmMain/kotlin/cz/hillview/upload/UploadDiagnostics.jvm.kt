package cz.hillview.upload

/**
 * Desktop has no WorkManager and no background uploader to explain — the
 * jvm target's upload path is the direct PhotoUploadApi used by the
 * backend-contract tests.
 */
actual suspend fun collectUploadDiagnostics(): UploadDiagnostics = UploadDiagnostics(
    rows = listOf(
        DiagRow(
            "Uploader",
            "not on this platform",
            DiagVerdict.Info,
            note = "Background uploads are the Android app's WorkManager stack.",
        ),
    ),
    takenAtMs = System.currentTimeMillis(),
)

actual suspend fun triggerUploadNow(): String = "Not on this platform."

actual suspend fun pingBackend(): String = "Not on this platform."

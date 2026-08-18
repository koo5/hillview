package cz.hillview.upload

/**
 * Why the uploader is (or is not) doing anything right now.
 *
 * Deliberately a flat list of observations rather than a reasoning engine:
 * everything here is a value something already knows — a preference, a queue
 * count, a WorkManager WorkInfo, a ConnectivityManager capability — read and
 * labelled. Nothing infers, so nothing can be subtly wrong about a state it
 * has not been taught.
 *
 * The design rule if this grows: only add a row you can READ. The moment a
 * row needs deducing from three other rows, show the three instead.
 */
data class UploadDiagnostics(
    val rows: List<DiagRow>,
    val takenAtMs: Long,
) {
    /**
     * The first blocking row, which is the answer to "why is nothing
     * happening" — or null when nothing is in the way.
     */
    val blocker: DiagRow? get() = rows.firstOrNull { it.verdict == DiagVerdict.Blocking }
}

enum class DiagVerdict {
    /** A condition uploads need, and it holds. */
    Ok,

    /** A condition uploads need, and it does not hold. */
    Blocking,

    /** Context, neither good nor bad. */
    Info,
}

data class DiagRow(
    val label: String,
    val value: String,
    val verdict: DiagVerdict = DiagVerdict.Info,
    /** Why this matters, when the label alone would not say. */
    val note: String? = null,
)

/** Read the current picture. Cheap, but touches disk and WorkManager. */
expect suspend fun collectUploadDiagnostics(): UploadDiagnostics

/**
 * Force a drain now, bypassing the Wi-Fi-only constraint — the Tauri app's
 * manual-upload button, which triggers `retry_button` for exactly that
 * reason. Returns a line to show the user.
 *
 * Still refuses when auto-upload is off, because the shared drain does
 * (startAutomaticUpload returns early), and saying so beats a button that
 * silently does nothing.
 */
expect suspend fun triggerUploadNow(): String

/**
 * Can this phone reach the configured server at all, and how fast? The one
 * question a queue that never moves cannot answer about itself — and the
 * one most likely to be about the phone's network rather than the app.
 */
expect suspend fun pingBackend(): String

/**
 * Tell the upload scheduler that something changed which could alter what the
 * schedule should be — see shared-kt's UploadScheduler.kt. Callers never decide
 * whether anything is enqueued; they only report that the world moved.
 *
 * Exists here because the events that matter (a session starting) live in
 * common code while the scheduler is Android-only.
 */
expect fun reconcileUploadSchedule(reason: String)

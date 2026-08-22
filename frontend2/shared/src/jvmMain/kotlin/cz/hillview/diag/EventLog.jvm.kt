package cz.hillview.diag

/** The event log lives in shared-kt, which is Android-only. */
actual suspend fun collectEventLog(): List<LoggedEvent> = emptyList()

actual fun clearEventLog() {}

actual fun formatLogTime(epochMs: Long): String =
    java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US)
        .format(java.util.Date(epochMs))

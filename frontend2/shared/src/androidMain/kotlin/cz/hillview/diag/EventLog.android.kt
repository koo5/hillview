package cz.hillview.diag

import cz.hillview.plugin.EventLog
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

actual suspend fun collectEventLog(): List<LoggedEvent> = withContext(Dispatchers.Default) {
    EventLog.snapshot().map { LoggedEvent(it.atMs, it.category, it.message) }
}

actual fun clearEventLog() = EventLog.clear()

actual fun formatLogTime(epochMs: Long): String =
    java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US)
        .format(java.util.Date(epochMs))

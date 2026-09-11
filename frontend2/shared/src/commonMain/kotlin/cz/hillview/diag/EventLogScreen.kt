package cz.hillview.diag

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

/**
 * The app's recent events, in the app.
 *
 * This exists because every interesting thing the app does was already
 * logged — to logcat, which is precisely where it cannot be read: on a
 * phone, in a field, when the question is "did an upload even get triggered
 * in the last hour". Same stream, somewhere it can be read and copied.
 *
 * Deliberately over-shares. Pruning is easy once it is clear which lines
 * earn their place; a missing line is the expensive kind of error.
 */
@Composable
fun EventLogScreen(onBack: () -> Unit) {
    var events by remember { mutableStateOf<List<LoggedEvent>>(emptyList()) }
    var category by remember { mutableStateOf<String?>(null) }
    var crash by remember { mutableStateOf(lastCrashReport()) }
    val clipboard = LocalClipboardManager.current

    LaunchedEffect(Unit) {
        while (true) {
            events = collectEventLog()
            delay(1_000)
        }
    }

    val shown = remember(events, category) {
        category?.let { c -> events.filter { it.category == c } } ?: events
    }

    Column(
        Modifier.fillMaxSize().padding(12.dp).testTag("event-log-screen"),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(
                onClick = onBack,
                modifier = Modifier.testTag("event-log-back"),
            ) { Text("← Back") }
            Text("Event log", style = MaterialTheme.typography.titleLarge)
        }

        Row(
            Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            // FIXED order, not alphabetical-as-discovered: sorting means a
            // newly-seen category inserts in the middle and shifts every
            // chip after it, under a thumb that was aiming at one of them.
            // Known categories hold their slots; anything new appends.
            val categories = remember(events) {
                val seen = events.map { it.category }.distinct()
                KNOWN_EVENT_CATEGORIES.filter { it in seen } +
                    seen.filterNot { it in KNOWN_EVENT_CATEGORIES }.sorted()
            }
            TextButton(onClick = { category = null }) {
                Text(
                    "all ${events.size}",
                    color = if (category == null) {
                        MaterialTheme.colorScheme.primary
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
            categories.forEach { c ->
                val n = events.count { it.category == c }
                TextButton(
                    onClick = { category = c },
                    modifier = Modifier.testTag("event-filter-$c"),
                ) {
                    Text(
                        "$c $n",
                        color = if (category == c) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                    )
                }
            }
        }

        // The previous run's crash, if there was one — see CrashLog. The
        // whole reason it exists is to be copied out and pasted into a
        // report, so that is the one action offered.
        crash?.let { report ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    "Previous run crashed: " +
                        (report.lineSequence().firstOrNull { it.contains("Exception") || it.contains("Error") }
                            ?.take(80) ?: "trace available"),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.weight(1f).testTag("event-log-crash"),
                )
                TextButton(
                    onClick = { clipboard.setText(AnnotatedString(report)) },
                    modifier = Modifier.testTag("event-log-copy-crash"),
                ) { Text("Copy crash") }
                TextButton(onClick = { clearCrashReport(); crash = null }) { Text("✕") }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            // The point of an in-field log is getting it OUT of the field.
            TextButton(
                onClick = {
                    clipboard.setText(
                        AnnotatedString(
                            shown.joinToString("\n") {
                                "${formatLogTime(it.atMs)} [${it.category}] ${it.message}"
                            },
                        ),
                    )
                },
                modifier = Modifier.testTag("event-log-copy"),
            ) { Text("Copy ${shown.size}") }
            TextButton(
                onClick = { clearEventLog(); events = emptyList() },
                modifier = Modifier.testTag("event-log-clear"),
            ) { Text("Clear") }
        }

        // Newest first: a log you are chasing is read from the top.
        //
        // No SelectionContainer around this list any more. It wrapped a
        // LazyColumn whose rows come and go by the second, get emptied by
        // Clear and rebuilt on every return to the screen — the exact churn
        // the selection registrar is known to fall over on — and the only
        // thing it added was per-row text selection, which the Copy button
        // already covers whole. Removed after a field crash on exactly that
        // clear/back/return sequence; NOT verified as the cause (the trace
        // did not survive — which is what CrashLog above is for).
        LazyColumn(
            Modifier.fillMaxSize().testTag("event-log-list"),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            items(shown) { event ->
                Text(
                    "${formatLogTime(event.atMs)} [${event.category}] ${event.message}",
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

/**
 * The categories this app writes, in the order the chips show them —
 * roughly the order a photo's life happens in. Fixed so the chips do not
 * reshuffle as new kinds of event appear during a session.
 */
private val KNOWN_EVENT_CATEGORIES = listOf("capture", "video", "refine", "upload", "geo")

/** One line of the app's own history. */
data class LoggedEvent(val atMs: Long, val category: String, val message: String)

expect suspend fun collectEventLog(): List<LoggedEvent>

expect fun clearEventLog()

/** The previous run's crash report (see CrashLog), or null. */
expect fun lastCrashReport(): String?
expect fun clearCrashReport()

/** Wall-clock to the second — the resolution a human correlates by. */
expect fun formatLogTime(epochMs: Long): String

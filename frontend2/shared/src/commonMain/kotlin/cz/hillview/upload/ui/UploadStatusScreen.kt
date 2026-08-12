package cz.hillview.upload.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import cz.hillview.upload.DiagRow
import cz.hillview.upload.DiagVerdict
import cz.hillview.upload.UploadDiagnostics
import cz.hillview.upload.collectUploadDiagnostics
import kotlinx.coroutines.delay

/**
 * What the uploader is doing, and why it is not doing anything else.
 *
 * Every line is a value read from somewhere that already knew it — a
 * preference, a queue count, a WorkManager WorkInfo, a network capability.
 * The page explains by SHOWING the inputs rather than by concluding, which
 * is why it needed no new machinery: the one thing nothing recorded was
 * "when did a drain last run and how did it end", and that is now three
 * strings in prefs.
 */
@Composable
fun UploadStatusScreen(onBack: () -> Unit) {
    var diagnostics by remember { mutableStateOf<UploadDiagnostics?>(null) }
    var refreshes by remember { mutableStateOf(0) }

    LaunchedEffect(refreshes) {
        // Re-read on a slow tick as well as on demand: the interesting
        // states (waiting for a constraint, a scheduled run coming due) are
        // ones you sit and watch.
        while (true) {
            diagnostics = collectUploadDiagnostics()
            delay(2_000)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .testTag("upload-status-screen"),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(
                onClick = onBack,
                modifier = Modifier.testTag("upload-status-back"),
            ) { Text("← Back") }
            Text("Uploads", style = MaterialTheme.typography.titleLarge)
        }

        val diag = diagnostics
        if (diag == null) {
            Text("reading…", style = MaterialTheme.typography.bodyMedium)
            return@Column
        }

        // The headline: the first thing standing in the way, or that nothing
        // is. This is a lookup over the rows below, not a separate opinion.
        val blocker = diag.blocker
        Text(
            text = blocker?.let { "Not uploading — ${it.label.lowercase()}: ${it.value}" }
                ?: "Nothing is blocking uploads.",
            style = MaterialTheme.typography.bodyLarge,
            color = if (blocker != null) {
                MaterialTheme.colorScheme.error
            } else {
                MaterialTheme.colorScheme.primary
            },
            modifier = Modifier.testTag("upload-status-headline"),
        )

        diag.rows.forEach { row -> DiagRowView(row) }

        TextButton(
            onClick = { refreshes++ },
            modifier = Modifier.testTag("upload-status-refresh"),
        ) { Text("Refresh now") }
    }
}

@Composable
private fun DiagRowView(row: DiagRow) {
    Column(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = when (row.verdict) {
                    DiagVerdict.Ok -> "✓ "
                    DiagVerdict.Blocking -> "✗ "
                    DiagVerdict.Info -> "· "
                },
                color = when (row.verdict) {
                    DiagVerdict.Ok -> Color(0xFF2EA043)
                    DiagVerdict.Blocking -> MaterialTheme.colorScheme.error
                    DiagVerdict.Info -> MaterialTheme.colorScheme.outline
                },
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                text = row.label,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(end = 8.dp),
            )
            Text(
                text = row.value,
                style = MaterialTheme.typography.bodyMedium,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.testTag("upload-status-${row.label.lowercase()}"),
            )
        }
        row.note?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.outline,
                modifier = Modifier.padding(start = 18.dp),
            )
        }
    }
}

package cz.hillview.upload.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import cz.hillview.settings.CertificatePin
import cz.hillview.settings.UploadSettings
import cz.hillview.settings.WorkerEndpoint
import cz.hillview.settings.WorkerStatus
import cz.hillview.settings.describe
import cz.hillview.settings.isHttps
import cz.hillview.settings.normalizeWorkerUrl
import cz.hillview.settings.withWorkerAdded
import cz.hillview.settings.withWorkerPin
import cz.hillview.settings.withWorkerRemoved
import cz.hillview.settings.withWorkerSelected
import kotlinx.coroutines.launch

/**
 * Where uploads go, and how each worker last answered — on the Uploads screen
 * (2026-11-09; until then a dialog under Settings → Servers, with its status
 * split between the two screens).
 *
 * One line per worker URL, [statuses]: the newest contact with that URL,
 * whether an upload made it or Test did (shared-kt WorkerOverride.kt). There
 * is no second "test result" line and no shared "last contact" slot: those
 * were how one screen came to say "HTTP 200" and "SSLException" at once, about
 * different workers, with nothing saying which was which (user, 2026-11-09:
 * "we've created a total mess").
 *
 * The panel does not poll: the screen reads [statuses], [serverWorkerUrl] and
 * [nowMs] on its one refresh tick and hands them in, so every age on the page
 * comes from the same reading. A Test or a pin calls [onContact] when it is
 * done, for an immediate re-read.
 *
 * Pinning a certificate is an action (fetch what the worker presents, trust
 * that), so it is a button, not a switch (user, 2026-11-09).
 *
 * [fetchCertificate] and [test] are the platform's (defaults); the platform
 * records their outcomes into [statuses]. Tests pass fakes.
 */
@Composable
fun WorkerPanel(
    settings: UploadSettings,
    update: ((UploadSettings) -> UploadSettings) -> Unit,
    statuses: Map<String, WorkerStatus>,
    serverWorkerUrl: String?,
    nowMs: Long,
    onContact: () -> Unit,
    modifier: Modifier = Modifier,
    fetchCertificate: suspend (String) -> CertificatePin = { cz.hillview.settings.fetchWorkerCertificate(it) },
    test: suspend (WorkerEndpoint) -> Unit = { cz.hillview.settings.testWorker(it) },
) {
    val scope = rememberCoroutineScope()
    // What is in progress, per URL ("Testing…") — shown instead of the status
    // line until it is done and the status line has the outcome.
    val busy = remember { mutableStateMapOf<String, String>() }
    var newUrl by remember { mutableStateOf("") }
    val normalized = normalizeWorkerUrl(newUrl)

    fun runTest(endpoint: WorkerEndpoint) {
        busy[endpoint.url] = "Testing…"
        scope.launch {
            try {
                test(endpoint)
            } finally {
                busy.remove(endpoint.url)
                onContact()
            }
        }
    }

    fun pin(endpoint: WorkerEndpoint) {
        busy[endpoint.url] = "Fetching its certificate…"
        scope.launch {
            try {
                val pin = fetchCertificate(endpoint.url)
                update { it.withWorkerPin(endpoint.url, pin) }
                //results.remove(endpoint.url)
                // Test through the new pin at once: the pin is only useful if
                // the worker now answers, and that is the question the user
                // pressed the button to settle.
                busy[endpoint.url] = "Pinned — testing…"
                test(endpoint.copy(pin = pin))
            } catch (e: Exception) {
                // The platform has recorded why as this URL's status.
            } finally {
                busy.remove(endpoint.url)
                onContact()
            }
        }
    }

    Column(
        modifier = modifier.fillMaxWidth().testTag("worker-panel"),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text("Worker", style = MaterialTheme.typography.titleMedium)
        Text(
            "Uploads go to the worker the server names for each photo, or to one " +
                "picked here — from the next photo, no restart.",
            style = MaterialTheme.typography.bodySmall,
        )

        OptionRow(
            selected = settings.workerOverrideUrl == null,
            label = "As the server says",
            tag = "worker-option-server",
            onSelect = { update { it.withWorkerSelected(null) } },
        )
        Indented {
            Text(
                serverWorkerUrl ?: "Named with each upload — none yet on this install.",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("worker-server-url"),
            )
            if (serverWorkerUrl != null) {
                StatusLine(busy[serverWorkerUrl], statuses[serverWorkerUrl], nowMs, "worker-status-server")
                TextButton(
                    onClick = { runTest(WorkerEndpoint(serverWorkerUrl)) },
                    modifier = Modifier.testTag("worker-test-server"),
                ) { Text("Test") }
            }
        }

        settings.workerEndpoints.forEachIndexed { i, endpoint ->
            HorizontalDivider()
            OptionRow(
                selected = settings.workerOverrideUrl == endpoint.url,
                label = endpoint.url,
                tag = "worker-option-$i",
                onSelect = { update { it.withWorkerSelected(endpoint.url) } },
            )
            Indented {
                StatusLine(busy[endpoint.url], statuses[endpoint.url], nowMs, "worker-status-$i")
                if (endpoint.isHttps) {
                    val pin = endpoint.pin
                    if (pin != null) {
                        Text(
                            "Pinned certificate: ${pin.subject}\nSHA-256 ${pin.fingerprint}\nValid until ${pin.notAfter}",
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.testTag("worker-pin-$i"),
                        )
                    } else {
                        Text(
                            "Trusted through the system's certificate authorities. A self-signed " +
                                "worker needs its certificate pinned.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                } else {
                    Text(
                        "Plain http: the photos and the upload token travel unencrypted.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton(
                        onClick = { runTest(endpoint) },
                        enabled = busy[endpoint.url] == null,
                        modifier = Modifier.testTag("worker-test-$i"),
                    ) { Text("Test") }
                    if (endpoint.isHttps) {
                        TextButton(
                            onClick = { pin(endpoint) },
                            enabled = busy[endpoint.url] == null,
                            modifier = Modifier.testTag("worker-pin-action-$i"),
                        ) { Text(if (endpoint.pin == null) "Pin certificate" else "Re-pin") }
                        if (endpoint.pin != null) {
                            TextButton(
                                onClick = { update { it.withWorkerPin(endpoint.url, null) } },
                                modifier = Modifier.testTag("worker-unpin-$i"),
                            ) { Text("Unpin") }
                        }
                    }
                    TextButton(
                        onClick = { update { it.withWorkerRemoved(endpoint.url) } },
                        modifier = Modifier.testTag("worker-remove-$i"),
                    ) { Text("Remove") }
                }
            }
        }

        HorizontalDivider()
        OutlinedTextField(
            value = newUrl,
            onValueChange = { newUrl = it },
            label = { Text("Add a worker URL") },
            placeholder = { Text("https://host:8056") },
            singleLine = true,
            isError = newUrl.isNotBlank() && normalized == null,
            supportingText = if (newUrl.isNotBlank() && normalized == null) {
                { Text("http:// or https:// and a host") }
            } else null,
            modifier = Modifier.fillMaxWidth().testTag("worker-new-url"),
        )
        TextButton(
            onClick = {
                normalized?.let { url -> update { it.withWorkerAdded(url) } }
                newUrl = ""
            },
            enabled = normalized != null,
            modifier = Modifier.testTag("worker-add"),
        ) { Text("Add and use") }
    }
}

/** A URL's newest news, or what is in progress for it. */
@Composable
private fun StatusLine(busy: String?, status: WorkerStatus?, nowMs: Long, tag: String) {
    Text(
        text = busy ?: status?.describe(nowMs) ?: "No contact yet.",
        style = MaterialTheme.typography.bodySmall,
        color = if (busy == null && status?.failed == true) MaterialTheme.colorScheme.error
        else MaterialTheme.colorScheme.onSurface,
        modifier = Modifier.testTag(tag),
    )
}

@Composable
private fun Indented(content: @Composable () -> Unit) {
    Column(Modifier.padding(start = 40.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) { content() }
}

@Composable
private fun OptionRow(selected: Boolean, label: String, tag: String, onSelect: () -> Unit) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .selectable(selected = selected, onClick = onSelect, role = Role.RadioButton)
            .padding(vertical = 2.dp)
            .testTag(tag),
    ) {
        RadioButton(selected = selected, onClick = null)
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(start = 8.dp))
    }
}

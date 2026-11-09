package cz.hillview.settings.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
import cz.hillview.settings.isHttps
import cz.hillview.settings.normalizeWorkerUrl
import cz.hillview.settings.withWorkerAdded
import cz.hillview.settings.withWorkerPin
import cz.hillview.settings.withWorkerRemoved
import cz.hillview.settings.withWorkerSelected
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Settings → Worker URL: where uploads go instead of the worker the server
 * names (see cz.hillview.settings.WorkerEndpoints). Saved URLs, one selected
 * or none; an https one can trust its own certificate by pinning it; each one
 * can be tested with the upload's own preflight, and the last real contact is
 * shown underneath — the status this needs to be debuggable on a phone.
 *
 * [fetchCertificate], [test] and [lastContact] are the platform's (defaults);
 * tests pass fakes.
 */
@Composable
fun WorkerUrlDialog(
    settings: UploadSettings,
    update: ((UploadSettings) -> UploadSettings) -> Unit,
    onDismiss: () -> Unit,
    fetchCertificate: suspend (String) -> CertificatePin = { cz.hillview.settings.fetchWorkerCertificate(it) },
    test: suspend (WorkerEndpoint) -> String = { cz.hillview.settings.testWorker(it) },
    lastContact: () -> String? = { cz.hillview.settings.lastWorkerContact() },
) {
    val scope = rememberCoroutineScope()
    // Per-URL lines under each entry: a test result, or what pinning said.
    val results = remember { mutableStateMapOf<String, String>() }
    var contact by remember { mutableStateOf(lastContact()) }
    // Live while the dialog is open (user, 2026-11-06): the background drain keeps
    // contacting the worker, and a line read once at open went on showing a
    // refused connection after the pin that fixed it — until Test was pressed.
    // A prefs read a second is nothing, and it also keeps the "Ns ago" honest.
    LaunchedEffect(Unit) {
        while (true) {
            delay(CONTACT_REFRESH_MS)
            contact = lastContact()
        }
    }
    var newUrl by remember { mutableStateOf("") }
    val normalized = normalizeWorkerUrl(newUrl)

    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.testTag("worker-dialog"),
        title = { Text("Worker URL") },
        confirmButton = {
            TextButton(onClick = onDismiss, modifier = Modifier.testTag("worker-dialog-done")) { Text("Done") }
        },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    "Uploads go to the worker the server names for each photo. Pick " +
                        "one here to send them elsewhere — from the next photo, no restart.",
                    style = MaterialTheme.typography.bodySmall,
                )
                OptionRow(
                    selected = settings.workerOverrideUrl == null,
                    label = "As the server says",
                    tag = "worker-option-server",
                    onSelect = { update { it.withWorkerSelected(null) } },
                )
                settings.workerEndpoints.forEachIndexed { i, endpoint ->
                    HorizontalDivider()
                    OptionRow(
                        selected = settings.workerOverrideUrl == endpoint.url,
                        label = endpoint.url,
                        tag = "worker-option-$i",
                        onSelect = { update { it.withWorkerSelected(endpoint.url) } },
                    )
                    if (endpoint.isHttps) {
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                            Text(
                                "Trust its own certificate (self-signed)",
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.weight(1f),
                            )
                            Switch(
                                checked = endpoint.pin != null,
                                onCheckedChange = { on ->
                                    if (!on) {
                                        update { it.withWorkerPin(endpoint.url, null) }
                                        results.remove(endpoint.url)
                                    } else {
                                        results[endpoint.url] = "Fetching its certificate…"
                                        scope.launch {
                                            try {
                                                val pin = fetchCertificate(endpoint.url)
                                                update { it.withWorkerPin(endpoint.url, pin) }
                                                //results.remove(endpoint.url)
                                                // Test through the new pin at once: the
                                                // pin is only useful if the worker now
                                                // answers, and that is the question the
                                                // user turned it on to settle.
                                                results[endpoint.url] = "Pinned — testing…"
                                                results[endpoint.url] = test(endpoint.copy(pin = pin))
                                                contact = lastContact()
                                            } catch (e: Exception) {
                                                results[endpoint.url] = "Could not fetch a certificate — " +
                                                    (e.message ?: e::class.simpleName)
                                            }
                                        }
                                    }
                                },
                                modifier = Modifier.testTag("worker-self-signed-$i"),
                            )
                        }
                        endpoint.pin?.let { pin ->
                            Text(
                                "Pinned: ${pin.subject}\nSHA-256 ${pin.fingerprint}\nValid until ${pin.notAfter}",
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.testTag("worker-pin-$i"),
                            )
                        }
                    } else {
                        Text(
                            "Plain http: the photos and the upload token travel unencrypted.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(
                            onClick = {
                                results[endpoint.url] = "Testing…"
                                scope.launch {
                                    results[endpoint.url] = test(endpoint)
                                    contact = lastContact()
                                }
                            },
                            modifier = Modifier.testTag("worker-test-$i"),
                        ) { Text("Test") }
                        TextButton(
                            onClick = {
                                update { it.withWorkerRemoved(endpoint.url) }
                                results.remove(endpoint.url)
                            },
                            modifier = Modifier.testTag("worker-remove-$i"),
                        ) { Text("Remove") }
                    }
                    results[endpoint.url]?.let { line ->
                        Text(line, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("worker-result-$i"))
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
                Text(
                    "Last worker contact: " + (contact ?: "none yet"),
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.testTag("worker-last-contact"),
                )
            }
        },
    )
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

/** How often the last-contact line re-reads what the upload recorded. */
private const val CONTACT_REFRESH_MS = 1_000L

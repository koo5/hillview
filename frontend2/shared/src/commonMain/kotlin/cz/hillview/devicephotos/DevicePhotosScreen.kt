package cz.hillview.devicephotos

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.auth.SessionManager
import cz.hillview.auth.SessionState
import cz.hillview.settings.ALLOWED_LICENSES
import cz.hillview.settings.UploadSettingsRepository
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

private const val PAGE_SIZE = 50

/**
 * The /device-photos route, ported — see the contract section in
 * docs/tauri-capture-ui-contract.md. Every capture and its upload fate,
 * newest first, straight from the shared Room DB the upload stack works.
 */
@Composable
fun DevicePhotosScreen(
    onBack: () -> Unit,
    browser: DevicePhotoBrowser = koinInject(),
    uploadSettingsRepo: UploadSettingsRepository = koinInject(),
    sessionManager: SessionManager = koinInject(),
) {
    val uploadSettings by uploadSettingsRepo.settings.collectAsState()
    val sessionState by sessionManager.state.collectAsState()
    val scope = rememberCoroutineScope()

    var filter by remember { mutableStateOf(PhotoFilter.All) }
    var filterCounts by remember { mutableStateOf<Map<PhotoFilter, Int>>(emptyMap()) }
    var cards by remember { mutableStateOf<List<DevicePhotoCard>>(emptyList()) }
    var counts by remember { mutableStateOf(StatusCounts(0, 0, 0)) }
    var totalCount by remember { mutableStateOf(0) }
    var hasMore by remember { mutableStateOf(false) }
    var page by remember { mutableStateOf(1) }
    var loading by remember { mutableStateOf(true) }
    var loadingMore by remember { mutableStateOf(false) }

    suspend fun load(target: Int, append: Boolean) {
        val result = browser.page(target, PAGE_SIZE, filter)
        filterCounts = browser.counts()
        cards = if (append) cards + result.photos else result.photos
        counts = result.counts
        totalCount = result.totalCount
        hasMore = result.hasMore
        page = target
        loading = false
        loadingMore = false
    }

    LaunchedEffect(Unit) { load(1, append = false) }

    Column(
        Modifier
            .fillMaxSize()
            .safeContentPadding()
            .testTag("device-photos-section"),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp),
        ) {
            TextButton(onClick = onBack) { Text("< Back") }
            Text(
                "Device Photos",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.weight(1f),
            )
            TextButton(
                onClick = {
                    loading = true
                    scope.launch { load(1, append = false) }
                },
                modifier = Modifier.testTag("refresh-button"),
            ) { Text(if (loading) "Loading…" else "Refresh") }
        }

        // The DevicePhotoStats line: what the upload stack has and hasn't done.
        Text(
            "$totalCount photos · ${counts.pending} pending · " +
                "${counts.done} uploaded · ${counts.failed} failed",
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(horizontal = 16.dp).testTag("device-photo-stats"),
        )

        // The filter IS the navigation. At ten thousand rows nobody scrolls
        // to find anything — the questions are "what is stuck", "what
        // failed", "what can I delete", and each is a subset with a count.
        // Page numbers would answer a question ("take me to row 4,000") that
        // nobody asks, and the answer would move under them as uploads land.
        Row(
            Modifier
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            PhotoFilter.entries.forEach { option ->
                val n = filterCounts[option]
                TextButton(
                    onClick = {
                        if (option != filter) {
                            filter = option
                            loading = true
                            scope.launch { load(1, append = false) }
                        }
                    },
                    modifier = Modifier.testTag("filter-${option.name.lowercase()}"),
                ) {
                    Text(
                        text = if (n != null) "${option.label} $n" else option.label,
                        color = if (option == filter) {
                            MaterialTheme.colorScheme.primary
                        } else {
                            MaterialTheme.colorScheme.onSurfaceVariant
                        },
                    )
                }
            }
        }

        when {
            loading && cards.isEmpty() -> Box(
                Modifier.fillMaxSize().testTag("loading-container"),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }

            cards.isEmpty() -> Column(
                Modifier.fillMaxSize().testTag("no-data"),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text("No Device Photos Found", style = MaterialTheme.typography.titleMedium)
                Text(
                    "No photos have been detected on this device yet.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }

            else -> LazyColumn(
                Modifier.fillMaxSize().testTag("photos-grid"),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(cards, key = { it.id }) { card ->
                    PhotoCard(
                        card = card,
                        retryOffered = uploadSettings.autoUploadEnabled &&
                            sessionState is SessionState.LoggedIn,
                        onRetry = { scope.launch { browser.retryUploads(); load(1, false) } },
                        onDelete = { alsoFile ->
                            scope.launch {
                                browser.delete(card.id, alsoFile)
                                load(1, append = false)
                            }
                        },
                        globalLicense = uploadSettings.license,
                        onChangeLicense = { license ->
                            scope.launch {
                                browser.changeLicense(card.id, license)
                                // Patch the one row rather than reloading:
                                // a reload snaps a long list back to page 1,
                                // which is a rude answer to editing a photo
                                // you scrolled to.
                                cards = cards.map {
                                    if (it.id == card.id) it.copy(license = license) else it
                                }
                            }
                        },
                    )
                }
                if (hasMore) {
                    item {
                        TextButton(
                            onClick = {
                                loadingMore = true
                                scope.launch { load(page + 1, append = true) }
                            },
                            enabled = !loadingMore,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testTag("load-more-button"),
                        ) { Text(if (loadingMore) "Loading more…" else "Load More Photos") }
                    }
                }
            }
        }
    }
}

@Composable
private fun PhotoCard(
    card: DevicePhotoCard,
    retryOffered: Boolean,
    onRetry: () -> Unit,
    onDelete: (alsoFile: Boolean) -> Unit = {},
    /** What a row with no licence of its own would go out under. */
    globalLicense: String? = null,
    onChangeLicense: (String) -> Unit = {},
) {
    var confirmingDelete by remember { mutableStateOf(false) }
    var editingLicense by remember { mutableStateOf(false) }

    if (editingLicense) {
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { editingLicense = false },
            title = { Text("License for this photo") },
            text = {
                Column {
                    Text(
                        "Set when the photo was taken, and only changeable " +
                            "until it goes out — afterwards the server has " +
                            "its own copy.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    ALLOWED_LICENSES.forEach { option ->
                        TextButton(
                            onClick = { editingLicense = false; onChangeLicense(option) },
                            modifier = Modifier.testTag("license-option-$option"),
                        ) {
                            Text(
                                if (option == (card.license ?: globalLicense)) "● $option"
                                else "○ $option",
                            )
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { editingLicense = false }) { Text("Cancel") }
            },
        )
    }

    if (confirmingDelete) {
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { confirmingDelete = false },
            title = { Text("Delete ${card.filename}?") },
            text = {
                Text(
                    if (card.fileMissing) {
                        "The file is already gone, so only the database row is left " +
                            "to remove. It can never upload."
                    } else {
                        "\"Forget row\" removes it from this list and the upload " +
                            "queue but leaves the file on the device. \"Delete file " +
                            "too\" also removes the bytes. Neither touches anything " +
                            "already uploaded to the server."
                    },
                )
            },
            confirmButton = {
                TextButton(
                    onClick = { confirmingDelete = false; onDelete(false) },
                    modifier = Modifier.testTag("delete-row-only"),
                ) { Text("Forget row") }
            },
            dismissButton = {
                Row {
                    TextButton(
                        onClick = { confirmingDelete = false },
                    ) { Text("Cancel") }
                    if (!card.fileMissing) {
                        TextButton(
                            onClick = { confirmingDelete = false; onDelete(true) },
                            modifier = Modifier.testTag("delete-with-file"),
                        ) {
                            Text("Delete file too", color = MaterialTheme.colorScheme.error)
                        }
                    }
                }
            },
        )
    }
    Surface(
        tonalElevation = 2.dp,
        shape = RoundedCornerShape(8.dp),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp)
            .testTag("photo-card"),
    ) {
        Column(Modifier.padding(8.dp)) {
            Row {
                PhotoThumbnail(
                    locator = card.locator,
                    modifier = Modifier
                        .size(96.dp)
                        .background(
                            androidx.compose.ui.graphics.Color(0xFF222222),
                            RoundedCornerShape(6.dp),
                        )
                        .testTag("photo-thumbnail"),
                )
                Column(Modifier.padding(start = 10.dp).weight(1f)) {
                    Text(
                        uploadStatusLabel(card.uploadStatus),
                        color = uploadStatusColor(card.uploadStatus),
                        style = MaterialTheme.typography.labelLarge,
                        modifier = Modifier.testTag("photo-status"),
                    )
                    Text(card.filename, style = MaterialTheme.typography.bodyMedium)
                    Detail("Size", formatFileSize(card.sizeBytes))
                    Detail(
                        "Date",
                        "${formatLocalDate(card.capturedAtMs)} ${formatLocalTime(card.capturedAtMs)}",
                    )
                    if (card.latitude != 0.0 || card.longitude != 0.0) {
                        Detail(
                            "Location",
                            "${fmt6(card.latitude)}, ${fmt6(card.longitude)}",
                        )
                    }
                    card.bearingDeg?.let { Detail("Bearing", "${fmt1(it)}°") }
                    Detail("Dimensions", "${card.width} × ${card.height}")
                    if (card.retryCount > 0) Detail("Retries", card.retryCount.toString())
                    // The licence THIS photo carries. Rows from before it
                    // was per-photo say so rather than pretending: they go
                    // out under whatever the setting says at upload time.
                    Detail(
                        "License",
                        card.license ?: (globalLicense?.let { "$it (global)" } ?: "not set"),
                    )
                }
            }
            Text(
                card.locator,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
            if (card.uploadStatus != "completed") {
                // Why this row is where it is — shown by default, because
                // a status alone never explains a stuck photo.
                card.lastAttemptAtMs?.let {
                    Detail(
                        "Last attempt",
                        "${formatLocalDate(it)} ${formatLocalTime(it)}" +
                            if (card.retryCount > 0) " · ${card.retryCount} retries" else "",
                    )
                }
                card.uploadError?.let { Detail("Error", it) }
                if (card.fileMissing) {
                    Text(
                        "File is gone — this row can never upload. Delete it.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.testTag("file-missing"),
                    )
                }

                if (retryOffered) {
                    TextButton(
                        onClick = onRetry,
                        modifier = Modifier.testTag("retry-uploads-button"),
                    ) { Text("Retry uploads") }
                } else {
                    Text(
                        "Enable auto-upload in settings to retry failed uploads.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            // OUTSIDE the not-completed gate: a photo that uploaded fine is
            // still one you may want off the phone, and an orphaned row can
            // be in any state. Delete was unreachable for exactly the rows a
            // cleanup is aimed at.
            //
            // Confirmation is a DIALOG, not an inline expansion: growing the
            // card in place shoves every card below it down, so a second
            // delete aimed at the same spot lands on a different photo. For
            // a destructive action that is unacceptable — and the dialog has
            // room to say what the two deletes differ on.
            Row {
                TextButton(
                    onClick = { confirmingDelete = true },
                    modifier = Modifier.testTag("delete-photo-button"),
                ) { Text("Delete", color = MaterialTheme.colorScheme.error) }

                // Always drawn, disabled once the photo is out of our hands,
                // rather than appearing and disappearing with the status: a
                // row whose upload starts while you are looking at it would
                // otherwise pull Delete sideways under your thumb.
                TextButton(
                    onClick = { editingLicense = true },
                    enabled = licenseEditable(card.uploadStatus),
                    modifier = Modifier.testTag("change-license-button"),
                ) { Text("Change license") }
            }
        }
    }
}

@Composable
private fun Detail(label: String, value: String) {
    Row {
        Text(
            "$label: ",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodySmall)
    }
}

private fun fmt6(v: Double): String = cz.hillview.capture.fmtDecimals(v, 6)
private fun fmt1(v: Double): String = cz.hillview.capture.fmtDecimals(v, 1)

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

    var cards by remember { mutableStateOf<List<DevicePhotoCard>>(emptyList()) }
    var counts by remember { mutableStateOf(StatusCounts(0, 0, 0)) }
    var totalCount by remember { mutableStateOf(0) }
    var hasMore by remember { mutableStateOf(false) }
    var page by remember { mutableStateOf(1) }
    var loading by remember { mutableStateOf(true) }
    var loadingMore by remember { mutableStateOf(false) }

    suspend fun load(target: Int, append: Boolean) {
        val result = browser.page(target, PAGE_SIZE)
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
) {
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
                }
            }
            Text(
                card.locator,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 4.dp),
            )
            if (card.uploadStatus != "completed") {
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

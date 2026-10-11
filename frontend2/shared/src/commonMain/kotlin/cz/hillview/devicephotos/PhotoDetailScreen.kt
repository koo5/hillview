package cz.hillview.devicephotos

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.auth.SessionManager
import cz.hillview.auth.SessionState
import cz.hillview.settings.UploadSettingsRepository
import kotlinx.coroutines.launch
import org.koin.compose.koinInject

/**
 * One photo, on its own page — where the shutter's thumbnail lands.
 *
 * Deliberately the SAME [PhotoCard] the Device photos list draws rather than
 * a second design (user-asked: "a page that would basically equal a single
 * item of the Device photos page's list"). Everything you can say about a
 * photo is said in one place, so a control added to the list is here too,
 * and neither can drift into telling a different story about the same row.
 */
@Composable
fun PhotoDetailScreen(
    photoId: String,
    onBack: () -> Unit,
    browser: DevicePhotoBrowser = koinInject(),
    uploadSettingsRepo: UploadSettingsRepository = koinInject(),
    sessionManager: SessionManager = koinInject(),
) {
    val uploadSettings by uploadSettingsRepo.settings.collectAsState()
    val sessionState by sessionManager.state.collectAsState()
    val scope = rememberCoroutineScope()

    var card by remember(photoId) { mutableStateOf<DevicePhotoCard?>(null) }
    var loaded by remember(photoId) { mutableStateOf(false) }
    var canRate by remember { mutableStateOf(false) }
    LaunchedEffect(sessionState) { canRate = browser.canRate() }

    suspend fun reload() {
        card = browser.card(photoId)
        loaded = true
    }

    LaunchedEffect(photoId) { reload() }

    Column(
        Modifier
            .fillMaxSize()
            .safeContentPadding()
            .testTag("photo-detail-section"),
    ) {
        TextButton(onClick = onBack, modifier = Modifier.testTag("photo-detail-back")) {
            Text("< Back")
        }

        val current = card
        when {
            !loaded -> Text("Loading…", modifier = Modifier.padding(16.dp))
            current == null -> Text(
                // The row can genuinely be gone by the time this opens: a
                // server deletion that has just been pushed takes the row
                // with it (DELETE_FORGET_LOCALLY).
                "This photo is no longer on the device.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(16.dp).testTag("photo-detail-gone"),
            )
            else -> PhotoCard(
                card = current,
                retryOffered = sessionState is SessionState.LoggedIn,
                ratingEnabled = canRate,
                onRetry = {
                    scope.launch {
                        browser.retryUpload(current.id)
                        kotlinx.coroutines.delay(2_000)
                        reload()
                    }
                },
                onDelete = { alsoFile ->
                    scope.launch {
                        browser.delete(current.id, alsoFile)
                        // Deleting the only thing on the page is a reason to
                        // leave it, not to stare at an empty one.
                        onBack()
                    }
                },
                globalLicense = uploadSettings.license,
                onSetAnonymization = { value ->
                    scope.launch {
                        browser.setAnonymization(current.id, value)
                        kotlinx.coroutines.delay(2_000)
                        reload()
                    }
                },
                onSetRating = { rating ->
                    card = current.copy(rating = rating)
                    scope.launch { browser.setRating(current.id, rating) }
                },
                onSetServerDeletion = { wanted ->
                    card = current.copy(
                        serverDeletion = if (wanted) ServerDeletion.Pending else null,
                    )
                    scope.launch { browser.setServerDeletion(current.id, wanted) }
                },
                onChangeLicense = { license ->
                    card = current.copy(license = license)
                    scope.launch { browser.changeLicense(current.id, license) }
                },
            )
        }
    }
}

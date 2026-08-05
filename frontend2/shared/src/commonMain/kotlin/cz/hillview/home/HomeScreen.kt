package cz.hillview.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.auth.SessionManager
import cz.hillview.auth.SessionState
import kotlinx.coroutines.launch
import androidx.compose.runtime.rememberCoroutineScope
import org.koin.compose.koinInject

@Composable
fun HomeScreen(
    onOpenLogin: () -> Unit,
    onOpenClockVideo: () -> Unit,
    onOpenCapture: () -> Unit,
    onOpenSettings: () -> Unit,
    session: SessionManager = koinInject(),
) {
    val sessionState by session.state.collectAsState()
    val expiredNotice by session.sessionExpiredNotice.collectAsState()
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        session.restoreIfNeeded()
    }

    Column(
        modifier = Modifier
            .safeContentPadding()
            .fillMaxSize()
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "Hillview",
            style = MaterialTheme.typography.headlineLarge,
            modifier = Modifier.padding(bottom = 8.dp),
        )

        Text(
            text = when (val s = sessionState) {
                is SessionState.LoggedIn -> "Signed in as ${s.username ?: "?"}"
                SessionState.LoggedOut -> "Not signed in"
                SessionState.Unknown -> "…"
            },
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier
                .padding(bottom = 24.dp)
                .testTag("home-session-status"),
        )

        expiredNotice?.let { reason ->
            Text(
                text = "Session expired ($reason) — please sign in again.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier
                    .padding(bottom = 16.dp)
                    .testTag("home-session-expired"),
            )
        }

        Button(
            onClick = onOpenCapture,
            modifier = Modifier.testTag("home-capture-button"),
        ) {
            Text("Capture")
        }

        OutlinedButton(
            onClick = onOpenClockVideo,
            modifier = Modifier
                .padding(top = 12.dp)
                .testTag("home-clock-video-button"),
        ) {
            Text("Clock calibration video")
        }

        OutlinedButton(
            onClick = onOpenSettings,
            modifier = Modifier
                .padding(top = 12.dp)
                .testTag("home-settings-button"),
        ) {
            Text("Settings")
        }

        when (sessionState) {
            is SessionState.LoggedIn -> TextButton(
                onClick = { scope.launch { session.logout() } },
                modifier = Modifier
                    .padding(top = 24.dp)
                    .testTag("home-logout-button"),
            ) {
                Text("Sign out")
            }
            else -> TextButton(
                onClick = onOpenLogin,
                modifier = Modifier
                    .padding(top = 24.dp)
                    .testTag("home-login-button"),
            ) {
                Text("Sign in")
            }
        }
    }
}

package cz.hillview.auth.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import cz.hillview.auth.LoginViewModel
import org.koin.compose.viewmodel.koinViewModel

@Composable
fun LoginScreen(
    onBack: () -> Unit,
    onLoggedIn: () -> Unit,
    viewModel: LoginViewModel = koinViewModel(),
) {
    val state = viewModel.uiState

    LaunchedEffect(state.done) {
        if (state.done) onLoggedIn()
    }

    // The passive layer: the device's saved password, offered as the screen
    // opens (Credential Manager sheet; a no-op on platforms without one).
    LaunchedEffect(Unit) { viewModel.offerSavedCredential() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("< Back") }
            Text(
                text = "Sign in",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        OutlinedTextField(
            value = state.username,
            onValueChange = viewModel::onUsernameChange,
            label = { Text("Username") },
            singleLine = true,
            enabled = !state.submitting,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("login-username"),
        )

        OutlinedTextField(
            value = state.password,
            onValueChange = viewModel::onPasswordChange,
            label = { Text("Password") },
            singleLine = true,
            enabled = !state.submitting,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier
                .fillMaxWidth()
                .testTag("login-password"),
        )

        state.errorMessage?.let { message ->
            Text(
                text = message,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.testTag("login-error"),
            )
        }

        Button(
            onClick = viewModel::submit,
            enabled = !state.submitting,
            modifier = Modifier
                .fillMaxWidth()
                .testTag("login-submit"),
        ) {
            Text(if (state.submitting) "Signing in…" else "Sign in")
        }

        // The original login page's shape: the form, an OR divider, then
        // Continue with Google (its GitHub button is commented out there —
        // matched by not surfacing one here either). Native-only for now:
        // the button hides when no Google client id is configured; the
        // browser fallback joins with the deep-link work.
        if (state.googleAvailable) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth(),
            ) {
                HorizontalDivider(Modifier.weight(1f))
                Text(
                    "OR",
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(horizontal = 12.dp),
                )
                HorizontalDivider(Modifier.weight(1f))
            }
            Button(
                onClick = viewModel::googleSignIn,
                enabled = !state.submitting,
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("continue-with-google"),
            ) {
                Text("Continue with Google")
            }
        }
    }
}

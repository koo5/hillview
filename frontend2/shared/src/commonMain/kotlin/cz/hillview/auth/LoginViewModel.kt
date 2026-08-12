package cz.hillview.auth

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.launch

data class LoginUiState(
    val username: String = "",
    val password: String = "",
    val submitting: Boolean = false,
    val errorMessage: String? = null,
    val done: Boolean = false,
    /** Show the Continue-with-Google button (client id configured). */
    val googleAvailable: Boolean = false,
)

class LoginViewModel(
    private val session: SessionManager,
    private val gateway: CredentialGateway = NoopCredentialGateway(),
) : ViewModel() {

    var uiState by mutableStateOf(LoginUiState(googleAvailable = gateway.googleAvailable))
        private set

    private var offeredSaved = false

    fun onUsernameChange(value: String) {
        uiState = uiState.copy(username = value, errorMessage = null)
    }

    fun onPasswordChange(value: String) {
        uiState = uiState.copy(password = value, errorMessage = null)
    }

    /**
     * The passive layer: offer the device's saved password once per screen
     * visit — picking one signs in without a keystroke; dismissing the
     * sheet just leaves the form. The credential came FROM the provider,
     * so nothing is saved back.
     */
    fun offerSavedCredential() {
        if (offeredSaved || uiState.submitting) return
        offeredSaved = true
        viewModelScope.launch {
            val saved = gateway.getSavedPassword() ?: return@launch
            uiState = uiState.copy(username = saved.username, password = saved.password)
            submit(saveOnSuccess = false)
        }
    }

    fun submit() = submit(saveOnSuccess = true)

    private fun submit(saveOnSuccess: Boolean) {
        if (uiState.submitting) return
        val u = uiState.username.trim()
        val p = uiState.password
        if (u.isEmpty() || p.isEmpty()) {
            uiState = uiState.copy(errorMessage = "Username and password are required")
            return
        }
        uiState = uiState.copy(submitting = true, errorMessage = null)
        viewModelScope.launch {
            try {
                session.login(u, p)
                if (saveOnSuccess) {
                    // The provider shows its own save sheet; declining is
                    // a valid answer and the login stands either way.
                    gateway.savePassword(u, p)
                }
                uiState = uiState.copy(submitting = false, done = true)
            } catch (e: InvalidCredentialsException) {
                uiState = uiState.copy(submitting = false, errorMessage = "Wrong username or password")
            } catch (e: Exception) {
                uiState = uiState.copy(
                    submitting = false,
                    errorMessage = "Could not reach the server (${e.message ?: e::class.simpleName})",
                )
            }
        }
    }

    /**
     * Native Sign in with Google: the system sheet produces an ID token,
     * the backend exchanges it for our session pair. A null token is a
     * dismissal — not an error, nothing to show.
     */
    fun googleSignIn() {
        if (uiState.submitting) return
        uiState = uiState.copy(submitting = true, errorMessage = null)
        viewModelScope.launch {
            try {
                val idToken = gateway.googleIdToken()
                if (idToken == null) {
                    uiState = uiState.copy(submitting = false)
                } else {
                    session.loginWithGoogle(idToken)
                    uiState = uiState.copy(submitting = false, done = true)
                }
            } catch (e: InvalidCredentialsException) {
                uiState = uiState.copy(
                    submitting = false,
                    errorMessage = "Google sign-in was rejected by the server",
                )
            } catch (e: Exception) {
                uiState = uiState.copy(
                    submitting = false,
                    errorMessage = "Could not reach the server (${e.message ?: e::class.simpleName})",
                )
            }
        }
    }
}

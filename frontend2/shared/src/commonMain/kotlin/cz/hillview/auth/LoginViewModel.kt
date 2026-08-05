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
)

class LoginViewModel(
    private val session: SessionManager,
) : ViewModel() {

    var uiState by mutableStateOf(LoginUiState())
        private set

    fun onUsernameChange(value: String) {
        uiState = uiState.copy(username = value, errorMessage = null)
    }

    fun onPasswordChange(value: String) {
        uiState = uiState.copy(password = value, errorMessage = null)
    }

    fun submit() {
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
}

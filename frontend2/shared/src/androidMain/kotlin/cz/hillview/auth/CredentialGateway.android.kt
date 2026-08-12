package cz.hillview.auth

import android.app.Activity
import android.content.Context
import androidx.credentials.CreatePasswordRequest
import androidx.credentials.CredentialManager
import androidx.credentials.CustomCredential
import androidx.credentials.GetCredentialRequest
import androidx.credentials.GetPasswordOption
import androidx.credentials.PasswordCredential
import androidx.credentials.exceptions.CreateCredentialException
import androidx.credentials.exceptions.GetCredentialException
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential

/**
 * Build-time native-auth wiring, set by HillviewApplication before Koin
 * starts (the PhotoStorage.folderBase pattern).
 *
 * [googleServerClientId] is the WEB client id the backend verifies
 * ID-token audiences against — the exact same GOOGLE_CLIENT_ID value the
 * server holds; passed to Credential Manager as serverClientId. Empty
 * (the default) keeps the Continue-with-Google button hidden.
 *
 * [uiEnabled] is the kill-switch for the system sheets: the app-behaviour
 * tests drive the login UI and must never meet a Credential Manager
 * bottom sheet mid-test (they run in-process and flip this directly).
 */
object NativeAuthConfig {
    var googleServerClientId: String = ""
    var uiEnabled: Boolean = true
}

/**
 * The foreground activity, registered by MainActivity's resume/pause.
 * Credential Manager refuses an application context — its bottom sheets
 * need a real activity window to attach to.
 */
object CurrentActivityHolder {
    @Volatile
    var activity: Activity? = null
}

class AndroidCredentialGateway(
    appContext: Context,
) : CredentialGateway {
    private val manager by lazy { CredentialManager.create(appContext) }

    override val googleAvailable: Boolean
        get() = NativeAuthConfig.googleServerClientId.isNotBlank()

    private fun host(): Activity? =
        if (NativeAuthConfig.uiEnabled) CurrentActivityHolder.activity else null

    override suspend fun getSavedPassword(): SavedCredential? {
        val activity = host() ?: return null
        return try {
            val result = manager.getCredential(
                context = activity,
                request = GetCredentialRequest(listOf(GetPasswordOption())),
            )
            (result.credential as? PasswordCredential)
                ?.let { SavedCredential(it.id, it.password) }
        } catch (e: GetCredentialException) {
            // No provider, no saved credential, or a dismissal — all mean
            // "type it yourself"; never an error the UI should surface.
            null
        }
    }

    override suspend fun savePassword(username: String, password: String) {
        val activity = host() ?: return
        try {
            manager.createCredential(activity, CreatePasswordRequest(username, password))
        } catch (e: CreateCredentialException) {
            // Declining to save is a valid answer; the login stands.
        }
    }

    override suspend fun googleIdToken(): String? {
        val activity = host() ?: return null
        if (!googleAvailable) return null
        return try {
            val option = GetGoogleIdOption.Builder()
                .setServerClientId(NativeAuthConfig.googleServerClientId)
                // Offer every device account, not only previously
                // authorized ones — first sign-in is exactly the moment
                // this sheet appears.
                .setFilterByAuthorizedAccounts(false)
                .build()
            val result = manager.getCredential(activity, GetCredentialRequest(listOf(option)))
            val credential = result.credential
            if (credential is CustomCredential &&
                credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL
            ) {
                GoogleIdTokenCredential.createFrom(credential.data).idToken
            } else {
                null
            }
        } catch (e: GetCredentialException) {
            // No Play services (degoogled), dismissed, or not set up — the
            // browser fallback joins with the deep-link work; until then
            // this quietly stands down.
            null
        }
    }
}

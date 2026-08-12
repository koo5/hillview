package cz.hillview.auth

/** A username+password the device's credential provider handed back. */
data class SavedCredential(val username: String, val password: String)

/**
 * The device credential layer (Android: Credential Manager) behind one
 * seam. Every call is best-effort and may show a system sheet:
 * implementations return null / do nothing when the platform has no
 * provider, the user dismisses, or the sheets are administratively off
 * (instrumented tests drive the login UI and must never meet one).
 *
 * The native paths only change how a login PROOF is acquired — the
 * backend stays the sole token authority, and everything downstream of
 * [SessionManager] is unaware which front door minted the session.
 */
interface CredentialGateway {
    /** Native Sign in with Google is worth offering (client id configured). */
    val googleAvailable: Boolean

    suspend fun getSavedPassword(): SavedCredential?

    suspend fun savePassword(username: String, password: String)

    /** A verified Google ID token, or null (dismissed / no Play / not set up). */
    suspend fun googleIdToken(): String?
}

/** Platforms without a credential provider (desktop JVM, tests). */
class NoopCredentialGateway : CredentialGateway {
    override val googleAvailable = false
    override suspend fun getSavedPassword(): SavedCredential? = null
    override suspend fun savePassword(username: String, password: String) {}
    override suspend fun googleIdToken(): String? = null
}

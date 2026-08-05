package cz.hillview.auth

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class Token(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String? = null,
    @SerialName("token_type") val tokenType: String,
    // ISO datetimes; kept as strings — nothing needs instant math yet.
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("refresh_token_expires_at") val refreshTokenExpiresAt: String? = null,
)

@Serializable
data class UserOut(
    val id: String,
    val email: String,
    val username: String,
    @SerialName("is_active") val isActive: Boolean,
    @SerialName("is_test") val isTest: Boolean = false,
    val role: String = "user",
)

@Serializable
data class StoredTokens(
    val accessToken: String,
    val refreshToken: String? = null,
    val expiresAt: String? = null,
    // Needed by the shared-kt AuthenticationManager (Android): it refuses to
    // refresh without a stored refresh-token expiry.
    val refreshTokenExpiresAt: String? = null,
    val username: String? = null,
)

/** Login/refresh rejected the credentials — definitive. */
class InvalidCredentialsException(message: String) : Exception(message)

/** The session is over (refresh token rejected) — definitive, logs out. */
class SessionExpiredException(message: String) : Exception(message)

/**
 * Backend or network trouble (5xx, IO) — transient. The session survives;
 * this mirrors the old app's hard-learned behavior (a 5xx during token
 * refresh must NOT log the user out).
 */
class TransientBackendException(message: String, cause: Throwable? = null) : Exception(message, cause)

/** An authorized call came back 401 — access token stale, try refresh. */
class UnauthorizedException(message: String) : Exception(message)

class NotLoggedInException : Exception("not logged in")

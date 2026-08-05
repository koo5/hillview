package cz.hillview.auth

import cz.hillview.core.net.BackendConfig
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.forms.submitForm
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.http.parameters
import io.ktor.utils.io.errors.IOException
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
private data class RefreshTokenRequest(@SerialName("refresh_token") val refreshToken: String)

class AuthApi(
    private val http: HttpClient,
    private val config: BackendConfig,
) {
    private fun url(path: String) = config.apiUrl.trimEnd('/') + path

    suspend fun token(username: String, password: String): Token {
        val response = wrapIo {
            http.submitForm(
                url = url("/auth/token"),
                formParameters = parameters {
                    append("grant_type", "password")
                    append("username", username)
                    append("password", password)
                },
            )
        }
        return when {
            response.status.isSuccess() -> response.body()
            response.status.isDefinitiveAuthFailure() ->
                throw InvalidCredentialsException("login rejected: ${response.status} ${response.safeBody()}")
            else -> throw TransientBackendException("login failed: ${response.status}")
        }
    }

    suspend fun refresh(refreshToken: String): Token {
        val response = wrapIo {
            http.post(url("/auth/refresh")) {
                contentType(ContentType.Application.Json)
                setBody(RefreshTokenRequest(refreshToken))
            }
        }
        return when {
            response.status.isSuccess() -> response.body()
            response.status.isDefinitiveAuthFailure() ->
                throw SessionExpiredException("refresh rejected: ${response.status}")
            else -> throw TransientBackendException("refresh failed: ${response.status}")
        }
    }

    suspend fun me(accessToken: String): UserOut {
        val response = wrapIo {
            http.get(url("/auth/me")) {
                header(HttpHeaders.Authorization, "Bearer $accessToken")
            }
        }
        return when {
            response.status.isSuccess() -> response.body()
            response.status == HttpStatusCode.Unauthorized ->
                throw UnauthorizedException("me: 401")
            else -> throw TransientBackendException("me failed: ${response.status}")
        }
    }

    suspend fun logout(accessToken: String) {
        // Best-effort server-side logout; local state is cleared regardless.
        wrapIo {
            http.post(url("/auth/logout")) {
                header(HttpHeaders.Authorization, "Bearer $accessToken")
            }
        }
    }

    private fun HttpStatusCode.isDefinitiveAuthFailure(): Boolean =
        this == HttpStatusCode.BadRequest ||
            this == HttpStatusCode.Unauthorized ||
            this == HttpStatusCode.Forbidden ||
            this == HttpStatusCode.UnprocessableEntity

    private suspend fun HttpResponse.safeBody(): String =
        try { bodyAsText().take(200) } catch (e: Exception) { "" }

    private suspend fun wrapIo(block: suspend () -> HttpResponse): HttpResponse =
        try {
            block()
        } catch (e: IOException) {
            throw TransientBackendException("network error: ${e.message}", e)
        }
}

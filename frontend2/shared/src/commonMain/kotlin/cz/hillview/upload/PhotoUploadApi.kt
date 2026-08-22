package cz.hillview.upload

import cz.hillview.auth.SessionManager
import cz.hillview.auth.UnauthorizedException
import cz.hillview.core.net.BackendConfig
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.bodyAsText
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import io.ktor.utils.io.errors.IOException

/** Rewrites dev worker URLs for the platform (emulator loopback). */
expect fun mapWorkerUrl(url: String): String

class PhotoUploadApi(
    private val http: HttpClient,
    private val config: BackendConfig,
    private val session: SessionManager,
) {
    private fun url(path: String) = config.apiUrl.trimEnd('/') + path

    /** Idempotent; registers the signing key for the logged-in account. */
    suspend fun registerClientKey(signer: UploadSigner) {
        session.authorized { token ->
            val response = http.post(url("/auth/register-client-key")) {
                header(HttpHeaders.Authorization, "Bearer $token")
                contentType(ContentType.Application.Json)
                setBody(ClientPublicKeyData(signer.publicKeyPem, signer.keyId, signer.createdAtIso))
            }
            when {
                response.status.isSuccess() -> Unit
                response.status == HttpStatusCode.Unauthorized -> throw UnauthorizedException("register-client-key: 401")
                response.status.value in 500..599 ->
                    throw UploadRetryableException("register-client-key: ${response.status}")
                else -> throw UploadPermanentException(
                    "register-client-key: ${response.status} ${response.bodyAsText().take(200)}"
                )
            }
        }
    }

    suspend fun authorize(request: UploadAuthorizationRequest): UploadAuthorizationResponse =
        session.authorized { token ->
            val response = try {
                http.post(url("/photos/authorize-upload")) {
                    header(HttpHeaders.Authorization, "Bearer $token")
                    contentType(ContentType.Application.Json)
                    setBody(request)
                }
            } catch (e: IOException) {
                throw UploadRetryableException("authorize: network error: ${e.message}", e)
            }
            when {
                response.status.isSuccess() -> response.body()
                response.status == HttpStatusCode.Unauthorized -> throw UnauthorizedException("authorize: 401")
                response.status.value in 500..599 ->
                    throw UploadRetryableException("authorize: ${response.status}")
                else -> throw UploadPermanentException(
                    "authorize: ${response.status} ${response.bodyAsText().take(200)}"
                )
            }
        }

    /**
     * Readiness preflight, then multipart upload to the worker. A 503 from
     * /ready means the fleet is saturated — abort the drain pass (ported
     * WorkerBusy semantics; fly machine pinning is dropped for now, dev runs
     * a single worker).
     */
    suspend fun uploadToWorker(
        workerUrl: String,
        uploadJwt: String,
        filename: String,
        bytes: ByteArray,
        signature: String,
    ) {
        val base = mapWorkerUrl(workerUrl).trimEnd('/')
        val ready = try {
            http.get("$base/ready")
        } catch (e: IOException) {
            throw UploadRetryableException("worker preflight: ${e.message}", e)
        }
        when {
            ready.status == HttpStatusCode.ServiceUnavailable ->
                throw WorkerBusyException("worker upload queue is full")
            ready.status == HttpStatusCode.NotFound -> Unit // older worker without /ready
            !ready.status.isSuccess() ->
                throw UploadRetryableException("worker not ready: ${ready.status}")
        }

        val response = try {
            http.post("$base/upload_async") {
                header(HttpHeaders.Authorization, "Bearer $uploadJwt")
                setBody(
                    MultiPartFormDataContent(
                        formData {
                            append(
                                "file",
                                bytes,
                                Headers.build {
                                    append(HttpHeaders.ContentType, "image/jpeg")
                                    append(
                                        HttpHeaders.ContentDisposition,
                                        "filename=\"$filename\"",
                                    )
                                },
                            )
                            append("client_signature", signature)
                        }
                    )
                )
            }
        } catch (e: IOException) {
            throw UploadRetryableException("worker upload: network error: ${e.message}", e)
        }
        when {
            response.status.isSuccess() -> Unit
            response.status == HttpStatusCode.ServiceUnavailable ->
                throw WorkerBusyException("worker rejected: queue full")
            response.status.value in 500..599 ->
                throw UploadRetryableException("worker upload: ${response.status}")
            else -> throw UploadPermanentException(
                "worker upload: ${response.status} ${response.bodyAsText().take(200)}"
            )
        }
    }
}

package cz.hillview.upload

import cz.hillview.auth.AuthApi
import cz.hillview.auth.InMemoryTokenStore
import cz.hillview.auth.SessionManager
import cz.hillview.core.net.BackendConfig
import cz.hillview.core.net.createHttpClient
import kotlinx.coroutines.runBlocking
import org.junit.Assume.assumeTrue
import java.awt.image.BufferedImage
import java.io.File
import java.net.HttpURLConnection
import java.net.URI
import javax.imageio.ImageIO
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

/**
 * The whole upload protocol against the real stack: docker api + worker.
 * ECDSA key registration, md5 dedup authorize, signed worker upload.
 */
class BackendUploadIntegrationTest {

    // Full API URL, per project convention (never assembled from a host).
    private val apiUrl = System.getenv("HILLVIEW_BACKEND") ?: "http://localhost:8055/api"

    private fun backendUp(): Boolean = try {
        val conn = URI("$apiUrl/debug").toURL().openConnection() as HttpURLConnection
        conn.connectTimeout = 2_000
        conn.readTimeout = 2_000
        conn.responseCode == 200
    } catch (e: Exception) {
        false
    }

    @Test
    fun endToEndUploadThroughWorker() {
        assumeTrue("backend not running at $apiUrl", backendUp())
        runBlocking {
            val tmp = File.createTempFile("hillview-upload-test", "").parentFile
            val work = File(tmp, "hv-upload-${System.nanoTime()}").also { it.mkdirs() }

            // Unique image every run so md5 dedup doesn't short-circuit.
            val img = BufferedImage(32, 32, BufferedImage.TYPE_INT_RGB)
            img.setRGB(3, 3, (System.nanoTime() and 0xFFFFFF).toInt())
            val photoFile = File(work, "hv_it_${System.currentTimeMillis()}.jpg")
            ImageIO.write(img, "jpg", photoFile)

            val http = createHttpClient()
            val config = BackendConfig(apiUrl)
            val session = SessionManager(AuthApi(http, config), InMemoryTokenStore())
            session.restoreIfNeeded()
            session.login("test", "StrongTestPassword123!")

            // Drives PhotoUploadApi directly — the UploadQueue that once sat
            // between capture and this protocol was retired (2026-08-05, see
            // /frontend2/attic); on Android the shared-kt stack replaces it.
            val api = PhotoUploadApi(http, config, session)
            val signer = EcdsaUploadSigner(File(work, "client_key"))
            api.registerClientKey(signer)

            val bytes = readFileBytes(photoFile.absolutePath)
            val auth = api.authorize(
                UploadAuthorizationRequest(
                    filename = photoFile.name,
                    fileSize = bytes.size.toLong(),
                    contentType = "image/jpeg",
                    fileMd5 = md5Hex(bytes),
                    clientKeyId = signer.keyId,
                    license = "ccbysa4+osm",
                    latitude = 50.115,
                    longitude = 14.501,
                    bearing = 123.0,
                )
            )
            assertEquals(false, auth.duplicate, "unique image deduped: ${auth.message}")
            val photoId = assertNotNull(auth.photoId)
            val uploadJwt = assertNotNull(auth.uploadJwt)
            val workerUrl = assertNotNull(auth.workerUrl)
            val authorizedAt = assertNotNull(auth.uploadAuthorizedAt)

            api.uploadToWorker(
                workerUrl = workerUrl,
                uploadJwt = uploadJwt,
                filename = photoFile.name,
                bytes = bytes,
                signature = signer.signUpload(photoFile.name, photoId, authorizedAt),
            )
            println("uploaded photo_id=$photoId")
        }
    }
}

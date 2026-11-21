package cz.hillview.plugin

import com.sun.net.httpserver.HttpsConfigurator
import com.sun.net.httpserver.HttpsServer
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.net.InetSocketAddress
import java.nio.file.Files
import java.security.KeyStore
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext
import kotlin.test.AfterTest
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/**
 * A self-signed worker, trusted by pinning (shared-kt WorkerOverride.kt) —
 * against a real TLS server on loopback, with certificates keytool makes, so
 * the handshake, the chain validation and the hostname check are the JDK's
 * own and not a fake of them.
 */
class WorkerPinningTest {

    private val dir: File = Files.createTempDirectory("worker-pin").toFile()
    private val servers = mutableListOf<HttpsServer>()
    private val base = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .build()

    @AfterTest
    fun cleanUp() {
        servers.forEach { it.stop(0) }
        dir.deleteRecursively()
    }

    /** A PKCS12 key store holding one self-signed EC certificate. */
    private fun keyStore(name: String, san: String?): KeyStore {
        val file = File(dir, "$name.p12")
        val keytool = File(System.getProperty("java.home"), "bin/keytool").path
        val cmd = mutableListOf(
            keytool, "-genkeypair", "-alias", "w", "-keyalg", "EC", "-groupname", "secp256r1",
            "-dname", "CN=$name", "-validity", "2", "-storetype", "PKCS12",
            "-keystore", file.path, "-storepass", "secret", "-keypass", "secret",
        )
        if (san != null) cmd += listOf("-ext", "san=$san")
        val p = ProcessBuilder(cmd).redirectErrorStream(true).start()
        val out = p.inputStream.bufferedReader().readText()
        check(p.waitFor() == 0) { "keytool failed: $out" }
        return KeyStore.getInstance("PKCS12").apply { file.inputStream().use { load(it, "secret".toCharArray()) } }
    }

    private fun certOf(store: KeyStore) = store.getCertificate("w") as X509Certificate

    /** An https worker on loopback answering /ready, as [store]. Its base URL. */
    private fun worker(store: KeyStore, host: String = "localhost"): String {
        val kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
        kmf.init(store, "secret".toCharArray())
        val ssl = SSLContext.getInstance("TLS").apply { init(kmf.keyManagers, null, null) }
        val server = HttpsServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.httpsConfigurator = HttpsConfigurator(ssl)
        server.createContext("/ready") { ex ->
            val body = "{}".toByteArray()
            ex.sendResponseHeaders(200, body.size.toLong())
            ex.responseBody.use { it.write(body) }
        }
        server.start()
        servers += server
        return "https://$host:${server.address.port}"
    }

    private fun ready(client: OkHttpClient, url: String): Int =
        client.newCall(Request.Builder().url("$url/ready").build()).execute().use { it.code }

    @Test
    fun theProbeHandsBackTheCertificateWithoutConnecting() {
        val store = keyStore("worker", "dns:localhost,ip:127.0.0.1")
        val url = worker(store)
        val presented = fetchPresentedCertificate(base, url)
        assertContentEquals(certOf(store).encoded, presented.encoded)
    }

    @Test
    fun withoutAPinASelfSignedWorkerIsRefused() {
        val url = worker(keyStore("worker", "dns:localhost"))
        val e = assertFailsWith<javax.net.ssl.SSLException> { ready(base, url) }
        assertTrue(checkWorker(base, url, null).startsWith("Failed"), describeFailure(e))
    }

    @Test
    fun pinnedTheWorkerIsReached() {
        val store = keyStore("worker", "dns:localhost,ip:127.0.0.1")
        val url = worker(store)
        val pin = fetchPresentedCertificate(base, url).encoded
        assertEquals(200, ready(pinnedClient(base, pin), url))
        assertTrue(checkWorker(base, url, pin).startsWith("Ready"))
    }

    @Test
    fun aDifferentServerAtTheSameAddressIsRefused() {
        val pinned = certOf(keyStore("worker", "dns:localhost")).encoded
        val impostor = worker(keyStore("impostor", "dns:localhost"))
        assertFailsWith<javax.net.ssl.SSLException> { ready(pinnedClient(base, pinned), impostor) }
        val line = checkWorker(base, impostor, pinned)
        assertTrue(line.startsWith("Failed"), line)
    }

    /**
     * A home-made certificate often names no host, or not the address it is
     * reached by. Byte-for-byte the pinned one, it is still the pinned server.
     */
    @Test
    fun aPinnedCertificateNamingNoHostIsStillAccepted() {
        val store = keyStore("bare", san = null)
        val url = worker(store, host = "127.0.0.1")
        assertEquals(200, ready(pinnedClient(base, certOf(store).encoded), url))
    }

    @Test
    fun aFailureIsDescribedWithItsCauses() {
        val inner = java.security.cert.CertPathValidatorException("Trust anchor for certification path not found.")
        val outer = javax.net.ssl.SSLHandshakeException("handshake failed").apply { initCause(inner) }
        assertEquals(
            "SSLHandshakeException: handshake failed ← CertPathValidatorException: Trust anchor for certification path not found.",
            describeFailure(outer),
        )
    }

    @Test
    fun theFingerprintIsSha256InTheBrowsersForm() {
        val fp = certificateFingerprint(byteArrayOf(1, 2, 3))
        assertEquals(32 * 3 - 1, fp.length)
        assertTrue(fp.matches(Regex("([0-9A-F]{2}:){31}[0-9A-F]{2}")), fp)
    }
}

package cz.hillview.upload

import java.io.File
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import java.security.spec.PKCS8EncodedKeySpec
import java.text.SimpleDateFormat
import java.util.Base64
import java.util.Date
import java.util.Locale
import java.util.TimeZone

actual fun md5Hex(bytes: ByteArray): String =
    MessageDigest.getInstance("MD5").digest(bytes)
        .joinToString("") { b -> ((b.toInt() and 0xFF) + 0x100).toString(16).substring(1) }

/**
 * ECDSA P-256 client key, persisted as a small JSON-ish properties file under
 * the app's private storage. Signature format is base64 DER from
 * SHA256withECDSA, matching the old Kotlin client (ClientCryptoManager);
 * the backend accepts it alongside the browsers' P1363.
 */
class EcdsaUploadSigner(private val keyFile: File) : UploadSigner {

    override val keyId: String
    override val publicKeyPem: String
    override val createdAtIso: String
    private val privateKey: PrivateKey

    init {
        val loaded = load()
        keyId = loaded.first
        publicKeyPem = loaded.second
        createdAtIso = loaded.third.first
        privateKey = loaded.third.second
    }

    override fun sign(payload: String): String {
        val signature = Signature.getInstance("SHA256withECDSA")
        signature.initSign(privateKey)
        signature.update(payload.toByteArray(Charsets.UTF_8))
        return Base64.getEncoder().encodeToString(signature.sign())
    }

    private fun load(): Triple<String, String, Pair<String, PrivateKey>> {
        if (keyFile.exists()) {
            try {
                val lines = keyFile.readLines().associate {
                    val i = it.indexOf('=')
                    it.substring(0, i) to it.substring(i + 1)
                }
                val keyBytes = Base64.getDecoder().decode(lines.getValue("private_pkcs8"))
                val priv = KeyFactory.getInstance("EC")
                    .generatePrivate(PKCS8EncodedKeySpec(keyBytes))
                return Triple(
                    lines.getValue("key_id"),
                    lines.getValue("public_pem").replace("\\n", "\n"),
                    lines.getValue("created_at") to priv,
                )
            } catch (e: Exception) {
                // corrupt — regenerate below
            }
        }

        val generator = KeyPairGenerator.getInstance("EC")
        generator.initialize(ECGenParameterSpec("secp256r1"), SecureRandom())
        val pair = generator.generateKeyPair()

        val pem = buildString {
            append("-----BEGIN PUBLIC KEY-----\n")
            Base64.getEncoder().encodeToString(pair.public.encoded)
                .chunked(64).forEach { append(it).append('\n') }
            append("-----END PUBLIC KEY-----\n")
        }
        val id = "key_" + md5Hex(pair.public.encoded).take(16)
        val createdAt = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
            .apply { timeZone = TimeZone.getTimeZone("UTC") }
            .format(Date())

        keyFile.parentFile?.mkdirs()
        keyFile.writeText(
            listOf(
                "key_id=$id",
                "created_at=$createdAt",
                "public_pem=${pem.replace("\n", "\\n")}",
                "private_pkcs8=${Base64.getEncoder().encodeToString(pair.private.encoded)}",
            ).joinToString("\n")
        )
        return Triple(id, pem, createdAt to pair.private)
    }
}

// FileQueueStore was retired with the UploadQueue (2026-08-05) — parked in
// /frontend2/attic/FileQueueStore.kt.fragment.

fun readFileBytes(path: String): ByteArray = File(path).readBytes()

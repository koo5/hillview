package cz.hillview.upload

import android.content.Context
import cz.hillview.plugin.ClientCryptoManager

/**
 * UploadSigner backed by the shared-kt ClientCryptoManager — the exact
 * battle-tested implementation the Tauri app ships, with keys in
 * AndroidKeyStore (an upgrade over the file-backed EcdsaUploadSigner, which
 * remains for JVM/desktop and tests).
 */
class KeystoreUploadSigner(context: Context) : UploadSigner {

    private val manager = ClientCryptoManager(context)
    private val info = run {
        check(manager.getOrCreateKeyPair()) { "client key pair unavailable" }
        manager.getPublicKeyInfo() ?: throw IllegalStateException("client key info unavailable")
    }

    override val keyId: String = info.keyId
    override val publicKeyPem: String = info.publicKeyPem
    override val createdAtIso: String = info.createdAt

    override fun sign(payload: String): String =
        throw UnsupportedOperationException("use signUpload()")

    override fun signUpload(filename: String, photoId: String, authorizedAt: Long): String =
        manager.signUploadData(photoId, filename, authorizedAt)?.signature
            ?: throw IllegalStateException("signing failed")
}

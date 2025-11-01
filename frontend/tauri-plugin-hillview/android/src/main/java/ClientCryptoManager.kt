package cz.hillview.plugin

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import org.json.JSONObject
import java.security.*
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec
import java.util.*

/**
 * Android Client-Side Cryptographic Key Management
 *
 * Implements the same secure upload authorization scheme as the web client,
 * using Android Keystore for secure key storage and ECDSA P-256 signatures.
 *
 * SECURITY ARCHITECTURE:
 * =====================
 *
 * This Android implementation mirrors the web client's three-phase security model:
 *
 * Phase 1 - Upload Authorization (Client → API Server):
 *   - Android app requests upload authorization with file metadata
 *   - API server creates pending photo record and returns upload JWT
 *   - Upload JWT contains: photo_id, user_id, client_public_key_id, expiry
 *
 * Phase 2 - Signed Upload (Client → Worker):
 *   - Android app signs upload payload: {photo_id, filename, timestamp}
 *   - App sends: upload_jwt + file + client_signature to worker
 *   - Worker verifies upload_jwt using API server's public key
 *   - Worker processes file (does NOT verify client signature)
 *
 * Phase 3 - Result Storage (Worker → API Server):
 *   - Worker sends processed results + client_signature to API
 *   - API server verifies client_signature using client's public key
 *   - Only saves results if client signature is valid
 *   - Signature retained in database for audit trail
 *
 * ANDROID KEYSTORE INTEGRATION:
 * =============================
 *
 * - Uses Android Keystore for secure private key storage
 * - Private keys are hardware-backed when available (TEE/Secure Element)
 * - Keys survive app reinstalls and are tied to device identity
 * - Public key exported for server registration
 * - ECDSA P-256 for compatibility with web client
 *
 * BENEFITS:
 * =========
 *
 * ✅ Hardware-backed security (when available)
 * ✅ Keys protected by Android Keystore
 * ✅ Consistent with web client architecture
 * ✅ Non-repudiation and tamper-proofing
 * ✅ Zero-trust workers
 */
class ClientCryptoManager(private val context: Context) {

    companion object {
        private const val TAG = "🢄ClientCryptoManager"
        private const val PREFS_NAME = "hillview_client_crypto"
        private const val KEY_ALIAS = "hillview_client_signing_key"
        private const val KEY_ID_PREF = "client_key_id"
        private const val KEY_CREATED_PREF = "client_key_created"
        private const val PUBLIC_KEY_PEM_PREF = "client_public_key_pem"
    }

    private val prefs: SharedPreferences = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val keyStore: KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    /**
     * Get or generate client ECDSA key pair
     *
     * This is the main entry point for key management. It ensures the Android app
     * always has a valid ECDSA key pair for signing upload requests.
     *
     * Flow:
     * 1. Check if key exists in Android Keystore
     * 2. If key missing, generate new P-256 ECDSA key pair in Keystore
     * 3. Export public key and store metadata in SharedPreferences
     *
     * Keys persist in Android Keystore across app reinstalls and are tied to
     * device hardware when available. If keys are lost, a new pair will be
     * generated and the server will need the new public key on next login.
     */
    fun getOrCreateKeyPair(): Boolean {
        try {
            // Check if key already exists in Keystore
            if (keyStore.containsAlias(KEY_ALIAS)) {
                Log.d(TAG, "Client key pair already exists in Keystore")
                return true
            }

            Log.d(TAG, "Generating new client ECDSA key pair in Android Keystore")

            // Generate P-256 ECDSA key pair in Android Keystore
            val keyGenerator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")

            val keyGenSpec = KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_SIGN
            )
                .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1")) // P-256
                .setDigests(KeyProperties.DIGEST_SHA256)
                .setUserAuthenticationRequired(false) // Allow background signing
                .build()

            keyGenerator.initialize(keyGenSpec)
            val keyPair = keyGenerator.generateKeyPair()

            // Store metadata and public key for easy access
            storeKeyMetadata(keyPair.public)

            Log.d(TAG, "New client key pair generated successfully")
            return true

        } catch (e: Exception) {
            Log.e(TAG, "Error generating client key pair: ${e.message}", e)
            return false
        }
    }

    /**
     * Get client public key info for registration with server
     *
     * Called during login process to register the client's public key with the API server.
     * The server stores this public key and associates it with the user account.
     *
     * Returns ClientKeyInfo containing:
     * - publicKeyPem: PEM-formatted public key for server storage
     * - keyId: Unique identifier for this key pair
     * - createdAt: Timestamp when key was first generated
     *
     * The server uses this information to:
     * 1. Store the public key in user_public_keys table
     * 2. Include keyId in upload authorization JWTs
     * 3. Verify client signatures during upload process
     */
    fun getPublicKeyInfo(): ClientKeyInfo? {
        try {
            // Ensure key pair exists
            if (!getOrCreateKeyPair()) {
                Log.e(TAG, "Failed to ensure key pair exists")
                return null
            }

            val publicKeyPem = prefs.getString(PUBLIC_KEY_PEM_PREF, null)
            val keyId = prefs.getString(KEY_ID_PREF, null)
            val createdAt = prefs.getString(KEY_CREATED_PREF, null)

            if (publicKeyPem == null || keyId == null || createdAt == null) {
                Log.e(TAG, "Key metadata missing from SharedPreferences")
                return null
            }

            return ClientKeyInfo(
                publicKeyPem = publicKeyPem,
                keyId = keyId,
                createdAt = createdAt
            )

        } catch (e: Exception) {
            Log.e(TAG, "Error getting public key info: ${e.message}", e)
            return null
        }
    }

    /**
     * Sign upload data with client private key
     *
     * Creates a cryptographic signature proving the client authorized this specific upload.
     * This is the core security mechanism that prevents worker impersonation attacks.
     *
     * Process:
     * 1. Creates canonical JSON representation of upload data
     * 2. Signs the JSON string using client's ECDSA private key from Keystore
     * 3. Returns signature data containing both base64-encoded signature and key ID
     *
     * The signature covers:
     * - photo_id: Links to specific upload authorization
     * - filename: Prevents file substitution attacks
     * - timestamp: Prevents replay attacks
     *
     * The API server will later verify this signature using the client's
     * registered public key before accepting processed results.
     *
     * @param photoId Photo ID from upload authorization
     * @param filename Original filename being uploaded
     * @param timestamp Current timestamp (prevents replay)
     * @return SignatureData containing signature and key ID, or null on error
     */
    fun signUploadData(photoId: String, filename: String, timestamp: Long): SignatureData? {
        val uploadData = JSONObject().apply {
            put("photo_id", photoId)
            put("filename", filename)
            put("timestamp", timestamp)
        }
        return signJsonData(uploadData, "upload")
    }

    /**
     * Sign push registration data with client private key
     */
    fun signPushRegistration(endpoint: String, distributorPackage: String?, timestamp: Long): SignatureData? {
        val pushData = JSONObject().apply {
            put("push_endpoint", endpoint)
            if (distributorPackage != null) {
                put("distributor_package", distributorPackage)
            }
            put("timestamp", timestamp)
        }
        return signJsonData(pushData, "push registration")
    }

    /**
     * Generic method to sign JSON data with client private key
     */
    private fun signJsonData(data: JSONObject, logPrefix: String): SignatureData? {
        try {
            // Get private key from Android Keystore
            val privateKeyEntry = keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.PrivateKeyEntry
                ?: run {
                    Log.e(TAG, "Private key not found in Keystore")
                    return null
                }

            val message = data.toString() // Compact JSON, no spaces
            Log.d(TAG, "📝 Signing $logPrefix message: $message")

            // Sign the message using ECDSA with SHA-256
            val signature = Signature.getInstance("SHA256withECDSA")
            signature.initSign(privateKeyEntry.privateKey)
            signature.update(message.toByteArray(Charsets.UTF_8))
            val signatureBytes = signature.sign()

            // Convert to base64 for transmission
            val signatureBase64 = Base64.encodeToString(signatureBytes, Base64.NO_WRAP)

            // Get the key ID for this signature
            val keyId = getKeyId()
            if (keyId == null) {
                Log.e(TAG, "Failed to get key ID for $logPrefix signature")
                return null
            }

            return SignatureData(signatureBase64, keyId)

        } catch (e: Exception) {
            Log.e(TAG, "Error signing $logPrefix data", e)
            return null
        }
    }

    /**
     * Get the stored key ID from SharedPreferences
     */
    fun getKeyId(): String? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_ID_PREF, null)
    }

    /**
     * Clear stored client keys (e.g., on logout or security incident)
     *
     * Removes client cryptographic material from both Android Keystore and SharedPreferences.
     * This is optional - keys can persist across login sessions for convenience.
     *
     * When to call:
     * - On explicit logout (user choice)
     * - On account deletion
     * - On security incident/key compromise
     *
     * Note: Clearing keys will require re-registration of public key on next login.
     * Consider the user experience trade-off between security and convenience.
     */
    fun clearStoredKeys(): Boolean {
        try {
            Log.d(TAG, "Clearing client keys from Keystore and SharedPreferences")

            // Remove key from Android Keystore
            if (keyStore.containsAlias(KEY_ALIAS)) {
                keyStore.deleteEntry(KEY_ALIAS)
            }

            // Clear metadata from SharedPreferences
            prefs.edit()
                .remove(KEY_ID_PREF)
                .remove(KEY_CREATED_PREF)
                .remove(PUBLIC_KEY_PEM_PREF)
                .apply()

            Log.d(TAG, "Client keys cleared successfully")
            return true

        } catch (e: Exception) {
            Log.e(TAG, "Error clearing client keys: ${e.message}", e)
            return false
        }
    }

    // Private helper methods

    private fun storeKeyMetadata(publicKey: PublicKey) {
        try {
            // Export public key to PEM format
            val publicKeyBytes = publicKey.encoded
            val publicKeyPem = formatAsPem(publicKeyBytes, "PUBLIC KEY")

            // Generate unique key ID
            val keyId = "key_" + UUID.randomUUID().toString().replace("-", "")
            val createdAt = Date().toInstant().toString()

            // Store in SharedPreferences
            prefs.edit()
                .putString(PUBLIC_KEY_PEM_PREF, publicKeyPem)
                .putString(KEY_ID_PREF, keyId)
                .putString(KEY_CREATED_PREF, createdAt)
                .apply()

            Log.d(TAG, "Key metadata stored successfully")

        } catch (e: Exception) {
            Log.e(TAG, "Error storing key metadata: ${e.message}", e)
            throw e
        }
    }

    private fun formatAsPem(keyBytes: ByteArray, type: String): String {
        val base64 = Base64.encodeToString(keyBytes, Base64.NO_WRAP)
        val formatted = base64.chunked(64).joinToString("\n")
        return "-----BEGIN $type-----\n$formatted\n-----END $type-----"
    }
}

/**
 * Data class for client public key information
 */
data class ClientKeyInfo(
    val publicKeyPem: String,
    val keyId: String,
    val createdAt: String
)

/**
 * Data class for signature data containing both signature and key ID
 */
data class SignatureData(
    val signature: String,
    val keyId: String
)

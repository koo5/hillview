/**
 * Client-Side Cryptographic Key Management
 *
 * This module implements a secure upload authorization scheme using client-side ECDSA signatures.
 * It prevents compromised workers from impersonating users by requiring cryptographic proof
 * that the client authorized each specific upload.
 *
 * SECURITY ARCHITECTURE:
 * =====================
 *
 * Problem: A compromised worker service could use valid user JWT tokens to upload
 * malicious content on behalf of legitimate users.
 *
 * Solution: Three-phase cryptographically secured upload process:
 *
 * Phase 1 - Upload Authorization (Client → API Server):
 *   - Client requests upload authorization with file metadata
 *   - API server creates pending photo record and returns upload JWT
 *   - Upload JWT contains: photo_id, user_id, client_public_key_id, expiry
 *
 * Phase 2 - Signed Upload (Client → Worker):
 *   - Client signs upload payload: {photo_id, filename, timestamp}
 *   - Client sends: upload_jwt + file + client_signature to worker
 *   - Worker verifies upload_jwt using API server's public key
 *   - Worker processes file (does NOT verify client signature)
 *
 * Phase 3 - Result Storage (Worker → API Server):
 *   - Worker sends processed results + client_signature to API
 *   - API server verifies client_signature using client's public key
 *   - Only saves results if client signature is valid
 *   - Signature retained in database for audit trail
 *
 * KEY MANAGEMENT:
 * ===============
 *
 * - ECDSA P-256 key pairs generated client-side using Web Crypto API
 * - Private key stays on client device (never leaves client)
 * - Public key registered with server on successful login
 * - Keys stored in localStorage alongside auth tokens
 * - Keys survive logout/login cycles for consistency
 *
 * BENEFITS:
 * =========
 *
 * ✅ Non-repudiation: Cryptographic proof of client intent
 * ✅ Tamper-proof: Worker cannot modify upload metadata
 * ✅ Time-limited: Upload authorizations expire
 * ✅ Audit trail: Signatures prove legitimate uploads
 * ✅ Zero-trust workers: Workers verify upload auth but not client signatures
 *
 * USAGE PATTERN:
 * ==============
 *
 * 1. On app startup: getOrCreateKeyPair() - ensures keys exist
 * 2. On login: getPublicKeyInfo() → register with server
 * 3. On upload: signUploadData() → create proof of authorization
 * 4. On logout: clearStoredKeys() → cleanup (optional)
 */

export interface ClientKeyPair {
    publicKey: CryptoKey;
    privateKey: CryptoKey;
}

export interface ClientKeyInfo {
    publicKeyPem: string;
    keyId: string;
    createdAt: string;
}

export class ClientCryptoManager {
    private readonly LOG_PREFIX = '🔐[CLIENT_CRYPTO]';
    private readonly STORAGE_KEYS = {
        PRIVATE_KEY: 'hillview_client_private_key',
        PUBLIC_KEY: 'hillview_client_public_key',
        KEY_ID: 'hillview_client_key_id',
        KEY_CREATED: 'hillview_client_key_created'
    };

    /**
     * Get or generate client ECDSA key pair
     *
     * This is the main entry point for key management. It ensures the client
     * always has a valid ECDSA key pair for signing upload requests.
     *
     * Flow:
     * 1. Try to load existing keys from localStorage
     * 2. If keys missing/corrupt, generate new P-256 ECDSA key pair
     * 3. Store new keys securely in localStorage
     *
     * Keys persist across browser sessions to maintain consistent identity.
     * If keys are lost, a new pair will be generated and the server will
     * need to be updated with the new public key on next login.
     */
    async getOrCreateKeyPair(): Promise<ClientKeyPair> {
        try {
            // Try to load existing keys from localStorage
            const existingKeys = await this.loadStoredKeys();
            if (existingKeys) {
                console.log(`${this.LOG_PREFIX} Loaded existing client keys`);
                return existingKeys;
            }

            // Generate new key pair
            console.log(`${this.LOG_PREFIX} Generating new client ECDSA key pair`);
            const keyPair = await this.generateKeyPair();

            // Store keys in localStorage
            await this.storeKeys(keyPair);

            console.log(`${this.LOG_PREFIX} New client key pair generated and stored`);
            return keyPair;

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error managing client keys:`, error);
            throw error;
        }
    }

    /**
     * Get client public key info for registration with server
     *
     * Called during login process to register the client's public key with the API server.
     * The server stores this public key and associates it with the user account.
     *
     * Returns:
     * - publicKeyPem: PEM-formatted public key for server storage
     * - keyId: Unique identifier for this key pair
     * - createdAt: Timestamp when key was first generated
     *
     * The server uses this information to:
     * 1. Store the public key in user_public_keys table
     * 2. Include keyId in upload authorization JWTs
     * 3. Verify client signatures during upload process
     */
    async getPublicKeyInfo(): Promise<ClientKeyInfo> {
        const keyPair = await this.getOrCreateKeyPair();

        // Export public key to PEM format
        const publicKeyBuffer = await crypto.subtle.exportKey('spki', keyPair.publicKey);
        const publicKeyPem = this.bufferToPem(publicKeyBuffer, 'PUBLIC KEY');

        // Get or generate key ID
        const keyId = localStorage.getItem(this.STORAGE_KEYS.KEY_ID) || this.generateKeyId();
        const createdAt = localStorage.getItem(this.STORAGE_KEYS.KEY_CREATED) || new Date().toISOString();

        return {
            publicKeyPem,
            keyId,
            createdAt
        };
    }

    /**
     * Sign upload data with client private key
     *
     * Creates a cryptographic signature proving the client authorized this specific upload.
     * This is the core security mechanism that prevents worker impersonation attacks.
     *
     * Process:
     * 1. Creates canonical JSON representation of upload data
     * 2. Signs the JSON string using client's ECDSA private key
     * 3. Returns base64-encoded signature for transmission
     *
     * The signature covers:
     * - photo_id: Links to specific upload authorization
     * - filename: Prevents file substitution attacks
     * - timestamp: Prevents replay attacks
     *
     * The API server will later verify this signature using the client's
     * registered public key before accepting processed results.
     *
     * @param data Upload metadata to sign
     * @returns Base64-encoded ECDSA signature
     */
    async signUploadData(data: {
        photo_id: string;
        filename: string;
        timestamp: number;
    }): Promise<string> {
        try {
            const keyPair = await this.getOrCreateKeyPair();

            // Create canonical string representation
            const message = JSON.stringify({
                photo_id: data.photo_id,
                filename: data.filename,
                timestamp: data.timestamp
            }, null, 0); // No spaces for consistency

            console.log(`${this.LOG_PREFIX} 📝 Signing message: ${message}`);

            // Sign the message
            const encoder = new TextEncoder();
            const messageBuffer = encoder.encode(message);

            const signatureBuffer = await crypto.subtle.sign(
                {
                    name: 'ECDSA',
                    hash: 'SHA-256'
                },
                keyPair.privateKey,
                messageBuffer
            );

			console.debug(`keyPair.privateKey: (${JSON.stringify(keyPair.privateKey)}), keyPair.publicKey: (${JSON.stringify(keyPair.publicKey)})`);


            // Convert to base64 for transmission
            const signatureBase64 = this.bufferToBase64(signatureBuffer);

            console.log(`${this.LOG_PREFIX} Signed upload data for photo ${data.photo_id}`);
			console.debug(`${this.LOG_PREFIX} Signature (base64): ${signatureBase64}`);
            return signatureBase64;

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error signing upload data:`, error);
            throw error;
        }
    }

    /**
     * Clear stored client keys (e.g., on logout)
     */
    clearStoredKeys(): void {
        try {
            Object.values(this.STORAGE_KEYS).forEach(key => {
                localStorage.removeItem(key);
            });
            console.log(`${this.LOG_PREFIX} Client keys cleared from storage`);
        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error clearing client keys:`, error);
        }
    }

    // Private methods

    private async generateKeyPair(): Promise<ClientKeyPair> {
        const keyPair = await crypto.subtle.generateKey(
            {
                name: 'ECDSA',
                namedCurve: 'P-256' // Same as backend SECP256R1
            },
            true, // extractable
            ['sign', 'verify']
        );

        return {
            publicKey: keyPair.publicKey,
            privateKey: keyPair.privateKey
        };
    }

    private async storeKeys(keyPair: ClientKeyPair): Promise<void> {
        try {
            // Export keys to JWK format for storage
            const privateKeyJwk = await crypto.subtle.exportKey('jwk', keyPair.privateKey);
            const publicKeyJwk = await crypto.subtle.exportKey('jwk', keyPair.publicKey);

            // Generate unique key ID
            const keyId = this.generateKeyId();
            const createdAt = new Date().toISOString();

            // Store in localStorage
            localStorage.setItem(this.STORAGE_KEYS.PRIVATE_KEY, JSON.stringify(privateKeyJwk));
            localStorage.setItem(this.STORAGE_KEYS.PUBLIC_KEY, JSON.stringify(publicKeyJwk));
            localStorage.setItem(this.STORAGE_KEYS.KEY_ID, keyId);
            localStorage.setItem(this.STORAGE_KEYS.KEY_CREATED, createdAt);

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error storing keys:`, error);
            throw error;
        }
    }

    private async loadStoredKeys(): Promise<ClientKeyPair | null> {
        try {
            const privateKeyJwkStr = localStorage.getItem(this.STORAGE_KEYS.PRIVATE_KEY);
            const publicKeyJwkStr = localStorage.getItem(this.STORAGE_KEYS.PUBLIC_KEY);

            if (!privateKeyJwkStr || !publicKeyJwkStr) {
                return null;
            }

            const privateKeyJwk = JSON.parse(privateKeyJwkStr);
            const publicKeyJwk = JSON.parse(publicKeyJwkStr);

            // Import keys from JWK
            const privateKey = await crypto.subtle.importKey(
                'jwk',
                privateKeyJwk,
                { name: 'ECDSA', namedCurve: 'P-256' },
                false,
                ['sign']
            );

            const publicKey = await crypto.subtle.importKey(
                'jwk',
                publicKeyJwk,
                { name: 'ECDSA', namedCurve: 'P-256' },
                true,
                ['verify']
            );

            return { publicKey, privateKey };

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error loading stored keys:`, error);
            // If loading fails, return null to trigger new key generation
            return null;
        }
    }

    private generateKeyId(): string {
        // Generate a random key ID for tracking
        return 'key_' + Array.from(crypto.getRandomValues(new Uint8Array(16)))
            .map(b => b.toString(16).padStart(2, '0'))
            .join('');
    }

    private bufferToBase64(buffer: ArrayBuffer): string {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

    private bufferToPem(buffer: ArrayBuffer, type: string): string {
        const base64 = this.bufferToBase64(buffer);
        const formatted = base64.match(/.{1,64}/g)?.join('\n') || base64;
        return `-----BEGIN ${type}-----\n${formatted}\n-----END ${type}-----`;
    }
}

// Global instance
export const clientCrypto = new ClientCryptoManager();

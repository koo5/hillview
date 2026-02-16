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
    public_key: CryptoKey;
    private_key: CryptoKey;
    key_id: string;
}

export interface ClientKeyInfo {
    public_key_pem: string;
    key_id: string;
    created_at: string;
}

export class ClientCryptoManager {
    private readonly LOG_PREFIX = '🔐[CLIENT_CRYPTO]';
    private readonly STORAGE_KEYS = {
        PRIVATE_KEY: 'hillview_client_private_key',
        PUBLIC_KEY: 'hillview_client_public_key',
        KEY_ID: 'hillview_client_key_id',
        KEY_CREATED: 'hillview_client_key_created'
    };
    private readonly DB_NAME = 'HillviewAuthDB';
    private readonly DB_VERSION = 1;
    private readonly KEYS_STORE = 'client_keys';
    private readonly KEY_ID = 'client_keys'; // Single record ID
    private db: IDBDatabase | null = null;
    private useIndexedDB: boolean = false;

    constructor() {
        // Detect if we're in a service worker context (no localStorage)
        this.useIndexedDB = typeof localStorage === 'undefined';
        if (this.useIndexedDB) {
            console.log(`${this.LOG_PREFIX} Using IndexedDB for storage (service worker context)`);
        }
    }

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
            // Sync from localStorage to IndexedDB if needed (one-time migration)
            if (this.useIndexedDB) {
                await this.initIndexedDB();
            }

            // Try to load existing keys
            const existingKeys = await this.loadStoredKeys();
            if (existingKeys) {
                console.log(`${this.LOG_PREFIX} Loaded existing client keys`);
                return existingKeys;
            }

            // Generate new key pair
            console.log(`${this.LOG_PREFIX} Generating new client ECDSA key pair`);
            const keyPair = await this.generateKeyPair();

            // Store keys
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
        const publicKeyBuffer = await crypto.subtle.exportKey('spki', keyPair.public_key);
        const publicKeyPem = this.bufferToPem(publicKeyBuffer, 'PUBLIC KEY');

        // Get stored metadata
        let keyId: string;
        let createdAt: string;

        if (this.useIndexedDB) {
            const storedData = await this.getStoredKeyDataFromIDB();
            keyId = storedData?.key_id || keyPair.key_id;
            createdAt = storedData?.created_at || new Date().toISOString();
        } else {
            keyId = localStorage.getItem(this.STORAGE_KEYS.KEY_ID) || this.generateKeyId();
            createdAt = localStorage.getItem(this.STORAGE_KEYS.KEY_CREATED) || new Date().toISOString();
        }

        return {
            public_key_pem: publicKeyPem,
            key_id: keyId,
            created_at: createdAt
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
     * 3. Returns base64-encoded signature and key ID for transmission
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
     * @returns Object containing base64-encoded ECDSA signature and key ID
     */
    async signUploadData(data: {
        photo_id: string;
        filename: string;
        timestamp: number;
    }): Promise<{ signature: string; keyId: string }> {
        try {
            const keyPair = await this.getOrCreateKeyPair();

            // Create canonical string representation
            const message = JSON.stringify([
                data.filename,
                data.photo_id,
                data.timestamp
            ], null, 0);

            console.log(`${this.LOG_PREFIX} 📝 Signing message: ${message}`);

            // Sign the message
            const encoder = new TextEncoder();
            const messageBuffer = encoder.encode(message);

            const signatureBuffer = await crypto.subtle.sign(
                {
                    name: 'ECDSA',
                    hash: 'SHA-256'
                },
                keyPair.private_key,
                messageBuffer
            );

			console.debug(`keyPair.privateKey: (${JSON.stringify(keyPair.private_key)}), keyPair.publicKey: (${JSON.stringify(keyPair.public_key)})`);


            // Convert to base64 for transmission
            const signatureBase64 = this.bufferToBase64(signatureBuffer);

            console.log(`${this.LOG_PREFIX} Signed upload data for photo ${data.photo_id} with key ${keyPair.key_id}`);
			console.debug(`${this.LOG_PREFIX} Signature (base64): ${signatureBase64}`);

            return {
                signature: signatureBase64,
                keyId: keyPair.key_id
            };

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error signing upload data:`, error);
            throw error;
        }
    }

    /**
     * Clear stored client keys (e.g., on logout)
     */
    async clearStoredKeys(): Promise<void> {
        try {
            if (this.useIndexedDB) {
                await this.initIndexedDB();
                const transaction = this.db!.transaction([this.KEYS_STORE], 'readwrite');
                const store = transaction.objectStore(this.KEYS_STORE);

                await new Promise<void>((resolve, reject) => {
                    const request = store.delete(this.KEY_ID);
                    request.onsuccess = () => resolve();
                    request.onerror = () => reject(request.error);
                });
            } else {
                Object.values(this.STORAGE_KEYS).forEach(key => {
                    localStorage.removeItem(key);
                });
            }
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

        const keyId = this.generateKeyId();

        return {
            public_key: keyPair.publicKey,
            private_key: keyPair.privateKey,
            key_id: keyId
        };
    }

    private async storeKeys(keyPair: ClientKeyPair, createdAt?: string): Promise<void> {
        try {
            // Export keys to JWK format for storage
            const privateKeyJwk = await crypto.subtle.exportKey('jwk', keyPair.private_key);
            const publicKeyJwk = await crypto.subtle.exportKey('jwk', keyPair.public_key);
            const timestamp = createdAt || new Date().toISOString();

            if (this.useIndexedDB) {
                await this.initIndexedDB();
                const transaction = this.db!.transaction([this.KEYS_STORE], 'readwrite');
                const store = transaction.objectStore(this.KEYS_STORE);

                const storedData = {
                    id: this.KEY_ID,
                    private_key_jwk: privateKeyJwk,
                    public_key_jwk: publicKeyJwk,
                    key_id: keyPair.key_id,
                    created_at: timestamp
                };

                await new Promise<void>((resolve, reject) => {
                    const request = store.put(storedData);
                    request.onsuccess = () => resolve();
                    request.onerror = () => reject(request.error);
                });
            } else {
                // Store in localStorage
                localStorage.setItem(this.STORAGE_KEYS.PRIVATE_KEY, JSON.stringify(privateKeyJwk));
                localStorage.setItem(this.STORAGE_KEYS.PUBLIC_KEY, JSON.stringify(publicKeyJwk));
                localStorage.setItem(this.STORAGE_KEYS.KEY_ID, keyPair.key_id);
                localStorage.setItem(this.STORAGE_KEYS.KEY_CREATED, timestamp);

                // Also store in IndexedDB for service worker access (if in browser context)
                try {
                    await this.mirrorToIndexedDB(privateKeyJwk, publicKeyJwk, keyPair.key_id, timestamp);
                } catch (e) {
                    // Non-critical - service worker will generate its own keys if needed
                    console.debug(`${this.LOG_PREFIX} Could not mirror to IndexedDB:`, e);
                }
            }

        } catch (error) {
            console.error(`${this.LOG_PREFIX} Error storing keys:`, error);
            throw error;
        }
    }

    private async loadStoredKeys(): Promise<ClientKeyPair | null> {
        try {
            if (this.useIndexedDB) {
                return await this.loadStoredKeysFromIDB();
            } else {
                const privateKeyJwkStr = localStorage.getItem(this.STORAGE_KEYS.PRIVATE_KEY);
                const publicKeyJwkStr = localStorage.getItem(this.STORAGE_KEYS.PUBLIC_KEY);
                const keyId = localStorage.getItem(this.STORAGE_KEYS.KEY_ID);

                if (!privateKeyJwkStr || !publicKeyJwkStr || !keyId) {
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

                return { public_key: publicKey, private_key: privateKey, key_id: keyId };
            }

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

    // IndexedDB methods
    private async initIndexedDB(): Promise<void> {
        if (this.db) return;

        this.db = await new Promise<IDBDatabase>((resolve, reject) => {
            const request = indexedDB.open(this.DB_NAME, this.DB_VERSION);

            request.onerror = () => reject(new Error('Failed to open IndexedDB'));
            request.onsuccess = () => resolve(request.result);

            request.onupgradeneeded = (event) => {
                const db = (event.target as IDBOpenDBRequest).result;
                if (!db.objectStoreNames.contains(this.KEYS_STORE)) {
                    db.createObjectStore(this.KEYS_STORE, { keyPath: 'id' });
                }
            };
        });
    }

    private async mirrorToIndexedDB(
        privateKeyJwk: JsonWebKey,
        publicKeyJwk: JsonWebKey,
        keyId: string,
        createdAt: string
    ): Promise<void> {
        try {
            await this.initIndexedDB();
            const transaction = this.db!.transaction([this.KEYS_STORE], 'readwrite');
            const store = transaction.objectStore(this.KEYS_STORE);

            const storedData = {
                id: this.KEY_ID,
                private_key_jwk: privateKeyJwk,
                public_key_jwk: publicKeyJwk,
                key_id: keyId,
                created_at: createdAt
            };

            await new Promise<void>((resolve, reject) => {
                const request = store.put(storedData);
                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        } catch (error) {
            // Non-critical error - service worker will generate its own keys if needed
            console.debug(`${this.LOG_PREFIX} Could not mirror to IndexedDB:`, error);
        }
    }

    private async loadStoredKeysFromIDB(): Promise<ClientKeyPair | null> {
        await this.initIndexedDB();

        const storedData = await this.getStoredKeyDataFromIDB();
        if (!storedData) {
            return null;
        }

        // Import keys from JWK
        const privateKey = await crypto.subtle.importKey(
            'jwk',
            storedData.private_key_jwk,
            { name: 'ECDSA', namedCurve: 'P-256' },
            false,
            ['sign']
        );

        const publicKey = await crypto.subtle.importKey(
            'jwk',
            storedData.public_key_jwk,
            { name: 'ECDSA', namedCurve: 'P-256' },
            true,
            ['verify']
        );

        return {
            public_key: publicKey,
            private_key: privateKey,
            key_id: storedData.key_id
        };
    }

    private async getStoredKeyDataFromIDB(): Promise<any> {
        await this.initIndexedDB();

        const transaction = this.db!.transaction([this.KEYS_STORE], 'readonly');
        const store = transaction.objectStore(this.KEYS_STORE);

        return new Promise((resolve, reject) => {
            const request = store.get(this.KEY_ID);
            request.onsuccess = () => resolve(request.result || null);
            request.onerror = () => reject(request.error);
        });
    }
}

// Global instance
export const clientCrypto = new ClientCryptoManager();

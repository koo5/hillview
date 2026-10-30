import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/clientCrypto', () => ({
    clientCrypto: {
        getPublicKeyInfo: vi.fn().mockResolvedValue({
            key_id: 'key-1',
            public_key_pem: '-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----',
            created_at: '2026-01-01T00:00:00.000Z',
        }),
        signUploadData: vi.fn(),
    },
}));
vi.mock('$lib/config', () => ({ backendUrl: 'http://api.test/api' }));
vi.mock('$lib/browser/photoStorage', () => ({ browserPhotoStorage: {} }));

import {
    requestUploadAuthorization,
    NonRetryableUploadError,
    type AuthFetch,
    type UploadAuthorizationRequest,
} from '$lib/uploadProtocol';

const AUTH_REQUEST: UploadAuthorizationRequest = {
    filename: 'a.jpg',
    file_size: 10,
    content_type: 'image/jpeg',
    file_md5: 'deadbeef',
    client_key_id: 'key-1',
    is_public: true,
};

function response(status: number, body: unknown): Response {
    return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
}

const keyNotRegistered = response(409, {
    detail: {
        error_code: 'client_key_not_registered',
        message: "Client public key 'key-1' not found or inactive. Please ensure the key is registered and active.",
    },
});
const authorized = response(200, { photo_id: 'p1', upload_jwt: 'jwt', worker_url: 'http://w', upload_authorized_at: 1 });

beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'log').mockImplementation(() => {});
});

describe('requestUploadAuthorization key self-heal', () => {
    it('re-registers the key on 409 client_key_not_registered and retries once', async () => {
        const authFetch = vi.fn<AuthFetch>()
            .mockResolvedValueOnce(keyNotRegistered)
            .mockResolvedValueOnce(response(200, { message: 'registered' }))
            .mockResolvedValueOnce(authorized);

        const result = await requestUploadAuthorization(authFetch, AUTH_REQUEST);

        expect(result.photo_id).toBe('p1');
        const urls = authFetch.mock.calls.map(([url]) => url);
        expect(urls).toEqual([
            'http://api.test/api/photos/authorize-upload',
            'http://api.test/api/auth/register-client-key',
            'http://api.test/api/photos/authorize-upload',
        ]);
        const registerBody = JSON.parse(authFetch.mock.calls[1][1].body as string);
        expect(registerBody).toMatchObject({ key_id: 'key-1', created_at: '2026-01-01T00:00:00.000Z' });
        expect(registerBody.public_key_pem).toContain('BEGIN PUBLIC KEY');
    });

    it('treats 409 from register-client-key (already registered) as success', async () => {
        const authFetch = vi.fn<AuthFetch>()
            .mockResolvedValueOnce(keyNotRegistered)
            .mockResolvedValueOnce(response(409, { detail: 'Key already registered' }))
            .mockResolvedValueOnce(authorized);

        await expect(requestUploadAuthorization(authFetch, AUTH_REQUEST)).resolves.toMatchObject({ photo_id: 'p1' });
    });

    it('heals only once: a second 409 is a non-retryable failure with the server message', async () => {
        const authFetch = vi.fn<AuthFetch>()
            .mockResolvedValueOnce(keyNotRegistered)
            .mockResolvedValueOnce(response(200, {}))
            .mockResolvedValueOnce(keyNotRegistered);

        await expect(requestUploadAuthorization(authFetch, AUTH_REQUEST)).rejects.toThrow(
            new NonRetryableUploadError("Client public key 'key-1' not found or inactive. Please ensure the key is registered and active.")
        );
        expect(authFetch).toHaveBeenCalledTimes(3);
    });

    it('does not register on a 409 that is not about the key', async () => {
        const authFetch = vi.fn<AuthFetch>().mockResolvedValueOnce(response(409, { detail: 'Some other conflict' }));

        await expect(requestUploadAuthorization(authFetch, AUTH_REQUEST)).rejects.toThrow('Some other conflict');
        expect(authFetch).toHaveBeenCalledTimes(1);
    });

    it('reports an object detail by its message, not as [object Object]', async () => {
        const authFetch = vi.fn<AuthFetch>().mockResolvedValueOnce(
            response(400, { detail: { error_code: 'something_else', message: 'Explained here' } })
        );

        await expect(requestUploadAuthorization(authFetch, AUTH_REQUEST)).rejects.toThrow('Explained here');
    });

    it('fails without retry when the registration itself is rejected', async () => {
        const authFetch = vi.fn<AuthFetch>()
            .mockResolvedValueOnce(keyNotRegistered)
            .mockResolvedValueOnce(response(422, { detail: 'Invalid PEM' }));

        await expect(requestUploadAuthorization(authFetch, AUTH_REQUEST)).rejects.toThrow(
            'Client key registration failed: Invalid PEM'
        );
        expect(authFetch).toHaveBeenCalledTimes(2);
    });
});

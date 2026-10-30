import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { convertStreamPhoto, SseDataParser, StreamSourceLoader } from './StreamSourceLoader';
import { MockSseStream, sseResponse, errorResponse } from '../../tests/mocks/sseFetch';

const BOUNDS = { top_left: { lat: 51, lng: 14 }, bottom_right: { lat: 50, lng: 15 } };
const SOURCE = { id: 'hillview', type: 'stream', url: 'https://example.com/api/hillview' };

describe('StreamSourceLoader over fetch', () => {
    let streams: MockSseStream[];
    let fetchMock: ReturnType<typeof vi.fn>;

    /** Each call answers with the next scripted response; a stream is opened by default. */
    function scriptFetch(...answers: Array<'stream' | Response | Error>): void {
        fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
            const answer = answers.length > 0 ? answers.shift()! : 'stream';
            if (answer instanceof Error) throw answer;
            const stream = new MockSseStream(String(input), init);
            streams.push(stream);
            return answer === 'stream' ? sseResponse(stream) : answer;
        });
    }

    function makeLoader(token: string | null = null, options = {}) {
        const callbacks = {
            enqueueMessage: vi.fn(),
            getValidToken: vi.fn(async (_force?: boolean) => token),
            onError: vi.fn()
        };
        const loader = new StreamSourceLoader(SOURCE, callbacks, options);
        return { loader, callbacks };
    }

    beforeEach(() => {
        streams = [];
        fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);
        scriptFetch();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('sends the analysis and properties envelope to the Hillview stream', async () => {
        const queryOptionsJson = JSON.stringify({
            analysis: { time_of_day: 'day' }, properties: { min_width: 3000 }
        });
        const { loader } = makeLoader(null, { queryOptionsJson });
        try {
            const completion = loader.start(BOUNDS);
            await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
            const url = new URL(fetchMock.mock.calls[0][0]);
            expect(url.searchParams.get('filters')).toBe(queryOptionsJson);
            loader.cancel();
            await completion;
        } finally {
            loader.cancel();
        }
    });

    it('sends the token in an Authorization header, never in the URL', async () => {
        const { loader, callbacks } = makeLoader('tok-123');
        const completion = loader.start(BOUNDS);
        await vi.waitFor(() => expect(streams).toHaveLength(1));
        const [stream] = streams;
        expect(stream.headers['authorization']).toBe('Bearer tok-123');
        expect(new URL(stream.url).searchParams.has('token')).toBe(false);

        stream.emit({ type: 'photos', photos: [{ id: 'p1', coord: { lat: 50.5, lng: 14.5 }, bearing: 10 }] });
        stream.emit({ type: 'stream_complete' });
        await completion;

        const types = callbacks.enqueueMessage.mock.calls.map(([m]) => m.type);
        expect(types).toEqual(['photosAdded', 'streamComplete']);
        expect(callbacks.onError).not.toHaveBeenCalled();
        expect(stream.close).toHaveBeenCalledOnce(); // the client ends the request after stream_complete
    });

    it('sends no Authorization header when signed out', async () => {
        const { loader } = makeLoader(null);
        const completion = loader.start(BOUNDS);
        await vi.waitFor(() => expect(streams).toHaveLength(1));
        expect(streams[0].headers['authorization']).toBeUndefined();
        streams[0].emit({ type: 'stream_complete' });
        await completion;
    });

    it('retries a 401 once, forcing a token refresh', async () => {
        scriptFetch(errorResponse(401, 'Invalid authentication token'), 'stream');
        const { loader, callbacks } = makeLoader('tok');
        const completion = loader.start(BOUNDS);

        await vi.waitFor(() => expect(streams).toHaveLength(2));
        expect(callbacks.getValidToken.mock.calls.map(([force]) => force)).toEqual([false, true]);
        streams[1].emit({ type: 'stream_complete' });
        await completion;
        expect(callbacks.onError).not.toHaveBeenCalled();
    });

    it('retries a network failure once without forcing a refresh', async () => {
        scriptFetch(new TypeError('Failed to fetch'), 'stream');
        const { loader, callbacks } = makeLoader('tok');
        const completion = loader.start(BOUNDS);

        await vi.waitFor(() => expect(streams).toHaveLength(1));
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(callbacks.getValidToken.mock.calls.map(([force]) => force)).toEqual([false, false]);
        streams[0].emit({ type: 'stream_complete' });
        await completion;
    });

    it('does not retry a request the server rejected (4xx other than 401)', async () => {
        scriptFetch(errorResponse(422, 'bad bounds'));
        const { loader, callbacks } = makeLoader('tok');
        await loader.start(BOUNDS);

        expect(fetchMock).toHaveBeenCalledOnce();
        expect(callbacks.onError).toHaveBeenCalledOnce();
        expect(callbacks.onError.mock.calls[0][0].message).toContain('HTTP 422');
    });

    it('gives up after one retry when the 401 persists', async () => {
        scriptFetch(errorResponse(401), errorResponse(401));
        const { loader, callbacks } = makeLoader('tok');
        await loader.start(BOUNDS);

        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(callbacks.onError).toHaveBeenCalledOnce();
    });

    it('a stream that breaks after opening fails without a retry', async () => {
        const { loader, callbacks } = makeLoader('tok');
        const completion = loader.start(BOUNDS);
        await vi.waitFor(() => expect(streams).toHaveLength(1));

        streams[0].emit({ type: 'photos', photos: [] });
        streams[0].fail();
        await completion;

        expect(fetchMock).toHaveBeenCalledOnce();
        expect(callbacks.onError).toHaveBeenCalledOnce();
        expect(callbacks.onError.mock.calls[0][0].message).toContain('connection lost');
    });

    it('a body that ends without stream_complete is a failure', async () => {
        const { loader, callbacks } = makeLoader('tok');
        const completion = loader.start(BOUNDS);
        await vi.waitFor(() => expect(streams).toHaveLength(1));

        streams[0].end();
        await completion;
        expect(callbacks.onError).toHaveBeenCalledOnce();
        expect(callbacks.onError.mock.calls[0][0].message).toContain('ended before completion');
    });

    it('an error message from the server ends the stream and reports it', async () => {
        const { loader, callbacks } = makeLoader('tok');
        const completion = loader.start(BOUNDS);
        await vi.waitFor(() => expect(streams).toHaveLength(1));

        // Everything after the error message in the same chunk is ignored.
        streams[0].emitRaw('data: {"type":"error","message":"boom"}\n\ndata: {"type":"photos","photos":[{"id":"late"}]}\n\n');
        await completion;
        expect(callbacks.onError).toHaveBeenCalledOnce();
        expect(callbacks.onError.mock.calls[0][0].message).toBe('boom');
        expect(callbacks.enqueueMessage).not.toHaveBeenCalled();
        expect(streams[0].close).toHaveBeenCalledOnce();
    });

    it('cancel ends the request and resolves start()', async () => {
        const { loader, callbacks } = makeLoader('tok');
        const completion = loader.start(BOUNDS);
        await vi.waitFor(() => expect(streams).toHaveLength(1));

        loader.cancel();
        await completion;
        expect(streams[0].close).toHaveBeenCalled();
        expect(callbacks.onError).not.toHaveBeenCalled();
    });

    it('the watchdog ends a stream that goes silent', async () => {
        const { loader, callbacks } = makeLoader('tok', { streamInactivityTimeoutMs: 50 });
        const completion = loader.start(BOUNDS);
        await vi.waitFor(() => expect(streams).toHaveLength(1));

        await completion;
        expect(streams[0].close).toHaveBeenCalled();
        expect(callbacks.onError.mock.calls[0][0].message).toContain('timed out');
    });
});

describe('SseDataParser', () => {
    function parse(...chunks: string[]): string[] {
        const out: string[] = [];
        const parser = new SseDataParser((data) => out.push(data));
        for (const chunk of chunks) parser.push(chunk);
        return out;
    }

    it('dispatches each event on its blank line', () => {
        expect(parse('data: {"a":1}\n\ndata: {"b":2}\n\n')).toEqual(['{"a":1}', '{"b":2}']);
    });

    it('reassembles an event split anywhere across chunks', () => {
        expect(parse('da', 'ta: {"a"', ':1}\n', '\n')).toEqual(['{"a":1}']);
    });

    it('accepts CRLF and lone CR line endings, including a CRLF split across chunks', () => {
        expect(parse('data: x\r\n\r\n')).toEqual(['x']);
        expect(parse('data: y\r\r')).toEqual(['y']);
        expect(parse('data: z\r', '\n\r', '\n')).toEqual(['z']);
    });

    it('joins multi-line data with newlines and strips one leading space only', () => {
        expect(parse('data: one\ndata:  two\ndata:three\n\n')).toEqual(['one\n two\nthree']);
    });

    it('ignores comments, id and retry, and skips named events', () => {
        expect(parse(': keepalive\n\nid: 7\nretry: 1000\ndata: kept\n\nevent: progress\ndata: skipped\n\n')).toEqual(['kept']);
    });

    it('drops an unterminated final event', () => {
        expect(parse('data: done\n\ndata: half')).toEqual(['done']);
    });
});


describe('convertStreamPhoto', () => {
    const sampleSource = { id: 'hillview', type: 'stream' };

    const basePhoto = {
        id: 'photo-123',
        geometry: { coordinates: [14.5, 50.1] },
        compass_angle: 90,
        thumb_1024_url: 'https://example.com/thumb.jpg',
        filename: 'test.jpg',
    };

    it('flags a photo whose heading was not recorded, keeping bearing 0 on the wire', () => {
        const { compass_angle, ...noHeading } = basePhoto;
        const result = convertStreamPhoto(noHeading, sampleSource);
        expect(result.bearing).toBe(0);
        expect(result.has_bearing).toBe(false);
    });

    it('a heading of exactly 0 is a heading, not "unknown"', () => {
        const result = convertStreamPhoto({ ...basePhoto, compass_angle: 0 }, sampleSource);
        expect(result.bearing).toBe(0);
        expect(result.has_bearing).toBeUndefined();
    });

    it('preserves license field when present in response', () => {
        const photo = { ...basePhoto, license: 'ccbysa4+osm' };
        const result = convertStreamPhoto(photo, sampleSource);
        expect((result as any).license).toBe('ccbysa4+osm');
    });

    it('preserves arr license for seed content', () => {
        const photo = { ...basePhoto, license: 'arr' };
        const result = convertStreamPhoto(photo, sampleSource);
        expect((result as any).license).toBe('arr');
    });

    it('does not set license when backend omits the field', () => {
        const result = convertStreamPhoto(basePhoto, sampleSource);
        expect((result as any).license).toBeUndefined();
    });

    it('copies creator info when present (Mapillary)', () => {
        const photo = { ...basePhoto, creator: { id: 'user-1', username: 'alice' } };
        const result = convertStreamPhoto(photo, sampleSource);
        expect((result as any).creator).toEqual({ id: 'user-1', username: 'alice' });
    });

    it('maps is_pano to equirectangular projection (Mapillary 360°)', () => {
        const photo = { ...basePhoto, is_pano: true };
        expect((convertStreamPhoto(photo, sampleSource) as any).projection).toBe('equirectangular');
    });

    it('does not set projection for flat photos', () => {
        const photo = { ...basePhoto, is_pano: false };
        expect((convertStreamPhoto(photo, sampleSource) as any).projection).toBeUndefined();
    });

    it('exposes thumb_original_url as sizes.full (Mapillary full-res)', () => {
        const photo = { ...basePhoto, thumb_original_url: 'https://example.com/original.jpg' };
        const result = convertStreamPhoto(photo, sampleSource) as any;
        expect(result.sizes?.full?.url).toBe('https://example.com/original.jpg');
        expect(result.sizes?.['1024']?.url).toBe('https://example.com/thumb.jpg');
    });

    it('omits sizes.full when no original url is present', () => {
        const result = convertStreamPhoto(basePhoto, sampleSource) as any;
        expect(result.sizes?.full).toBeUndefined();
        expect(result.sizes?.['1024']?.url).toBe('https://example.com/thumb.jpg');
    });

    it('builds uid from source.id + photo.id', () => {
        const result = convertStreamPhoto(basePhoto, sampleSource);
        expect(result.uid).toBe('hillview-photo-123');
    });

    it('falls back through bearing candidates', () => {
        const photoWithComputed = { ...basePhoto, computed_compass_angle: 45, bearing: 180 };
        expect(convertStreamPhoto(photoWithComputed, sampleSource).bearing).toBe(45);

        const photoWithCompass = { ...basePhoto, compass_angle: 135, bearing: 180 };
        expect(convertStreamPhoto(photoWithCompass, sampleSource).bearing).toBe(135);

        const photoWithOnlyBearing = { ...basePhoto, compass_angle: undefined, bearing: 180 };
        expect(convertStreamPhoto(photoWithOnlyBearing, sampleSource).bearing).toBe(180);
    });
});

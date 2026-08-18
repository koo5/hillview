import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	loadOverlayDepth,
	overlayDepthReady,
	releaseOverlayDepth
} from './terrainOverlayApi';

const URL_A = 'https://pics.example/terrain/aaa.depth.bin.gz';
const URL_B = 'https://pics.example/terrain/bbb.depth.bin.gz';

function depthResponse(values: number[]) {
	return {
		ok: true,
		arrayBuffer: async () => Uint16Array.from(values).buffer
	} as unknown as Response;
}

describe('loadOverlayDepth', () => {
	beforeEach(() => {
		releaseOverlayDepth();
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		releaseOverlayDepth();
	});

	it('decodes the buffer as little-endian uint16', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => depthResponse([0, 1234, 65535]))
		);
		const d = await loadOverlayDepth(URL_A);
		expect(Array.from(d)).toEqual([0, 1234, 65535]);
	});

	it('serves the second request from cache', async () => {
		const fetchMock = vi.fn(async () => depthResponse([7, 8]));
		vi.stubGlobal('fetch', fetchMock);
		await loadOverlayDepth(URL_A);
		await loadOverlayDepth(URL_A);
		expect(fetchMock).toHaveBeenCalledTimes(1);
	});

	it('shares one request between concurrent callers', async () => {
		// a double-click must not start two multi-megabyte downloads
		const fetchMock = vi.fn(async () => depthResponse([1, 2, 3]));
		vi.stubGlobal('fetch', fetchMock);
		const [a, b] = await Promise.all([loadOverlayDepth(URL_A), loadOverlayDepth(URL_A)]);
		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(a).toBe(b);
	});

	it('refetches when the photo points at a different buffer', async () => {
		const fetchMock = vi.fn(async () => depthResponse([1]));
		vi.stubGlobal('fetch', fetchMock);
		await loadOverlayDepth(URL_A);
		await loadOverlayDepth(URL_B);
		expect(fetchMock).toHaveBeenCalledTimes(2);
		expect(overlayDepthReady(URL_B)).toBe(true);
		// only one buffer is held at a time — they are megabytes each
		expect(overlayDepthReady(URL_A)).toBe(false);
	});

	it('reports readiness so the UI can tell a click from a download', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => depthResponse([1]))
		);
		expect(overlayDepthReady(URL_A)).toBe(false);
		await loadOverlayDepth(URL_A);
		expect(overlayDepthReady(URL_A)).toBe(true);
		expect(overlayDepthReady(undefined)).toBe(false);
	});

	it('releases the buffer on request', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => depthResponse([1]))
		);
		await loadOverlayDepth(URL_A);
		releaseOverlayDepth();
		expect(overlayDepthReady(URL_A)).toBe(false);
	});

	it('rejects a buffer that does not match the overlay grid', async () => {
		// a truncated download (or one served without Content-Encoding: gzip)
		// reads past the end as `undefined`, which passes the `!== 0` sky test
		// and yields a confident marker reading "NaN, NaN · NaN km"
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => depthResponse([1, 2, 3]))
		);
		await expect(loadOverlayDepth(URL_A, 4096)).rejects.toThrow(/3 samples/);
		expect(overlayDepthReady(URL_A)).toBe(false);
	});

	it('accepts a buffer of the declared size', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => depthResponse([1, 2, 3]))
		);
		expect((await loadOverlayDepth(URL_A, 3)).length).toBe(3);
	});

	it('does not let an in-flight load resurrect a released buffer', async () => {
		// the user clicks, then closes the viewer before the download lands:
		// onDestroy releases, and the late response must not re-hold megabytes
		let resolveFetch: (r: Response) => void;
		vi.stubGlobal(
			'fetch',
			vi.fn(() => new Promise<Response>((r) => (resolveFetch = r)))
		);
		const p = loadOverlayDepth(URL_A);
		releaseOverlayDepth();
		resolveFetch!(depthResponse([1, 2]));
		await p;
		expect(overlayDepthReady(URL_A)).toBe(false);
	});

	it('does not cache a failed fetch', async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({ ok: false, status: 502 } as Response)
			.mockResolvedValueOnce(depthResponse([5]));
		vi.stubGlobal('fetch', fetchMock);
		await expect(loadOverlayDepth(URL_A)).rejects.toThrow('502');
		// a transient pool hiccup must not poison click-back for the session
		expect(Array.from(await loadOverlayDepth(URL_A))).toEqual([5]);
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});
});

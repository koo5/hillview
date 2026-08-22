import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseDepthBlob } from '$terrain/overlayFit';
import {
	inflateIfGzip,
	loadOverlayDepth,
	overlayDepthReady,
	releaseOverlayDepth
} from './terrainOverlayApi';

const URL_A = 'https://pics.example/terrain/aaa.depth.bin.gz';
const URL_B = 'https://pics.example/terrain/bbb.depth.bin.gz';

/** an HVD1 container around `values`, laid out as width×height (default 1 row) */
function depthBlob(values: number[], width = values.length, height = 1): ArrayBuffer {
	const buf = new ArrayBuffer(16 + values.length * 2);
	const dv = new DataView(buf);
	for (const [i, c] of [...'HVD1'].entries()) dv.setUint8(i, c.charCodeAt(0));
	dv.setUint16(4, 1, true); // version
	dv.setUint16(6, 16, true); // header bytes
	dv.setUint32(8, width, true);
	dv.setUint32(12, height, true);
	new Uint16Array(buf, 16).set(values);
	return buf;
}

function depthResponse(values: number[], width?: number, height?: number) {
	return { ok: true, arrayBuffer: async () => depthBlob(values, width, height) } as unknown as Response;
}

/** bare little-endian samples: what a truncated or foreign download looks like */
function headerlessResponse(values: number[]) {
	return { ok: true, arrayBuffer: async () => Uint16Array.from(values).buffer } as unknown as Response;
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
		// a truncated download reads past the end as `undefined`, which passes
		// the `!== 0` sky test and yields a confident marker reading
		// "NaN, NaN · NaN km" — the container's declared grid catches it
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => depthResponse([1, 2, 3]))
		);
		await expect(loadOverlayDepth(URL_A, { width: 64, height: 64 })).rejects.toThrow(/3×1/);
		expect(overlayDepthReady(URL_A)).toBe(false);
	});

	it('accepts a container whose grid matches the overlay', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => depthResponse([1, 2, 3, 4], 2, 2)));
		expect((await loadOverlayDepth(URL_A, { width: 2, height: 2 })).length).toBe(4);
	});

	it('refuses a headerless blob — there is no legacy form', async () => {
		vi.stubGlobal('fetch', vi.fn(async () => headerlessResponse([1, 2, 3, 4])));
		await expect(loadOverlayDepth(URL_A, { width: 2, height: 2 })).rejects.toThrow(/no HVD1 header/);
		expect(overlayDepthReady(URL_A)).toBe(false);
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


describe('inflateIfGzip', () => {
	it('a container can never be mistaken for gzip', async () => {
		// the collision the container removes: a BARE buffer whose first sample
		// is 0x8B1F is terrain at 142.46 km and reads as gzip's 1f 8b. Wrapped,
		// the same samples start with "HVD1" and the question cannot arise.
		const bare = new Uint16Array([0x8b1f, 0x0008, 7, 8]).buffer as ArrayBuffer;
		expect(new Uint8Array(bare).subarray(0, 3)).toEqual(new Uint8Array([0x1f, 0x8b, 0x08]));
		const wrapped = depthBlob([0x8b1f, 0x0008, 7, 8], 2, 2);
		expect(await inflateIfGzip(wrapped)).toBe(wrapped); // untouched
		expect(Array.from(parseDepthBlob(wrapped))).toEqual([0x8b1f, 0x0008, 7, 8]);
	});

	it('needs the deflate byte too, so 1f 8b alone is not enough', async () => {
		const notGzip = new Uint8Array([0x1f, 0x8b, 0x99, 0x00]).buffer as ArrayBuffer;
		expect(await inflateIfGzip(notGzip)).toBe(notGzip);
	});

	it('inflates gzip bytes and leaves raw samples alone', async () => {
		const { gzipSync } = await import('node:zlib');
		const raw = new Uint16Array([0, 1, 2, 65535, 4]);
		const gz = gzipSync(Buffer.from(raw.buffer));
		const gzBuf = new Uint8Array(gz).buffer as ArrayBuffer; // a fresh, plain ArrayBuffer copy
		const out = new Uint16Array(await inflateIfGzip(gzBuf));
		expect(Array.from(out)).toEqual([0, 1, 2, 65535, 4]);
		const same = await inflateIfGzip(raw.buffer);
		expect(new Uint16Array(same)).toEqual(raw);
	});
});

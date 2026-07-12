<script lang="ts">
	import { onDestroy } from 'svelte';
	import QRCode from 'qrcode';
	import { TAURI } from '$lib/tauri';
	import { invoke } from '@tauri-apps/api/core';

	// Records a clock-calibration video: the rear camera films the external
	// camera's date/time settings screen while every composited frame gets a
	// QR code of the phone's UTC time burned in. The file's container
	// timestamps are irrelevant by design — each frame carries its own real
	// time, so the pipeline (video_time_correction.py in the pics repo) only
	// trusts pixels. Frames are stamped with rVFC captureTime when the
	// WebView provides it (removes most of the camera-pipeline latency);
	// otherwise draw time is used and the sidecar says so.

	type Phase = 'idle' | 'starting' | 'recording' | 'saving' | 'done' | 'error';

	let phase: Phase = 'idle';
	let errorMsg = '';
	let savedPath = '';
	let elapsedS = 0;
	let framesDrawn = 0;

	let canvas: HTMLCanvasElement;
	let video: HTMLVideoElement;

	let stream: MediaStream | null = null;
	let canvasStream: MediaStream | null = null;
	let recorder: MediaRecorder | null = null;
	let rvfcHandle = 0;
	let rafId = 0;
	let usingRvfc = false;
	let rvfcStalled = false;
	let lastFrameAt = 0;
	let elapsedTimer: ReturnType<typeof setInterval> | null = null;
	let wakeLock: any = null;

	// Chunks are shipped to the plugin strictly in capture order through a
	// promise chain; a failed write poisons the chain so we stop recording
	// instead of silently saving a video with holes.
	let chunkChain: Promise<void> = Promise.resolve();
	let chunkError: string | null = null;
	let webChunks: Blob[] = [];
	let downloadVideoUrl = '';
	let downloadSidecarUrl = '';
	let downloadBasename = '';

	let mimeType = '';
	let startedAtMs = 0;
	let captureTimeFrames = 0;
	let latencySumMs = 0;
	let latencyMaxMs = 0;
	let panelRect = { x: 0, y: 0, w: 0, h: 0 };

	const MIME_CANDIDATES = [
		'video/webm;codecs=vp9',
		'video/webm;codecs=vp8',
		'video/webm',
		'video/mp4'
	];

	function extForMime(mime: string): string {
		return mime.startsWith('video/mp4') ? 'mp4' : 'webm';
	}

	// Synchronous QR render (QRCode.create, no canvas round-trip) so the
	// frame pixels and the stamp they encode are composited atomically
	// within one frame callback.
	function drawQrPanel(ctx: CanvasRenderingContext2D, stampMs: number, w: number, h: number) {
		const qr = QRCode.create(String(stampMs), { errorCorrectionLevel: 'M' });
		const nModules = qr.modules.size;
		const quiet = 2; // quiet-zone modules on each side
		const qrSize = Math.round(Math.min(w, h) * 0.3);
		const moduleSize = Math.floor(qrSize / (nModules + 2 * quiet));
		const qrPx = moduleSize * (nModules + 2 * quiet);
		const pad = moduleSize;
		const fontPx = Math.max(12, Math.floor(qrPx / 9));
		const panelW = qrPx + 2 * pad;
		const panelH = qrPx + fontPx + 3 * pad;
		const px = 16;
		const py = 16;
		panelRect = { x: px, y: py, w: panelW, h: panelH };

		ctx.fillStyle = '#ffffff';
		ctx.fillRect(px, py, panelW, panelH);
		ctx.fillStyle = '#000000';
		const ox = px + pad + quiet * moduleSize;
		const oy = py + pad + quiet * moduleSize;
		for (let r = 0; r < nModules; r++) {
			for (let c = 0; c < nModules; c++) {
				if (qr.modules.get(r, c)) {
					ctx.fillRect(ox + c * moduleSize, oy + r * moduleSize, moduleSize, moduleSize);
				}
			}
		}
		// Human-readable fallback: the raw ms number only — deliberately no
		// HH:MM:SS rendering, so the pipeline's clock-digit OCR can never
		// mistake our overlay for the camera's clock.
		ctx.font = `bold ${fontPx}px monospace`;
		ctx.textBaseline = 'top';
		ctx.fillText(String(stampMs), px + pad, py + qrPx + 2 * pad);
	}

	function drawFrame(nowPerf: number, metadata?: any) {
		if (phase !== 'recording' && phase !== 'starting') return;
		const ctx = canvas.getContext('2d')!;
		let stampMs: number;
		if (metadata && typeof metadata.captureTime === 'number') {
			// captureTime is on the performance timeline; anchor to the
			// current Date.now() so NTP steps during the session can't skew
			// the stamp.
			const latency = nowPerf - metadata.captureTime;
			stampMs = Math.round(Date.now() - latency);
			captureTimeFrames++;
			latencySumMs += latency;
			if (latency > latencyMaxMs) latencyMaxMs = latency;
		} else {
			stampMs = Date.now();
		}
		ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
		drawQrPanel(ctx, stampMs, canvas.width, canvas.height);
		framesDrawn++;
		lastFrameAt = performance.now();
	}

	function scheduleRvfc() {
		rvfcHandle = (video as any).requestVideoFrameCallback((now: number, metadata: any) => {
			drawFrame(now, metadata);
			if (phase === 'recording' || phase === 'starting') scheduleRvfc();
		});
	}

	function scheduleRaf() {
		rafId = requestAnimationFrame((now) => {
			drawFrame(now);
			if (phase === 'recording' || phase === 'starting') scheduleRaf();
		});
	}

	function startDrawLoop() {
		lastFrameAt = performance.now();
		if ('requestVideoFrameCallback' in HTMLVideoElement.prototype) {
			usingRvfc = true;
			scheduleRvfc();
		} else {
			usingRvfc = false;
			scheduleRaf();
		}
	}

	function stopDrawLoop() {
		if (usingRvfc && rvfcHandle && (video as any)?.cancelVideoFrameCallback) {
			(video as any).cancelVideoFrameCallback(rvfcHandle);
		}
		if (rafId) cancelAnimationFrame(rafId);
		rvfcHandle = 0;
		rafId = 0;
	}

	async function blobToBase64(blob: Blob): Promise<string> {
		const dataUrl: string = await new Promise((resolve, reject) => {
			const reader = new FileReader();
			reader.onload = () => resolve(reader.result as string);
			reader.onerror = () => reject(reader.error);
			reader.readAsDataURL(blob);
		});
		return dataUrl.substring(dataUrl.indexOf(',') + 1);
	}

	function enqueueChunk(blob: Blob) {
		if (blob.size === 0) return;
		chunkChain = chunkChain.then(async () => {
			if (chunkError) return;
			if (TAURI) {
				const data = await blobToBase64(blob);
				const res: any = await invoke('plugin:hillview|cmd', {
					command: 'clock_video_chunk',
					params: { data }
				});
				if (res && res.error) throw new Error(res.error);
			} else {
				webChunks.push(blob);
			}
		}).catch((e) => {
			console.error('🎬 clock video chunk write failed:', e);
			chunkError = e?.message || String(e);
		});
	}

	function buildSidecar(endedAtMs: number) {
		const track = stream?.getVideoTracks?.()[0];
		return {
			kind: 'hillview_clock_video',
			version: 1,
			started_at_ms: startedAtMs,
			ended_at_ms: endedAtMs,
			video: {
				width: canvas.width,
				height: canvas.height,
				mime: mimeType,
				fps_target: 30,
				track_settings: track ? track.getSettings() : null
			},
			qr: {
				format: 'unix_ms',
				error_correction: 'M',
				// Composited overlay is at a FIXED canvas position — the
				// pipeline masks this rect before OCRing the (handheld,
				// moving) camera clock, so our own digits can't leak in.
				panel_rect: panelRect
			},
			frames_drawn: framesDrawn,
			// Frames stamped from rVFC captureTime (camera capture moment)
			// vs. draw time. When capture_time_frames is 0, all stamps are
			// draw-time and carry the camera-pipeline latency as a
			// one-directional bias.
			capture_time_frames: captureTimeFrames,
			draw_time_frames: framesDrawn - captureTimeFrames,
			capture_latency_ms: captureTimeFrames
				? {
					mean: latencySumMs / captureTimeFrames,
					max: latencyMaxMs
				}
				: null,
			rvfc_used: usingRvfc,
			rvfc_stalled: rvfcStalled,
			user_agent: navigator.userAgent
		};
	}

	async function start() {
		if (phase === 'starting' || phase === 'recording') return;
		phase = 'starting';
		errorMsg = '';
		savedPath = '';
		framesDrawn = 0;
		captureTimeFrames = 0;
		latencySumMs = 0;
		latencyMaxMs = 0;
		elapsedS = 0;
		chunkError = null;
		chunkChain = Promise.resolve();
		webChunks = [];
		rvfcStalled = false;

		try {
			if (!navigator.mediaDevices?.getUserMedia) {
				throw new Error('Camera not available (getUserMedia unsupported)');
			}
			stream = await navigator.mediaDevices.getUserMedia({
				video: {
					facingMode: { ideal: 'environment' },
					width: { ideal: 1920 },
					height: { ideal: 1080 },
					frameRate: { ideal: 30 }
				},
				audio: false
			});
			video.srcObject = stream;
			await video.play();
			canvas.width = video.videoWidth || 1280;
			canvas.height = video.videoHeight || 720;

			mimeType = MIME_CANDIDATES.find((m) => MediaRecorder.isTypeSupported(m)) || '';
			if (!mimeType) throw new Error('MediaRecorder supports no webm/mp4 profile');

			if (TAURI) {
				const res: any = await invoke('plugin:hillview|cmd', {
					command: 'clock_video_begin',
					params: { ext: extForMime(mimeType) }
				});
				if (res && res.error) throw new Error(res.error);
				savedPath = res?.path || '';
			}

			canvasStream = canvas.captureStream(30);
			recorder = new MediaRecorder(canvasStream, {
				mimeType,
				videoBitsPerSecond: 8_000_000
			});
			recorder.ondataavailable = (e) => enqueueChunk(e.data);
			recorder.start(1000);

			try {
				wakeLock = await (navigator as any).wakeLock?.request('screen');
			} catch (e) {
				console.log('🎬 wake lock unavailable:', e);
			}

			startedAtMs = Date.now();
			phase = 'recording';
			startDrawLoop();

			elapsedTimer = setInterval(() => {
				elapsedS = Math.floor((Date.now() - startedAtMs) / 1000);
				if (chunkError) {
					stop(); // surfaced as error in stop()
					return;
				}
				// rVFC starvation watchdog: some WebViews stop presenting
				// frames for non-rendered videos. Fall back to rAF so the
				// recording keeps flowing (stamps become draw-time).
				if (usingRvfc && performance.now() - lastFrameAt > 1500) {
					console.warn('🎬 rVFC stalled, falling back to rAF');
					stopDrawLoop();
					usingRvfc = false;
					rvfcStalled = true;
					scheduleRaf();
				}
			}, 500);
		} catch (e: any) {
			console.error('🎬 failed to start clock video recording:', e);
			errorMsg = e?.message || String(e);
			phase = 'error';
			await teardownStreams();
		}
	}

	async function stop() {
		if (phase !== 'recording') return;
		phase = 'saving';
		if (elapsedTimer) {
			clearInterval(elapsedTimer);
			elapsedTimer = null;
		}
		stopDrawLoop();
		const endedAtMs = Date.now();

		try {
			if (recorder && recorder.state !== 'inactive') {
				const stopped = new Promise<void>((resolve) => {
					recorder!.onstop = () => resolve();
				});
				recorder.stop();
				await stopped;
			}
			await chunkChain;
			if (chunkError) throw new Error(`chunk write failed: ${chunkError}`);

			const sidecar = buildSidecar(endedAtMs);
			if (TAURI) {
				const res: any = await invoke('plugin:hillview|cmd', {
					command: 'clock_video_end',
					params: { sidecar: JSON.stringify(sidecar) }
				});
				if (res && res.error) throw new Error(res.error);
				savedPath = res?.path || savedPath;
			} else {
				downloadBasename = `hillview_clockvideo_${startedAtMs}`;
				downloadVideoUrl = URL.createObjectURL(new Blob(webChunks, { type: mimeType }));
				downloadSidecarUrl = URL.createObjectURL(
					new Blob([JSON.stringify(sidecar, null, '\t')], { type: 'application/json' })
				);
			}
			phase = 'done';
		} catch (e: any) {
			console.error('🎬 failed to save clock video:', e);
			errorMsg = e?.message || String(e);
			phase = 'error';
		} finally {
			await teardownStreams();
		}
	}

	// Detach the video element from the stream BEFORE stopping tracks so the
	// Android WebView's media pipeline cleanly releases the Camera2 device.
	// The settle delay gives the camera HAL time to fully release before any
	// subsequent getUserMedia() — same caution as CameraCapture.svelte.
	async function teardownStreams() {
		if (video) {
			try { video.pause(); } catch (e) { /* ignore */ }
			video.srcObject = null;
		}
		if (stream) {
			stream.getTracks().forEach((t) => t.stop());
			stream = null;
		}
		if (canvasStream) {
			canvasStream.getTracks().forEach((t) => t.stop());
			canvasStream = null;
		}
		recorder = null;
		if (wakeLock) {
			try { await wakeLock.release(); } catch (e) { /* ignore */ }
			wakeLock = null;
		}
		await new Promise((r) => setTimeout(r, 100));
	}

	onDestroy(() => {
		if (elapsedTimer) clearInterval(elapsedTimer);
		stopDrawLoop();
		// Fire-and-forget: onDestroy can't await. If a recording was live,
		// the plugin keeps the partial file; the next begin() closes the
		// orphaned stream.
		teardownStreams();
		if (downloadVideoUrl) URL.revokeObjectURL(downloadVideoUrl);
		if (downloadSidecarUrl) URL.revokeObjectURL(downloadSidecarUrl);
	});
</script>

<div class="recorder" data-testid="clock-video-recorder">
	<!-- svelte-ignore a11y-media-has-caption -->
	<video bind:this={video} class="hidden-video" playsinline muted></video>

	<canvas bind:this={canvas} class="preview" class:live={phase === 'recording'} data-testid="clock-video-canvas"></canvas>

	<div class="status" data-testid="clock-video-status">
		{#if phase === 'idle'}
			Ready. Fill the frame with the camera's clock screen, then start.
		{:else if phase === 'starting'}
			Starting camera…
		{:else if phase === 'recording'}
			<span class="rec-dot">●</span> Recording — {elapsedS}s, {framesDrawn} frames
			{#if captureTimeFrames > 0}
				· capture-time stamps
			{:else}
				· draw-time stamps
			{/if}
		{:else if phase === 'saving'}
			Saving…
		{:else if phase === 'done'}
			{#if TAURI}
				Saved to <code data-testid="clock-video-saved-path">{savedPath}</code>
			{:else}
				Ready to download.
			{/if}
		{:else if phase === 'error'}
			<span class="error" data-testid="clock-video-error">{errorMsg}</span>
		{/if}
	</div>

	<div class="controls">
		{#if phase === 'recording'}
			<button class="stop" on:click={stop} data-testid="clock-video-stop-button">Stop &amp; Save</button>
		{:else if phase === 'saving' || phase === 'starting'}
			<button disabled>…</button>
		{:else}
			<button class="start" on:click={start} data-testid="clock-video-start-button">
				{phase === 'done' || phase === 'error' ? 'Record Another' : 'Start Recording'}
			</button>
		{/if}
	</div>

	{#if phase === 'done' && !TAURI}
		<div class="downloads">
			<a href={downloadVideoUrl} download="{downloadBasename}.{extForMime(mimeType)}" data-testid="clock-video-download-video">Download video</a>
			<a href={downloadSidecarUrl} download="{downloadBasename}.json" data-testid="clock-video-download-sidecar">Download sidecar</a>
		</div>
	{/if}
</div>

<style>
	.recorder {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		align-items: center;
	}

	.hidden-video {
		position: absolute;
		width: 1px;
		height: 1px;
		opacity: 0;
		pointer-events: none;
	}

	.preview {
		width: 100%;
		max-height: 60vh;
		object-fit: contain;
		background: #111;
		border-radius: 0.5rem;
	}

	.preview.live {
		outline: 2px solid #dc2626;
	}

	.status {
		font-size: 0.875rem;
		text-align: center;
		min-height: 1.5em;
		word-break: break-all;
	}

	.rec-dot {
		color: #dc2626;
		animation: blink 1s step-start infinite;
	}

	@keyframes blink {
		50% { opacity: 0; }
	}

	.error {
		color: #dc2626;
	}

	.controls button {
		padding: 0.75rem 2rem;
		font-size: 1rem;
		border-radius: 0.5rem;
		border: none;
		cursor: pointer;
	}

	.controls .start {
		background: #2563eb;
		color: white;
	}

	.controls .stop {
		background: #dc2626;
		color: white;
	}

	.downloads {
		display: flex;
		gap: 1.5rem;
	}
</style>

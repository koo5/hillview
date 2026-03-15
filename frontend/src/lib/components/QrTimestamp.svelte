<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import QRCode from 'qrcode';

	let canvas: HTMLCanvasElement;
	let animationId: number;
	let running = false;

	function getTimestamp(): string {
		const now = new Date();
		return now.toISOString(); // e.g. 2026-03-15T14:30:05.123Z
	}

	function startRendering() {
		if (running) return;
		running = true;

		let lastRenderedMs = -1;

		function frame() {
			if (!running) return;

			const now = Date.now();
			const ms = now % 1000;

			// Only re-render when the millisecond portion changes enough (~30fps = every ~33ms)
			if (Math.abs(ms - lastRenderedMs) >= 33 || ms < lastRenderedMs) {
				lastRenderedMs = ms;
				const timestamp = getTimestamp();

				QRCode.toCanvas(canvas, timestamp, {
					width: 256,
					margin: 1,
					errorCorrectionLevel: 'L', // Low error correction for speed
					color: {
						dark: '#000000',
						light: '#ffffff'
					}
				}).catch((err: Error) => {
					console.error('QR render error:', err);
				});
			}

			animationId = requestAnimationFrame(frame);
		}

		animationId = requestAnimationFrame(frame);
	}

	function stopRendering() {
		running = false;
		if (animationId) {
			cancelAnimationFrame(animationId);
		}
	}

	onMount(() => {
		startRendering();
	});

	onDestroy(() => {
		stopRendering();
	});
</script>

<div class="qr-timestamp-container" data-testid="qr-timestamp-section">
	<p class="qr-description">
		Point your external camera at this QR code while taking photos.
		The QR code contains the current UTC timestamp (ISO 8601 with milliseconds),
		updated at ~30fps. This can be used to correlate external camera timestamps
		with Hillview's location/orientation data.
	</p>
	<div class="qr-canvas-wrapper">
		<canvas bind:this={canvas} data-testid="qr-timestamp-canvas"></canvas>
	</div>
	<p class="qr-format-hint">
		Format: <code>2026-03-15T14:30:05.123Z</code>
	</p>
</div>

<style>
	.qr-timestamp-container {
		margin-top: 0.5rem;
	}

	.qr-description {
		font-size: 0.85rem;
		color: #4b5563;
		line-height: 1.5;
	}

	.qr-canvas-wrapper {
		display: flex;
		justify-content: center;
		padding: 1rem 0;
		background: white;
		border-radius: 0.5rem;
		border: 1px solid #e5e7eb;
	}

	.qr-format-hint {
		font-size: 0.75rem;
		color: #9ca3af;
		text-align: center;
	}

	.qr-format-hint code {
		background-color: #f3f4f6;
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		font-size: 0.75rem;
	}
</style>

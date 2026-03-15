<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import QRCode from 'qrcode';

	let canvases: [HTMLCanvasElement, HTMLCanvasElement] = [null as any, null as any];
	let slots: [HTMLDivElement, HTMLDivElement] = [null as any, null as any];
	let container: HTMLDivElement;
	let animationId: number;
	let running = false;
	let qrWidth = 256;
	let timestamps: [string | null, string | null] = [null, null];
	let activeIdx = 0;
	let resizeObserver: ResizeObserver;

	function getTimestamp(): string {
		return Date.now().toString();
	}

	function updateQrWidth() {
		// Use the first slot's width to size the QR canvas
		const slot = slots[0];
		if (slot) {
			const w = slot.clientWidth;
			if (w > 0) qrWidth = w;
		}
	}

	function startRendering() {
		if (running) return;
		running = true;

		let lastRenderedMs = -1;

		function frame() {
			if (!running) return;

			const now = Date.now();
			const ms = now % 1000;

			if (Math.abs(ms - lastRenderedMs) >= 33 || ms < lastRenderedMs) {
				lastRenderedMs = ms;
				const ts = getTimestamp();

				const backIdx = activeIdx === 0 ? 1 : 0;
				const backCanvas = canvases[backIdx];

				if (backCanvas) {
					QRCode.toCanvas(backCanvas, ts, {
						width: qrWidth,
						margin: 0,
						errorCorrectionLevel: 'L',
						color: {
							dark: '#000000',
							light: '#ffffff'
						}
					}).then(() => {
						timestamps[backIdx] = ts;
						timestamps = timestamps;
						activeIdx = backIdx;
					}).catch((err: Error) => {
						console.error('QR render error:', err);
					});
				}
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
		updateQrWidth();

		resizeObserver = new ResizeObserver(() => {
			updateQrWidth();
		});
		if (container) resizeObserver.observe(container);

		startRendering();
	});

	onDestroy(() => {
		stopRendering();
		if (resizeObserver) resizeObserver.disconnect();
	});
</script>

<div class="qr-container" bind:this={container} data-testid="qr-timestamp-section">
	{#each [0, 1] as idx}
		<div class="qr-slot" class:active={idx === activeIdx} bind:this={slots[idx]}>
			<canvas bind:this={canvases[idx]} data-testid="qr-timestamp-canvas-{idx}"></canvas>
			<p class="ts-label">
				{#if idx === activeIdx}●{:else}○{/if}
				{timestamps[idx] ? new Date(Number(timestamps[idx])).toISOString() : ''}
			</p>
		</div>
	{/each}
</div>

<style>
	.qr-container {
		display: flex;
		flex-direction: column;
		width: 100%;
		height: 100%;
		background: white;
		overflow: hidden;
	}

	/* Landscape: side by side */
	@media (orientation: landscape) {
		.qr-container {
			flex-direction: row;
		}
	}

	.qr-slot {
		flex: 1;
		min-width: 0;
		min-height: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		overflow: hidden;
		padding: 1rem;
	}

	.qr-slot.active {
	}

	.qr-slot :global(canvas) {
		display: block;
		flex: 1;
		min-height: 0;
		max-width: 100%;
		object-fit: contain;
	}

	.ts-label {
		flex-shrink: 0;
		font-size: clamp(0.75rem, 2vw, 1.5rem);
		text-align: center;
		font-weight: 900;
		padding: 0;
		margin: 0.25rem 0 0 0;
		white-space: nowrap;
	}
</style>

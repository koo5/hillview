<script lang="ts">
	/**
	 * Debug readout for the web capture's device pose (debug mode 4), for the
	 * real-device series in docs/todo/web-capture-level-stamp.md.
	 *
	 * The first rows are the one state, what the shutter stamps and the indicator
	 * draws. The last row is a DIAGNOSTIC, the documented exception in
	 * docs/one-state.md: devicemotion's raw accelerationIncludingGravity, which
	 * nothing a photo records may come from. Held upright, its y reads about +9.8 on
	 * Android and about -9.8 if iOS inverts it, which settles why the stamp converts
	 * deviceorientation instead.
	 */
	import { onDestroy, onMount } from 'svelte';
	import { capturePose } from '$lib/capturePose';
	import { levelState, poseFromGravity } from '$lib/capturePoseMath';

	let motion: { x: number | null; y: number | null; z: number | null } | null = null;
	const DME = typeof window !== 'undefined'
		? (window as unknown as { DeviceMotionEvent?: { requestPermission?: () => Promise<string> } }).DeviceMotionEvent
		: undefined;
	const needsPermission = typeof DME?.requestPermission === 'function';

	function onMotion(event: DeviceMotionEvent) {
		const a = event.accelerationIncludingGravity;
		motion = a ? { x: a.x, y: a.y, z: a.z } : null;
	}

	onMount(() => window.addEventListener('devicemotion', onMotion));
	onDestroy(() => {
		if (typeof window !== 'undefined') window.removeEventListener('devicemotion', onMotion);
	});

	const f = (v: number | null | undefined, digits = 2) => (v == null ? '–' : v.toFixed(digits));

	$: pose = $capturePose ? poseFromGravity($capturePose.gravity) : null;
</script>

<div class="capture-subsection" data-testid="capture-pose-debug">
	<div class="subsection-header">🧭 Device pose (capturePose):</div>
	{#if $capturePose}
		<div>source: {$capturePose.source}</div>
		<div>gravity: [{$capturePose.gravity.map((v) => f(v)).join(', ')}]</div>
		<div>pitch {f(pose?.pitch, 1)}° · roll {f(pose?.roll, 1)}° · {levelState(pose)}</div>
	{:else}
		<div>nothing measured (the camera is closed, or no source)</div>
	{/if}
	<div class="diagnostic">
		accelerationIncludingGravity (diagnostic):
		{#if motion}[{f(motion.x)}, {f(motion.y)}, {f(motion.z)}]{:else}–{/if}
		{#if needsPermission && !motion}
			<button on:click={() => DME?.requestPermission?.()}>allow motion</button>
		{/if}
	</div>
</div>

<style>
	.diagnostic {
		margin-top: 4px;
		opacity: 0.8;
	}
</style>

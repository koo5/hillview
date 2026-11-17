<script lang="ts">
	/**
	 * The capture screen's level indicator: whether the next photo will pass the
	 * Panoramax pitch and roll gates (|pitch| ≤ MAX_PITCH_DEG, |roll| ≤ MAX_ROLL_DEG).
	 *
	 * It reads the pose from the one state (capturePose), the reading the shutter
	 * stamps, and never opens a sensor of its own. It informs and never refuses:
	 * the shutter stays live whatever it shows. Hidden in car mode, which the
	 * gates exempt. When nothing is measured it says so ("Tilt not measured."), and
	 * while the Panoramax toggle is on it adds that such photos cannot be published
	 * there; on a desktop browser that note is all of it. Rules: "Capture guidance
	 * for Panoramax: the level indicator" in docs/todo/photo-pose-and-level-gates.md.
	 */
	import { capturePose } from '$lib/capturePose';
	import {
		horizonScreenAngle,
		levelReferenceScreenAngle,
		levelState,
		levelWords,
		poseFromGravity,
	} from '$lib/capturePoseMath';
	import { screenOrientationAngle } from '$lib/deviceOrientationExif';
	import { bearingMode } from '$lib/mapState';
	import { capturePanoramaxShare } from '$lib/data.svelte';

	/** The active camera's facingMode. A camera facing the user stamps no gravity
	 * (capture_pose assumes the back camera's axis), so it shows as unmeasured. */
	export let facing: string | null = null;

	$: reading = facing === 'user' ? null : $capturePose;
	$: pose = reading ? poseFromGravity(reading.gravity) : null;
	$: state = levelState(pose);
	$: words = levelWords(pose);
	$: horizon = reading ? horizonScreenAngle(reading.gravity, $screenOrientationAngle) : 0;
	$: reference = reading ? levelReferenceScreenAngle(reading.gravity, $screenOrientationAngle) : 0;
</script>

{#if $bearingMode !== 'car'}
	<div class="level-indicator" data-testid="capture-level-indicator" data-level-state={state}
		 data-level-source={reading?.source ?? ''}>
		{#if state === 'level' || state === 'tilted'}
			<div class="reference" style="transform: rotate({reference}deg)">
				<span class="tick"></span><span class="tick"></span>
			</div>
			<div class="horizon" class:level={state === 'level'} style="transform: rotate({horizon}deg)"></div>
		{/if}
		{#if words}
			<div class="label" class:level={state === 'level'} data-testid="capture-level-words">
				{state === 'level' ? '✓ ' : ''}{words}
			</div>
		{:else if state === 'unmeasured'}
			<div class="note" data-testid="capture-level-unmeasured-note">
				Tilt not measured.
				{#if $capturePanoramaxShare}
					<div><small>(These photos cannot be published to Panoramax)</small></div>
				{/if}
			</div>
		{/if}
	</div>
{/if}

<style>
	.level-indicator {
		position: absolute;
		inset: 0;
		pointer-events: none;
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 5;
	}

	.horizon,
	.reference {
		position: absolute;
		width: 200px;
		height: 0;
	}

	.horizon {
		border-top: 2px solid #ffb300;
		filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.8));
	}

	.horizon.level {
		border-top-color: #4caf50;
	}

	.reference {
		display: flex;
		justify-content: space-between;
	}

	.tick {
		width: 28px;
		margin: 0 -36px;
		border-top: 3px solid rgba(255, 255, 255, 0.85);
		transform: translateY(-1.5px);
		filter: drop-shadow(0 0 2px rgba(0, 0, 0, 0.8));
	}

	.label,
	.note {
		position: absolute;
		top: calc(50% + 24px);
		padding: 3px 10px;
		border-radius: 12px;
		background: rgba(0, 0, 0, 0.55);
		color: #ffd54f;
		font-family: monospace;
		font-size: 0.85rem;
		white-space: nowrap;
	}

	.label.level {
		color: #81c784;
	}

	.note {
		top: auto;
		bottom: 96px;
		max-width: calc(100% - 32px);
		white-space: normal;
		text-align: center;
		color: #fff;
	}
</style>

<svelte:head>
	<title>Clock Calibration Video - Hillview</title>
</svelte:head>

<script lang="ts">
	import StandardHeaderWithAlert from "$lib/components/StandardHeaderWithAlert.svelte";
	import StandardBody from "$lib/components/StandardBody.svelte";
	import ClockVideoRecorder from "$lib/components/ClockVideoRecorder.svelte";
</script>

<StandardHeaderWithAlert
	title="Clock Calibration Video"
	showMenuButton={true}
	fallbackHref="/settings/advanced"
/>

<StandardBody>
	<div data-testid="clock-video-page">
		<p>
			Film your external camera's date/time settings screen so the ticking
			seconds are large, sharp and well-lit. Hold steady for 15–20 seconds —
			enough to catch several second flips. Every recorded frame carries a QR
			code of this phone's UTC time, so the video needs no trustworthy file
			timestamps. Process with <code>video_time_correction.py</code>; the
			video is saved next to the geo tracking CSV dumps.
		</p>

		<ClockVideoRecorder />
	</div>
</StandardBody>

<style>
	p {
		font-size: 0.875rem;
		color: #374151;
		line-height: 1.5;
	}

	code {
		background-color: #f3f4f6;
		padding: 0.1rem 0.3rem;
		border-radius: 0.25rem;
		font-size: 0.8em;
	}
</style>

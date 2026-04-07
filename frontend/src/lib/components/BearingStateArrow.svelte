<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let width = 16;
	export let height = 16;
	export let centerX = width / 2;
	export let centerY = height / 2;
	export let arrowX = width / 2;
	export let arrowY = 0;

	// Hit area covers the outer third of the arrow
	$: hitStartX = centerX + (arrowX - centerX) * 1.8 / 3;
	$: hitStartY = centerY + (arrowY - centerY) * 1.8 / 3;

	const dispatch = createEventDispatcher();

	function handlePointerDown(e: PointerEvent) {
		e.preventDefault();
		e.stopPropagation();
		dispatch('arrowdragstart', { pointerId: e.pointerId, clientX: e.clientX, clientY: e.clientY });
	}
</script>


<svg
	height={height}
	viewBox={`0 0 ${width} ${height}`}
	width={width}
	style="pointer-events: none;"
	data-testid="bearing-arrow-svg"
>
	<circle
		cx={centerX}
		cy={centerY}
		fill="rgb(4, 5, 250)"
		stroke="rgb(250, 0, 0)"
		fill-opacity="0.6"
		stroke-opacity="0.5"
		r="3"
	/>

	<line

		marker-end="url(#arrowhead)"
		stroke-opacity="0.5"
		stroke-width="3"
		stroke="rgb(4, 5, 250)"
		x1={centerX}
		x2={arrowX}
		y1={centerY}
		y2={arrowY}
	/>
	<!-- Hit area on outer third of arrow for dragging -->
	<line
		x1={hitStartX}
		y1={hitStartY}
		x2={arrowX}
		y2={arrowY}
		stroke="transparent"
		stroke-width="30"
		style="pointer-events: auto; cursor: grab;"
		on:pointerdown={handlePointerDown}
		data-testid="bearing-arrow-hitarea"
	/>
	<defs>
		<marker
		id="arrowhead"
			markerHeight="12"
			markerWidth="11"
			orient="auto"
			refX="9"
			refY="6"
		>
			<polygon
				fill="rgb(4, 5, 250)"
				stroke="rgb(250, 0, 0)"
				stroke-opacity="0.6"
				fill-opacity="0.6"
				points="0 0, 10 6, 0 12"
			/>
		</marker>
	</defs>
</svg>

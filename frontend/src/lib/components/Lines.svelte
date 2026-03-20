<script lang="ts">
	import {linesVisible, lines, type Line} from '$lib/data.svelte';
	import {spatialState, bearingState} from '$lib/mapState';
	import {destinationPoint} from '$lib/geo';
	import {get} from 'svelte/store';
	import {Plus, Trash2} from 'lucide-svelte';

	function addLine() {
		const {center} = get(spatialState);
		const {bearing} = get(bearingState);
		const end = destinationPoint(center.lat, center.lng, bearing, 50);
		lines.update(l => [{label: '', start: {lat: center.lat, lng: center.lng}, end, visible: true}, ...l]);
	}

	function removeLine(index: number) {
		lines.update(l => l.filter((_, i) => i !== index));
	}

	function toggleLineVisible(index: number) {
		lines.update(l => l.map((line, i) => i === index ? {...line, visible: !line.visible} : line));
	}
</script>

<div class="lines-view" data-testid="lines-view">
	<div class="toolbar">
		<label class="toggle-option" data-testid="lines-visible-toggle">
			<input type="checkbox" bind:checked={$linesVisible} />
			<span class="option-title">Show on map</span>
		</label>
		<button class="add-btn" data-testid="lines-add-btn" on:click={addLine}>
			<Plus size={18} /> Add line
		</button>
	</div>

	{#if $lines.length > 0}
		<table class="lines-table" data-testid="lines-table">
			<thead>
				<tr>
					<th>Vis</th>
					<th>Label</th>
					<th></th>
				</tr>
			</thead>
			<tbody>
				{#each $lines as line, i}
					<tr data-testid="lines-row-{i}">
						<td>
							<input
								type="checkbox"
								checked={line.visible}
								on:change={() => toggleLineVisible(i)}
								data-testid="line-visible-{i}"
							/>
						</td>
						<td>
							<input
								type="text"
								bind:value={line.label}
								placeholder="Line {i + 1}"
								data-testid="line-label-{i}"
							/>
						</td>
						<td>
							<button class="delete-btn" on:click={() => removeLine(i)} data-testid="line-delete-{i}" aria-label="Delete line">
								<Trash2 size={16} />
							</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>

<style>
	.lines-view {
		width: 100%;
		height: 100%;
		padding-top: calc(50px + var(--safe-area-inset-top, 10px));
		padding-left: calc(50px + var(--safe-area-inset-left, 10px));
		padding-right: 0.75rem;
		box-sizing: border-box;
		display: flex;
		flex-direction: column;
		color: white;
		background: linear-gradient(135deg, #000000, #388E3C);
		overflow-y: auto;
	}

	.toolbar {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.toggle-option {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		cursor: pointer;
	}

	.toggle-option input[type="checkbox"] {
		width: 1.1rem;
		height: 1.1rem;
		cursor: pointer;
		accent-color: #4a90e2;
	}

	.option-title {
		font-weight: 500;
		white-space: nowrap;
	}

	.add-btn {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.5rem 1rem;
		background: rgba(255, 255, 255, 0.15);
		color: white;
		border: 1px solid rgba(255, 255, 255, 0.3);
		border-radius: 0.5rem;
		cursor: pointer;
		font-size: 0.9rem;
		transition: background-color 0.2s, border-color 0.2s;
	}

	.add-btn:hover {
		background: rgba(255, 255, 255, 0.25);
		border-color: rgba(255, 255, 255, 0.5);
	}

	.lines-table {
		margin-top: 0.75rem;
		border-collapse: collapse;
		width: 100%;
		font-size: 0.85rem;
	}

	.lines-table th {
		text-align: left;
		padding: 0.4rem 0.3rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.3);
		font-weight: 500;
		white-space: nowrap;
	}

	.lines-table td {
		padding: 0.3rem 0.3rem;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}

	.lines-table input[type="text"] {
		width: 100%;
		padding: 0.25rem 0.4rem;
		background: rgba(0, 0, 0, 0.3);
		color: white;
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 0.25rem;
		font-size: 0.85rem;
		box-sizing: border-box;
	}

	.lines-table input[type="text"]:focus {
		outline: none;
		border-color: #4a90e2;
	}

	.lines-table input[type="text"]::placeholder {
		color: rgba(255, 255, 255, 0.4);
	}

	.lines-table input[type="checkbox"] {
		width: 1.1rem;
		height: 1.1rem;
		cursor: pointer;
		accent-color: #4a90e2;
	}

	.delete-btn {
		background: none;
		border: none;
		color: rgba(255, 255, 255, 0.6);
		cursor: pointer;
		padding: 0.25rem;
		border-radius: 0.25rem;
		display: flex;
		align-items: center;
		transition: color 0.2s, background-color 0.2s;
	}

	.delete-btn:hover {
		color: #ff6b6b;
		background: rgba(255, 107, 107, 0.15);
	}
</style>

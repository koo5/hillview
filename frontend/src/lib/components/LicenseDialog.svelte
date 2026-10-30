<script lang="ts">
	import { onMount } from 'svelte';
	import { UPLOAD_LICENSES, canGrantPanoramax } from '$lib/licenses';
	export let current: string | null = null;
	export let forPanoramax = false;
	export let sharing = false;
	export let context = 'Future camera photos. Existing photos keep their choices.';
	export let note = 'This does not start an upload.';
	export let onConfirm: (license: string) => void | Promise<void>;
	export let onClose: () => void;
	let dialog: HTMLDialogElement;
	let selected: string | null = forPanoramax ? null : current;
	let busy = false;
	let error = '';
	$: options = forPanoramax ? UPLOAD_LICENSES.filter(option => canGrantPanoramax(option.id)) : UPLOAD_LICENSES;
	$: turnsSharingOff = !forPanoramax && sharing && selected && !canGrantPanoramax(selected);

	onMount(() => {
		const previous = document.activeElement as HTMLElement | null;
		dialog.showModal();
		return () => {
			dialog.close();
			if (previous?.isConnected) previous.focus();
		};
	});

	async function confirm() {
		if (!selected || busy) return;
		busy = true;
		error = '';
		try {
			await onConfirm(selected);
			onClose();
		} catch (err) {
			error = err instanceof Error ? err.message : 'Could not apply this choice. Please try again.';
		} finally {
			busy = false;
		}
	}
</script>

<dialog bind:this={dialog} aria-label={forPanoramax ? 'Choose a license for Panoramax' : 'Choose an upload license'}
	on:keydown={(event) => event.stopPropagation()}
	on:cancel|preventDefault={() => { if (!busy) onClose(); }} data-testid="license-dialog">
	<form on:submit|preventDefault={confirm}>
		<header>
			<h2>{forPanoramax ? 'CC needs a different grant for Panoramax' : 'Choose an upload license'}</h2>
			<p class="context" data-testid="license-dialog-context">{context}</p>
			{#if forPanoramax}
				<p>CC BY-SA 4.0 + OSM does not cover Panoramax’s derived-data uses. To turn sharing on, choose one of the compatible grants below, or cancel to keep your current choices.</p>
			{/if}
			<p>You keep your copyright. Choose what permission to give Hillview.</p>
		</header>
		<div class="choices">
			<fieldset disabled={busy} data-testid="license-selector">
				<legend>Upload grant</legend>
				{#each options as option}
					<div class="option" class:selected={selected === option.id}>
						<label>
							<input type="radio" name="upload-grant" value={option.id} checked={selected === option.id}
								on:change={() => selected = option.id}
								data-testid={option.id === 'ccbysa4+osm' ? 'license-checkbox' : `license-option-${option.id}`} />
							<span><strong>{option.label}</strong><span>{option.summary}</span></span>
						</label>
						<details>
							<summary data-testid={`license-help-${option.id}`}>Learn more about this license</summary>
							<p>{option.explainer}</p>
						</details>
					</div>
				{/each}
			</fieldset>
			{#if error}<p class="error" role="alert" data-testid="license-dialog-error">{error}</p>{/if}
		</div>
		<footer>
			{#if turnsSharingOff}<p>Panoramax sharing will be turned off with this license.</p>{/if}
			<p>{note}</p>
			<div class="actions">
				<button type="button" on:click={onClose} disabled={busy} data-testid="license-dialog-cancel">Cancel</button>
				<button type="submit" class="confirm" disabled={!selected || busy} data-testid="license-dialog-confirm">
					{busy ? 'Applying…' : forPanoramax ? 'Use this license and enable sharing' : turnsSharingOff ? 'Use this license and turn sharing off' : 'Use this license'}
				</button>
			</div>
		</footer>
	</form>
</dialog>

<style>
	dialog { width: min(40rem, calc(100vw - 2rem)); max-height: calc(100dvh - 2rem); padding: 0; border: 1px solid #cbd5e1; border-radius: 1rem; color: #1f2937; background: white; box-shadow: 0 1rem 4rem #0004; font: 1rem/1.5 system-ui, sans-serif; }
	dialog::backdrop { background: #0009; }
	form { display: flex; flex-direction: column; max-height: calc(100dvh - 2rem); }
	header { padding: 1.25rem 1.25rem 0; }
	h2 { margin: 0; font-size: 1.35rem; line-height: 1.3; }
	p { margin: .65rem 0; }
	.context { font-weight: 600; }
	.choices { overflow-y: auto; padding: .5rem 1.25rem 1rem; min-height: 4rem; }
	fieldset { border: 0; margin: 0; padding: 0; min-width: 0; }
	legend { font-weight: 600; margin-bottom: .5rem; }
	.option { border: 1px solid #cbd5e1; border-radius: .75rem; margin: .5rem 0; }
	.option.selected { background: #eff6ff; border-color: #2563eb; }
	label { display: flex; align-items: flex-start; gap: .75rem; padding: 1rem; cursor: pointer; }
	label > span { display: flex; flex-direction: column; gap: .4rem; }
	strong { font-size: 1.05rem; }
	input { flex-shrink: 0; width: 1.2rem; height: 1.2rem; margin: .2rem 0; }
	details { padding: 0 1rem .75rem; }
	summary { cursor: pointer; padding: .5rem 0; color: #1d4ed8; text-decoration: underline; }
	footer { border-top: 1px solid #e2e8f0; padding: .65rem 1.25rem 1rem; background: #f8fafc; }
	.actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: .6rem; }
	button { min-height: 44px; padding: .5rem .85rem; border: 1px solid #94a3b8; border-radius: .5rem; background: white; color: #1f2937; font: inherit; cursor: pointer; }
	.confirm { background: #166534; border-color: #166534; color: white; }
	button:disabled { opacity: .55; cursor: default; }
	.error { color: #b91c1c; }
	@media(max-width: 480px) { header { padding: 1rem 1rem 0; } .choices { padding: .5rem 1rem; } footer { padding: .5rem 1rem .75rem; } .actions { flex-direction: column; } }
</style>

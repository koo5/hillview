<script lang="ts">
	import LicenseDialog from './LicenseDialog.svelte';
	import { needsPanoramaxLicenseChoice } from '$lib/licenses';
	export let sharing = false;
	export let license: string | null = null;
	export let context = 'Future camera photos. Existing photos keep their choices.';
	export let note = 'This does not start an upload.';
	export let label = 'Panoramax sharing';
	export let compact = false;
	export let buttonText: string | null = null;
	export let disabled = false;
	export let testId = 'panoramax-sharing-checkbox';
	export let onChange: (sharing: boolean, grant?: string) => void | Promise<void>;
	let choosing = false;
	let busy = false;
	let error = '';

	async function apply(value: boolean, grant?: string) {
		busy = true;
		try { await onChange(value, grant); }
		finally { busy = false; }
	}

	async function toggle() {
		if (disabled || busy) return;
		error = '';
		if (needsPanoramaxLicenseChoice(license, !sharing)) {
			choosing = true;
			return;
		}
		try { await apply(!sharing); }
		catch (err) { error = err instanceof Error ? err.message : 'Could not update sharing'; }
	}
</script>

{#if compact || buttonText}
	<button type="button" class:compact class:active={sharing} disabled={disabled || busy} data-testid={testId}
		aria-pressed={sharing} aria-label={compact ? `Panoramax sharing ${sharing ? 'on' : 'off'}` : undefined}
		title={compact ? 'Panoramax sharing for future photos' : undefined} on:click={toggle}>
		{compact ? 'P' : buttonText}
	</button>
{:else}
	<label class="toggle">
		<input type="checkbox" checked={sharing} disabled={disabled || busy} data-testid={testId}
			on:change={(event) => { event.currentTarget.checked = sharing; void toggle(); }} />
		<span>{label}</span>
	</label>
{/if}
{#if error}<p class="error" role="alert">{error}</p>{/if}
{#if choosing}
	<LicenseDialog current={license} forPanoramax={true} {context} {note}
		onConfirm={(grant) => apply(true, grant)} onClose={() => choosing = false} />
{/if}

<style>
	.toggle { display: flex; align-items: center; gap: .75rem; min-height: 44px; font: 1rem/1.5 system-ui, sans-serif; cursor: pointer; }
	input { width: 1.2rem; height: 1.2rem; margin: 0; flex-shrink: 0; }
	button { min-height: 44px; padding: .5rem .75rem; border-radius: .5rem; border: 1px solid #94a3b8; background: white; color: #1f2937; font: inherit; cursor: pointer; }
	button.compact { display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 50%; border: 1px solid #ffffff70; background: #000b; color: white; font: 1.1rem system-ui, sans-serif; }
	button.active.compact { background: #4caf50; color: #000; border-color: #4caf50; }
	button:disabled { opacity: .55; cursor: default; }
	.error { color: #b91c1c; font-size: 1rem; }
</style>

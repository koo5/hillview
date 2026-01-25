<script lang="ts">
	import { dropdownMenuState, closeDropdownMenu } from './dropdownMenu.svelte.js';
	import { portal } from '$lib/actions/portal';

	let menuElement: HTMLElement | undefined = $state();

	// Compute position styles based on anchor
	const positionStyles = $derived.by(() => {
		const { position, anchor } = $dropdownMenuState;
		const styles: string[] = [];

		switch (anchor) {
			case 'top-left':
				styles.push(`left: ${position.x}px`);
				styles.push(`top: ${position.y}px`);
				break;
			case 'top-right':
				styles.push(`right: ${window.innerWidth - position.x}px`);
				styles.push(`top: ${position.y}px`);
				break;
			case 'bottom-left':
				styles.push(`left: ${position.x}px`);
				styles.push(`bottom: ${window.innerHeight - position.y}px`);
				break;
			case 'bottom-right':
				styles.push(`right: ${window.innerWidth - position.x}px`);
				styles.push(`bottom: ${window.innerHeight - position.y}px`);
				break;
		}

		return styles.join('; ');
	});

	function handleClickOutside(event: PointerEvent) {
		if ($dropdownMenuState.visible && menuElement && !menuElement.contains(event.target as Node)) {
			closeDropdownMenu();
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if ($dropdownMenuState.visible && event.key === 'Escape') {
			closeDropdownMenu();
		}
	}

	function handleItemClick(onclick: () => void) {
		onclick();
		closeDropdownMenu();
	}
</script>

<svelte:document on:pointerup={handleClickOutside} on:keydown={handleKeydown} />

{#if $dropdownMenuState.visible}
	<div
		class="dropdown-menu-portal"
		style={positionStyles}
		data-testid={$dropdownMenuState.testId ?? 'dropdown-menu'}
		bind:this={menuElement}
		use:portal
	>
		<div class="dropdown-menu">
			{#each $dropdownMenuState.items as item, index}
				{#if item.type === 'divider'}
					<div class="menu-divider"></div>
				{:else if item.type === 'custom'}
					{@render item.render({ close: closeDropdownMenu })}
				{:else}
					<button
						class="menu-item"
						class:selected={item.selected}
						class:disabled={item.disabled}
						disabled={item.disabled}
						data-testid={item.testId}
						onclick={() => handleItemClick(item.onclick)}
					>
						{#if item.icon}
							{@const Icon = item.icon}
							<span class="menu-item-icon">
								<Icon size={16} />
							</span>
						{/if}
						<span class="menu-item-content">
							<span class="menu-item-label">{item.label}</span>
							{#if item.description}
								<span class="menu-item-description">{item.description}</span>
							{/if}
						</span>
					</button>
				{/if}
			{/each}
		</div>
	</div>
{/if}

<style>
	.dropdown-menu-portal {
		position: fixed;
		z-index: 2147483647;
		pointer-events: auto;
	}

	.dropdown-menu {
		background: white;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
		min-width: 160px;
		max-width: 280px;
		overflow: hidden;
		padding: 4px 0;
	}

	.menu-item {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		width: 100%;
		padding: 10px 14px;
		border: none;
		background: transparent;
		color: #1f2937;
		cursor: pointer;
		text-align: left;
		transition: background-color 0.15s ease;
		font-size: 14px;
	}

	.menu-item:hover:not(:disabled) {
		background-color: #f3f4f6;
	}

	.menu-item:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.menu-item.selected {
		background-color: #e3f2fd;
	}

	.menu-item.selected:hover:not(:disabled) {
		background-color: #bbdefb;
	}

	.menu-item-icon {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #6b7280;
	}

	.menu-item.selected .menu-item-icon {
		color: #1976d2;
	}

	.menu-item-content {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.menu-item-label {
		font-weight: 500;
		color: #1f2937;
	}

	.menu-item-description {
		font-size: 12px;
		color: #6b7280;
	}

	.menu-divider {
		height: 1px;
		background: #e5e7eb;
		margin: 4px 0;
	}
</style>

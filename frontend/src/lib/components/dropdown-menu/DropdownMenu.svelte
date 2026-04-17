<script lang="ts">
	import { dropdownMenuState, closeDropdownMenu } from './dropdownMenu.svelte.js';
	import { portal } from '$lib/actions/portal';

	let menuElement: HTMLElement | undefined = $state();
	let adjustedPosition: { left?: number; right?: number; top?: number; bottom?: number } | null = $state(null);

	// After menu renders, check if it's off-screen and adjust
	$effect(() => {
		if ($dropdownMenuState.visible && menuElement) {
			// Reset adjustment when menu opens
			adjustedPosition = null;

			// Use requestAnimationFrame to ensure menu has rendered
			requestAnimationFrame(() => {
				if (!menuElement) return;

				const rect = menuElement.getBoundingClientRect();
				const viewport = {
					width: window.innerWidth,
					height: window.innerHeight
				};
				const padding = 8; // Minimum distance from viewport edge

				let newPos: typeof adjustedPosition = {};
				const { position, anchor } = $dropdownMenuState;

				// Calculate where menu currently is
				let menuLeft = rect.left;
				let menuRight = rect.right;
				let menuTop = rect.top;
				let menuBottom = rect.bottom;

				// Check horizontal overflow
				if (menuLeft < padding) {
					// Menu is off left edge - anchor to left instead
					newPos.left = padding;
					newPos.right = undefined;
				} else if (menuRight > viewport.width - padding) {
					// Menu is off right edge - anchor to right instead
					newPos.right = padding;
					newPos.left = undefined;
				}

				// Check vertical overflow
				if (menuTop < padding) {
					// Menu is off top edge - position below instead
					newPos.top = padding;
					newPos.bottom = undefined;
				} else if (menuBottom > viewport.height - padding) {
					// Menu is off bottom edge - position above instead
					newPos.bottom = padding;
					newPos.top = undefined;
				}

				// Only update if we need adjustment
				if (Object.keys(newPos).length > 0) {
					adjustedPosition = newPos;
				}
			});
		}
	});

	// Compute position styles based on anchor, with adjustment override
	const positionStyles = $derived.by(() => {
		const { position, anchor } = $dropdownMenuState;
		const styles: string[] = [];

		// If we have an adjusted position, use it
		if (adjustedPosition) {
			if (adjustedPosition.left !== undefined) {
				styles.push(`left: ${adjustedPosition.left}px`);
			}
			if (adjustedPosition.right !== undefined) {
				styles.push(`right: ${adjustedPosition.right}px`);
			}
			if (adjustedPosition.top !== undefined) {
				styles.push(`top: ${adjustedPosition.top}px`);
			}
			if (adjustedPosition.bottom !== undefined) {
				styles.push(`bottom: ${adjustedPosition.bottom}px`);
			}

			// Fill in missing dimensions from original calculation
			if (adjustedPosition.left === undefined && adjustedPosition.right === undefined) {
				if (anchor === 'top-left' || anchor === 'bottom-left') {
					styles.push(`left: ${position.x}px`);
				} else {
					styles.push(`right: ${window.innerWidth - position.x}px`);
				}
			}
			if (adjustedPosition.top === undefined && adjustedPosition.bottom === undefined) {
				if (anchor === 'top-left' || anchor === 'top-right') {
					styles.push(`top: ${position.y}px`);
				} else {
					styles.push(`bottom: ${window.innerHeight - position.y}px`);
				}
			}

			return styles.join('; ');
		}

		// Original positioning logic
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

	// Block click synthesis from touch so the ghost click can't land on the
	// element that ends up under the pointer after the menu closes.
	// NOTE: to actually prevent click synthesis we must preventDefault on
	// `touchstart` / `touchend`, not just on pointerdown.
	function swallowEvent(event: Event) {
		event.preventDefault();
		event.stopPropagation();
	}

	// On Android webview, touching a menu item can still fire a synthetic click
	// after we close the dropdown — the target is whatever is under the touch
	// point now (the gallery), which receives a spurious tap. Arm a brief
	// document-level capture-phase swallower to catch that stray click.
	function armClickSwallower() {
		const handler = (e: Event) => {
			e.preventDefault();
			e.stopPropagation();
			e.stopImmediatePropagation();
			document.removeEventListener('click', handler, true);
		};
		document.addEventListener('click', handler, { capture: true });
		setTimeout(() => {
			document.removeEventListener('click', handler, true);
		}, 150);
	}

	function handleItemPointerUp(event: PointerEvent, onclick: () => void) {
		event.preventDefault();
		event.stopPropagation();
		onclick();
		closeDropdownMenu();
		if (event.pointerType === 'touch') armClickSwallower();
	}

	// Middle-click, ctrl/meta-click, and shift-click should fall through to the
	// browser's native anchor behavior (open in new tab / new window). Primary
	// unmodified clicks go through `item.onclick` and the browser default is
	// suppressed, so exactly one navigation happens per click.
	function isOpenInNewTabClick(e: { button?: number; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }): boolean {
		return e.button === 1 || !!e.ctrlKey || !!e.metaKey || !!e.shiftKey;
	}

	// Primary anchor activation goes through pointerup so touch input works:
	// on touch, swallowing ontouchstart/end kills the synthetic click, so
	// click never fires. pointerup fires for both touch and mouse.
	function handleAnchorPointerUp(event: PointerEvent, onclick: () => void) {
		if (isOpenInNewTabClick(event)) {
			// Modifier/middle: let native click happen so the browser opens a new tab.
			setTimeout(closeDropdownMenu, 0);
			return;
		}
		event.preventDefault();
		event.stopPropagation();
		onclick();
		closeDropdownMenu();
		if (event.pointerType === 'touch') armClickSwallower();
	}

	// Mouse click backup: suppress native anchor nav so we don't double-trigger.
	// onclick was already called by pointerup above.
	function handleAnchorClick(event: MouseEvent) {
		if (isOpenInNewTabClick(event)) return;
		event.preventDefault();
		event.stopPropagation();
	}

	function handleAnchorAuxClick() {
		setTimeout(closeDropdownMenu, 0);
	}

	// Stop drag/touch events from propagating to the page underneath
	function stopEvent(event: Event) {
		event.stopPropagation();
		event.preventDefault();
	}

	// For clicks we only stop propagation, not default (so buttons work)
	function stopPropagation(event: Event) {
		event.stopPropagation();
	}

	// Action to add capture-phase event listeners that intercept before anything else
	function captureEvents(node: HTMLElement) {
		const handler = (e: Event) => {
			e.stopPropagation();
			e.stopImmediatePropagation();
		};

		const events = ['touchstart', 'touchmove', 'touchend', 'pointerdown', 'pointermove', 'pointerup'];
		events.forEach(evt => node.addEventListener(evt, handler, { capture: true, passive: false }));

		return {
			destroy() {
				events.forEach(evt => node.removeEventListener(evt, handler, { capture: true }));
			}
		};
	}
</script>

{#snippet menuItemBody(item: import('./dropdownMenu.svelte.js').DropdownMenuItemAction)}
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
{/snippet}

<svelte:document on:pointerup={handleClickOutside} on:keydown={handleKeydown} />

{#if $dropdownMenuState.visible}
	<!-- Backdrop to close menu when clicking outside -->
	<div
		class="dropdown-backdrop"
		use:portal
		ontouchstart={swallowEvent}
		ontouchmove={swallowEvent}
		ontouchend={swallowEvent}
		onpointerdown={swallowEvent}
		onpointerup={(e) => { swallowEvent(e); closeDropdownMenu(); }}
		onclick={swallowEvent}
		onmousedown={swallowEvent}
		onmouseup={swallowEvent}
		onkeydown={handleKeydown}
		role="button"
		tabindex="-1"
	></div>
	<!-- svelte-ignore a11y_no_static_element_interactions -->
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
				{:else if item.type === 'header'}
					<div class="menu-header">{item.label}</div>
				{:else if item.type === 'custom'}
					{@render item.render({ close: closeDropdownMenu })}
				{:else if item.url && !item.disabled}
					<a
						class="menu-item"
						class:selected={item.selected}
						href={item.url}
						data-testid={item.testId}
						ontouchstart={swallowEvent}
						ontouchmove={swallowEvent}
						ontouchend={swallowEvent}
						onpointerdown={swallowEvent}
						onpointerup={(e) => handleAnchorPointerUp(e, item.onclick)}
						onclick={handleAnchorClick}
						onauxclick={handleAnchorAuxClick}
					>
						{@render menuItemBody(item)}
					</a>
				{:else}
					<button
						class="menu-item"
						class:selected={item.selected}
						class:disabled={item.disabled}
						disabled={item.disabled}
						data-testid={item.testId}
						ontouchstart={swallowEvent}
						ontouchmove={swallowEvent}
						ontouchend={swallowEvent}
						onpointerdown={swallowEvent}
						onpointerup={(e) => handleItemPointerUp(e, item.onclick)}
						onclick={swallowEvent}
					>
						{@render menuItemBody(item)}
					</button>
				{/if}
			{/each}
		</div>
	</div>
{/if}

<style>
	.dropdown-backdrop {
		position: fixed;
		inset: 0;
		z-index: 2147483646;
		background: rgba(0, 0, 0, 0.35);
		/* Prevent browser handling of touch gestures */
		touch-action: none;
	}

	.dropdown-menu-portal {
		position: fixed;
		z-index: 2147483647;
		pointer-events: auto;
		touch-action: none;
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
		text-decoration: none;
		box-sizing: border-box;
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

	.menu-header {
		padding: 8px 14px 4px;
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: #6b7280;
		background: #f8f8f8;
		border-bottom: 1px solid #eee;
	}
</style>

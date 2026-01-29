import { writable, get } from 'svelte/store';
import type { Component, Snippet } from 'svelte';

/**
 * A regular menu item with label, optional icon, and click handler
 */
export type DropdownMenuItemAction = {
	type?: 'item';
	id: string;
	label: string;
	icon?: Component;
	/** Optional description shown below the label */
	description?: string;
	/** Whether this item is currently selected/active */
	selected?: boolean;
	disabled?: boolean;
	onclick: () => void;
	/** data-testid for testing */
	testId?: string;
};

/**
 * A custom item that renders a snippet for full control
 */
export type DropdownMenuItemCustom = {
	type: 'custom';
	id: string;
	/** Snippet receives { close } function */
	render: Snippet<[{ close: () => void }]>;
	testId?: string;
};

/**
 * A divider between groups of items
 */
export type DropdownMenuItemDivider = {
	type: 'divider';
};

export type DropdownMenuItem = DropdownMenuItemAction | DropdownMenuItemCustom | DropdownMenuItemDivider;

export type DropdownMenuPlacement = 'below-left' | 'below-right' | 'above-left' | 'above-right';

export type DropdownMenuState = {
	visible: boolean;
	items: DropdownMenuItem[];
	position: { x: number; y: number };
	/** Which corner of the menu anchors to the position */
	anchor: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
	/** Optional test id for the menu container */
	testId?: string;
};

const initialState: DropdownMenuState = {
	visible: false,
	items: [],
	position: { x: 0, y: 0 },
	anchor: 'top-left'
};

export const dropdownMenuState = writable<DropdownMenuState>(initialState);

/**
 * Show the dropdown menu positioned relative to a trigger element
 */
export function showDropdownMenu(
	items: DropdownMenuItem[],
	element: HTMLElement,
	options?: {
		/** Where to position relative to element. Default: 'below-left' */
		placement?: DropdownMenuPlacement;
		/** data-testid for the menu container */
		testId?: string;
	}
): void {
	const rect = element.getBoundingClientRect();
	const placement = options?.placement ?? 'below-left';

	let position: { x: number; y: number };
	let anchor: DropdownMenuState['anchor'];

	switch (placement) {
		case 'below-left':
			position = { x: rect.left, y: rect.bottom };
			anchor = 'top-left';
			break;
		case 'below-right':
			position = { x: rect.right, y: rect.bottom };
			anchor = 'top-right';
			break;
		case 'above-left':
			position = { x: rect.left, y: rect.top };
			anchor = 'bottom-left';
			break;
		case 'above-right':
			position = { x: rect.right, y: rect.top };
			anchor = 'bottom-right';
			break;
	}

	dropdownMenuState.set({
		visible: true,
		items,
		position,
		anchor,
		testId: options?.testId
	});
}

/**
 * Show the dropdown menu at exact coordinates
 */
export function showDropdownMenuAt(
	items: DropdownMenuItem[],
	x: number,
	y: number,
	options?: {
		anchor?: DropdownMenuState['anchor'];
		testId?: string;
	}
): void {
	dropdownMenuState.set({
		visible: true,
		items,
		position: { x, y },
		anchor: options?.anchor ?? 'top-left',
		testId: options?.testId
	});
}

/**
 * Close the dropdown menu
 */
export function closeDropdownMenu(): void {
	dropdownMenuState.update(state => ({ ...state, visible: false }));
}

/**
 * Check if the menu is currently visible
 */
export function isDropdownMenuVisible(): boolean {
	return get(dropdownMenuState).visible;
}

/**
 * Toggle the dropdown menu - if visible, close it; if hidden, show it
 */
export function toggleDropdownMenu(
	items: DropdownMenuItem[],
	element: HTMLElement,
	options?: {
		placement?: DropdownMenuPlacement;
		testId?: string;
	}
): void {
	if (isDropdownMenuVisible()) {
		closeDropdownMenu();
	} else {
		showDropdownMenu(items, element, options);
	}
}

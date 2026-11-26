import { writable } from 'svelte/store';
import type { WorldView } from '$world/worldView';

/** The scene's rendered camera, like the terrain pane's viewport rect; cleared when the pane closes. */
export const worldView = writable<WorldView | null>(null);

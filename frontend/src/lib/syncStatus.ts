// Sync status reporting for upload progress.
// Provides stores that track whether the service worker or foreground
// upload loop is active, along with progress details. The main thread
// listens for SW status messages and exposes a combined derived store
// for UI consumption.

import { writable, derived, get } from 'svelte/store';

export interface SyncStatusReport {
	source: 'sw' | 'fg';
	timestamp: number;
	active: boolean;
	phase: 'idle' | 'starting' | 'uploading' | 'finished' | 'error';
	currentPhotoId: string | null;
	totalPending: number;
	successCount: number;
	failureCount: number;
	remainingCount: number;
	error?: string;
}

/** Callback that receives status updates from the upload loop */
export type StatusReporter = (status: SyncStatusReport) => void;

// ── Stores ──────────────────────────────────────────────────────────

/** Latest status report from the service worker upload loop */
export const swSyncStatus = writable<SyncStatusReport | null>(null);

/** Latest status report from the foreground upload loop */
export const fgSyncStatus = writable<SyncStatusReport | null>(null);

/** Combined view for UI consumption */
export const combinedSyncStatus = derived(
	[swSyncStatus, fgSyncStatus],
	([$sw, $fg]) => ({
		sw: $sw,
		fg: $fg,
		activeSource: $sw?.active ? ('sw' as const) : $fg?.active ? ('fg' as const) : null,
		isUploading: ($sw?.active ?? false) || ($fg?.active ?? false)
	})
);

// ── Window-exposed snapshots (debugging + Playwright tests) ─────────

if (typeof window !== 'undefined') {
	const w = window as any;
	w.__stores = w.__stores ?? {};
	w.__stores.fgSyncStatus = null;
	w.__stores.swSyncStatus = null;
	w.__stores.combinedSyncStatus = null;
	w.__stores.fgSyncHistory = [] as SyncStatusReport[];

	fgSyncStatus.subscribe((v) => {
		w.__stores.fgSyncStatus = v;
		if (v) w.__stores.fgSyncHistory.push(v);
	});
	swSyncStatus.subscribe((v) => { w.__stores.swSyncStatus = v; });
	combinedSyncStatus.subscribe((v) => { w.__stores.combinedSyncStatus = v; });
}

// ── Foreground reporter ─────────────────────────────────────────────

/** Creates a reporter that writes directly into the fgSyncStatus store */
export function createFgStatusReporter(): StatusReporter {
	return (status: SyncStatusReport) => {
		fgSyncStatus.set(status);
	};
}

// ── SW message listener ─────────────────────────────────────────────

let listenerInitialized = false;

/**
 * Registers a `message` listener on the SW container that routes
 * SYNC_STATUS messages into the swSyncStatus store.
 * Safe to call multiple times — only registers once.
 */
export function initSyncStatusListener(): void {
	if (listenerInitialized) return;
	if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;

	navigator.serviceWorker.addEventListener('message', (event) => {
		if (event.data?.type === 'SYNC_STATUS') {
			swSyncStatus.set(event.data.data as SyncStatusReport);
		}
	});

	listenerInitialized = true;
}

// ── SW liveness check ───────────────────────────────────────────────

/**
 * Returns true if the service worker recently reported upload activity.
 * Used by the probe-then-fallback logic to decide whether the SW is
 * handling uploads or we need to fall back to foreground.
 *
 * Considers the SW alive if it:
 * - Is actively uploading (active: true), OR
 * - Recently finished (phase: 'finished') — e.g. zero pending photos
 *   processed instantly before the probe timeout.
 *
 * In both cases the timestamp must be within the threshold.
 */
export function isSwAlive(thresholdMs = 1000): boolean {
	const status = get(swSyncStatus);
	if (!status) return false;
	const recent = Date.now() - status.timestamp < thresholdMs;
	if (!recent) return false;
	// Active upload OR recently completed — either proves the SW is functional
	return status.active || status.phase === 'finished';
}

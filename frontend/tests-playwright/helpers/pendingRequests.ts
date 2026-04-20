import type { Page, Request } from '@playwright/test';

export interface PendingRequestTracker {
	size(): number;
	snapshot(): Array<{ ageMs: number; method: string; resourceType: string; url: string }>;
	logSnapshot(prefix?: string): void;
}

/**
 * Track in-flight network requests on a page so that timeouts
 * (especially `waitForLoadState('networkidle')`) can report which
 * requests were still outstanding when the wait failed.
 */
export function trackPendingRequests(page: Page): PendingRequestTracker {
	const pending = new Map<Request, number>();
	page.on('request', (r) => pending.set(r, Date.now()));
	page.on('requestfinished', (r) => pending.delete(r));
	page.on('requestfailed', (r) => pending.delete(r));

	return {
		size: () => pending.size,
		snapshot: () => {
			const now = Date.now();
			return Array.from(pending, ([r, started]) => ({
				ageMs: now - started,
				method: r.method(),
				resourceType: r.resourceType(),
				url: r.url()
			}));
		},
		logSnapshot(prefix = '') {
			const snap = this.snapshot();
			console.log(`${prefix}${snap.length} still-inflight:`);
			for (const r of snap) {
				console.log(`   • ${r.ageMs}ms ${r.method} ${r.resourceType} ${r.url}`);
			}
		}
	};
}

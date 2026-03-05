// Service worker status reporter.
// Broadcasts SyncStatusReport to all open window clients via postMessage.

import type { StatusReporter, SyncStatusReport } from '$lib/syncStatus';

declare const self: ServiceWorkerGlobalScope;

/** Creates a reporter that broadcasts status to all window clients */
export function createSwStatusReporter(): StatusReporter {
	return (status: SyncStatusReport) => {
		self.clients.matchAll({ type: 'window' }).then((clients) => {
			for (const client of clients) {
				client.postMessage({ type: 'SYNC_STATUS', data: status });
			}
		});
	};
}

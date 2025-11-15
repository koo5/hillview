export interface ActivityLogEntry {
	timestamp: Date;
	message: string;
	type: 'success' | 'warning' | 'error' | 'info';
	metadata?: {
		operation?: 'upload' | 'delete' | 'import' | 'rate' | 'batch_complete';
		filename?: string;
		photo_id?: string;
		outcome?: 'success' | 'failure' | 'complete';
	};
}

export type LogEntryCallback = (
	message: string,
	type: 'success' | 'warning' | 'error' | 'info',
	metadata?: ActivityLogEntry['metadata']
) => void;
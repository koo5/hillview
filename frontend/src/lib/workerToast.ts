/**
 * Worker toast helper - posts toast messages to main thread
 * Used by workers to trigger toast notifications in the UI
 */

export interface WorkerToastMessage {
  type: 'toast';
  level: 'error' | 'warning' | 'info' | 'success';
  message: string;
  source: string;
  duration?: number; // 0 for persistent
}

/**
 * Post a toast message from worker context to main thread
 */
export function postToast(
  level: WorkerToastMessage['level'],
  message: string,
  source: string,
  duration?: number
): void {
  if (typeof postMessage === 'function') {
    postMessage({
      type: 'toast',
      level,
      message,
      source,
      duration
    } as WorkerToastMessage);
  }
}
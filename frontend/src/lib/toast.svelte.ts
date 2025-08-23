/**
 * Toast notification system for user feedback
 */

import { writable } from 'svelte/store';

export interface Toast {
  id: string;
  message: string;
  type: 'error' | 'warning' | 'info' | 'success';
  duration?: number; // Auto-dismiss time in ms, or 0 for persistent
  source?: string; // Source identifier for deduplication
}

// Store for active toasts
export const toasts = writable<Toast[]>([]);

let toastIdCounter = 0;

/**
 * Add a new toast notification
 */
export function addToast(
  message: string, 
  type: Toast['type'] = 'info',
  duration: number = 5000,
  source?: string
): string {
  const id = `toast-${++toastIdCounter}-${Date.now()}`;
  
  const toast: Toast = {
    id,
    message,
    type,
    duration,
    source
  };

  // Remove any existing toasts from the same source if this is an error/warning
  if (source && (type === 'error' || type === 'warning')) {
    toasts.update(current => current.filter(t => t.source !== source || (t.type !== 'error' && t.type !== 'warning')));
  }

  toasts.update(current => [...current, toast]);

  // Auto-dismiss after duration (unless duration is 0)
  if (duration > 0) {
    setTimeout(() => {
      removeToast(id);
    }, duration);
  }

  return id;
}

/**
 * Remove a toast by ID
 */
export function removeToast(id: string): void {
  toasts.update(current => current.filter(toast => toast.id !== id));
}

/**
 * Remove all toasts from a specific source
 */
export function removeToastsBySource(source: string): void {
  toasts.update(current => current.filter(toast => toast.source !== source));
}

/**
 * Clear all toasts
 */
export function clearToasts(): void {
  toasts.update(() => []);
}

/**
 * Network-specific helpers
 */
export function showNetworkError(message: string, source: string): string {
  return addToast(`${source}: ${message}`, 'error', 0, source); // Persistent
}

export function showConnectionRestored(source: string): string {
  // Clear any existing error toasts for this source
  removeToastsBySource(source);
  return addToast(`Connection restored to ${source}`, 'success', 3000, source);
}
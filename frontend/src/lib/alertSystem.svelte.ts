/**
 * Unified Alert System - Replaces the toast system with a more powerful alert area
 * Supports priority queues, click-to-fade, auto-dismiss, and multiple alert types
 */

import { writable } from 'svelte/store';
import { logout } from './auth.svelte';

export interface Alert {
  id: string;
  message: string;
  type: 'error' | 'warning' | 'info' | 'success';
  priority: number; // Higher = more important (0-10)
  duration?: number; // Auto-dismiss time in ms, or 0 for persistent
  source?: string; // Source identifier for deduplication
  actions?: AlertAction[];
  dismissible?: boolean; // Can be manually dismissed
  retryable?: boolean; // Show retry button
  onRetry?: () => void;
  createdAt: Date;
  faded?: boolean; // Temporarily hidden via click-to-fade
}

export interface AlertAction {
  label: string;
  action: () => void;
  style?: 'primary' | 'secondary' | 'danger';
}

// Store for active alerts - only the highest priority alert is visible
export const alerts = writable<Alert[]>([]);

// Store for current visible alert
export const currentAlert = writable<Alert | null>(null);

let alertIdCounter = 0;

/**
 * Add a new alert to the system
 */
export function addAlert(
  message: string,
  type: Alert['type'] = 'info',
  options: {
    priority?: number;
    duration?: number;
    source?: string;
    actions?: AlertAction[];
    dismissible?: boolean;
    retryable?: boolean;
    onRetry?: () => void;
  } = {}
): string {
  const id = `alert-${++alertIdCounter}-${Date.now()}`;
  
  const alert: Alert = {
    id,
    message,
    type,
    priority: options.priority ?? getDefaultPriority(type),
    duration: options.duration ?? getDefaultDuration(type),
    source: options.source,
    actions: options.actions,
    dismissible: options.dismissible ?? true,
    retryable: options.retryable ?? false,
    onRetry: options.onRetry,
    createdAt: new Date(),
    faded: false
  };

  // Remove any existing alerts from the same source if this is higher priority
  if (options.source) {
    alerts.update(current => current.filter(a => 
      a.source !== options.source || a.priority <= alert.priority
    ));
  }

  alerts.update(current => {
    const newAlerts = [...current, alert];
    // Sort by priority (highest first), then by creation time (newest first)
    newAlerts.sort((a, b) => {
      if (a.priority !== b.priority) return b.priority - a.priority;
      return b.createdAt.getTime() - a.createdAt.getTime();
    });
    return newAlerts;
  });

  // Update current alert to highest priority non-faded alert
  updateCurrentAlert();

  // Auto-dismiss after duration (unless duration is 0)
  if (alert.duration && alert.duration > 0) {
    setTimeout(() => {
      removeAlert(id);
    }, alert.duration);
  }

  return id;
}

/**
 * Remove an alert by ID
 */
export function removeAlert(id: string): void {
  alerts.update(current => {
    const filtered = current.filter(alert => alert.id !== id);
    return filtered;
  });
  updateCurrentAlert();
}

/**
 * Remove all alerts from a specific source
 */
export function removeAlertsBySource(source: string): void {
  alerts.update(current => current.filter(alert => alert.source !== source));
  updateCurrentAlert();
}

/**
 * Temporarily fade an alert (click-to-fade behavior)
 */
export function fadeAlert(id: string): void {
  alerts.update(current => 
    current.map(alert => 
      alert.id === id ? { ...alert, faded: true } : alert
    )
  );
  updateCurrentAlert();
}

/**
 * Unfade an alert
 */
export function unfadeAlert(id: string): void {
  alerts.update(current => 
    current.map(alert => 
      alert.id === id ? { ...alert, faded: false } : alert
    )
  );
  updateCurrentAlert();
}

/**
 * Clear all alerts
 */
export function clearAlerts(): void {
  alerts.update(() => []);
  currentAlert.set(null);
}

/**
 * Update the current visible alert to the highest priority non-faded alert
 */
function updateCurrentAlert(): void {
  alerts.subscribe(allAlerts => {
    const visibleAlert = allAlerts.find(alert => !alert.faded) || null;
    currentAlert.set(visibleAlert);
  })();
}

/**
 * Get default priority based on alert type
 */
function getDefaultPriority(type: Alert['type']): number {
  switch (type) {
    case 'error': return 8;
    case 'warning': return 6;
    case 'success': return 4;
    case 'info': return 2;
    default: return 2;
  }
}

/**
 * Get default duration based on alert type
 */
function getDefaultDuration(type: Alert['type']): number {
  switch (type) {
    case 'error': return 0; // Persistent
    case 'warning': return 8000;
    case 'success': return 3000;
    case 'info': return 5000;
    default: return 5000;
  }
}

/**
 * Convenience functions for common alert patterns
 */

export function showNetworkError(message: string, source: string, onRetry?: () => void): string {
  return addAlert(message, 'error', {
    priority: 9,
    duration: 0, // Persistent
    source,
    retryable: !!onRetry,
    onRetry
  });
}

export function showConnectionRestored(source: string): string {
  // Clear any existing error alerts for this source
  removeAlertsBySource(source);
  return addAlert(`Connection restored`, 'success', {
    priority: 5,
    duration: 3000,
    source
  });
}

export function showTokenRefreshIssue(message: string, onRetry?: () => void): string {
  return addAlert(message, 'warning', {
    priority: 7,
    duration: 0, // Persistent until resolved
    source: 'token_refresh',
    retryable: !!onRetry,
    onRetry,
    actions: onRetry ? [
      { label: 'Retry', action: onRetry, style: 'primary' },
      { label: 'Logout', action: () => logout('Authentication failed'), style: 'danger' }
    ] : undefined
  });
}

export function showUploadProgress(message: string, source: string): string {
  return addAlert(message, 'info', {
    priority: 3,
    duration: 0, // Persistent until upload completes
    source,
    dismissible: false // Can't dismiss active uploads
  });
}

export function showUploadComplete(filename: string, source: string): string {
  // Clear upload progress for this source
  removeAlertsBySource(source);
  return addAlert(`Uploaded: ${filename}`, 'success', {
    priority: 4,
    duration: 3000,
    source
  });
}

// Legacy toast compatibility layer
export function addToast(
  message: string,
  type: Alert['type'] = 'info', 
  duration: number = 5000,
  source?: string
): string {
  return addAlert(message, type, { duration, source });
}
import { describe, expect, test } from 'vitest';
import { shouldRefreshActivityFromNotification } from './notificationRouteUtils';

describe('shouldRefreshActivityFromNotification', () => {
	test('returns true when already on /activity and notification route is /activity', () => {
		expect(shouldRefreshActivityFromNotification('/activity', '/activity')).toBe(true);
	});

	test('returns true when notification route has query string but activity path matches', () => {
		expect(shouldRefreshActivityFromNotification('/activity', '/activity?from=notification')).toBe(true);
	});

	test('returns true with trailing slashes on current path and route', () => {
		expect(shouldRefreshActivityFromNotification('/activity/', '/activity//')).toBe(true);
	});

	test('returns false for empty or non-activity paths', () => {
		expect(shouldRefreshActivityFromNotification('', '/activity')).toBe(false);
		expect(shouldRefreshActivityFromNotification('/activity', '')).toBe(false);
	});

	test('returns false when current page is not /activity', () => {
		expect(shouldRefreshActivityFromNotification('/settings', '/activity')).toBe(false);
	});

	test('returns false when notification route is not /activity', () => {
		expect(shouldRefreshActivityFromNotification('/activity', '/settings')).toBe(false);
	});
});

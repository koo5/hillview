export const ACTIVITY_NOTIFICATION_REFRESH_EVENT = 'activity-notification-refresh';

function normalizePath(path: string): string {
	const [pathname] = path.split('?');
	if (!pathname) return '/';
	return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;
}

export function shouldRefreshActivityFromNotification(currentPath: string, route: string): boolean {
	return normalizePath(currentPath) === '/activity' && normalizePath(route) === '/activity';
}

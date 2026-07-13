import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { callAdminAPI, getUserToken, BACKEND_URL } from './helpers/adminAuth';

type Page = import('@playwright/test').Page;

/** Open the nav drawer from any page (map uses hamburger-menu, sub-pages use header-menu-button). */
async function openMenu(page: Page) {
	const menuButton = page.locator('[data-testid="header-menu-button"], [data-testid="hamburger-menu"]').first();
	await menuButton.click();
	await expect(page.getByTestId('nav-menu')).toBeVisible();
}

/** Submit a contact message via the public API so the admin counts are non-zero. */
async function seedContactMessage() {
	const res = await fetch(`${BACKEND_URL}/api/contact`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ contact: 'admin-e2e@example.com', message: 'Admin dashboard e2e seed message.' }),
	});
	if (!res.ok) throw new Error(`Failed to seed contact message: ${res.status}`);
}

test.describe('Admin dashboard', () => {
	test('regular user sees no Admin menu item and /admin is forbidden', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);

		await page.goto('/bestof');
		await openMenu(page);
		await expect(page.getByTestId('nav-admin-link')).toHaveCount(0);
		// A non-admin never sees the badge, anywhere (and the client never polls it).
		await expect(page.getByTestId('admin-notification-badge')).toHaveCount(0);

		await page.goto('/admin');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-card-contact')).toHaveCount(0);
	});

	test('anonymous user is forbidden from /admin', async ({ page }) => {
		await page.goto('/admin');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-card-contact')).toHaveCount(0);
	});

	test('admin opens the dashboard from the menu and sees live counts', async ({ page, testUsers }) => {
		await seedContactMessage();

		// The numbers the badge and dashboard should show, straight from the API they poll.
		const counts = await (await callAdminAPI('/api/admin/notifications', testUsers.passwords.admin)).json();
		expect(counts.contact_new).toBeGreaterThan(0);

		await loginAs(page, 'admin', testUsers.passwords.admin);

		// On the map, the hamburger carries the summed badge once the counts load.
		await expect(
			page.locator('[data-testid="hamburger-menu"] [data-testid="admin-notification-badge"]')
		).toBeVisible({ timeout: T(15000) });

		// The Admin item appears in the menu and navigates to the dashboard.
		await openMenu(page);
		const adminLink = page.getByTestId('nav-admin-link');
		await expect(adminLink).toBeVisible();
		await adminLink.click();
		await page.waitForURL('/admin', { timeout: T(10000) });

		// Dashboard shows the same counts the API reports.
		await expect(page.getByTestId('admin-dashboard')).toBeVisible();
		await expect(page.getByTestId('admin-count-contact')).toHaveText(String(counts.contact_new), { timeout: T(15000) });
		await expect(page.getByTestId('admin-count-flags')).toHaveText(String(counts.flags_open));
		await expect(page.getByTestId('admin-card-annotations')).toBeVisible();
		await expect(page.getByTestId('admin-card-audit')).toBeVisible();
	});

	test('dashboard shows a merged, squashed activity feed', async ({ page, testUsers }) => {
		const token = await getUserToken('test', testUsers.passwords.test);

		// A contact message, then a burst of 3 flags (newest, consecutive) — the
		// burst should collapse into a single "flagged 3 photos" row.
		await fetch(`${BACKEND_URL}/api/contact`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ contact: 'feed-e2e@example.com', message: 'Merged feed e2e contact message.' }),
		});
		for (let i = 0; i < 3; i++) {
			const r = await fetch(`${BACKEND_URL}/api/flagged/photos`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
				body: JSON.stringify({ photo_source: 'mapillary', photo_id: `feed-flag-${Date.now()}-${i}`, reason: 'feed e2e' }),
			});
			if (!r.ok) throw new Error(`seed flag failed: ${r.status}`);
		}

		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto('/admin');

		await expect(page.getByTestId('admin-activity')).toBeVisible();
		await expect(page.getByTestId('admin-activity-item').first()).toBeVisible({ timeout: T(15000) });

		// The 3-flag burst is squashed into one row, and 'test' (an ordinary user)
		// is highlighted.
		const flagItem = page.locator('[data-testid="admin-activity-item"][data-kind="flag"]').first();
		await expect(flagItem).toContainText('flagged 3 photos');
		await expect(flagItem.getByTestId('admin-activity-actor')).toHaveClass(/ordinary/);

		// Contact events are present and their row links to the contact page.
		const contactItem = page.locator('[data-testid="admin-activity-item"][data-kind="contact"]').first();
		await expect(contactItem).toBeVisible();
		await contactItem.click();
		await page.waitForURL('/admin/contact', { timeout: T(10000) });
	});
});

import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { callAdminAPI, getUserToken, BACKEND_URL } from './helpers/adminAuth';

/** Submit a contact message via the public API; returns its id. */
async function seedContact(contactInfo: string): Promise<number> {
	const res = await fetch(`${BACKEND_URL}/api/contact`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ contact: contactInfo, message: `Message for ${contactInfo} — admin-contact e2e.` }),
	});
	if (!res.ok) throw new Error(`Failed to seed contact message: ${res.status}`);
	return (await res.json()).id as number;
}

async function contactNewCount(adminPassword: string): Promise<number> {
	const res = await callAdminAPI('/api/admin/notifications', adminPassword);
	return (await res.json()).contact_new as number;
}

test.describe('Admin contact management', () => {
	test('marking a message read removes it from the New list and drops the count', async ({ page, testUsers }) => {
		// Use a distinct id-based marker so this row is unambiguous amid shared state.
		const id = await seedContact(`mark-read-${await contactNewCount(testUsers.passwords.admin)}@example.com`);
		const before = await contactNewCount(testUsers.passwords.admin);

		await loginAs(page, 'admin', testUsers.passwords.admin);

		// Navigate to the contact page via the dashboard card (verifies the link).
		await page.goto('/admin');
		await page.getByTestId('admin-card-contact').click();
		await page.waitForURL('/admin/contact', { timeout: T(10000) });

		// The seeded message shows in the default "New" filter, status 'new'.
		const row = page.locator(`[data-testid="admin-contact-message"][data-message-id="${id}"]`);
		await expect(row).toBeVisible({ timeout: T(15000) });
		await expect(row.getByTestId('admin-contact-status')).toHaveText('new');

		// Mark it read → it leaves the "New" list.
		await row.getByTestId('admin-contact-mark-read').click();
		await expect(row).toHaveCount(0, { timeout: T(15000) });

		// The backend unhandled-count dropped by exactly one.
		expect(await contactNewCount(testUsers.passwords.admin)).toBe(before - 1);

		// Under "All" it still exists, now marked read.
		await page.getByTestId('admin-contact-filter-all').click();
		const allRow = page.locator(`[data-testid="admin-contact-message"][data-message-id="${id}"]`);
		await expect(allRow).toBeVisible({ timeout: T(15000) });
		await expect(allRow.getByTestId('admin-contact-status')).toHaveText('read');
	});

	test('non-admin is forbidden at /admin/contact', async ({ page, testUsers }) => {
		await loginAs(page, 'test', testUsers.passwords.test);
		await page.goto('/admin/contact');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-contact-message')).toHaveCount(0);
	});

	test('a registered sender shows their username as a link to their profile', async ({ page, testUsers }) => {
		// Submit as 'test' (authenticated) so the message carries a real account.
		const testToken = await getUserToken('test', testUsers.passwords.test);
		const marker = `reg-sender-${Date.now()}`;
		const res = await fetch(`${BACKEND_URL}/api/contact`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${testToken}` },
			body: JSON.stringify({ contact: `${marker}@example.com`, message: `Registered sender message ${marker}.` }),
		});
		expect(res.ok).toBeTruthy();

		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto('/admin/contact');

		const row = page.locator('[data-testid="admin-contact-message"]', { hasText: marker });
		await expect(row).toBeVisible({ timeout: T(15000) });

		// The real account username shows, as a link to the user's profile.
		const link = row.getByTestId('admin-contact-user-link');
		await expect(link).toHaveText('test');
		await expect(link).toHaveAttribute('href', /^\/users\//);

		await link.click();
		await page.waitForURL(/\/users\//, { timeout: T(10000) });
	});
});

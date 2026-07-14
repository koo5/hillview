import { T } from './helpers/timeouts';
import { test, expect } from './fixtures';
import { loginAs } from './helpers/testUsers';
import { getUserToken } from './helpers/adminAuth';

test.describe('Admin user management', () => {
	test('admin can change a role, suspend, and delete a user', async ({ page, testUsers }) => {
		await loginAs(page, 'admin', testUsers.passwords.admin);

		// Reach the page via the dashboard card (verifies the link).
		await page.goto('/admin');
		await page.getByTestId('admin-card-users').click();
		await page.waitForURL('/admin/users', { timeout: T(10000) });

		const row = page.locator('[data-testid="admin-user-row"][data-username="testuser"]');
		await expect(row).toBeVisible({ timeout: T(15000) });

		// Change role → moderator.
		await row.getByTestId('admin-user-role-select').selectOption('moderator');
		await expect(row).toHaveAttribute('data-role', 'moderator', { timeout: T(10000) });

		// Suspend → blocks that user's login.
		await row.getByTestId('admin-user-suspend').click();
		await expect(row.getByTestId('admin-user-status')).toHaveText('suspended', { timeout: T(10000) });
		await expect(getUserToken('testuser', testUsers.passwords.testuser)).rejects.toThrow();

		// Delete → gone from the list.
		await row.getByTestId('admin-user-delete').click();
		await expect(page.getByTestId('admin-user-delete-dialog')).toBeVisible();
		await page.getByTestId('admin-user-delete-confirm').click();
		await expect(row).toHaveCount(0, { timeout: T(15000) });
	});

	test('an admin cannot modify their own account', async ({ page, testUsers }) => {
		await loginAs(page, 'admin', testUsers.passwords.admin);
		await page.goto('/admin/users');

		const selfRow = page.locator('[data-testid="admin-user-row"][data-username="admin"]');
		await expect(selfRow).toBeVisible({ timeout: T(15000) });
		await expect(selfRow.getByTestId('admin-user-self')).toBeVisible();
		// No role dropdown, suspend, or delete on your own row.
		await expect(selfRow.getByTestId('admin-user-role-select')).toHaveCount(0);
		await expect(selfRow.getByTestId('admin-user-delete')).toHaveCount(0);
	});

	test('non-admin is forbidden at /admin/users', async ({ page, testUsers }) => {
		await loginAs(page, 'moderator', testUsers.passwords.moderator);
		await page.goto('/admin/users');
		await expect(page.getByTestId('admin-forbidden')).toBeVisible({ timeout: T(15000) });
		await expect(page.getByTestId('admin-user-row')).toHaveCount(0);
	});
});

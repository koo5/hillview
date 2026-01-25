import { test, expect } from '@playwright/test';
import { createTestUsers, loginAsTestUser } from './helpers/testUsers';
import { callAdminAPI } from './helpers/adminAuth';

test.describe('Contact Form', () => {
  test.beforeEach(async ({ page }) => {
    // Clean up test users before each test
    const response = await fetch('http://localhost:8055/api/debug/recreate-test-users', {
      method: 'POST'
    });
    const result = await response.json();
    console.log('🢄Test cleanup result:', result);
  });

  test('should submit contact form as logged-in user and verify via admin endpoint', async ({ page }) => {
    // Create test users for this test
    const result = await createTestUsers();
    const testPassword = result.passwords.test;
    const adminPassword = result.passwords.admin;

    // Login as test user
    await loginAsTestUser(page, testPassword);

    // Give auth state time to settle after login
    await page.waitForTimeout(1000);

    // Navigate to contact page
    await page.goto('/contact');
    await page.waitForLoadState('networkidle');

    // Verify user is properly logged in - this should NOT be a guest
    const isLoggedIn = await page.locator('.user-info').isVisible();
    const isGuest = await page.locator('.guest-info').isVisible();

    console.log('Auth state check:', { isLoggedIn, isGuest });

    // FAIL the test if user is not logged in after login
    expect(isLoggedIn).toBe(true);
    expect(isGuest).toBe(false);

    // Should see "Sending as: test"
    await expect(page.locator('text=Sending as:')).toBeVisible();
    await expect(page.locator('strong:has-text("test")')).toBeVisible();

    // Fill out contact form
    const contactInfo = 'test@example.com';
    const message = 'This is a test message from the automated test suite. Please verify that the user_id is correctly captured.';

    await page.fill('input[id="contact"]', contactInfo);
    await page.fill('textarea[id="message"]', message);

    // Submit the form
    await page.click('button[type="submit"]');

    // Wait for success message
    await expect(page.locator('text=Message Sent!')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Thank you for contacting us')).toBeVisible();

    // Now verify the message was stored correctly via admin endpoint
    const adminResponse = await callAdminAPI('/api/admin/contact/messages', adminPassword);
    const adminData = await adminResponse.json();

    expect(adminResponse.status).toBe(200);
    expect(adminData.messages).toBeDefined();
    expect(adminData.messages.length).toBeGreaterThan(0);

    // Find our test message
    const testMessage = adminData.messages.find((msg: any) =>
      msg.contact_info === contactInfo && msg.message.includes('automated test suite')
    );

    expect(testMessage).toBeDefined();
    expect(testMessage.contact_info).toBe(contactInfo);
    expect(testMessage.message).toContain('automated test suite');
    expect(testMessage.user_id).toBeTruthy(); // This is what we're testing - user_id should be set
    expect(testMessage.status).toBe('new');
    expect(testMessage.ip_address).toBeTruthy();

    console.log('✅ Contact message verified:', {
      id: testMessage.id,
      user_id: testMessage.user_id,
      contact_info: testMessage.contact_info,
      message_preview: testMessage.message.substring(0, 50) + '...',
      status: testMessage.status
    });
  });

  test('should submit contact form as guest user', async ({ page }) => {
    // Don't login - test as guest
    await page.goto('/contact');
    await page.waitForLoadState('networkidle');

    // Verify user is NOT logged in (should show guest message)
    await expect(page.locator('text=You\'re sending this message as a guest')).toBeVisible();
    await expect(page.locator('a[href="/login"]')).toBeVisible();

    // Fill out contact form
    const contactInfo = 'guest@example.com';
    const message = 'This is a test message from a guest user. The user_id should be null.';

    await page.fill('input[id="contact"]', contactInfo);
    await page.fill('textarea[id="message"]', message);

    // Submit the form
    await page.click('button[type="submit"]');

    // Wait for success message
    await expect(page.locator('text=Message Sent!')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Thank you for contacting us')).toBeVisible();

    // Create test users to get admin access
    const result = await createTestUsers();
    const adminPassword = result.passwords.admin;

    // Verify message via admin API
    const adminResponse = await callAdminAPI('/api/admin/contact/messages', adminPassword);
    const adminData = await adminResponse.json();

    expect(adminResponse.status).toBe(200);

    // Find our guest message
    const guestMessage = adminData.messages.find((msg: any) =>
      msg.contact_info === contactInfo && msg.message.includes('guest user')
    );

    expect(guestMessage).toBeDefined();
    expect(guestMessage.contact_info).toBe(contactInfo);
    expect(guestMessage.message).toContain('guest user');
    expect(guestMessage.user_id).toBeNull(); // Guest users should have null user_id
    expect(guestMessage.status).toBe('new');
    expect(guestMessage.ip_address).toBeTruthy();

    console.log('✅ Guest contact message verified:', {
      id: guestMessage.id,
      user_id: guestMessage.user_id,
      contact_info: guestMessage.contact_info,
      message_preview: guestMessage.message.substring(0, 50) + '...',
      status: guestMessage.status
    });
  });

  test('should validate form fields', async ({ page }) => {
    await page.goto('/contact');
    await page.waitForLoadState('networkidle');

    const submitButton = page.locator('button[type="submit"]');

    // Empty form - button should be disabled
    await expect(submitButton).toBeDisabled();

    // Fill contact but leave message empty - button should still be disabled
    await page.fill('input[id="contact"]', 'test@example.com');
    await expect(submitButton).toBeDisabled();

    // Fill message too short - button is enabled but validation should fail on submit
    await page.fill('textarea[id="message"]', 'short');
    await expect(submitButton).toBeEnabled();
    await submitButton.click();
    await expect(page.locator('text=Message must be at least 10 characters long')).toBeVisible();

    // Fill valid form
    await page.fill('textarea[id="message"]', 'This is a valid message with enough characters.');
    await submitButton.click();

    // Should succeed now
    await expect(page.locator('text=Message Sent!')).toBeVisible({ timeout: 10000 });
  });
});
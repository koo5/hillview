import {expect} from '@wdio/globals'
import {TestWorkflows} from '../helpers/TestWorkflows'
import {ScreenshotHelper} from '../helpers/ScreenshotHelper'

/**
 * Android Photo Import Test
 *
 * Tests the photo import functionality using the device file picker
 * This test verifies the fix for the photo picker result callback integration
 */
describe('Android Photo Import', () => {
	let workflows: TestWorkflows;
	let screenshots: ScreenshotHelper;

	beforeEach(async function () {
		this.timeout(130000);

		// Initialize helpers
		workflows = new TestWorkflows();
		screenshots = new ScreenshotHelper('photo-import');
		screenshots.reset();

		console.log('🧪 Starting photo import test with clean app state');
	});

	describe('Photo Import from Device', () => {
		it('should login and successfully import photos from device', async function () {
			this.timeout(180000);

			console.log('📂 Testing complete photo import workflow...');

			try {
				await screenshots.takeScreenshot('initial-state');

				// Step 1: Create test users and get password
				const testPassword = await workflows.createTestUsers();
				
				// Step 2: Login
				const loginSuccess = await workflows.quickLogin('test', testPassword);
				expect(loginSuccess).toBe(true);
				await screenshots.takeScreenshot('login-complete');

				// Step 2: Complete photo import workflow
				const importSuccess = await workflows.performPhotoImportWorkflow();
				expect(importSuccess).toBe(true);
				await screenshots.takeScreenshot('import-complete');

				console.log('✅ Photo import test completed successfully!');

			} catch (error) {
				console.error('❌ Photo import test failed:', error);
				await screenshots.takeScreenshot('error-state');
				throw error;
			}
		});

		it('should handle file picker cancellation gracefully', async function () {
			this.timeout(120000);

			console.log('❌ Testing file picker cancellation...');

			try {
				// Create test users and login
				const testPassword = await workflows.createTestUsers();
				const loginSuccess = await workflows.quickLogin('test', testPassword);
				expect(loginSuccess).toBe(true);

				const navigationSuccess = await workflows.navigateToPhotoImport();
				expect(navigationSuccess).toBe(true);

				// Click import button to open file picker
				const importButton = await $('[data-testid="import-from-device-button"]');
				await importButton.waitForDisplayed({timeout: 10000});
				await importButton.click();
				console.log('📂 Opened file picker');

				await driver.pause(2000);

				// Cancel the file picker
				const cancelSuccess = await workflows.cancelFilePicker();
				expect(cancelSuccess).toBe(true);

				await driver.pause(2000);

				// Verify import button is still functional
				const importButtonAfter = await $('[data-testid="import-from-device-button"]');
				const isEnabled = await importButtonAfter.isEnabled();
				expect(isEnabled).toBe(true);

				console.log('✅ File picker cancellation handled correctly');

			} catch (error) {
				console.error('❌ Cancellation test failed:', error);
				await screenshots.takeScreenshot('cancellation-error');
				throw error;
			}
		});
	});
});
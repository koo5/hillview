import {expect} from '@wdio/globals'
import {TestWorkflows} from '../helpers/TestWorkflows'
import {ScreenshotHelper} from '../helpers/ScreenshotHelper'
import {CameraWorkflowHelper} from '../helpers/CameraWorkflowHelper'

/**
 * Android Photo Capture Test
 *
 * Tests the complete login and photo capture workflow using in-app camera
 */
describe('Android Photo Capture', () => {
	let workflows: TestWorkflows;
	let screenshots: ScreenshotHelper;
	let cameraWorkflow: CameraWorkflowHelper;

	beforeEach(async function () {
		this.timeout(130000);

		// Initialize helpers
		workflows = new TestWorkflows();
		screenshots = new ScreenshotHelper('photo-capture');
		cameraWorkflow = new CameraWorkflowHelper();
		screenshots.reset();

		// Clean app state is now automatically provided by wdio.conf.ts beforeTest hook
		console.log('🧪 Starting photo capture test with clean app state');
	});

	describe('Complete Photo Workflow', () => {
		it('should login and capture a photo with upload verification', async function () {
			this.timeout(180000);

			console.log('🔐📸 Testing login and photo capture workflow...');

			try {
				// Take screenshot of initial state
				await screenshots.takeScreenshot('initial-state');

				// Step 1: Login to the app
				console.log('🔐 Starting login process...');

				// Find the hamburger menu button
				const hamburgerMenu = await $('android=new UiSelector().text("Toggle menu")');
				await hamburgerMenu.waitForDisplayed({timeout: 10000});
				console.log('✅ Found hamburger menu');

				// Click hamburger menu to open it
				await hamburgerMenu.click();
				await driver.pause(2000);
				console.log('🍔 Opened hamburger menu');

				// Take screenshot of open menu
				await screenshots.takeScreenshot('menu-open');

				// Switch to WebView context to access login link
				const contexts = await driver.getContexts();
				const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));

				if (webViewContexts.length > 0) {
					await driver.switchContext(webViewContexts[0]);
					console.log('🌐 Switched to WebView context for login');

					// Look for login link
					try {
						const loginLink = await $('a[href="/login"]');
						const loginVisible = await loginLink.isDisplayed();

						if (loginVisible) {
							console.log('🔐 Found login link, clicking...');
							await loginLink.click();
							await driver.pause(3000);

							// Take screenshot of login page
							await screenshots.takeScreenshot('login-page');

							// Fill in login credentials
							const usernameInput = await $('input[type="text"]');
							await usernameInput.waitForDisplayed({timeout: 10000});
							await usernameInput.setValue('test');
							console.log('✅ Entered username');

							const passwordInput = await $('input[type="password"]');
							await passwordInput.setValue('test123');
							console.log('✅ Entered password');

							const submitButton = await $('button[type="submit"]');
							await submitButton.click();
							console.log('🔐 Submitted login form');

							// Wait for redirect back to main page
							await driver.pause(5000);

							console.log('✅ Login completed');
						} else {
							console.log('ℹ️ User may already be logged in');
						}
					} catch (e) {
						console.log('ℹ️ Could not find login link, user may already be logged in');
					}

					// Switch back to native context
					await driver.switchContext('NATIVE_APP');
					console.log('↩️ Switched back to native context');
				} else {
					console.log('⚠️ No WebView context found for login');
				}

				// Close menu if still open
				await driver.back();
				await driver.pause(2000);

				// Take screenshot before camera workflow
				await screenshots.takeScreenshot('before-camera');

				// Perform complete photo capture workflow using the helper
				const photoSuccess = await cameraWorkflow.performCompletePhotoCapture();
				
				// Take screenshot after camera workflow
				await screenshots.takeScreenshot('after-camera');
				
				if (!photoSuccess) {
					throw new Error('Photo capture workflow failed');
				}
				
				console.log('✅ Photo capture workflow completed successfully');

				const appHealthy = await workflows.performQuickHealthCheck();
				expect(appHealthy).toBe(true);

			} catch (error) {
				console.error('❌ Photo capture workflow failed:', error);
				await screenshots.takeScreenshot('error-state');
				throw error;
			}
		});
	});

	afterEach(async function () {
		// Take final screenshot
		await screenshots.takeScreenshot('cleanup');
		console.log('📸 Photo capture test cleanup completed');
	});
});

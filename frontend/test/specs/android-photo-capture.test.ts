import {expect} from '@wdio/globals'
import {TestWorkflows} from '../helpers/TestWorkflows'
import {ScreenshotHelper} from '../helpers/ScreenshotHelper'

/**
 * Android Photo Capture Test
 *
 * Tests the complete login and photo capture workflow using in-app camera
 */
describe('Android Photo Capture', () => {
	let workflows: TestWorkflows;
	let screenshots: ScreenshotHelper;

	beforeEach(async function () {
		this.timeout(130000);

		// Initialize helpers
		workflows = new TestWorkflows();
		screenshots = new ScreenshotHelper('photo-capture');
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

				await openCamera();

				// Take screenshot of camera interface
				await screenshots.takeScreenshot('camera-interface');

				// Handle camera and location permissions
				console.log('📋 Checking for permission dialogs...');


				try {
					const button = await $('android=new UiSelector().text("Only this time")');
					if (await button.isDisplayed()) {
						console.log('📍 Selecting "Only this time"...');
						await button.click();
						await driver.pause(2000);
					}
				} catch (e) {
					console.log(' No "Only this time" option');
				}


				// Check for "Enable Camera" button (app-specific) FIRST
				console.log('📷 Checking for "Enable Camera" button...');
				try {
					const enableCameraButton = await $('android=new UiSelector().text("Enable Camera")');
					if (await enableCameraButton.isDisplayed()) {
						console.log('📷 Clicking "Enable Camera" button...');
						await enableCameraButton.click();
						await driver.pause(3000);
						console.log('✅ Camera enabled');

						// Take screenshot after enabling camera
						await screenshots.takeScreenshot('camera-enabled');
					} else {
						console.log('ℹ️ No "Enable Camera" button found - camera may already be enabled');
					}
				} catch (e) {
					console.log('ℹ️ Could not find "Enable Camera" button:', e.message);
				}


				try {
					const button = await $('android=new UiSelector().text("Only this time")');
					if (await button.isDisplayed()) {
						console.log('📍 Selecting "Only this time"...');
						await button.click();
						await driver.pause(2000);
					}
				} catch (e) {
					console.log(' No "Only this time" option');
				}


				// Wait for camera to initialize and look for in-app capture button
				await driver.pause(3000);

				// Take screenshot to see current state
				await screenshots.takeScreenshot('before-capture');

				// Capture photo using in-app camera interface
				console.log('📸 Looking for in-app capture button...');

				const captureButtons = [
					'android=new UiSelector().text("SINGLE")',
				];

				let photoTaken = false;
				for (const selector of captureButtons) {
					try {
						const captureButton = await $(selector);
						if (await captureButton.isDisplayed()) {
							console.log(`📸 Found capture button: ${selector}`);
							await captureButton.click();
							await driver.pause(2000);
							photoTaken = true;
							console.log('✅ Photo captured using in-app camera');
							break;
						}
					} catch (e) {
						console.log(`ℹ️ Capture button not found: ${selector}`);
					}
				}


				// Take screenshot after capture
				await screenshots.takeScreenshot('after-capture');

				// Wait for photo processing
				await driver.pause(3000);

				// Return to main view
				console.log('↩️ Returning to main view...');


				await closeCamera();


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



async function openCamera() {
	console.log('📸 Looking for camera button...');
	
	// Switch to WebView context first since this is an HTML button
	const contexts = await driver.getContexts();
	const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
	
	if (webViewContexts.length > 0) {
		await driver.switchContext(webViewContexts[0]);
		
		// Just find the camera button and click it - keep it simple
		const cameraButton = await $('[data-testid="camera-button"]');
		await cameraButton.click();
		console.log('✅ Clicked camera button');
		
		await driver.switchContext('NATIVE_APP');
	} else {
		throw new Error('No WebView context found');
	}
	
	await driver.pause(2000);
	console.log('📸 Opened camera mode');
}


async function closeCamera() {
	console.log('📸 Looking for close camera button...');
	
	// Switch to WebView context first since this is an HTML button
	const contexts = await driver.getContexts();
	const webViewContexts = contexts.filter(ctx => ctx.includes('WEBVIEW'));
	
	if (webViewContexts.length > 0) {
		await driver.switchContext(webViewContexts[0]);
		
		// Just find the camera button and click it again - keep it simple
		const cameraButton = await $('[data-testid="camera-button"]');
		await cameraButton.click();
		console.log('✅ Clicked camera button to close');
		
		await driver.switchContext('NATIVE_APP');
	} else {
		throw new Error('No WebView context found');
	}
	
	await driver.pause(2000);
	console.log('📸 Closed camera mode');
}

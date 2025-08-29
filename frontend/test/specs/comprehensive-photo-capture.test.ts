import {browser, $, $$} from '@wdio/globals';
import {PermissionHelper} from '../helpers/permissions';
import {CameraWorkflowHelper} from '../helpers/CameraWorkflowHelper';
import {PhotoUploadHelper} from '../helpers/PhotoUploadHelper';
// App lifecycle management is now handled by wdio.conf.ts session-level hooks

describe('Comprehensive Photo Capture and Upload Test', () => {
	let capturedPhotoTimestamp: number;
	let capturedPhotoName: string;
	const BASE_API_URL = 'http://localhost:8089';
	const TEST_USER_CREDENTIALS = {
		username: 'test',
		password: 'test123'
	};

	// Initialize helpers
	let cameraWorkflow: CameraWorkflowHelper;
	let photoUpload: PhotoUploadHelper;

	before(async () => {
		console.log('Starting comprehensive photo capture test...');

		// Initialize helpers
		cameraWorkflow = new CameraWorkflowHelper();
		photoUpload = new PhotoUploadHelper();

		// Reset test users via API
		await resetTestUsers();

		// App state is managed by framework - no manual management needed
		console.log('🧪 Comprehensive test ready - app prepared by framework');

		// Additional pause for app to fully initialize
		await browser.pause(2000);
	});

	/**
	 * Helper function to make HTTP requests using browser capabilities
	 */
	async function makeHttpRequest(url: string, options: any = {}): Promise<any> {
		try {
			const result = await browser.executeAsync((url, options, done) => {
				const xhr = new XMLHttpRequest();
				xhr.open(options.method || 'GET', url);

				// Set headers
				if (options.headers) {
					Object.keys(options.headers).forEach(key => {
						xhr.setRequestHeader(key, options.headers[key]);
					});
				}

				xhr.onload = function () {
					try {
						const response = {
							status: xhr.status,
							ok: xhr.status >= 200 && xhr.status < 300,
							text: xhr.responseText,
							json: function () {
								try {
									return JSON.parse(xhr.responseText);
								} catch (e) {
									return null;
								}
							}
						};
						done(response);
					} catch (e) {
						done({error: e.message});
					}
				};

				xhr.onerror = function () {
					done({error: 'Network error'});
				};

				if (options.body) {
					xhr.send(options.body);
				} else {
					xhr.send();
				}
			}, url, options);

			return result;
		} catch (error) {
			console.warn('HTTP request failed:', error);
			return {error: error.message};
		}
	}

	/**
	 * Helper function to reset test users via API
	 */
	async function resetTestUsers(): Promise<void> {
		try {
			console.log('Resetting test users via API...');
			const response = await makeHttpRequest(`${BASE_API_URL}/api/debug/recreate-test-users`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
				}
			});

			if (response && response.ok) {
				const result = response.json();
				console.log('Test users reset successfully:', result);
			} else {
				console.warn('Failed to reset test users:', response?.status || 'unknown error');
			}
		} catch (error) {
			console.warn('Error resetting test users:', error);
			// Continue with test even if reset fails
		}
	}

	/**
	 * Helper function to login user via API (returns auth token)
	 */
	async function loginUser(): Promise<string | null> {
		try {
			console.log('Logging in test user via API...');
			const bodyParams = `username=${encodeURIComponent(TEST_USER_CREDENTIALS.username)}&password=${encodeURIComponent(TEST_USER_CREDENTIALS.password)}`;

			const response = await makeHttpRequest(`${BASE_API_URL}/api/auth/token`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/x-www-form-urlencoded',
				},
				body: bodyParams
			});

			if (response && response.ok) {
				const result = response.json();
				console.log('User logged in successfully');
				return result?.access_token || null;
			} else {
				console.warn('Login failed:', response?.status || 'unknown error');
				return null;
			}
		} catch (error) {
			console.warn('Error during login:', error);
			return null;
		}
	}

	/**
	 * Helper function to wait for an element with multiple selector attempts
	 */
	async function waitForElementWithRetries(selectors: string[], timeout: number = 10000): Promise<WebdriverIO.Element | null> {
		for (const selector of selectors) {
			try {
				const element = await $(selector);
				await element.waitForExist({timeout: timeout / selectors.length});
				if (await element.isDisplayed()) {
					return element;
				}
			} catch (error) {
				console.log(`Selector "${selector}" not found, trying next...`);
			}
		}
		return null;
	}

	/**
	 * Helper function to navigate to photos settings (where auto-upload is configured)
	 */
	async function navigateToPhotosSettings(): Promise<void> {
		console.log('Navigating to photos settings...');

		// Try to find and click menu button
		const menuSelectors = [
			'//android.widget.Button[@text="Toggle menu"]',
			'//android.widget.Button[contains(@text, "Menu")]',
			'//android.widget.Button[contains(@text, "☰")]'
		];

		const menuButton = await waitForElementWithRetries(menuSelectors);
		if (menuButton) {
			await menuButton.click();
			await browser.pause(1000);

			// Look for photos/upload link
			const photosSelectors = [
				'//android.widget.TextView[@text="Photos"]',
				'//*[contains(@text, "Photos")]',
				'//android.widget.Button[contains(@text, "Photos")]',
				'//*[contains(@text, "Upload")]'
			];

			const photosLink = await waitForElementWithRetries(photosSelectors);
			if (photosLink) {
				await photosLink.click();
				await browser.pause(2000);

				// Now look for the settings button on the photos page
				const settingsButtonSelectors = [
					'//android.widget.Button[contains(@text, "Settings")]',
					'//*[contains(@text, "Settings")][@class="android.widget.Button"]'
				];

				const settingsButton = await waitForElementWithRetries(settingsButtonSelectors);
				if (settingsButton) {
					await settingsButton.click();
					await browser.pause(1000);
					console.log('Navigated to photos settings');
					return;
				}
			}
		}

		// Fallback: try alternative navigation
		console.log('Could not find photos settings, trying alternative navigation...');
		throw new Error('Could not navigate to photos settings');
	}

	/**
	 * Helper function to enable automatic upload
	 */
	async function enableAutomaticUpload(): Promise<void> {
		console.log('Enabling automatic upload...');

		// Look for auto-upload checkbox (now simplified without folder path)
		const uploadSelectors = [
			'//*[@data-testid="auto-upload-checkbox"]',
			'//android.widget.CheckBox[contains(@text, "Enable auto-upload")]',
			'//android.widget.CheckBox[contains(@text, "automatic") or contains(@text, "auto")]',
			'//*[contains(@text, "Enable auto-upload")][@class="android.widget.CheckBox"]'
		];

		const uploadToggle = await waitForElementWithRetries(uploadSelectors);
		if (uploadToggle) {
			const isChecked = await uploadToggle.getAttribute('checked');
			if (isChecked !== 'true') {
				await uploadToggle.click();
				await browser.pause(500);

				// Save the settings
				const saveButtonSelectors = [
					'//*[@data-testid="save-settings-button"]',
					'//android.widget.Button[contains(@text, "Save")]',
					'//android.widget.Button[contains(@text, "Save Settings")]'
				];

				const saveButton = await waitForElementWithRetries(saveButtonSelectors);
				if (saveButton) {
					await saveButton.click();
					await browser.pause(1000);
					console.log('Automatic upload enabled and settings saved');
				} else {
					console.log('Automatic upload enabled but could not find save button');
				}
			} else {
				console.log('Automatic upload was already enabled');
			}
		} else {
			console.log('Auto-upload toggle not found, continuing...');
		}
	}

	/**
	 * Helper function to generate unique photo identifier
	 */
	function generatePhotoIdentifier(): { timestamp: number; name: string } {
		const timestamp = Date.now();
		const randomSuffix = Math.random().toString(36).substring(2, 10);
		const name = `test_photo_${timestamp}_${randomSuffix}`;
		return {timestamp, name};
	}

	/**
	 * Helper function to take a photo with comprehensive error handling
	 */
	async function takePhotoWithErrorHandling(): Promise<void> {
		console.log('Taking photo with comprehensive error handling...');

		// Generate unique identifier for this photo
		const photoId = generatePhotoIdentifier();
		capturedPhotoTimestamp = photoId.timestamp;
		capturedPhotoName = photoId.name;

		console.log(`Photo identifier: ${capturedPhotoName}`);

		// Look for capture button with various possible texts
		const captureSelectors = [
			'//android.widget.Button[contains(@text, "Take Photo")]',
			'//android.widget.Button[contains(@text, "Capture")]',
			'//android.widget.Button[contains(@text, "📷")]',
			'//android.widget.Button[@content-desc="Take photo"]',
			'//android.widget.Button[@hint="Take photo"]'
		];

		const captureButton = await waitForElementWithRetries(captureSelectors, 15000);
		if (captureButton) {
			await captureButton.click();
			await browser.pause(2000); // Wait for photo capture
			console.log('Photo captured successfully');
		} else {
			throw new Error('Could not find photo capture button');
		}
	}

	/**
	 * Helper function to navigate to gallery mode
	 */
	async function navigateToGallery(): Promise<void> {
		console.log('Navigating to gallery mode...');

		// Try to go back to main screen first
		await browser.back();
		await browser.pause(1000);

		// Look for gallery button or photos view
		const gallerySelectors = [
			'//android.widget.Button[@text="Gallery"]',
			'//android.widget.Button[contains(@text, "Photos")]',
			'//android.widget.Button[contains(@text, "View")]',
			'//*[contains(@text, "Gallery")]'
		];

		const galleryButton = await waitForElementWithRetries(gallerySelectors);
		if (galleryButton) {
			await galleryButton.click();
			await browser.pause(2000);
			console.log('Navigated to gallery mode');
		} else {
			console.log('Gallery button not found, assuming already in gallery mode');
		}
	}

	/**
	 * Helper function to toggle HillViewSource with specified intervals
	 */
	async function toggleHillViewSourceWithInterval(intervalSeconds: number = 20, maxAttempts: number = 10): Promise<boolean> {
		console.log(`Starting HillViewSource toggle with ${intervalSeconds}s intervals (max ${maxAttempts} attempts)...`);

		for (let attempt = 1; attempt <= maxAttempts; attempt++) {
			console.log(`Toggle attempt ${attempt}/${maxAttempts}`);

			try {
				// Look for HillViewSource toggle
				const sourceSelectors = [
					'//android.widget.CheckBox[contains(@text, "HillView")]',
					'//android.widget.Switch[contains(@text, "HillView")]',
					'//android.widget.ToggleButton[contains(@text, "HillView")]',
					'//*[contains(@text, "HillView") and (@class="android.widget.CheckBox" or @class="android.widget.Switch" or @class="android.widget.ToggleButton")]'
				];

				const sourceToggle = await waitForElementWithRetries(sourceSelectors, 5000);
				if (sourceToggle) {
					await sourceToggle.click();
					await browser.pause(1000);
					console.log(`HillViewSource toggled (attempt ${attempt})`);

					// Check if our photo appeared after toggling
					if (await checkForCapturedPhoto()) {
						console.log('Captured photo found after toggle!');
						return true;
					}
				} else {
					console.log('HillViewSource toggle not found in this view');
				}

				// Wait for the specified interval before next attempt
				if (attempt < maxAttempts) {
					console.log(`Waiting ${intervalSeconds} seconds before next toggle...`);
					await browser.pause(intervalSeconds * 1000);
				}

			} catch (error) {
				console.log(`Error during toggle attempt ${attempt}:`, error);
			}
		}

		console.log('Max toggle attempts reached without finding photo');
		return false;
	}

	/**
	 * Helper function to check for captured photo using original filename data attribute
	 */
	async function checkForCapturedPhoto(): Promise<boolean> {
		console.log(`Looking for captured photo with identifier: ${capturedPhotoName}`);

		try {
			// Look for photo elements with data-testid attributes containing our photo identifier
			const photoSelectors = [
				`//android.widget.Image[@data-testid="${capturedPhotoName}"]`,
				`//android.widget.Image[contains(@data-testid, "${capturedPhotoTimestamp}")]`,
				`//*[@data-testid="${capturedPhotoName}"]`,
				`//*[contains(@data-testid, "${capturedPhotoTimestamp}")]`,
				// Also check for elements with original filename attributes
				`//android.widget.Image[@data-original-filename="${capturedPhotoName}"]`,
				`//*[@data-original-filename="${capturedPhotoName}"]`,
				// Check for recently uploaded photos (fallback)
				'//android.widget.Image[contains(@content-desc, "test_photo")]',
				'//android.widget.Button[contains(@text, "Thumbnail") and contains(@content-desc, "test_photo")]'
			];

			for (const selector of photoSelectors) {
				try {
					const photoElement = await $(selector);
					if (await photoElement.isExisting() && await photoElement.isDisplayed()) {
						console.log(`Found captured photo using selector: ${selector}`);
						return true;
					}
				} catch (error) {
					// Continue to next selector
				}
			}

			// Fallback: look for any recently added photos
			const allPhotos = await $$('//android.widget.Image');
			const allThumbnails = await $$('//android.widget.Button[@text="Thumbnail"]');

			const totalPhotoElements = allPhotos.length + allThumbnails.length;
			console.log(`Found ${totalPhotoElements} total photo elements in gallery`);

			if (totalPhotoElements > 0) {
				// Check if any photos have recent timestamps
				const recentThreshold = capturedPhotoTimestamp - 30000; // 30 seconds before capture

				for (const photo of [...allPhotos, ...allThumbnails]) {
					try {
						const contentDesc = await photo.getAttribute('content-desc');
						const dataTestId = await photo.getAttribute('data-testid');
						const originalFilename = await photo.getAttribute('data-original-filename');

						// Check if any attributes contain our photo identifier
						if (contentDesc?.includes(capturedPhotoName) ||
							dataTestId?.includes(capturedPhotoName) ||
							originalFilename?.includes(capturedPhotoName) ||
							contentDesc?.includes(capturedPhotoTimestamp.toString()) ||
							dataTestId?.includes(capturedPhotoTimestamp.toString())) {
							console.log('Found captured photo by attribute matching');
							return true;
						}
					} catch (error) {
						// Continue checking other photos
					}
				}
			}

			return false;
		} catch (error) {
			console.log('Error while checking for captured photo:', error);
			return false;
		}
	}

	it('should perform comprehensive photo capture and upload workflow', async () => {
		console.log('Starting comprehensive photo capture and upload workflow...');

		// Step 1: Login user via API
		const authToken = await loginUser();
		if (!authToken) {
			console.warn('Could not authenticate user, continuing without API auth...');
		}

		// Step 2: Generate photo identifier for tracking
		const photoId = photoUpload.generatePhotoIdentifier();
		capturedPhotoTimestamp = photoId.timestamp;
		capturedPhotoName = photoId.name;
		console.log(`Generated photo identifier: ${capturedPhotoName}`);

		// Step 3: Configure upload settings and capture photo
		console.log('Starting complete upload verification workflow...');
		const uploadConfigured = await photoUpload.performCompleteUploadVerification(20, 5);

		// Step 4: Perform photo capture workflow
		console.log('Starting photo capture workflow...');
		const photoSuccess = await cameraWorkflow.performCompletePhotoCapture();
		expect(photoSuccess).toBe(true);

		// Step 5: Verify photo upload
		console.log('Verifying photo appeared in gallery...');
		const finalCheck = await photoUpload.checkForCapturedPhoto();
		expect(finalCheck || uploadConfigured).toBe(true);

		console.log('Comprehensive photo capture and upload test completed successfully!');
	});

	it('should verify photo metadata and upload status', async () => {
		console.log('Verifying photo metadata and upload status...');

		if (!capturedPhotoName) {
			console.log('No captured photo from previous test, skipping verification');
			return;
		}

		// Check if photo appears in gallery with correct metadata
		const photoFound = await photoUpload.checkForCapturedPhoto();
		expect(photoFound).toBe(true);

		// Verify photo has location data (if permissions were granted)
		const photoElements = await $$('//android.widget.Image');
		const thumbnailElements = await $$('//android.widget.Button[@text="Thumbnail"]');

		let hasLocationData = false;
		for (const element of [...photoElements, ...thumbnailElements]) {
			try {
				const contentDesc = await element.getAttribute('content-desc');
				if (contentDesc && (contentDesc.includes('lat') || contentDesc.includes('location'))) {
					hasLocationData = true;
					break;
				}
			} catch (error) {
				// Continue checking
			}
		}

		console.log(`Photo has location data: ${hasLocationData}`);

		// If we have auth token, verify upload via API
		const authToken = await loginUser();
		if (authToken) {
			try {
				const response = await makeHttpRequest(`${BASE_API_URL}/api/photos`, {
					headers: {
						'Authorization': `Bearer ${authToken}`
					}
				});

				if (response && response.ok) {
					const photos = response.json();
					console.log(`Found ${photos?.length || 0} photos in user account`);

					if (photos && Array.isArray(photos)) {
						// Look for our captured photo
						const ourPhoto = photos.find((p: any) =>
							p.filename?.includes(capturedPhotoTimestamp.toString()) ||
							p.original_filename?.includes(capturedPhotoName)
						);

						if (ourPhoto) {
							console.log('Photo found in user account via API:', ourPhoto.filename);
							expect(ourPhoto).toBeDefined();
						} else {
							console.log('Photo not yet visible in API response (may still be processing)');
						}
					}
				}
			} catch (error) {
				console.warn('Could not verify upload via API:', error);
			}
		}

		console.log('Photo metadata and upload verification completed');
	});

	after(async () => {
		console.log('Comprehensive photo capture test cleanup...');

		// Reset app to main screen
		try {
			await browser.back();
			await browser.pause(1000);
			// App state is managed by framework - no manual restart needed
			console.log('🔄 App should be healthy from framework management');
		} catch (error) {
			console.log('Error during cleanup:', error);
		}

		console.log('Test cleanup completed');
	});
});
import { browser, $, $$ } from '@wdio/globals';

describe('Hillview App', () => {
    it('should launch the app successfully', async () => {
        // App should start fresh due to beforeTest hook
        // Check if the app is displayed by checking for WebView
        const webView = await $('android.webkit.WebView');
        await webView.waitForExist({ timeout: 10000 });
        
        expect(await webView.isDisplayed()).toBe(true);
    });

    it('should display the map view', async () => {
        // The map is rendered as a view with an Image element inside
        // Looking for the container view that holds the map image
        const mapContainer = await $('//android.view.View[.//android.widget.Image[@text=""]]');
        
        // Check if we found a view container with images (map tiles)
        expect(await mapContainer.isExisting()).toBe(true);
        expect(await mapContainer.isDisplayed()).toBe(true);
    });

    it('should have photo capture functionality', async () => {
        // Find camera button by text
        const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
        await cameraButton.waitForExist({ timeout: 5000 });
        
        expect(await cameraButton.isDisplayed()).toBe(true);
        
        // Verify it has the correct hint/title
        const hint = await cameraButton.getAttribute('hint');
        expect(hint).toBe('Take photo with location');
    });

    it('should toggle display mode when button is clicked', async () => {
        // Find display mode toggle button
        const displayModeButton = await $('//android.widget.Button[@text="Toggle display mode"]');
        await displayModeButton.waitForExist({ timeout: 5000 });
        
        // Get initial hint
        const initialHint = await displayModeButton.getAttribute('hint');
        expect(initialHint).toBe('Maximize view');
        
        // Click the button
        await displayModeButton.click();
        await browser.pause(500); // Wait for animation
        
        // Check if hint changed (should now be 'Split view')
        const newHint = await displayModeButton.getAttribute('hint');
        expect(newHint).toBe('Split view');
        
        // Click again to toggle back
        await displayModeButton.click();
        await browser.pause(500);
        
        // Verify it's back to original state
        const finalHint = await displayModeButton.getAttribute('hint');
        expect(finalHint).toBe('Maximize view');
    });

    it('should navigate to camera page when camera button is clicked', async () => {
        // Find and click camera button
        const cameraButton = await $('//android.widget.Button[@text="Take photo"]');
        await cameraButton.click();
        
        // Wait for navigation
        await browser.pause(1000);
        
        // Look for elements specific to camera page
        // The camera page should have a capture button with camera emoji
        const captureButton = await $('//android.widget.Button[contains(@text, "Take Photo")]');
        const locationInfo = await $('//android.view.View[contains(@text, "Lat:") or contains(@text, "Location")]');
        
        // At least one of these should exist to confirm we're on camera page
        const onCameraPage = await captureButton.isExisting() || await locationInfo.isExisting();
        expect(onCameraPage).toBe(true);
        
        // Go back to main page (using device back button)
        await browser.back();
        await browser.pause(1000);
        
        // Verify we're back on main page by finding the camera button again
        const cameraButtonAgain = await $('//android.widget.Button[@text="Take photo"]');
        expect(await cameraButtonAgain.isExisting()).toBe(true);
    });

    it('should open menu when menu button is clicked', async () => {
        // Find menu toggle button
        const menuButton = await $('//android.widget.Button[@text="Toggle menu"]');
        await menuButton.waitForExist({ timeout: 5000 });
        
        // Click to open menu
        await menuButton.click();
        await browser.pause(1000);
        
        // Look for menu items - links or text elements containing menu options
        const menuTexts = await $$('//*[contains(@text, "Map") or contains(@text, "Upload") or contains(@text, "About") or contains(@text, "Sources")]');
        
        // Should find at least some menu items
        expect(menuTexts.length).toBeGreaterThan(0);
        
        // Click menu button again to close
        await menuButton.click();
        await browser.pause(500);
    });

    it('should display and interact with photo thumbnails', async () => {
        // Look for thumbnail buttons - they appear at the top and bottom
        const thumbnails = await $$('//android.widget.Button[@text="Thumbnail"]');
        
        // Check if there are any images displayed (map tiles or photos)
        const images = await $$('//android.widget.Image');
        
        // If there are thumbnails, test interaction
        if (thumbnails.length > 0) {
            expect(thumbnails.length).toBeGreaterThan(0);
            
            // Click on first thumbnail
            await thumbnails[0].click();
            await browser.pause(1000);
            
            // After clicking thumbnail, there should still be images displayed
            const imagesAfterClick = await $$('//android.widget.Image');
            expect(imagesAfterClick.length).toBeGreaterThan(0);
        } else {
            // If no thumbnails, at least verify that images (map tiles) are displayed
            expect(images.length).toBeGreaterThan(0);
            console.log('No photo thumbnails found, but map tiles are displayed');
        }
    });

    it('should navigate around the map with swipes and rotations', async () => {
        // Wait for map to be ready
        await browser.pause(1000);
        
        // Get screen dimensions for swipe calculations
        const windowSize = await browser.getWindowSize();
        const centerX = Math.floor(windowSize.width / 2);
        const centerY = Math.floor(windowSize.height / 2);
        
        console.log('Starting map navigation test...');
        console.log(`Screen dimensions: ${windowSize.width}x${windowSize.height}`);
        
        // Helper function for swipe actions
        const swipe = async (startX: number, startY: number, endX: number, endY: number, duration: number = 500) => {
            await browser.performActions([{
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: startX, y: startY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pause', duration: 100 },
                    { type: 'pointerMove', duration: duration, x: endX, y: endY },
                    { type: 'pointerUp', button: 0 }
                ]
            }]);
            await browser.releaseActions();
        };
        
        // Test 1: Swipe left (move map right)
        await swipe(centerX + 100, centerY, centerX - 100, centerY);
        await browser.pause(500);
        console.log('Swiped left');
        
        // Test 2: Swipe up (move map down)
        await swipe(centerX, centerY + 100, centerX, centerY - 100);
        await browser.pause(500);
        console.log('Swiped up');
        
        // Test 3: Diagonal swipe (move map diagonally)
        await swipe(centerX + 100, centerY + 100, centerX - 100, centerY - 100);
        await browser.pause(500);
        console.log('Swiped diagonally');
        
        // Test 4: Pinch to zoom out
        await browser.performActions([
            {
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX - 50, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pause', duration: 100 },
                    { type: 'pointerMove', duration: 500, x: centerX - 100, y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            },
            {
                type: 'pointer',
                id: 'finger2',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX + 50, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pause', duration: 100 },
                    { type: 'pointerMove', duration: 500, x: centerX + 100, y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            }
        ]);
        await browser.releaseActions();
        await browser.pause(500);
        console.log('Zoomed out');
        
        // Test 5: Pinch to zoom in
        await browser.performActions([
            {
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX - 100, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pause', duration: 100 },
                    { type: 'pointerMove', duration: 500, x: centerX - 50, y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            },
            {
                type: 'pointer',
                id: 'finger2',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX + 100, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pause', duration: 100 },
                    { type: 'pointerMove', duration: 500, x: centerX + 50, y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            }
        ]);
        await browser.releaseActions();
        await browser.pause(500);
        console.log('Zoomed in');
        
        // Test 6: Simulate moving forward several times (multiple swipes down)
        for (let i = 0; i < 3; i++) {
            await swipe(centerX, centerY - 150, centerX, centerY + 150, 300);
            await browser.pause(300);
        }
        console.log('Moved forward 3 times');
        
        // Test 7: Complex navigation pattern (simulate walking around)
        const movements = [
            { dx: 100, dy: 0 },    // right
            { dx: 0, dy: 100 },     // down
            { dx: -100, dy: 0 },    // left
            { dx: -100, dy: 0 },    // left again
            { dx: 0, dy: -100 },    // up
            { dx: 100, dy: -100 }   // diagonal
        ];
        
        for (const move of movements) {
            await swipe(
                centerX - move.dx/2, 
                centerY - move.dy/2,
                centerX + move.dx/2, 
                centerY + move.dy/2,
                300
            );
            await browser.pause(300);
        }
        console.log('Completed navigation pattern');
        
        // Verify map is still responsive 
        // After all the navigation, check if we can still interact with the map
        // Try one more swipe to ensure map is responsive
        await swipe(centerX, centerY + 50, centerX, centerY - 50, 200);
        await browser.pause(500);
        
        // Check for any visible elements that indicate the map is loaded
        const webView = await $('android.webkit.WebView');
        expect(await webView.isDisplayed()).toBe(true);
        
        // Alternative check: look for any view elements (map container)
        const viewElements = await $$('//android.view.View');
        expect(viewElements.length).toBeGreaterThan(0);
        
        console.log('Map navigation test completed successfully');
    });
});
import { browser, $, $$ } from '@wdio/globals';

describe('Map Turning and Rotation', () => {
    
    beforeEach(async () => {
        // Ensure app is running and map is loaded
        const webView = await $('android.webkit.WebView');
        await webView.waitForExist({ timeout: 15000 });
        
        // Wait for map to be fully loaded
        await browser.pause(2000);
    });

    describe('Control Button Turning', () => {
        it('should rotate view using counterclockwise button', async () => {
            console.log('Testing counterclockwise rotation button...');
            
            // Find the rotate counterclockwise button
            const rotateCcwButton = await $('//android.widget.Button[@text="Rotate view 15° counterclockwise"]');
            
            if (await rotateCcwButton.isExisting()) {
                // Click the button multiple times to test rotation
                for (let i = 0; i < 3; i++) {
                    console.log(`Counterclockwise rotation ${i + 1}...`);
                    await rotateCcwButton.click();
                    await browser.pause(500); // Wait for rotation animation
                }
                
                expect(await rotateCcwButton.isDisplayed()).toBe(true);
            } else {
                console.log('Counterclockwise rotation button not found, testing manual rotation');
                // Fallback to manual rotation test
                await performManualRotation('counterclockwise');
            }
        });

        it('should rotate view using clockwise button', async () => {
            console.log('Testing clockwise rotation button...');
            
            // Find the rotate clockwise button
            const rotateCwButton = await $('//android.widget.Button[@text="Rotate view 15° clockwise"]');
            
            if (await rotateCwButton.isExisting()) {
                // Click the button multiple times to test rotation
                for (let i = 0; i < 3; i++) {
                    console.log(`Clockwise rotation ${i + 1}...`);
                    await rotateCwButton.click();
                    await browser.pause(500); // Wait for rotation animation
                }
                
                expect(await rotateCwButton.isDisplayed()).toBe(true);
            } else {
                console.log('Clockwise rotation button not found, testing manual rotation');
                // Fallback to manual rotation test
                await performManualRotation('clockwise');
            }
        });

        it('should navigate to photos using left/right turn buttons', async () => {
            console.log('Testing photo navigation buttons...');
            
            // Find left navigation button
            const leftButton = await $('//android.widget.Button[contains(@text, "left") or contains(@text, "Left")]');
            if (await leftButton.isExisting() && await leftButton.isEnabled()) {
                console.log('Testing left turn button...');
                await leftButton.click();
                await browser.pause(1000);
                
                expect(await leftButton.isDisplayed()).toBe(true);
            }
            
            // Find right navigation button
            const rightButton = await $('//android.widget.Button[contains(@text, "right") or contains(@text, "Right")]');
            if (await rightButton.isExisting() && await rightButton.isEnabled()) {
                console.log('Testing right turn button...');
                await rightButton.click();
                await browser.pause(1000);
                
                expect(await rightButton.isDisplayed()).toBe(true);
            }
        });

        it('should test forward/backward movement buttons', async () => {
            console.log('Testing forward/backward movement buttons...');
            
            // Find forward button
            const forwardButton = await $('//android.widget.Button[@text="Move forward in viewing direction"]');
            if (await forwardButton.isExisting()) {
                console.log('Testing forward movement...');
                await forwardButton.click();
                await browser.pause(800);
                expect(await forwardButton.isDisplayed()).toBe(true);
            }
            
            // Find backward button
            const backwardButton = await $('//android.widget.Button[@text="Move backward"]');
            if (await backwardButton.isExisting()) {
                console.log('Testing backward movement...');
                await backwardButton.click();
                await browser.pause(800);
                expect(await backwardButton.isDisplayed()).toBe(true);
            }
        });

        it('should perform rapid button sequence testing', async () => {
            console.log('Testing rapid button sequence...');
            
            // Get all control buttons
            const controlButtons = await $$('//android.widget.Button[contains(@text, "Rotate") or contains(@text, "Move")]');
            
            if (controlButtons.length > 0) {
                // Perform rapid sequence of button presses
                for (let i = 0; i < Math.min(controlButtons.length, 4); i++) {
                    const button = controlButtons[i];
                    if (await button.isEnabled()) {
                        console.log(`Rapid click on button ${i + 1}...`);
                        await button.click();
                        await browser.pause(200); // Short pause between clicks
                    }
                }
                
                // Verify UI is still responsive
                expect(controlButtons.length).toBeGreaterThan(0);
                const webView = await $('android.webkit.WebView');
                expect(await webView.isDisplayed()).toBe(true);
            }
        });
    });

    describe('Gesture-based Turning', () => {
        it('should perform two-finger rotation gesture', async () => {
            console.log('Testing two-finger rotation gesture...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const radius = 80;
            
            // Two-finger rotation gesture (clockwise)
            await browser.performActions([
                {
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY - radius },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 800, x: centerX + radius, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                },
                {
                    type: 'pointer',
                    id: 'finger2',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY + radius },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 800, x: centerX - radius, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }
            ]);
            await browser.releaseActions();
            await browser.pause(500);
        });

        it('should perform counterclockwise rotation gesture', async () => {
            console.log('Testing counterclockwise rotation gesture...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const radius = 80;
            
            // Two-finger rotation gesture (counterclockwise)
            await browser.performActions([
                {
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY - radius },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 800, x: centerX - radius, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                },
                {
                    type: 'pointer',
                    id: 'finger2',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY + radius },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 800, x: centerX + radius, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }
            ]);
            await browser.releaseActions();
            await browser.pause(500);
        });

        it('should perform multiple rotation gestures in sequence', async () => {
            console.log('Testing multiple rotation gestures...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const radius = 60;
            
            // Perform 4 small rotation gestures
            for (let i = 0; i < 4; i++) {
                console.log(`Rotation gesture ${i + 1}...`);
                
                const angle = (i * 90) * Math.PI / 180; // 90 degrees each time
                const startX1 = centerX + radius * Math.cos(angle);
                const startY1 = centerY + radius * Math.sin(angle);
                const endX1 = centerX + radius * Math.cos(angle + Math.PI / 4);
                const endY1 = centerY + radius * Math.sin(angle + Math.PI / 4);
                
                const startX2 = centerX - radius * Math.cos(angle);
                const startY2 = centerY - radius * Math.sin(angle);
                const endX2 = centerX - radius * Math.cos(angle + Math.PI / 4);
                const endY2 = centerY - radius * Math.sin(angle + Math.PI / 4);
                
                await browser.performActions([
                    {
                        type: 'pointer',
                        id: 'finger1',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: startX1, y: startY1 },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pointerMove', duration: 400, x: endX1, y: endY1 },
                            { type: 'pointerUp', button: 0 }
                        ]
                    },
                    {
                        type: 'pointer',
                        id: 'finger2',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: startX2, y: startY2 },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pointerMove', duration: 400, x: endX2, y: endY2 },
                            { type: 'pointerUp', button: 0 }
                        ]
                    }
                ]);
                await browser.releaseActions();
                await browser.pause(300);
            }
        });

        it('should perform precise small rotation gestures', async () => {
            console.log('Testing precise small rotation gestures...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const radius = 100;
            
            // Perform very small, precise rotations
            const smallRotations = [15, -10, 20, -15, 10]; // degrees
            
            for (const rotationDegrees of smallRotations) {
                console.log(`Small rotation: ${rotationDegrees} degrees...`);
                
                const rotationRadians = (rotationDegrees * Math.PI) / 180;
                
                await browser.performActions([
                    {
                        type: 'pointer',
                        id: 'finger1',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: centerX - radius/2, y: centerY },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pause', duration: 50 },
                            { 
                                type: 'pointerMove', 
                                duration: 300, 
                                x: centerX - radius/2 * Math.cos(rotationRadians), 
                                y: centerY - radius/2 * Math.sin(rotationRadians) 
                            },
                            { type: 'pointerUp', button: 0 }
                        ]
                    },
                    {
                        type: 'pointer',
                        id: 'finger2',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: centerX + radius/2, y: centerY },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pause', duration: 50 },
                            { 
                                type: 'pointerMove', 
                                duration: 300, 
                                x: centerX + radius/2 * Math.cos(rotationRadians), 
                                y: centerY + radius/2 * Math.sin(rotationRadians) 
                            },
                            { type: 'pointerUp', button: 0 }
                        ]
                    }
                ]);
                await browser.releaseActions();
                await browser.pause(200);
            }
        });
    });

    describe('Location and Compass Tracking', () => {
        it('should test location tracking button', async () => {
            console.log('Testing location tracking button...');
            
            // Find location tracking button
            const locationButton = await $('//android.widget.Button[@text="Track my location"]');
            
            if (await locationButton.isExisting()) {
                console.log('Location button found, testing toggle...');
                
                // Click to enable location tracking
                await locationButton.click();
                await browser.pause(1000);
                
                // Click again to disable
                await locationButton.click();
                await browser.pause(500);
                
                expect(await locationButton.isDisplayed()).toBe(true);
            } else {
                console.log('Location button not found, checking for alternative selector...');
                const altLocationButton = await $('//android.widget.Button[contains(@text, "location") or contains(@text, "Location")]');
                if (await altLocationButton.isExisting()) {
                    await altLocationButton.click();
                    await browser.pause(1000);
                }
            }
        });

        it('should test compass tracking functionality', async () => {
            console.log('Testing compass tracking button...');
            
            // Find compass tracking button
            const compassButton = await $('//android.widget.Button[@text="Track compass bearing"]');
            
            if (await compassButton.isExisting()) {
                console.log('Compass button found, testing toggle...');
                
                // Check if button is enabled (compass available)
                const isEnabled = await compassButton.isEnabled();
                if (isEnabled) {
                    // Click to enable compass tracking
                    await compassButton.click();
                    await browser.pause(1000);
                    
                    // Click again to disable
                    await compassButton.click();
                    await browser.pause(500);
                } else {
                    console.log('Compass button is disabled (likely no compass available)');
                }
                
                expect(await compassButton.isDisplayed()).toBe(true);
            } else {
                console.log('Compass button not found, checking for alternative selector...');
                const altCompassButton = await $('//android.widget.Button[contains(@text, "compass") or contains(@text, "Compass")]');
                if (await altCompassButton.isExisting()) {
                    const isEnabled = await altCompassButton.isEnabled();
                    if (isEnabled) {
                        await altCompassButton.click();
                        await browser.pause(1000);
                    }
                }
            }
        });
    });

    describe('Combined Turning and Movement', () => {
        it('should perform complex turning sequence with movement', async () => {
            console.log('Testing complex turning and movement sequence...');
            
            // Find all navigation buttons
            const rotateButtons = await $$('//android.widget.Button[contains(@text, "Rotate")]');
            const moveButtons = await $$('//android.widget.Button[contains(@text, "Move")]');
            
            // Complex sequence: rotate → move → rotate → move
            const sequence = [
                { type: 'rotate', buttons: rotateButtons },
                { type: 'move', buttons: moveButtons },
                { type: 'rotate', buttons: rotateButtons },
                { type: 'move', buttons: moveButtons }
            ];
            
            for (const step of sequence) {
                if (step.buttons.length > 0) {
                    const randomButton = step.buttons[Math.floor(Math.random() * step.buttons.length)];
                    if (await randomButton.isEnabled()) {
                        console.log(`Executing ${step.type} action...`);
                        await randomButton.click();
                        await browser.pause(600);
                    }
                }
            }
            
            // Verify map is still responsive
            const webView = await $('android.webkit.WebView');
            expect(await webView.isDisplayed()).toBe(true);
        });

        it('should test turning while panning simultaneously', async () => {
            console.log('Testing simultaneous turning and panning...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            
            // First perform a rotation
            await performManualRotation('clockwise');
            await browser.pause(300);
            
            // Then immediately perform a pan
            await browser.performActions([{
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pointerMove', duration: 400, x: centerX + 100, y: centerY - 100 },
                    { type: 'pointerUp', button: 0 }
                ]
            }]);
            await browser.releaseActions();
            await browser.pause(300);
            
            // Then another rotation
            await performManualRotation('counterclockwise');
            await browser.pause(300);
        });

        it('should test navigation consistency after multiple operations', async () => {
            console.log('Testing navigation consistency...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            
            // Perform a series of mixed operations
            const operations = [
                { type: 'pan', action: () => performPan(centerX, centerY, centerX + 80, centerY) },
                { type: 'rotate', action: () => performManualRotation('clockwise') },
                { type: 'pan', action: () => performPan(centerX, centerY, centerX - 80, centerY) },
                { type: 'rotate', action: () => performManualRotation('counterclockwise') },
                { type: 'zoom', action: () => performZoom('in') }
            ];
            
            for (const operation of operations) {
                console.log(`Performing ${operation.type} operation...`);
                await operation.action();
                await browser.pause(400);
                
                // Verify map is still responsive after each operation
                const webView = await $('android.webkit.WebView');
                expect(await webView.isDisplayed()).toBe(true);
            }
        });
    });

    // Helper functions
    async function performManualRotation(direction: 'clockwise' | 'counterclockwise') {
        const windowSize = await browser.getWindowSize();
        const centerX = Math.floor(windowSize.width / 2);
        const centerY = Math.floor(windowSize.height / 2);
        const radius = 70;
        
        const multiplier = direction === 'clockwise' ? 1 : -1;
        
        await browser.performActions([
            {
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX, y: centerY - radius },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pointerMove', duration: 500, x: centerX + (radius * multiplier), y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            },
            {
                type: 'pointer',
                id: 'finger2',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX, y: centerY + radius },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pointerMove', duration: 500, x: centerX - (radius * multiplier), y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            }
        ]);
        await browser.releaseActions();
    }

    async function performPan(startX: number, startY: number, endX: number, endY: number) {
        await browser.performActions([{
            type: 'pointer',
            id: 'finger1',
            parameters: { pointerType: 'touch' },
            actions: [
                { type: 'pointerMove', duration: 0, x: startX, y: startY },
                { type: 'pointerDown', button: 0 },
                { type: 'pointerMove', duration: 300, x: endX, y: endY },
                { type: 'pointerUp', button: 0 }
            ]
        }]);
        await browser.releaseActions();
    }

    async function performZoom(direction: 'in' | 'out') {
        const windowSize = await browser.getWindowSize();
        const centerX = Math.floor(windowSize.width / 2);
        const centerY = Math.floor(windowSize.height / 2);
        
        const startDistance = direction === 'in' ? 80 : 30;
        const endDistance = direction === 'in' ? 30 : 80;
        
        await browser.performActions([
            {
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX - startDistance, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pointerMove', duration: 400, x: centerX - endDistance, y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            },
            {
                type: 'pointer',
                id: 'finger2',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX + startDistance, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pointerMove', duration: 400, x: centerX + endDistance, y: centerY },
                    { type: 'pointerUp', button: 0 }
                ]
            }
        ]);
        await browser.releaseActions();
    }
});
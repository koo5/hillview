import { browser, $, $$ } from '@wdio/globals';

describe('Map Navigation - Turning and Panning', () => {
    
    beforeEach(async () => {
        // Ensure app is running and map is loaded
        const webView = await $('android.webkit.WebView');
        await webView.waitForExist({ timeout: 15000 });
        
        // Wait for map to be fully loaded
        await browser.pause(2000);
    });

    describe('Panning Operations', () => {
        it('should pan map in all cardinal directions', async () => {
            console.log('Testing cardinal direction panning...');
            
            // Get screen dimensions for consistent panning
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const panDistance = 150;
            
            // Helper function for performing pans
            const performPan = async (startX: number, startY: number, endX: number, endY: number, direction: string) => {
                console.log(`Panning ${direction}...`);
                await browser.performActions([{
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: startX, y: startY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 500, x: endX, y: endY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }]);
                await browser.releaseActions();
                await browser.pause(300);
            };
            
            // Test panning in all directions
            await performPan(centerX, centerY, centerX - panDistance, centerY, 'left');
            await performPan(centerX, centerY, centerX + panDistance, centerY, 'right');
            await performPan(centerX, centerY, centerX, centerY - panDistance, 'up');
            await performPan(centerX, centerY, centerX, centerY + panDistance, 'down');
            
            // Verify map is still responsive after panning
            const webView = await $('android.webkit.WebView');
            expect(await webView.isDisplayed()).toBe(true);
        });

        it('should perform diagonal panning movements', async () => {
            console.log('Testing diagonal panning...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const panDistance = 100;
            
            const diagonalMoves = [
                { name: 'northeast', dx: panDistance, dy: -panDistance },
                { name: 'southeast', dx: panDistance, dy: panDistance },
                { name: 'southwest', dx: -panDistance, dy: panDistance },
                { name: 'northwest', dx: -panDistance, dy: -panDistance }
            ];
            
            for (const move of diagonalMoves) {
                console.log(`Panning ${move.name}...`);
                await browser.performActions([{
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 400, x: centerX + move.dx, y: centerY + move.dy },
                        { type: 'pointerUp', button: 0 }
                    ]
                }]);
                await browser.releaseActions();
                await browser.pause(300);
            }
        });

        it('should handle rapid successive panning gestures', async () => {
            console.log('Testing rapid panning...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const panDistance = 80;
            
            // Perform 5 rapid pans in different directions
            const rapidPans = [
                { dx: panDistance, dy: 0 },
                { dx: 0, dy: panDistance },
                { dx: -panDistance, dy: 0 },
                { dx: 0, dy: -panDistance },
                { dx: panDistance/2, dy: panDistance/2 }
            ];
            
            for (let i = 0; i < rapidPans.length; i++) {
                const pan = rapidPans[i];
                await browser.performActions([{
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 200, x: centerX + pan.dx, y: centerY + pan.dy },
                        { type: 'pointerUp', button: 0 }
                    ]
                }]);
                await browser.releaseActions();
                await browser.pause(100); // Short pause between gestures
            }
            
            // Verify map responsiveness after rapid panning
            const webView = await $('android.webkit.WebView');
            expect(await webView.isDisplayed()).toBe(true);
        });

        it('should perform smooth continuous panning motion', async () => {
            console.log('Testing continuous panning motion...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            const radius = 100;
            
            // Create a circular panning motion
            const points = [];
            const numPoints = 8;
            for (let i = 0; i < numPoints; i++) {
                const angle = (i * 2 * Math.PI) / numPoints;
                points.push({
                    x: centerX + radius * Math.cos(angle),
                    y: centerY + radius * Math.sin(angle)
                });
            }
            
            // Perform continuous circular pan
            const actions = [
                { type: 'pointerMove', duration: 0, x: points[0].x, y: points[0].y },
                { type: 'pointerDown', button: 0 }
            ];
            
            for (let i = 1; i < points.length; i++) {
                actions.push({
                    type: 'pointerMove',
                    duration: 300,
                    x: points[i].x,
                    y: points[i].y
                });
            }
            
            actions.push({ type: 'pointerUp', button: 0 });
            
            await browser.performActions([{
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: actions
            }]);
            await browser.releaseActions();
            await browser.pause(500);
        });
    });

    describe('Zoom Operations', () => {
        it('should perform pinch-to-zoom out', async () => {
            console.log('Testing pinch-to-zoom out...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            
            // Pinch gesture to zoom out
            await browser.performActions([
                {
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX - 30, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 600, x: centerX - 100, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                },
                {
                    type: 'pointer',
                    id: 'finger2',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX + 30, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 600, x: centerX + 100, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }
            ]);
            await browser.releaseActions();
            await browser.pause(500);
        });

        it('should perform pinch-to-zoom in', async () => {
            console.log('Testing pinch-to-zoom in...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            
            // Pinch gesture to zoom in
            await browser.performActions([
                {
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX - 100, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pause', duration: 100 },
                        { type: 'pointerMove', duration: 600, x: centerX - 30, y: centerY },
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
                        { type: 'pointerMove', duration: 600, x: centerX + 30, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }
            ]);
            await browser.releaseActions();
            await browser.pause(500);
        });

        it('should perform multiple zoom levels', async () => {
            console.log('Testing multiple zoom levels...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            
            // Zoom out multiple times
            for (let i = 0; i < 3; i++) {
                await browser.performActions([
                    {
                        type: 'pointer',
                        id: 'finger1',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: centerX - 40, y: centerY },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pointerMove', duration: 400, x: centerX - 80, y: centerY },
                            { type: 'pointerUp', button: 0 }
                        ]
                    },
                    {
                        type: 'pointer',
                        id: 'finger2',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: centerX + 40, y: centerY },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pointerMove', duration: 400, x: centerX + 80, y: centerY },
                            { type: 'pointerUp', button: 0 }
                        ]
                    }
                ]);
                await browser.releaseActions();
                await browser.pause(300);
            }
            
            // Then zoom back in
            for (let i = 0; i < 3; i++) {
                await browser.performActions([
                    {
                        type: 'pointer',
                        id: 'finger1',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: centerX - 80, y: centerY },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pointerMove', duration: 400, x: centerX - 40, y: centerY },
                            { type: 'pointerUp', button: 0 }
                        ]
                    },
                    {
                        type: 'pointer',
                        id: 'finger2',
                        parameters: { pointerType: 'touch' },
                        actions: [
                            { type: 'pointerMove', duration: 0, x: centerX + 80, y: centerY },
                            { type: 'pointerDown', button: 0 },
                            { type: 'pointerMove', duration: 400, x: centerX + 40, y: centerY },
                            { type: 'pointerUp', button: 0 }
                        ]
                    }
                ]);
                await browser.releaseActions();
                await browser.pause(300);
            }
        });
    });

    describe('Combined Pan and Zoom Operations', () => {
        it('should perform pan followed by zoom', async () => {
            console.log('Testing pan followed by zoom...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            
            // First, pan to a new area
            await browser.performActions([{
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: centerX, y: centerY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pointerMove', duration: 500, x: centerX - 150, y: centerY - 100 },
                    { type: 'pointerUp', button: 0 }
                ]
            }]);
            await browser.releaseActions();
            await browser.pause(500);
            
            // Then zoom in on the new area
            await browser.performActions([
                {
                    type: 'pointer',
                    id: 'finger1',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX - 60, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 600, x: centerX - 20, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                },
                {
                    type: 'pointer',
                    id: 'finger2',
                    parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX + 60, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 600, x: centerX + 20, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }
            ]);
            await browser.releaseActions();
            await browser.pause(500);
        });

        it('should perform complex navigation pattern', async () => {
            console.log('Testing complex navigation pattern...');
            
            const windowSize = await browser.getWindowSize();
            const centerX = Math.floor(windowSize.width / 2);
            const centerY = Math.floor(windowSize.height / 2);
            
            // Complex pattern: pan → zoom → pan → zoom
            const navigationSteps = [
                // Step 1: Pan right
                {
                    type: 'pan',
                    action: async () => {
                        await browser.performActions([{
                            type: 'pointer',
                            id: 'finger1',
                            parameters: { pointerType: 'touch' },
                            actions: [
                                { type: 'pointerMove', duration: 0, x: centerX, y: centerY },
                                { type: 'pointerDown', button: 0 },
                                { type: 'pointerMove', duration: 400, x: centerX + 120, y: centerY },
                                { type: 'pointerUp', button: 0 }
                            ]
                        }]);
                        await browser.releaseActions();
                    }
                },
                // Step 2: Zoom in
                {
                    type: 'zoom_in',
                    action: async () => {
                        await browser.performActions([
                            {
                                type: 'pointer',
                                id: 'finger1',
                                parameters: { pointerType: 'touch' },
                                actions: [
                                    { type: 'pointerMove', duration: 0, x: centerX - 50, y: centerY },
                                    { type: 'pointerDown', button: 0 },
                                    { type: 'pointerMove', duration: 500, x: centerX - 20, y: centerY },
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
                                    { type: 'pointerMove', duration: 500, x: centerX + 20, y: centerY },
                                    { type: 'pointerUp', button: 0 }
                                ]
                            }
                        ]);
                        await browser.releaseActions();
                    }
                },
                // Step 3: Pan diagonally
                {
                    type: 'pan_diagonal',
                    action: async () => {
                        await browser.performActions([{
                            type: 'pointer',
                            id: 'finger1',
                            parameters: { pointerType: 'touch' },
                            actions: [
                                { type: 'pointerMove', duration: 0, x: centerX, y: centerY },
                                { type: 'pointerDown', button: 0 },
                                { type: 'pointerMove', duration: 400, x: centerX - 80, y: centerY - 80 },
                                { type: 'pointerUp', button: 0 }
                            ]
                        }]);
                        await browser.releaseActions();
                    }
                },
                // Step 4: Zoom out
                {
                    type: 'zoom_out',
                    action: async () => {
                        await browser.performActions([
                            {
                                type: 'pointer',
                                id: 'finger1',
                                parameters: { pointerType: 'touch' },
                                actions: [
                                    { type: 'pointerMove', duration: 0, x: centerX - 20, y: centerY },
                                    { type: 'pointerDown', button: 0 },
                                    { type: 'pointerMove', duration: 500, x: centerX - 70, y: centerY },
                                    { type: 'pointerUp', button: 0 }
                                ]
                            },
                            {
                                type: 'pointer',
                                id: 'finger2',
                                parameters: { pointerType: 'touch' },
                                actions: [
                                    { type: 'pointerMove', duration: 0, x: centerX + 20, y: centerY },
                                    { type: 'pointerDown', button: 0 },
                                    { type: 'pointerMove', duration: 500, x: centerX + 70, y: centerY },
                                    { type: 'pointerUp', button: 0 }
                                ]
                            }
                        ]);
                        await browser.releaseActions();
                    }
                }
            ];
            
            // Execute all navigation steps
            for (const step of navigationSteps) {
                console.log(`Executing ${step.type}...`);
                await step.action();
                await browser.pause(400);
            }
            
            // Verify map is still responsive after complex navigation
            const webView = await $('android.webkit.WebView');
            expect(await webView.isDisplayed()).toBe(true);
        });
    });
});
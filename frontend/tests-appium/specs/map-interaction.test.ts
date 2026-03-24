import { browser } from '@wdio/globals';
import { byTestId, ensureNativeContext, TESTID } from '../helpers/selectors';
import { recreateTestUsers } from '../helpers/backend';

describe('Map Interaction', () => {

    before(async () => {
        await recreateTestUsers();
        await browser.pause(3000);
    });

    describe('Button Controls', () => {
        it('should rotate view with CCW and CW buttons', async () => {
            const ccw = await byTestId(TESTID.rotateCcw);
            await ccw.waitForDisplayed({ timeout: 10000 });

            for (let i = 0; i < 3; i++) {
                await ccw.click();
                await browser.pause(300);
            }

            const cw = await byTestId(TESTID.rotateCw);
            for (let i = 0; i < 3; i++) {
                await cw.click();
                await browser.pause(300);
            }
        });

        it('should move forward and backward', async () => {
            const forward = await byTestId(TESTID.moveForward);
            await forward.waitForDisplayed({ timeout: 5000 });
            await forward.click();
            await browser.pause(500);

            const backward = await byTestId(TESTID.moveBackward);
            await backward.click();
            await browser.pause(500);
        });

        it('should zoom in and out with buttons', async () => {
            const zoomIn = await byTestId(TESTID.zoomIn);
            await zoomIn.waitForDisplayed({ timeout: 5000 });
            await zoomIn.click();
            await browser.pause(500);

            const zoomOut = await byTestId(TESTID.zoomOut);
            await zoomOut.click();
            await browser.pause(500);
        });

        it('should toggle location tracking', async () => {
            const locationBtn = await byTestId(TESTID.trackLocation);
            await locationBtn.waitForDisplayed({ timeout: 5000 });

            // Enable
            await locationBtn.click();
            await browser.pause(1000);

            // Disable
            await locationBtn.click();
            await browser.pause(500);
        });
    });

    describe('Touch Gestures', () => {
        let centerX: number;
        let centerY: number;

        before(async () => {
            const windowSize = await browser.getWindowSize();
            centerX = Math.floor(windowSize.width / 2);
            centerY = Math.floor(windowSize.height / 2);
        });

        async function swipe(startX: number, startY: number, endX: number, endY: number, duration = 400) {
            await browser.performActions([{
                type: 'pointer',
                id: 'finger1',
                parameters: { pointerType: 'touch' },
                actions: [
                    { type: 'pointerMove', duration: 0, x: startX, y: startY },
                    { type: 'pointerDown', button: 0 },
                    { type: 'pause', duration: 50 },
                    { type: 'pointerMove', duration, x: endX, y: endY },
                    { type: 'pointerUp', button: 0 }
                ]
            }]);
            await browser.releaseActions();
        }

        async function pinch(spread: boolean, distance = 80) {
            const startDist = spread ? 30 : distance;
            const endDist = spread ? distance : 30;
            await browser.performActions([
                {
                    type: 'pointer', id: 'finger1', parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX - startDist, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 400, x: centerX - endDist, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                },
                {
                    type: 'pointer', id: 'finger2', parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX + startDist, y: centerY },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 400, x: centerX + endDist, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }
            ]);
            await browser.releaseActions();
        }

        async function twoFingerRotate(clockwise: boolean) {
            const radius = 70;
            const m = clockwise ? 1 : -1;
            await browser.performActions([
                {
                    type: 'pointer', id: 'finger1', parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY - radius },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 500, x: centerX + radius * m, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                },
                {
                    type: 'pointer', id: 'finger2', parameters: { pointerType: 'touch' },
                    actions: [
                        { type: 'pointerMove', duration: 0, x: centerX, y: centerY + radius },
                        { type: 'pointerDown', button: 0 },
                        { type: 'pointerMove', duration: 500, x: centerX - radius * m, y: centerY },
                        { type: 'pointerUp', button: 0 }
                    ]
                }
            ]);
            await browser.releaseActions();
        }

        it('should pan the map with swipe gestures', async () => {
            await swipe(centerX + 100, centerY, centerX - 100, centerY); // left
            await browser.pause(300);
            await swipe(centerX, centerY + 100, centerX, centerY - 100); // up
            await browser.pause(300);
            await swipe(centerX - 100, centerY, centerX + 100, centerY); // right
            await browser.pause(300);
        });

        it('should pinch to zoom in and out', async () => {
            await pinch(true);  // spread = zoom in
            await browser.pause(500);
            await pinch(false); // pinch = zoom out
            await browser.pause(500);
        });

        it('should rotate with two-finger gesture', async () => {
            await twoFingerRotate(true);  // clockwise
            await browser.pause(500);
            await twoFingerRotate(false); // counterclockwise
            await browser.pause(500);
        });

        it('should remain responsive after mixed operations', async () => {
            await swipe(centerX, centerY - 80, centerX, centerY + 80);
            await browser.pause(200);
            await twoFingerRotate(true);
            await browser.pause(200);
            await pinch(true);
            await browser.pause(200);
            await swipe(centerX + 80, centerY, centerX - 80, centerY);
            await browser.pause(200);

            // Verify app is still alive
            const zoomIn = await byTestId(TESTID.zoomIn);
            expect(await zoomIn.isDisplayed()).toBe(true);
        });
    });
});

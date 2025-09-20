import { browser } from '@wdio/globals';

export class Gestures {
    /**
     * Swipe from one point to another
     */
    static async swipe(startX: number, startY: number, endX: number, endY: number) {
        await browser.action('pointer')
            .move({ x: startX, y: startY })
            .down()
            .move({ x: endX, y: endY })
            .up()
            .perform();
    }

    /**
     * Swipe up on the screen
     */
    static async swipeUp() {
        const { width, height } = await browser.getWindowSize();
        await this.swipe(
            width / 2,
            height * 0.8,
            width / 2,
            height * 0.2
        );
    }

    /**
     * Swipe down on the screen
     */
    static async swipeDown() {
        const { width, height } = await browser.getWindowSize();
        await this.swipe(
            width / 2,
            height * 0.2,
            width / 2,
            height * 0.8
        );
    }

    /**
     * Tap at specific coordinates
     */
    static async tap(x: number, y: number) {
        await browser.action('pointer')
            .move({ x, y })
            .down()
            .up()
            .perform();
    }
}
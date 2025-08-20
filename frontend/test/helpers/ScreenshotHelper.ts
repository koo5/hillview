/**
 * Screenshot Helper
 * 
 * Provides automated screenshot numbering functionality for tests
 */
export class ScreenshotHelper {
    private counter = 0;
    private testName: string;

    constructor(testName: string) {
        this.testName = testName;
    }

    /**
     * Take a numbered screenshot with descriptive name
     */
    async takeScreenshot(description: string): Promise<void> {
        this.counter++;
        const paddedNumber = this.counter.toString().padStart(2, '0');
        const filename = `./test-results/${this.testName}-${paddedNumber}-${description}.png`;
        await driver.saveScreenshot(filename);
    }

    /**
     * Reset counter (call in beforeEach)
     */
    reset(): void {
        this.counter = 0;
    }

    /**
     * Get current counter value
     */
    getCount(): number {
        return this.counter;
    }
}
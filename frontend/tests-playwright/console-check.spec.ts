import { test, expect } from './fixtures';

test.describe('Console Error Check', () => {
  test('should show all console messages and check for runtime errors', async ({ page }) => {
    const consoleMessages: string[] = [];
    const errors: string[] = [];
    const uncaughtExceptions: string[] = [];

    // Capture all console messages
    page.on('console', (msg) => {
      const message = `[${msg.type()}] ${msg.text()}`;
      consoleMessages.push(message);
      console.log('🢄BROWSER CONSOLE:', message);
      
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Capture uncaught exceptions
    page.on('pageerror', (error) => {
      const message = `UNCAUGHT EXCEPTION: ${error.message}`;
      uncaughtExceptions.push(error.message);
      console.log(message);
    });

    console.log('🢄🔍 Navigating to main page...');
    await page.goto('/');
    
    console.log('🢄🔍 Waiting for network idle...');
    await page.waitForLoadState('networkidle');
    
    console.log('🢄🔍 Waiting 3 seconds for app initialization...');
    await page.waitForTimeout(3000);

    console.log('🢄🔍 Performing navigation actions...');
    
    // Test keyboard navigation
    console.log('🢄🔍 Testing z key (rotate left)...');
    await page.keyboard.press('z');
    await page.waitForTimeout(200);
    
    console.log('🢄🔍 Testing x key (rotate right)...');
    await page.keyboard.press('x');
    await page.waitForTimeout(200);
    
    console.log('🢄🔍 Testing c key (turn to left photo)...');
    await page.keyboard.press('c');
    await page.waitForTimeout(200);
    
    console.log('🢄🔍 Testing v key (turn to right photo)...');
    await page.keyboard.press('v');
    await page.waitForTimeout(200);

    console.log('🢄🔍 Final wait...');
    await page.waitForTimeout(1000);

    // Report findings
    console.log('🢄\n📊 SUMMARY:');
    console.log(`Total console messages: ${consoleMessages.length}`);
    console.log(`Console errors: ${errors.length}`);
    console.log(`Uncaught exceptions: ${uncaughtExceptions.length}`);

    if (errors.length > 0) {
      console.log('🢄\n❌ CONSOLE ERRORS:');
      errors.forEach((error, i) => console.log(`🢄  ${i + 1}. ${error}`));
    }

    if (uncaughtExceptions.length > 0) {
      console.log('🢄\n💥 UNCAUGHT EXCEPTIONS:');
      uncaughtExceptions.forEach((error, i) => console.log(`🢄  ${i + 1}. ${error}`));
    }

    // Check for specific "pos is not defined" errors
    const hasPosErrors = [
      ...errors.filter(error => error.includes('pos is not defined')),
      ...uncaughtExceptions.filter(error => error.includes('pos is not defined'))
    ];

    const hasLegacyErrors = [
      ...errors.filter(error => 
        error.includes('bearing is not defined') ||
        error.includes('pos2 is not defined') ||
        error.includes('photos_in_area is not defined') ||
        error.includes('photos_in_range is not defined')
      ),
      ...uncaughtExceptions.filter(error => 
        error.includes('bearing is not defined') ||
        error.includes('pos2 is not defined') ||
        error.includes('photos_in_area is not defined') ||
        error.includes('photos_in_range is not defined')
      )
    ];

    console.log('🢄\n✅ SPECIFIC ERROR CHECKS:');
    console.log(`"pos is not defined" errors: ${hasPosErrors.length}`);
    console.log(`Legacy store errors: ${hasLegacyErrors.length}`);

    if (hasPosErrors.length > 0) {
      console.log('🢄\n🚨 "pos is not defined" ERRORS FOUND:');
      hasPosErrors.forEach((error, i) => console.log(`🢄  ${i + 1}. ${error}`));
    }

    if (hasLegacyErrors.length > 0) {
      console.log('🢄\n🚨 LEGACY STORE ERRORS FOUND:');
      hasLegacyErrors.forEach((error, i) => console.log(`🢄  ${i + 1}. ${error}`));
    }

    // Test assertions
    expect(hasPosErrors.length, `Found "pos is not defined" errors: ${hasPosErrors.join(', ')}`).toBe(0);
    expect(hasLegacyErrors.length, `Found legacy store errors: ${hasLegacyErrors.join(', ')}`).toBe(0);

    console.log('🢄\n🎉 ALL RUNTIME ERROR CHECKS PASSED!');
  });
});
/**
 * Tests for photo-in-front persistence through map panning
 * Verifies that navigated-to photos stay loaded on the map
 */

import { test, expect } from '@playwright/test';

// Declare debug properties on window for TypeScript
declare global {
  interface Window {
    __DEBUG__?: {
      picks?: string[];
      photoInFront?: { id: string };
      [key: string]: any;
    };
    __WORKER_MESSAGES__?: any[];
  }
}

test.describe('Photo Navigation Persistence', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app
    await page.goto('/');

    // Wait for map to load
    await page.waitForSelector('[data-testid="map-container"]', { timeout: 10000 });
  });

  test('photo in front should be added to picks when bearing changes', async ({ page }) => {
    // Enable a photo source
    await page.click('[data-testid="source-toggle-hillview"]');

    // Wait for photos to load
    await page.waitForTimeout(2000);

    // Simulate navigation to a photo (arrow key press)
    await page.keyboard.press('ArrowLeft');

    // Wait for bearing state update
    await page.waitForTimeout(500);

    // Check that picks state has been updated (via console log or debug panel)
    const picksState = await page.evaluate(() => {
      // Access the picks store from window (if exposed in dev mode)
      return window.__DEBUG__?.picks || [];
    });

    expect(picksState.length).toBeGreaterThan(0);
  });

  test('picked photo should persist through map pan', async ({ page }) => {
    // Enable a photo source
    await page.click('[data-testid="source-toggle-hillview"]');

    // Wait for photos to load
    await page.waitForTimeout(2000);

    // Get initial photo markers count
    const initialMarkers = await page.locator('[data-testid^="photo-marker-"]').count();

    // Navigate to a specific photo
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(500);

    // Get the ID of the photo in front
    const photoInFrontId = await page.evaluate(() => {
      // Get from bearing state or navigation state
      return window.__DEBUG__?.photoInFront?.id || null;
    });

    expect(photoInFrontId).not.toBeNull();

    // Pan the map slightly
    const map = await page.locator('[data-testid="map-container"]');
    await map.dragTo(map, {
      sourcePosition: { x: 200, y: 200 },
      targetPosition: { x: 250, y: 250 }
    });

    // Wait for map update
    await page.waitForTimeout(1000);

    // Verify the picked photo marker is still present
    const pickedMarker = await page.locator(`[data-testid="photo-marker-${photoInFrontId}"]`);
    await expect(pickedMarker).toBeVisible();
  });

  test('picks should update when navigating between photos', async ({ page }) => {
    // Enable a photo source
    await page.click('[data-testid="source-toggle-hillview"]');

    // Wait for photos to load
    await page.waitForTimeout(2000);

    // Navigate through multiple photos
    for (let i = 0; i < 3; i++) {
      await page.keyboard.press('ArrowLeft');
      await page.waitForTimeout(500);
    }

    // Get current picks
    const picksState = await page.evaluate(() => {
      return window.__DEBUG__?.picks || [];
    });

    // Should only have one pick (the current photo in front)
    expect(picksState.length).toBe(1);
  });

  test('picked photo should be prioritized in dense areas', async ({ page }) => {
    // Enable a photo source
    await page.click('[data-testid="source-toggle-hillview"]');

    // Wait for photos to load
    await page.waitForTimeout(2000);

    // Navigate to a photo
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(500);

    const photoInFrontId = await page.evaluate(() => {
      return window.__DEBUG__?.photoInFront?.id || null;
    });

    // Zoom out to load more photos (simulating dense area)
    await page.keyboard.press('-');
    await page.waitForTimeout(1000);

    // Verify picked photo is still visible despite potential culling
    const pickedMarker = await page.locator(`[data-testid="photo-marker-${photoInFrontId}"]`);
    await expect(pickedMarker).toBeVisible();

    // Check that it has a special class or attribute indicating it's picked
    const isPicked = await pickedMarker.evaluate(el =>
      el.classList.contains('picked') || el.getAttribute('data-picked') === 'true'
    );
    expect(isPicked).toBeTruthy();
  });

  test('picks should clear when photo source is disabled', async ({ page }) => {
    // Enable a photo source
    await page.click('[data-testid="source-toggle-hillview"]');

    // Wait for photos to load
    await page.waitForTimeout(2000);

    // Navigate to a photo
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(500);

    // Disable the photo source
    await page.click('[data-testid="source-toggle-hillview"]');
    await page.waitForTimeout(500);

    // Picks should be cleared when source is disabled
    const picksState = await page.evaluate(() => {
      return window.__DEBUG__?.picks || [];
    });

    expect(picksState.length).toBe(0);
  });
});

test.describe('Picks Worker Integration', () => {
  test('picks should be sent to photo worker on update', async ({ page }) => {
    // Set up a spy for worker messages (if in dev mode)
    await page.evaluate(() => {
      window.__WORKER_MESSAGES__ = [];

      // Override worker postMessage to capture messages
      if (window.Worker) {
        const OriginalWorker = window.Worker;
        window.Worker = class extends OriginalWorker {
          constructor(...args: ConstructorParameters<typeof Worker>) {
            super(...args);
            const originalPostMessage = this.postMessage.bind(this);
            this.postMessage = (message: any) => {
              window.__WORKER_MESSAGES__!.push(message);
              return originalPostMessage(message);
            };
          }
        };
      }
    });

    // Navigate to the app
    await page.goto('/');

    // Enable a photo source
    await page.click('[data-testid="source-toggle-hillview"]');
    await page.waitForTimeout(2000);

    // Navigate to trigger picks update
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(500);

    // Check that picksUpdated message was sent to worker
    const workerMessages = await page.evaluate(() => window.__WORKER_MESSAGES__ || []);

    const picksMessage = workerMessages.find((msg: any) => msg.type === 'picksUpdated');
    expect(picksMessage).toBeDefined();
    expect(picksMessage.data.picks).toBeInstanceOf(Array);
  });
});
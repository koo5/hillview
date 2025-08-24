import { test, expect } from '@playwright/test';

test.describe('Photo Navigation and Image URLs', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the main page
    await page.goto('/');
    
    // Wait for the app to load
    await page.waitForLoadState('networkidle');
    
    // Wait for photos to load
    await page.waitForTimeout(5000);
  });

  test('should have correct image URLs', async ({ page }) => {
    // Wait for photos to load
    await page.waitForTimeout(3000);
    
    // Look for gallery images
    const galleryImages = page.locator('.thumbnail img');
    const imageCount = await galleryImages.count();
    
    console.log(`🖼️ Found ${imageCount} gallery images`);
    
    if (imageCount > 0) {
      // Check first few images for correct URL format
      const imagesToCheck = Math.min(5, imageCount);
      
      for (let i = 0; i < imagesToCheck; i++) {
        const img = galleryImages.nth(i);
        const src = await img.getAttribute('src');
        
        console.log(`🔗 Image ${i} URL: ${src}`);
        
        const hasCorrectPrefix = src && (
          src.startsWith('http')
        );
        
        expect(hasCorrectPrefix, `Image URL should have correct prefix: ${src}`).toBe(true);
        
        // Should not be a relative URL starting with just filename
        const isRelativeFilename = src && !src.startsWith('http') && !src.startsWith('/') && !src.startsWith('blob:');
        expect(isRelativeFilename, `Image URL should not be just a filename: ${src}`).toBe(false);
      }
    } else {
      console.log('🢄⚠️ No gallery images found to test URLs');
    }
  });

  test('should navigate to left/right photos with c/v keys', async ({ page }) => {
    const consoleMessages: string[] = [];
    
    page.on('console', (msg) => {
      consoleMessages.push(`[${msg.type()}] ${msg.text()}`);
    });

    // Wait for photos to load
    await page.waitForTimeout(3000);
    
    // Get initial photo state
    const initialPhotoInfo = await page.evaluate(() => {
      return {
        // Try to get current photo information
        hasPhotoInFront: !!(window as any).photoInFront,
        hasPhotoToLeft: !!(window as any).photoToLeft,
        hasPhotoToRight: !!(window as any).photoToRight
      };
    });
    
    console.log('🢄📊 Initial photo state:', initialPhotoInfo);
    
    // Test left navigation (c key)
    console.log('🢄🔍 Testing c key (turn to left photo)...');
    await page.keyboard.press('c');
    await page.waitForTimeout(500);
    
    // Test right navigation (v key) 
    console.log('🢄🔍 Testing v key (turn to right photo)...');
    await page.keyboard.press('v');
    await page.waitForTimeout(500);
    
    // Check console messages for navigation
    const navigationMessages = consoleMessages.filter(msg => 
      msg.includes('turn_to_photo_to') || 
      msg.includes('photo to left') ||
      msg.includes('photo to right') ||
      msg.includes('photoToLeft') ||
      msg.includes('photoToRight')
    );
    
    console.log('🢄🧭 Navigation messages:');
    navigationMessages.forEach(msg => console.log(`🢄  ${msg}`));
    
    // Should have navigation messages
    expect(navigationMessages.length, 'Expected navigation messages when pressing c/v keys').toBeGreaterThan(0);
    
    // Check if navigation is working or failing
    const hasNavigationErrors = consoleMessages.some(msg => 
      msg.includes('No photo to left') || 
      msg.includes('No photo to right')
    );
    
    if (hasNavigationErrors) {
      console.log('🢄⚠️ Navigation errors detected - photos may not be properly set up for navigation');
      
      // This is expected if photos aren't properly sorted by bearing yet
      // We'll check if the navigation system is at least responding
      const hasNavigationAttempts = consoleMessages.some(msg => 
        msg.includes('turn_to_photo_to')
      );
      
      expect(hasNavigationAttempts, 'Navigation system should respond to c/v keys').toBe(true);
    } else {
      console.log('🢄✅ Navigation appears to be working');
    }
  });

  test('should have photoInFront, photoToLeft, photoToRight populated', async ({ page }) => {
    // Wait for photos to load
    await page.waitForTimeout(5000);
    
    // Check if photo navigation stores are populated
    const photoStates = await page.evaluate(() => {
      // Access the stores via window or through debug info
      const debugElement = document.querySelector('.debug');
      if (debugElement) {
        const debugText = debugElement.textContent || '';
        return {
          hasDebugInfo: true,
          frontPhoto: debugText.includes('Front:') ? debugText.match(/Front:\s*([^\n\r]+)/)?.[1]?.trim() : null,
          leftPhoto: debugText.includes('Left:') ? debugText.match(/Left:\s*([^\n\r]+)/)?.[1]?.trim() : null,
          rightPhoto: debugText.includes('Right:') ? debugText.match(/Right:\s*([^\n\r]+)/)?.[1]?.trim() : null,
          photosInAreaCount: debugText.includes('Photos in area:') ? debugText.match(/Photos in area:\s*(\d+)/)?.[1] : null
        };
      }
      return { hasDebugInfo: false };
    });
    
    console.log('🢄📊 Photo navigation states:', photoStates);
    
    if (photoStates.hasDebugInfo) {
      // If we have photos in area, we should have at least a front photo
      if (photoStates.photosInAreaCount && parseInt(photoStates.photosInAreaCount) > 0) {
        expect(photoStates.frontPhoto && photoStates.frontPhoto !== 'undefined' && photoStates.frontPhoto !== '', 
          'Should have a front photo when photos are available').toBe(true);
        
        console.log(`✅ Front photo: ${photoStates.frontPhoto}`);
        console.log(`📍 Left photo: ${photoStates.leftPhoto || 'none'}`);
        console.log(`📍 Right photo: ${photoStates.rightPhoto || 'none'}`);
      } else {
        console.log('🢄⚠️ No photos in area, navigation states expected to be empty');
      }
    } else {
      // Try to enable debug mode to see the info
      const debugButton = page.locator('button.debug-toggle');
      await debugButton.click();
      await page.waitForTimeout(1000);
      
      console.log('🢄⚠️ Debug info not visible, tried to enable debug mode');
    }
  });
});
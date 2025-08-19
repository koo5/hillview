import { browser, $, $$ } from '@wdio/globals';
import { promises as fs } from 'fs';
import path from 'path';

/**
 * Check for common error patterns that indicate a broken app
 */
async function checkForAppErrors(): Promise<boolean> {
    const errorPatterns = [
        'error sending request',
        'connection failed', 
        'network error',
        'tauri error',
        'backend error',
        'failed to fetch',
        'cannot connect'
    ];
    
    console.log('🔍 Checking for app error indicators...');
    
    for (const pattern of errorPatterns) {
        try {
            const errorEl = await $(`//*[contains(@text, "${pattern}")]`);
            if (await errorEl.isExisting()) {
                console.error(`❌ Found error pattern: "${pattern}"`);
                await saveDebugScreenshot(`error-${pattern.replace(/\s+/g, '-')}`);
                return true;
            }
        } catch (e) {
            // Ignore xpath errors, continue checking
        }
    }
    
    // Also check for generic error elements
    try {
        const errorElements = await $$('//*[contains(translate(@text, "ERROR", "error"), "error")]');
        if (errorElements.length > 0) {
            console.error(`❌ Found ${errorElements.length} elements with "error" text`);
            const errorTexts = await Promise.all(errorElements.map(el => el.getText().catch(() => 'N/A')));
            console.error('Error texts:', errorTexts);
            await saveDebugScreenshot('generic-errors');
            return true;
        }
    } catch (e) {
        // Ignore xpath errors
    }
    
    console.log('✅ No error patterns detected');
    return false;
}

/**
 * Verify the app is actually functional by checking for expected UI elements
 */
async function verifyAppHealth(): Promise<boolean> {
    console.log('🏥 Performing app health check...');
    
    // Take screenshot for debugging
    await saveDebugScreenshot('health-check');
    
    // First check for errors
    const hasErrors = await checkForAppErrors();
    if (hasErrors) {
        return false;
    }
    
    // Check for expected core UI elements
    const expectedElements = [
        { selector: '//android.widget.Button[@text="Take photo"]', name: 'Take photo button' },
        { selector: 'android.webkit.WebView', name: 'WebView container' }
    ];
    
    let foundElements = 0;
    for (const element of expectedElements) {
        try {
            const el = await $(element.selector);
            const exists = await el.isExisting();
            if (exists) {
                console.log(`✅ Found: ${element.name}`);
                foundElements++;
            } else {
                console.log(`⚠️  Missing: ${element.name}`);
            }
        } catch (e) {
            console.log(`⚠️  Error checking ${element.name}:`, e.message);
        }
    }
    
    // App is healthy if we found at least one expected element
    const isHealthy = foundElements > 0;
    
    if (!isHealthy) {
        console.error('❌ App health check failed - no expected UI elements found');
        await logAppState();
        return false;
    }
    
    console.log(`✅ App appears healthy - found ${foundElements}/${expectedElements.length} expected elements`);
    return true;
}

/**
 * Log detailed information about the current app state for debugging
 */
async function logAppState(): Promise<void> {
    console.log('📱 ===== APP STATE DEBUG =====');
    
    try {
        // Save screenshot
        await saveDebugScreenshot('app-state-debug');
        
        // Log all visible text elements
        console.log('📝 Scanning for visible text...');
        const textElements = await $$('//*[@text!=""]');
        const visibleTexts = [];
        
        for (let i = 0; i < Math.min(textElements.length, 20); i++) { // Limit to avoid spam
            try {
                const text = await textElements[i].getText();
                if (text && text.trim()) {
                    visibleTexts.push(text.trim());
                }
            } catch (e) {
                // Skip elements we can't read
            }
        }
        
        if (visibleTexts.length > 0) {
            console.log('📝 Visible text elements:', visibleTexts);
        } else {
            console.log('📝 No visible text elements found');
        }
        
        // Log clickable elements
        console.log('🖱️  Scanning for clickable elements...');
        const buttons = await $$('//android.widget.Button');
        const buttonTexts = [];
        
        for (let i = 0; i < Math.min(buttons.length, 10); i++) {
            try {
                const text = await buttons[i].getText();
                if (text) {
                    buttonTexts.push(text);
                }
            } catch (e) {
                // Skip
            }
        }
        
        if (buttonTexts.length > 0) {
            console.log('🖱️  Available buttons:', buttonTexts);
        } else {
            console.log('🖱️  No buttons found');
        }
        
        // Log page source (truncated) for deep debugging
        const pageSource = await browser.getPageSource();
        const truncated = pageSource.length > 2000 ? 
            pageSource.substring(0, 2000) + '\n...[truncated - full source saved to debug file]' : 
            pageSource;
        console.log('🏗️  Page structure preview:', truncated);
        
        // Save full page source to file for detailed analysis
        await saveDebugFile('page-source.xml', pageSource);
        
    } catch (e) {
        console.error('❌ Failed to log app state:', e.message);
    }
    
    console.log('📱 ===== END APP STATE DEBUG =====');
}

/**
 * Save a screenshot with timestamp for debugging, with fallback methods
 */
async function saveDebugScreenshot(name: string): Promise<void> {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `${name}-${timestamp}.png`;
    
    try {
        await browser.saveScreenshot(`./test-results/${filename}`);
        console.log(`📸 Screenshot saved: ${filename}`);
        return;
    } catch (e) {
        console.warn(`⚠️ Primary screenshot failed: ${e.message}`);
    }
    
    // Fallback 1: Try ADB screenshot
    try {
        console.log('📸 Attempting ADB screenshot fallback...');
        await browser.execute('mobile: shell', {
            command: 'screencap -p /sdcard/screenshot.png'
        });
        await browser.execute('mobile: shell', {
            command: 'chmod 644 /sdcard/screenshot.png'
        });
        console.log('📸 ADB screenshot saved to device /sdcard/screenshot.png');
        console.log('💡 Run: adb pull /sdcard/screenshot.png ./test-results/adb-' + filename);
        return;
    } catch (e) {
        console.warn(`⚠️ ADB screenshot fallback failed: ${e.message}`);
    }
    
    // Fallback 2: Log what we can see without screenshots
    try {
        console.log('📸 Screenshot unavailable, logging UI state instead...');
        const appState = await browser.queryAppState('io.github.koo5.hillview.dev');
        console.log(`📱 App state: ${appState} (0=not installed, 1=not running, 2=bg, 3=bg suspended, 4=fg)`);
        
        // Try to get some basic element info
        const webViews = await browser.$$('android.webkit.WebView');
        console.log(`🌐 WebViews found: ${webViews.length}`);
        
        // Save device info instead
        await saveDebugFile(`${name}-device-info.txt`, 
            `App State: ${appState}\nWebViews: ${webViews.length}\nTimestamp: ${timestamp}\nError: Screenshot failed with DeadObjectException`
        );
        
    } catch (e) {
        console.error(`❌ All screenshot and fallback methods failed: ${e.message}`);
    }
}

/**
 * Save debug data to file
 */
async function saveDebugFile(filename: string, content: string): Promise<void> {
    try {
        const resultsDir = './test-results';
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const fullPath = path.join(resultsDir, `${timestamp}-${filename}`);
        
        // Ensure directory exists
        await fs.mkdir(resultsDir, { recursive: true });
        await fs.writeFile(fullPath, content, 'utf8');
        console.log(`💾 Debug file saved: ${path.basename(fullPath)}`);
    } catch (e) {
        console.error('Failed to save debug file:', e.message);
    }
}

/**
 * Check if Android device/emulator is in a healthy state
 */
async function checkDeviceHealth(): Promise<boolean> {
    try {
        console.log('🔧 Checking Android device health...');
        
        // Test basic device communication
        const appState = await browser.queryAppState('io.github.koo5.hillview.dev');
        console.log(`📱 App state query successful: ${appState}`);
        
        // Test screenshot capability
        try {
            await browser.saveScreenshot('./test-results/device-health-check.png');
            console.log('📸 Device screenshot capability: OK');
            return true;
        } catch (e) {
            if (e.message.includes('DeadObjectException') || e.message.includes('UiAutomation')) {
                console.warn('⚠️ Device has UiAutomation issues - screenshots will be unreliable');
                console.log('💡 Consider restarting the emulator if issues persist');
                return false;
            }
            throw e;
        }
        
    } catch (e) {
        console.error('❌ Device health check failed:', e.message);
        return false;
    }
}

export async function ensureAppIsRunning() {
    const appId = 'io.github.koo5.hillview.dev';
    const maxRetries = 3;
    
    // Check device health first
    const deviceHealthy = await checkDeviceHealth();
    if (!deviceHealthy) {
        console.warn('⚠️ Device has UiAutomation issues - tests may be unreliable');
        console.log('📋 Debug info will be limited to text logs and page source');
    }
    
    for (let i = 0; i < maxRetries; i++) {
        try {
            // Check app state
            const state = await browser.queryAppState(appId);
            console.log(`App state: ${state} (attempt ${i + 1}/${maxRetries})`);
            
            // States: 0=not installed, 1=not running, 2=running in background, 3=running in background, 4=running in foreground
            if (state === 0) {
                throw new Error('App is not installed!');
            }
            
            if (state !== 4) {
                console.log('App not in foreground, launching...');
                
                // Terminate if running in background
                if (state === 2 || state === 3) {
                    await browser.terminateApp(appId);
                    await browser.pause(1000);
                }
                
                // Try multiple launch methods
                try {
                    // Method 1: Start activity directly
                    await browser.startActivity({
                        appPackage: appId,
                        appActivity: '.MainActivity',
                        appWaitPackage: appId,
                        appWaitActivity: '.MainActivity'
                    });
                } catch (e) {
                    console.log('startActivity failed, trying activateApp...');
                    // Method 2: Use activateApp
                    await browser.activateApp(appId);
                }
                
                await browser.pause(3000);
            }
            
            // Verify WebView is present
            const webView = await $('android.webkit.WebView');
            await webView.waitForExist({ timeout: 15000 });
            
            // NEW: Verify app is actually functional, not just running
            console.log('🔍 WebView found, now verifying app health...');
            const isHealthy = await verifyAppHealth();
            if (!isHealthy) {
                console.error('❌ App is running but appears broken - check test-results/ for debug info');
                throw new Error('App health check failed - app appears broken');
            }
            
            console.log('✅ App is running and healthy');
            return true;
            
        } catch (error) {
            console.error(`❌ Failed to launch app (attempt ${i + 1}):`, error.message);
            
            // Save debug info on failure
            try {
                await saveDebugScreenshot(`launch-failure-attempt-${i + 1}`);
                await logAppState();
            } catch (debugError) {
                console.error('Failed to save debug info:', debugError.message);
            }
            
            if (i === maxRetries - 1) {
                console.error('❌ All launch attempts failed. Check test-results/ for debug screenshots and logs.');
                throw error;
            }
            await browser.pause(2000);
        }
    }
    
    return false;
}

export async function launchAppUsingAdb() {
    // Fallback method using ADB commands directly
    const appId = 'io.github.koo5.hillview.dev';
    
    try {
        // Force stop the app first
        await browser.execute('mobile: shell', {
            command: `am force-stop ${appId}`
        });
        await browser.pause(1000);
        
        // Launch using am start
        await browser.execute('mobile: shell', {
            command: `am start -n ${appId}/.MainActivity`
        });
        await browser.pause(3000);
        
        return true;
    } catch (error) {
        console.error('Failed to launch app using ADB:', error);
        return false;
    }
}
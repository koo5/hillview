import { browser, $ } from '@wdio/globals';

export async function ensureAppIsRunning() {
    const appId = 'io.github.koo5.hillview.dev';
    const maxRetries = 3;
    
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
            
            // If we got here, app is running
            console.log('App is running and WebView is ready');
            return true;
            
        } catch (error) {
            console.error(`Failed to launch app (attempt ${i + 1}):`, error);
            if (i === maxRetries - 1) {
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
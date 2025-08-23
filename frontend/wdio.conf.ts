import type { Options } from '@wdio/types';
import { ensureAppIsRunning, prepareAppForTest, prepareAppForTestFast } from './test/helpers/app-launcher';

// Test configuration
const TEST_CONFIG = {
    // Set to false for faster development testing (skips data clearing)
    // Set to true for proper test isolation with clean app state
    CLEAN_APP_STATE: process.env.WDIO_CLEAN_STATE !== 'false',
    // Set to true to only restart before describe blocks, not every test case
    RESTART_PER_SUITE: process.env.WDIO_RESTART_PER_SUITE === 'true'
};

export const config: Options.Testrunner = {
    runner: 'local',
    autoCompileOpts: {
        autoCompile: true,
        tsNodeOpts: {
            project: './tsconfig.json',
            transpileOnly: true
        }
    },
    
    port: 4723,
    specs: [
        './test/specs/**/*.ts'
    ],
    exclude: [],
    
    maxInstances: 1,
    
    capabilities: [{
        platformName: 'Android',
        'appium:deviceName': 'Android Emulator',
        'appium:platformVersion': '14',
        'appium:automationName': 'UiAutomator2',
        'appium:app': './src-tauri/gen/android/app/build/outputs/apk/x86_64/debug/app-x86_64-debug.apk',
        'appium:noReset': false,
        'appium:fullReset': false,
        'appium:skipInstall': false,
        'appium:allowTestPackages': true,
        'appium:forceAppLaunch': true,
        'appium:appPackage': 'io.github.koo5.hillview.dev',
        'appium:appActivity': '.MainActivity',
        'appium:appWaitActivity': '.MainActivity',
        'appium:autoLaunch': true,
        'appium:appWaitDuration': 30000,
        'appium:uiautomator2ServerInstallTimeout': 60000,
        'appium:uiautomator2ServerLaunchTimeout': 60000,
        // Permission handling capabilities
        'appium:autoGrantPermissions': false, // Don't auto-grant to test permission flows
        'appium:autoAcceptAlerts': false, // Don't auto-accept alerts
        // Capabilities to improve screenshot stability
        'appium:screenshotQuality': 50, // Reduce quality for faster screenshots
        'appium:mjpegServerScreenshotQuality': 50,
        'appium:mjpegScalingFactor': 50,
        // Reduce retry attempts for faster failure recovery
        'appium:uiautomator2ServerReadTimeout': 20000,
        'appium:permissions': {
            'io.github.koo5.hillview.dev': {
                'android.permission.CAMERA': 'unset',
                'android.permission.ACCESS_FINE_LOCATION': 'unset',
                'android.permission.ACCESS_COARSE_LOCATION': 'unset'
            }
        }
    }],
    
    logLevel: 'info',
    bail: 1,  // Stop after first failure
    waitforTimeout: 10000,  // Wait timeout for element searches
    connectionRetryTimeout: 30000,  // Connection timeout for session creation
    connectionRetryCount: 0,  // Disable connection retries
    
    services: [
        ['appium', {
            command: 'appium',
            args: {
                relaxedSecurity: true,
                log: './logs/appium.log'
            }
        }]
    ],
    
    framework: 'mocha',
    reporters: ['spec'],
    
    mochaOpts: {
        ui: 'bdd',
        timeout: 60000,
        retries: 0  // Disable all test retries for faster failure
    },
    
    beforeSession: async function () {
        console.log('🢄Starting test session...');
    },
    
    before: async function () {
        console.log('🢄Initial session setup - preparing clean app state once...');
        // Do a one-time clean restart at the start of the session
        // This eliminates the need for individual test restarts
        if (TEST_CONFIG.CLEAN_APP_STATE) {
            console.log('🢄🧹 Session-level clean app preparation');
            await prepareAppForTest(true); // clearData = true
        } else {
            console.log('🢄⚡ Session-level fast app preparation');
            await prepareAppForTestFast();
        }
    },
    
    beforeTest: async function (test, context) {
        // Check if this is the first test in a suite
        const isFirstTestInSuite = context.specIndex === 0 || 
                                  context.testIndex === 0 ||
                                  !context.previousTest;
        
        if (TEST_CONFIG.RESTART_PER_SUITE && !isFirstTestInSuite) {
            // Skip restart for subsequent tests in same suite
            console.log('🢄⚡ Skipping restart - using existing app state within suite');
            return;
        }
        
        // Only do a lightweight health check - app was already prepared in 'before' hook
        console.log('🢄🔍 Quick health check before test...');
        try {
            // Just verify the app is still responsive (no restart unless absolutely necessary)
            const webView = await $('android.webkit.WebView');
            const webViewExists = await webView.isExisting();
            
            if (!webViewExists) {
                console.log('🢄⚠️ WebView missing, doing minimal restart...');
                await ensureAppIsRunning(false); // Don't force restart, just ensure it's running
            } else {
                console.log('🢄✅ App appears healthy, proceeding with test');
            }
        } catch (e) {
            console.log('🢄⚠️ Health check failed, doing minimal restart...');
            await ensureAppIsRunning(false); // Don't force restart, just ensure it's running
        }
    },
    
    afterTest: async function (test, context, { error, result, duration, passed, retries }) {
        // Always save a screenshot after each test for debugging
        const testName = test.title.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        
        if (error || !passed) {
            // Test failed - save comprehensive debug info
            console.log(`❌ Test failed: ${test.title}`);
            console.log(`📊 Error details: ${error?.message || 'Unknown error'}`);
            
            try {
                // Try screenshot first
                let screenshotSaved = false;
                try {
                    await driver.saveScreenshot(`./test-results/failed-${testName}-${timestamp}.png`);
                    screenshotSaved = true;
                    console.log('🢄📸 Failure screenshot saved');
                } catch (screenshotError) {
                    console.warn(`🢄⚠️ Screenshot failed: ${screenshotError.message}`);
                    if (screenshotError.message.includes('DeadObjectException')) {
                        console.log('🢄🔧 Device appears to have UiAutomation issues - skipping screenshot attempts');
                        // Skip all other screenshot attempts for this test
                        return;
                    }
                }
                
                // Log what's visible for debugging (even if screenshot failed)
                try {
                    const textElements = await driver.$$('//*[@text!=""]');
                    const visibleTexts = [];
                    for (let i = 0; i < Math.min(textElements.length, 10); i++) {
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
                        console.log('🢄📝 Visible text at test failure:', visibleTexts);
                    } else {
                        console.log('🢄📝 No visible text elements found');
                    }
                } catch (e) {
                    console.warn('🢄⚠️ Could not read text elements:', e.message);
                }
                
                // Save page source for detailed analysis
                try {
                    const pageSource = await driver.getPageSource();
                    const fs = require('fs').promises;
                    await fs.mkdir('./test-results', { recursive: true });
                    await fs.writeFile(`./test-results/failed-${testName}-${timestamp}-source.xml`, pageSource);
                    console.log('🢄💾 Page source saved for analysis');
                } catch (e) {
                    console.warn('🢄⚠️ Could not save page source:', e.message);
                }
                
                // Save device state info
                try {
                    const appState = await driver.queryAppState('io.github.koo5.hillview.dev');
                    const deviceInfo = `Test: ${test.title}\nTimestamp: ${timestamp}\nApp State: ${appState}\nError: ${error?.message || 'Unknown'}\nScreenshot Saved: ${screenshotSaved}\n`;
                    const fs = require('fs').promises;
                    await fs.writeFile(`./test-results/failed-${testName}-${timestamp}-info.txt`, deviceInfo);
                } catch (e) {
                    console.warn('🢄⚠️ Could not save device info:', e.message);
                }
                
            } catch (debugError) {
                console.error('🢄❌ Failed to save any debug info for failed test:', debugError.message);
            }
        } else {
            // Test passed - try to save a basic screenshot (but don't fail if it doesn't work)
            try {
                await driver.saveScreenshot(`./test-results/passed-${testName}-${timestamp}.png`);
            } catch (e) {
                // Silently ignore screenshot errors for passed tests - especially DeadObjectException
                if (e.message && e.message.includes('DeadObjectException')) {
                    console.log('🢄📸 Passed test screenshot skipped (UiAutomation dead)');
                } else {
                    console.log('🢄📸 Passed test screenshot skipped (device issues)');
                }
            }
        }
    }
};
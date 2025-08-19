import type { Options } from '@wdio/types';
import { ensureAppIsRunning } from './test/helpers/app-launcher';

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
        'appium:permissions': {
            'io.github.koo5.hillview.dev': {
                'android.permission.CAMERA': 'unset',
                'android.permission.ACCESS_FINE_LOCATION': 'unset',
                'android.permission.ACCESS_COARSE_LOCATION': 'unset'
            }
        }
    }],
    
    logLevel: 'info',
    bail: 0,
    waitforTimeout: 10000,
    connectionRetryTimeout: 120000,
    connectionRetryCount: 3,
    
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
        timeout: 60000
    },
    
    beforeSession: async function () {
        console.log('Starting test session...');
    },
    
    before: async function () {
        console.log('Ensuring app is running before tests...');
        await ensureAppIsRunning();
    },
    
    beforeTest: async function () {
        // Ensure app is in foreground for each test
        await ensureAppIsRunning();
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
                    console.log('📸 Failure screenshot saved');
                } catch (screenshotError) {
                    console.warn(`⚠️ Screenshot failed: ${screenshotError.message}`);
                    if (screenshotError.message.includes('DeadObjectException')) {
                        console.log('🔧 Device appears to have UiAutomation issues - using fallback debugging');
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
                        console.log('📝 Visible text at test failure:', visibleTexts);
                    } else {
                        console.log('📝 No visible text elements found');
                    }
                } catch (e) {
                    console.warn('⚠️ Could not read text elements:', e.message);
                }
                
                // Save page source for detailed analysis
                try {
                    const pageSource = await driver.getPageSource();
                    const fs = require('fs').promises;
                    await fs.mkdir('./test-results', { recursive: true });
                    await fs.writeFile(`./test-results/failed-${testName}-${timestamp}-source.xml`, pageSource);
                    console.log('💾 Page source saved for analysis');
                } catch (e) {
                    console.warn('⚠️ Could not save page source:', e.message);
                }
                
                // Save device state info
                try {
                    const appState = await driver.queryAppState('io.github.koo5.hillview.dev');
                    const deviceInfo = `Test: ${test.title}\nTimestamp: ${timestamp}\nApp State: ${appState}\nError: ${error?.message || 'Unknown'}\nScreenshot Saved: ${screenshotSaved}\n`;
                    const fs = require('fs').promises;
                    await fs.writeFile(`./test-results/failed-${testName}-${timestamp}-info.txt`, deviceInfo);
                } catch (e) {
                    console.warn('⚠️ Could not save device info:', e.message);
                }
                
            } catch (debugError) {
                console.error('❌ Failed to save any debug info for failed test:', debugError.message);
            }
        } else {
            // Test passed - try to save a basic screenshot (but don't fail if it doesn't work)
            try {
                await driver.saveScreenshot(`./test-results/passed-${testName}-${timestamp}.png`);
            } catch (e) {
                // Silently ignore screenshot errors for passed tests
                console.log('📸 Passed test screenshot skipped (device issues)');
            }
        }
    }
};
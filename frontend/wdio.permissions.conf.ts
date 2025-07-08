import { config as baseConfig } from './wdio.conf';
import type { Options } from '@wdio/types';

// Permission-specific test configuration
export const config: Options.Testrunner = {
    ...baseConfig,
    
    // Only run permission tests
    specs: [
        './test/specs/permissions.test.ts'
    ],
    
    // Override capabilities for permission testing
    capabilities: [{
        ...(baseConfig.capabilities as any)[0],
        // Ensure clean state for permission tests
        'appium:fullReset': true, // Reset app state and permissions
        'appium:noReset': false,
        // Don't auto-grant permissions
        'appium:autoGrantPermissions': false,
        'appium:autoAcceptAlerts': false,
        // Extended timeouts for permission dialogs
        'appium:newCommandTimeout': 300,
        'appium:adbExecTimeout': 60000
    }],
    
    // Increase timeouts for permission handling
    waitforTimeout: 15000,
    
    // More detailed logging for debugging
    logLevel: 'debug',
    
    // Mocha options with longer timeout
    mochaOpts: {
        ui: 'bdd',
        timeout: 90000 // 90 seconds for permission tests
    },
    
    // Add screenshot on failure
    afterTest: async function(test, context, { error }) {
        if (error) {
            await browser.takeScreenshot();
        }
    }
};
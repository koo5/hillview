import type { Options } from '@wdio/types';

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
        'appium:platformVersion': '16',
        'appium:automationName': 'UiAutomator2',
        'appium:app': './src-tauri/gen/android/app/build/outputs/apk/x86_64/debug/app-x86_64-debug.apk',
        'appium:noReset': false,
        'appium:fullReset': false,
        'appium:skipInstall': false,
        'appium:allowTestPackages': true,
        'appium:forceAppLaunch': true,
        'appium:appWaitActivity': '*'
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
    
    beforeTest: async function () {
        // Ensure app starts fresh
        await browser.terminateApp('io.github.koo5.hillview');
        await browser.activateApp('io.github.koo5.hillview');
        await browser.pause(2000); // Wait for app to fully load
    }
};
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
        'appium:appPackage': 'io.github.koo5.hillview',
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
            'io.github.koo5.hillview': {
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
    }
};
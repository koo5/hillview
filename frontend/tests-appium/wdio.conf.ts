// Tracks the spec FILE that last triggered a backend reset so beforeSuite
// recreates test users once per file (not once per nested describe) — the
// Appium analog of the Playwright `testUsers` auto-fixture.
let lastBackendResetFile = '';

export const config: WebdriverIO.Config = {
    //
    // ====================
    // Runner Configuration
    // ====================
    // WebdriverIO supports running e2e tests as well as unit and component tests.
    runner: 'local',
    tsConfigPath: './tsconfig.json',
    
    port: 4723,
    //
    // ==================
    // Specify Test Files
    // ==================
    // Define which test specs should run. The pattern is relative to the directory
    // of the configuration file being run.
    //
    // The specs are defined as an array of spec files (optionally using wildcards
    // that will be expanded). The test for each spec file will be run in a separate
    // worker process. In order to have a group of spec files run in the same worker
    // process simply enclose them in an array within the specs array.
    //
    // The path of the spec files will be resolved relative from the directory of
    // of the config file unless it's absolute.
    //
    specs: [
        './specs/**/*.ts'
    ],
    // Patterns to exclude.
    exclude: [
        // 'path/to/excluded/files'
    ],
    //
    // ============
    // Capabilities
    // ============
    // Define your capabilities here. WebdriverIO can run multiple capabilities at the same
    // time. Depending on the number of capabilities, WebdriverIO launches several test
    // sessions. Within your capabilities you can overwrite the spec and exclude options in
    // order to group specific specs to a specific capability.
    //
    // First, you can define how many instances should be started at the same time. Let's
    // say you have 3 different capabilities (Chrome, Firefox, and Safari) and you have
    // set maxInstances to 1; wdio will spawn 3 processes. Therefore, if you have 10 spec
    // files and you set maxInstances to 10, all spec files will get tested at the same time
    // and 30 processes will get spawned. The property handles how many capabilities
    // from the same test should run tests.
    //
    // Single emulator + single Appium server → no room for parallelism.
    // Higher values make every spec fight for the same WebView context
    // and lose; the full-suite failure mode is "No WebView context
    // available" on pretty much every before-all hook.
    maxInstances: 1,
    //
    // If you have trouble getting all important capabilities together, check out the
    // Sauce Labs platform configurator - a great tool to configure your capabilities:
    // https://saucelabs.com/platform/platform-configurator
    //
    capabilities: [{
        // capabilities for native Hillview app tests on Android Emulator
        platformName: 'Android',
        'appium:deviceName': 'Android GoogleAPI Emulator',
        'appium:platformVersion': '12.0',
        'appium:automationName': 'UiAutomator2',
        'appium:appPackage': 'cz.hillviedev',
        'appium:appActivity': '.MainActivity',
        'appium:noReset': false, // Reset app state between tests
        'appium:fullReset': false, // Don't reinstall, but clear app data
        // chromedriver is pinned (checked-in, gitignored binary); an explicit
        // executable overrides autodownload, so we don't set chromedriverAutodownload.
        // The onPrepare hook fails fast if this binary's major version drifts from
        // the emulator's System WebView.
        'appium:chromedriverExecutable': './chromedriver',
        'appium:ensureWebviewsHavePages': true,
        'appium:nativeWebScreenshot': true,
        'appium:recreateChromeDriverSessions': true
    }],

    //
    // ===================
    // Test Configurations
    // ===================
    // Define all options that are relevant for the WebdriverIO instance here
    //
    // Level of logging verbosity: trace | debug | info | warn | error | silent
    logLevel: 'info',
    //
    // Set specific log levels per logger
    // loggers:
    // - webdriver, webdriverio
    // - @wdio/browserstack-service, @wdio/lighthouse-service, @wdio/sauce-service
    // - @wdio/mocha-framework, @wdio/jasmine-framework
    // - @wdio/local-runner
    // - @wdio/sumologic-reporter
    // - @wdio/cli, @wdio/config, @wdio/utils
    // Level of logging verbosity: trace | debug | info | warn | error | silent
    // logLevels: {
    //     webdriver: 'info',
    //     '@wdio/appium-service': 'info'
    // },
    //
    // If you only want to run your tests until a specific amount of tests have failed use
    // bail (default is 0 - don't bail, run all tests).
    bail: 0,
    //
    // Set a base URL in order to shorten url command calls. If your `url` parameter starts
    // with `/`, the base url gets prepended, not including the path portion of your baseUrl.
    // If your `url` parameter starts without a scheme or `/` (like `some/path`), the base url
    // gets prepended directly.
    // baseUrl: 'http://localhost:8080',
    //
    // Default timeout for all waitFor* commands.
    waitforTimeout: 10000,
    //
    // Default timeout in milliseconds for request
    // if browser driver or grid doesn't send response
    connectionRetryTimeout: 120000,
    //
    // Default request retries count
    connectionRetryCount: 3,
    //
    // Test runner services
    // Services take over a specific job you don't want to take care of. They enhance
    // your test setup with almost no effort. Unlike plugins, they don't add new
    // commands. Instead, they hook themselves up into the test process.
    services: [
        // Enable `adb_shell` so tests can call `mobile: shell` for things
        // like `dumpsys notification` (used to verify the photo-upload
        // foreground notification without opening the shade UI). Scoped
        // to the single feature — safer than the nuclear --relaxed-security.
        ['appium', { args: { allowInsecure: 'uiautomator2:adb_shell' } }],
        'visual',
    ],

    // Framework you want to run your specs with.
    // The following are supported: Mocha, Jasmine, and Cucumber
    // see also: https://webdriver.io/docs/frameworks
    //
    // Make sure you have the wdio adapter package for the specific framework installed
    // before running any tests.
    framework: 'mocha',
    
    //
    // The number of times to retry the entire specfile when it fails as a whole
    // specFileRetries: 1,
    //
    // Delay in seconds between the spec file retry attempts
    // specFileRetriesDelay: 0,
    //
    // Whether or not retried spec files should be retried immediately or deferred to the end of the queue
    // specFileRetriesDeferred: false,
    //
    // Test reporter for stdout.
    // The only one supported by default is 'dot'
    // see also: https://webdriver.io/docs/dot-reporter
    reporters: ['spec'],

    // Options to be passed to Mocha.
    // See the full list at http://mochajs.org/
    mochaOpts: {
        ui: 'bdd',
        // 180s accommodates the longest legitimate tests (offline upload
        // queue drain ≈ 90s + camera capture overhead). `this.timeout()`
        // per-test isn't reliably picked up by @wdio/mocha-framework, so
        // we set the ceiling globally. `bail: 1` still keeps the suite
        // fail-fast at the spec level.
        timeout: 180000
    },

    //
    // =====
    // Hooks
    // =====
    // WebdriverIO provides several hooks you can use to interfere with the test process in order to enhance
    // it and to build services around it. You can either apply a single function or an array of
    // methods to it. If one of them returns with a promise, WebdriverIO will wait until that promise got
    // resolved to continue.
    /**
     * Gets executed once before all workers get launched.
     * @param {object} config wdio configuration object
     * @param {Array.<Object>} capabilities list of capabilities details
     */
    // Lock is acquired by lockAndRun.ts wrapper before wdio starts.
    onPrepare: async function () {
        // Fail-fast preflight: a WebView session can't attach when the pinned
        // chromedriver's MAJOR version doesn't match the emulator's active System
        // WebView. Unchecked, that surfaces as a cryptic "session not created …
        // only supports Chrome version N" deep in the first spec's before-all,
        // after Appium has already spun up — wasting a run. chromedriver is
        // gitignored and pinned via chromedriverExecutable, so a WebView
        // auto-update silently drifts it out of range. Catch it here, once,
        // before any worker or Appium session starts.
        const { execSync } = await import('node:child_process');
        const majorOf = (s: string): string | null => s.match(/(\d+)\.\d+\.\d+/)?.[1] ?? null;

        let cdMajor: string | null = null;
        let wvMajor: string | null = null;
        try {
            cdMajor = majorOf(execSync('./chromedriver --version', { encoding: 'utf8' }));
            // "  Current WebView package (name, version): (com.google.android.webview, 149.0.7827.159)"
            const wv = execSync('adb shell dumpsys webviewupdate', { encoding: 'utf8' });
            wvMajor = majorOf(wv.split('\n').find((l) => l.includes('Current WebView package')) ?? '');
        } catch (err) {
            // Don't let the check itself become a flaky gate (adb missing, no
            // device attached, dumpsys shape change): warn and let the run proceed
            // so a real mismatch still surfaces the usual way rather than this
            // preflight blocking an otherwise-fine environment.
            console.warn(`⚠️  chromedriver/WebView preflight skipped: ${err instanceof Error ? err.message : String(err)}`);
            return;
        }

        if (cdMajor && wvMajor && cdMajor !== wvMajor) {
            throw new Error(
                `chromedriver/WebView major-version mismatch: chromedriver ${cdMajor} vs Android System ` +
                `WebView ${wvMajor}. The WebView session cannot attach. Replace tests-appium/chromedriver ` +
                `with major ${wvMajor} (linux64) from ` +
                `https://googlechromelabs.github.io/chrome-for-testing/, or roll the emulator's System ` +
                `WebView back to major ${cdMajor}.`,
            );
        }
        console.log(
            cdMajor && wvMajor
                ? `✅ chromedriver ${cdMajor} matches Android System WebView ${wvMajor}`
                : `⚠️  chromedriver/WebView preflight: versions indeterminate (chromedriver=${cdMajor}, webview=${wvMajor}); skipped`,
        );
    },
    /**
     * Gets executed before a worker process is spawned and can be used to initialize specific service
     * for that worker as well as modify runtime environments in an async fashion.
     * @param  {string} cid      capability id (e.g 0-0)
     * @param  {object} caps     object containing capabilities for session that will be spawn in the worker
     * @param  {object} specs    specs to be run in the worker process
     * @param  {object} args     object that will be merged with the main configuration once worker is initialized
     * @param  {object} execArgv list of string arguments passed to the worker process
     */
    // onWorkerStart: function (cid, caps, specs, args, execArgv) {
    // },
    /**
     * Gets executed just after a worker process has exited.
     * @param  {string} cid      capability id (e.g 0-0)
     * @param  {number} exitCode 0 - success, 1 - fail
     * @param  {object} specs    specs to be run in the worker process
     * @param  {number} retries  number of retries used
     */
    // onWorkerEnd: function (cid, exitCode, specs, retries) {
    // },
    /**
     * Gets executed just before initialising the webdriver session and test framework. It allows you
     * to manipulate configurations depending on the capability or spec.
     * @param {object} config wdio configuration object
     * @param {Array.<Object>} capabilities list of capabilities details
     * @param {Array.<String>} specs List of spec file paths that are to be run
     * @param {string} cid worker id (e.g. 0-0)
     */
    // beforeSession: function (config, capabilities, specs, cid) {
    // },
    /**
     * Gets executed before test execution begins. At this point you can access to all global
     * variables like `browser`. It is the perfect place to define custom commands.
     * @param {Array.<Object>} capabilities list of capabilities details
     * @param {Array.<String>} specs        List of spec file paths that are to be run
     * @param {object}         browser      instance of created browser/device session
     */
    // before: function (capabilities, specs) {
    // },
    /**
     * Runs before a WebdriverIO command gets executed.
     * @param {string} commandName hook command name
     * @param {Array} args arguments that command would receive
     */
    // beforeCommand: function (commandName, args) {
    // },
    /**
     * Hook that gets executed before the suite starts.
     *
     * PARTIAL backend reset once per spec FILE, mirroring the Playwright
     * `testUsers` auto-fixture (tests-playwright/fixtures.ts). Appium's
     * noReset:false already clears APP state (login, prefs, DB) between spec
     * files, but the backend API server is shared and persists across files —
     * so a spec that never calls recreateTestUsers() inherits the previous
     * file's test-user photos/annotations (e.g. the "authorized" photo
     * placeholders authorize-upload leaves behind). recreateTestUsers()
     * cascade-deletes them, giving every spec a clean *test-user* slate.
     *
     * This deliberately does NOT wipe the whole DB: a local backend is often
     * loaded with a production clone owned by OTHER users, kept for manual dev
     * — those photos survive (and still render on the map during tests, which
     * is expected, not a leak). A spec that ASSERTS on map photo state must
     * clear completely and seed its own fixtures via clearDatabase() (see
     * helpers/backend.ts); the partial reset here is only enough for specs
     * that don't depend on ambient map content.
     *
     * Specs that call recreateTestUsers() themselves still do (they need the
     * returned passwords, and some re-clean mid-file); this just closes the
     * gap for the ones that don't and removes the cross-file ordering
     * dependency. Keyed on suite.file so nested describe() blocks within one
     * file (e.g. map-interaction's Button Controls / Touch Gestures) don't
     * wipe state mid-run.
     */
    beforeSuite: async function (suite) {
        if (suite.file && suite.file !== lastBackendResetFile) {
            lastBackendResetFile = suite.file;
            const { recreateTestUsers } = await import('./helpers/backend');
            console.log(`♻️  Recreating test users for spec file (partial reset; other users' photos persist): ${suite.file}`);
            await recreateTestUsers();
        }
    },
    /**
     * Function to be executed before a test (in Mocha/Jasmine) starts.
     * Ensures app starts fresh for each test
     */
    beforeTest: async function (test, context) {
        console.log(`🚀 Starting fresh test: ${test.title}`);

        // The noReset: false setting handles app state cleanup automatically
        // Wait for app to be ready after automatic reset
        await browser.pause(2000);
        console.log('🎯 App should be ready for testing');
    },
    /**
     * Hook that gets executed _before_ a hook within the suite starts (e.g. runs before calling
     * beforeEach in Mocha)
     */
    // beforeHook: function (test, context, hookName) {
    // },
    /**
     * Hook that gets executed _after_ a hook within the suite starts (e.g. runs after calling
     * afterEach in Mocha)
     */
    // afterHook: function (test, context, { error, result, duration, passed, retries }, hookName) {
    // },
    /**
     * Function to be executed after a test (in Mocha/Jasmine only)
     * Cleans up after each test
     * @param {object}  test             test object
     * @param {object}  context          scope object the test was executed with
     * @param {Error}   result.error     error object in case the test fails, otherwise `undefined`
     * @param {*}       result.result    return object of test function
     * @param {number}  result.duration  duration of test
     * @param {boolean} result.passed    true if test has passed, otherwise false
     * @param {object}  result.retries   information about spec related retries, e.g. `{ attempts: 0, limit: 0 }`
     */
    afterTest: async function(test, context, { error, result, duration, passed, retries }) {
        const status = passed ? '✅ PASSED' : '❌ FAILED';
        console.log(`🏁 Test completed: ${test.title} - ${status} (${duration}ms)`);

        if (error) {
            console.log(`❌ Test error: ${error.message}`);
        }

        // App state will be automatically reset before next test due to noReset: false
        console.log('🧹 Test cleanup complete - app will reset for next test');
    },


    /**
     * Hook that gets executed after the suite has ended
     * @param {object} suite suite details
     */
    // afterSuite: function (suite) {
    // },
    /**
     * Runs after a WebdriverIO command gets executed
     * @param {string} commandName hook command name
     * @param {Array} args arguments that command would receive
     * @param {number} result 0 - command success, 1 - command error
     * @param {object} error error object if any
     */
    // afterCommand: function (commandName, args, result, error) {
    // },
    /**
     * Gets executed after all tests are done. You still have access to all global variables from
     * the test.
     * @param {number} result 0 - test pass, 1 - test fail
     * @param {Array.<Object>} capabilities list of capabilities details
     * @param {Array.<String>} specs List of spec file paths that ran
     */
    // after: function (result, capabilities, specs) {
    // },
    /**
     * Gets executed right after terminating the webdriver session.
     * @param {object} config wdio configuration object
     * @param {Array.<Object>} capabilities list of capabilities details
     * @param {Array.<String>} specs List of spec file paths that ran
     */
    // afterSession: function (config, capabilities, specs) {
    // },
    /**
     * Gets executed after all workers got shut down and the process is about to exit. An error
     * thrown in the onComplete hook will result in the test run failing.
     * @param {object} exitCode 0 - success, 1 - fail
     * @param {object} config wdio configuration object
     * @param {Array.<Object>} capabilities list of capabilities details
     * @param {<Object>} results object containing test results
     */
    // Lock is released by lockAndRun.ts wrapper after wdio exits
    // onComplete: function(exitCode, config, capabilities, results) {
    // },
    /**
    * Gets executed when a refresh happens.
    * @param {string} oldSessionId session ID of the old session
    * @param {string} newSessionId session ID of the new session
    */
    // onReload: function(oldSessionId, newSessionId) {
    // }
    /**
    * Hook that gets executed before a WebdriverIO assertion happens.
    * @param {object} params information about the assertion to be executed
    */
    // beforeAssertion: function(params) {
    // }
    /**
    * Hook that gets executed after a WebdriverIO assertion happened.
    * @param {object} params information about the assertion that was executed, including its results
    */
    // afterAssertion: function(params) {
    // }
}

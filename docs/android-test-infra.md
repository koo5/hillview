# Android (Appium) test infrastructure

Specs live in `frontend/tests-appium/specs/`. Helpers in `helpers/`.
Config in `wdio.conf.ts`. This doc covers the non-obvious pieces a new
contributor would otherwise re-discover by grepping.

## Appium capabilities worth knowing

- **Dev package**: `cz.hillviedev` (prod is `cz.hillview`). Capabilities
  pin `appium:appPackage` to the dev one. The WebView context name is
  `WEBVIEW_cz.hillviedev`.
- **Driver**: UiAutomator2.
- **`noReset: false`, `fullReset: false`**: between *sessions* (per
  spec file) Appium clears app data. Within a single spec file (session),
  state persists across `it` blocks — including SharedPreferences,
  permissions, login, FCM registration, captured-photo DB rows. If a
  test needs per-`it` isolation, use `terminateApp` + `activateApp` in
  `beforeEach` (see `specs/deep-link-auth.test.ts` for the pattern).
- **`allowInsecure: 'uiautomator2:adb_shell'`** is opted-in in
  `wdio.conf.ts` services. Enables `driver.execute('mobile: shell', …)`
  scoped to that one feature (safer than `--relaxed-security`). Used
  for `dumpsys notification`, `am` commands, etc.

## Cheat sheet for the less-obvious mobile: commands

| Need                             | Use                                                                                           |
| -------------------------------- | --------------------------------------------------------------------------------------------- |
| Turn wifi/data off and on        | `driver.execute('mobile: setConnectivity', { wifi: true, data: true })` — NOT `setNetworkConnection` (deprecated, fails on modern Android). |
| Fire a deep link                 | `driver.execute('mobile: deepLink', { url, package })`. Back-to-back calls can be dropped — restart the app between invocations if a spec fires more than one. |
| Fire an arbitrary intent         | `driver.execute('mobile: startActivity', { component, extras: [['s', 'click_action', '/settings']] })` — extras use `adb shell am`-style `[type, key, value]` triples. |
| Background the app (no kill)     | `driver.execute('mobile: backgroundApp', { seconds: -1 })` — `-1` means indefinitely; bring back with `driver.activateApp(pkg)`. |
| Kill the app (simulate swipe-from-recents) | `driver.execute('mobile: shell', { command: 'am', args: ['kill', pkg] })`. Different from `driver.terminateApp(pkg)` — the latter uses `am force-stop`, which puts the package in the force-stopped state and makes Android refuse all future broadcasts (including FCM) until the user re-launches. |
| Check active/recent notifications | `driver.execute('mobile: shell', { command: 'dumpsys', args: ['notification', '--noredact'] })`. Parse `NotificationRecord(…)` stanzas for `when=`, and the shorter `StatusBarNotification(…)` entries in `mArchive` for recent history. |

## Backend test hooks

Both tests and prod ops can hit these; they're localhost-only
(`require_internal_ip`), so Caddy blocks them externally.

- `POST /api/internal/debug/delays {name, seconds}` — inject a server-side
  sleep on a named hot path. Current tenant: `authorize_upload` (the
  photo-upload auth hop). Used by the upload-notification test to stretch
  the worker's runtime so the foreground notification stays visible
  long enough to poll.
- `POST /api/internal/debug/push-enabled {enabled}` — gate all outgoing
  FCM/UnifiedPush. Reset by `recreate-test-users` / `clear-database`.
  See `docs/push-notifications.md`.
- `POST /api/internal/debug/force-logout-user {username, clear?}` —
  mark a user's sessions invalid. Next API call / refresh returns 401.
  Self-clears on password re-auth. Drives the "Login Required"
  notification path.
- `POST /api/internal/debug/clear-notifications` — truncate the
  `notifications` table so activity-broadcast's 12-hour dedup filter
  doesn't skip the test user.

## Test hygiene — current weaknesses

These don't bite today but a future reorganization could trip on them.
Listed in rough order of risk.

### Module-level `permissionsGranted` flags

Several specs (e.g. `specs/photo-workflow.test.ts`,
`specs/upload-queue-offline.test.ts`) keep a module-scoped
`let permissionsGranted = false` and flip it to `true` after the first
camera-permission dance completes. That works only because Appium
preserves app data across `it` blocks within a single session. Two
sharp edges:

- If a future session-level reset wipes camera permissions but the
  module variable stays set, subsequent tests skip the dialog-accept
  path and fail silently on the next `byTestId('single-capture-button')`
  wait.
- Specs that run in isolation (`--spec foo.test.ts`) can't benefit from
  the caching — every solo-run pays the first-open permission cost even
  when the emulator has had the permission for months.

Fix when bothersome: probe permission state via `adb shell pm list
permissions --user 0 | grep granted` or query `PackageManager.checkPermission`
through a plugin invoke. Until then, assume the current pattern.

### Order-coupled sibling tests

`specs/deep-link-auth.test.ts` has two cases — rejected-token first
(runs from clean state), happy-path second (runs after rejected leaves
state). Swapping the order would leave the rejected-token case running
against an already-logged-in app and fail trivially. The file's comment
is clear about the intent but the ordering isn't enforced.

Fix when bothersome: put each case in its own `describe`, each with
its own `before` that restarts the app explicitly. Or go the other way
and use `terminateApp` + `activateApp` in `beforeEach` to isolate.

### `mockCamera` localStorage dependency

Most capture-flow specs set `localStorage.setItem('mockCamera', 'true')`
once in `before` and rely on it sticking. WebView localStorage does
persist across `terminateApp`/`activateApp`, but not across a fullReset
/ `pm clear`. A spec that restarts the session for isolation has to
re-set `mockCamera` itself.

### `recreateTestUsers` doesn't cascade to everything

`POST /api/debug/recreate-test-users` wipes users → cascades to photos,
hidden_users, annotations, etc. but **leaves** `push_registrations`
and the Kotlin-side Room DB (`photos.db`). If a future spec asserts on
an empty push_registrations / empty device-photos table, those would
need explicit wipes too. Current test suite sidesteps this by using
relative assertions (count-before vs count-after, or set-diff against
a pre-snapshot) rather than absolute values.

### Shared FCM-broadcast setup is expensive to repeat

`specs/fcm-broadcast.test.ts` registers with FCM in the spec's
`before()` and reuses the registration across three `it` blocks. That's
fine for now, but if a future test wants to assert on a fresh FCM token
(e.g. re-register after change-password), it has to explicitly unselect
and re-select the distributor. The helpers (`enableNotifications`,
`selectPushDistributor`, `getPushRegistrationStatus`) are in the spec
file — consider promoting them to `helpers/push.ts` when a second spec
needs them.

### Dumpsys `when`-baseline matching is fragile on low-activity emulators

`fcm-broadcast.test.ts`'s final form uses a key-set diff (pre-snapshot
vs post-snapshot) rather than parsing `when=` timestamps out of
`NotificationRecord` stanzas. Earlier iterations tried the timestamp
approach and ran into the emulator moving notifications straight to
`mArchive` (where `when=` isn't present). Record this if you design a
new push-assertion helper — the key-set diff is the reliable primitive,
the `when=`-based one isn't.

### No retry on transient Appium/Chromedriver session drops

A few `before` hooks include a `source.includes('error sending request')`
→ `browser.refresh()` fallback, but the rest of the tests don't protect
against Chromedriver session loss after e.g. `terminateApp` if the
spec doesn't re-wait for WebView context. Pattern to follow:
`await driver.activateApp(pkg)` → `browser.pause(3000)` → loop on
`driver.getContexts()` until `WEBVIEW_*` appears → `ensureWebViewContext()`.
Extracted as `waitForWebViewContext` in a couple of specs; could move
to `helpers/`.

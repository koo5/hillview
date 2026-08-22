# Hillview KMP/CMP app

Ground-up rewrite of the Android app in Kotlin Multiplatform + Compose
Multiplatform, replacing the Tauri app in `../frontend/`.

Follows the post-May-2026 default KMP project structure (thin app modules,
required by AGP 9 — the Android application plugin can no longer live in a
multiplatform module):

```
frontend2/
├── shared/       # KMP library: all app code, Compose UI in commonMain
│   └── src/
│       ├── commonMain/   # UI + logic shared by all platforms
│       ├── androidMain/  # Android actuals
│       └── jvmMain/      # Desktop actuals
├── androidApp/   # thin Android application module (entry point + packaging)
└── desktopApp/   # thin desktop JVM app — mainly here for Compose Hot Reload
```

iOS is intentionally not wired up yet (needs macOS). When the time comes, add
`iosArm64()`/`iosSimulatorArm64()` targets to `shared/build.gradle.kts` and an
`iosApp/` Xcode project — the kmp.jetbrains.com wizard output can be used as a
reference.

## Versions

Kotlin 2.4.10, Compose Multiplatform 1.11.1, AGP 9.3.1, Gradle 9.5.1.
The Compose compiler plugin is versioned with Kotlin (same `kotlin` ref in
`gradle/libs.versions.toml`). The `compose.*` Gradle dependency aliases are
deprecated since CMP 1.10, so libraries are declared directly in the version
catalog (the sole exception is `compose.desktop.currentOs` in `desktopApp`,
which resolves the OS-specific Skiko artifact).

Note AGP 9 has built-in Kotlin: `androidApp` applies only
`com.android.application` + the Compose compiler plugin, **not**
`org.jetbrains.kotlin.android`.

## JDK

Use a JetBrains Runtime (JBR) — it carries desktop-relevant fixes. One ships
with Android Studio; on this machine:

```fish
set -x JAVA_HOME /snap/android-studio/current/jbr
```

In Android Studio / IntelliJ, set Gradle JDK to the bundled JBR
(Settings → Build Tools → Gradle → Gradle JVM).

Note the bundled JBR moves when Android Studio updates itself, and nothing
pins it — which has bitten once: the JBR went to **JDK 25**, and while this
app (Gradle 9.5.1) was fine, the Tauri project (Gradle 8.14.3, Kotlin 2.0.20)
died at `IllegalArgumentException: 25.0.2` inside `JavaVersion.parse`, since
that toolchain predates JDK 25. A warm Gradle daemon masked it for hours.
Build the Tauri Android project with `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`
(`apt install openjdk-21-jdk-headless`).

## Commands

Everything assumes `JAVA_HOME` points at the JBR (see above). On a
RAM-constrained box, wrap gradle in a scope:
`systemd-run --user --scope -p MemoryMax=12G ./gradlew …`.

```bash
# Android debug APK (output: androidApp/build/outputs/apk/debug/androidApp-debug.apk)
./gradlew :androidApp:assembleDebug

# Install on a running emulator/device (or: adb install -r <apk>)
./gradlew :androidApp:installDebug

# Run the desktop app
./gradlew :desktopApp:run

# Desktop with Compose Hot Reload (bundled with CMP since 1.10)
./gradlew :desktopApp:hotRun --auto
```

Install-under-a-running-app gotcha: `adb install -r` while the app is open
leaves the OLD code running (and even screencaps blank) — force-stop and
relaunch after installing:

```bash
adb shell am force-stop cz.hillview.debug
adb shell am start -n cz.hillview.debug/cz.hillview.MainActivity
```

## Tests

Four layers, cheapest first:

```bash
# 1. Pure rules + desktop Compose UI tests (no device; ~130 tests)
./gradlew :shared:jvmTest

# 2. The same commonTest rules on the Android target's JVM
./gradlew :shared:testAndroidHostTest

# 3. Shared-module instrumented tests (needs an emulator/device):
#    EXIF golden, storage chain, map gestures with real MotionEvents
./gradlew :shared:connectedAndroidDeviceTest

# 4. App-level behaviour tests (needs an emulator/device): the Appium
#    scenario ports driving the real MainActivity through Compose semantics
./gradlew :androidApp:connectedDebugAndroidTest
```

Notes for the device layers:
- Filtering instrumented tests uses
  `-Pandroid.testInstrumentationRunnerArguments.package=cz.hillview.map`
  (`--tests` is not a connected-test option).
- ddmlib finds the adb server via `ANDROID_ADB_SERVER_PORT` (it ignores
  `ADB_SERVER_SOCKET`) — only relevant when driving a forwarded adb.
- Camera still-capture needs an API 34+ image (API 31 + CameraX 1.6
  camera-pipe loses capture callbacks), and the emulated camera's JPEG
  EXIF is canned — verify exposure via CaptureResult logs, never EXIF.

## Emulator

`scripts/emulator.sh {start|stop|status}` boots the `Medium_Phone_API_36`
AVD headless with a CPU quota (an unguarded emulator idles at ~800% CPU)
and a memory cap, clears the stale multiinstance.lock that silently blocks
boots, and waits for `boot_completed`.

The AVD's back camera is `hw.camera.back = emulated` (not virtualscene):
the virtualscene camera lacks MANUAL_SENSOR, which the shutter-time
control gates on.

Useful emulator drives:

```bash
adb emu geo fix <lng> <lat>        # set the GPS position
# synthesise a compass heading θ for an upright phone:
adb emu sensor set magnetic-field <-48.4*sinθ>:5.9:<-48.4*cosθ>
```

## App identity

- `applicationId`: `cz.hillview` for release; debug builds get
  `applicationIdSuffix = ".debug"` → `cz.hillview.debug`, labeled
  "Hillview Dev", so they install alongside the production Tauri app (the old
  dev Tauri app `cz.hillviedev` never conflicted). `app_name` is a per-build-
  type `resValue` — note AGP 9 needs `buildFeatures { resValues = true }`.
- Android namespace: `cz.hillview` (app) / `cz.hillview.shared` (library)
- Kotlin package everywhere: `cz.hillview`

## Signing

Both build types are signed with **our own key**, not the SDK's debug key.
Every machine's `~/.android/debug.keystore` holds the same `CN=Android Debug`
certificate, so a debug-signed APK has an identity shared with every test
build and malware sample ever scanned — no reputation of its own, which is
the profile a sideload scanner treats with suspicion.

The key lives outside the repo, at `~/secrets/frontend2-keystore.properties`:

```properties
storeFile=/home/you/secrets/hillview-frontend2-dev.jks
keyAlias=hillview-frontend2-dev
password=...
```

Deliberately NOT `~/secrets/keystore.properties` — that path is what
`frontend/scripts/patch-android-gen-files.py` reads for the **Tauri** app's
release signing, and Play App Signing binds the first upload key, so a
provisional key must not be able to become that by accident.

Without the file the build still works, falling back to the debug key: a
checkout without the secret must not be unbuildable. To create one:

```fish
keytool -genkeypair -v -keystore ~/secrets/hillview-frontend2-dev.jks \
  -alias hillview-frontend2-dev -keyalg RSA -keysize 4096 -validity 10000 \
  -dname "CN=Hillview Dev, O=Hillview, C=CZ"
```

10000 days so a provisional key CAN later be promoted to a real upload key
(Google requires validity past 2033) rather than regenerated.

**Changing the key forces an uninstall.** Android refuses to update an app
whose certificate changed (`INSTALL_FAILED_UPDATE_INCOMPATIBLE`), and
uninstalling wipes app data — both Room databases and the prefs, i.e. the
photo queue and its provenance rows. The JPEGs in DCIM survive; the rows that
know their bearing, licence and upload state do not. Drain the upload queue
before switching keys.

## Features

### Clock calibration video (`shared/src/*/kotlin/cz/hillview/clockvideo/`)

Native reimplementation of the Tauri app's recorder
(`ClockVideoRecorder.svelte` + `ClockVideoWriter.kt`): the rear camera films
an external camera's clock screen while a CameraX `OverlayEffect` burns a
phone-time QR (unix ms) into every VIDEO_CAPTURE frame. Frames are stamped
from the **sensor timestamp** mapped to the epoch (anchored per frame so NTP
steps can't skew it) — better than the old rVFC/draw-time stamps. Output:
`GeoTrackingDumps/hillview_clockvideo_<ms>.mp4` + sidecar `.json` (schema v2,
still `qr.panel_rect`-compatible with pics' `video_time_correction.py`). The
effects pipeline physically rotates the buffer, so files carry no rotation
metadata and the QR panel sits upright at (16,16) in final-video pixels.

Verified end-to-end on the API 36 emulator (2026-08-04): 34/34 written frames
decoded to monotonic in-window stamps inside `panel_rect`
(`oneoff/scripts/2026-08-04_0735_clockvideo_kmp_qr_probe.py`); the only
anomaly was emulator-encoder frame-dropping, not a recorder defect.

The camera binds when the screen opens (aim first, record second — Start/Stop
only control the `Recording`, the camera stays warm between takes). The
preview shows a translucent **ghost of the QR panel region** (the burn-in
itself only exists on the recorded stream, keeping `panel_rect` exact) so you
can aim the camera's menu clear of it; a shared `ViewPort` makes the preview
FOV match the recording. Two interop gotchas encoded in `CameraPane`:
PreviewView needs `ImplementationMode.COMPATIBLE` + `Modifier.clipToBounds()`
or the viewport-scaled preview draws outside the pane (Compose interop
containers don't clip child views).

UI test hooks: Compose `testTag`s exposed as resource-ids
(`testTagsAsResourceId` in MainActivity), mirroring the old `data-testid`
convention — `home-clock-video-button`, `clock-video-start-button`,
`clock-video-stop-button`, `clock-video-status`.

## Backend

Same backend as the rest of the repo (`docker compose up -d api`, port 8055).
From the Android emulator use `http://10.0.2.2:8055`; from desktop,
`http://localhost:8055`. The app's server URL lives in upload settings and
is always the FULL API URL (`…/api`) — never assembled from a host.

For the full capture→upload loop against a local backend, source
`~/env/android_emu` (fish) before `docker compose up` — it carries the
`WORKER_URL` override the emulator needs (`http://10.0.2.2:8056`). Gotcha:
the api container loses that override on a bare restart; re-run the
compose up from the env file. Dev login: `test` / `StrongTestPassword123!`.

## Photo folder naming

The DCIM folder is build-configured: `Hillview2` in both build types —
this app generation keeps its own folder, never mixing with the Tauri
app's `DCIM/Hillview` on the same device. The `HILLVIEW_FOLDER` env var
at build time overrides it. See androidApp/build.gradle.kts.

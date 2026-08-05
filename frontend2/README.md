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

## Commands

```bash
# Android debug APK (output: androidApp/build/outputs/apk/debug/)
./gradlew :androidApp:assembleDebug

# Install on a running emulator/device
./gradlew :androidApp:installDebug

# Run the desktop app
./gradlew :desktopApp:run

# Desktop with Compose Hot Reload (bundled with CMP since 1.10)
./gradlew :desktopApp:hotRun --auto

# Shared-module unit tests (JVM)
./gradlew :shared:jvmTest
```

## App identity

- `applicationId`: `cz.hillview` for release; debug builds get
  `applicationIdSuffix = ".debug"` → `cz.hillview.debug`, labeled
  "Hillview Dev", so they install alongside the production Tauri app (the old
  dev Tauri app `cz.hillviedev` never conflicted). `app_name` is a per-build-
  type `resValue` — note AGP 9 needs `buildFeatures { resValues = true }`.
- Android namespace: `cz.hillview` (app) / `cz.hillview.shared` (library)
- Kotlin package everywhere: `cz.hillview`

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
`http://localhost:8055`. Ktor client + kotlinx-serialization + Coil are
pre-declared in the version catalog but not yet wired into any module.

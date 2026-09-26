# frontend2 — the KMP/Compose rewrite

Kotlin Multiplatform + Compose Multiplatform port of the Svelte/Tauri app in
`/frontend`. Shared Kotlin that BOTH apps compile lives in `/shared-kt`.

## Read this first: one state

**There is one user-facing location/orientation state (`MapStateHolder`).
Everything either writes it or reads it. Nothing talks to the hardware behind
its back.** See [docs/one-state.md](../docs/one-state.md).

This is the load-bearing idea extracted from the original, and every geo bug
this port has produced has been a violation of it — a pane with its own
sensor subscription, a second copy of an intent, two actors configuring one
engine. If you need a field the state does not have, ADD IT TO THE STATE;
that is what happened to `pitch`, which a photo used to sample separately
from its own bearing.

`OneStateArchitectureTest` (in `:shared:jvmTest`) enforces the read side, so
a new side channel fails the build.

The upload stack has the same shape of rule — one scheduler, one drain — in
[docs/upload-one-funnel.md](../docs/upload-one-funnel.md), enforced by
`UploadFunnelArchitectureTest`.

## The original is the specification

The Tauri app carries known-good semantics, worked out against real use. When
porting, read it first — `frontend/src/lib/`, especially `mapState.ts`,
`compass.svelte.ts`, `bearingTracking.ts`, `Map.svelte`,
`CameraCapture.svelte`. Check `/shared-kt` for a Kotlin twin before writing
one. Divergences are allowed, but they are DECISIONS: state them at the call
site and in `docs/frontend2-status.md`, never as silence.

What the original does is already written down control by control in
`docs/tauri-map-ui-contract.md`, `docs/tauri-capture-ui-contract.md` and
`docs/tauri-viewer-ui-contract.md`; what it is *supposed* to do, as its test
suites assert it, in `docs/app-behaviour-scenarios.md`. Port from those, not
from memory.

## Logging

Tags come from `hvTag("GeoEngine")` (shared-kt, `LogTag.kt`) — never a
hand-written `"hv-…"` string. The prefix exists in one place, and
`LogTagConventionTest` fails the build if a tag skips the helper; it used to be
a convention held by 49 copies, and three tests had already lost it.

```bash
adb logcat | grep hv-                      # this project's own output
adb logcat --pid=$(adb shell pidof cz.hillview.debug)   # ...and what the
                                           # PLATFORM says about it
```

Prefer the PID form when hunting a crash: a `FATAL EXCEPTION` is logged under
`AndroidRuntime`, not under any `hv-` tag, so the grep hides exactly the thing
you are looking for. The in-app event log (`EventLog.record`) is for
things a USER may need to see later — a re-registration, an export, a stand
down; it survives without a cable attached and shows up in the Event log
screen.

## Sensors and battery

When the inertial sensors run, what every constant is pinned to, and what breaks
if you change the window length or add a fast-mode toggle:
[docs/imu-sampling-design.md](../docs/imu-sampling-design.md). Read it before
touching `GeoConfig`, `GeoDefaults` or anything that claims the engine — the
claim merge is `any { }`, so a per-screen toggle silently does nothing while
another claim is live.

## Building and testing

```bash
export JAVA_HOME=/snap/android-studio/current/jbr   # NOT the Tauri app's JDK 21
./gradlew :shared:jvmTest :shared:testAndroidHostTest   # host tests
./gradlew :androidApp:assembleDebug                     # APK
# Which build is on the phone: Settings footer, or `adb logcat | grep hv-build`
# → "0.1.0 · <git sha>[+<diff hash> (uncommitted)] · <commit time>" (BuildInfo,
# stamped from git content in androidApp/build.gradle.kts — not the clock)
./gradlew :shared:connectedAndroidDeviceTest \
    -Pandroid.testInstrumentationRunnerArguments.class=<FQCN>   # on a device
```

Builds are memory-hungry; wrap them when the machine is loaded:
`systemd-run --user --scope -p MemoryMax=12G ./gradlew …`

Emulator: this machine reaches one over `ANDROID_ADB_SERVER_PORT=5038` as
well as a local AVD. Its synthesized rotation vector does NOT follow
`adb emu sensor set acceleration/magnetic-field`, so it cannot settle
questions about sensor fusion or device pose — only a real phone can.

## Orientation

`docs/frontend2-status.md` is the status page: what is done, what is
deferred, and the findings that cost a session to learn. Read it before
starting something that sounds like it has been touched before. It links
the design records it grew: `frontend2-rewrite-plan.md`,
`frontend2-geo-engine-design.md` (the one position/bearing stream — built;
the reasoning is the valuable part), `frontend2-capture-backlog.md`.

[docs/native-auth.md](../docs/native-auth.md) covers the Credential Manager +
Google ID-token login — concepts, security reasoning, and where everything
lives.

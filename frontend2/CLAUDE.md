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

## Logging

Every tag carries the `hv-` prefix (`hv-GeoEngine`, `hv-Sensors`), so the
whole app is one grep on a real device:

```bash
adb logcat | grep hv-
```

Keep it when adding a tag. The in-app event log (`EventLog.record`) is for
things a USER may need to see later — a re-registration, an export, a stand
down; it survives without a cable attached and shows up in the Event log
screen.

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
starting something that sounds like it has been touched before.

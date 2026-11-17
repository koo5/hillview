# frontend2: positive-up pitch and the level indicator

Handoff, written 2026-11-17. The user agreed this plan that day. It is the frontend2 half of
the follow-ups in [photo-pose-and-level-gates.md](photo-pose-and-level-gates.md). Read that
doc's *Conventions* section and its level-indicator rules before starting. The web half is
[web-capture-level-stamp.md](web-capture-level-stamp.md), run separately.

## The goal

Three changes, in this order:

- **The app's pitch is positive up, as everywhere else in the stack.** On the server,
  `photos.pitch` has been positive up (GPano) since commit `f42dcceb`, derived from the
  capture stamp by `common/capture_pose.py`. The app itself still holds positive DOWN, in
  `DeviceAttitude.pitch`, `BearingState.pitch` and `PhotoEntity.pitch`.
- **"Write EXIF" stamps carry the same objects as the fast-write path.** That is
  `capture_timing` and `inertial`, beside `attitude`.
- **The capture screen gets a level indicator** that says whether the shot will pass the
  Panoramax gates: |pitch| ≤ 20° and |roll| ≤ 10°.

## Already decided, don't re-open

- **The upload stamp keeps its sign.** `attitude.pitch_deg` stays positive down, and
  `metadata_version` stays 3. `capture_pose` negates `pitch_deg` for every version from 1 up,
  and has no v4 branch. So a flipped stamp would be stored inverted, unless the server learned
  v4 first.
- **Stop sending the top-level upload `pitch`.** Every current capture carries `attitude` and
  `inertial`, so the server never reads it (`_from_upload_pitch` in `capture_pose.py` reads it
  only when the stamp has neither). And once the app is positive up, a stray value there would
  be negated into the wrong sign.
- **`shared-kt`'s sensor code does not flip.** That is `EnhancedSensorService`, `CameraPose`
  and `OrientationSensorData`. The Tauri app will likely not have another release (the user,
  2026-11-17), so that is no longer the reason. The reason is that everything below the one
  state wants positive down: the stamp, the bearings table and the IMU ring's raw rows. The
  conversion belongs where samples enter the one state. `shared-kt` must still compile into
  the Tauri build.
- **Roll is not changed in the app.** Only the indicator reduces it to the nearest quarter
  turn.
- **The indicator follows the shared rules** in the plan doc ("Capture guidance for
  Panoramax: the level indicator"). That means the gate limits, `capture_pose`'s maths and
  the one state's reading; it never refuses the shutter, it is hidden in car mode, and it
  shows always by default.

## Read first

- `frontend2/CLAUDE.md`, and `docs/one-state.md`. `OneStateArchitectureTest` enforces the read
  side, so the indicator must read the state, not a sensor.
- `docs/recon-capture-metadata.md`, "Pitch has three homes" and the 2026-11-15 section on
  `photos.pitch` and `photos.roll`.
- `docs/imu-sampling-design.md`, before anything that touches when sensors run.

## Where raw pitch enters the one state

**There are two entry points, not one.** The 2026-11-16 research named only the first.

- **`toDeviceAttitude`** (in `AttitudeMapping.kt`) builds the attitude that
  `MapStateHolder.updateDeviceAttitude` publishes. `GeoEngine`'s attitude ring builds the
  same record, and the shutter stamp is looked up in that ring.
- **The compass callback in `MapSensorController.startBearing`** (in `MapScreen.android.kt`)
  passes the raw `OrientationSensorData.pitch` as `onHeading`'s fourth argument. The `MapScreen`
  effect that started it hands that to `state.updateBearing(pitch = pitch)`, so it becomes
  `BearingState.pitch` without passing through `toDeviceAttitude`.

Route both through one named conversion function, so a third entry point has an obvious
thing to call. If a structural test can assert that no `OrientationSensorData.pitch` reaches
the state except through it, add one, in the manner of `OneStateArchitectureTest`.

## Readers to convert or check

Each one either converts back to positive down or relies on positive up. Find them again
with a structural query rather than trusting this list. A grep for `.pitch` misses
`pitchDeg`, and the other way round.

- **`attitudeProvenanceJson`** (`PhotoCapture.kt`) writes `pitch_deg`. Negate it back here.
  `AttitudeProvenanceTest` must keep pinning positive down. `PhotoExifWriter` uses the same
  function, so the EXIF stamp follows.
- **The bearings table.** `MapStateHolder.updateBearing` passes `attitude?.pitch` to
  `sink.writeBearingRow`, and `TrackingSink`'s `writeBearingRow` stores it with
  `storeBearingNamed`. The engine's own sensor rows in that table are positive down, so
  convert back at the sink, or the table mixes signs.
- **The IMU ring** (`ImuRing.KIND_POSE` in `GeoEngine`) stores `raw.pitch` from
  `OrientationSensorData`, which does not flip. Leave it alone.
- **`ViewDirection`** (`OverlapRun.kt`) is documented as positive down, and `turnBetween`
  builds the lens vector with `-sin(p)`. The angle between two views is the same under either
  sign, but fix the doc and the formula together so they stay honest. `OverlapTrigger`'s tests
  show whether anything else cared.
- **The capture overlay's `attitude-readout`** (`CameraOverlayUi.kt`) prints `↕` from
  `PhotoCaptureState.pitchDeg`. Both that comment and the field's own doc say positive looking
  down. The number flips, so update both. Check whether a test pins the text.
- **`SensorSnapshot.pitchDeg`** flows through `CaptureScreen` and `SharedStackUploadPipeline`
  into `PhotoEntity.pitch`. It becomes positive up for new photos.
- **`PhotoUploadLogic.buildUploadMetadata`** (`shared-kt`) puts `pitch` in the metadata.
  Remove that line, per the decision above, and keep its explanatory comment as history.
  Tauri's `addPhotoToDatabase` never set a pitch, so nothing else is affected.

## Stored data

- **A Room migration negates the stored `PhotoEntity.pitch`** where it is not null.
  `PhotoDatabase` is in `shared-kt`, so the migration compiles into the Tauri build too. That
  is harmless, because Tauri rows have a null pitch, but check the claim on its writer.
  Photos still in the outbox are fine: their `attitudeJson` is already serialized, and the
  top-level pitch no longer travels.
- **Rename the photo dump's `pitch` column** (`PhotoTableDump`) in the same release, for
  example to `pitch_up_deg`, so no exported CSV mixes signs under one header. Look for
  anything that reads those CSVs, such as an enrich or recon importer, before renaming.
- **Then let `DevicePhotoLoader` (`shared-kt`) pass the pitch to the viewer.** Today local
  photos reach `PhotoData.toMarker` with no pitch and count as level. With positive up they
  can take part in `pitchNeighbour`'s up and down. An uploaded photo still shows its server
  copy (`collapseTwins`), which is already positive up.

## "Write EXIF" stamps

With that setting on, the worker keeps the file's own UserComment. The one `PhotoExifWriter`
writes carries `attitude` only, so `capture_pose` reads it as a pre-versioning row: portrait
works, landscape and upside-down get no pitch or roll and fail the gates. Make
`PhotoExifWriter` write the same `capture_timing` and `inertial` objects that the fast-write
path sends in the upload metadata, built by the same functions rather than copies.
`PhotoExifWriterTest` (a device test) is the place to pin it. The setting is off by default,
and no photo in the 2026-11-15 data was affected.

## The level indicator

- **What it reads:** `PhotoCaptureState`, which mirrors `stampAttitude` from the one state.
  Use its `pitchDeg` (positive up after the work above) and `imageRollDeg`, which is
  `atan2(g_x, g_y)`, the same quantity as the stamp's `roll_deg`. It must not subscribe to
  anything itself.
- **The maths, as `capture_pose` does it:**
  - level roll = `−(r − 90·round(r/90))`;
  - "pointing at the ground or the sky" below the roll floor. Reuse `GRAVITY_ROLL_FLOOR` from
    `CameraPose.kt` rather than a new 0.26. It needs the in-plane share of gravity; if the
    state carries only angles, that share is `cos(pitch)`, which is the test `_from_attitude`
    uses;
  - level = |pitch| ≤ 20 and |level roll| ≤ 10.

  Name the limits as constants that cite `MAX_PITCH_DEG` and `MAX_ROLL_DEG` in
  `backend/panoramax/app/eligibility.py`.
- **Pin it with cases from `test_capture_pose.py`**, the real-series rows above all, in a
  common test. The web handoff may create a shared fixture file of these cases. If it has
  landed by the time you merge, read the cases from it instead of copying them.
- **The horizon on screen:** a positive `roll_deg` puts the true horizon turned clockwise on a
  screen upright to the phone (from the 2026-11-15 series, sign and size). If the capture UI
  rotates with the device, take the screen angle off first; `ScreenAngle.kt` is the port of
  the original's `screenOrientationAngle`. Check it on the phone in portrait and in both
  landscapes before calling it right. The emulator cannot settle sensor questions.
- **Placement:** in or beside the `attitude-readout` pill in `CameraOverlayUi.kt`, as a new
  composable with its own test tags, in the kebab-case style already there, for example
  `level-indicator` and `level-indicator-state`. Hide it when `bearingMode == BearingMode.Car`.
  When `uploadSettings.shareToPanoramax` is on and there is no attitude, show the
  "not measured, won't be published" note.
- **Smoothing** is for display only, and the stamp is untouched by it. The state already
  arrives smoothed, so start without extra filtering and add it only if the phone shows
  flicker.

## Tests and checks

- `./gradlew :shared:jvmTest :shared:testAndroidHostTest`, with `JAVA_HOME` as in
  `frontend2/CLAUDE.md`.
- **Unit tests:**
  - the conversion function;
  - `attitudeProvenanceJson` still positive down;
  - the bearings-table sink still positive down;
  - the Room migration, as a migration test with a positive and a null row;
  - the dump header;
  - the indicator's level/tilted/flat decisions on the shared cases;
  - `pitchNeighbour` with a local photo that now carries a pitch.
- **On the phone:**
  - a few shots looking clearly up and clearly down, checking that the readout and the
    uploaded photo's server `pitch` agree in sign;
  - the indicator in portrait and both landscapes, rolled both ways;
  - one "Write EXIF" capture, checking that its server row has a pitch and roll in landscape.
- **Keep it compiling:** `shared-kt` changes must still compile into the Tauri build. There
  will likely be no release from it, but don't break it.

## When it is done

- Update the frontend2 follow-up in `photo-pose-and-level-gates.md`, and only that section
  (the web session edits its own).
- Update the "Pitch has three homes" table in `docs/recon-capture-metadata.md`, and
  `docs/frontend2-status.md`.
- Screenshots of the indicator go to the user, who decides whether it shows always or only
  while the Panoramax toggle is on.

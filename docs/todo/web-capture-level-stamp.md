# Web capture: gravity stamp and level indicator

Handoff, written 2026-11-17. The user agreed this plan that day. It is the web half of the
follow-ups in [photo-pose-and-level-gates.md](photo-pose-and-level-gates.md). Read that doc's
*Conventions* section and its level-indicator rules before starting. The frontend2 half is
[frontend2-pitch-sign-and-level.md](frontend2-pitch-sign-and-level.md), run separately.

**Status, 2026-11-17: built, not yet checked on a real phone.** What was built, how it differs
from this plan, and what is left are in the web follow-up of
[photo-pose-and-level-gates.md](photo-pose-and-level-gates.md#follow-ups-not-in-this-change).
Two corrections to the plan below. `types/photoTypes.ts` holds no capture type in use: the
stored photo is `StoredPhoto` in `browser/photoStorage.ts`. And `uploadToWorker` kept a
third key list, which now passes the builder's output through.

## The goal

- **Web captures carry a gravity measurement**, so the server can derive `photos.pitch` and
  `photos.roll` and the photo can pass the Panoramax level gates. Today every web capture is
  unmeasured, so none can be published to Panoramax.
- **The camera view gets a level indicator** that says whether the shot will pass: |pitch| ≤
  20° and |roll| ≤ 10°.
- **Both uploaders build their metadata in one place.** That fixes a live bug on the way.

## Already decided, don't re-open

- **No backend change for the stamp.** `BrowserMetadata.inertial` and `PROVENANCE_KEYS`
  already carry an `inertial` object. Canvas JPEGs have no UserComment of their own, so the
  worker synthesizes one, and `capture_pose`'s gravity branch reads `inertial.gravity` first.
  Verify the extra keys survive with a test, but don't add server code for them.
- **The stamp is only `inertial`.** Don't send `attitude`, `capture_timing.metadata_version`
  or a top-level `pitch`: those carry frontend2's versioned meanings.
- **The pose gets its own one-state home**, written only while the camera is shown. It is
  never part of `bearingState`, and the indicator reads it rather than a sensor.
- **The indicator follows the shared rules** in the plan doc ("Capture guidance for
  Panoramax: the level indicator"). That means the gate limits, `capture_pose`'s maths and
  the one state's reading; it never refuses the shutter, it is hidden in car mode, and it
  shows always by default.
- **The Tauri app will likely not have another release** (the user, 2026-11-17). Build for the
  web only, but don't break the `TAURI` branches in shared components.

## Read first

- `frontend/CLAUDE.md` and `docs/one-state.md`.
- `docs/tauri-capture-ui-contract.md`, for what the capture screen's controls already do.
- `common/capture_pose.py` and its tests (`backend/api/app/tests/unit/test_capture_pose.py`):
  the gravity formulas, `level_roll`, `ROLL_FLOOR`, and what makes a vector junk.

## Sources, by browser

- **Chromium on Android** (Chrome, Samsung Internet): `GravitySensor({referenceFrame:
  'device'})`. Chromium maps it to Android's `TYPE_GRAVITY`, the sensor frontend2 stamps, so
  the vector goes into the stamp as-is. `gravity_source: 'gravity-sensor'`.
- **iOS Safari and Firefox:** `deviceorientation` beta/gamma, converted on every event to the
  up vector `9.80665·[−cosβ·sinγ, sinβ, cosβ·cosγ]`. That is the spec's rotation matrix,
  the same row WebKit derives beta/gamma from. `gravity_source: 'deviceorientation'`. The
  angles jump near upright portrait and the vector doesn't, so average vectors, never angles.
  A conversion checked against `capture_pose`'s conventions gives:
  - upright portrait → [0, g, 0];
  - flat → [0, 0, g];
  - a counterclockwise roll → a positive `roll_deg`.
- **Never `accelerationIncludingGravity`.** It is the raw accelerometer, and reportedly
  sign-inverted on iOS. An inverted vector flips pitch's sign but leaves the reduced roll
  unchanged, and the gates compare absolute values, so such a photo would pass with its
  stored pitch silently wrong.
- **Desktop** has neither, and stays unmeasured.
- **Permission:** iOS needs `DeviceOrientationEvent.requestPermission()` inside a user
  gesture. Call it, and the Generic Sensor permission check where it exists, in the click
  that opens the camera. Chrome plans to make sensor permission Ask-by-default, so do this
  everywhere, not only on iOS. A refusal leaves photos unmeasured and must not break capture.

## Sampling and the stamp

- **A ring buffer of about 1 s of samples**, filled only while the camera is shown.
- **At the shutter:** read at the very top of `handleCapture` in `CameraCapture.svelte`, before
  any await. Take the samples from the last 300 ms and average their unit vectors, scaled
  back to 9.80665.
- **No fresh sample means no `inertial` object at all.** Don't send a stale or default vector.
- **Front camera:** leave out `inertial` when the active camera faces the user (`'user'`
  facing mode), because `capture_pose` assumes the lens looks along −z.
- **The object:**

  ```json
  {"gravity": [gx, gy, gz], "age_ms": 40, "gravity_source": "gravity-sensor",
   "sample_count": 18, "window_ms": 300, "gravity_spread_deg": 0.8}
  ```

  `gravity_spread_deg` is the largest angle between a sample and the mean. It is diagnostic
  only, and the server doesn't gate on it.
- **Device frame vs the page:** `GravitySensor` in the device frame and the converted
  deviceorientation vector are both in DEVICE coordinates, which is what the stamp needs
  whatever the page's rotation. Don't rotate the stamp's vector by `screen.orientation`.
  Only the indicator's drawing uses the screen angle (`screenOrientationAngle` in
  `deviceOrientationExif.ts`).

## Where the code goes

- **A new module beside `deviceOrientationExif.ts`**, for example `capturePose.ts`. It holds:
  - the source selection and the ring buffer;
  - the conversion, `stampInertial()`;
  - a readable store for the indicator.

  Keep the maths (conversion, averaging, pitch, `level_roll`, the floor) in pure functions in
  a separate module with no DOM, so vitest can reach them.
- **`CameraCapture.svelte`:** start the pose source in `onMount`'s non-`TAURI` branch and stop
  it on teardown and when the camera hides. That branch today starts an
  `AbsoluteOrientationSensor` at 100 Hz whose readings are only logged. Replace it, keeping
  the old code commented out (never delete commented-out code). The `TAURI` branch, with the
  plugin's device-orientation events, stays as it is.
- **Plumbing.** The metadata passes through explicit key lists at each hop, so `inertial` must
  be added at each:
  - `CameraCapture.svelte` builds the capture's location and metadata;
  - `captureQueue.ts` carries it through the queue item;
  - `types/photoTypes.ts` stores it with the photo;
  - `browser/photoSync.ts` (`foregroundUploader`) or `sw/serviceWorkerSecureUpload.ts`
    (`swSecureUploader`) builds the upload metadata;
  - `uploadProtocol.ts` sends it.

  Trace it once yourself; this list is from research, not a test.
- **One builder for both uploaders.** They have already drifted: `swSecureUploader` drops
  `alt_location`, which `foregroundUploader` sends, so photos uploaded through Background
  Sync lose it (confirmed 2026-11-16). Move the metadata construction into one function that
  both call, which fixes that and stops `inertial` drifting the same way. Pin it with a vitest
  that builds the metadata for one stored photo through both paths and compares them.

## The level indicator

- **What it reads:** the pose module's store. It never reads a sensor of its own.
- **The maths, a TS port of `capture_pose`'s gravity branch:**
  - pitch = `−asin(g_z/|g|)`, positive up;
  - r = `atan2(g_x, g_y)`, and level roll = `−(r − 90·round(r/90))`;
  - "pointing at the ground or the sky" when `hypot(g_x, g_y)/|g| < 0.26` (`ROLL_FLOOR`);
  - level = |pitch| ≤ 20 and |level roll| ≤ 10.
- **The limits:** export `MAX_PITCH_DEG` and `MAX_ROLL_DEG` from `panoramaxStatus.ts`, citing
  `eligibility.py`. Make `PANORAMAX_GATE_TEXT`'s "over 20°" and "over 10°" use them.
- **The display** reads a short display-only average of the ring at the render rate. The
  stamp's 300 ms window is separate.
- **On screen:** draw the horizon from the vector. In device coordinates, `(g_x, g_y)` points
  to the sky in the screen plane, and the horizon is perpendicular to it. On a page upright to
  the phone, a positive `roll_deg` puts the horizon turned clockwise (the 2026-11-15 series).
  When the page has rotated, take `screenOrientationAngle` off first.
- **Test ids,** in the style of the capture screen's (`bearing-tracking-hint`,
  `switch-to-car-mode-btn`): for example `capture-level-indicator` and a
  `data-level-state="level|tilted|flat|unmeasured"` attribute for tests to read.
- **Visibility:**
  - hidden in car mode;
  - absent when nothing is measured;
  - when `capturePanoramaxShare` is on and nothing is measured, a short note that such photos
    are not published to Panoramax. On desktop that note is the only part that shows.

  Changed while building (the user, 2026-11-17): when nothing is measured the indicator
  always says "Tilt not measured.", and adds the Panoramax line only while the toggle is on.

## A shared fixture for the maths

**Recommended:** one JSON file of `capture_pose` cases next to it, such as
`backend/common/capture_pose_cases.json`. Each case is a gravity vector with its pitch, roll
and level verdict, plus the two limits. Take the cases from the real 2026-11-15 series rows
and the boundary cases already in `test_capture_pose.py`.

Three suites read it, so the maths and the limits cannot drift apart:

- `test_capture_pose.py`, which also asserts that the limits equal `eligibility.py`'s
  constants;
- the vitest for the TS port, which also checks `panoramaxStatus.ts`'s constants;
- later, frontend2's common tests. Its handoff copies the cases until this file has landed.

## Tests and checks

- **vitest:**
  - the beta/gamma conversion: upright, flat, rolled both ways, both landscapes, upside down,
    and near-upright portrait where the angles jump;
  - averaging across that jump;
  - the stale and empty window;
  - the front-camera omission;
  - the indicator's decisions from the shared fixture;
  - the one-builder comparison above.
- **Backend unit:** add a "web stamp" block to `test_capture_pose.py`: `inertial` only, no
  `attitude`, no `capture_timing`. Include the extra keys, checking they don't disturb the
  result.
- **Playwright, Chromium:**
  - CDP `Emulation.setSensorOverrideReadings` for gravity, and
    `DeviceOrientation.setDeviceOrientationOverride` for the fallback;
  - the indicator's state changes;
  - an upload whose server row gets the expected pitch and roll.

  Playwright targets the docker `frontend` container, so rebuild it with the dev overlay
  before testing.
- **A real-device series**, like the frontend2 one: on iOS Safari, Firefox Android and Chrome
  Android, portrait rolled both ways, both landscapes, pitched up and down. Then read the
  server rows back through the timeline endpoint.
  - **The iOS inversion:** a debug readout of `accelerationIncludingGravity.y` held upright
    (about +9.8 on Android, −9.8 if iOS is inverted) settles it, and confirms the conversion
    is the right choice.
  - **Image rotation:** look at whether a landscape web capture's image is rotated twice via
    `orientation_code`. It wouldn't change pitch or roll, but it would be a bug worth its own
    note.

## When it is done

- Update the web follow-up in `photo-pose-and-level-gates.md`, and only that section (the
  frontend2 session edits its own).
- Add a line to `docs/recon-capture-metadata.md` naming the web as a gravity source.
- Screenshots of the indicator go to the user, who decides whether it shows always or only
  while the Panoramax toggle is on.

# Photo pitch and roll: corrected columns, and the Panoramax level gates

Planned 2026-11-15, with the numbers measured on that day's prod dump. **Implemented the
same day**, and rehearsed on the dev copy of that dump (see *Rollout*). The prod rollout and the
follow-ups remain. Supersedes
[pitch-backfill-from-usercomment.md](pitch-backfill-from-usercomment.md): the roll decision
it left open is made here, and the backfill it proposed reads a UserComment shape this plan
no longer trusts.

## Why

Panoramax should only get photos we know were held reasonably level. A photo that looks
40° down at the pavement, or whose horizon leans, is a poor street-level image whoever took
it, and nothing at publication time can fix it. So the federation is conservative: it takes a
photo only once the phone has measured it level, and no measurement means no publication.

Two defects come along with the fix:

- **`photos.pitch` holds the wrong sign.** Migration 032 documents it as positive up, and
  both viewers assume that (`photoUpDownLogic` in `frontend/src/lib/mapState.ts`,
  `pitchNeighbour` in frontend2's `ViewerRules.kt`). But frontend2 writes its device pitch,
  which is positive LOOKING DOWN (`DeviceAttitude.pitch`). On the prod dump, for photos
  tilted more than 10°, the column has the same sign as gravity's positive-down pitch on
  12,164 photos and the opposite sign on 285. So up/down swiping in the viewer is reversed
  for every photo that has a pitch.
- **There is no roll column.** Roll arrives on every frontend2 capture since 2026-09-26, and
  nothing can query it.

## Decisions

Agreed with the user, 2026-11-14/15:

- **Three new Panoramax gates:** `bearing`, `pitch` and `roll`.
- **The limits:** |pitch| ≤ 20° and |roll| ≤ 10°.
- **A photo without a measurement fails `pitch` and `roll`.** This is the opposite of
  `blurry` and `location_accuracy`, where NULL passes.
- **Car mode is exempt from `pitch` and `roll`.** Holding a level phone in a moving car is a
  losing fight against inertia (see *Gravity in a moving car*). The car-mode photos in the
  database are mostly level anyway: 1,208 of the 1,267 that carry a measurement pass both
  limits.
- **Car mode means `bearing_source = 'gps-kalman'`.** Both apps have written that since
  2026-03-24. Before then, car mode stamped `'map'`, the same default a bearing set by turning
  the map gets, so those photos cannot be told apart. That doesn't matter: exactly one
  shared photo is from that period.
- **External-camera work and panoramas need no exemption.** None of them are Panoramax
  candidates.
- **`pitch` is overwritten with the corrected value, and `roll` is added beside it.** Both
  are signed, in the GPano conventions below.
- **They are plain columns, not generated ones.** Other sources will write better values
  later, enrich's pose recovery for one, and a generated column would forbid that.
- **Old attitude rows are trusted in upright portrait only.** These are rows from before
  `metadata_version` existed. The user trusts the phone's recorded orientation
  (`device_rotation_deg`) for them. Landscape and upside-down rows are blocked: their angles
  are known to be wrong.
- **The app-sent pitch of unstamped portrait photos is kept, sign-flipped** (decided
  2026-11-16). Dropping it would have lost a usable pitch on 21,606 photos for nothing:
  - Panoramax is unaffected either way, since those photos recorded no roll and fail `roll`;
  - the web viewer treats a missing pitch as level (`photo.pitch ?? 0` in
    `photoUpDownLogic`), so dropped values would all have sorted as level;
  - the value is rough but usable in portrait (see *Where the values come from*);
  - the recon bench gets a rough level prior where it would otherwise have none.

  Landscape values are dropped: that era's landscape fault puts them up to 97° off.

## Conventions

Both columns follow GPano (Google's photo-sphere XMP, which Panoramax reads as
`Xmp.GPano.PosePitchDegrees` / `PoseRollDegrees`), so a photo's bearing, pitch and roll are
one standard triple:

- **`pitch`:** degrees above the horizon at the centre of the image, positive up, in
  [−90, 90]. This is what migration 032 always said.
- **`roll`:** the roll of the PUBLISHED image, 0 when level. As roll increases, the horizon
  rotates counterclockwise in the image. It is measured from the nearest quarter turn, so it
  lies in (−45, 45], and a level landscape shot reads 0, not 90. Which quarter turn the photo
  was taken in is the image's own orientation, and the image already shows it.

How they relate to the phone's stamp, where `r` is the stamp's `roll_deg`:

- **`pitch`** is `−attitude.pitch_deg`. The stamp's pitch is positive down.
- **`roll`** is `−(r − 90·round(r / 90))`. The stamp's roll is 0 with the screen's top at the
  sky and positive when the phone is turned counterclockwise as its user sees it. That is the
  opposite of GPano's.

That roll sign was worked out from the gravity formula, and a deliberate series confirms it,
sign and size. The series is the owner's timeline from shared link 35 (anchor `95f1b993…`),
taken 2026-11-15 14:47–15:41: 29 shots in left/right pairs, rolled 12–31° with pitch under
12°. There are 13 portrait shots, 6 landscape at `device_rotation_deg` 90 and 10 at 270.

- **Sign:** on all 29, the scene leans the way the GPano value says. When it is negative, the
  horizon falls to the right (the scene is turned clockwise). When it is positive, the
  horizon rises to the right.
- **Size:** each image was rotated back by its GPano value, and every one came out level
  by eye. The poles, gabion corners and railing posts are vertical, and the horizons are
  flat. That holds for both landscape directions, so the quarter-turn reduction is right
  too.
- **Pitch sign, as a by-product:** the stamp's `pitch_deg` is +4 to +11 on nearly all of
  them. Where the true horizon is visible, it sits above the image centre, so the camera
  looks down, which confirms that the stamp's pitch is positive down.
- **The fused matrix's roll is not usable:** `matrix_roll_deg` is more than 5° from gravity
  on 23 of the 29, with the wrong sign on 18. Gravity reproduces the stamp's `roll_deg` and
  `pitch_deg` (within 0.06°) on every one.

Two earlier, milder shots (`83211a7b…` rolled left, +6.4; `04ded9c8…` rolled right, −10.7)
agree as well.

## Where the values come from

A pure function, `capture_pose(exif_data) -> (pitch, roll)` in a new `common/capture_pose.py`.
It follows the precedent of `is_blurry` in `common/image_quality.py`. It reads the capture
app's UserComment, parsed as defensively as `_user_comment` in `photo_routes.py`, and takes
the first of these that applies:

- **`inertial.gravity`, when it is three finite numbers of non-zero length.** The formulas
  are `pitch_down = asin(g_z / |g|)` and `r = atan2(g_x, g_y)`. They are what the app itself
  uses since `metadata_version` 3, and gravity never went through the broken remap, so it is
  good in every period.
  - Measured on the dump: on version-3 rows the formulas reproduce the stamped attitude
    exactly (median pitch difference 0.00°, 99th percentile 1.15°, roll disagreeing on 2 of
    21,048 rows). On version-1 rows roll disagrees on 544 of 1,265 (the 180° branch fault).
    On rows from before versioning, the pitch difference reaches 93° at the 99th percentile
    (the landscape fault). That is why gravity comes first.
  - `|g|` is 9.81 on every row, as `TYPE_GRAVITY` reports it.
- **`attitude.pitch_deg` / `roll_deg`, when `capture_timing.metadata_version` is 1 or more.**
- **The same attitude angles on rows without `metadata_version`, only when
  `device_rotation_deg = 0`.** Old portrait rows were right; landscape rows were not. On
  shared photos that is 2,843 rows in portrait (698 of them car mode) against 67 at 270°.
- **Last, pitch only: the app-sent `pitch` upload field, negated** (`exif_data->'gps'->'pitch'`,
  see below). Only when the stamp has neither an `attitude` nor an `inertial` object, and the
  image is portrait-shaped (taller than wide). `capture_pose` takes the stored width and
  height for this. Roll stays NULL.
  - **Its error**, on photos that carry both it and gravity: portrait values are off by 3.3° at
    the median, 10.1° at the 90th percentile and 20.3° at the 99th (10% are more than 10° off).
    Landscape values are off by 28° at the 90th percentile and 97° at the 99th, which is why
    landscape is not read.
  - **Image shape tells landscape apart**, on 1,427 of 1,428 landscape photos. An upside-down
    portrait looks like a portrait, but there were 10 among 25,374.
  - **Who it reaches:** in the 2026-11 data, only frontend2 photos captured 2026-08-27 to
    2026-09-24 (`android-compass-true`, the label whose sign was verified). That is 21,606 in
    portrait and 2,538 in landscape. Every frontend2 capture since then stamps both objects,
    and no other client sends the field.
  - **A stamped photo whose stamp yields nothing** (an old landscape row, say) does not fall
    back: its upload pitch came through the same broken path.
- **Otherwise NULL.** NULL covers:
  - the Tauri app, which computes pitch and roll for its compass display but stamps neither
    on a photo;
  - the web app;
  - frontend2's landscape photos from before its attitude stamp (2026-09-22);
  - external cameras;
  - the 4,807 UserComments with a top-level `{"pitch", "roll"}`. They come from a client
    outside this tree, and values like pitch −84 / roll −175 are the old landscape fault.

Within about 15° of flat, gravity's roll is meaningless (`GRAVITY_ROLL_FLOOR` in
`CameraPose.kt`): which way gravity points in the image plane says where the phone's top was
turned, not how the horizon leans. So `capture_pose` stores NULL roll there (`ROLL_FLOOR`) and
keeps the pitch. Such a photo fails `pitch` anyway, so no gate outcome depends on it. On the
dump that is 268 photos.

The app-sent `pitch` upload field (`exif_data->'gps'->'pitch'`, from
`PhotoUploadLogic.buildUploadMetadata`) is read only as that last resort. Nothing elects pitch
(see "Pitch has three homes" in `docs/recon-capture-metadata.md`). It is the tilt that rode
along with the bearing (`BearingState.pitch`): the same smoothed sensor reading as
`attitude.pitch_deg`, taken when the bearing was last set, NULL whenever the bearing source
measures no tilt (car mode, a hand-set arrow), and positive down. See *Follow-ups* for when
it should win over the measurement.

## Schema and code

- **Migration `045_photo_pose`:**
  - adds `roll double precision`;
  - adds `bearing_source text`, generated and stored, from a defensive IMMUTABLE function
    over `exif_data`. This is the `photo_location_accuracy_m` pattern from 039: a non-JSON
    comment, a NUL-padded Canon comment or broken JSON all give NULL, and so does a
    non-string value. It is capped at 128 characters, not the 64 the API's provenance
    projection uses: the longest real label is 73 (the Tauri compass's). Being stored, it
    rewrites the photos table once, as 039 did;
  - updates the `pitch` column's comment to the convention above.

  It doesn't touch values; the backfill does.
- **`common/models.py`:** `roll`, and `bearing_source` as a `Computed` column.
- **Write path:** in the processed-photo handler in `photo_routes.py`, where
  `photo.exif_data = processed_data.exif_data` is assigned, set `photo.pitch` and
  `photo.roll` from `capture_pose`. This replaces the `processed_data.pitch` assignment.
  The worker keeps passing the field, unused.
- **`backend/scripts/pose_backfill.py`:** recomputes `pitch` and `roll` for every live row,
  with `--dry-run` printing the counts first. It is idempotent: the values are a function of
  `exif_data`, so re-running after a rule change is the same command. Running it is how
  every existing row gets the corrected values.
- **Gates in `GATES`** (`backend/panoramax/app/eligibility.py`), after `blurry`, with
  constants `MAX_PITCH_DEG = 20` and `MAX_ROLL_DEG = 10`:
  - `bearing`: `p.compass_angle IS NOT NULL AND p.compass_angle NOT IN ('NaN', 'Infinity',
    '-Infinity')`. No shared photo lacks a bearing today; this guards photos to come.
  - `pitch`: `p.bearing_source = 'gps-kalman' OR abs(p.pitch) <= 20`.
  - `roll`: `p.bearing_source = 'gps-kalman' OR abs(p.roll) <= 10`.

  A NULL fails, as every gate's NULL does in `GATE_RESULTS_SQL`. The module docstring gets a
  paragraph. Neither column bumps the sequence's `updated_at`, so changes reach the catalog
  on the sequencer's cadence, like the blur verdict and the location radius.
- **`PANORAMAX_GATE_TEXT`** (`frontend/src/lib/panoramaxStatus.ts`):
  - `bearing`: "it has no bearing"
  - `pitch`: "its up/down tilt was not measured or is over 20°"
  - `roll`: "its horizon tilt was not measured or is over 10°"
- **Docs:**
  - the eligibility list in `docs/panoramax-federation.md`;
  - a section in `docs/recon-capture-metadata.md` on how the server columns map from the
    stamp;
  - a superseded note at the top of `pitch-backfill-from-usercomment.md`.

## Tests

- **`capture_pose` unit tests (api unit suite):**
  - each source, and the priority between them (gravity over attitude);
  - a version-1 row whose roll is 180° off gravity;
  - an old row in portrait, landscape and upside down;
  - the app-sent pitch: read negated for an unstamped portrait photo; not read for landscape,
    square or missing dimensions, beside any stamp, or when it is junk;
  - the 2026-09-28 rows whose gravity is null;
  - junk: a non-array, strings, NaN, a zero vector, a Canon comment, NUL padding;
  - the quarter-turn boundaries;
  - the signs, pinned on real-shaped rows: a lens above the horizon gives positive pitch.
- **`test_federation_eligibility`:**
  - the fixture photo gains `compass_angle`, `pitch`, `roll` and `bearing_source`;
  - rows at 20 / 20.1 and 10 / 10.1, on both sides of level;
  - NULL fails;
  - car mode with NULLs passes;
  - a NULL or NaN bearing fails.
- **A `bearing_source` function test** in the shape of `test_location_accuracy_column`.
- **An integration test** that uploads a photo with an `attitude` + `inertial` stamp and reads
  `pitch` / `roll` back, plus unstamped portrait and landscape uploads.

## Measured on the prod dump, 2026-11-15

Of 120,443 live photos, 89,422 are shared to Panoramax. How the shared ones fare:

| | source of the angles | photos | pass `pitch` | pass `roll` | pass both |
|---|---|---|---|---|---|
| not car | gravity | 23,058 | 18,601 | 21,152 | 17,553 |
| not car | old attitude, portrait | 2,145 | 1,752 | 1,654 | 1,405 |
| not car | old attitude, landscape | 19 | 0 | 0 | 0 |
| not car | none | 41,153 | 0 | 0 | 0 |
| car | gravity | 1,267 | 1,252 | 1,222 | 1,208 |
| car | old attitude, portrait | 698 | 697 | 676 | 676 |
| car | old attitude, landscape | 48 | — | — | — |
| car | none | 21,034 | — | — | — |

Car mode is exempt; its pass counts are only there to show it is mostly level. For measured
non-car photos, pitch is −23.5 / −8.0 / +10.8 at the 10th / 50th / 90th percentile (positive
up), and |roll| is 3.5 at the median and 9.8 at the 90th percentile.

Current Panoramax members: 30,526.

- 10,957 are car mode and stay.
- 16,891 have no measurement and leave.
- 838 fail on angle.
- 1,840 pass.

Re-selection can fill some vacated cells with other eligible photos.

The `pitch` column after the backfill:

- 53,305 rows have a value today, and 52,650 will after it.
- 31,044 are measured from the stamp.
- 21,606 keep the app-sent pitch, sign-flipped. These are frontend2's portrait photos captured
  2026-08-27 to 2026-09-24, which carry nothing else. None of them recorded a roll (their
  UserComment has no `attitude` at all), so all of them fail the roll gate. The flip passes
  the pitch gate for many of them, but they still fail on roll, so Panoramax gets the same
  either way. The flip matters only to the column's other readers.
- 2,557 lose their value: the same era's 2,538 landscape photos, whose pitch is wrong, and
  19 old landscape rows, blocked by design.
- 2,097 gain one. These are car-mode photos, which never had a pitch.

## Rollout

- **The order:** migration, then `pose_backfill.py --dry-run`
  (compare it with the numbers above), then the real backfill, then a sequencer pass.
- **Rehearsed on the dev copy, 2026-11-15.** The dry-run printed 120,443 photos, 31,044
  pitches derived, 30,776 rolls, 24,163 lost, 2,097 gained and 28,947 changed (24,869 of
  them with the sign flipped), so 55,207 rows to write. The real run wrote them, and a second
  dry-run had nothing to write. Afterwards the new gates split today's 30,526 members exactly
  as above: 10,957 car mode, 16,891 unmeasured, 838 failing on angle and 1,840 passing, with
  none lacking a bearing. The dev copy's old pitch values were saved first (in the session's
  scratchpad, not the repo). The rebuilt sequencer's next pass then left 12,928 members:
  10,957 car mode and 1,971 measured and level, re-selection having filled 131 vacated cells.
  So 17,598 left.
- **Re-run with the portrait flip, 2026-11-16,** on top of the first run. It wrote 21,606 rows
  and a second dry-run had nothing to write. Every one of the 2,557 rows that lost a pitch is
  landscape-shaped, and every flipped row holds exactly the negated old value. The 12,928
  members all still pass. From the original data, a prod dry-run should print:
  - 52,650 pitches derived and 30,776 rolls;
  - 2,557 lost and 2,097 gained;
  - 50,553 changed, 45,933 of them with the sign flipped;
  - 55,207 rows to write.
- **What leaves Panoramax:** the serve-time filter drops failing members from `/items` at
  once, and the harvester then removes them from the catalog. That is about 17,700 of today's
  30,526 members.
- **The released Tauri app (1.32.0)** reads `pitch` from the photo stream for up/down. The
  field's shape doesn't change, and its values flip to the positive-up the app already
  assumes. So its navigation gets fixed, not broken.
- **frontend2's viewer** is fixed for server photos. Its own photos on the phone still carry
  positive-down pitch: see *Follow-ups*.

## Follow-ups (not in this change)

- **frontend2's sign.** Researched 2026-11-16, agreed 2026-11-17, together with the level
  indicator below. The work is handed off in
  [frontend2-pitch-sign-and-level.md](frontend2-pitch-sign-and-level.md), which also corrects
  the research: raw sensor pitch reaches `BearingState.pitch` by a second path, the compass
  callback in `MapSensorController.startBearing`, bypassing `toDeviceAttitude`.
  - `DeviceAttitude.pitch`, `BearingState.pitch` and `PhotoEntity.pitch` are positive down.
    Local photos do not navigate inverted: `DevicePhotoLoader` never passes a pitch to the
    viewer, so they count as level. An uploaded photo shows its server copy instead
    (`collapseTwins`).
  - **One conversion point**, in `toDeviceAttitude`, makes the app positive up internally.
    Two places convert back: `attitudeProvenanceJson`, so the stamp keeps its sign at
    `metadata_version` 3, and the bearings-table writer, so its rows don't mix signs.
    `EnhancedSensorService`, `CameraPose` and `OrientationSensorData` live in `shared-kt` and
    feed the Tauri app, so they must not flip.
  - **A Room migration flips the stored `PhotoEntity.pitch`.** The photo dump's `pitch`
    column is renamed in the same release, so no CSV mixes signs under one header. After
    that, `DevicePhotoLoader` can pass the pitch to the viewer.
  - **Stop sending the top-level upload `pitch`.** Every current capture carries `attitude`,
    so `capture_pose`'s last resort never reads it, and a positive-up value there would be
    negated wrongly.
  - **Keep the stamp positive down.** `capture_pose` does NOT branch on a version above 1:
    every version from 1 up negates `pitch_deg`, so a flipped stamp at version 4 would be
    read inverted unless the server learned v4 first. Gravity is read before attitude
    anyway.
  - **Roll** has no reader in the app with a horizon assumption; it stays as it is.
- **"Write EXIF" stamps lack `capture_timing` and `inertial`.** With that setting on, the
  worker keeps the file's own UserComment, and the one `PhotoExifWriter` writes carries
  `attitude` only. `capture_pose` then reads it as a pre-versioning row: portrait is fine,
  landscape and upside-down get no pitch or roll and fail the gates. No photo in the
  2026-11-15 data is affected (all 25,281 with `attitude` since 2026-10-10 carry both
  objects), and the setting is off by default. Fix: have `PhotoExifWriter` write the same
  objects the fast-write path sends. Part of the frontend2 handoff.
- **The web app.** Worth doing (the user, 2026-11-16). Researched the same day, agreed
  2026-11-17 together with the level indicator below, handed off in
  [web-capture-level-stamp.md](web-capture-level-stamp.md), and **built the same day**. No
  backend code changed: `BrowserMetadata.inertial` and `PROVENANCE_KEYS` already carried
  the object, and canvas JPEGs have no UserComment of their own, so the worker
  synthesizes one. Not yet checked on a real phone.
  - **Sources**, in `frontend/src/lib/capturePose.ts`: Chromium's
    `GravitySensor({referenceFrame: 'device'})`, which is `TYPE_GRAVITY`; elsewhere
    deviceorientation's beta/gamma, converted per event to the up vector
    `9.80665·[−cosβ·sinγ, sinβ, cosβ·cosγ]` and averaged as vectors. Never
    `accelerationIncludingGravity`. Desktop stays unmeasured. It replaces the
    `AbsoluteOrientationSensor` in `CameraCapture.svelte`, whose readings were only
    logged; that code is kept commented out.
  - **The stamp:** `inertial: {gravity, age_ms, gravity_source, sample_count, window_ms,
    gravity_spread_deg}`, the mean of the unit vectors from the 300 ms before the press,
    read at the top of `handleCapture`. There is no object when no sample is fresh or
    the camera faces the user. No `attitude`, `capture_timing` or top-level `pitch`.
  - **One state:** the ring buffer in `capturePose.ts`, filled only while the camera is
    shown. The shutter reads it through `stampInertial()`, and the indicator through
    the `capturePose` store. Neither touches a sensor.
  - **One builder:** `buildUploadMetadata` in `uploadProtocol.ts` is now the only key
    list. `uploadToWorker` passes it through, and both uploaders call it, which fixes the
    Background Sync uploader dropping `alt_location`. `uploadMetadata.test.ts` drives one
    photo through both and compares them.
  - **Permission:** `requestCapturePosePermission()` runs in `toggleCamera`, inside the
    click, before anything awaits.
  - **The indicator** (`CaptureLevelIndicator.svelte`) follows the rules below. It draws
    the horizon against reference marks at the nearest quarter turn, says the state in
    words, and carries `data-testid="capture-level-indicator"` and `data-level-state`.
    The limits are `MAX_PITCH_DEG` / `MAX_ROLL_DEG` in `panoramaxStatus.ts`. When nothing
    is measured it says "Tilt not measured.", with the Panoramax line only while the toggle
    is on (the user's change, see the rules below). It shows always: that default is still
    the user's to judge, from the screenshots.
  - **Shared fixture:** `backend/common/capture_pose_cases.json`. `test_capture_pose.py`
    pins its limits to `eligibility.py` and the TS port's test pins them to
    `panoramaxStatus.ts`; both run every case. frontend2's tests can read it once it is committed.
  - **Tests:** vitest (`capturePoseMath.test.ts`, `uploadMetadata.test.ts`), the web
    stamp in `test_capture_pose.py`, the worker's `BrowserMetadata` test, an upload in
    `test_capture_pose_upload.py`, and `capture-level-stamp.spec.ts` (Chromium, CDP
    sensor overrides, through to the server row's `pitch` and `roll`).
  - **Found while building:**
    - **Chromium rounds every motion-sensor axis to 0.1 m/s²**, a fingerprinting
      mitigation, which is up to about 0.6° per reading. Averaging a handheld phone's
      samples smooths some of it. It matters only within a degree of a limit.
    - **A constant reading produces no stream of events**, for GravitySensor and
      deviceorientation alike. With a CDP override set once and left alone, the reading
      lapses to unmeasured within the window, which is why the spec re-sends its
      overrides with a small jitter. A real handheld sensor always changes, but a phone
      held perfectly still (on a tripod, say) might go quiet for longer than 300 ms. Its
      photo would then be stamped unmeasured, the conservative direction. This was
      observed with overrides only, so check it on the device series before deciding
      whether the window should accept an unchanged last reading.
    - **The API's `inertial` projection serves `gravity` and `age_ms` only.**
      `gravity_source`, `sample_count`, `window_ms` and `gravity_spread_deg` are in the
      stored UserComment, which the owner's detail response includes in full, but not in
      the typed projection. No server change was made, as agreed.
  - **Left:** the real-device series on iOS Safari, Firefox Android and Chrome Android, then
    the always-or-toggle decision. Debug mode 4 (`CapturePoseDebug.svelte`) shows the pose's
    source, vector, pitch and roll beside the raw `accelerationIncludingGravity`, whose y held
    upright settles the iOS inversion. The series should also check whether a landscape web
    capture is rotated twice via `orientation_code`.
- **The Tauri app** has the same gap: it measures pitch and roll for its compass but stamps
  neither. Not planned: the Tauri app will likely not have another release (the user,
  2026-11-17). Its released build must still keep working against the prod API.
- **Bringing back the app-sent pitch.** Once an app lets the user override pitch (as
  `arrow_drag` does for bearing), the upload's `pitch` means "the user says so" and should win
  over the measurement.
  - It needs a source marker beside it, `pitch_source` in the stamp like `bearing_source`,
    so the server can tell an override from today's ride-along sensor value.
  - Decide then whether a claimed pitch satisfies the Panoramax gate, or only a measured one.
- **Capture guidance for Panoramax: the level indicator.** Agreed 2026-11-17 for frontend2 and
  the web app, built in each handoff. It is what makes the share of photos that fail on angle
  shrink in future. The rules both apps follow, so the two indicators and the server agree:
  - **It shows what the gates will decide.** "Level" means |pitch| ≤ `MAX_PITCH_DEG` and
    |roll| ≤ `MAX_ROLL_DEG`, the constants in `eligibility.py`. Each app mirrors them as named
    constants that cite `eligibility.py`, and a test pins each copy to the same values.
  - **Same maths as `capture_pose`.** Pitch is positive up. Roll is `level_roll`, measured from
    the nearest quarter turn, so a level landscape shot reads level. Within `ROLL_FLOOR` of
    flat, roll has no meaning: the indicator says the camera points at the ground or the sky,
    and doesn't draw a horizon.
  - **Same reading as the stamp.** The indicator reads the pose from the one state, the
    same reading the shutter stamps. It never opens a sensor of its own.
  - **On screen.** A positive stamp `roll_deg` (phone turned counterclockwise as its user sees it)
    puts the true horizon turned CLOCKWISE on a screen upright to the phone. The 2026-11-15
    series showed this for the image, which is what the back-camera preview shows. When the
    UI itself rotates, take the screen's rotation off first.
  - **It informs and never refuses.** The shutter stays live whatever the indicator shows
    (`docs/one-state.md`).
  - **Not colour alone.** The state is also said in words or a glyph, such as "level" or "tilted
    down 25°".
  - **Hidden in car mode**, which is exempt from the gates, and absent when nothing is
    measured. When the Panoramax toggle is on and nothing is measured, a short note says that
    such photos are not published.
    - **The web changed this, 2026-11-17 (the user):** when nothing is measured it always
      says "Tilt not measured.", and adds that such photos cannot be published to
      Panoramax only while the toggle is on. frontend2's handoff was written to the rule
      above and keeps it unless the user extends the change.
  - **Open, for the user to judge on screenshots:** whether the indicator shows always or
    only while the Panoramax toggle is on. Both handoffs default to always, because a level
    photo is better for every reader.
- **Better values from enrich.** `capture_pose` runs on every processed-photo write, so a
  reprocess would overwrite a value enrich wrote. Give the columns a provenance marker before
  anything else writes them.
- **Publishing pitch and roll to Panoramax.** With GPano conventions in the columns, the STAC
  items could carry them. Check what the item format expects first.
- **Gravity in a moving car.** Should car mode ever lose its exemption: the gravity sensor
  drifts toward the accelerometer over seconds, so a sustained 0.1 / 0.2 / 0.3 g corner or
  brake tilts "down" by about 6 / 11 / 17°. On a side-window mount, cornering shows as pitch
  error and braking as roll. It's measurable from what is recorded: GPS speed × change in
  heading gives the real sideways acceleration. A median per drive would beat judging each
  photo, since the mount is rigid.
- **The recon bench** reads `photos.pitch` into each run's frame manifest (per the superseded
  todo), and its code is not in this checkout. Check its sign assumption before the backfill
  runs.

# Test debt from the geo-tracking election rework

Handoff doc. The rework landed 2026-08-08 across `shared-kt`, both mobile apps
and the sibling `pics` pipeline; it is compiling and the existing suites are
green, but several of its load-bearing claims are asserted by nothing. This
lists what is missing, ranked by what would actually catch a regression, with
the existing pattern to copy for each.

Read `docs/frontend2-status.md` (the election entry + items 0d/0e) and
`docs/tauri-capture-ui-contract.md` §"Fix freshness" first. The short version:

- `bearings`/`locations` are keyed on `(timestamp, sourceId)`, not timestamp
  alone, so concurrent streams stop overwriting each other.
- `source` is a small elect-able vocabulary (`android` | `gps-kalman` |
  `manual`); fine provenance moved to a new `detail` column.
- Every row records `electedSourceId` — which source was PRIMARY when it was
  written — so a background stream can be re-elected after the fact.
- An election must be a **user act**. No silent hand-over; that would make the
  recorded election a lie, and re-judging the choice later is the point of
  recording it.

## Already covered — don't redo

| Claim | Where |
|---|---|
| Two ways in, one election; follow-me withdraws the claim but not the no-fix hatch | `frontend2/shared/src/commonTest/.../map/MapStateTest.kt` (`MapSessionTest`) |
| Shutter gate opens on a fix OR an elected map position | `frontend2/shared/src/commonTest/.../capture/ShutterGateTest.kt` |
| An accepted claim opens the gate and suppresses the duplicate lift offer | `frontend2/androidApp/src/androidTest/.../CaptureGatingBehaviourTest.kt` |
| Tauri: the election flips end-to-end into the exported CSV (`android` rows, `elected` moving between `android`/`manual`) | `frontend/tests-appium/specs/background-location-tracking.test.ts` |
| pics: two-step lookup, staleness unbounded, no cross-stream substitution, old dumps fall back source-blind | `pics/src/tests/test_gps_log_election.py` |

## Missing, highest value first

### 1. The composite key actually keeps both rows

The core of the whole change, asserted nowhere. Two sources writing the *same
millisecond* must produce two rows; before, one silently replaced the other.

Instrumented (needs Room): `frontend2/shared/src/androidDeviceTest/kotlin/cz/hillview/`
— see `PhotoStorageTest.kt` for the shape. Insert two `BearingEntity` rows with
one timestamp and different `sourceId`, assert both come back. Then insert the
same `(timestamp, sourceId)` twice and assert REPLACE still collapses that —
the narrowing is deliberate, not an accident.

### 2. Per-source rate limiting, and the starvation bug that was fixed

`GeoTrackingManager` gated all writes on one 10 ms clock that advanced **even
on rejection**, so a stream arriving faster than the interval starved every
writer indefinitely, and a 1 Hz `gps-kalman` bearing could lose its slot to the
~10 Hz sensor stream. Now per-`sourceId`, and only an accepted sample moves
that source's clock.

Awkward: `rateLimitStorage` is private. Either widen it to `internal` and unit
test it directly (cheapest, and the logic is the whole point), or drive it via
the instrumented layer — hammer source A while source B writes once, assert B
landed.

### 3. Claim → pan → shoot (item 0e)

Regression fixed 2026-08-08, currently unguarded. `capture.manualLocation` was
read once at the electing moment, so claiming at A, panning to B and shooting
stamped **A** while the tracking table (which does follow pans) recorded **B**
— photo and log disagreeing about where the user said they were.

Behaviour layer: `frontend2/androidApp/src/androidTest/.../CaptureGatingBehaviourTest.kt`
has the pattern — `GlobalContext.get().get<MapSession>().claimManualPosition()`,
then `compose.openCaptureAndAwaitCamera()`. Claim, move the map holder, capture,
and assert the stamped position is the NEW centre. `MapGestureTest.kt` shows how
to move the map.

Cheap partial alternative: assert `capture.manualLocation` tracks
`mapState.spatial` without shooting at all. Weaker, but it pins the wiring that
actually broke.

### 4. frontend2's election reaches the tables

The Tauri side has this (appium, above); frontend2 has nothing equivalent, and
its publisher is a different implementation — `MapScreen.android.kt`, keyed on
the map centre so every pan writes a fresh `manual` row.

Behaviour layer: claim manual, pan, trigger the export, assert the locations CSV
has a `manual` row at the new centre carrying `elected=manual`, and that fixes
recorded meanwhile are `android` rows carrying `elected=manual` too. The appium
spec's `csvColumn()` helper is the header-driven way to read a column — don't
index by position, the dumps have gained columns twice now.

### 5. `toTableSource` / `kotlinOwnsSource`

Pure functions in `frontend/src/lib/mapState.ts`, no test. `bun run test:unit`
(vitest) is already set up — see `src/lib/geo.test.ts`. Worth pinning:

- `arrow_drag` / `url` / `featured` / `photo_navigation` / `map` → `manual`,
  original kept as `detail`.
- `gps-kalman` keeps its identity (it is separately elect-able — car mode).
- Anything containing `-compass-` → `android`. This is the web
  DeviceOrientation fallback, which DOES reach the tables when the native
  sensor won't start; labelling it `manual` would corrupt the election. The
  test should say so, because the string test mirrors how
  `currentCompassHeading` builds those names in `compass.svelte.ts` and the
  two must move together.
- `kotlinOwnsSource` covers `android*` AND `gps-kalman` — the second was a
  duplicate-row bug (Kotlin writes that row at the fix's `location.time`, the
  echo re-wrote it at `Date.now()`).

### 6. The v13→v14 migration

Runs only on a device carrying a v13 database, and is asserted by nothing. Room
validates the DDL against the entity schema at *runtime*, so a mismatch is a
crash on first open after upgrade, not a build failure.

Blocked on a decision: `PhotoDatabase` has `exportSchema = false`, and Room's
`MigrationTestHelper` needs the exported JSON. Turning it on (and committing the
schema files) is the only way to test migrations properly, and would have
verified this one mechanically instead of by the eyeball diff that was actually
used — the generated `PhotoDatabase_Impl.kt` was read and compared by hand
against the migration's `CREATE TABLE`s.

### 7. `overridePosition` for the no-fix hatch (item 0d)

Now applies to the hatch as well as the pill, since both set the same flag.
Consistent by construction, unverified on a device.

## Notes for whoever picks this up

- Don't assert on source *names* by substring. The vocabulary is deliberately
  small and exact now; substring matching is what
  `is_sensor_bearing_source` (Rust) still does and what item 0d is about.
- The dumps have gained columns twice. Read CSVs by header name.
- `pics/src/tests/` are self-contained `uv` scripts and each needs a committed
  `.lock` — `uv lock --script <file>` before the first run. The suite needs
  `HV_OFFDISK_ROOT` set (`HV_OFFDISK_ROOT=` is a valid "keep it local" value);
  `test_select_task.py` fails at HEAD for unrelated reasons.
- frontend2 device/behaviour tests need the emulator; per project memory it
  lives on another machine, reachable with `adb -P 5038`.

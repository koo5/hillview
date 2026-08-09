# Test debt from the geo-tracking election rework

Handoff doc. The rework landed 2026-08-08 across `shared-kt`, both mobile apps
and the sibling `pics` pipeline; it is compiling and the existing suites are
green, but several of its load-bearing claims are asserted by nothing. This
lists what is missing, ranked by what would actually catch a regression, with
the existing pattern to copy for each.

**Status 2026-08-08 (evening):** items 1, 2, 3, 4, 5 and 7 are done — see
"Landed" below. Item 4 failed on its first run and found a real bug (two
`GeoTrackingManager` instances, so the election never reached the rows the
capture pane wrote); that is fixed. Only item 6 remains, and it is a decision
before it is a test — see the note under it.

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

## Landed 2026-08-08

| Item | Where | Notes |
|---|---|---|
| 1. Composite key keeps both rows; REPLACE still collapses within a source; the `electedSourceId` filter in both DAO lookups; age-truncation across sources | `frontend2/shared/src/androidDeviceTest/.../plugin/GeoTrackingTablesTest.kt` | in-memory Room, so the app's own rows are untouched |
| 2. Per-source rate limiting, accept-only clock, the starvation regression, the atomic claim | `frontend2/shared/src/androidHostTest/.../plugin/SourceRateGateTest.kt` | the gate moved out of `GeoTrackingManager` into `SourceRateGate` (shared-kt) with an injectable clock — no sleeping, and the rules are stated where they are enforced |
| 3. Claim → pan → shoot stamps the NEW centre (item 0e) | `frontend2/androidApp/src/androidTest/.../GeoElectionBehaviourTest.kt` | |
| 4. frontend2's election reaches the CSVs: `manual` row at the new centre (`detail=map`, `elected=manual`), fixes meanwhile as `android` rows carrying `elected=manual`, source names inside the exact vocabulary | same file | **found the bug below** |
| 5. `toTableSource` / `kotlinOwnsSource` | `frontend/src/lib/mapState.test.ts` | 8 tests; `kotlinOwnsSource` had to be exported. Pins `-compass-` → `android` (incl. the web fallback, which elects as android but is NOT Kotlin-owned — the asymmetry is deliberate) and prefix-not-substring matching |
| 7. `overridePosition` for the no-fix hatch (item 0d) — the hatch's label follows the map and the capture stamps the same position | same file | |

The bug item 4 caught: `GeoTrackingManager` was constructed twice in
frontend2 — once by `MapSensorController` (which PUBLISHES the election) and
once by `AndroidPhotoCapture` (which writes the fix rows) — and the elected
source is per-instance state. So every fix taken while the map position was
elected went to disk with no election recorded at all, which is exactly the
row `getLocationNearTimestamp` has to be able to drop. Fixed by
`GeoTrackingManager.get(context)`, one instance per process (the `PhotoDatabase.
getDatabase` idiom), with all four frontend2 call sites moved onto it. The
Tauri app was never affected — `ExamplePlugin` holds exactly one.

## Missing, highest value first

### 1. The composite key actually keeps both rows — DONE

The core of the whole change, asserted nowhere. Two sources writing the *same
millisecond* must produce two rows; before, one silently replaced the other.

Instrumented (needs Room): `frontend2/shared/src/androidDeviceTest/kotlin/cz/hillview/`
— see `PhotoStorageTest.kt` for the shape. Insert two `BearingEntity` rows with
one timestamp and different `sourceId`, assert both come back. Then insert the
same `(timestamp, sourceId)` twice and assert REPLACE still collapses that —
the narrowing is deliberate, not an accident.

### 2. Per-source rate limiting, and the starvation bug that was fixed — DONE

`GeoTrackingManager` gated all writes on one 10 ms clock that advanced **even
on rejection**, so a stream arriving faster than the interval starved every
writer indefinitely, and a 1 Hz `gps-kalman` bearing could lose its slot to the
~10 Hz sensor stream. Now per-`sourceId`, and only an accepted sample moves
that source's clock.

Awkward: `rateLimitStorage` is private. Either widen it to `internal` and unit
test it directly (cheapest, and the logic is the whole point), or drive it via
the instrumented layer — hammer source A while source B writes once, assert B
landed.

### 3. Claim → pan → shoot (item 0e) — DONE

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

### 4. frontend2's election reaches the tables — DONE

The Tauri side has this (appium, above); frontend2 has nothing equivalent, and
its publisher is a different implementation — `MapScreen.android.kt`, keyed on
the map centre so every pan writes a fresh `manual` row.

Behaviour layer: claim manual, pan, trigger the export, assert the locations CSV
has a `manual` row at the new centre carrying `elected=manual`, and that fixes
recorded meanwhile are `android` rows carrying `elected=manual` too. The appium
spec's `csvColumn()` helper is the header-driven way to read a column — don't
index by position, the dumps have gained columns twice now.

### 5. `toTableSource` / `kotlinOwnsSource` — DONE

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

Was blocked on a decision: `PhotoDatabase` had `exportSchema = false`, and
Room's `MigrationTestHelper` needs the exported JSON. Turning it on (and
committing the schema files) is the only way to test migrations properly, and
would have verified this one mechanically instead of by the eyeball diff that
was actually used — the generated `PhotoDatabase_Impl.kt` was read and compared
by hand against the migration's `CREATE TABLE`s.

**Decided 2026-08-08: export is ON**, per app, into
`shared-kt/schemas/{frontend2,tauri}/` — see the README there. Measured, not
assumed: the two toolchains produce the SAME `identityHash`
(`ef6349b19157b4e0aa99385e36151066`), so they agree about the schema; the files
differ only in Room 2.6.1 writing defaults that 2.8.4 omits. Cost was one word
here and one argument in each build file. The known hole (a processor argument
is not a Gradle output, so the directory is untracked by up-to-date checking) is
documented in both build files and the README.

**The v13→v14 test itself is still not written**, deliberately: `13.json` was
never exported, so this particular migration needs a hand-made fixture either
way, and the appetite for that ran out. From v14 onward the mechanical route is
available. If it is ever wanted, two options remain — recover `13.json` by
building the pre-v14 tree in a git worktree with export on, or the raw-SQL
fixture below.

**Archaeology (2026-08-08), because nobody remembered why it is off.**
`exportSchema = false` has been there since the file was created
(337ed8da, 2025-08-15, at `version = 2`) — it is the value you write to
silence Room's "Schema export directory is not provided" build warning, not a
decision anyone took. The day after, the same author added
`kapt { arguments { arg("room.schemaLocation", "$projectDir/schemas") } }` to
`frontend/tauri-plugin-hillview/android/build.gradle.kts` (2c760628) — the
other half of that fix — but with `exportSchema = false` nothing is ever
written, `schemas/` does not exist, and the build still prints
*"The following options were not recognized by any processor:
'[room.schemaLocation, …]'"* on every run. So the Tauri side is dead config,
and frontend2's KSP setup passes no Room argument at all.

Tradeoffs, if it is turned on:
- Two build systems compile the same entities (Tauri kapt, frontend2 KSP) and
  would each emit a `14.json`. They must be pointed somewhere deliberate, or
  two copies drift apart and whichever build ran last "wins" the diff.
- The JSON has to be committed with the entity change that produced it. Nothing
  in this repo enforces that, so a stale schema file is a silent possibility.
- It does not help THIS migration: `13.json` was never exported, and
  `MigrationTestHelper.createDatabase(db, 13)` needs it. The v13 fixture is
  hand-written either way.
- Upside is real but forward-looking: from the next migration on, every one can
  be tested mechanically, and entity edits show up as a reviewable schema diff.

**Alternative that needs no build change**, and tests the actual crash: create a
v13-shaped database by raw SQL (the old DDL, `PRAGMA user_version = 13`), open
it through `Room.databaseBuilder(...).addMigrations(MIGRATION_13_14)` and touch
a DAO. Room validates the migrated schema against the entities on open and
throws "Migration didn't properly handle…" if they disagree — which IS the
first-open-after-upgrade crash. Weaker only in that the v13 starting DDL is
transcribed by hand (recoverable from MIGRATION_8_9 / 9_10 and the photos
migrations).

### 7. `overridePosition` for the no-fix hatch (item 0d) — DONE

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

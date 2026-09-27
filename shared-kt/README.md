# shared-kt — Kotlin shared between the Tauri app and frontend2

One implementation, consumed as **source** by both Android builds (no
published artifact, so no Kotlin-metadata/AGP version coupling):

- `frontend/tauri-plugin-hillview/android` adds `../../shared-kt/src` to its
  main source set;
- `frontend2/shared` adds it to `androidMain`.

Rules:

- Files move here **verbatim** from the plugin (keep `package
  cz.hillview.plugin`, keep the learning); refactors are limited to severing
  Tauri-bridge/DB imports via constructor-injected interfaces.
- Conservative Kotlin only — must compile under both toolchains (currently
  Kotlin 2.0.20 on the Tauri side, 2.4.x in frontend2).
- No Tauri imports, no Room entities, no android.app dependencies beyond
  Context; anything platform-orchestration (WorkManager, foreground
  services) stays app-side and calls in.
- Pure-logic files (MadgwickAHRS, HeadingFilter, culling) are candidates to
  graduate further into frontend2's commonMain later; they enter here first.

Photo-worker family (2026-08-07, third wave): PhotoWorkerTypes, WorkerState,
StreamPhotoLoader, DevicePhotoLoader, PanoramaxPhotoLoader, CullingGrid,
AngularRangeCuller — pure moves, both toolchains verified. frontend2 adopts
the loaders behind its PhotoMarkerSource adapters (LoaderMarkerSources.kt);
PhotoWorkerService stays plugin-side until its ExamplePlugin reference is
carved out (the PhotoUploadCommands pattern). Known upstream quirk kept
verbatim: StreamPhotoLoader sends client_id=default.
2026-08-27 (SOURCES): `StreamPhotoLoader.loadPhotos(…, onBatch = null)` reports
each SSE batch (accumulated, bounds-filtered, capped) so both consumers can
publish per source as it arrives; `CullingGrid` tie-breaks equal-priority
sources by id (arrival-order independence) and has host tests in frontend2.
See docs/sources-loading.md.

Sensor family COMPLETE (2026-08-05, second wave): EnhancedSensorService,
DeviceOrientationProvider, MyDeviceOrientationSensor, PreciseLocationService,
AppLifecycleObserver (pure moves) + GeoTrackingManager (its two JSObject
command handlers carved to the plugin's GeoTrackingCommands.kt). frontend2
gained play-services-location 21.3.0. Adoption in frontend2's capture
bearing is the next step (EXIF direction-ref contract review first).

Pilot COMPLETE (2026-08-05): the full upload family compiles in both apps —
PhotoUploadLogic (Tauri bridge carved out to the plugin's
PhotoUploadCommands.kt as same-package extension functions),
PhotoUploadManager/Worker/StatusSyncWorker/ForegroundService, PhotoDatabase +
all entities/DAOs, AuthenticationManager, NotificationHelper, PhotoUtils,
ClientCryptoManager. frontend2 does not yet *run* it (its Ktor UploadQueue is
still the live path); wiring + retiring the queue is the next step. See
docs/frontend2-rewrite-plan.md.

## The two builds do not agree on dependency versions

Same source, two classpaths — and they are further apart than the toolchain note
above suggests. Measured 2026-09-27:

| | Tauri app | frontend2 |
|---|---|---|
| okhttp | **4.11.0** (declared, `tauri-plugin-hillview/android/build.gradle.kts`) | **5.3.2** (resolved: `libs` pins 4.12.0, ktor 3.4.3 drags `okhttp-jvm` 5.x in, highest wins) |
| Room | 2.6.1 | 2.8.4 |
| kotlinx-serialization | 1.5.1 | 1.9.0 |
| Kotlin | 2.0.20 | 2.4.x |

**So a "redundant" warning here may be load-bearing there.** `Response.body` is
`@Nullable` in okhttp 4.11.0 and `@NotNull` in 5.3.2 — verified twice, by javap on
both jars and by compiling frontend2 against the forced-down version. frontend2
therefore reports a dozen "Unnecessary safe call on a non-null receiver of type
'ResponseBody'" in `PhotoUploadLogic`, `AuthenticationManager`,
`PanoramaxPhotoLoader` and `StreamPhotoLoader` that are the ONLY form compiling in
both apps. They stay. Do not "clean them up"; `?.` on a non-null receiver is
merely redundant, while `.` on a nullable one does not compile.

The asymmetry is what makes this a trap: only frontend2's build log gets read, so
a warning that is wrong for the Tauri app is invisible, and a fix that breaks the
Tauri app is invisible until someone builds it.

Before acting on any "unnecessary"/"redundant" warning in this directory, compile
frontend2 against the OTHER app's version — no source edit needed:

```bash
cat > /tmp/force.gradle <<'EOF'
allprojects { configurations.all { resolutionStrategy {
    force 'com.squareup.okhttp3:okhttp:4.11.0'
} } }
EOF
cd frontend2 && ./gradlew --init-script /tmp/force.gradle \
    :shared:compileAndroidMain --rerun-tasks
```

If the warning disappears under the older version, the code it points at is
required. (Forcing kotlinx-serialization down to 1.5.1 this way fails in KSP
instead — fall back to `javap -v` on the two jars and read the
`@Nullable`/`@NotNull` after each method's Code block.)

Checked and found NOT to diverge, so these were safe to act on: Room's
`Migration.migrate` parameter is named `db` in 2.6.1 and 2.8.4 alike (our 25
overrides were renamed from `database` to match), and serialization's
`JsonElement.jsonObject` is `@NotNull` in 1.5.1 and 1.9.0 alike.

## Auditable refactor method (how code moves here)

Converged on during the PhotoUploadLogic split; use it for every move:

1. Derived files start as `cp` of the original at its canonical path
   (verify `diff -q`); the original stays put as the diff baseline until the
   final step. Pure moves are `git mv` (git records a rename). For a code
   *section* moving between existing files, the same principle at line
   granularity: sed line-range extract spliced verbatim into the target
   (verify `diff <(sed -n 'A,Bp' src) <(sed -n 'C,Dp' dst)`), then shaped
   with visible edits.
2. Changes are surgical and individually reviewable: contiguous deletions +
   minimal one-line seams (receiver changes, `private`→`internal`), each
   non-obvious seam commented. No wholesale rewrites, no opaque scripted
   multi-transforms.
3. Nothing is deleted-to-nowhere: a removed symbol either remains in a
   sibling file or its destination is named.
4. Cosmetics (surplus imports, moved-code indentation) are deferred to one
   explicit final formatting pass so intermediate diffs are purely semantic.
5. Green compile+tests at the end of each coherent step; review with
   `diff original derived` (deletions + seams only) and
   `git diff --color-moved=dimmed-zebra` (verbatim moves shown dimmed).

Layout note: `src/` is compiled by both apps; `src-pending/` is
shared-in-principle code whose dependency closure frontend2 doesn't satisfy
yet (compiled only by the Tauri build). Graduation src-pending → src is a
pure `git mv`; an empty `src-pending/` is the convergence finish line —
reached for the upload family 2026-08-05; the dir stays for the next wave.

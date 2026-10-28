# Panoramax contribution: flags, the `panoramax_in` grant, intake vs outflow licence

## Implementation status (2026-10-28)

Phases 1 and 2 are implemented. Phase 0 was already complete and was not rerun.
The migration is **038_panoramax_contribution**, chained after the existing
037_photo_bestof_eligible merge; dev now has one head and scope `p1`.

Verification completed: API unit tests (380 passed, 1 skipped), federation unit
tests (81 passed), upload/edit/contributor and real PostgreSQL eligibility
integration tests, JVM tests (455), Android host tests (548), Room migration and
outbox device tests, CSV export device tests, and both real-catalog e2e modes.
The heavy run used 50,000 photos and harvested 40,473 eligible items with zero
harvest errors; all new exclusion kinds and share withdrawal/restoration passed.
Both Room v31 schemas have the same identity hash. The Tauri plugin also passes
a clean `assembleDebug`; its incremental kapt cache needed clearing to export
the correct v31 entity layout (see `shared-kt/schemas/README.md`).

Implementation also fixes gaps exposed during verification: JSON-null detections
are excluded, outbox-only work wakes the single upload drain even with automatic
file uploads off, and CSV delta fields have a separator. A changed CSV header
starts a new segment with a current baseline and preserves older segments.

The live emulator upload/card-edit smoke test passed, including withdrawal with
automatic file uploads off, as did capture-to-CSV verification. The external ADB
server on port 5038 has no device; device verification used a disposable local
AVD. Panoramax legal wording and SPDX declarations remain provisional as planned.
See [the federation guide](../panoramax-federation.md) for the implemented model.

## Context

The Panoramax federation service (`backend/panoramax/`, not yet deployed/registered)
federates exactly the `ccbysa4+osm` photos today. That is wrong: our CC grant does not
cover the LO 2.0 / CC-BY derived-data use the catalog makes (docs/panoramax-federation.md,
"How our grant compares"). Hillview can federate only what it holds enough rights to
relicense: `full1` and a new third intake grant, `panoramax_in`.

A photo's licence has two layers that stay distinct everywhere: what the user grants
Hillview (intake, `Photo.legal_rights`) and what Hillview publishes it under (outflow,
every read's `license`):

| intake (granted by the user) | outflow (published by Hillview) |
|---|---|
| `full1` | `arr` (Hillview chooses to keep all rights); **`panoramax`** if the owner chose Panoramax sharing, regardless of every other gate |
| `ccbysa4+osm` | `ccbysa4+osm` |
| `panoramax_in` (new) | **`panoramax`** (new), always, federated or not |

The wording of the `panoramax` outflow licence is not decided yet, so labels and prose are
placeholders. Installed Tauri builds will show the new outflow id as unknown until the
next release, which is accepted.

A photo is federated iff:
- its intake is `full1` or `panoramax_in`;
- the **owner share flag** is on (new capture toggle, default OFF);
- the **moderator approval** is on (default ON);
- the owner's **contributor flag** is on (moderator toggle, default ON);
- it has **no anonymization doodles**: the detector ran and no box is blurred. Skipped or
  manual anonymization never federates;
- plus every existing gate.

User decisions (2026-10-26):
- Instance host is `p1.geovisio.hillview.cz`.
- The capture toggle is always shown; only the panoramax service acts on the flags.
- Photos taken before a licence choice keep `license = null` and adopt the global licence
  at upload. This is today's behaviour, with no migration and no dialog.
- The "Contributing to Panoramax" explainer is its own settings page.
- Outflow changes are recorded in a **new** history table. `PhotoLicenseHistory` stays the
  intake history. Recall is not a concern.
- The detections format migration goes first (Phase 0). The doodle check then reads the
  stored `blurred` flag directly, with no new column.

The prototype client is frontend2. The web frontend follows once this settles (out of scope).

## Phase 0: prerequisite, `docs/todo/detections-format-migration.md`

Follow that plan and its 2026-10-27 git/inventory findings:
1. inventory the production dump for rehearsal, then refresh the inventory in live prod
2. establish writer behavior from history; use pixel checks for unresolved questions
3. idempotent batch migration with backup and `--dry-run`
4. verify unchanged blur verdicts, selected objects and geometry, allowing only added flag/provenance fields
5. delete the legacy rule from consumers.

Afterwards, every object carries an explicit `blurred`, so a raw-SQL consumer (the panoramax
service imports nothing from `common`) can test doodles without re-deriving `should_blur()`.

The plan has its own verification and is its own PR. Reconsider then whether a stored
column is still worth having. The default answer is no.

The DB column is `json` (`001_initial_schema.py:115`, confirmed in the local
production-dump inventory); the migration plan now reflects this.

## Phase 1: backend

### Migration `037_panoramax_contribution`
Merges the two current heads: `down_revision = ('036_photo_analysis_queue', '036_photo_imu_samples_url')`.
If Phase 0 needs a migration of its own, chain after it.

- **`users`:** `panoramax_contributor BOOL NOT NULL server_default true`.
- **`photos`:**
  - `panoramax_owner_share BOOL NOT NULL server_default false`
  - `panoramax_moderator_approved BOOL NOT NULL server_default true`
- **New table `photo_outflow_license_history`**, append-only and FK-free on the same reasoning
  as `PhotoLicenseHistory` (`common/models.py:408`): it must outlive the photo and both accounts.
  - Columns: `id`, `photo_id`, `photo_owner_id`, `photo_owner_username`,
    `old_license`/`new_license` (outflow ids), and `cause`
    (`'grant_change'` | `'panoramax_share'`).
  - Plus `actor_user_id`, `actor_username`, `actor_role`, `actor_was_owner`, `reason`,
    `ip_address`, `user_agent` and `created_at`.
  - Its question is "under which licence did Hillview publish this photo, and when". The
    original outflow is not a row: it is derived from the intake and share flag at upload,
    mirroring `PhotoLicenseHistory`'s convention.
- **`user_moderation`:** `old_panoramax_contributor`, `new_panoramax_contributor`
  (BOOL NULL), mirroring `old_active`/`new_active`.
- **`CREATE OR REPLACE` the trigger functions:**
  - `panoramax.bump_sequence_on_photo_change()` (033:109-136): add `panoramax_owner_share`,
    `panoramax_moderator_approved` and `detected_objects::text` to the `IS DISTINCT FROM`
    list, because a re-anonymization changes eligibility.
  - `photos_stamp_content_updated_at()` (034:61-75): add `panoramax_owner_share`, because it
    changes the photo page's licence.
- `UPDATE panoramax.sequences SET scope='p1' WHERE scope='cc'`, with a downgrade that reverses it.

### Models and helpers
- **`common/models.py`:** new columns on `User`, `Photo` and `UserModeration`, plus the new
  `PhotoOutflowLicenseHistory` model.
- **`api/app/hillview_routes.py:48-67`:**
  - add `'panoramax_in': 'panoramax'` to `LEGAL_RIGHTS_TO_LICENSE`, which also extends
    `ALLOWED_LICENSES` for upload and edit.
  - add `outflow_license(legal_rights, panoramax_share)`, which returns `'panoramax'` for
    `full1` with sharing on and otherwise the existing mapping.
  - replace every read call with it; each one already loads the full `Photo` row:
    `hillview_routes.py:241`, `bestof_routes.py:268`, `activity_routes.py:121`,
    `photo_routes.py:859, 1434, 2220`.
  - rewrite the comment block in intake/outflow terms: `full1 → arr` is Hillview's outflow
    choice.

### API
- **Upload:** `UploadAuthorizationRequest` (`user_routes.py:1571-1594`) gets `panoramax_share: bool = False`.
  The `Photo(...)` at `:1771-1796` sets `panoramax_owner_share`.
- **`PATCH /photos/{id}`** (`photo_routes.py` `edit_photo`):
  - `panoramax_share: Optional[bool]` is **owner-only**; anyone else gets a 403.
  - `panoramax_approved: Optional[bool]` is **moderator-only**, copying the `featured` gate at
    `:1302-1325`. The `PhotoModerationAudit` write at `:1398-1418` records it through `changes`.
  - **History:**
    - The intake `PhotoLicenseHistory` write (`:1376-1395`) is unchanged.
    - Compute the outflow before and after the edit. If it changed, also write a
      `PhotoOutflowLicenseHistory` row, with cause `grant_change` or `panoramax_share`. So
      turning sharing on for a `full1` photo records `arr → panoramax`.
  - The response adds `license_granted` and `panoramax_share` for owners and moderators, plus
    `panoramax_approved` for moderators.
- **Reads:** `license` stays the outflow, as today, and is now computed by `outflow_license`.
  `GET /photos/public/{uid}` (`photo_routes.py:2220`) gets the same owner and moderator extras
  as PATCH, so edit forms read `license_granted` instead of inverting the outflow.
- **`GET /photos/{id}/license-history`** (`photo_routes.py:809-882`):
  - `current` comes from `outflow_license`.
  - The existing `entries` stay intake changes.
  - Add `outflow_entries` from the new table, filtered by the same viewer rules for actor fields.
- **Contributor toggle:** a new `PUT /api/admin/users/{user_id}/panoramax-contributor` in
  `admin_routes.py`, guarded by `require_moderator()` (`auth.py:866`). It writes a
  `UserModeration(action='panoramax_contributor', old/new_panoramax_contributor, reason)`,
  following the pattern at `:269`. Add the field to `_serialize_user` (`:164`).
- **Known gap, noted but not fixed:** a version-bump re-upload recreates the row
  (`user_routes.py:1695-1709`). An intake or flag change made that way writes no history row,
  which is the same gap intake history already has.

### Panoramax service (`backend/panoramax/`, raw SQL, no `common` import)
- **`app/settings.py`:** `Scope.legal_rights` becomes a tuple, and `SCOPES = {'p1': Scope(id='p1',
  legal_rights=('full1', 'panoramax_in'), license='CC-BY-SA-4.0', …)}`. The declared SPDX and
  `/api/configuration` description (`main.py:143-171`, `:118`) stay placeholders until the
  `panoramax` wording is settled. The docstrings move from `cc.geovisio` to `p1.geovisio.hillview.cz`.
- **`app/eligibility.py`**, which relies on Phase 0's explicit flag:
  ```sql
  p.legal_rights = ANY(:scope_legal_rights)
  AND p.panoramax_owner_share AND p.panoramax_moderator_approved AND u.panoramax_contributor
  AND p.detected_objects IS NOT NULL
  AND COALESCE((p.detected_objects->>'manual')::boolean, false) = false
  AND NOT EXISTS (SELECT 1 FROM json_array_elements(COALESCE(p.detected_objects->'objects', '[]'::json)) o
                  WHERE (o->>'blurred')::boolean)
  ```
  Update the docstring, and say why skip/manual are excluded.
- **Bind sites** pass a list: `sequencer.py:164`, and `main.py:226, 312, 369, 429`.
- **Default `PANORAMAX_SCOPE` → `p1`:**
  - `docker-compose.yml:298-302`
  - `docker-compose.dev.yml:53-58`
  - `.env.example:40`
  - `.env.dev:14-15`
  - `hosts.example.toml:29`
  - `scripts/host_profiles.py:103`
  - `app/tests/unit/test_config_validation.py`
- `frontend/src/lib/config.ts:25-28`: change the `ownPanoramaxInstanceUrls` default to
  `https://p1.geovisio.hillview.cz`. It currently says `panoramax.hillview.cz`, which is
  already a mismatch.
- **Scripts:**
  - `scripts/seed_photos.py:66` seeds `full1`/`panoramax_in` with `panoramax_share=True`, and
    a real detector record.
  - `scripts/generate_load.py:218-236, 347-373` writes the new columns and a `detected_objects`
    value. It sets none today, which would now exclude every row. It adds these exclusion kinds:
    `cc` (replacing `arr`), `not_shared`, `not_approved`, `non_contributor`, `doodled`, `manual`.
- **`docs/panoramax-federation.md`:** update the "Scope and licensing", naming and deployment sections.

## Phase 2: frontend2

- **Room v30 → v31** (`shared-kt/src/cz/hillview/plugin/PhotoDatabase.kt`):
  - `MIGRATION_30_31`: `ALTER TABLE photos ADD COLUMN panoramaxShare INTEGER NOT NULL DEFAULT 0`.
    Use the v17/v27 migrations as the model, append it to `MIGRATIONS`, and bump `PHOTO_DB_VERSION`.
  - Commit `shared-kt/schemas/{frontend2,tauri}/…/31.json`.
  - Add `PhotoEntity.panoramaxShare: Boolean = false` after `captureTimingJson`.
- **Capture snapshot**, the same path the licence takes:
  `CaptureScreen.kt:426` → `PendingUpload` (`UploadModels.kt:155`) →
  `SharedStackUploadPipeline.kt:331` → `registerCapturedPhoto` (`PhotoUploadLogic.kt:1460/1514`,
  with a defaulted parameter because the Tauri plugin calls it too) → authorize JSON
  `"panoramax_share"` (`PhotoUploadLogic.kt:749`).
- **The capture toggle**, one bool flipped by one button:
  - stored as `UploadSettings.shareToPanoramax: Boolean = false` (`UploadSettingsRepository.kt:63-116`),
    so it survives an app restart; persisted in `PrefsUploadSettingsRepository.kt` and
    `JavaPrefsUploadSettingsRepository.kt`; no `reconcile` needed. Each shot copies its
    current value into the row's `panoramaxShare` (above).
  - placed bottom-left, right of ⏱: record ⏱'s right edge with `onGloballyPositioned`, the same way ⏱ follows `cameraButtonRight` (`CaptureScreen.kt:1239-1276`)
  - on/off look `Color(0xCC4CAF50)` vs `LightGlass`, with `semantics { selected }`
  - `testTag("capture-panoramax-toggle")`
  - hidden while `ladderVisible`, like ⏱
  - long-press opens the explainer.
- **Edits after capture** use the photo outbox (docs/photo-outbox.md, "Adding a kind"):
  - new `OUTBOX_KIND_PANORAMAX_SHARE`, whose `PhotoOutboxPusher.push` branch sends
    `PATCH /photos/{serverPhotoId} {"panoramax_share": …}`
  - a `PhotoOutbox` setter and a read-back in `PhotoWishes`
  - editing also updates the row's `panoramaxShare`. An unuploaded photo then authorizes
    with the new value, and the outbox push after `afterUpload()` is an idempotent repeat.
- **Device photo card** (`DevicePhotosScreen.kt` `PhotoCard`, `DevicePhotoCard`, `DevicePhotos.android.kt:77-105`,
  both `DevicePhotoBrowser` impls, both screens' callbacks):
  - a "Panoramax: on/off" button, enabled at every status, `testTag("photo-panoramax-share-button")`
  - it shows the outbox wish when one is pending.
- **Licence option:** add `LicenseInfo("panoramax_in", …)` to `LICENSE_INFO` (`UploadSettingsRepository.kt:173`).
  The explainer gives Hillview permission to publish under a Panoramax-compatible licence
  (placeholder wording, pending the user's notes). Update `UploadConsentTest.kt:34`.
- **Explainer page:**
  - new `PanoramaxInfoKey` in `nav/Routes.kt`, registered in `App.kt:47-64` and the `NavDisplay`
    entries (`:110-160`)
  - `help/PanoramaxInfoScreen.kt` modelled on `CaptureGuideScreen.kt`, with placeholder
    sections: qualifying licences (intake vs outflow), anonymization (photos with doodles or
    skipped blurring are not federated), photo-quality rules, moderation, and the permanence of copies
  - linked from an "About contributing to Panoramax" button after the licence block
    (`SettingsScreen.kt:381-419`, via an `onOpenPanoramaxInfo` callback) and from the
    capture toggle's long-press.
- **`PhotoTableDump.kt`:** append a `panoramaxShare` cell and column. Move `last = true` off
  `captureTimingJson` (:847) and add the name at the end of `PHOTO_DUMP_COLUMNS` (:912-920).
- **Read side:** `StreamPhotoLoader.kt:431` passes `license` through. Add a `panoramax` label
  wherever frontend2 labels read values, and fix the stale "no endpoint to amend it"
  comments at `SimplePhotoDao.kt:347` and `DevicePhotos.kt:232`. Post-upload licence edits are out of scope.
- **Pre-choice photos:** no code change. The card already shows "X (global)" for a null row.

## Verification
- **Phase 0:** follow its own "Done when" section.
- **Backend unit tests** (`./api/run_unit_tests.sh`):
  - `test_legal_rights.py`: the `outflow_license` matrix (3 intakes × share, plus None)
  - `./backend/panoramax/run_unit_tests.sh`: config validation with `p1`, STAC, and the
    eligibility predicate over auto-clean / doodled / skip / manual-rects / NULL records.
- **Migration:** `./scripts/migrate.sh upgrade head`, then `current` shows one head, and the
  dev `sequences.scope` is now `p1`.
- **Integration tests** (`./tests/run_integration_tests.sh`):
  - `test_upload_license.py`: `panoramax_in` accepted; `panoramax_share` persisted.
  - `test_photo_metadata_edit.py`:
    - an owner share toggle on `full1` writes an `arr → panoramax` outflow row and no intake row
    - an intake change writes both
    - a non-owner share edit gets 403; a non-moderator approval edit gets 403
    - `license_granted` appears for owners and moderators only.
  - Moderator contributor toggle plus a `UserModeration` row.
- **Federation:**
  - `./backend/panoramax/scripts/e2e_federation.sh`, then `--heavy`; each new exclusion kind must be absent from the catalog.
  - Flipping share off on one photo makes it disappear after the incremental harvest.
- **frontend2:**
  - `:shared:testAndroidHostTest` and jvmTest (`UploadConsentTest`, `DevicePhotosRulesTest`, outbox pusher)
  - androidDeviceTest `PhotoDatabaseMigrationTest` (chain to v31; existing rows get 0)
  - `PhotoTableDumpStreamTest`
  - an instrumentation test that toggles `capture-panoramax-toggle`, shoots, and asserts the row's `panoramaxShare` through the dump
  - on the external emulator (`adb -P 5038`): capture with the toggle on, upload to the dev
    backend, check the DB column, toggle off in the card, and check that the PATCH lands.

# Exported Room schemas

Room's build-time description of `PhotoDatabase` — one JSON per database
version, written by the annotation processor when `exportSchema = true`
(`shared-kt/src/cz/hillview/plugin/PhotoDatabase.kt`).

Nothing reads these at runtime. They exist so that a change to an entity shows
up as a reviewable diff, and so that migrations can be tested mechanically with
Room's `MigrationTestHelper` instead of by comparing `CREATE TABLE`s by eye —
which `frontend2`'s `PhotoDatabaseMigrationTest` now does, on a device.

## Why two directories

shared-kt's entities are compiled by both apps, with different Room versions
and different processors:

| directory | app | Room | processor | configured in |
|---|---|---|---|---|
| `frontend2/` | frontend2 (KMP) | 2.8.4 | KSP | `frontend2/shared/build.gradle.kts` |
| `tauri/` | Tauri plugin | 2.6.1 | kapt | `frontend/tauri-plugin-hillview/android/build.gradle.kts` |

One shared directory would have the two overwriting each other's file on every
build. They agree on the `identityHash` — the value Room actually verifies
against `room_master_table` when the database opens — so the schemas are the
same schema; 2.6.1 merely also writes the defaults 2.8.4 omits (`"notNull":
false`, empty `foreignKeys`/`views`), which is the whole of the diff between
them.

## The rule when you change an entity

**Commit the regenerated JSON with the entity change.**

`frontend2/` is now written by the `androidx.room` Gradle plugin
(`room { schemaDirectory(...) }`), so its directory is a real declared task
output that takes part in up-to-date checking, and the same plugin stages these
files into the device test's assets — which is how `MigrationTestHelper` finds
them. The open question that had kept the plugin unadopted, whether it
understands AGP 9.3.1 plus the KMP `androidLibrary` plugin, is answered: it
knows the `com.android.kotlin.multiplatform.library` id by name.

`tauri/` is still the bare kapt argument, and there the old warning stands.
Gradle treats a processor argument as an opaque string, so that directory is
not a declared output: it takes no part in up-to-date checking or the build
cache, deleting a file goes unnoticed, and a build that finds kapt up-to-date
leaves whatever is on disk. If a Tauri-side schema diff fails to appear, force
kapt to run (touch the entity, or clean) before believing it.

## History

`exportSchema = false` sat here from the first commit of `PhotoDatabase`
(2025-08-15, at `version = 2`) — the value you write to silence Room's
"Schema export directory is not provided" warning, not a decision. A
`room.schemaLocation` line was added to the Tauri plugin's build the next day
and never wrote anything, because export was off. Both were sorted out
2026-08-08; see `docs/geo-election-test-todo.md` item 6.

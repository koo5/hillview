# Exported Room schemas

Room's build-time description of `PhotoDatabase` — one JSON per database
version, written by the annotation processor when `exportSchema = true`
(`shared-kt/src/cz/hillview/plugin/PhotoDatabase.kt`).

Nothing reads these at runtime. They exist so that a change to an entity shows
up as a reviewable diff, and so a future migration can be tested mechanically
with Room's `MigrationTestHelper` instead of by comparing `CREATE TABLE`s by
eye.

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

**Commit the regenerated JSON with the entity change.** Nothing enforces it:
the export is wired through a processor argument, which Gradle treats as an
opaque string, so the directory is not a declared task output. It takes no part
in up-to-date checking or the build cache, deleting a file goes unnoticed, and
a build that finds the processor up-to-date leaves whatever is on disk. If an
entity change seems to produce no schema diff, force the processor to run
(touch the entity, or clean) before believing it.

The proper fix, when it is worth the risk, is the `androidx.room` Gradle plugin
(`room { schemaDirectory(...) }`), which registers the directory as a real
output. It is not adopted yet — it needs a version-catalog entry and, the real
unknown, compatibility with AGP 9.3.1 plus the KMP `androidLibrary` plugin.

## History

`exportSchema = false` sat here from the first commit of `PhotoDatabase`
(2025-08-15, at `version = 2`) — the value you write to silence Room's
"Schema export directory is not provided" warning, not a decision. A
`room.schemaLocation` line was added to the Tauri plugin's build the next day
and never wrote anything, because export was off. Both were sorted out
2026-08-08; see `docs/geo-election-test-todo.md` item 6.

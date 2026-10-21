# Photo table export format

The Android photo index is an ordered change log split into 10,000-record CSV
segments: `photos.csv`, `photos-2.csv`, and so on. The first line identifies
the format and records the segment checkpoint and record count. The next line
is the CSV header; it retains the photo-table columns and appends `changeId`
and `changeAction`.

Each row is either an `upsert`, which contains the current state of that photo,
or a `delete`, which is a tombstone for a physically removed photo. Apply
segments in numeric filename order, then rows in file order. For each `id`,
retain the row with the greatest `changeId`; discard IDs whose latest action is
`delete`. Soft deletes remain ordinary upserts with `deleted=1`.

SQLite triggers coalesce pending changes by photo ID. A dump reads only those
IDs, fetches their current rows in small batches, and acknowledges changes only
through the checkpoint written to the active segment. Existing installations
seed their current rows once during the database migration to establish the
new format. Later dumps append only changed states to the active segment.

The active segment is staged before publication. Local files use Android's
`AtomicFile`; MediaStore writes a pending entry and publishes it only after the
stream closes. A full segment is sealed and later changes go into the next
segment.

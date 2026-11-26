# Orphaned photo files

Status: **todo, not started** (2026-11-07). These are notes for the work, not
a design yet.

## The problem

A photo's bytes can outlive the photo. An upload that never finishes leaves
files behind that no record points to, so no delete ever reaches them. For
example, the API connection breaks mid-upload, and the user deletes the photo
on the phone in the meantime.

**This is a privacy issue, not just a storage one.** A user who deletes a
photo assumes it's gone. If a copy lingers on a worker, in a storage pool or on
the CDN, it isn't. Deleting has to reach every copy, within a bounded time
that can be stated to the user.

## Where the bytes are, stage by stage

To be confirmed against the code as the first step of the work; this is what
a first read shows.

| Stage | Copies | Who deletes them today |
|---|---|---|
| On the phone, before upload | the local file | the user |
| Upload authorized | a `photos` row, `authorized`, no `sizes` yet | nobody, unless the photo completes or is deleted |
| On the worker, queued and processing | the upload in `UPLOAD_DIR`, the job's work dir | `process()`'s `finally` rmtree; at startup, a sweep of `UPLOAD_DIR/work` left by a crash |
| Processed, before the result is posted | size variants and the DZI tree, either on the CDN (CDN builds upload directly) or in a files pool through the API's `/photos/upload-file` | **nobody**, see below |
| Completed | the same files, now listed in `photos.sizes` (and `imu_samples_url`) | `delete_photo_files`, driven by those columns |
| `keep_pics_in_worker` | artifacts kept under `UPLOAD_DIR/opt/` on the worker | to check |

## Known ways files get orphaned

1. **Deleted before the result lands.** The worker has already written the
   variants to the pool or CDN. The user deletes the photo, and the API's
   delete soft-deletes the row and runs `delete_photo_files(photo)`. That works
   from `photo.sizes`, which is still empty because the result never arrived,
   so nothing is deleted. Afterwards the worker's result POST gets 410 and
   `/photos/upload-file` refuses further files, but what was written before
   stays.
2. **The result never arrives** (worker death, result POST given up; see
   `worker-lost-photo-detection.md`). The variants are written; the row
   stays `authorized` or later turns to `error`; nothing records the files.
3. **Re-authorization.** `authorize-upload` hard-deletes an `authorized` or
   `error` row and creates a new one under the same photo id. Files from the
   earlier attempt are not tracked anywhere. Whether the new attempt
   overwrites them (same paths) or adds a second set depends on how file names
   are built. To check.
4. **Deleted in the gallery, not in the app.** The user deletes the file with
   the system gallery or a file manager. The app doesn't notice, and the
   upload, or a server copy uploaded earlier, carries on. Whether a deletion
   outside the app should count as "delete from the server" is a product
   decision. The privacy argument says it should, at least for photos not yet
   uploaded.
5. **`/photos/cleanup-orphaned`** (`user_routes.py`) deletes `authorized`
   rows older than 1 hour, rows only, not their files. So it would itself
   orphan any files those rows had. Nothing but an integration test calls it
   today. It must not be wired up as it stands: the 1-hour cutoff would also
   delete the rows of photos legitimately queued on an aux worker overnight.

## What already helps

- The phone's delete is an outbox wish (`PhotoOutbox.wantDeleted`). A photo
  not yet uploaded stops being an upload candidate. A photo caught mid-upload
  gets deleted on the server as soon as its server id exists
  (`PhotoOutboxPusher.afterUpload`).
- A deleted row is kept (soft delete). A later result gets 410, and
  `/photos/upload-file` refuses files for it.
- The worker's own temporary files are cleaned per job and at startup.

## Directions, to decide when this is picked up

- **Make deletion work by photo id, not by what the row lists.**
  - If every artifact of a photo lives under a per-photo prefix, in pools and
    on the CDN alike, a delete can sweep the prefix whatever stage the photo
    reached and however many attempts it had.
  - Check the current path layout first; this may already nearly hold.
- **A reconciliation sweep, report-only first.**
  - List the pools' and CDN's per-photo prefixes, and flag every prefix whose
    photo id has no row, a deleted row, or a row that has been unfinished for
    longer than a worker can plausibly hold it.
  - Once the report is trusted, delete what it finds.
  - The "unfinished" test should use the worker holdings from the lost-photo
    design rather than a fixed age, so a photo queued on an overnight aux
    worker is never swept.
- **Close the gap in orphan path 1 at its source.**
  - When a photo is deleted while `authorized`, record that in the deleted
    row, and have the API's delete (or the worker, on its 410) remove whatever
    the worker already wrote.
  - The worker knows exactly which files it wrote, so it's the natural party
    to clean up on a 410.
- **The phone and deletions outside the app** (orphan path 4): decide the
  policy. If it's "deleting the file deletes the photo", the app notices
  missing files at its next scan and records a delete wish.
- **State the guarantee.** Once the above holds, say in the app and the
  privacy policy how soon a deleted photo is gone from every copy.
- **`/photos/cleanup-orphaned`:** fix it (files too, and holdings-aware rather
  than a 1-hour cutoff) or remove it.

# Upload: one funnel

**The upload schedule is a projection of queue state, decided in one place.
Status transitions happen in one place. Nothing enqueues a drain or moves a
row's status behind those two.**

Sibling of [one-state.md](one-state.md), for the same reason: every upload
bug this port has produced lived in a gap between two components that each
thought they owned a decision.

## The two owners

- **`PhotoUploadManager.reconcile(reason)`** — the ONLY thing that touches
  WorkManager. Every event that could change the queue or the settings calls
  it (a capture, a drain ending, a settings change, app start, login, a
  delete, the retry buttons); it reads the world, asks the pure
  `decideUploadSchedule` what the schedule should be, and makes WorkManager
  match. See the header of `shared-kt/.../UploadScheduler.kt` for the rule it
  keeps and the bugs that preceded it.
- **`PhotoUploadLogic.doWorkInternal`** — the ONLY thing that moves a row
  between `pending / uploading / processing / completed / failed`. It claims
  atomically on the status it selected under, and every exit path restores
  or advances the status it found.

One sanctioned helper each side: `StartupReconciler` hands abandoned
`uploading` rows back (`reclaimAbandonedUploads`) before the first reconcile,
and `StampRefiner` releases its own upload hold (`clearUploadHold`) — a gate,
not a status.

## What is NOT a violation

Reading status is free (`DevicePhotos`, the capture pill, diagnostics).
Writing fields that are not status is free (`updateLicense`,
`updateAnonymizationOverride`, `updateDeleted`). Calling
`startAutomaticUpload` / `reconcile` from anywhere is the whole point.

## Auditing it

```bash
# scheduling: only PhotoUploadManager may enqueue
grep -rn "enqueueUniqueWork\|enqueueUniquePeriodicWork\|\.enqueue(" \
    frontend2 shared-kt --include=*.kt | grep -v Test

# status: only the drain (and the startup hand-back) may move a row
grep -rn "updateUploadStatus(\|updateUploadFailure(\|updateUploadStatusAndServerId(\|claimForUpload(\|reclaimAbandonedUploads(" \
    frontend2 shared-kt --include=*.kt | grep -v "Dao.kt\|Test"
```

`UploadFunnelArchitectureTest` runs both as a test.

Retired code parked outside the source sets (frontend2 was still untracked
in git when these were dumped, so deletion would have left no history).

- UploadQueue.kt + UploadQueueTest.kt (2026-08-05): the commonMain Ktor
  upload queue and its 8 chaos-ported tests, retired when Android switched
  to the shared-kt upload stack (see /shared-kt/README.md). Its kept
  models (PendingUpload/QueueStats/UploadState, md5Hex) moved verbatim to
  UploadModels.kt. Delete this dir once its contents exist in git history.

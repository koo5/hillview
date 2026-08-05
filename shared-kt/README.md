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

Pilot COMPLETE (2026-08-05): the full upload family compiles in both apps —
PhotoUploadLogic (Tauri bridge carved out to the plugin's
PhotoUploadCommands.kt as same-package extension functions),
PhotoUploadManager/Worker/StatusSyncWorker/ForegroundService, PhotoDatabase +
all entities/DAOs, AuthenticationManager, NotificationHelper, PhotoUtils,
ClientCryptoManager. frontend2 does not yet *run* it (its Ktor UploadQueue is
still the live path); wiring + retiring the queue is the next step. See
docs/frontend2-rewrite-plan.md.

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

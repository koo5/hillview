# Panoramax contribution in the web frontend

The browser implements contribution controls alongside frontend2. Capture and
upload settings live at `/settings/upload`, the explainer at
`/settings/panoramax`, and per-grant help at `/licensing#full1`,
`/licensing#panoramax_in` and `/licensing#ccbysa4+osm`.

## Choices and their effects

Photo permissions is a separate section above Auto-Upload. It shows the current
grant, a Change button and one Panoramax sharing control. Auto-Upload contains
the upload timing choices and login status. File uploads have their own compact
File permissions section.

The license picker opens in a modal dialog without leaving the current page.
The selectable title, description and radio choose a draft grant. Each option's
separate Learn more control expands help inline without selecting anything.
Only the confirmation button applies the draft; Cancel and Escape preserve all
choices, selected files, captured photos and unsaved photo edits. The order is the
broadest grant to Hillview first: full rights, Panoramax contribution, CC.
This is not a ranking of public reuse rights.

| Upload grant | Sharing off | Sharing on |
| --- | --- | --- |
| `full1` | Publish as `arr`; not offered to federation | Publish as `panoramax`; offer for selection |
| `panoramax_in` | Publish as `panoramax`; not offered to federation | Publish as `panoramax`; offer for selection |
| `ccbysa4+osm` | Publish as CC; not offered to federation | Opens a compatible-grant dialog before enabling sharing |
| Not chosen | Upload blocked | Upload blocked; the sharing preference can still be set |

Turning sharing on with a CC grant explains the conflict and offers the two
compatible grants, with neither preselected. Cancel keeps CC and sharing off.
Confirmation applies the chosen grant and sharing together. Choosing CC in the
ordinary picker while sharing is on explicitly warns that confirmation will
also turn sharing off. This guard applies in settings, capture, file uploads,
queued photos and the owner editor. Existing legacy CC/sharing combinations
still cannot federate on the strength of that grant alone.

The summary beside the controls explains the current combination. Sharing
offers eligible views; approval, account contribution status, anonymization
and representative-view selection still apply. Final Panoramax license
wording remains pending.

Signing in, choosing a grant, enabling automatic upload and offering a photo
to Panoramax are independent. Fresh browser preferences select no grant,
disable sharing and disable automatic upload. Signing in or registering
preserves explicit browser choices and enables none of them implicitly.
If automatic upload was already enabled, signing in can upload queued photos.

## Capture, files and persistence

The browser P button sits above camera settings, with a separate help link.
It and capture Settings use `capturePanoramaxShare`. File uploads use the
separate `manualPanoramaxShare` and `manualUploadLicense` preferences.
These are browser/device preferences, rather than account settings.

At the start of a capture, its upload grant and sharing choice are copied into
the capture queue, then into the IndexedDB photo row. Changing defaults does
not alter those snapshots. Older rows and pre-choice captures have a null or
absent grant and adopt the current capture-upload grant when uploading;
absent sharing always means off. The unindexed optional fields need no
IndexedDB version change. A manual batch snapshots both choices when submitted.

Foreground and service-worker uploaders resolve consent using the same
`photoUploadConsent` helper and send it to API authorization. The image-worker
protocol is unchanged. A missing grant prevents authorization in both paths.
Automatic upload starts after Settings has mirrored its state to IndexedDB.
When there is no active service worker, sync uses the foreground drain rather
than waiting indefinitely for `navigator.serviceWorker.ready`.

Every dialog states its scope: future captures, the next file-upload batch or
only the selected photo. Capture defaults do not rewrite existing photos. A
compatible grant chosen for one queued photo changes only that photo, together
with its sharing choice in a single IndexedDB transaction.

Device-photo cards can change sharing before upload. The update and upload
claim are atomic; the uploader re-reads the claimed row so a preceding edit
cannot be lost. While uploading, local consent edits are disabled. After an
upload, the card links to the server photo page.

## Existing photos and moderation

The web photo editor uses explicit online Save, including failure feedback.
Its license dialog changes only the editor's draft; Save remains necessary to
apply either the license or sharing change to the server.
It reads `license_granted` to identify the upload grant: the `panoramax`
publication value can result from either `full1` or `panoramax_in`, so it must
never be inverted into a guessed grant. When the field is unavailable, the
editor preserves ambiguous grants rather than submitting a new one.

Only the owner gets the sharing control. Moderators get the independent
approval control; administrators can enable or disable an account's
contributions in User management. Published license changes and their causes
appear in the photo's history, including the SSR batch. Successful owner edits
also update a matching local capture's consent for later re-uploads.

Uploaded-photo edits do not have frontend2's offline outbox. They require a
successful server Save. Tauri completion is outside this browser follow-up;
the capture sharing controls are browser-only.

## Verification

`bun run check` and `bun run test:unit` cover type safety, the publication
matrix, ambiguous intake handling, capture/default resolution and both
authorization wrappers. Browser scenarios cover new preferences, label/help
clicks, modal confirmation and cancellation, signup/login, queued capture
upload, explicit opt-in, per-photo sharing and grant changes, selected-file and
unsaved-edit preservation, separate manual defaults, history and moderation.

Against a running web build:

```sh
cd frontend/tests-playwright
FRONTEND_URL=https://your-local-web-host PW_TIMEOUT_MULT=1 \
  bunx playwright test --config=playwright.panoramax.config.ts
```

This configuration acquires the usual backend test lock and creates/deletes
only its own temporary accounts and photos; it does not clear the development
database. Camera scenarios require Chromium. Playwright's WebKit cannot persist
photo Blobs in IndexedDB, so its legacy queued-capture case is skipped; its
ordinary file uploads and consent UI remain covered.

Verified 2026-10-30 against the local production web build: Svelte check had
zero errors or warnings, 840 unit tests passed, and 20 browser scenarios passed
across Chromium, Firefox and WebKit. Seven cases were skipped because camera
capture requires Chromium or WebKit cannot persist the test photo Blobs.
Desktop and 390 px mobile settings and dialogs were inspected. Mobile settings
had no horizontal overflow, and the dialog's actions remained visible while its
license details scrolled. Temporary test accounts and photos were removed.

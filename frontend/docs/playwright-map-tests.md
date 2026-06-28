# Playwright map / timeline tests

Specs live in `frontend/tests-playwright/`. Seeding + map-driving helpers are in
`helpers/captureSeed.ts`. Worked examples: `timeline-refresh.spec.ts` (marker clicks,
refresh button, stepping) and `timeline-swipe.spec.ts` (arrow / swipe navigation).

This covers the non-obvious pieces a test that puts real photos on the map and drives the
timeline would otherwise re-discover the hard way. Chromium-only: the seed needs the fake
camera, and WebKitGTK can't store photo Blobs in IndexedDB — `test.skip(browserName !==
'chromium', …)` in `beforeEach`.

## Seed photos by capturing, not by uploading files or inserting rows

There is no backend hook to insert a Hillview photo directly — a real photo has to go
through upload + worker processing. Capturing through the fake camera is the right tool
because the test fixture (`fixtures.ts`) stamps unique pixels into every frame, so the
server's MD5 duplicate-detection never fires, and a canvas frame carries no EXIF, so the
GPS and bearing aren't read from the image — the map centre and compass we set per capture
are authoritative. Uploading a fixture file instead would re-trigger dedup across captures
and pin every photo to that file's baked-in EXIF location.

`captureAt(page, lat, lon, bearing)` sets `spatialState.center` and `bearingState.bearing`
in `localStorage` and reloads; the captured photo lands exactly there. `addCaptureInit`
only flips on the camera button (debug); it deliberately does **not** pin a location, so
`captureAt` controls it per shot.

## Interleave each capture with its upload

The capture button is disabled while an upload is in flight (`$frontendBusy > 0`). If you
fire the next `captureAt` immediately, its page reload interrupts the previous upload and
the queue wedges — the button never re-enables and you hit a long timeout. So capture and
then wait for that photo to upload before the next capture: `captureAt(…)` then
`waitUploadedAtCoord(…)` (or `waitNewUpload`), one photo at a time.

## A freshly uploaded photo doesn't appear until the source is re-streamed

The map doesn't pick up a photo that finished processing after the area was already loaded
— you have to pan, toggle the source, or reload. `openMap(page, center, ids)` re-toggles
the Hillview source until all the expected markers render (it also rides out the last
photo's processing lag). Toggling — not reloading — is deliberate: a reload would reset
hunter mode, which must stay on for the non-featured captured photos to be navigable.

## Click markers with `dispatchEvent`, not `.click()`

A marker is doubly awkward: its container is `transform: translate()`-offset from its paint
box, so a `{ force: true }` click fires at the bbox centre (dead space) and misses; and the
markers re-render / detach continuously while the timeline is open, so a plain `.click()`
never passes Playwright's stability gate. `clickMarker` uses `dispatchEvent('click')`,
which only needs the element *attached* and fires the exact event the map's delegated
handler consumes (`target.closest('.marker-container[data-photo-id]')`).

## The walk can anchor on the wrong photo — retry, don't fight it

Pressing `t` anchors the walk on whatever `photoInFront` is at that instant. When seeded
photos sit at the same spot / share a bearing, the front photo can flicker to a sibling
under stream churn, and the walk anchors there. Don't try to fix it by re-opening the panel
(toggling it detaches the markers your next step needs). The describe blocks set
`retries: 2`; the rare mis-anchor is absorbed by a retry (a serial group re-runs its setup,
so the photo ids are re-seeded cleanly).

## Telling co-located photos apart

`waitUploadedAtCoord(target)` matches the just-uploaded photo by coordinate — fine when the
photos are seeded > ~50m apart. For photos at the *same* spot (e.g. the swipe test, which
needs two navigable neighbours in range), a coordinate match is ambiguous; use
`waitNewUpload(exclude)` to grab the upload whose server id you haven't seen yet.

# App behaviour, as the test suites define it

Extracted from the Appium suite (`frontend/tests-appium/specs/`, 27 specs).
Where the source tells you *how* the app works, these tell you what it is
*supposed to do* — including rules that only exist as an assertion plus a
comment explaining which bug it was written for. Companion to
`docs/tauri-map-ui-contract.md`, which covers the map UI's structure.

Written while porting to frontend2; the last section lists where the port
currently disagrees.

## Capture

- Opening the camera asks for **location permission first**, then shows an
  in-app gate (`allow-camera-btn`) whose tap triggers the **system camera
  prompt**. Reopening later shows the shutter directly, no prompts.
- The camera button is a **toggle**; capturing must not navigate away or
  unmount the shutter.
- The shutter **disables itself while a capture is in flight** and re-enables
  when the pipeline is free — the burst test clicks 50 times, each blocking
  on that, at roughly 4 s per round trip.
- Closing the camera **must not lose in-flight captures**.
- After the first capture an auto-upload prompt appears in the camera view
  (`configure-auto-upload`) leading to upload settings, where the
  auto-upload radios stay **inert until the licence is accepted**. Choosing
  "Disabled (never prompt)" suppresses the overlay entirely, *"so the
  capture-then-prompt overlay doesn't block rapid-fire clicks"*.
- Every capture must reach the device photo DB: 50 captures ⇒ 50 rows
  within 30 s.

### Storage preference is a hint, not a promise

The spec asserts the saved path matches *one of* the three shapes, not the
chosen one, and says so outright: *"Which method actually wins depends on
the Android API level and the app's runtime state, and a given preference
won't always land in its 'named' location — that's by design… What this
spec does NOT assert: that the preferred method is the one that actually
ran."* A save must never silently fail. Both `Hillview` and hidden
`.Hillview` are valid.

## Upload

- **Coalescing.** A burst of N captures must collapse to ~1 worker run, not
  N: *"a burst of N captures produced ~N workers each churning
  SystemForegroundService on the main thread, which froze the UI for minutes
  and could crash with ForegroundServiceDidNotStartInTimeException"*. The
  test bounds it at 1–3 runs for 20 captures, and asserts the UI stays
  responsive throughout.
- **Foreground drains stay silent.** Promotion to a foreground service — and
  therefore the "Uploading Photos" notification — happens **only while the
  app is backgrounded**. Zero promotions during a foreground burst is an
  assertion, not an accident.
- **Offline.** Capture must succeed with no network; nothing reaches the
  server; on reconnect the queue drains within 90 s.
- **Worker down (503).** The photo stays pending — not dropped, not marked
  done — and uploads once the fault clears.
- **Counting rule:** `authorize-upload` creates placeholder rows *before* any
  bytes arrive, so "uploaded" counts must filter to fully-processed photos.

## Map and bearing

- Required gestures: pan, pinch zoom, and **two-finger rotate**. No
  combination of them may wedge the map.
- `bearing-arrow-hitarea` exposes the current bearing through
  **`aria-valuenow`** — the only externally readable bearing in the app.
- **Long-press the compass button (≥500 ms)** opens the mode menu, and
  picking a mode **turns tracking on as a side effect**
  (*"selectBearingMode() inside bearingTracking.ts turns gps orientation ON"*).
- Car mode: driving the emulator east must move the indicator to within 45°
  of east. The filter needs speed > **1.5 m/s**, movement > **10 m**, and
  fixes spaced ≥ **1 s**; tolerance is loose because *"FusedLocation mixes in
  its own smoothing"*.
- **Bearing must survive backgrounding** — byte-identical `aria-valuenow`
  after a 5 s background.
- Markers are `photo-marker-<id>` carrying `data-photo-id`,
  `data-is-placeholder` and `data-source`.

## Location tracking

The three-state button, asserted through its CSS class:

| From | Trigger | To |
|---|---|---|
| OFF | click | ACTIVE (`active`) |
| ACTIVE | **manual map pan**, not a click | BACKGROUND (`background`) |
| BACKGROUND | click | OFF |
| OFF | click | ACTIVE — *"the cycle is restored, not stuck"* |

In BACKGROUND, GPS stays subscribed and fixes keep being logged tagged
`-background` so they lose the photo-pairing lookup, while the map stops
following.

**Entering capture must re-arm a clean ACTIVE**, and there is a regression
comment saying why: previously it left the background flag set, *"leaving
the button stuck half-blue, GPS still logging '-background', and captures
recording the live fix only as alt_location"*.

Geo export writes `hillview_orientations_<ts>.csv` and
`hillview_locations_<ts>.csv`; auto-export fires on backgrounding and again
at plugin init; the CSV's source column must show both tagged and untagged
rows.

## Auth and session

- **Transient failures must not log out.** A refresh that times out (native
  read timeout ~10 s) or returns **5xx** keeps the session; only a **401**
  clears it. The client proactively refreshes with a **2-minute** buffer.
- **Genuine expiry logs out in lockstep**: native clears the session, the
  WebView is told, and the UI lands on `/login` within 30 s.
- **And it survives process death**: the session-expired flag is
  deliberately *not* cleared by the token clear, so a kill between death and
  delivery still surfaces at next launch as a **persistent** in-app alert
  (duration 0) reading "session has expired".
- A 401 on any authenticated call forces logout within seconds.

## Notifications

- "Login Required" — channel `auth_notifications`, id 1001, within 30 s of
  the worker hitting a 401 it cannot refresh past.
- "Uploading Photos" — id 2001, ongoing for the whole drain, backgrounded
  only.
- Push: foreground delivery posts our own notification; **backgrounded
  delivery must stay silent** because Android already auto-displays it;
  killed-from-recents posts ours again. Force-stopped is explicitly out of
  scope: *"Android refuses to deliver any intent … That's a legitimate
  Android guarantee, not something to test for delivery against."*

## Resilience

Must survive: backgrounding (auth, bearing, controls), orientation flips
(no control may be lost in landscape), restarts (permissions, prefs, DB,
session-expired flag). Must not survive: a genuinely 401'd session. An API
failure on the photo list shows an inline error and recovers on remount.

---

## Where frontend2 disagrees today

Found by reading the above against the port; unfixed unless noted.

1. **Bearing is not persisted.** The map holds its state in `remember`, so
   backgrounding or leaving the screen loses it. The suite asserts the
   bearing is byte-identical after backgrounding, and the Tauri store
   persists it (default 141°).
2. **Picking a bearing mode does not enable tracking.** The port preserves
   the previous on/off state; the original turns tracking *on* as a side
   effect of choosing a mode.
3. **No `aria-valuenow` on the arrow.** The canvas arrow exposes no
   semantics, so the bearing is unreadable from outside — bad for both
   accessibility and any future UI test.
4. **Markers carry no identity.** They are canvas-drawn, so there is no
   per-photo node to find, unlike `photo-marker-<id>`.
5. **Entering capture does not re-arm location tracking**, so the
   BACKGROUND → capture → ACTIVE regression the suite guards is unguarded
   here.
6. **No auto-upload prompt after the first capture**, and no licence gate on
   the auto-upload toggle.
7. **No two-finger map rotation** — rotation is arrow-only.
8. **The session-expired notice is not persistent and worded differently**
   ("Session expired (reason)" vs the asserted "session has expired").
9. **The location button exposes no state** an external test could read
   (the original uses `active`/`background` classes).

# Zoom view: print view

A chrome-less rendering of the zoom view's current window with the share-link
QR code in the middle, meant to be sent to the printer with the browser's own
print dialog (Ctrl+P). Web only — the Android webview has no print dialog to
hand over to.

## Using it

Open a photo in the zoom view, pan/zoom to the wanted window, then ⋮ → **Print
view**. The close button and toolbar disappear, the background turns paper
white, the title and (when the terrain overlay is on) the data attribution stay
at the bottom, and a white tile with the QR and the site's name
(`hillview.cz`) sits dead centre. A scan of the code reopens exactly this
window — the link is minted the same way the Share item mints it
(`buildShareUrl` in `shareUtils.ts`: short `/shared/{slug}` when the backend
cooperates — public, non-deleted hillview photos — the long `?photo=…&x1..y2`
form otherwise). The code is kept sparse two ways: error-correction level L,
and the slug's decorative title part is dropped (`compactShareUrl` →
`/shared/{id}`, which is all the resolver reads) — a typical link is a 25×25
symbol. If it comes out dense, the mint fell back to the long URL. Only the
host is spelled out: nobody types a slug off paper, and a text strip turned
the tile into a slab. Info popups (photo info window, terrain pick card, label evidence) are
left alone: what is open prints.

The pills flip to a paper palette while the mode is on — white with black
text and a thin dark outline, for both the annotation labels
(`LABEL_PALETTE_PRINT` in `shared/zoomview/labelPaint.ts`) and the terrain
slats (`SKY_PILL_PALETTE_PRINT` in `shared/terrain/labelPills.ts`; settlements
keep a faint blue cast) — and the leaders get thicker (annotation ×2, slats
2.5 px at scale 1): a stationary hairline over a photo is easy to miss on a
sheet. Both painters take the palette as an optional style field; their
defaults, and the on-screen look, are unchanged.

Ctrl+P (or the hint strip's **Print** button) prints; **Esc** or **Exit**
leaves the mode. Mouse navigation is locked while the mode is on so the view
cannot drift from what the QR encodes — leave, adjust, re-enter. The hint
strip (screen only) spells out what the code encodes — `QR → hillview.cz/shared/13`
— or flags `short link unavailable` when the mint was refused and the code
carries the long map URL instead. "Save as PDF" is named after
`document.title`, which is `<photo title> – Hillview` for as long as the zoom
view is open (the page's own title comes back on close).

For framing the view before entering: **Shift+wheel** zooms in fine steps
(1.15× per notch against the plain wheel's 2.5×). Browsers report a shifted
wheel as a horizontal delta, which OpenSeadragon ignores, so the viewer reads
the wheel itself on `canvas-scroll`.

What ends up on paper is the viewer at its on-screen pixel size, scaled to
the page: printed resolution equals screen resolution. The mode switches the
label scale to 1.4× (`PRINT_LABEL_SCALE`) for the duration — the whole view
shrinks onto a page, the pills should not — and restores the visitor's own
value on exit. Page orientation follows the view's aspect ratio (an injected
`@page { size }` rule — Chrome's dialog then does not offer the flip).

## How it prints — the freeze

Printing this viewer live was racy: OpenSeadragon refits itself in its rAF
loop, the terrain/label overlay canvases are resized (which clears them) by a
`ResizeObserver` with a rAF redraw behind it, and Chromium snapshots the print
layout somewhere in the middle. The terrain line came out on a stale
projection and the label canvas blank. Compositing the layers into one image
is not an option either: the OSD canvas is tainted by cross-origin tiles.

So nothing re-renders at print time. During a print job (`beforeprint` →
`afterprint`) and for the whole time the print view is on:

- `viewer.autoResize = false` — OSD keeps its screen-sized canvas;
- the ResizeObserver callback is a no-op — the overlay canvases keep their
  bitmaps;
- `@media print` turns `.osd-overlay` into a centred box with the screen
  container's aspect ratio (`--print-ar`), so the CSS scale applied to the
  frozen bitmaps is uniform and the overlays stay on the photo. This is also
  what makes the paper show exactly the current view, letterboxed.
- the rest of the app is `visibility: hidden` under `body.hv-zoomview-open`
  so the map does not print around the box, or on pages after it.

This applies to plain Ctrl+P too, not only the print view.

The pre-existing "slightly off" print bug had a second, older cause: the
overlay canvases were `position:absolute; inset:0` with no CSS width/height.
A `<canvas>` is a replaced element, so `inset:0` alone leaves it at its bitmap
size — indistinguishable from "fills the container" on screen, wrong the
moment the container is scaled for the page while OSD's own canvas
(`width:100%`) scales along. They are `width:100%; height:100%` now.

## Known limits

- Annotorious draws the annotation rectangles on a WebGL canvas, which
  Chromium prints blank (no `preserveDrawingBuffer`). The label pills and
  their leader lines are ours and print; the green boxes do not.
- The QR tile, title and attribution are DOM, not bitmap; they follow the
  box through `--print-short` (the box's shorter side: `vmin` on screen, the
  letterboxed box on paper), so a print is the screen picture scaled — but
  only while the print view is on. Plain Ctrl+P outside the mode keeps the
  stylesheet's px sizes for the strip.

## Layers

Bottom to top inside the OSD container: annotation leaders
(`osd-label-leader-canvas`) — terrain canvas (horizon, slat leaders, slats;
slats painted after all their leaders) — annotation pills
(`osd-label-canvas`). So no leader of either kind is drawn across a label of
either kind, and the pills stay readable over the horizon line. `paintLabels`
takes `pass: 'leaders' | 'pills'` for the split; the workbench keeps calling it
once with the default.

## Verifying

`page.pdf()` in headless Chromium goes through the same print pipeline as
Ctrl+P (it does dispatch `beforeprint`/`afterprint`), so a Playwright script
that opens the view, enters the mode and calls `page.pdf({ landscape: true })`
is a faithful reproduction — compare against `page.screenshot()`.
`tests-playwright/zoomview-print.spec.ts` pins the chrome hiding, the QR/link,
the aspect-locked print layout with the canvases scaled onto it, and the
single-page PDF.

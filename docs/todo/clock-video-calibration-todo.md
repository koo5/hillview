# Clock-calibration video — TODO / handoff

Status as of **2026-07-13**. Feature spans two repos: the recorder in
`hillview/frontend`, the solver + pipeline wiring in the `pics` sibling repo
(`~/repos/koo5/pics/0/pics`).

## ✅ Validated end-to-end on a real video (2026-07-13)

First real recording (`~/GeoTrackingDumps/hillview_clockvideo_1783977790271.webm`,
Armor 22 / Android 14, night handheld footage of a Canon Date/Time menu) went through
the whole pipeline and **recovered the correct correction**:

- Recorder is solid: 161/161 frames carried rVFC `captureTime` stamps (mean latency
  1.5ms, max 30ms) — the draw-time bias concern is moot on this device. Burned QR
  decodes on every extracted frame.
- Solver output: main-clock correction **[-186.064s, -185.831s)** (233ms wide) →
  **camera ~185.95s (≈3m6s) fast**. Independent by-hand check (phone UTC 21:23:10 vs
  camera clock 21:26:16) = +186s. **Agreement ~50ms.**
- This worked *despite* tesseract misreading many individual frames (the `1`→`4`
  seconds confusion gave phantom `21:26:48`/`:49` reads). The monotonicity +
  median-offset outlier filters dropped 25 of 58 clock frames; the 4 clean second
  flips (21:26:17→20) carried the answer. Individually-unreliable OCR,
  statistically-robust result — as designed.
- **Cross-validated by a second, longer video** (`hillview_clockvideo_1783977739431.webm`,
  431 frames → 37 flips): correction pinned to **−186.013s** (14ms leeway), landing inside
  the short video's interval. Two independent clips agree on ~186.0s fast to ~15ms. The
  14ms leeway is the real precision floor (LCD-refresh latency + rolling shutter — the
  tens-of-ms budget the design anticipated), not the literal 0.000s width the rounding shows.
- **Timezone resolved:** camera menu shows "London" but does **not** DST-shift (would
  read ~22:23 if it did) — it's effectively UTC, just ~3min fast. `tz_offset_hours=0`
  is correct. The ~3min is genuine clock drift, which is the whole point.

### Fixes made from the real footage
- `CLOCK_RE` now tolerates spaces around the colons — the Canon menu renders
  `21 : 26 : 16` and the old regex required bare `21:26:16`. Regression test added
  (`test_extract_clock_spaced_colons`). geotag tests 13 pass.

The items below remain, but the method is proven.

## What this is

Alternative to the QR-photo clock correction. The Hillview app films the external
camera's date/time **settings screen**; every recorded frame has a QR of the phone's
UTC time (unix ms) burned into a fixed panel, so the video's container timestamps are
irrelevant — each frame carries its own real time. The pipeline OCRs the camera clock
on every frame (handheld → no stable crop) and, per observed **second flip**, ties a
camera main-clock whole second to a one-frame-wide phone-time window (~33ms @ 30fps).
Intersecting those windows gives the main-clock correction; widened by the Canon
work-timer δ∈[0,1) it becomes the EXIF-correction window `[main_lo, main_hi+1)` that
feeds the existing drift fit.

## Done (green here, unverified on target hardware)

- **Recorder (hillview/frontend):**
  - `src/routes/settings/advanced/clock-video/+page.svelte` + link from
    `settings/advanced/+page.svelte`.
  - `src/lib/components/ClockVideoRecorder.svelte` — canvas composite, `QRCode.create`
    per frame, `requestVideoFrameCallback` captureTime stamps with a rAF fallback +
    stall watchdog, MediaRecorder 1s chunks, browser-download fallback when not in Tauri.
  - Plugin: `ClockVideoWriter.kt` + `clock_video_begin/chunk/end` commands in
    `ExamplePlugin.kt` → streams to
    `GeoTrackingDumps/hillview_clockvideo_<ms>.webm` + `.json` sidecar.
  - `bun run check` clean; plugin JVM unit tests pass.
- **Solver (pics `src/geotag/video_time_correction.py`):** core + CLI, mirrors
  `qr_time_correction.py`. Pluggable `ocr=` (tesseract default, `--psm 11`, digit+colon
  whitelist tolerant of spaced colons, both polarities), rotation probe-and-lock, LNDS +
  median-offset outlier rejection, bounded-memory streaming OCR pool. Primary output =
  `FlipObservation` list. **Proven on real footage (see above).**
- **Pipeline (pics `src/pipeline/task/clockvideo.py`):** `SolveClockVideo` (per-video,
  caches `<video>.correction.json`) + `ClockVideoCorrections` (per-camera, discovers
  videos in `csv_dir` = `~/GeoTrackingDumps`, writes `~/.geotag/<cam>/video_corrections.csv`
  + `video_flips.csv`). Folded into `CameraCorrections` (dict-requires; video rows carry
  the EXIF window, `main_lo_s/main_hi_s/n_flips` cols added to the correction_points schema).
- **Tests:** `src/tests/test_video_time_correction.py` (13 pass, incl. real-tesseract now
  that the binary is installed), `src/tests/test_clockvideo_task.py` (5 pass). `import
  tasks` clean with new deps (`opencv-python-headless`, `pytesseract`) added to pipeline +
  geotag `pyproject.toml`.

## TODO

- [ ] **Compile-verify the Kotlin.** Not built this session (declined the heavy build).
      Run `frontend/scripts/android/debug-build.sh` (scaffolding at `src-tauri/gen/android/`
      is already generated). Confirm `ClockVideoWriter` + the three commands build. *(The
      recorder itself is confirmed working — real videos exist in `GeoTrackingDumps` — but
      that was from an already-installed build, not one compiled from this session's diff.)*
- [ ] **CameraCorrections regression check.** `requires()` changed from a list to a dict
      (`{"corrections": [...], "clock_videos": ...}`) and `.input()`/`complete()` handling
      was updated to match. Its existing tests were **not** re-run for this change — verify
      the task still runs end-to-end (a real `RunDate`/`RunWorkdir`, or add a task test).
- [ ] **OCR robustness (optional / quality).** Not a blocker — outlier rejection already
      recovers the right answer on hard night footage — but yield could be higher. On the
      real video, 25/58 clock frames were dropped (tesseract's `1`→`4` seconds confusion;
      date+time concatenation defeating the leading regex guard). Options if a future video
      resolves too few flips: crop-to-screen + upscale before OCR, a digit classifier via
      the `ocr=` seam, or just shoot brighter/steadier footage that fills more of the frame.
- [ ] **Measure the systematic bias (optional).** Camera-LCD render latency + draw-time
      stamps (when rVFC captureTime is unavailable) both make `c_main` read high by tens of
      ms, one direction. On the first device captureTime was available for 100% of frames
      (latency ~1.5ms), so this is negligible there — revisit only if a device falls back to
      draw-time stamps (the sidecar's `capture_time_frames` flags it).

## Quick verification commands

```bash
# pics solver + task tests
cd ~/repos/koo5/pics/0/pics/src/tests
uv run --script test_video_time_correction.py
uv run --script test_clockvideo_task.py

# solve one real video ad-hoc (writes per-frame CSV for inspection)
cd ~/repos/koo5/pics/0/pics/src/geotag
python video_time_correction.py <video>.webm --csv frames.csv --json result.json

# hillview: type-check + plugin build
cd ~/repos/koo5/hillview/0/hillview/frontend
bun run check
./scripts/android/debug-build.sh          # Kotlin compile (not yet run)
```

## File map

| Repo | Path | Role |
|---|---|---|
| hillview | `frontend/src/routes/settings/advanced/clock-video/+page.svelte` | recorder page |
| hillview | `frontend/src/lib/components/ClockVideoRecorder.svelte` | camera→canvas→QR→MediaRecorder |
| hillview | `frontend/tauri-plugin-hillview/android/src/main/java/ClockVideoWriter.kt` | file writer |
| hillview | `…/ExamplePlugin.kt` (`clock_video_*` cases) | command dispatch |
| pics | `src/geotag/video_time_correction.py` | solver core + CLI |
| pics | `src/pipeline/task/clockvideo.py` | `SolveClockVideo`, `ClockVideoCorrections` |
| pics | `src/pipeline/task/cameracorrections.py` | consumes video rows (dict-requires) |
| pics | `src/tests/test_video_time_correction.py`, `src/tests/test_clockvideo_task.py` | tests |

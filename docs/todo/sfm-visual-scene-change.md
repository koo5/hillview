# SfM run: judge scene change visually

Parked 2026-11-13, unstarted. Measured on the desktop only; nothing is built in
the app.

The SfM run (`OverlapRun.kt`, the bottom rung of the shutter's ladder) shoots
on **distance** (the receiver's integrated speed), **turn** (the angle between
lens directions) and a **heartbeat**. All three are proxies for the thing SfM
actually needs: how much of the last shot is still in view. The idea parked
here is to measure that directly from the camera, as a fourth trigger ("the
view changed by N %"). It matters most where the proxies are weakest:
- indoors and in tunnels, where there is no GPS speed;
- with compass tracking off, where there is no attitude and so no turn signal
  (the "Known gap" in the 2026-11-05 section of `../frontend2-status.md`).

Origin: user, 2026-11-09: "we should look into how cpu intensive it would be
to make it judge scene change visually".

## The frames are already there

CameraX `ImageAnalysis` at 640x480 is bound for exposure metering
(`PhotoCapture.android.kt`, `onAnalysisFrame`). It uses
`STRATEGY_KEEP_ONLY_LATEST` on a single-thread `analysisExecutor`, and today
it only feeds SceneMeter's subsampled mean (~2 µs a frame). A visual judge
would read the same luma plane, so it costs CPU only: no extra camera stream
and no change to the capture pipeline.

## Benchmark

`oneoff/scripts/2026-11-09_1800_scene_change_bench.java`, with its output in
`…bench.out.txt`. It is a single-file Java program run on one thread under
HotSpot, on a Ryzen 5900X. It turns a real photo into luma at 1.6× a 640x480
frame and simulates a pan by sliding a 640x480 window to the right across it.

Cost per frame, median µs:

| Method | µs | Rough phone estimate (not measured) |
|---|---|---|
| SceneMeter subsampled mean (what runs today) | 1.8 | — |
| Thumbnail 80x60 + sum of absolute differences | 176 | ~1 ms |
| Phase correlation, 64x64 Hann-windowed FFT | 632 | 3–5 ms |
| KLT: build a 3-level pyramid from 320x240 | 261 | |
| KLT: track 150 Shi-Tomasi corners (9x9 window, 8 iterations) | 3707 | 15–30 ms as written; 3–6 ms with OpenCV |
| KLT: find corners on a new keyframe (once a shot) | 2059 | |

The phone column assumes a mid-range big core is 4–8× slower than this
desktop, and little cores 10–15×. **Real numbers need a run on the phone**; see
next step 1.

The pan check. The window slides dx pixels of a 640-wide frame:

|  dx | overlap | thumb SAD | phase (dx, dy, peak)  | KLT tracked / 150 |
|----:|--------:|----------:|-----------------------|------------------:|
|   0 |   100 % |      0.00 | 0, 0, 1.00            | 139 |
|  16 |    98 % |     12.01 | 20, 0, 0.68           | 134 |
|  64 |    90 % |     25.33 | 60, 0, 0.63           |  62 |
| 128 |    80 % |     40.52 | 130, 0, 0.61          |  26 |
| 192 |    70 % |     47.39 | 190, 0, 0.40          |  13 |
| 256 |    60 % |     41.46 | 260, 0, 0.15          |  19 |
| 320 |    50 % |     40.59 | 50, 15, 0.16 (wrong)  |  21 |
| 380 |    41 % |     44.45 | 110, 15, 0.13 (wrong) |  17 |

## What each method can and cannot tell

- **Thumbnail difference saturates at about 20 % shift.**
  - Past that point it reads ~40–47 whatever the pan: a 20 % pan reads 40.5
    and a 60 % pan reads 41.5. It cannot separate "overlaps a lot" from
    "barely overlaps", which is exactly the range a trigger has to judge, and
    it is not even monotonic.
  - It measures how different the picture looks, not how far the camera
    moved. A plain scene (sky, a wall, fog) reads low after a big pan, and a
    passing car, swaying branches or an exposure change read high with the
    camera still.
  - It is at most a "something changed" hint.
- **Phase correlation is the candidate.**
  - It reports the global shift itself, accurate to about 40 % pan (256 px →
    260), and fails at 50 % and beyond. When it fails, the peak height drops
    to ~0.15, so a low peak can be read as "lost track, shoot now".
  - It only needs to compare the current frame with the last shot, so it can
    run a few times a second rather than on every frame. At ~5 Hz that is
    about 2 % of one core.
  - It does not see walking forward, because that changes the scale rather
    than shifting the view. The distance trigger covers forward walking.
    Fourier–Mellin (log-polar) would measure scale and rotation too, at
    roughly 2–3× the cost.
- **KLT feature tracking measures overlap for any motion,** as the share of
  tracks still alive. It is what SfM and SLAM front ends do.
  - Tracked straight against the keyframe, as written, it loses track beyond
    about 30 px at 320 resolution: at dx = 64 it gave −19.6 px instead of −32.
    So it must chain frame to frame, which means running on every frame.
  - It costs 5–10× more than phase correlation. It probably also needs OpenCV
    to be fast enough, and OpenCV is a large native dependency: it would go
    through `scripts/deps.py` and add to the APK size.

## Suggested shape, if picked up

1. **Measure on the phone first.** Port the bench to an `androidDeviceTest`
   that runs the same kernels on a synthetic or bundled frame and prints the
   medians, for both the big and the little cores if they can be pinned.
2. **Then try phase correlation as a fourth `OverlapSpacing` trigger,** next to
   `metres`, `turnDeg` and the heartbeat, and null when switched off like the
   others.
   - **Where it runs:** on the analysis executor, throttled to a few Hz, and
     only while an SfM run is armed.
   - **What it compares against:** the 64x64 luma of the frame captured
     nearest the last shot.
   - **When it shoots:** when |shift| exceeds N % of the frame (try 25 %), or
     when the peak falls below a floor (lost track).
   - **What it records:** a new `OverlapReason`, e.g. `Viewed("view")`, so the
     capture stats say how often vision paced the run.
3. **KLT only if field runs show phase correlation missing real overlap loss.**
   The likely case is forward walking where GPS speed is absent.

## Open questions

- Which frame is "the last shot's"? The analysis frame nearest the shutter is
  close, but not the exposed one. The gap may not matter at a few Hz.
- Does auto-exposure moving between frames upset the correlation? Phase
  correlation normalises magnitude, so it should be fairly robust, but this
  is untested.
- Portrait vs landscape: a shift is a different share of the frame along each
  axis, so it must be measured against the right dimension.

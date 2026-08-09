# Reconstruction field notes — MASt3R-SfM, the Prosek bit, and the board

*Companion to `vision-subsystem.md` (the design doc) and `pano-source-archaeology.md` (the
pano→source-frame map). This is the narrative/empirical log of the 2026-06-15/16 session that
turned "match annotations against random photos" into "reconstruct the world bit by bit." Kept
for posterity; durable decisions get promoted into `vision-subsystem.md`.*

## The turn: from random matching to local reconstruction

We started trying to localize annotated pano features by matching a hand-drawn rectangle against
candidate photos. The hard wall was **Doppelgangers**: pairwise feature matching (even MASt3R)
returns confident, geometrically-verified matches between things that merely *look* alike — a
different church, a similar skyline, 32–80 RANSAC inliers on a false pair. Pairwise matching has no
way to know. The realization: **global consistency is the missing signal.** If instead of matching
A↔B in isolation we *reconstruct a local patch of the world* from many overlapping photos, an
impostor cannot register into a single coherent multi-view solution — its geometry contradicts the
rest. So the strategy flipped to "model the world bit by bit," and localization becomes "register
the query into the reconstruction."

## The demo: `scripts/enrich/reconstruct.py`

Drives the full **MASt3R-SfM** (`sparse_global_alignment`: per-pair forward pass → matching → 3D
optimisation → 2D reprojection refine → triangulation) end-to-end on **CPU**. It:
1. Selects a coherent set of close-range photos from the prod dump — gates: within radius of a
   centre, optional capture-time window, has a full-res URL, **not `deleted`**; then sorts by
   capture time and slices/strides.
2. Downloads, runs the reconstruction, exports `scene.npz` (poses, focals, sparse points),
   optional `dense.npz` (per-pixel cloud + depthmaps + confidences), `points.ply`/`dense.ply`,
   `metadata.json` (every frame: GPS, bearing, focal, recovered pose, residual), and a Leaflet
   `report.html`.

**The validation that matters.** We have no ground-truth poses, but we have independent **GPS**.
So: take the recovered camera centres, align them to GPS with a single **Umeyama similarity**
(scale + rotation + translation — 7 DoF, nothing per-camera), and measure each camera's residual.
First run (5-photo, 71-second burst): ~30 k sparse points, **median camera↔GPS residual 5.2 m**
(mean 4.9, max 7.5) — i.e. *within phone-GPS noise itself*. The reconstruction, told only "here are
some pixels," independently agrees with where the phone thought it was. That's the honest success
signal, and it's the whole thesis in one number.

Bonus observation: MASt3R estimates **focal length from pixels alone** (not EXIF) — ~395 px on a
512-tall frame ⇒ ~52–65° FOV, the correct phone lens, and 5 frames landed within 4% of each other.
Coherent geometry, not flailing.

## Hard-won operational facts

- **512 (long side) is MASt3R's native resolution, not a downgrade.** The ViT is `img_size=512`,
  16-px patches → 32×32 tokens; it was trained there. It reasons from low-res *global* context,
  which is exactly why it bridges wide-baseline / scale-gap pairs that classical keypoint matchers
  can't. Detail-precision, when needed, comes from a separate coarse-to-fine pass, not from feeding
  the backbone bigger images.
- **A GPU buys speed, not resolution.** ~32 s/pair CPU → sub-second GPU (30–100×). That flips N²
  whole-cluster reconstruction from weeks to hours. Install the CUDA RoPE2D kernel
  (`dust3r/croco/models/curope`) — the "slow pytorch version" warning is the CPU fallback.
- **Forward passes cache per-machine** (keyed by image content), so CPU work here won't transfer to
  a rented GPU box — prove correctness on CPU, run scale on GPU.
- **Don't globally disable autograd** — `sparse_scene_optimizer` needs it for the optim loop (the
  forward passes manage their own no_grad). A one-line `set_grad_enabled(False)` killed the first run.
- **Select by time-window, not list index** — different filter sets produce different orderings, so
  "index 79" meant different photos in two scripts and silently selected a months-spanning,
  non-overlapping set. Time bounds are reproducible.
- **Filter `deleted`** — the dump carries deleted duplicates (e.g. two extra "západ" panos at the
  lookout); they'd poison a cluster reconstruction.

## Two clustering axes (and a terminology trap)

We kept saying "sparse/dense" for two *orthogonal* things — name them separately:
- **Frame sampling:** *contiguous* (every frame, small baseline, safe overlap) vs *strided*
  (every Nth, real baseline, risks losing overlap). The open question on a walk.
- **Output density:** *sparse* cloud (keypoints) vs *dense* cloud (a 3D point per confident pixel).

And the bigger axis — **how you choose the set**:
- **Time clustering** (a walk): consecutive captures overlap by construction; cheap *time-ordered
  sliding-window* pairing works. The easy regime, same lighting, gradual viewpoint change.
- **GPS clustering** (a vantage across all dates): *more meaningful* for modelling a place — fuses
  every view of it, ever — but harder two ways. Harder on the **model** (cross-date lighting/season/
  foliage gaps; Doppelganger-adjacent). Harder on **compute**: no natural order ⇒ the cheap window
  doesn't apply ⇒ exhaustive or retrieval pairing (N²) ⇒ the GPU job.

Experiments (2026-06-16): `walk_sparse` (strided across the whole 432 m / 9-min walk) vs
`walk_dense` (contiguous first 1.5 min, dense output) — bracketing the strided-overlap question.

**Result — strided sampling fails, as predicted.** `walk_sparse` (30 frames, every ~8th, ~14 m
apart): **median camera↔GPS residual 81 m, max 173 m** (vs the contiguous burst's 5.2 m), focals
incoherent (`354…632`, varying 2× where the burst held within 4%), and the residual profile is
textbook SfM **drift** — low in the middle (12–36 m), ballooning at both ends (150–173 m). The
top-down shows the 30 cameras *clumped in one corner* instead of tracing the path, with the cloud
spraying in disagreeing directions: weak overlap couldn't establish baseline, so the solve collapsed
the chain. Conclusion: **you can't sparsify a walk** — ~14 m spacing on a *turning* path drops below
the overlap MASt3R needs to lock geometry. Contiguous (or retrieval-paired) frames are required.

**Control — contiguous vindicates.** `walk_dense` (48 contiguous frames, overlap maintained
during capture): **median camera↔GPS residual 2.9 m** (mean 4.0, max 12.8, *0 frames >25 m*) —
tighter than the stationary burst, and the walk's back half sits at **1–2 m**. 715 k sparse / **2.88 M
dense** points, and the top-down shows the cameras tracing the path with the dense cloud forming
coherent planar facades/ground. So the bracket closes cleanly: **contiguous → 2.9 m, sparsified →
81 m** — same walk, same everything else, only the frame spacing differs. Caveat: a few focal
estimates were outliers (280–576 px vs the ~370–404 cluster) on under-textured frames, yet their
*positions* still resolved (low residual) because the network pins them — focal is locally
under-constrained but globally rescued. Takeaway for capture & selection: **keep every overlapping
frame; never subsample a sweep.**

**Big caveat — the GPS residual is a weak metric (don't over-read it).** It measures only
*camera-centre* alignment after a 7-DoF Umeyama fit: it reliably catches **catastrophic drift** (the
81 m strided case *is* broken), but it says almost nothing about whether the **3-D structure** is
good. Cameras can sit a few metres from the GPS track while the point cloud is smeared or locally
warped. On eyeballing, the contiguous Prosek walk **did not actually solve well** despite its 2.9 m
residual — so "contiguous → 2.9 m = clean reconstruction" was an overclaim. Treat the residual as a
*drift gate*, not a quality score. We need a structure-level signal instead — MASt3R-SfM's own **2-D
reprojection error** from the bundle is GPS-independent and the obvious candidate to surface. The
strided-vs-contiguous *ordering* still holds (81 m is genuinely broken, 2.9 m is at least
non-catastrophic); the *absolute* "clean" verdict does not.

## Corpus regimes → pairing tools (two kinds of overlap)

Bearing is present on **all non-deleted photos** (cornerstone of the DB) — biased as a measurement
but guaranteed-present, so it's a universal pairing/gating key. But it predicts only *one* of two
overlap types:
- **Rotation / co-location overlap** — frames at ~same spot, similar bearing (a 360 sweep or a
  pan-as-you-walk sequence). Predicted by **bearing + proximity** pairing. The reconstructable
  sweet spot.
- **Convergence overlap** — frames at *different* spots whose cones meet on a shared *distant*
  landmark; cameras can be far apart with different bearings and still overlap. **Not** predictable
  by bearing+proximity (proximity excludes them; the convergence angle depends on target distance,
  which is what we're solving — circular). Needs **image retrieval** (appearance-based).

The corpus splits the same way, and the tools map onto it:

| Pattern | Overlap | Tool |
| --- | --- | --- |
| 4 cardinal shots at one spot | none (orthogonal) | nothing connects them; bearing-pairing returns ~0 pairs — correct, not a failure |
| 360-ish sequence (rotate / walk-sweep) | rotation, frame-to-frame | bearing + proximity pairing — the Prosek walk is one |
| Distant landmark from many spots | convergence | image retrieval (the original localization problem; GPU) |

So **geometric pairing reconstructs local 360/sweep units; retrieval links far-apart views of a
shared distant feature.** Cardinal-only spots simply won't form connected local models — fine; they
get localized later via the retrieval/anchor path. Don't subsample sweeps (kills rotation overlap,
per the 81 m strided result).

## The board: a perfect flat Doppelganger

At **Vyhlídka Prosecké skály** (Prosek Rocks lookout, ~50.1169, 14.4884) — the end of the
2026-06-15 walk, and the home of the well-annotated east pano `333e8851` — there is a physical
metal **information board printed with a labelled panoramic photo of the Prague vista**: numbered
markers + legend (*O2 Arena, Pankrác, Balabenka, Plynojem Palmovka, …*). It is, bolted to a railing,
**exactly Hillview's annotation task** — and the most adversarial impostor imaginable: a flat board
~1 m from the camera whose pixels reproduce a scene that is kilometres deep. Seen frontally in
`f05f60ee` (2026-01-19), and alongside the real skyline in walk frame `85d931b5` (2026-06-15 18:35).

Why it's *the* decisive probe: a 2D matcher must match the board's printed skyline to the real
vista — a confident false positive, the Doppelganger by construction. But MASt3R is **3D-grounded**:
the board should reconstruct as a **coplanar patch at ~1 m and wrong scale**, the real vista as deep
structure to the horizon. **Plane-vs-depth** is the thesis made visible — global geometry rejecting
what pairwise matching cannot. The board's legend doubles as a ground-truth landmark list for
localization validation. This vantage is the natural target for the GPS-cluster experiment and the
first GPU job.

**Tested so far — inconclusive.** Two attempts: (a) the 3-frame Jan session (`f05f60ee`/`f2239b09`/
`6519358d`) was *underpowered* — 3 m baseline, board fills the frame, so MASt3R fell back on its
monocular prior and the depth came out compressed/noisy. (b) The 60-frame June walk-end **sweep**
(`board_sweep`, 18:34–18:37 with real baseline) solved far better, but `85d931b5`'s depthmap is still
*messy*: the board reads near-ish at the bottom, **but with stripey depth artifacts that follow the
printed panorama's content** — the depth estimator partly hallucinates depth from the *printed*
scene. That's the Doppelganger one level deeper (it fools depth, not just 2-D matching), and it's
genuinely interesting, but it is **not** the clean flat-plane-vs-deep-vista demo. Verdict pending a
better setup (more board-facing baseline) and a structure metric, not the GPS residual.

## Panoramas: slice the delivery, or use the source frames?

A delivered pano (`333e8851` is 66 897×5 133) can't go into MASt3R raw — squashed to 512 wide it's a
useless smear. Two ways to feed panos into reconstruction:
1. **Slice the delivered pano** into perspective sub-views (overlapping virtual pinhole cameras). The
   work we already wanted for pano calibration; but it bakes in any stitching errors.
2. **Use the original source frames** (the individual photos that were stitched). Advantages: real
   perspective images (MASt3R-native), and — key — the **`.pto` stitch project records each source
   frame's solved yaw/pitch/roll/FOV**, so the in-pano geometry is *written down by the stitcher*,
   not presumed. That makes the source frames a ready-made mini-reconstruction *and* a mutual
   cross-check (MASt3R's solve vs the `.pto` angles). It also dodges stitching artifacts entirely
   (none in the Prosek panos; a few in others). Cost: a retrieve/redevelop pipeline for the source
   frames — see `pano-source-archaeology.md`. Maybe not worth it yet, but the right idea if/when we
   pull panos into the 3D solve.

## Masking: don't paint — crop or mask correspondences

**Don't paint masked regions (gray/black fill) — it's wrong on the mechanics.** A fill creates a hard
fill↔scene **boundary**, and edge/corner detectors fire precisely on that boundary → you *add*
artificial features at box-determined locations instead of removing them. And a flat fill isn't
ignored either: MASt3R is **detector-free / dense**, so it still estimates correspondence + depth on
the fill (low-confidence, not zero — an ill-posed uniform region can inject drift). The literature
avoids fill for exactly this reason. The two correct tools:

1. **Crop** when the clutter is a fixed band at the edge → removes the content *and* its boundary, no
   artifact. → the **Solocator top compass/GPS bar**: `crop_solocator_bar` lops the fixed top ~15%.
2. **Correspondence-level masking** otherwise → exclude masked pixels from *matching*: keep a binary
   per-image mask and **drop any correspondence whose endpoint lands in it** (no pixel touched). This
   is the standard approach — dynamic-object SLAM (**DynaSLAM** drops keypoints on people/cars),
   MASt3R's own **`mask_sky`** removes sky from the solve rather than filling it. Implemented by
   wrapping `forward_mast3r` (`install_corr_masking`): after the per-pair `(xy1,xy2,confs)` are
   cached, filter by `CORR_MASKS[path]` (keyed by path — `convert_dust3r_pairs_naming` remaps
   `instance`→path). **Validated:** on a 2-frame Solocator-overlay pair it dropped **152/1226
   correspondences** (12%) landing on the green marks — i.e. the image-fixed overlay *was* generating
   false frame-to-frame matches at fixed pixel positions, exactly the hazard, now removed cleanly.

What gets masked, by what it's *pinned to*:
- **Pinned to the image** (same pixel every frame) → **always remove** (false-match hazard). The
  **Solocator overlay** (`--mask_solocator`): top bar **cropped**, neon-green crosshair/tilt/timestamp
  marks **correspondence-masked** (green ≈ R44 G221 B38, separable from olive foliage; detected on the
  loaded frame so it's in the correspondences' own coordinate frame). Identify by `original_filename ∈
  /shared/slc/sync` (2871 matched); overlay only on a 2025-03 subset (green-detected, so others are
  untouched). The worker does **not** strip these.
- **Synthetic clutter pinned to the scene** — the worker **doodles random colors per photo** over
  detected people/cars (privacy handled upstream; real content never reaches us). Random per-photo ⇒
  mostly no correspondence, but random ≠ guaranteed-distinct, so a chance doodle-match would be a
  *false* one. `--mask_anon` now **correspondence-masks** these too (no painting): the boxes come in
  original-image px, so they're mapped original → full(download) → saved (any Solocator crop) →
  loaded frame via `map_box_to_loaded` (replicating load_images' resize-long-side-512 + centre-crop-
  to-/16), then fed to the same `CORR_MASKS`. **Validated:** dropped 310/10740 correspondences on a
  2-frame walk pair. (The old gray-fill is gone; the `walk_dense` 2.9 vs `walk_dense_masked` 9.8 A/B
  that seemed to "prove harm" was over-read noise anyway.)

(Worker side, independent value: `detected_objects` now persists an explicit `"blurred"` bool so the
debug overlay / threshold tuning needn't re-derive `should_blur`; four schema variants documented in
`backend/worker/detections.py`.)

## Walk → world: merging local reconstructions

Per-walk SfM is the easy part; **stitching walks into one model is the hard part** (large-scale SfM /
lifelong SLAM). The architecture: **walk = submap** (locally rigid, GPS-anchored, metric) → **pose
graph over submaps** (nodes = walks; edges = relative transforms from GPS priors + *verified* visual
overlaps) → optimize the graph (cheap; distributes drift) → grow incrementally. Foreseeable
challenges:
1. **Inter-walk linking, and false links.** Walks connect only where they share view content —
   *retrieval at scale*, not the within-walk pairing. A single false link (lookalike places, the
   board) **folds two parts of the city together and warps everything** — so loop-closure
   verification by reconstruction-consistency is load-bearing here (the anti-Doppelganger thesis, now
   global).
2. **GPS is the gauge, not the glue.** It pins each submap into a shared frame + bounds drift, but at
   metre-scale noise → overlapping walks ghost/double unless snapped tight by *visual* correspondence.
3. **Drift & scale.** Per-walk scales are wildly different (62 / 9 / 1.7 units/m before metric
   anchoring); accumulated drift needs GPS-anchored BA + loop closures.
4. **Time.** Cross-date lighting/season/foliage + transients (the Doppelganger-adjacent regime).
5. **No global batch BA.** Hence the submap + pose-graph hierarchy; **DEM** (Copernicus GLO-30) is a
   coarse vertical/scale sanity constraint.

Storage reality (from `walk_dense`, 48 frames): the canonical layer is **poses + sparse points
≈ 16 MB/walk** (~0.2 MB/m); dense clouds ~60 MB and the forward-pass **cache ~1.8 GB are disposable**
(regenerable from photos + poses). A densely-walked city ≈ **hundreds of GB sparse-only**, ~1 TB with
dense — tractable. Gaussian Splatting, if wanted, is a *separate* GPU optimization **seeded by** these
poses+points (init Gaussians at the sparse points → differentiable-render-fit to the photos) — i.e.
our SfM output is the front half of a splat pipeline.

## Tooling built this session

`scripts/enrich/reconstruct.py` — selection (`--photos_csv`, time-window, radius, `--stride`,
`--deleted`-filtered), pairing (`--pairs swin|complete|bearing`), `--dense`, `--inject` (impostor
test), `--mask_solocator`/`--mask_anon`, per-frame depthmap renders, full `metadata.json`. Reports
served (with the inspector) on **:8765** — `/runs/` index, `report.html` (tiles4.ueueeu.eu basemap,
input thumbnails linking to hillview.cz for cross-check, depth column), and `/runs/<run>/view` (a
three.js colored point-cloud viewer). `regen_report.py` rebuilds a report from `metadata.json`
without recompute.

## Structure metrics (2026-07-28) — tooling and the traps in it

`scripts/enrich/recon_metrics.py` computes two GPS-independent numbers per run, both in pixels
of the loaded 512-long-side frames, both **per pair** (a false link hides in one pair, and a
run-level scalar averages it away). It needs nothing but what a finished run already has on
disk: `scene.npz` plus the forward-pass cache. `--self-test` validates it on a synthetic scene;
`--compare` prints a cross-run table.

- **reproj** — unproject a correspondence through image *i*'s depthmap, project into *j*, measure
  the pixel miss. This is the structure metric: it tests depth and pose together. Directional by
  construction (it uses the source frame's depth), so both directions are reported.
- **epipolar** — distance to the epipolar line, from poses and focals only, so it works on every
  run with no re-solve. **It has a blind direction**: error *along* the epipolar lines is
  invisible to it. Synthetically, a 2° camera rotation about the baseline axis produced 14 px of
  real reprojection error and **0.10 px** of epipolar error, while the same rotation across the
  lines produced 14.13 px of both. So epipolar is a cheap screen, never a quality score; a low
  epipolar beside a high reproj means the depth is wrong, not the poses. It also degenerates as
  the baseline goes to zero, so near-zero-baseline pairs are flagged and excluded, not scored.

Three traps, each of which silently produced wrong numbers before being caught:

1. **`scene.npz` did not save intrinsics, and `sparse_ga` optimizes principal points**
   (`opt_pp=True`). Approximating pp at the image centre is not a rounding error — it is larger
   than a good solve's entire error. On masktest the true pps sit 4–6 px off centre, and the
   approximation inflated the reprojection median from **0.71 px to 3.57 px**. reconstruct.py now
   saves the full `intrinsics` matrix; older runs need `recon_resolve.py`.
2. **A run can be re-solved from its cache, and comparing two solves must be gauge-invariant.**
   The expensive forward passes are cached, so only the 300+300 optimizer iterations re-run.
   masktest, board_jan and walk_sparse came back bit-identical (max delta **0**). walk_dense
   appeared to land 41 scene units away — **140% of the scene extent** — which read as a different
   local minimum and was nothing of the sort: **a reconstruction is only defined up to a global
   similarity**, and once the two pose sets are Umeyama-aligned they agree to **0.67% of extent**,
   with a global scale difference of 0.22% and focals within 2.9%. Its GPS residual reproduced to
   0.003 m. So the naive check was the bug; `recon_resolve.py` now aligns first and reports
   aligned RMS as a fraction of extent, alongside focals (which *are* gauge-invariant).
   The corollary bites in the metric too: mixing a re-solve's poses with the archived
   `dense.npz` depthmaps puts baseline and depth in **different units**, so recon_metrics rescales
   the depths by the recovered gauge factor, and never pairs K from one solve with poses from
   another. It also recomputes the GPS residual for whichever poses it scores, so the drift and
   structure numbers always describe one reconstruction. (That reimplementation was checked against
   reconstruct.py's: it agrees to 3 decimals.) Sidecars never modify archived artifacts.
3. **Pair ORDER feeds the kinematic chain.** Hand-assembling the pair list from the cache — same
   pairs, different order — sent masktest to a different local minimum whose cameras sat 264% of
   the scene extent from the archived ones. Pairs must come from `make_pairs` with the run's own
   scene-graph string; recon_resolve verifies the rebuilt set against the cache and refuses to
   proceed on a mismatch.

Coverage is reported too, because it is a signal rather than a footnote: pixels whose depth was
cleaned away, or that land behind the other camera, cannot be scored. A badly broken solve can
therefore *look* better than it is, since those correspondences are excluded rather than
penalized — board_jan can only score 51.5% of its correspondences, and walk_sparse pushed 1604
points behind cameras.

**And the metric this doc originally asked for is not the one to use.** The open thread said
"surface MASt3R-SfM's own 2-D reprojection error". That number is printed as `>> final loss`, and
harvesting it from the run logs shows it ranks the runs *wrongly*: board_jan scores **0.0029**,
the lowest — i.e. best — of every run, while being the most structurally broken one we have. It
is a confidence-weighted gamma loss over the solver's own parameterization plus a DUSt3R
regression term, in no interpretable unit, and a degenerate 3-frame solve can drive it to near
zero. So the honest metric has to be recomputed post hoc, unweighted, in pixels — which is what
recon_metrics does. Treat `final loss` as an optimizer diagnostic only.

## Results (2026-07-28) — every archived run, measured

All seven re-measured with exact recovered intrinsics. `reproj` = median / p90 pooled over all
correspondences; `epi` = median epipolar; GPS = median camera↔GPS residual for the *same* poses.

| run | frames | reproj med | reproj p90 | tail | epi med | GPS m | coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| masktest | 4 | **0.71** | 4.0 | ×6 | 0.33 | 0.2 † | 100% |
| board_sweep | 60 | **0.94** | 76.0 | ×81 | 0.50 | 3.9 | 99% |
| walk_jizni | 70 | **1.96** | 69.2 | ×35 | 0.61 | 11.1 | 98% |
| walk_dense | 48 | **2.55** | 135.1 | ×53 | 0.70 | 2.9 | 97% |
| walk_dense_masked | 48 | **2.86** | 132.2 | ×46 | 0.62 | 9.9 | 95% |
| walk_sparse | 30 | **77.2** | 657.5 | ×9 | 42.20 | 81.0 | 95% |
| board_jan | 3 | **560** | 648.9 | ×1 | 294.02 | 0.0 † | 52% |

† fewer than 5 cameras: a 7-DoF Umeyama fit has nearly as many parameters as observations, so the
GPS residual is arithmetic, not evidence. board_jan is the proof — 0.0 m on the worst solve we own.

**The GPS residual does not rank these runs.** Spearman correlation between the structure ordering
and the GPS ordering is **0.07** — essentially none. Dropping the two sub-5-camera runs it rises to
0.50, so the drift gate carries weak signal once it has enough cameras, and none at all before that.
The single worst inversion: walk_jizni is 3rd best by structure and 2nd worst by GPS.

**Most of these solves are good, and that was hidden.** Five of seven sit under 3 px median; the
earlier "everything solved poorly" reading was entirely the principal-point artifact. The real
defect is the **tail**: p90 runs 35–81× the median on the walks and the sweep. So the answer to
"did walk_dense actually solve?" is *yes in the core, no in a minority* — median 2.55 px with a
135 px p90 and 18 k points behind cameras. That is what the June eyeball verdict was seeing, and it
reframes the work from "make it solve" to "find the broken minority", which the per-pair table
localizes.

**Two failure modes, distinguished by the tail ratio.** A genuinely broken solve is *uniformly*
broken (board_jan p90/median ×1, walk_sparse ×9); a good solve is excellent-with-a-warped-minority
(board_sweep ×81). The median says whether the right structure was found; the tail says how much of
it is wrong. Reporting only one of the two misleads in opposite directions.

**The masking A/B was a wash, not a harm** — which retires the doubt the notes recorded in June. GPS
claimed masking made things 3.4× worse (2.9 → 9.9 m). Structure barely moves and disagrees with
itself about the sign: median 2.55 → 2.86 px favours unmasked, while p90 (135 → 132) and epipolar
(0.70 → 0.62) favour masked. Differences of a few percent in both directions ⇒ the A/B never carried
a verdict. Keeping correspondence-masking on mechanical grounds stands.

Dashboard (charts, per-pair spread, synthetic validation):
https://claude.ai/code/artifact/871175e0-efc4-4f3a-88ea-d879f0b06e1c

## The Doppelganger control, instrumented (2026-07-29)

The `--inject` impostor test was always the point of the reconstruction turn — "a Doppelganger
that fools pairwise matching cannot register into a globally consistent solve" — but until now
it produced no number. It does now, and the instrumentation is what makes it a test rather than
an argument:

- Injected frames are excluded from the GPS alignment fit (they always were), **and** scored
  separately by recon_metrics: their reprojection/epipolar error is compared against a baseline
  computed over **real-real pairs only**, so the impostor cannot dilute the very baseline it is
  being judged against. Reported as `impostors[]` with a ratio and a verdict.
- **"No matches" is its own verdict, not a pass.** An impostor that produced under 100
  correspondences was never a test of anything: nothing had to be rejected. Counting that as
  success is how this experiment would fool itself, so the metric names it `no-matches`.
- Thresholds: ≥5× the real baseline = `rejected`, ≤2× = `registered` (the thesis failed for
  that case), between = `ambiguous`.

**Methodology caveat on pairing.** The API appends impostors at the end of the frame list, and
with the default `swin-N-noncyclic` pairing an appended frame is only paired with the *tail* of
the cluster — its window neighbours, not every real frame. That is a weaker test than the notes
originally imagined. For a full-strength impostor test use `pairs: "complete"`, which costs
little at cluster sizes where this experiment is interesting (9 frames: 72 directed pairs vs
52).

### Result: THE BOARD IS REJECTED (`doppelganger-board`, 2026-07-29)

The adversarial case, finally measured. Cluster: 8 real frames from the June sweep at the
Prosek lookout (18:35:11–18:35:26, panning SW→SE). Impostor: **`f05f60ee`**, the January frontal
shot of the information board — a flat panel ~1 m from the camera, printed with the very Prague
vista it stands in front of. Chosen over the notes' suggested `b6d0d53b` (7.5 km away, bearing
279°) precisely because that one would simply fail to match and test nothing.

| | real frames (8) | the board (impostor) | ratio |
| --- | --- | --- | --- |
| reprojection | **10.94 px** | **256.13 px** | **×23.4** |
| epipolar | **3.31 px** | **190.12 px** | **×57.4** |
| GPS residual | 0.3 m | 2.55 m | ×8.5 |
| correspondences to cluster | — | **1,012** | — |

**Verdict: `rejected`** — and every part of the chain behaved as the thesis says it should:

1. **Pairwise matching WAS fooled.** 1,012 confident correspondences between the board's printed
   skyline and the real skyline. This was not a "no-matches" non-test; the Doppelganger did its
   job.
2. **The GPS gate would NOT have caught it.** The board photo was taken standing at the lookout,
   so its camera centre is genuinely correct: 2.55 m of residual. That is 8.5× the real frames'
   0.3 m but *well inside phone-GPS noise* — nobody would flag 2.55 m. The drift gate twitches
   and shrugs.
3. **Global geometric consistency threw it out by 23–57×.** The matched points sit ~1 m deep in
   the board frame and kilometres deep in the vista frames; no single coherent solution holds
   both, so the impostor's reprojection explodes while the real frames stay at 10.9 px.

The per-pair view shows the same thing as a *signature* rather than a scalar: pair 8→6 is wrong
by 1,487 px over **349 correspondences** — thick and confidently wrong, which is exactly the
false-link fingerprint the min-correspondence filter exists to isolate (the neighbouring 7↔8
pairs at ~1,400 px over 4 correspondences are noise by comparison and would be filtered out).

So the anti-Doppelganger argument that motivated the whole reconstruction turn is no longer an
argument. It is a number, on the most adversarial impostor available, in a case the previous
metric would have passed.

**Confirmed under full-strength pairing, and a caution about the ratio.** The same cluster re-run
with `pairs: "complete"` (72 directed pairs; the impostor now meets *every* real frame rather
than the window's tail) reaches the same verdict:

| | swin-4 (52 pairs) | complete (72 pairs) |
| --- | --- | --- |
| real reproj / epipolar | 10.94 / 3.31 px | 17.44 / 4.72 px |
| impostor reproj / epipolar | 256.13 / 190.12 px | 216.57 / 219.34 px |
| ratio | ×23.4 / ×57.4 | ×12.4 / ×46.5 |
| correspondences to cluster | 1,012 | **1,212** |
| verdict | rejected | **rejected** |

The impostor's own error barely moved (256 → 217 px). What changed is the **baseline**: complete
pairing adds far-apart real pairs (frame 0 against frame 7, seconds apart with large rotation)
that are genuinely harder, so the real frames' median rose from 10.9 to 17.4 px and the reproj
ratio fell from 23× to 12×. Read that as a warning about the statistic, not the finding: **the
ratio is only as stable as the baseline's pair composition**, so compare ratios only between runs
paired the same way. The verdict is robust; the number is not a physical constant. (The same
effect surfaces a real-real casualty: pair 1→7 is wrong by 1,774 px over 184 correspondences —
distant pairs within the real cluster are themselves poorly solved, which is the localized-tail
story again.)

### The board IS a flat plane — but the "deep vista" was never there (2026-07-29)

The pair metric says the board was rejected; it cannot say what geometry the solver gave it.
Unprojecting the Doppelganger run's per-pixel depth and RANSAC-fitting a dominant plane per
frame answers the other half, and gives one clean result plus one uncomfortable one.

| | depth p50 | p90 | spread p90/p10 | on one plane | plane at |
| --- | --- | --- | --- | --- | --- |
| **board (impostor)** | 2.0 m | 3.0 m | **×1.5** | **54%** | 1.8 m |
| real frames (median of 8) | 1.7 m | ~21 m | ×20 | 31% | ~1.1 m |

**The board reconstructed as a near, tight, coplanar patch** — depth spread ×1.5 against the
real frames' ×20, more than half its pixels on a single plane 1.8 m away, RMS 2 cm to that
plane. So the June prediction was right about the board: MASt3R saw a flat panel, not the scene
printed on it. The depth estimator was *not* fooled the way the June depthmaps suggested.

**But the vista in this reconstruction has no depth at all.** Not one pixel in any of the nine
frames exceeds 100 m; the whole solve tops out at **62 m**, for a viewpoint whose subject is
Prague landmarks kilometres away. And the reason is not a model failure — it is geometry:

- The eight real cameras span a maximum baseline of **1.47 m** (median pair 0.63 m). These are
  pan frames: the photographer stood at the railing and rotated. **You stand still to photograph
  a vista**, and standing still is the same thing as having no baseline.
- With f ≈ 388 px and B = 1.47 m, one pixel of disparity error costs `z²/(f·B)`: ±4% at 25 m,
  ±18% at 100 m, **±175% at 1 km**. The 20 %-error horizon is **114 m**.

Note carefully which failure this is. The solve did **not** over-claim: its 62 m ceiling sits
*inside* its own 114 m horizon, so MASt3R never pretended to measure kilometres. It
**under-reported** — the subject is kilometres away, the honest horizon is 114 m, and everything
past it was compressed into the near field. That asymmetry matters for tooling: a
baseline-vs-reported-depth guard (now in recon_metrics as `depth_horizon`) catches a solve
claiming *more* depth than its geometry supports, but nothing about this run's numbers looks
wrong from the inside. The number to compare against is the **subject's** distance, which only
the person choosing the cluster knows.

So the board rejection is real, and the plane is real, but it must **not** be described as
"flat plane versus deep vista" — the contrast measured is a plane at 1.8 m against shallow
structure out to 62 m. The advertised demo cannot be produced from a vantage point at all, and
that is a permanent property of vantage points, not a tuning problem: at a 5 m baseline the
20 %-horizon only reaches 388 m, and hundreds of metres of walking would change or lose the very
vista being photographed.

**Depth reach, measured across every run.** `recon_metrics` now reports `depth_horizon` —
recovered baseline, the 20 %-error horizon `0.2·f·B`, the depth the solve actually claims, and the
recovered-vs-GPS spread ratio. (Unit trap worth knowing: metadata's `scale_units_per_m` is the
Umeyama scale mapping scene → ENU, i.e. metres *per unit* despite the name. Multiply. Dividing it
inflated masktest's 1.28 m baseline to 24 m and briefly invented a spectacular fake "collapse
detector".)

| run | baseline | horizon | claims depth to | recovered/GPS | reproj |
| --- | --- | --- | --- | --- | --- |
| masktest | 1.28 m | 100 m | 15.8 m | 1.04 | **0.71 px** |
| board_sweep | 28.6 m | 2255 m | 243 m | 0.80 | 0.94 px |
| walk_jizni | 70.4 m | 5505 m | 234 m | 0.68 | 1.96 px |
| walk_dense | 70.0 m | 5490 m | 367 m | 0.98 | 2.55 px |
| bench-smoke5 | 10.1 m | 753 m | 83 m | 0.96 | 11.0 px |
| doppelganger-board | 1.48 m | 115 m | **62 m** | 0.87 | 11.9 px |
| doppelganger (complete) | 1.35 m | 100 m | **79 m** | 0.79 | 18.0 px |
| walk_sparse | 188 m | 15278 m | 1203 m | 0.59 | 77.2 px |

Two things to take from it, and one non-finding:

- **A small baseline is not inherently bad — it is just short-reach.** masktest has the *smallest*
  baseline (1.28 m) and the *best* structure on disk (0.71 px), because its content sits at 16 m,
  comfortably inside its 100 m reach. Baseline sets how far you can see, not how well.
- **Quality degrades as content approaches the horizon.** The two board runs are the only ones
  whose claimed depth is a large fraction of their own reach (62/115 = 0.54, 79/100 = 0.79), and
  they are the worst non-broken solves (11.9 and 18.0 px). Everything scoring under 3 px sits at
  ≤0.13 of its horizon.
- **Non-finding: the recovered/GPS spread ratio does not separate good from bad.** It ranks
  plausibly (walk_sparse lowest at 0.59, walk_dense 0.98, masktest 1.04) but walk_jizni is a fine
  1.96 px solve at 0.68, right beside walk_sparse. It is reported as a prompt to look, not a
  verdict — and no archived run trips the 0.5 threshold. Good reach never guarantees a good solve
  either: bench-smoke5, walk_sparse and board_jan all fail for unrelated reasons (too few frames,
  lost overlap, degenerate 3-view geometry).

**Architectural consequence.** Distant structure from a viewpoint is not recon's job, and the
workbench already owns the two tools that are: the **terrain bench** (DEM-rendered depth
panoramas — correct by construction at any range) for far-field depth, and **triangulation**
(rays from widely separated viewpoints) for distant POIs. Recon covers the near field, and we now
know where the seam is: ~100 m for a hand-held pan, ~400 m for a walked 5 m baseline. Pointing
recon at a vista and expecting kilometres was the mistake; the "GPS-cluster fuse at the lookout"
thread inherits this limit and should be reframed accordingly.

*(Caveat on the metres: `scale_units_per_m` is fit over 1.5 m of camera spread, so the absolute
metre values are weakly constrained. Every claim above that matters is a ratio — depth spread,
plane fraction, relative uncertainty — and those are scale-invariant.)*

### The tail is a focal problem, and it has a one-flag fix (2026-07-29)

Having localized each run's warped minority to specific frames, the obvious next question is what
those frames have in common. Scoring every frame on four candidate explanations — focal deviation
from the cluster median, focal movement away from the canonical prior, rotation to its neighbours,
and depth coverage — against its own reprojection error:

| run | focal deviation | focal vs prior | rotation to neighbours | depth coverage |
| --- | --- | --- | --- | --- |
| walk_jizni | **+0.54** | +0.28 | +0.01 | −0.11 |
| walk_dense | **+0.41** | +0.04 | −0.20 | +0.02 |
| board_sweep | +0.05 | +0.13 | **+0.46** | −0.31 |

(Spearman rho against per-frame reprojection error.)

**Focal deviation is the dominant signature in the walks.** walk_dense's worst frame carries a
focal of **571 px against a 392 px cluster median** (reproj 91.8 px); walk_jizni's worst is
**165 px against 391** (reproj 709 px). In the fast-panning board_sweep the leading term is
inter-frame rotation instead, which fits a sweep where consecutive frames barely overlap.

**Looking at the actual frames explains the mechanism.** walk_dense frame 4 (focal 571) is a
downward shot of **blank motion-blurred pavement**; frame 20 (focal 300) is two-thirds **grass**
with the far scene a thin strip at the top; the best frame (0.7 px, focal 396) is a receding street
with a lamp post, buildings and sky — structure at many depths. A frame filled by a single
textureless fronto-parallel surface cannot constrain focal (focal and depth trade off against each
other there), so the optimizer lets it wander, and the wandering focal wrecks that frame's
geometry. This sharpens June's note that outlier focals were "globally rescued": the *pose* is
rescued, the *structure* is not.

**The fix is right, but not for the reason the numbers first suggested.** Every one of these
clusters is one phone, one lens, one walk, so the focal is physically constant and
`shared_intrinsics=True` is simply the true model. reconstruct.py had it hardcoded off; it is now
`--shared_intrinsics`, plumbed through the API whitelist and the worker, and **on by default** for
single-camera clusters. The A/B on the smoke5 cluster — same 5 frames, one knob:

| | per-frame focals | one shared focal |
| --- | --- | --- |
| reproj median | **11.02 px** | 14.74 px |
| reproj p90 | 227.7 px | **178.9 px** |
| epipolar median | **4.11 px** | 4.61 px |
| GPS residual | **0.39 m** | 0.81 m |
| per-frame focals | 360, 376, 373, 391, **151** | 383 × 5 |
| per-frame reproj | 19.0, 3.7, 1.0, 3.2, **160.9** | 35.4, 8.1, 1.2, 6.7, **152.9** |

Sharing the focal did exactly what it should mechanically — the pavement frame's focal went from a
nonsense 151 px to the cluster's 383 px — while the median rose and p90 fell.

**Read that as the constraint working, not failing.** A per-frame focal is a free parameter the
optimizer uses to *absorb* error: given a frame it cannot otherwise fit, it can always lower that
frame's reprojection by inventing a lens. 151 px on a 512-frame is a **119° fisheye**; 571 px is a
**48° telephoto**; the phone is neither, and the same photo gets 571 inside walk_dense and 151
inside smoke5. Those are not measurements, they are a residual sink. So the "better" free-focal
median was partly bought with an impossible camera — lower error from a model with extra
*unphysical* degrees of freedom is overfitting, and comparing the two medians directly is not
apples to apples. Constrain the lens to what the hardware is and the residual surfaces where it
belongs; p90 improving (228 → 179) is the honest half of the trade, because worst-case geometry got
genuinely better once no single frame could cheat.

So `shared_intrinsics` ships **on by default** for single-camera clusters, which is what it always
physically was. Two caveats stay attached: it must not be set on a mixed-source cluster (the preview
checks and the form warns), and the underlying frame is still bad — its *content* cannot support
geometry, and no intrinsics constraint fixes blank blurred pavement. The rho +0.4/+0.5 correlation
remains a useful **marker** for finding suspect frames; dropping or down-weighting content-free
frames is the actual fix, and the per-frame table now identifies them.

**Deciding "one camera" — use the client key, not a proxy.** Three tiers, best first:
EXIF `Make`/`Model`/`LensModel` (authoritative but present on only ~12% of the mirror, because the
app re-encodes its own uploads and strips camera tags — `DeviceModel` comes back empty);
**`client_public_key_id`**, the uploading device's public-key fingerprint, which is **100% populated
in production** (28,323/28,323 rows, 1,424 distinct keys) and is genuinely per-*device* where
`owner_id` is per-*account* (one account, several phones); then owner + frame dimensions as the
fallback. Frame dimensions fold into every tier, since the same phone switching to its ultra-wide
lens is a different focal. The key is now mirrored (`009_photo_client_key.sql`, added to
`PHOTO_PLAIN`); rows mirrored before it stay NULL until a reconcile re-reads them, which is why the
fallback exists. Capture-time span is reported alongside (`same_session`) because frames minutes
apart from one device are one lens setting, while the same device months apart may have been
re-zoomed — corroborating, so not folded into the boolean, since a deliberate cross-date fuse of one
camera is still one camera.

Where EXIF *does* survive there is no need to solve for the focal at all: `FocalLength35efl` gives
it directly (f_px = f35 × long_side / 36), and the preview now reports it.

### And with shared intrinsics the solved focal matches EXIF to 3.9%

The DSLR uploads make the decisive test possible, and it was run. Cluster `dslr-focal-truth`: 8
frames from a Canon EOS 5DS + EF16-35mm at ~15.6 mm, one afternoon, 2.3 m of camera spread —
**EXIF ground truth 222 px** on the 512-long-side frame the solver works on.

| | value |
| --- | --- |
| EXIF focal (ground truth) | **222 px** |
| solved focal, `shared_intrinsics` | **230.6 px** |
| error | **+3.9%** |
| reprojection median | **0.78 px** (2nd best solve on disk) |
| baseline / horizon / claimed depth | 2.29 m / 105 m / 82 m |

Set that beside the free-focal behaviour on the phone walks, where *the same photograph* was
solved at 571 px in one cluster and 151 px in another — +46% and −61% against the cluster
consensus, i.e. a 48° telephoto and a 119° fisheye for one phone. Constrained, the estimate lands
within 4% of what the camera itself recorded; unconstrained, it is a residual sink. That is
independent confirmation, from a camera that wrote down the answer, that sharing intrinsics is the
right model and that the earlier "shared_intrinsics made the median worse" reading was measuring
overfitting rather than accuracy.

(Caveat: this cluster's frames differ in dimensions by ~0.6% from per-shot lens correction, so
`uniform_capture` is False for it and the single shared value is itself a small approximation —
some of the 3.9% may be that rather than solver error.)

### Deciding "one camera": three axes, not one

What produces the pixels is the camera **and the pics pipeline**, whose lens-geometry correction
has changed over time — so a change in frame dimensions signals a change in effective intrinsics
even from the identical body, and exact equality is the right test rather than a tolerance. The
preview therefore reports three axes separately, and `uniform_capture` is their conjunction:

- **same camera** — EXIF `Make`/`Model`/`LensModel`, else `client_public_key_id`, else `owner_id`.
- **same dimensions** — exact.
- **same day** — the processing-stability window: a series shot in one day can be trusted to have
  had the same processing applied.

`client_public_key_id` is the uploading device's key fingerprint and is the load-bearing tier for
app photos: **100% populated in production** (41,906 rows, 1,806 distinct devices) and genuinely
per-*device*, where `owner_id` is per-*account*. It proved its worth immediately — the January
board photo and the June walk share an owner, so the owner-based proxy called them one camera,
while the client key correctly reports two devices. Mirrored via `009_photo_client_key.sql` +
`PHOTO_PLAIN`; adding a column does not backfill through reconcile (the source row-hash is
unchanged), so existing rows were filled by a targeted update.

> Dev-sync gotcha worth keeping: the mirror holds 41,908 rows and `photos_1.csv` only 28,458, so
> seeding from the wrong dump makes reconcile stamp ~13.4 k rows `missing_since` — which silently
> removes a third of the photo pool from every bench that filters on it. `photos_3.csv` (41,908
> rows) is the one that matches; with it, reconcile stamped **0** missing and changed 41.

### The 3-D viewer (2026-07-29)

`/recon` now has an orbitable point cloud with **camera frusta drawn from the solved poses** — the
thing the old viz_app viewer lacked, and the thing that makes a bad solve legible at a glance: a
collapsed run shows its cameras piled together, an impostor (amber) sits where the real ones do
not. Sparse/dense toggle per run.

The format matters. reconstruct.py writes ASCII PLY, which is ~65 MB for a 715 k-point sparse
cloud and hundreds of MB dense — not openable in a browser. The API converts to packed
`[float32 x,y,z][uint8 r,g,b]` (15 bytes/point vs ~90) on first request and caches it beside the
artifact, with a `max_points` cap applied by even stride so a downsampled cloud still spans the
whole scene. Frusta come from `metadata.json`'s `pose_cam2world` (scene.npz is not uploaded).

## Open threads / next experiments

- **What is the warped tail made of?** ✅✅ **Answered, and it has a fix.** See "The tail is a
  focal problem" below. First half below:
  **the tail is localized, not diffuse**. Filtering the per-pair table to pairs with ≥1000
  correspondences (so a wild error can't just be a thin pair) leaves a handful of culprits, and
  they cluster on specific frames: board_sweep's worst thick pairs are all *frame 27*
  (28→27, 29→27, 27→28, 30→27, 230–382 px); walk_dense's are frames 9–13 (11→9 at 1094 px over
  3511 correspondences); walk_jizni's are 36–39 and 64–66. Roughly 10% of thick pairs exceed
  100 px in each run. So the work is now "find the bad frames", not "make it solve" — go look at
  those specific crops, and consider whether the solver should down-weight or drop them.
- ~~**Board test**~~ ✅ **CLOSED (2026-07-29).** The board is rejected by 23–57× when injected
  into a real-vista cluster, *and* it reconstructs as a coplanar patch at 1.8 m (spread ×1.5,
  54% on one plane) — so the depth estimator was not fooled by the printed content. What died
  with it is the framing: there is no "deep vista" to contrast against, because a vantage point
  supplies no baseline (1.47 m here; 114 m honest depth horizon). Don't re-run this hoping for
  kilometres.
- **Prosek-Rocks GPS-cluster fuse, reframed.** The cross-date vantage fuse (`bearing`/complete
  pairing, `deleted` filtered) will *not* recover distant structure — same no-baseline problem as
  above, now quantified — so run it for the question it can actually answer: do cross-season
  frames of the same place register with each other at all? Far field stays with the terrain
  bench.
- ~~**`--inject` Doppelganger test**~~ ✅ **DONE** — see the board result above. `b6d0d53b` was
  the wrong impostor for it (7.5 km away, would never match); the printed board was the right one.
- ~~**eyeball `walk_jizni`**~~ ✅ measured instead: 1.96 px median, the second-best real solve on
  disk, with its tail localized to frames 36–39 and 64–66.
- **Walk → world merge** (the big one): submap pose-graph + verified loop closures. The retrieval +
  consistency-check machinery is the gate — and the per-pair reprojection metric is now that
  machinery's verification signal: a false loop closure is a thick pair that is confidently wrong,
  which is exactly what the board impostor looked like (1,487 px over 349 correspondences).
- **Where recon stops and terrain starts.** Depth uncertainty is `z²/(f·B)`, so the honest horizon
  is ~100 m for a hand-held pan and ~400 m for a walked 5 m baseline. Anything beyond that should
  come from the DEM (terrain bench) or from triangulation across widely separated viewpoints, not
  from asking SfM for it. Worth encoding as a guard in the bench: warn when a cluster's recovered
  baseline is too small for the depths its own solve is reporting.
- Eventually: pano source-frame ingestion + `.pto` cross-check; corpus-scale fusion + splats on GPU.

> Methodology note from this session: **don't over-read the GPS residual**, and verify findings by
> eyeballing the actual structure (viewer/depthmaps) — several "good number" claims (the masking A/B,
> the contiguous walk) did not survive visual inspection.

> Methodology note, 2026-07-28: the eyeball beat the number again, and then the number explained the
> eyeball. Both June "failures" that visual inspection flagged were real — but not as
> "it didn't solve": the solves are locally excellent with warped tails. Meanwhile every *metric*
> we reached for first was wrong in a way that looked plausible: the GPS residual (ranks the worst
> run best), MASt3R's printed loss (same), the epipolar distance (blind along its own lines), and
> our own first reprojection numbers (inflated 5× by a principal point nobody had saved). Each was
> caught by a cheap consistency check — a synthetic scene with known error, a gauge-invariant
> comparison, a coverage count. Build the check before trusting the number.

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

## Open threads / next experiments

- **Surface a structure-quality metric** (MASt3R-SfM 2-D reprojection error) — the GPS residual is
  only a drift gate; we need a GPS-independent quality number before trusting any "it solved" claim.
- **Board test, properly powered** — more board-facing baseline; does the flat plane separate from
  the deep vista, or does the printed-content depth hallucination dominate?
- Prosek-Rocks **GPS-cluster** reconstruction (exhaustive/`bearing` pairing, `deleted` filtered) —
  the cross-date vantage fuse, distinct from the same-day walk-end sweep already run.
- The deliberate **`--inject` Doppelganger test** (e.g. `b6d0d53b` into a coherent cluster; alignment
  fit on real frames only, so the impostor can't corrupt it).
- `walk_jizni` (fresh 2026-06-16 dense walk, `/shared/photos_1.csv`, `--mask_solocator`) — eyeball
  it; another submap candidate.
- **Walk → world merge** (the big one): submap pose-graph + verified loop closures. The retrieval +
  consistency-check machinery is the gate.
- Eventually: pano source-frame ingestion + `.pto` cross-check; corpus-scale fusion + splats on GPU.

> Methodology note from this session: **don't over-read the GPS residual**, and verify findings by
> eyeballing the actual structure (viewer/depthmaps) — several "good number" claims (the masking A/B,
> the contiguous walk) did not survive visual inspection.

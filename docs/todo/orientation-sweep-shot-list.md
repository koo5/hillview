# One orientation shoot, so it is not shot again

Planned 2026-10-10 for a single session with `b1ad5e00` or later, where an IMU
window is self-contained (`accel`, `gyro`, `rv`, `mag`, `pose`, `decide` — see
`ImuSampleEntity`'s payload doc). Sub-second interval mode throughout, so the
windows effectively tile and nothing between shutters is lost.

## What needs a VISUAL reference, and what does not

Gravity is silent about azimuth. That one fact decides the whole plan.

- **Pitch and roll need no site at all.** `accel` gives an unambiguous down and
  `gyro` the true angular rate, both independent of the fused attitude under
  suspicion. Any view with a vertical edge in it is enough, and the window
  already carries the arbitration.
- **The azimuth cannot be arbitrated by any sensor in the phone.** The only
  candidate is the magnetometer, which is the suspect input. So the bearing's
  ground truth has to come from the WORLD — from identifying what is in the
  frame and knowing where it is.

Everything below therefore spends its effort on azimuth and treats pitch/roll as
a free rider.

## The site: Prosek Rocks lookout, not a street

`Vyhlídka Prosecké skály`, ~50.1169, 14.4884 — the project's existing anchor
vantage (see the Prosek board notes and the annotated panorama `333e8851`).

Why it beats a square or a boulevard:

- **The landmarks are kilometres away.** Position error stops mattering: at 300 m
  a metre of GPS error is 0.19° of bearing, at 8 km it is 0.007°. A street canyon
  puts its sharp features at tens of metres, where the same error is degrees —
  the size of the thing being measured.
- **The ground truth is already written down.** The metal board's legend names
  the landmarks (O2 Arena, Pankrác, Balabenka, Plynojem Palmovka, …), each of
  which has a known position, so the true bearing of a centred landmark is a
  two-point calculation rather than a photogrammetry problem.
- **Azimuth spread**, which a canyon cannot give: it offers two usable bearings,
  up the street and down it. Shape needs a circle.
- It joins ~114 existing photos across 6+ dates at that vantage.

Bring the centre mark (📷 → Centre mark → Shown, default on since `46945829`).

## The shape question the azimuth map has to settle

There is an unresolved contradiction in what we know about the
landscape-above-horizon mirror:

- correcting the azimuth as `b → 360 − b` on `pitch < 0` reduced the worst step
  across one sweep from 109.4° to 15.7°, which is why it ships;
- but the same session reported "the rest of the sphere seems fine", and a pure
  mirror about the north–south axis is only harmless at exactly 0° and 180°. At
  30° it would be 60° wrong, at 90° it is 180° wrong.

Both cannot be true of a global mirror. Either the earlier "fine" sampled only
near north and south, or the fault is not the mirror we are correcting for. An
azimuth map with real bearings decides it, and nothing else does.

## The sequence

Stand in ONE spot for the whole session and do not move between frames.

**1 — the azimuth map, as PAIRS.** The mirror lives above the horizon, but the
landmarks that establish a bearing are at or below it. So shoot two frames per
azimuth and do not turn between them:

   a. landmark centred on the reticle — this frame carries the TRUE bearing;
   b. tilt up ~20° without turning — same true bearing, now in the faulty regime.

Work round the available view in ~30° steps, and **include the azimuths nearest
north and south**: those are where a mirror hides, so they are what confirms its
shape rather than merely its amplitude.

**2 — roll sweeps**, at three azimuths from step 1 (one near north or south, two
near east or west). Landmark centred, roll in steps `0, ±10, ±20, ±45, ±90`, 2–3
frames per step, at two pitches: ~10° BELOW the horizon (the mirror correction
off) and ~20° ABOVE (on). Not level — `pitch < 0` is the switch, and a level
sweep straddles it.

**3 — steady landscape holds**, ~30 s each at two azimuths, phone as still as
possible. The 180° branch flip appears on steady holds (6 of 100 captures), and
sub-second interval will catch it flipping in `rv`, `pose` and `decide` while
nothing physical moves.

**4 — a portrait control** at each azimuth of step 1. Portrait is the regime
reported as always having worked; without it there is no baseline to say what
"working" looks like in this dataset.

**5 — a few frames with the board itself in view**, for the existing
reconstruction work at this vantage.

## What a frame has to carry for this to be readable afterwards

All of it is automatic on `b1ad5e00`, listed so a gap is noticed in the field
rather than at the desk:

- `attitude.rotation_vector` + `matrix_determinant` + `bearing_reference` +
  `bearing_conditioning` + `branch_corrected` + `azimuth_mirrored`;
- `inertial.gravity`, for the independent pitch and roll;
- `imu_samples_url`, with all six kinds;
- `lens.focal_length_mm` and `sensor_physical_size_mm`, which turn a pixel offset
  into an angle for any landmark that is not exactly centred (`intrinsics_available`
  is false, so this is a pinhole approximation — good to a fraction of a degree
  near the centre, which is why centring still matters);
- `capture_timing.metadata_version` 2, and `build`.

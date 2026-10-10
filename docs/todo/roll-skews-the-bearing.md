# Does roll skew the bearing, and is there one rule that covers it?

Parked 2026-10-10, straight after the two landscape faults were corrected
(`CameraPose.withBranchCorrected` / `withMirroredAzimuth`). Next effort, not
part of that one.

## The observation (user, on the phone, not yet measured)

> this is immediately visible even in portrait mode: in a few degrees of roll it
> bears on the bearing. And in landscape mode not only it bears on the bearing,
> but there is also still the flip behaviour controlled by tilt. So the question
> could be whether there is some universal logic that would accommodate the roll.

Two parts, and they are probably not the same thing:

1. **A few degrees of roll in portrait moves the reported bearing.** Small roll,
   near-level pitch — the easy, well-conditioned corner of the sphere.
2. **In landscape the bearing still moves with roll**, on top of the
   tilt-controlled flip that `withMirroredAzimuth` now corrects on `pitch < 0`.

## What we already know, structurally

`pointingBearingDeg` is the azimuth of the lens vector, and the lens vector is
`−R[*,2]` — the third column of the device→world matrix. **Rolling the phone
about its optical axis does not move its optical axis.** So in the geometry as
written, a pure roll cannot change the bearing. That is not a hope, it is the
construction, and `CameraPoseTest` sweeps it: `poseFor(az, el, roll)` holds the
bearing fixed across roll.

So a roll-dependent bearing has to come from somewhere else. The candidates, in
the order they are worth testing:

- **The HAL's attitude is itself roll-dependent.** `TYPE_ROTATION_VECTOR` is
  fused, and this device has already been caught producing two faults in it (a
  180° branch in level landscape, an azimuth mirror above the horizon). A
  magnetometer whose calibration is wrong in the device frame skews the fused
  azimuth as the phone rotates relative to the field — and that *would* show up
  at a few degrees in portrait. Check `det` and the raw `rv` quaternion in the
  frame probe, not just our derived numbers.
- **Our roll-weighted fallback.** `fallbackWeight = (1 − w) · |cos(imageRoll)|`
  blends the top edge in when the lens goes vertical. Near-level portrait should
  have `w ≈ 1` and so no fallback at all — confirm that from
  `horizontalLength` / `bearing_reference` in the probe before suspecting it.
  If `w` is not ≈ 1 there, the conditioning constants are wrong, not the blend.
- **The consumer, not the sensor.** The overlay arrow and the stamped
  `attitude.bearing` come from the same `pointingBearingDeg`, but the overlay
  also rotates with the device. A roll-dependent *arrow* with a roll-invariant
  *stamp* would move this out of `CameraPose` entirely.

The "universal logic" the user asks about is only findable once we know which of
those three it is: a HAL skew wants a calibration or a raw-sensor path, a
conditioning bug wants new constants, an overlay bug wants neither.

## 2026-10-10, before any sweep: one cause found and fixed

The user reported the ROLL READOUT itself non-monotonic — rotating portrait →
landscape below the horizon it read 0, −10, then jumped to +110 and came down to
+90 — and wrong whenever the camera looked below the horizon.

That is `−70+180`, `−80+180`, `−90+180`: the 180° branch correction firing on a
healthy attitude. Two code facts made it:

- `OrientationEventListener` returns `ORIENTATION_UNKNOWN` when the phone is near
  flat, which pitched down IS. `fromDegrees` maps that to `FLAT_UP` and
  `toDegrees(FLAT_UP)` is **0** — the same value as `PORTRAIT`. So the class said
  "portrait" for "I don't know", `expectedLandscapeRollSign()` flickered between
  ±1 and 0 as the phone tilted, and the correction flickered with it.
- The `abs(roll) > LANDSCAPE_ROLL_DEG` gate put a step at exactly 60°, which is
  where the jump appeared.

The detector now asks GRAVITY instead: `atan2(g_x, g_y)`, the identity `roll_deg`
is documented to satisfy, from the accelerometer — a different stream from the
fused rotation vector and therefore able to judge it. On 100 consecutive prod
captures, 94 rows agree with gravity to within 15° and 6 are 173–175° off, with
nothing in between, so the 90° threshold sits in a 160°-wide empty band. The old
sign table scored 6/6 with no false positives on those same rows, so what was
wrong with it was its INPUT, not its logic — it is kept as
`onWrongAttitudeBranchByOrientationClass` with that written down.

What this buys beyond the fix: the test is continuous (no 45° buckets, so nothing
to flicker), needs no step in the roll, and works at every roll and pitch the
conditioning allows — including mid-roll around 40° and pitched steeply down,
both of which the old gate could not reach. `GRAVITY_ROLL_FLOOR` declines within
~15° of flat, where gravity has no in-plane direction, rather than guessing.

**NOT phone-verified.** The mechanism explains the report exactly and the maths is
pinned by a 3 000-pose sweep asserting a self-consistent attitude is never called
wrong-branch, but nobody has rotated a phone with this build yet. If the roll is
still non-monotonic, the remaining suspect is the HAL's own fused roll, and
`attitude.branch_corrected` on a captured frame now says whether our correction
was involved at all.

## The measurement that would settle it

Two sweeps, and from 2026-10-10 the photos carry everything needed to read them —
`attitude.rotation_vector`, `matrix_determinant`, `bearing_reference`,
`bearing_conditioning`, `camera_bearing_deg`, `device_bearing_deg`,
`branch_corrected`, `azimuth_mirrored`, beside the heading, pitch, roll,
`device_rotation_deg` and `motion.gravity` that were already there. No cable, no
log probe: fetch the sweep from the timeline API and the analysis is arithmetic.
Frames are `capture_timing.metadata_version` 2.

**Centre one distant landmark in every frame.** The lens axis lands on the
landmark however the phone is rolled, so the landmark IS the ground truth for the
true bearing. Without it a handheld sweep cannot separate "the bearing skewed"
from "I turned slightly while rolling", and that confound is fatal to the whole
measurement. Distant matters — a near object changes bearing when the feet move.

**Pitch: off the horizon, not on it.** The mirror correction switches on
`pitch < 0`, so a level sweep straddles the branch it is meant to hold still. One
sweep ~10° BELOW the horizon (correction off), one ~20° ABOVE (correction on).

**Roll: signed, both directions.** The branch detector keys on the roll sign
against gravity, so +45° and −45° are different experiments: `0, ±10, ±20, ±45,
±90`. The ±10 step is where the user reports seeing it in portrait, so it is the
one not to skip. ±20 is the first to drop if the set gets tedious.

**2–3 shots per step.** The HAL flips branch on a steady hold; one shot per step
cannot distinguish a roll skew from a flip that happened between two shots.

Then plot reported bearing against roll, per sweep:

- Flat → the stamp is fine and the problem is downstream, in the overlay.
- Tracks roll → recompute the lens azimuth from `rotation_vector` directly. If
  the raw quaternion's azimuth tracks roll too, it is the HAL; if it does not, it
  is our arithmetic, and `bearing_reference` plus `bearing_conditioning` say
  whether the fallback blend was involved.
- `branch_corrected` / `azimuth_mirrored` make each row self-describing, so a
  corrected frame never has to be told from an uncorrected one by eye again.

Mid-roll (~40°) is the gap both existing corrections deliberately leave alone
(`LANDSCAPE_ROLL_DEG = 60f`), so that step is the interesting one for the
combined question.

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

## The measurement that would settle it

The same instrument that settled both landscape faults — the `[frame-probe]`
block in `EnhancedSensorService`, which is why it is still in the build.

Hold one bearing and one pitch, vary **only** roll in steps (0°, 10°, 20°, 30°,
45°, 60°, 90°), and read off per step: `bearing`, `pitch`, `roll`, `det`, the
lens `e/n/u` and the raw `rv`. Do it twice: near-level pitch, and ~20° above the
horizon. Then plot reported bearing against roll.

- Flat line → the stamp is fine and the problem is downstream (overlay).
- A line that tracks roll → read `rv`: if the raw quaternion's azimuth tracks
  roll too, it is the HAL; if it does not, it is us.
- Mid-roll (~40°) is the gap both existing corrections deliberately leave
  uncorrected (`LANDSCAPE_ROLL_DEG = 60f`), so that step is the interesting one
  for the combined question.

Captured photos carry all of this in `attitude.*` plus
`device_rotation_deg`, so a sweep uploaded from the field is analysable after the
fact via the timeline API — no cable needed, same as last time.

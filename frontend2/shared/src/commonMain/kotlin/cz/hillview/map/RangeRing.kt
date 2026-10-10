package cz.hillview.map

/*
 * Where each part of the one circle on the map sits, measured from the range
 * THRESHOLD: the radius at which a photo stops being in range.
 *
 * The user's rule (2026-10-10): "the circle should give users the exact
 * threshold of the range". So the circle IS the threshold — one thin solid
 * line — and nothing else drawn crosses it: the arrow's head rests on it
 * from outside, the bearing hold hugs it from inside.
 *
 * The head was first put just inside the line ("the bearing arrow should end
 * right inside it"), then, the same day, back where the original has it:
 * "my bad about the arrow, in the original, the arrow tip's base sits flush
 * on the threshold, lets copy that".
 *
 * There used to be a dashed band as well, Leaflet's `weight 8.8` with a 5/15
 * dash, centred on the range: the threshold was the invisible middle of an
 * 8.8 dp stripe that was mostly gaps, so a photo anywhere under it could be
 * in or out. It is not drawn any more (user, 2026-10-10: "the dashed band
 * really had no meaning that im aware of") — a divergence from the original,
 * whose dashed circle it was.
 */

/**
 * The circle, in dp: a solid line centred exactly on the range threshold.
 * Thin, so where it is can be read.
 */
const val RANGE_THRESHOLD_LINE_DP = 2f

/**
 * The arrowhead's length (and its width), in dp — base to tip.
 *
 * Smaller than the original's: its SVG marker is a 10×12 polygon in units of
 * the 3 px stroke, so 30 px long and 36 wide, with a red outline. This one
 * has been 11 dp since the port; only its PLACE is copied here.
 */
const val ARROW_HEAD_DP = 11f

/**
 * The bearing hold's stroke, in dp — the same while it charges and once it
 * is served. The ring CLOSING is what says the hold is served, with the buzz
 * and the arrow jumping to the finger.
 *
 * It used to thicken at that moment (3 → 5 dp from 2026-09-11, then 8.8 to
 * cover the dashed band, then 6), and nothing said why (user, 2026-10-10:
 * "its not clear why the blue circle thickens once the hold period
 * finishes"). Its last reason went with the band.
 */
const val BEARING_HOLD_DP = 3f

/**
 * Where the arrowhead's BASE sits: flush on the threshold line, resting on
 * its outer edge, so the head points out of the range and the line under it
 * stays whole.
 *
 * As the original has it, give or take two pixels: its line ends at
 * `range × 1.3` (91 px on the 70 px ring) and its head is anchored 27 px
 * back from there, which lands the base at 64 px — on the inner edge of its
 * 8.8 px dashed band (65.6 px), the edge that band showed. With the band
 * gone, the line is that edge.
 */
fun arrowHeadBaseRadiusPx(thresholdPx: Float, density: Float): Float =
    thresholdPx + RANGE_THRESHOLD_LINE_DP / 2f * density

/** Where the arrow's tip sits: one head length out from its base. */
fun arrowTipRadiusPx(thresholdPx: Float, density: Float): Float =
    arrowHeadBaseRadiusPx(thresholdPx, density) + ARROW_HEAD_DP * density

/**
 * The radius to draw the bearing hold's arc at: just INSIDE the threshold,
 * its outer edge on the line's inner edge. So it covers neither the line nor
 * the arrowhead resting on it from outside — only the shaft, which crosses
 * it anyway.
 */
fun bearingHoldRadiusPx(thresholdPx: Float, density: Float): Float =
    thresholdPx - (RANGE_THRESHOLD_LINE_DP + BEARING_HOLD_DP) / 2f * density

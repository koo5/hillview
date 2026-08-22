package cz.hillview.viewer

import cz.hillview.map.absBearingDiff

/**
 * The viewer pane's navigation, kept free of any drawing so it can be tested.
 * Ported from docs/tauri-viewer-ui-contract.md — read that first; this file
 * is the rules, not the reasoning.
 *
 * The pane is a DIRECTIONAL viewer, not a gallery: you stand where the map
 * says, face a bearing, and see the photo you are facing. So every function
 * here answers "what is in this direction from here", and the caller turns
 * the answer into a BEARING WRITE — navigating and turning are the same act.
 *
 * Everything below assumes [ring] is the in-range set already culled and
 * SORTED BY BEARING (ascending, uid as tiebreak) — shared-kt's
 * AngularRangeCuller and sortPhotosByBearing do that upstream, and both apps
 * share them. Left/right is index arithmetic on that order, so an unsorted
 * ring silently produces nonsense rather than an error.
 */

/**
 * The photos you may turn to, out of those in range.
 *
 * Two filters, in the original's order:
 *  - [overrideFilters] keeps everything; otherwise `filtered` photos go.
 *  - then, when hunter mode is OFF and anything featured is in range, ONLY
 *    featured photos remain. That is the surprising one: a single featured
 *    photo in range collapses the ring to the featured subset, which is the
 *    app quietly steering you at the good views unless you asked to hunt.
 *
 * "Anything featured" is `featured && !filtered` over the photos IN RANGE,
 * decided before the override rather than after it (mapState.ts:127-130). It
 * matters: a featured-but-filtered photo must not become a featured set just
 * because the user overrode the filters, which is what computing it from the
 * post-override list would do.
 *
 * Photos without a bearing are dropped: they cannot be placed in a ring
 * whose whole order is bearing.
 */
fun <T> navigablePhotos(
    inRange: List<T>,
    hunterMode: Boolean,
    overrideFilters: Boolean,
    filtered: (T) -> Boolean,
    featured: (T) -> Boolean,
    bearing: (T) -> Double?,
): List<T> {
    val withBearing = inRange.filter { bearing(it) != null }
    val anyFeatured = withBearing.any { featured(it) && !filtered(it) }
    val navigable = if (overrideFilters) withBearing else withBearing.filterNot { filtered(it) }
    return if (!hunterMode && anyFeatured) navigable.filter { featured(it) } else navigable
}

/**
 * The photo you are facing.
 *
 * [stickyUid] is the photo we last deliberately turned to. It wins only
 * while the view has not moved off it (bearing difference exactly 0) — which
 * is what makes a chosen photo STAY chosen when several share a bearing,
 * instead of the id tiebreak silently reclaiming it. Once the bearing moves
 * at all, the ordinary nearest-bearing rule takes over again.
 *
 * Otherwise: smallest absolute bearing difference, uid as tiebreak so the
 * choice cannot flip between equally-good candidates.
 */
fun <T> viewerFrontPhoto(
    ring: List<T>,
    viewBearing: Double,
    stickyUid: String?,
    uid: (T) -> String,
    bearing: (T) -> Double,
): T? {
    if (ring.isEmpty()) return null
    if (stickyUid != null) {
        val sticky = ring.firstOrNull { uid(it) == stickyUid }
        if (sticky != null && absBearingDiff(bearing(sticky), viewBearing) == 0.0) return sticky
    }
    return ring.minWithOrNull(
        compareBy<T> { absBearingDiff(bearing(it), viewBearing) }.thenBy { uid(it) },
    )
}

/**
 * The next photo round the ring: [step] -1 for left, +1 for right.
 *
 * Modulo the ring length, so turning past north keeps going rather than
 * hitting a wall — the ring is a compass, not a list. Null when there is
 * nothing to turn to: an empty ring, a single photo (you are already looking
 * at it), or a front photo that has fallen out of range since it was chosen.
 */
fun <T> ringNeighbour(
    ring: List<T>,
    front: T?,
    step: Int,
    uid: (T) -> String,
): T? {
    if (front == null || ring.size < 2) return null
    val index = ring.indexOfFirst { uid(it) == uid(front) }
    if (index == -1) return null
    val next = ((index + step) % ring.size + ring.size) % ring.size
    return ring[next]
}

/**
 * The photo above or below: same view direction, different elevation.
 *
 * "Same direction" is within [bearingWindow] degrees of the front photo's
 * bearing — you are looking the same way, just up or down. Pitch must be
 * STRICTLY greater (up) or smaller (down), and the winner is the most
 * extreme, so repeated swipes climb rather than oscillate. A missing pitch
 * counts as 0.
 *
 * [alsoReachableAs] suppresses the answer when it is already the left or
 * right neighbour: one photo must not occupy two slots, or a swipe up and a
 * swipe right would land in the same place and the pane would look broken.
 */
fun <T> pitchNeighbour(
    ring: List<T>,
    front: T?,
    up: Boolean,
    alsoReachableAs: List<T?>,
    uid: (T) -> String,
    bearing: (T) -> Double,
    pitch: (T) -> Double?,
    bearingWindow: Double = 5.0,
): T? {
    if (front == null || ring.size < 2) return null
    if (ring.none { uid(it) == uid(front) }) return null

    val frontPitch = pitch(front) ?: 0.0
    val frontBearing = bearing(front)
    var winner: T? = null
    for (candidate in ring) {
        if (uid(candidate) == uid(front)) continue
        if (absBearingDiff(bearing(candidate), frontBearing) > bearingWindow) continue
        val candidatePitch = pitch(candidate) ?: 0.0
        val better = if (up) {
            candidatePitch > frontPitch && candidatePitch > (winner?.let { pitch(it) ?: 0.0 } ?: Double.NEGATIVE_INFINITY)
        } else {
            candidatePitch < frontPitch && candidatePitch < (winner?.let { pitch(it) ?: 0.0 } ?: Double.POSITIVE_INFINITY)
        }
        if (better) winner = candidate
    }
    val winnerUid = winner?.let { uid(it) } ?: return null
    if (alsoReachableAs.any { it != null && uid(it) == winnerUid }) return null
    return winner
}

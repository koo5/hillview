package cz.hillview.map

/**
 * The marker rules that are worth pinning down, kept free of any drawing so
 * they can be tested. Both come from docs/tauri-map-ui-contract.md.
 */

/**
 * How opaque a photo's bearing circle is: full when it points the same way
 * as the current view, fading as it diverges. The Tauri app computes
 * `hsla(120,100%,70%, 1/step)` with `step = round(diff / (200/7))`, i.e.
 * buckets about 28.57 degrees wide.
 *
 * @param absDiff unsigned bearing difference, 0..180.
 */
fun bearingAgreementAlpha(absDiff: Double): Float {
    val step = kotlin.math.round(absDiff / (200.0 / 7.0)).toInt()
    return if (step > 0) 1f / step else 1f
}

/**
 * Groups items that land within [radius] of each other on screen, so photos
 * shot from one viewpoint can be drawn as a single bearing rose instead of a
 * pile.
 *
 * Greedy and single-pass: the first ungrouped item seeds a group and pulls in
 * everything within [radius] OF THE SEED (not a transitive chain), which
 * keeps clusters from growing along a line of markers. Input order therefore
 * decides seeds — callers should pass a stable order.
 */
fun <T> clusterByProximity(
    items: List<T>,
    radius: Float,
    x: (T) -> Float,
    y: (T) -> Float,
): List<List<T>> {
    val remaining = items.toMutableList()
    val out = mutableListOf<List<T>>()
    while (remaining.isNotEmpty()) {
        val seed = remaining.removeAt(0)
        val group = mutableListOf(seed)
        val iterator = remaining.iterator()
        while (iterator.hasNext()) {
            val candidate = iterator.next()
            val dx = x(candidate) - x(seed)
            val dy = y(candidate) - y(seed)
            if (kotlin.math.sqrt(dx * dx + dy * dy) <= radius) {
                group.add(candidate)
                iterator.remove()
            }
        }
        out.add(group)
    }
    return out
}

/**
 * The front photo: of the photos **in range**, the one whose own bearing is
 * closest to where the view is pointed, with the id as tiebreak.
 *
 * The tiebreak is not decoration — the Playwright suite notes that without
 * it "the front photo is decided by a diff-0 tie and flips under marker
 * churn". Returns null when nothing is in range.
 */
fun <T> frontPhoto(
    photos: List<T>,
    viewBearing: Double,
    id: (T) -> String,
    bearing: (T) -> Double?,
    inRange: (T) -> Boolean,
): T? = photos
    .filter { inRange(it) && bearing(it) != null }
    .minWithOrNull(
        compareBy<T> { absBearingDiff(bearing(it)!!, viewBearing) }.thenBy { id(it) },
    )

/**
 * Which marker a tap picks: the nearest one inside the touch radius, and
 * when a rose has stacked several at the very same point, the one that best
 * agrees with the current view.
 *
 * That second rule matters because a rose is *drawn* as one glyph, so every
 * photo in it is exactly equidistant from the tap. Falling back to the same
 * "closest to where we are looking" test [frontPhoto] uses keeps a tap and
 * the automatic selection from ever disagreeing about the same pile.
 */
fun <T> markerAtTap(
    drawn: List<T>,
    tapX: Float,
    tapY: Float,
    radius: Float,
    viewBearing: Double,
    x: (T) -> Float,
    y: (T) -> Float,
    id: (T) -> String,
    bearing: (T) -> Double?,
): T? {
    fun distance(item: T): Float = kotlin.math.hypot(tapX - x(item), tapY - y(item))
    return drawn
        .filter { distance(it) <= radius }
        .minWithOrNull(
            compareBy<T> { distance(it) }
                // A photo with no bearing sorts last: it can never be the
                // thing you are looking at.
                .thenBy { bearing(it)?.let { b -> absBearingDiff(b, viewBearing) } ?: 360.0 }
                .thenBy { id(it) },
        )
}

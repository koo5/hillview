package cz.hillview.map

/**
 * The map's marker budget, applied ACROSS sources — MapSettings.maxPhotos
 * is what gets drawn in total, not per source.
 *
 * On Android this is shared-kt's CullingGrid (the Tauri worker's rule:
 * a 10×10 grid over the viewport, one photo per cell per round, sources in
 * priority order device < hillview < other < mapillary, picks always kept)
 * behind [SharedMarkerCuller]. It is an interface for the same reason the
 * viewer's RangeCuller is: the rule lives in shared-kt, which is
 * Android-only, and the composite that applies it lives in commonMain.
 *
 * Whatever implements it must be a pure function of its arguments — the
 * composite re-culls on every source's arrival, and the final set must not
 * depend on which source answered first.
 */
fun interface MarkerCuller {
    /**
     * @param perSource markers by source id, twins already collapsed
     * @param picks ids (see PhotoMarker.id) that must survive whatever the budget
     */
    fun cull(
        perSource: Map<String, List<PhotoMarker>>,
        viewport: MapViewport,
        maxPhotos: Int,
        picks: Set<String>,
    ): List<PhotoMarker>

    companion object {
        /**
         * No spatial fairness — picks first, then source order, cut at the
         * budget. The desktop placeholder and the tests' default.
         */
        val Plain = MarkerCuller { perSource, _, maxPhotos, picks ->
            val all = perSource.values.flatten()
            val picked = all.filter { it.id in picks }
            (picked + all.filter { it.id !in picks }).take(maxPhotos)
        }
    }
}

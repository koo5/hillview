package cz.hillview.plugin

/**
 * Worker State Management - Faithful translation of worker state from new.worker.ts
 *
 * Manages the current state with the same structure as the TypeScript implementation:
 * - config: Sources configuration and settings
 * - area: Current map bounds and range
 * - sourcesPhotosInArea: Photo data per source
 */
class WorkerState {
    val config = StateData<ConfigData>()
    val area = StateData<Bounds>()
    val sourcesPhotosInArea = StateData<Map<SourceId, List<PhotoData>>>()

    // Initialize sourcesPhotosInArea with empty map
    init {
        sourcesPhotosInArea.data = emptyMap()
    }

    fun hasUnprocessedUpdates(): Triple<Boolean, Boolean, Boolean> {
        val configUnprocessed = config.lastUpdateId > config.lastProcessedId
        val areaUnprocessed = area.lastUpdateId > area.lastProcessedId
        val sourcesUnprocessed = sourcesPhotosInArea.lastUpdateId > sourcesPhotosInArea.lastProcessedId

        return Triple(configUnprocessed, areaUnprocessed, sourcesUnprocessed)
    }

    fun markConfigProcessed(updateId: Int) {
        config.lastProcessedId = updateId
    }

    fun markAreaProcessed(updateId: Int) {
        area.lastProcessedId = updateId
    }

    fun markSourcesPhotosInAreaProcessed(updateId: Int) {
        sourcesPhotosInArea.lastProcessedId = updateId
    }

    fun updateConfig(data: ConfigData, updateId: Int) {
        config.data = data
        config.lastUpdateId = updateId
    }

    fun updateArea(data: Bounds, updateId: Int, range: Double? = null) {
        area.data = data
        area.lastUpdateId = updateId
        // Range handling would be added if needed
    }

    fun updateSourcesPhotosInArea(data: Map<SourceId, List<PhotoData>>, updateId: Int) {
        sourcesPhotosInArea.data = data
        sourcesPhotosInArea.lastUpdateId = updateId
    }

    // Helper function to calculate center from bounds (translation from worker)
    fun calculateCenterFromBounds(bounds: Bounds): LatLng {
        // Longitude: handle antimeridian crossing
        val lng = if (bounds.top_left.lng <= bounds.bottom_right.lng) {
            (bounds.top_left.lng + bounds.bottom_right.lng) / 2
        } else {
            var l = (bounds.top_left.lng + bounds.bottom_right.lng + 360) / 2
            if (l > 180) l -= 360
            l
        }

        // Latitude: average in Mercator projection space so the result matches
        // the visual center of the viewport (Mercator is nonlinear in latitude,
        // so a geographic midpoint diverges significantly at low zoom).
        val toRad = Math.PI / 180
        val topY = Math.log(Math.tan(Math.PI / 4 + bounds.top_left.lat * toRad / 2))
        val bottomY = Math.log(Math.tan(Math.PI / 4 + bounds.bottom_right.lat * toRad / 2))
        val lat = (2 * Math.atan(Math.exp((topY + bottomY) / 2)) - Math.PI / 2) / toRad

        return LatLng(lat = lat, lng = lng)
    }
}
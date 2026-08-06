package cz.hillview.map

/**
 * Where the map's camera and bearing survive between sessions.
 *
 * The Tauri app persists both (bearing debounced, spatial written straight
 * through) and the Appium suite asserts the bearing is byte-identical after
 * the app is backgrounded — so holding this only in memory is a bug, not a
 * simplification. See docs/app-behaviour-scenarios.md.
 */
interface MapStateStore {
    fun load(): Pair<SpatialState, BearingState>?
    fun save(spatial: SpatialState, bearing: BearingState)
}

/** Desktop and tests: nothing to persist to. */
class InMemoryMapStateStore : MapStateStore {
    private var saved: Pair<SpatialState, BearingState>? = null
    override fun load() = saved
    override fun save(spatial: SpatialState, bearing: BearingState) {
        saved = spatial to bearing
    }
}

package cz.hillview.viewer

import cz.hillview.map.BearingState
import cz.hillview.map.MapStateHolder
import cz.hillview.map.PhotoMarker
import cz.hillview.map.SpatialState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn

/**
 * What the viewer pane draws: the photo you are facing and the four you can
 * turn to. See docs/tauri-viewer-ui-contract.md.
 */
data class ViewerState(
    /** In range, filtered, bearing-sorted — the ring you navigate. */
    val ring: List<PhotoMarker> = emptyList(),
    val front: PhotoMarker? = null,
    val left: PhotoMarker? = null,
    val right: PhotoMarker? = null,
    val up: PhotoMarker? = null,
    val down: PhotoMarker? = null,
)

/**
 * Which photos are near enough to turn to, spread evenly around the compass.
 *
 * A seam, not an abstraction for its own sake: the real implementation is
 * shared-kt's AngularRangeCuller, which is Android-only and shared with the
 * Tauri app, so it cannot be called from here — and re-implementing it in
 * commonMain would be the drift the contract warns about. Android hands the
 * shared one in; tests hand in a trivial one.
 *
 * Implementations must return the survivors SORTED BY BEARING (ascending,
 * id as tiebreak): left/right is index arithmetic on that order.
 */
fun interface RangeCuller {
    fun inRange(
        photos: List<PhotoMarker>,
        centerLat: Double,
        centerLon: Double,
        rangeMetres: Double,
        picks: Set<String>,
    ): List<PhotoMarker>
}

/**
 * The whole derivation, as a pure function of the inputs — no flows, no
 * scope, no clock. The holder below is only the wiring.
 *
 * The order matters and is the contract's: cull to what is in range, drop
 * what the filters hide, pick what you face, then read the neighbours off
 * that. Up and down are computed last because they must know left and right
 * in order to refuse to duplicate them.
 */
fun deriveViewerState(
    markers: List<PhotoMarker>,
    spatial: SpatialState,
    bearing: BearingState,
    hunterMode: Boolean,
    overrideFilters: Boolean,
    cull: RangeCuller,
): ViewerState {
    // The photo we deliberately turned to is exempt from culling — otherwise
    // the thing you are looking at can be culled out from under you.
    val picks = bearing.photoUid?.let { setOf(it) } ?: emptySet()
    val inRange = cull.inRange(
        markers, spatial.latitude, spatial.longitude, spatial.range, picks,
    )
    val ring = navigablePhotos(
        inRange, hunterMode, overrideFilters,
        filtered = { it.filteredOut }, featured = { it.featured }, bearing = { it.bearingDeg },
    )
    val front = viewerFrontPhoto(
        ring, bearing.bearing, bearing.photoUid, { it.id }, { it.bearingDeg!! },
    )
    val left = ringNeighbour(ring, front, -1) { it.id }
    val right = ringNeighbour(ring, front, +1) { it.id }
    val sideways = listOf(left, right)
    return ViewerState(
        ring = ring,
        front = front,
        left = left,
        right = right,
        up = pitchNeighbour(ring, front, true, sideways, { it.id }, { it.bearingDeg!! }, { it.pitchDeg }),
        down = pitchNeighbour(ring, front, false, sideways, { it.id }, { it.bearingDeg!! }, { it.pitchDeg }),
    )
}

/**
 * The pane's state, and its one action.
 *
 * [turnTo] is the point of the whole pane: choosing a photo is not a
 * selection, it is a BEARING WRITE. It goes through [MapStateHolder] like
 * every other bearing — the compass, car mode, a manual claim — so the map's
 * arrow, the marker fade and the next capture's stamp all follow from it.
 * A viewer that kept a bearing of its own would be a fourth source of truth,
 * which is exactly what the geo engine work removed.
 */
class ViewerStateHolder(
    private val map: MapStateHolder,
    /**
     * Turning to a photo stands bearing tracking down, because the original
     * does: updateBearingWithPhoto() calls disableBearingTracking() before
     * it writes. Without it the compass overwrites the photo's bearing on
     * its next reading and the turn does not stick — you are looking along
     * a PHOTO's direction now, not your own. The pane goes quiet in the
     * process, which is what the capture screen's bearing-tracking hint is
     * there to say out loud.
     */
    private val standDownTracking: () -> Unit,
    markers: StateFlow<List<PhotoMarker>>,
    hunterMode: StateFlow<Boolean>,
    overrideFilters: StateFlow<Boolean>,
    cull: RangeCuller,
    scope: CoroutineScope,
    private val now: () -> Long,
) {
    /**
     * Computed only while something is looking — the original's semantics
     * exactly: photoInFront is a Svelte derived store, and derived stores
     * run only while subscribed, which only the Gallery does. Eagerly here
     * meant a range cull and a sort of the whole marker set on every compass
     * tick (~10 Hz) for as long as the process lived, including the entire
     * time the capture or external-camera pane was up and nobody could see
     * the result (user-caught). WhileSubscribed makes the pane's collector
     * the switch; the first frame after entering the viewer pays one
     * derivation, as the original's first subscription does.
     */
    val state: StateFlow<ViewerState> =
        combine(markers, map.spatial, map.bearing, hunterMode, overrideFilters) { m, s, b, h, o ->
            deriveViewerState(m, s, b, h, o, cull)
        }.stateIn(scope, SharingStarted.WhileSubscribed(), ViewerState())

    /**
     * Turn to a neighbour. The uid is recorded alongside the bearing so the
     * choice STICKS while the view has not moved off it — see
     * viewerFrontPhoto.
     */
    fun turnTo(photo: PhotoMarker) {
        val bearing = photo.bearingDeg ?: return
        standDownTracking()
        map.updateBearing(
            bearing = bearing,
            source = SOURCE_PHOTO_NAVIGATION,
            photoUid = photo.id,
            now = now(),
        )
    }

    companion object {
        /** The original's `updateBearingWithPhoto(photo, 'photo_navigation')`. */
        const val SOURCE_PHOTO_NAVIGATION = "photo_navigation"
    }
}

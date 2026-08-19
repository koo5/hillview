package cz.hillview.viewer

import cz.hillview.map.PhotoMarker
import cz.hillview.plugin.AngularRangeCuller
import cz.hillview.plugin.LatLng
import cz.hillview.plugin.PhotoData
import cz.hillview.plugin.sortPhotosByBearing

/**
 * The viewer's [RangeCuller], backed by shared-kt's AngularRangeCuller —
 * the same culling the Tauri app's photo worker runs, not a second opinion.
 *
 * It is an adapter rather than a call because the shared culler speaks
 * PhotoData (the worker's model) and the map speaks PhotoMarker. Rewriting it
 * against PhotoMarker would leave two implementations of a rule with real
 * consequences — uniform angular coverage is what stops 200 photos of one
 * landmark from making every other direction unreachable — so the model is
 * translated instead and the rule stays in one place.
 *
 * Only what the culler reads is carried across: position, bearing, and the
 * identity used for picks. Results are matched back to the original markers
 * by id, so nothing downstream ever sees the stand-ins.
 */
internal class SharedRangeCuller(
    private val maxPhotos: Int = MAX_RING_PHOTOS,
) : RangeCuller {

    private val culler = AngularRangeCuller()

    override fun inRange(
        photos: List<PhotoMarker>,
        centerLat: Double,
        centerLon: Double,
        rangeMetres: Double,
        picks: Set<String>,
    ): List<PhotoMarker> {
        val byId = HashMap<String, PhotoMarker>(photos.size)
        val standIns = ArrayList<PhotoData>(photos.size)
        for (marker in photos) {
            // A photo with no bearing cannot be bucketed by direction, and
            // could not be navigated to afterwards either.
            val bearing = marker.bearingDeg ?: continue
            byId[marker.id] = marker
            standIns += PhotoData(
                id = marker.id,
                // The culler matches picks on uid; frontend2 identifies photos
                // by the raw id everywhere (see PhotoData.toMarker), so the two
                // are deliberately the same string here.
                uid = marker.id,
                source_type = marker.source,
                coord = LatLng(marker.latitude, marker.longitude),
                bearing = bearing,
                source = marker.source,
            )
        }

        val culled = culler.cullPhotosInRange(
            standIns, LatLng(centerLat, centerLon), rangeMetres, maxPhotos, picks,
        ).toMutableList()
        // The culler returns picks first and then bucket order; the ring's
        // left/right is index arithmetic on BEARING order, so this sort is not
        // cosmetic. The Svelte pipeline sorts at the same point, immediately
        // after culling (mapState.ts:194).
        sortPhotosByBearing(culled)
        return culled.mapNotNull { byId[it.id] }
    }

    companion object {
        /**
         * The ring's size cap, matching the Svelte pipeline's 300
         * (mapState.ts:191) rather than the map's marker budget: this is how
         * many photos you could turn to, not how many are drawn.
         */
        const val MAX_RING_PHOTOS = 300
    }
}

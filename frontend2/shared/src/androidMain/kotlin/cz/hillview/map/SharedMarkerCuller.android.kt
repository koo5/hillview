package cz.hillview.map

import cz.hillview.plugin.Bounds
import cz.hillview.plugin.CullingGrid
import cz.hillview.plugin.LatLng
import cz.hillview.plugin.PhotoData

/**
 * The map's [MarkerCuller], backed by shared-kt's CullingGrid — the same
 * cross-source cap the Tauri app's photo worker applies, not a second
 * opinion. An adapter for the same reason SharedRangeCuller is one: the
 * shared culler speaks PhotoData, the map speaks PhotoMarker, and the rule
 * must stay in one place.
 *
 * Only what the grid reads is carried across: position, source, content
 * hash, capture time (device photos in a crowded cell keep the newest) and
 * the identity picks are matched on. Results map back to the original
 * markers, so nothing downstream sees the stand-ins.
 */
class SharedMarkerCuller : MarkerCuller {

    override fun cull(
        perSource: Map<String, List<PhotoMarker>>,
        viewport: MapViewport,
        maxPhotos: Int,
        picks: Set<String>,
    ): List<PhotoMarker> {
        val bounds = Bounds(
            top_left = LatLng(viewport.topLeftLat, viewport.topLeftLon),
            bottom_right = LatLng(viewport.bottomRightLat, viewport.bottomRightLon),
        )
        // Keyed by source AND id: ids are only unique within a source.
        val byKey = HashMap<String, PhotoMarker>()
        val standIns = LinkedHashMap<String, List<PhotoData>>()
        for ((sourceId, markers) in perSource) {
            standIns[sourceId] = markers.map { marker ->
                byKey["$sourceId|${marker.id}"] = marker
                PhotoData(
                    id = marker.id,
                    // The grid matches picks on uid; frontend2 identifies
                    // photos by the raw id everywhere (see PhotoData.toMarker),
                    // so the two are deliberately the same string here — as
                    // in SharedRangeCuller.
                    uid = marker.id,
                    source_type = marker.source,
                    coord = LatLng(marker.latitude, marker.longitude),
                    bearing = marker.bearingDeg ?: 0.0,
                    has_bearing = marker.bearingDeg != null,
                    source = sourceId,
                    fileHash = marker.fileMd5,
                    captured_at = marker.capturedAtMs,
                    is_device_photo = marker.isDevicePhoto,
                )
            }
        }
        return CullingGrid(bounds)
            .cullPhotos(standIns, maxPhotos, picks)
            .mapNotNull { byKey["${it.source}|${it.id}"] }
    }
}

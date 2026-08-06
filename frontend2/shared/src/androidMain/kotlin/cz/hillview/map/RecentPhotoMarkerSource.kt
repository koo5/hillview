package cz.hillview.map

import android.content.Context
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.settings.MapSettingsRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext

/**
 * SCAFFOLDING (see PhotoMarkerSource): the last N photos captured on this
 * device, straight from the shared upload database — the same rows the
 * upload stack works with, so what the map shows is what the app really has.
 * getPhotosPaginated already orders by createdAt DESC, which is exactly
 * "most recent first".
 */
class RecentPhotoMarkerSource(
    private val context: Context,
    private val settings: MapSettingsRepository,
) : PhotoMarkerSource {
    private val _markers = MutableStateFlow<List<PhotoMarker>>(emptyList())
    override val markers: StateFlow<List<PhotoMarker>> = _markers.asStateFlow()

    /**
     * The selected photo is pinned: the limit must never drop what the user
     * is looking at. The Tauri app calls these "picks" and sends them to the
     * backend for the same reason — otherwise a quota filled by other photos
     * silently deselects you.
     */
    var pinnedId: String? = null

    override suspend fun refresh() {
        val limit = settings.settings.value.maxPhotos
        val pinned = pinnedId
        _markers.value = withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()
            val page = dao.getPhotosPaginated(limit, 0)
            val withPin = if (pinned != null && page.none { it.id == pinned }) {
                page + listOfNotNull(dao.getPhotoById(pinned))
            } else {
                page
            }
            withPin
                .filter { it.latitude != 0.0 || it.longitude != 0.0 }
                .map {
                    PhotoMarker(
                        id = it.id,
                        latitude = it.latitude,
                        longitude = it.longitude,
                        // 0 is the DB's "unset" for bearing, not a heading.
                        bearingDeg = it.bearing.takeIf { b -> b != 0.0 },
                        capturedAtMs = it.capturedAt,
                        uploadStatus = it.uploadStatus,
                    )
                }
        }
    }
}

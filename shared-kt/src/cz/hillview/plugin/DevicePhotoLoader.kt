package cz.hillview.plugin

import android.content.Context
import android.util.Log
import androidx.room.Room

/**
 * Device Photo Loader - Loads photos from local device storage using Room database
 *
 * Faithful translation of DeviceSourceLoader.ts functionality using the existing
 * Room database and PhotoEntity structure.
 */
class DevicePhotoLoader(private val context: Context) {
    companion object {
        private const val TAG = "DevicePhotoLoader"
        private const val doLog = false
    }

    private val photoDatabase = PhotoDatabase.getDatabase(context)
    private val photoDao = photoDatabase.photoDao()

    suspend fun loadPhotos(
        source: SourceConfig,
        bounds: Bounds?,
        maxPhotos: Int,
        shouldAbort: () -> Boolean,
        picks: Set<String> = emptySet()
    ): List<PhotoData> {
        return try {
            if (doLog) Log.d(TAG, " Loading device photos from database")
            if (doLog) Log.d(TAG, " Source config: ${source.id}")
            if (doLog) Log.d(TAG, " Bounds: $bounds")
            if (doLog) Log.d(TAG, " MaxPhotos: $maxPhotos")

            val photoEntities = if (bounds != null) {
                // First get picked photos that are in bounds (they always stay on map)
                val pickedPhotos = if (picks.isNotEmpty()) {
                    photoDao.getPickedPhotosInBounds(
                        minLat = bounds.bottom_right.lat,
                        maxLat = bounds.top_left.lat,
                        minLng = bounds.top_left.lng,
                        maxLng = bounds.bottom_right.lng,
                        picks = picks
                    )
                } else {
                    emptyList()
                }

                // Then get regular photos up to the limit minus picked photos
                val remainingLimit = maxPhotos - pickedPhotos.size
                val regularPhotos = if (remainingLimit > 0) {
                    photoDao.getPhotosInBounds(
                        minLat = bounds.bottom_right.lat,
                        maxLat = bounds.top_left.lat,
                        minLng = bounds.top_left.lng,
                        maxLng = bounds.bottom_right.lng,
                        limit = remainingLimit
                    ).filter { photo -> !picks.contains(photo.id) } // Exclude already picked photos
                } else {
                    emptyList()
                }

                // Combine picked photos first, then regular photos
                pickedPhotos + regularPhotos
            } else {
                // No bounds specified, get all photos with limit
                photoDao.getPhotosPaginated(limit = maxPhotos, offset = 0)
            }

            if (shouldAbort()) {
                if (doLog) Log.d(TAG, " Aborted during photo loading")
                return emptyList()
            }

            // Convert PhotoEntity to PhotoData format
            val photos = photoEntities.map { photoEntity ->
                convertToPhotoData(photoEntity, source)
            }

            if (doLog) Log.d(TAG, " Loaded ${photos.size} photos from device source ${source.id}")
            photos

        } catch (error: Exception) {
            Log.e(TAG, " Error loading device photos", error)
            throw error
        }
    }

    private fun convertToPhotoData(photoEntity: PhotoEntity, source: SourceConfig): PhotoData {
        // content:// URIs stay as-is, file paths get file:// prefix
        val fileUrl = if (PhotoUtils.isContentUri(photoEntity.path)) {
            photoEntity.path
        } else {
            "file://${photoEntity.path}"
        }

        // Create sizes dict with 'full' size entry for consistency with other photo sources
        val sizes = mapOf(
            "full" to PhotoSize(
                url = fileUrl,
                width = photoEntity.width,
                height = photoEntity.height
            )
        )

        return PhotoData(
            id = photoEntity.id,
            uid = "${source.id}-${photoEntity.id}",
            source_type = source.type,
            filename = photoEntity.filename,
            coord = LatLng(
                lat = photoEntity.latitude,
                lng = photoEntity.longitude
            ),
            bearing = photoEntity.bearing,
            altitude = photoEntity.altitude,
            source = source.id,
            sizes = sizes,
            is_device_photo = true,
            captured_at = photoEntity.capturedAt,
            created_at = photoEntity.createdAt,
            accuracy = photoEntity.accuracy,
            fileHash = photoEntity.fileHash
        )
    }

}


// Device photo format (matching frontend interface)
data class DevicePhoto(
    val id: String,
    val filePath: String,
    val fileName: String,
    val fileHash: String,
    val fileSize: Long,
    val capturedAt: Long,
    val createdAt: Long,
    val latitude: Double,
    val longitude: Double,
    val altitude: Double,
    val bearing: Double,
    val accuracy: Double,
    val width: Int,
    val height: Int,
    val uploadStatus: String,
    val uploadedAt: Long? = null
)

data class DevicePhotosResponse(
    val photos: List<DevicePhoto>,
    val lastUpdated: Long,
    val page: Int,
    val pageSize: Int,
    val totalCount: Int,
    val totalPages: Int,
    val hasMore: Boolean,
    val error: String? = null
)

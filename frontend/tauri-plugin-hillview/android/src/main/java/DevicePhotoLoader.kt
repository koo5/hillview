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
    }

    private val photoDatabase = PhotoDatabase.getDatabase(context)
    private val photoDao = photoDatabase.photoDao()

    suspend fun loadPhotos(
        source: SourceConfig,
        bounds: Bounds?,
        maxPhotos: Int,
        shouldAbort: () -> Boolean
    ): List<PhotoData> {
        return try {
            Log.d(TAG, " Loading device photos from database")
            Log.d(TAG, " Source config: ${source.id}")
            Log.d(TAG, " Bounds: $bounds")
            Log.d(TAG, " MaxPhotos: $maxPhotos")

            /*
            val photoEntities = if (bounds != null) {
                // Apply spatial filtering using Room query with bounds
                photoDao.getPhotosInBounds(
                    minLat = bounds.bottom_right.lat,
                    maxLat = bounds.top_left.lat,
                    minLng = bounds.top_left.lng,
                    maxLng = bounds.bottom_right.lng,
                    limit = maxPhotos
                )
            } else {
                // No bounds specified, get all photos with limit
                photoDao.getPhotosPaginated(limit = maxPhotos, offset = 0)
            }
            */

            // TEMPORARY: Load all photos without bounds filtering for debugging
            // First, check database status
            val totalCount = photoDao.getTotalPhotoCount()
            Log.d(TAG, " Database total photo count: $totalCount")

            // Get all photos to see what's in the database
            val allPhotos = photoDao.getAllPhotos()
            Log.d(TAG, " Found ${allPhotos.size} total photos in database")

            if (allPhotos.isNotEmpty()) {
                Log.d(TAG, " Sample photo details:")
                allPhotos.take(3).forEach { photo ->
                    Log.d(TAG, "  Photo ID: ${photo.id}, Path: ${photo.path}, Lat: ${photo.latitude}, Lng: ${photo.longitude}, UploadStatus: ${photo.uploadStatus}")
                }
            }

            val photoEntities = photoDao.getPhotosPaginated(limit = maxPhotos, offset = 0)
            Log.d(TAG, " DEBUG - Loading ALL photos (bounds disabled), found ${photoEntities.size} photos")

            if (shouldAbort()) {
                Log.d(TAG, " Aborted during photo loading")
                return emptyList()
            }

            // Convert PhotoEntity to PhotoData format
            val photos = photoEntities.map { photoEntity ->
                convertToPhotoData(photoEntity, source)
            }

            Log.d(TAG, " Loaded ${photos.size} photos from device source ${source.id}")
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
            file = photoEntity.filename,
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

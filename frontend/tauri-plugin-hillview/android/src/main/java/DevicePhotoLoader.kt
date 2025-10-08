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

    private val photoDatabase = Room.databaseBuilder(
        context,
        PhotoDatabase::class.java,
        "photo-database"
    ).build()

    private val photoDao = photoDatabase.photoDao()

    suspend fun loadPhotos(
        source: SourceConfig,
        bounds: Bounds?,
        maxPhotos: Int,
        shouldAbort: () -> Boolean
    ): List<PhotoData> {
        return try {
            Log.d(TAG, "DevicePhotoLoader: Loading device photos from database")
            Log.d(TAG, "DevicePhotoLoader: Source config: ${source.id}")
            Log.d(TAG, "DevicePhotoLoader: Bounds: $bounds")
            Log.d(TAG, "DevicePhotoLoader: MaxPhotos: $maxPhotos")

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

            if (shouldAbort()) {
                Log.d(TAG, "DevicePhotoLoader: Aborted during photo loading")
                return emptyList()
            }

            // Convert PhotoEntity to PhotoData format
            val photos = photoEntities.map { photoEntity ->
                convertToPhotoData(photoEntity, source)
            }

            Log.d(TAG, "DevicePhotoLoader: Loaded ${photos.size} photos from device source ${source.id}")
            photos

        } catch (error: Exception) {
            Log.e(TAG, "DevicePhotoLoader: Error loading device photos", error)
            throw error
        }
    }

    private fun convertToPhotoData(photoEntity: PhotoEntity, source: SourceConfig): PhotoData {
        return PhotoData(
            id = photoEntity.id,
            uid = "${source.id}-${photoEntity.id}",
            source_type = source.type,
            file = photoEntity.filename,
            url = "file://${photoEntity.path}",
            coord = LatLng(
                lat = photoEntity.latitude,
                lng = photoEntity.longitude
            ),
            bearing = photoEntity.bearing,
            altitude = photoEntity.altitude,
            source = source,
            isDevicePhoto = true,
            timestamp = photoEntity.timestamp,
            accuracy = photoEntity.accuracy,
            fileHash = photoEntity.fileHash
        )
    }

    /**
     * Get device photos with pagination (for future use)
     */
    suspend fun getDevicePhotosResponse(
        page: Int = 1,
        pageSize: Int = 50,
        bounds: Bounds? = null
    ): DevicePhotosResponse {
        return try {
            val offset = (page - 1) * pageSize

            val photoEntities = if (bounds != null) {
                photoDao.getPhotosInBounds(
                    minLat = bounds.bottom_right.lat,
                    maxLat = bounds.top_left.lat,
                    minLng = bounds.top_left.lng,
                    maxLng = bounds.bottom_right.lng,
                    limit = pageSize + 1 // Get one extra to check if there are more
                )
            } else {
                photoDao.getPhotosPaginated(limit = pageSize + 1, offset = offset)
            }

            val hasMore = photoEntities.size > pageSize
            val photosToReturn = if (hasMore) photoEntities.dropLast(1) else photoEntities

            val totalCount = photoDao.getTotalPhotoCount()
            val totalPages = (totalCount + pageSize - 1) / pageSize

            val devicePhotos = photosToReturn.map { entity ->
                DevicePhoto(
                    id = entity.id,
                    filePath = entity.path,
                    fileName = entity.filename,
                    fileHash = entity.fileHash,
                    fileSize = entity.fileSize,
                    timestamp = entity.timestamp,
                    createdAt = entity.createdAt,
                    latitude = entity.latitude,
                    longitude = entity.longitude,
                    altitude = entity.altitude,
                    bearing = entity.bearing,
                    accuracy = entity.accuracy,
                    width = entity.width,
                    height = entity.height,
                    uploadStatus = entity.uploadStatus,
                    uploadedAt = entity.uploadedAt
                )
            }

            DevicePhotosResponse(
                photos = devicePhotos,
                lastUpdated = System.currentTimeMillis(),
                page = page,
                pageSize = pageSize,
                totalCount = totalCount,
                totalPages = totalPages,
                hasMore = hasMore
            )

        } catch (error: Exception) {
            Log.e(TAG, "Error getting device photos response", error)
            DevicePhotosResponse(
                photos = emptyList(),
                lastUpdated = System.currentTimeMillis(),
                page = page,
                pageSize = pageSize,
                totalCount = 0,
                totalPages = 0,
                hasMore = false,
                error = error.message
            )
        }
    }
}

// Device photo format (matching frontend interface)
data class DevicePhoto(
    val id: String,
    val filePath: String,
    val fileName: String,
    val fileHash: String,
    val fileSize: Long,
    val timestamp: Long,
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
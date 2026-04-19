package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update

@Dao
interface SimplePhotoDao {

    @Query("SELECT * FROM photos ORDER BY createdAt DESC")
    fun getAllPhotos(): List<PhotoEntity>

    @Query("SELECT * FROM photos ORDER BY createdAt DESC LIMIT :limit OFFSET :offset")
    fun getPhotosPaginated(limit: Int, offset: Int): List<PhotoEntity>

    @Query("""
        SELECT * FROM photos
        WHERE latitude BETWEEN :minLat AND :maxLat
        AND longitude BETWEEN :minLng AND :maxLng
        AND deleted = 0
        ORDER BY capturedAt DESC
        LIMIT :limit
    """)
    fun getPhotosInBounds(minLat: Double, maxLat: Double, minLng: Double, maxLng: Double, limit: Int): List<PhotoEntity>

    @Query("""
        SELECT * FROM photos
        WHERE latitude BETWEEN :minLat AND :maxLat
        AND longitude BETWEEN :minLng AND :maxLng
        AND id IN (:picks)
        AND deleted = 0
    """)
    fun getPickedPhotosInBounds(minLat: Double, maxLat: Double, minLng: Double, maxLng: Double, picks: Set<String>): List<PhotoEntity>


    @Query("SELECT COUNT(*) FROM photos")
    fun getTotalPhotoCount(): Int

    @Query("SELECT * FROM photos WHERE id = :photoId")
    fun getPhotoById(photoId: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE path = :path")
    fun getPhotoByPath(path: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE fileHash = :hash")
    fun getPhotoByHash(hash: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE serverPhotoId = :serverPhotoId")
    fun getPhotoByServerPhotoId(serverPhotoId: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE uploadStatus = :status AND deleted = 0 ORDER BY createdAt ASC")
    fun getPhotosByUploadStatus(status: String): List<PhotoEntity>

    @Query("SELECT * FROM photos WHERE uploadStatus = 'pending' AND deleted = 0 ORDER BY createdAt ASC")
    fun getPendingUploads(): List<PhotoEntity>

    //@Query("SELECT * FROM photos WHERE uploadStatus = 'failed' ORDER BY lastUploadAttempt ASC")
    //fun getFailedUploadsForRetry(): List<PhotoEntity>

    @Query("""
        SELECT * FROM photos
        WHERE deleted = 0
        AND (id NOT IN (:seen) AND (
            uploadStatus IN ('pending', 'failed') OR
            (uploadStatus = 'uploading' AND lastUploadAttempt < :uploadingStaleThreshold) OR
            (uploadStatus = 'processing' AND lastUploadAttempt < :processingStaleThreshold)
        ))
        ORDER BY
            CASE uploadStatus
                WHEN 'pending' THEN 1
                WHEN 'failed' THEN 2
                WHEN 'uploading' THEN 3
                WHEN 'processing' THEN 4
            END,
            CASE uploadStatus
                WHEN 'pending' THEN createdAt
                WHEN 'failed' THEN lastUploadAttempt
                WHEN 'uploading' THEN lastUploadAttempt
                WHEN 'processing' THEN lastUploadAttempt
            END ASC
        LIMIT 1
    """)
    fun getNextPhotoForUpload(seen: Set<String>, uploadingStaleThreshold: Long, processingStaleThreshold: Long): PhotoEntity?

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'pending' AND deleted = 0")
    fun getPendingUploadCount(): Int

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'failed' AND deleted = 0")
    fun getFailedUploadCount(): Int

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'completed' AND deleted = 0")
    fun getCompletedUploadCount(): Int

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'uploading' AND deleted = 0")
    fun getUploadingCount(): Int

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'processing' AND deleted = 0")
    fun getProcessingCount(): Int

    @Query("SELECT COUNT(*) FROM photos WHERE deleted = 1")
    fun getDeletedCount(): Int

    @Query("UPDATE photos SET deleted = :deleted WHERE id = :photoId")
    fun updateDeleted(photoId: String, deleted: Boolean)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertPhoto(photo: PhotoEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertPhotos(photos: List<PhotoEntity>)

    @Update
    fun updatePhoto(photo: PhotoEntity)

    @Query("UPDATE photos SET uploadStatus = :status, uploadedAt = :uploadedAt WHERE id = :photoId")
    fun updateUploadStatus(photoId: String, status: String, uploadedAt: Long)

    @Query("UPDATE photos SET serverPhotoId = :serverPhotoId WHERE id = :photoId")
    fun updateServerPhotoId(photoId: String, serverPhotoId: String)

    @Query("UPDATE photos SET uploadStatus = :status, serverPhotoId = :serverPhotoId, lastUploadAttempt = :lastAttempt WHERE id = :photoId")
    fun updateUploadStatusAndServerId(photoId: String, status: String, serverPhotoId: String, lastAttempt: Long)

    @Query("UPDATE photos SET uploadStatus = :status, retryCount = :retryCount, lastUploadAttempt = :lastAttempt, uploadError = :error WHERE id = :photoId")
    fun updateUploadFailure(photoId: String, status: String, retryCount: Int, lastAttempt: Long, error: String)

    @Query("SELECT * FROM photos WHERE uploadStatus = 'processing' AND serverPhotoId IS NOT NULL AND deleted = 0")
    fun getProcessingPhotos(): List<PhotoEntity>

    @Query("DELETE FROM photos WHERE id = :photoId")
    fun deletePhoto(photoId: String)

    @Query("DELETE FROM photos WHERE path NOT IN (SELECT path FROM photos WHERE path LIKE :pathPattern)")
    fun deletePhotosNotInPath(pathPattern: String)

    @Query("SELECT EXISTS(SELECT 1 FROM photos WHERE path = :path)")
    fun photoExists(path: String): Boolean

    @Query("UPDATE photos SET lastUploadAttempt = :timestamp WHERE id = :photoId")
    suspend fun updateUploadHeartbeat(photoId: String, timestamp: Long)

    @Query("UPDATE photos SET anonymizationOverride = :override, version = version + 1, uploadStatus = 'pending' WHERE id = :photoId")
    fun updateAnonymizationOverride(photoId: String, override: String?)
}

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
        ORDER BY bearing ASC, createdAt DESC
        LIMIT :limit
    """)
    fun getPhotosInBounds(minLat: Double, maxLat: Double, minLng: Double, maxLng: Double, limit: Int): List<PhotoEntity>

    @Query("SELECT COUNT(*) FROM photos")
    fun getTotalPhotoCount(): Int

    @Query("SELECT * FROM photos WHERE id = :photoId")
    fun getPhotoById(photoId: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE path = :path")
    fun getPhotoByPath(path: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE fileHash = :hash")
    fun getPhotoByHash(hash: String): PhotoEntity?

    @Query("SELECT * FROM photos WHERE uploadStatus = :status ORDER BY createdAt ASC")
    fun getPhotosByUploadStatus(status: String): List<PhotoEntity>

    @Query("SELECT * FROM photos WHERE uploadStatus = 'pending' ORDER BY createdAt ASC")
    fun getPendingUploads(): List<PhotoEntity>

    @Query("SELECT * FROM photos WHERE uploadStatus = 'failed' ORDER BY lastUploadAttempt ASC")
    fun getFailedUploadsForRetry(): List<PhotoEntity>

    @Query("""
        SELECT * FROM photos
        WHERE uploadStatus IN ('pending', 'uploading', 'failed')
        ORDER BY
            CASE uploadStatus
                WHEN 'pending' THEN 1
                WHEN 'uploading' THEN 2
                WHEN 'failed' THEN 3
            END,
            CASE uploadStatus
                WHEN 'pending' THEN createdAt
                WHEN 'uploading' THEN createdAt
                WHEN 'failed' THEN lastUploadAttempt
            END ASC
        LIMIT 1
    """)
    fun getNextPhotoForUpload(): PhotoEntity?

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'pending'")
    fun getPendingUploadCount(): Int

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'failed'")
    fun getFailedUploadCount(): Int

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertPhoto(photo: PhotoEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertPhotos(photos: List<PhotoEntity>)

    @Update
    fun updatePhoto(photo: PhotoEntity)

    @Query("UPDATE photos SET uploadStatus = :status, uploadedAt = :uploadedAt WHERE id = :photoId")
    fun updateUploadStatus(photoId: String, status: String, uploadedAt: Long)

    @Query("UPDATE photos SET uploadStatus = :status, retryCount = :retryCount, lastUploadAttempt = :lastAttempt, uploadError = :error WHERE id = :photoId")
    fun updateUploadFailure(photoId: String, status: String, retryCount: Int, lastAttempt: Long, error: String)

    @Query("DELETE FROM photos WHERE id = :photoId")
    fun deletePhoto(photoId: String)

    @Query("DELETE FROM photos WHERE path NOT IN (SELECT path FROM photos WHERE path LIKE :pathPattern)")
    fun deletePhotosNotInPath(pathPattern: String)

    @Query("SELECT EXISTS(SELECT 1 FROM photos WHERE path = :path)")
    fun photoExists(path: String): Boolean
}

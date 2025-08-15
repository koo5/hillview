package io.github.koo5.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update

@Dao
interface PhotoDao {
    
    @Query("SELECT * FROM photos ORDER BY createdAt DESC")
    suspend fun getAllPhotos(): List<PhotoEntity>
    
    @Query("SELECT * FROM photos WHERE id = :photoId")
    suspend fun getPhotoById(photoId: String): PhotoEntity?
    
    @Query("SELECT * FROM photos WHERE path = :path")
    suspend fun getPhotoByPath(path: String): PhotoEntity?
    
    @Query("SELECT * FROM photos WHERE fileHash = :hash")
    suspend fun getPhotoByHash(hash: String): PhotoEntity?
    
    @Query("SELECT * FROM photos WHERE uploadStatus = :status ORDER BY createdAt ASC")
    suspend fun getPhotosByUploadStatus(status: String): List<PhotoEntity>
    
    @Query("SELECT * FROM photos WHERE uploadStatus = 'pending' AND autoUploadEnabled = 1 ORDER BY createdAt ASC")
    suspend fun getPendingUploads(): List<PhotoEntity>
    
    @Query("SELECT * FROM photos WHERE uploadStatus = 'failed' AND retryCount < 5 ORDER BY lastUploadAttempt ASC")
    suspend fun getFailedUploadsForRetry(): List<PhotoEntity>
    
    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'pending'")
    suspend fun getPendingUploadCount(): Int
    
    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'failed'")
    suspend fun getFailedUploadCount(): Int
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPhoto(photo: PhotoEntity)
    
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertPhotos(photos: List<PhotoEntity>)
    
    @Update
    suspend fun updatePhoto(photo: PhotoEntity)
    
    @Query("UPDATE photos SET uploadStatus = :status, uploadedAt = :uploadedAt WHERE id = :photoId")
    suspend fun updateUploadStatus(photoId: String, status: String, uploadedAt: Long?)
    
    @Query("UPDATE photos SET uploadStatus = :status, retryCount = :retryCount, lastUploadAttempt = :lastAttempt, uploadError = :error WHERE id = :photoId")
    suspend fun updateUploadFailure(photoId: String, status: String, retryCount: Int, lastAttempt: Long, error: String?)
    
    @Query("UPDATE photos SET autoUploadEnabled = :enabled")
    suspend fun setAutoUploadForAllPhotos(enabled: Boolean)
    
    @Query("DELETE FROM photos WHERE id = :photoId")
    suspend fun deletePhoto(photoId: String)
    
    @Query("DELETE FROM photos WHERE path NOT IN (SELECT path FROM photos WHERE path LIKE :pathPattern)")
    suspend fun deletePhotosNotInPath(pathPattern: String)
    
    @Query("SELECT EXISTS(SELECT 1 FROM photos WHERE path = :path)")
    suspend fun photoExists(path: String): Boolean
}
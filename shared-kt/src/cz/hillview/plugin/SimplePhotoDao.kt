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
        WHERE deleted = 0 AND uploadHoldUntil <= :now
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
    fun getNextPhotoForUpload(seen: Set<String>, uploadingStaleThreshold: Long, processingStaleThreshold: Long, now: Long): PhotoEntity?

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'pending' AND deleted = 0")
    fun getPendingUploadCount(): Int

    @Query("SELECT COUNT(*) FROM photos WHERE uploadStatus = 'failed' AND deleted = 0")
    fun getFailedUploadCount(): Int

    // Candidates the drain loop will consider this run — the SQL half of
    // getNextPhotoForUpload's predicate (minus the per-iteration seen/order/
    // limit). The caller applies the shared Kotlin backoff predicate
    // (isEligibleNow) so the progress denominator matches what the loop
    // actually attempts; validation drops (missing file / bad hash) are
    // loop-only and just shrink the numerator slightly.
    @Query("""
        SELECT * FROM photos
        WHERE deleted = 0 AND uploadHoldUntil <= :now AND (
            uploadStatus IN ('pending', 'failed') OR
            (uploadStatus = 'uploading' AND lastUploadAttempt < :uploadingStaleThreshold) OR
            (uploadStatus = 'processing' AND lastUploadAttempt < :processingStaleThreshold)
        )
    """)
    fun getUploadableCandidates(uploadingStaleThreshold: Long, processingStaleThreshold: Long, now: Long): List<PhotoEntity>

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

    // The refiner's hold released early (completion or defeat) — without
    // this the row waits out its deadline before the drain may take it.
    @Query("UPDATE photos SET uploadHoldUntil = 0 WHERE id = :photoId")
    fun clearUploadHold(photoId: String)

    /**
     * Take the row for upload, atomically — a compare-and-set on the status
     * we selected it under. Returns rows updated: 0 means we lost it (the
     * refiner or another pass moved it) and the caller must skip.
     *
     * This replaced an unconditional "set uploading", which made claiming a
     * two-step read-then-write with a token refresh and a file hash in
     * between. A stamp refinement landing in that gap was written to the row
     * but missed by the upload, so device-photos and the server disagreed
     * about where a photo was taken. Pairing this with a re-READ after the
     * claim closes it from both sides: a refinement before the claim is
     * seen, and one after is impossible, since applyRefinedStamp only
     * touches rows that are still 'pending'.
     */
    @Query("""
        UPDATE photos SET uploadStatus = 'uploading', uploadedAt = :now
        WHERE id = :photoId AND uploadStatus = :expectedStatus AND deleted = 0
    """)
    fun claimForUpload(photoId: String, expectedStatus: String, now: Long): Int

    // The stamp refiner's write. Guarded on 'pending' so a refinement never
    // rewrites a row the drain already picked up — the uploaded metadata and
    // the local row must keep telling the same story; a photo the upload
    // won keeps its at-the-time stamp, by design. Returns rows updated
    // (0 = lost the race or already gone).
    @Query("""
        UPDATE photos SET latitude = :latitude, longitude = :longitude,
            altitude = :altitude, bearing = :bearing, stampRefinedAt = :refinedAt
        WHERE id = :photoId AND uploadStatus = 'pending' AND deleted = 0
    """)
    fun applyRefinedStamp(
        photoId: String,
        latitude: Double,
        longitude: Double,
        altitude: Double,
        bearing: Double,
        refinedAt: Long,
    ): Int

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

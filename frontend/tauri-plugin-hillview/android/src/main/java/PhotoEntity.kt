package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.ColumnInfo
import androidx.room.Index

@Entity(
    tableName = "photos",
    indices = [
        Index(value = ["createdAt"], name = "idx_photos_created_at"),
        Index(value = ["uploadStatus", "createdAt"], name = "idx_photos_upload_status_created_at"),
        Index(value = ["latitude", "longitude"], name = "idx_photos_location"),
        Index(value = ["fileHash"], name = "idx_photos_file_hash"),
        Index(value = ["path"], name = "idx_photos_path")
    ]
)
data class PhotoEntity(
    @PrimaryKey
    val id: String,
    val filename: String,
    val path: String,
    val latitude: Double,
    val longitude: Double,
    val altitude: Double = 0.0,
    val bearing: Double = 0.0,
    val capturedAt: Long,
    val accuracy: Double,
    val width: Int,
    val height: Int,
    val fileSize: Long,
    val createdAt: Long,

    // Upload tracking fields
    val uploadStatus: String = "pending", // pending, uploading, completed, failed
    val uploadedAt: Long = 0L,
    val retryCount: Int = 0,
    val lastUploadAttempt: Long = 0L,
    val uploadError: String = "",
    val fileHash: String = ""
)

enum class UploadStatus {
    PENDING,
    UPLOADING,
    COMPLETED,
    FAILED
}

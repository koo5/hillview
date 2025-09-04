package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.ColumnInfo

@Entity(tableName = "photos")
data class PhotoEntity(
    @PrimaryKey
    val id: String,
    val filename: String,
    val path: String,
    val latitude: Double,
    val longitude: Double,
    val altitude: Double = 0.0,
    val bearing: Double = 0.0,
    val timestamp: Long,
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
    val autoUploadEnabled: Boolean = true,
    val fileHash: String = ""
)

enum class UploadStatus {
    PENDING,
    UPLOADING,
    COMPLETED,
    FAILED
}

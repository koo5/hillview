package io.github.koo5.hillview.plugin

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "photos")
data class PhotoEntity(
    @PrimaryKey
    val id: String,
    val filename: String,
    val path: String,
    val latitude: Double,
    val longitude: Double,
    val altitude: Double?,
    val bearing: Double?,
    val timestamp: Long,
    val accuracy: Double,
    val width: Int,
    val height: Int,
    val fileSize: Long,
    val createdAt: Long,
    
    // Upload tracking fields
    val uploadStatus: String = "pending", // pending, uploading, completed, failed
    val uploadedAt: Long? = null,
    val retryCount: Int = 0,
    val lastUploadAttempt: Long? = null,
    val uploadError: String? = null,
    val autoUploadEnabled: Boolean = true,
    val fileHash: String? = null
)

enum class UploadStatus {
    PENDING,
    UPLOADING, 
    COMPLETED,
    FAILED
}
package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.ForeignKey
import androidx.room.Index

/**
 * Represents a pending edit action on a photo.
 * Edits are processed before the main upload loop, allowing actions like
 * toggling anonymization to trigger a re-upload.
 */
@Entity(
    tableName = "edits",
    foreignKeys = [
        ForeignKey(
            entity = PhotoEntity::class,
            parentColumns = ["id"],
            childColumns = ["photoId"],
            onDelete = ForeignKey.CASCADE
        )
    ],
    indices = [
        Index(value = ["photoId"], name = "idx_edits_photo_id"),
        Index(value = ["createdAt"], name = "idx_edits_created_at")
    ]
)
data class EditEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,

    val photoId: String,

    // JSON describing the edit action
    // Examples:
    // - {"action": "set_anonymization_override", "value": []} - empty list, no anonymization
    // - {"action": "set_anonymization_override", "value": null} - null, use auto-detection
    // - {"action": "set_anonymization_override", "value": [{"x":10,"y":20,"w":100,"h":50}]} - manual rectangles
    val actionJson: String,

    val createdAt: Long = System.currentTimeMillis(),

    // Whether this edit has been processed
    val processed: Boolean = false,
    val processedAt: Long = 0L
)

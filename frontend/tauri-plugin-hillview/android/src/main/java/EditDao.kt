package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

@Dao
interface EditDao {

    @Query("SELECT * FROM edits WHERE processed = 0 ORDER BY createdAt ASC")
    fun getPendingEdits(): List<EditEntity>

    @Query("SELECT * FROM edits WHERE photoId = :photoId AND processed = 0 ORDER BY createdAt ASC")
    fun getPendingEditsForPhoto(photoId: String): List<EditEntity>

    @Query("SELECT * FROM edits WHERE photoId = :photoId ORDER BY createdAt DESC")
    fun getAllEditsForPhoto(photoId: String): List<EditEntity>

    @Query("SELECT COUNT(*) FROM edits WHERE processed = 0")
    fun getPendingEditCount(): Int

    @Insert
    fun insertEdit(edit: EditEntity): Long

    @Update
    fun updateEdit(edit: EditEntity)

    @Query("UPDATE edits SET processed = 1, processedAt = :processedAt WHERE id = :editId")
    fun markProcessed(editId: Long, processedAt: Long = System.currentTimeMillis())

    @Query("DELETE FROM edits WHERE id = :editId")
    fun deleteEdit(editId: Long)

    @Query("DELETE FROM edits WHERE photoId = :photoId")
    fun deleteEditsForPhoto(photoId: String)

    @Query("DELETE FROM edits WHERE processed = 1 AND processedAt < :olderThan")
    fun cleanupOldProcessedEdits(olderThan: Long)
}

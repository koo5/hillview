package cz.hillview.plugin

import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PhotoExportChangeTrackingTest {
    private lateinit var db: PhotoDatabase

    @Before
    fun open() {
        db = Room.inMemoryDatabaseBuilder(
            InstrumentationRegistry.getInstrumentation().targetContext,
            PhotoDatabase::class.java,
        ).addCallback(PhotoExportChangeTracking.callback).allowMainThreadQueries().build()
    }

    @After
    fun close() = db.close()

    private fun insert(id: String = "p1") = db.photoDao().insertPhoto(PhotoEntity(
        id = id, filename = "$id.jpg", path = "/tmp/$id.jpg",
        latitude = null, longitude = null, capturedAt = 1, accuracy = 0.0,
        width = 4, height = 4, fileSize = 16, createdAt = 1,
    ))

    private fun changes(): Map<String, Long> = db.openHelper.writableDatabase
        .query("SELECT photoId, changeId FROM photo_export_changes").use { cursor ->
            buildMap { while (cursor.moveToNext()) put(cursor.getString(0), cursor.getLong(1)) }
        }

    @Test
    fun insertMetadataEditsAndPhysicalDeleteCoalesceWithIncreasingSequence() {
        insert()
        val inserted = changes().getValue("p1")
        db.openHelper.writableDatabase.execSQL("UPDATE photos SET license = 'CC0' WHERE id = 'p1'")
        val edited = changes().getValue("p1")
        assertTrue(edited > inserted)
        db.photoDao().deletePhoto("p1")
        assertTrue(changes().getValue("p1") > edited)
        assertEquals(1, changes().size)
        assertEquals(0, db.photoDao().getTotalPhotoCount())
    }

    @Test
    fun acknowledgingAnExportCannotEraseAnEditThatArrivedDuringWriting() {
        insert()
        val checkpoint = changes().getValue("p1")
        db.openHelper.writableDatabase.execSQL("UPDATE photos SET license = 'CC0' WHERE id = 'p1'")
        db.openHelper.writableDatabase.execSQL(
            "DELETE FROM photo_export_changes WHERE changeId <= ?", arrayOf(checkpoint),
        )
        assertTrue(changes().getValue("p1") > checkpoint)
    }

    @Test
    fun renamingAnIdQueuesBothItsTombstoneAndItsNewState() {
        insert()
        db.openHelper.writableDatabase.execSQL("UPDATE photos SET id = 'renamed' WHERE id = 'p1'")
        val pending = changes()
        assertEquals(setOf("p1", "renamed"), pending.keys)
        assertTrue(pending.getValue("renamed") > pending.getValue("p1"))
    }

    @Test
    fun rollbackDoesNotLeaveAChangeForAPhotoThatWasNeverCommitted() {
        val sql = db.openHelper.writableDatabase
        sql.beginTransaction()
        try {
            insert()
            assertFalse(changes().isEmpty())
        } finally {
            sql.endTransaction()
        }
        assertTrue(changes().isEmpty())
        assertEquals(0, db.photoDao().getTotalPhotoCount())
    }
}

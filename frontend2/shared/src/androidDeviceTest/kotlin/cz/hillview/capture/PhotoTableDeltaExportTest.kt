package cz.hillview.capture

import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import androidx.test.platform.app.InstrumentationRegistry
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoEntity
import java.io.File
import java.io.IOException
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/** Real Room triggers, MediaStore publication, and filesystem failure recovery. */
class PhotoTableDeltaExportTest {
    private val context = object : ContextWrapper(InstrumentationRegistry.getInstrumentation().targetContext) {
        override fun getApplicationContext(): Context = this
        override fun getDatabasePath(name: String): File = super.getDatabasePath("delta-test-$name")
        override fun getSharedPreferences(name: String, mode: Int): SharedPreferences =
            super.getSharedPreferences("delta-test-$name", mode)
    }
    private val prefs get() = context.getSharedPreferences("hillview_photo_dump", Context.MODE_PRIVATE)
    private lateinit var db: PhotoDatabase
    private lateinit var originalFolder: String

    @Before
    fun prepare() {
        originalFolder = PhotoStorage.folderBase
        PhotoStorage.folderBase = "HillviewExportTest-${System.nanoTime()}"
        db = PhotoDatabase.getDatabase(context)
        val sql = db.openHelper.writableDatabase
        db.runInTransaction {
            sql.execSQL("DELETE FROM photos")
            sql.execSQL("DELETE FROM photo_export_changes")
            sql.execSQL("UPDATE photo_export_sequence SET value = 0 WHERE id = 1")
        }
        prefs.edit().clear().commit()
    }

    @After
    fun cleanup() {
        try {
            context.contentResolver.delete(
                MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                "${MediaStore.MediaColumns.RELATIVE_PATH}=?",
                arrayOf("${Environment.DIRECTORY_DOCUMENTS}/${PhotoStorage.folderBase}/"),
            )
        } finally {
            PhotoStorage.folderBase = originalFolder
            prefs.edit().clear().commit()
        }
    }

    private fun photo(id: String) = PhotoEntity(
        id = id, filename = "$id.jpg", path = "/tmp/$id.jpg",
        latitude = null, longitude = null, capturedAt = 1, accuracy = 0.0,
        width = 4, height = 4, fileSize = 16, createdAt = 1,
    )

    private fun dump() = PhotoTableDump.dumpNow(context, "integration test", spaced = false, force = false)

    private fun uri(shard: Int = 0): String {
        val uri = prefs.getString("last_shard_uris", "").orEmpty().split(",")[shard]
        assertTrue(uri.isNotEmpty(), "this test must exercise the real MediaStore path")
        return uri
    }

    private fun text(uri: String): String = context.contentResolver.openInputStream(Uri.parse(uri))!!
        .bufferedReader().use { it.readText() }

    @Test
    fun unchangedDumpsDoNotReplaceTheFileAndOnlyEditedRowsAreAppended() {
        db.photoDao().insertPhotos(listOf(photo("p1"), photo("p2")))
        dump()
        val initialUri = uri()
        val initial = text(initialUri)
        assertTrue(initial.lineSequence().first().endsWith("rows=2"))
        dump()
        assertEquals(initialUri, uri(), "an unchanged table must keep its published MediaStore row")
        assertEquals(initial, text(uri()))

        db.photoDao().updatePhoto(photo("p1").copy(license = "updated,licence\nvalue"))
        dump()
        val edited = text(uri())
        assertTrue(edited.lineSequence().first().endsWith("rows=3"))
        assertTrue(edited.substringAfter('\n').startsWith(initial.substringAfter('\n')))
        assertTrue(edited.contains("\"updated,licence\nvalue\""))
        db.photoDao().deletePhoto("p2")
        dump()
        val deleted = text(uri())
        assertTrue(deleted.lineSequence().first().endsWith("rows=4"))
        assertTrue(deleted.endsWith(",delete\n"))
    }

    @Test
    fun fullSegmentsStaySealedWhenAnOldPhotoChanges() {
        db.runInTransaction {
            for (i in 0..PHOTO_DUMP_SHARD_ROWS) db.photoDao().insertPhoto(photo("p$i"))
        }
        dump()
        val sealedUri = uri(0)
        val sealed = text(sealedUri)
        assertTrue(sealed.lineSequence().first().endsWith("rows=10000"))
        assertTrue(text(uri(1)).lineSequence().first().endsWith("rows=1"))
        db.photoDao().updatePhoto(photo("p0").copy(license = "CC0"))
        dump()
        assertEquals(sealedUri, uri(0))
        assertEquals(sealed, text(sealedUri))
        assertTrue(text(uri(1)).lineSequence().first().endsWith("rows=2"))
    }

    @Test
    fun recoveryUsesThePublishedCheckpointBeforeAcknowledgingLeftoverChanges() {
        db.photoDao().insertPhotos(listOf(photo("p1"), photo("p2")))
        dump()
        val publishedUri = uri()
        val published = text(publishedUri)
        val checkpoint = prefs.getLong("change_checkpoint", -1L)
        // Simulate death after publication, before checkpoint preferences/acknowledgement.
        prefs.edit().putLong("change_checkpoint", 0L).putInt("active_rows", 0).commit()
        db.openHelper.writableDatabase.execSQL(
            "INSERT INTO photo_export_changes(photoId, changeId) VALUES ('p2', ?)", arrayOf(checkpoint),
        )
        dump()
        assertEquals(publishedUri, uri())
        assertEquals(published, text(uri()))
        assertEquals(checkpoint, prefs.getLong("change_checkpoint", -1L))
        db.openHelper.writableDatabase.query("SELECT COUNT(*) FROM photo_export_changes").use {
            assertTrue(it.moveToFirst())
            assertEquals(0, it.getInt(0))
        }
    }

    @Test
    fun emptyStartPublishesACompleteHeaderAndCanLaterAppendItsFirstPhoto() {
        dump()
        assertTrue(text(uri()).lineSequence().first().endsWith("rows=0"))
        db.photoDao().insertPhoto(photo("first"))
        dump()
        assertTrue(text(uri()).lineSequence().first().endsWith("rows=1"))
        assertTrue(text(uri()).endsWith(",upsert\n"))
    }

    @Test
    fun failedFilesystemWriteLeavesThePreviousCompleteFile() {
        val file = File.createTempFile("photo-export-atomic-", ".csv", context.cacheDir)
        try {
            PhotoTableDump.writeAtomicFile(file) { it.write("complete".toByteArray()) }
            assertFailsWith<IOException> {
                PhotoTableDump.writeAtomicFile(file) {
                    it.write("partial".toByteArray())
                    throw IOException("injected write failure")
                }
            }
            assertEquals("complete", file.readText())
        } finally {
            file.delete()
        }
    }

    @Test
    fun failedMediaStoreStageLeavesThePreviousPublishedFile() {
        val first = PhotoTableDump.writeViaMediaStoreAtomic(
            context, PhotoStorage.folderBase, "photos.csv",
            { it.write("complete".toByteArray()) }, null,
        )
        assertFailsWith<IOException> {
            PhotoTableDump.writeViaMediaStoreAtomic(
                context, PhotoStorage.folderBase, "photos.csv",
                { it.write("partial".toByteArray()); throw IOException("injected write failure") },
                first.uri,
            )
        }
        assertEquals("complete", text(first.uri!!))
        context.contentResolver.query(
            MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
            arrayOf(MediaStore.MediaColumns.DISPLAY_NAME, MediaStore.MediaColumns.IS_PENDING),
            "${MediaStore.MediaColumns.RELATIVE_PATH}=?",
            arrayOf("${Environment.DIRECTORY_DOCUMENTS}/${PhotoStorage.folderBase}/"), null,
        )!!.use {
            assertEquals(1, it.count, "the failed pending row must be removed")
            assertTrue(it.moveToFirst())
            assertEquals("photos.csv", it.getString(0))
            assertEquals(0, it.getInt(1))
        }
    }
}

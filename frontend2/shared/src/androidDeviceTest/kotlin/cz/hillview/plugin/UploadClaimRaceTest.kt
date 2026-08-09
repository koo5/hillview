package cz.hillview.plugin

import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * The refiner-versus-upload race (concern C3), asserted at the level where
 * it is actually decided: two SQL statements and who wins.
 *
 * The hazard: a photo's row is written at the shutter with at-the-time
 * values, the stamp refiner improves it a second or two later, and the
 * upload drain sends whatever it holds. If the drain can snapshot a row,
 * spend time validating (a token refresh, a file hash), and only THEN mark
 * it uploading, a refinement landing in that window is written locally but
 * never uploaded — and device-photos disagrees with the server about where
 * a photo was taken. In-memory database: this is about the statements, not
 * about a session.
 */
class UploadClaimRaceTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var db: PhotoDatabase

    @Before
    fun openDatabase() {
        db = Room.inMemoryDatabaseBuilder(context, PhotoDatabase::class.java).build()
    }

    @After
    fun closeDatabase() {
        db.close()
    }

    private fun insertPending(id: String = "p1") = db.photoDao().insertPhoto(
        PhotoEntity(
            id = id,
            filename = "$id.jpg",
            path = "/tmp/$id.jpg",
            latitude = 50.0,
            longitude = 14.0,
            bearing = 100.0,
            capturedAt = 1_000L,
            accuracy = 5.0,
            width = 4,
            height = 4,
            fileSize = 16,
            createdAt = 1_000L,
            uploadStatus = "pending",
        ),
    )

    @Test
    fun aClaimSucceedsOnceAndTheSecondAttemptLoses() {
        insertPending()
        val dao = db.photoDao()

        assertEquals(1, dao.claimForUpload("p1", "pending", 2_000L), "first claim takes it")
        assertEquals(
            0, dao.claimForUpload("p1", "pending", 3_000L),
            "the row is no longer 'pending', so a second pass must lose and skip",
        )
        assertEquals("uploading", dao.getPhotoById("p1")?.uploadStatus)
    }

    @Test
    fun aRefinementAfterTheClaimCannotLand() {
        // The ordering guarantee the upload depends on: once claimed, the
        // row cannot change under the upload, so what was read after the
        // claim is what the server gets.
        insertPending()
        val dao = db.photoDao()

        assertEquals(1, dao.claimForUpload("p1", "pending", 2_000L))
        val refined = dao.applyRefinedStamp("p1", 51.0, 15.0, 0.0, 200.0, 3_000L)

        assertEquals(0, refined, "applyRefinedStamp must only touch rows still 'pending'")
        val row = assertNotNull(dao.getPhotoById("p1"))
        assertEquals(50.0, row.latitude, 0.0001, "the at-the-time stamp stands")
        assertEquals(null, row.stampRefinedAt, "and the row does not claim to be refined")
    }

    @Test
    fun aRefinementBeforeTheClaimIsWhatGetsUploaded() {
        // The other half: the drain re-reads AFTER claiming, so a refinement
        // that won the race reaches the server rather than being stranded
        // in a snapshot taken before it.
        insertPending()
        val dao = db.photoDao()

        assertEquals(1, dao.applyRefinedStamp("p1", 51.0, 15.0, 0.0, 200.0, 2_000L))
        assertEquals(1, dao.claimForUpload("p1", "pending", 3_000L))

        val uploaded = assertNotNull(dao.getPhotoById("p1"))
        assertEquals(51.0, uploaded.latitude, 0.0001)
        assertEquals(200.0, uploaded.bearing, 0.0001)
        assertNotNull(uploaded.stampRefinedAt, "so the metadata says refined:true")
    }

    @Test
    fun aHeldRowIsInvisibleToTheDrainUntilItsDeadline() {
        // The hold is what makes the race rare rather than routine: the
        // refiner normally finishes and releases before the drain may look.
        db.photoDao().insertPhoto(
            PhotoEntity(
                id = "held", filename = "held.jpg", path = "/tmp/held.jpg",
                latitude = 50.0, longitude = 14.0, capturedAt = 1_000L, accuracy = 5.0,
                width = 4, height = 4, fileSize = 16, createdAt = 1_000L,
                uploadStatus = "pending", uploadHoldUntil = 9_000L,
            ),
        )
        val dao = db.photoDao()

        assertEquals(
            null,
            dao.getNextPhotoForUpload(emptySet(), 0L, 0L, now = 5_000L),
            "still held: the drain must not see it",
        )
        // …and a timestamp, not a status, is what frees it — so a crash
        // mid-refinement cannot strand the photo forever.
        assertNotNull(
            dao.getNextPhotoForUpload(emptySet(), 0L, 0L, now = 9_001L),
            "past the deadline the row is claimable again with no rescuer",
        )
    }
}

package cz.hillview.plugin

import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Before
import org.junit.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The outbox's mechanics, against real SQLite — which is the only place they
 * are real. The compare-and-set, the eligibility join and the upload gate are
 * all SQL, and a host test of them would be a test of nothing.
 */
class PhotoOutboxDaoTest {

    private lateinit var db: PhotoDatabase
    private lateinit var outbox: PhotoOutboxDao
    private lateinit var photos: SimplePhotoDao

    private val me = "user-1"
    private val someoneElse = "user-2"

    @Before
    fun open() {
        db = Room.inMemoryDatabaseBuilder(
            InstrumentationRegistry.getInstrumentation().targetContext,
            PhotoDatabase::class.java,
        ).allowMainThreadQueries().build()
        outbox = db.outboxDao()
        photos = db.photoDao()
    }

    @After
    fun close() = db.close()

    private fun photo(id: String, serverPhotoId: String? = null) = PhotoEntity(
        id = id,
        filename = "$id.jpg",
        path = "/tmp/$id.jpg",
        latitude = 50.1,
        longitude = 14.4,
        capturedAt = 1,
        accuracy = 4.2,
        width = 4,
        height = 4,
        fileSize = 16,
        createdAt = 1,
        serverPhotoId = serverPhotoId,
    ).also { photos.insertPhoto(it) }

    private fun want(photoId: String, kind: String, valueJson: String?, userId: String = me) {
        val now = System.currentTimeMillis()
        db.runInTransaction {
            if (outbox.find(userId, photoId, kind, "") == null) {
                outbox.insert(
                    PhotoOutboxEntity(
                        userId = userId, photoId = photoId, kind = kind,
                        valueJson = valueJson, changedAt = now,
                    ),
                )
            } else {
                outbox.setWanted(userId, photoId, kind, "", valueJson, now)
            }
        }
    }

    /**
     * Like, unlike, like again is ONE row saying "liked" and one call to make.
     * That collapse is the reason this is a state and not a message log.
     */
    @Test
    fun repeatedWishesCollapseIntoOneRow() {
        photo("p1", serverPhotoId = "s1")
        want("p1", OUTBOX_KIND_RATING, """{"rating":"thumbs_up"}""")
        want("p1", OUTBOX_KIND_RATING, null)
        want("p1", OUTBOX_KIND_RATING, """{"rating":"thumbs_up"}""")

        assertEquals(1, outbox.forPhoto(me, "p1").size)
        val row = outbox.find(me, "p1", OUTBOX_KIND_RATING, "")!!
        assertEquals(3L, row.revision)
        assertTrue(row.valueJson!!.contains("thumbs_up"))
        assertTrue(row.dirty)
    }

    /**
     * The whole reason for a revision rather than a timestamp: an edit made
     * while a push is in flight must not be marked clean for the value that
     * was actually sent.
     */
    @Test
    fun aWishChangedMidPushStaysDirty() {
        photo("p1", serverPhotoId = "s1")
        want("p1", OUTBOX_KIND_RATING, """{"rating":"thumbs_up"}""")
        val sent = outbox.find(me, "p1", OUTBOX_KIND_RATING, "")!!.revision

        // The user changes their mind while the request is on the wire.
        want("p1", OUTBOX_KIND_RATING, """{"rating":"thumbs_down"}""")

        assertEquals(0, outbox.markSynced(me, "p1", OUTBOX_KIND_RATING, "", sent))
        assertTrue(outbox.find(me, "p1", OUTBOX_KIND_RATING, "")!!.dirty)

        // The revision that IS current clears it.
        val current = outbox.find(me, "p1", OUTBOX_KIND_RATING, "")!!.revision
        assertEquals(1, outbox.markSynced(me, "p1", OUTBOX_KIND_RATING, "", current))
        assertTrue(!outbox.find(me, "p1", OUTBOX_KIND_RATING, "")!!.dirty)
    }

    /**
     * A wish about a photo the server has never seen is not an error and not
     * a queue entry waiting on a dependency — it is simply not selected yet.
     */
    @Test
    fun aPhotoWithNoServerIdIsNotPushableUntilItHasOne() {
        photo("local", serverPhotoId = null)
        want("local", OUTBOX_KIND_RATING, """{"rating":"thumbs_up"}""")
        assertTrue(outbox.getPushable(me, 10).isEmpty())

        photos.updateServerPhotoId("local", "s-local")
        assertEquals(listOf("local"), outbox.getPushable(me, 10).map { it.photoId })
    }

    @Test
    fun anotherAccountsWishesAreKeptButNeverPushedAsMine() {
        photo("p1", serverPhotoId = "s1")
        want("p1", OUTBOX_KIND_RATING, """{"rating":"thumbs_up"}""", userId = someoneElse)

        assertTrue(outbox.getPushable(me, 10).isEmpty())
        assertEquals(1, outbox.otherAccountCount(me))
        // Kept, not purged: the row is still there for that account.
        assertEquals(1, outbox.getPushable(someoneElse, 10).size)
    }

    /**
     * The "never uploads" half of deleting a photo that has not been sent.
     * The gate is on the candidate queries, so the file is never offered to
     * the drain at all.
     */
    @Test
    fun aWantedDeletionTakesThePhotoOutOfTheUploadQueue() {
        photo("p1")
        val now = System.currentTimeMillis()
        assertEquals(1, photos.getUploadableCandidates(now, now, now).size)

        want("p1", OUTBOX_KIND_DELETE, "{}")
        assertTrue(photos.getUploadableCandidates(now, now, now).isEmpty())
        assertNull(photos.getNextPhotoForUpload(emptySet(), now, now, now))

        // Withdrawn before it was ever sent: the photo is a candidate again.
        want("p1", OUTBOX_KIND_DELETE, null)
        assertEquals(1, photos.getUploadableCandidates(now, now, now).size)
    }

    /**
     * A deletion already accepted by the server still means the photo must
     * not be uploaded — the gate asks what is WANTED, not what is pending.
     */
    @Test
    fun aPushedDeletionStillHoldsTheUploadBack() {
        photo("p1")
        want("p1", OUTBOX_KIND_DELETE, "{}")
        val row = outbox.find(me, "p1", OUTBOX_KIND_DELETE, "")!!
        outbox.markSynced(me, "p1", OUTBOX_KIND_DELETE, "", row.revision)

        val now = System.currentTimeMillis()
        assertTrue(!outbox.find(me, "p1", OUTBOX_KIND_DELETE, "")!!.dirty)
        assertTrue(photos.getUploadableCandidates(now, now, now).isEmpty())
    }

    @Test
    fun failuresAreCountedSoTheyCanBeBackedOff() {
        photo("p1", serverPhotoId = "s1")
        want("p1", OUTBOX_KIND_RATING, """{"rating":"thumbs_down"}""")
        outbox.recordFailure(me, "p1", OUTBOX_KIND_RATING, "", 5_000, "boom")
        val row = outbox.find(me, "p1", OUTBOX_KIND_RATING, "")!!
        assertEquals(1, row.attempts)
        assertEquals(5_000, row.lastAttemptAt)
        assertEquals("boom", row.lastError)
        assertTrue(row.dirty)
    }
}

package cz.hillview.plugin

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * When a failed outbox row is allowed to try again, and the one thing the
 * dirty flag must mean.
 */
class PhotoOutboxBackoffTest {

    private fun row(attempts: Int, lastAttemptAt: Long, revision: Long = 1, synced: Long = 0) =
        PhotoOutboxEntity(
            userId = "u1",
            photoId = "p1",
            kind = OUTBOX_KIND_RATING,
            valueJson = """{"rating":"thumbs_up"}""",
            revision = revision,
            syncedRevision = synced,
            changedAt = 0,
            attempts = attempts,
            lastAttemptAt = lastAttemptAt,
        )

    @Test
    fun aFreshRowGoesAtOnce() {
        assertTrue(PhotoOutboxPusher.isDueNow(row(attempts = 0, lastAttemptAt = 0), now = 0))
    }

    @Test
    fun aFailedRowWaitsAndThenGoes() {
        val failedAt = 1_000_000L
        val once = row(attempts = 1, lastAttemptAt = failedAt)
        assertFalse(PhotoOutboxPusher.isDueNow(once, failedAt + 29_000))
        assertTrue(PhotoOutboxPusher.isDueNow(once, failedAt + 30_000))
    }

    @Test
    fun theWaitGrowsWithTheFailures() {
        val at = 1_000_000L
        assertFalse(PhotoOutboxPusher.isDueNow(row(attempts = 2, lastAttemptAt = at), at + 60_000))
        assertTrue(PhotoOutboxPusher.isDueNow(row(attempts = 2, lastAttemptAt = at), at + 120_000))
        // ...and stops growing, rather than running off into days.
        val many = row(attempts = 99, lastAttemptAt = at)
        assertTrue(PhotoOutboxPusher.isDueNow(many, at + 60 * 60_000))
    }

    /**
     * Dirty is "the server has not accepted what I now want" — not "I have
     * never pushed". A row pushed once and edited again is dirty again.
     */
    @Test
    fun dirtyIsAComparisonNotAFlag() {
        assertTrue(row(0, 0, revision = 1, synced = 0).dirty)
        assertFalse(row(0, 0, revision = 1, synced = 1).dirty)
        assertTrue(row(0, 0, revision = 2, synced = 1).dirty)
    }
}

package cz.hillview.plugin

import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * The in-app event log's ring semantics. On a device because it writes to
 * android.util.Log on every record, which a host JVM test would have to
 * mock — and the mocking would be the only thing under test.
 */
class EventLogTest {

    @Before
    fun emptyTheRing() {
        EventLog.clear()
    }

    @Test
    fun newestComesFirst() {
        // A log you are chasing is read from the top: the thing that just
        // happened is the thing you came to see.
        EventLog.record("upload", "first")
        EventLog.record("upload", "second")

        val snapshot = EventLog.snapshot()
        assertEquals("second", snapshot.first().message)
        assertEquals("first", snapshot.last().message)
    }

    @Test
    fun theRingDropsTheOldestRatherThanGrowingForever() {
        // A capture session can run for hours; unbounded history would be a
        // leak, and the recent past is what the log is for.
        repeat(600) { EventLog.record("capture", "shot $it") }

        val snapshot = EventLog.snapshot()
        assertEquals(500, snapshot.size)
        assertEquals("shot 599", snapshot.first().message, "newest kept")
        assertEquals("shot 100", snapshot.last().message, "oldest dropped")
    }

    @Test
    fun categoriesAreWhatTheFilterChipsOffer() {
        EventLog.record("upload", "a")
        EventLog.record("geo", "b")
        EventLog.record("upload", "c")

        assertEquals(listOf("geo", "upload"), EventLog.categories())
    }

    @Test
    fun eventsCarryTheirOwnTime() {
        val before = System.currentTimeMillis()
        EventLog.record("upload", "stamped")
        val event = EventLog.snapshot().first()

        assertTrue(
            event.atMs >= before && event.atMs <= System.currentTimeMillis(),
            "an event without a usable timestamp cannot be correlated with anything",
        )
    }
}

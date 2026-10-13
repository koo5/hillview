package cz.hillview.plugin

import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.junit.After
import org.junit.Before
import org.junit.Test

/**
 * The keyset the CSV export pages by — asserted against real SQL, because that is where
 * the claim lives.
 *
 * WHY IT EXISTS. `getAllSamples()` materialised the whole table and `imuSamplesToCsv`
 * joined it into one String; at ~720 rows/s stored during an interval run, a table that
 * had missed a few dumps held a million rows, the StringBuilder grew to 131 MB against a
 * 268 MB heap and the app died. The clear at the end of the dump then never ran, so the
 * table grew and the next dump died harder — a self-reinforcing loop (crash report
 * 2026-10-09, build d5a5699c).
 *
 * The export now pages. Paging is only safe if it covers every row EXACTLY once, and the
 * hard case is the one the composite key exists for: two sensors reporting the same
 * millisecond, and one sensor reporting twice within it. An OFFSET would also "work"
 * here and is what this deliberately is not — see `ImuDao.samplesAfter`.
 */
class ImuCsvPagingTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private lateinit var db: GeoTrackingDatabase

    @Before
    fun openDatabase() {
        db = Room.inMemoryDatabaseBuilder(context, GeoTrackingDatabase::class.java).build()
    }

    @After
    fun closeDatabase() {
        db.close()
    }

    /** Walk the table the way writeImuSamplesCsv does, and return what it saw. */
    private fun pageThrough(pageRows: Int): List<Triple<Long, String, Int>> {
        val seen = mutableListOf<Triple<Long, String, Int>>()
        var ts = Long.MIN_VALUE
        var kind = ""
        var seq = Int.MIN_VALUE
        while (true) {
            val page = db.imuDao().samplesAfter(ts, kind, seq, pageRows)
            if (page.isEmpty()) break
            page.forEach { seen += Triple(it.timestamp, it.kind, it.sequence) }
            val last = page.last()
            ts = last.timestamp
            kind = last.kind
            seq = last.sequence
            if (page.size < pageRows) break
        }
        return seen
    }

    private fun insert(rows: List<ImuSampleEntity>) = db.imuDao().insertAll(rows)

    /**
     * THE HARD CASE: both sensors on the same millisecond, several samples each. A key of
     * `timestamp` alone would skip or repeat whole millisecond groups at a page boundary.
     */
    @Test
    fun pagingCoversEveryRowExactlyOnceAcrossSameMillisecondGroups() {
        val rows = mutableListOf<ImuSampleEntity>()
        for (ms in 1_000L until 1_050L) {
            for (kind in listOf("accel", "gyro")) {
                for (seq in 0 until 3) {
                    rows += ImuSampleEntity(ms, kind, seq, 1f, 2f, 3f, ms * 1_000_000)
                }
            }
        }
        insert(rows)
        assertEquals(300, db.imuDao().count())

        // Page sizes chosen to land boundaries INSIDE a millisecond group, which is the
        // case a timestamp-only keyset gets wrong: 300 rows in groups of 6.
        for (pageRows in listOf(1, 2, 4, 5, 7, 299, 300, 301)) {
            val seen = pageThrough(pageRows)
            assertEquals(300, seen.size, "page size $pageRows saw ${seen.size} rows")
            assertEquals(300, seen.distinct().size, "page size $pageRows repeated a row")
            assertEquals(
                seen.sortedWith(compareBy({ it.first }, { it.second }, { it.third })), seen,
                "page size $pageRows returned rows out of the table's order",
            )
        }
    }

    /** An empty table pages to nothing rather than looping or throwing. */
    @Test
    fun anEmptyTablePagesToNothing() {
        assertEquals(0, db.imuDao().count())
        assertTrue(pageThrough(5_000).isEmpty())
    }

    /**
     * The first page must include the very first row. `Long.MIN_VALUE` as the starting
     * key is what makes the comparison strictly-greater work from nothing, and a
     * timestamp of 0 — the value an unstamped sample would carry — must not be skipped.
     */
    @Test
    fun theFirstPageIncludesTheFirstRowEvenAtTimestampZero() {
        insert(
            listOf(
                ImuSampleEntity(0L, "accel", 0, 1f, 1f, 1f, 0L),
                ImuSampleEntity(1L, "accel", 0, 1f, 1f, 1f, 1L),
            ),
        )
        assertEquals(2, pageThrough(5_000).size)
        assertEquals(Triple(0L, "accel", 0), pageThrough(1).first())
    }

    /**
     * Rows arriving DURING a dump — the engine keeps writing. A later row is picked up by
     * a later page or left for the next dump; what must never happen is a row written
     * twice, because the keyset is strictly greater than everything already emitted.
     */
    @Test
    fun aRowArrivingMidDumpIsNeverWrittenTwice() {
        insert((0 until 10).map { ImuSampleEntity(it.toLong(), "accel", 0, 1f, 1f, 1f, 0L) })
        val seen = mutableListOf<Triple<Long, String, Int>>()
        var ts = Long.MIN_VALUE
        var kind = ""
        var seq = Int.MIN_VALUE
        var inserted = false
        while (true) {
            val page = db.imuDao().samplesAfter(ts, kind, seq, 4)
            if (page.isEmpty()) break
            page.forEach { seen += Triple(it.timestamp, it.kind, it.sequence) }
            val last = page.last()
            ts = last.timestamp; kind = last.kind; seq = last.sequence
            if (!inserted) {
                // One BEHIND the cursor and one ahead: the first must not reappear.
                insert(
                    listOf(
                        ImuSampleEntity(0L, "gyro", 0, 1f, 1f, 1f, 0L),
                        ImuSampleEntity(99L, "accel", 0, 1f, 1f, 1f, 0L),
                    ),
                )
                inserted = true
            }
            if (page.size < 4) break
        }
        assertEquals(seen.size, seen.distinct().size, "a row was emitted twice: $seen")
        assertTrue(seen.contains(Triple(99L, "accel", 0)), "the row ahead of the cursor was missed")
    }
}

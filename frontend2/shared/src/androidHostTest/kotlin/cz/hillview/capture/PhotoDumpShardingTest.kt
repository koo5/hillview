package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * How the index stays affordable as the table grows (user-raised: "space the
 * dumps more once it's in thousands of rows, and switch to a new file after
 * 10k rows perhaps?").
 *
 * Two knobs, and they answer different halves of the worry: sharding bounds
 * the WRITE, so one more photo rewrites one file however many there are;
 * spacing bounds how often the read happens at all.
 */
class PhotoDumpShardingTest {

    @Test
    fun anEmptyTableStillHasOneFile() {
        // A file that says "no photos" and a missing file must not look
        // alike, so there is always at least one.
        assertEquals(1, shardCount(0))
        assertEquals(1, shardCount(-1))
    }

    @Test
    fun aShardIsFullBeforeTheNextOneStarts() {
        assertEquals(1, shardCount(1))
        assertEquals(1, shardCount(PHOTO_DUMP_SHARD_ROWS - 1))
        assertEquals(1, shardCount(PHOTO_DUMP_SHARD_ROWS))
        assertEquals(2, shardCount(PHOTO_DUMP_SHARD_ROWS + 1))
        assertEquals(2, shardCount(PHOTO_DUMP_SHARD_ROWS * 2))
        assertEquals(3, shardCount(PHOTO_DUMP_SHARD_ROWS * 2 + 1))
    }

    /** The first file keeps the plain name; nobody with 300 photos sees a number. */
    @Test
    fun theFirstFileIsJustPhotosCsv() {
        assertEquals("photos.csv", photoDumpFileName(0))
        assertEquals("photos-2.csv", photoDumpFileName(1))
        assertEquals("photos-3.csv", photoDumpFileName(2))
    }

    @Test
    fun everyShardHasItsOwnName() {
        val names = (0 until 12).map { photoDumpFileName(it) }
        assertEquals(names.size, names.distinct().size)
        assertTrue(names.all { it.endsWith(".csv") })
    }

    @Test
    fun thePulseSlowsAsTheTableGrows() {
        val sizes = listOf(0, 999, 1_000, 9_999, 10_000, 49_999, 50_000, 500_000)
        val intervals = sizes.map { photoDumpIntervalMs(it) }
        assertEquals(intervals.sorted(), intervals, "a bigger table must never dump MORE often")
        assertEquals(2 * 60_000L, photoDumpIntervalMs(0))
        assertEquals(10 * 60_000L, photoDumpIntervalMs(1_000))
        assertEquals(30 * 60_000L, photoDumpIntervalMs(10_000))
        assertEquals(60 * 60_000L, photoDumpIntervalMs(50_000))
    }

    /**
     * The number of files tracks the number of photos, which is the whole
     * reason not to write one per day: a phone that shot nothing this month
     * gains no files, and one with 40k photos has four rather than a year of
     * dated leftovers.
     */
    @Test
    fun theFileCountFollowsThePhotosAndNotTheCalendar() {
        assertEquals(1, shardCount(300))
        assertEquals(4, shardCount(40_000))
        assertEquals(10, shardCount(100_000))
    }
}

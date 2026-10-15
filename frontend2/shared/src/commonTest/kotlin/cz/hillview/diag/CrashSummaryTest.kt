package cz.hillview.diag

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The line a bug report gets pasted into.
 *
 * It was the same `firstOrNull { contains("Exception") }` written twice — in the Event
 * log screen and in the Application — and the two had already drifted in what they said
 * when nothing matched. A crash summary is read by someone who cannot attach a cable, so
 * "trace available" versus "see Event log → Copy crash" is the difference between them
 * knowing there is more and assuming that was all of it.
 */
class CrashSummaryTest {

    /** The shape CrashLog.report() actually writes: three header lines, then the trace. */
    private fun report(trace: String) = """
        build: 0.1.0 · e1b1dd5e · 2026-10-09T10:00:00+00:00
        at: Thu Oct 09 12:34:56 GMT+02:00 2026
        thread: main

        $trace
    """.trimIndent()

    @Test
    fun itSkipsTheHeaderAndFindsTheException() {
        val line = crashSummaryLine(
            report(
                "java.lang.IllegalStateException: no camera bound\n" +
                    "\tat cz.hillview.capture.AndroidPhotoCapture.capture(PhotoCapture.android.kt:1704)",
            ),
        )
        assertEquals("java.lang.IllegalStateException: no camera bound", line)
    }

    /** An Error is a crash too, and the commoner one for a native or OOM death. */
    @Test
    fun itFindsAnErrorAsWellAsAnException() {
        val line = crashSummaryLine(report("java.lang.OutOfMemoryError: Failed to allocate"))
        assertTrue(line.startsWith("java.lang.OutOfMemoryError"), line)
    }

    /**
     * Nothing matched — a trace with neither word in it, which happens for a Kotlin
     * error class that is named for its problem rather than its kind. The summary must
     * then POINT AT THE BUTTON rather than describing nothing, which is the drift the
     * two copies had.
     */
    @Test
    fun withNothingRecognisableItPointsAtTheButton() {
        val line = crashSummaryLine(report("kotlin.NotImplementedError"))
        // ...that one does contain "Error". The real fallback case:
        assertTrue(crashSummaryLine(report("something went wrong")).contains("Copy crash"))
    }

    /** Long lines are cut, with a mark saying so rather than ending mid-word silently. */
    @Test
    fun aLongLineIsTruncatedVisibly() {
        val long = "java.lang.IllegalStateException: " + "x".repeat(400)
        val line = crashSummaryLine(report(long))
        assertEquals(121, line.length, "120 plus the ellipsis")
        assertTrue(line.endsWith("…"))
    }

    /** The header is skipped even when it is all there is — an empty trace. */
    @Test
    fun aReportWithNoTraceStillSaysSomethingUseful() {
        assertTrue(crashSummaryLine(report("")).contains("Copy crash"))
    }
}

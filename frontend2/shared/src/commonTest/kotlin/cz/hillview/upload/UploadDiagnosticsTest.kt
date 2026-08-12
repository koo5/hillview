package cz.hillview.upload

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * The one piece of reasoning the diagnostics page does: pick the headline.
 *
 * Everything else on that page is a value read from somewhere that already
 * knew it, which is the design rule. This is the exception, so it is the
 * part worth pinning.
 */
class UploadDiagnosticsTest {

    private fun diag(vararg rows: DiagRow) = UploadDiagnostics(rows.toList(), takenAtMs = 0)

    @Test
    fun theHeadlineIsTheFirstBlockingRow() {
        // "First" is deliberate: the rows are built in the order the drain
        // itself checks them, so the earliest failure is the one to fix.
        val d = diag(
            DiagRow("Auto-upload", "on", DiagVerdict.Ok),
            DiagRow("Licence", "not accepted", DiagVerdict.Blocking),
            DiagRow("Signed in", "no", DiagVerdict.Blocking),
        )
        assertEquals("Licence", d.blocker?.label)
    }

    @Test
    fun nothingBlockingMeansNoHeadline() {
        val d = diag(
            DiagRow("Auto-upload", "on", DiagVerdict.Ok),
            DiagRow("Queue", "3 pending", DiagVerdict.Info),
        )
        assertNull(d.blocker, "Info rows are context, never a reason to be stopped")
    }

    @Test
    fun anEmptyReportBlamesNothing() {
        assertNull(diag().blocker)
    }
}

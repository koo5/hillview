package cz.hillview.diag

import android.os.Debug
import android.util.Log
import cz.hillview.plugin.EventLog
import cz.hillview.plugin.GeoTrackingManager
import cz.hillview.plugin.hvTag
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * The Java heap over time, where it survives without a cable (2026-11-06).
 *
 * Two OutOfMemoryErrors in two days (hillview-geo in GeomagneticField, then the photo
 * dump escaping a 1 KB CSV cell) each died on a small allocation with the 256 MB heap
 * already full — so the trace named a victim, never the culprit. What a trace cannot
 * say, a series can: WHEN the heap started to climb, how fast, and what the app was
 * doing then (the event log around it).
 *
 * Every [SAMPLE_MS] (2 s) a line goes to logcat. The event log, which holds 500 entries of
 * everything and is what a phone in the field keeps, gets one only when the heap has
 * moved by [RECORD_STEP_BYTES] since the last one or [RECORD_EVERY_MS] has passed — a
 * steady app adds two lines an hour, a climbing one draws its own curve.
 *
 * Beside the heap: the tracking-write queue's depth (GeoTrackingManager's bounded
 * writer, the suspect capped the same day at ~32 MB). A climb that the queue's MB
 * accounts for points there; a climb with the queue near zero clears it.
 */
object HeapLog {
    private val TAG = hvTag("Heap")
    // Every 2 s while the OOM is being hunted (user, 2026-11-06: "make it more frequent
    // for now"). It is the LOGCAT cadence; the event log keeps its change-based rule
    // below, since a line every 2 s would roll its 500 entries over in 17 minutes and
    // take the crash context with them.
    private const val SAMPLE_MS = 2_000L
    private const val RECORD_EVERY_MS = 30 * 60_000L
    private const val RECORD_STEP_BYTES = 16L * 1024 * 1024
    private const val MIB = 1024 * 1024

    @Volatile private var started = false

    fun start() {
        if (started) return
        started = true
        CoroutineScope(SupervisorJob() + Dispatchers.Default).launch {
            var lastRecordedUsed = -1L
            var lastRecordedAt = 0L
            while (true) {
                try {
                    val rt = Runtime.getRuntime()
                    val used = rt.totalMemory() - rt.freeMemory()
                    val line = "heap ${used / MIB}/${rt.maxMemory() / MIB} MB" +
                        " · native ${Debug.getNativeHeapAllocatedSize() / MIB} MB" +
                        (GeoTrackingManager.pendingWritesIfRunning()?.let { n ->
                            val bytes = GeoTrackingManager.pendingWriteBytesIfRunning() ?: 0L
                            " · tracking queue $n (~${bytes / MIB} MB)"
                        } ?: "")
                    Log.i(TAG, line)
                    val now = android.os.SystemClock.elapsedRealtime()
                    if (lastRecordedUsed < 0 ||
                        kotlin.math.abs(used - lastRecordedUsed) >= RECORD_STEP_BYTES ||
                        now - lastRecordedAt >= RECORD_EVERY_MS
                    ) {
                        EventLog.record("heap", line)
                        lastRecordedUsed = used
                        lastRecordedAt = now
                    }
                } catch (e: Throwable) {
                    // A probe must never be what takes the app down — and when the heap
                    // is this full, skipping one sample is all there is to do.
                    if (e is OutOfMemoryError) Log.w(TAG, "heap sample skipped: out of memory")
                    else Log.w(TAG, "heap sample failed", e)
                }
                delay(SAMPLE_MS)
            }
        }
    }
}

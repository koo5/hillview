package cz.hillview.capture

import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CaptureResult
import android.os.SystemClock
import android.util.Log
import java.io.File

private const val TAG = "hv-VideoFrameLog"

/**
 * The sidecar that makes a recording pairable with the geo record.
 *
 * An mp4 CANNOT carry these timestamps: MPEG4Writer rebases presentation
 * timestamps to ~0, and CameraX's VideoTimebaseConverter rewrites
 * REALTIME→UPTIME before the encoder ever sees a frame. So the only place
 * the real per-frame instants exist is the capture session itself, and the
 * only way to keep them is to write them down as they arrive — the
 * conclusion of the per-frame metadata research
 * (docs/frontend2-capture-backlog.md, 2026-08-07).
 *
 * The consumer's side of the contract: the mp4's own sample times
 * (MediaExtractor.getSampleTime) carry the same DELTAS as this list, so the
 * two align by index — or by delta-matching if the encoder dropped frames.
 * That is the technique OpenCamera-Sensors uses for the same problem.
 *
 * [timestampSource] decides how the numbers relate to the tracking tables:
 * REALTIME means they share `elapsedRealtimeNanos` with the sensor stream
 * and pair by nearest neighbour directly; UNKNOWN means roughly uptime, and
 * the anchors written in the header are what a consumer needs to shift them.
 */
class VideoFrameLog(private val timestampSource: Int?) {

    private data class Frame(
        val sensorTimestampNs: Long,
        val exposureNs: Long?,
        val iso: Int?,
    )

    private val frames = ArrayList<Frame>(2048)

    /** Wall/monotonic anchors, taken as close to the first frame as possible. */
    @Volatile private var startedWallMs: Long = 0
    @Volatile private var startedElapsedNs: Long = 0

    fun onRecordingStarted() {
        startedWallMs = System.currentTimeMillis()
        startedElapsedNs = SystemClock.elapsedRealtimeNanos()
    }

    /**
     * One completed capture. Called from the camera thread via
     * Camera2Interop's session capture callback — the route the research
     * settled on, because it needs no extra stream and reports the SAME
     * timestamp that every output buffer of that frame carries.
     */
    fun onFrame(result: CaptureResult) {
        val ts = result.get(CaptureResult.SENSOR_TIMESTAMP) ?: return
        synchronized(frames) {
            frames += Frame(
                sensorTimestampNs = ts,
                // Free, and the only honest answer to "does an exposure
                // rule reach video?" — these are what the sensor DID.
                exposureNs = result.get(CaptureResult.SENSOR_EXPOSURE_TIME),
                iso = result.get(CaptureResult.SENSOR_SENSITIVITY),
            )
        }
    }

    val frameCount: Int get() = synchronized(frames) { frames.size }

    /**
     * Write the sidecar and return it. CSV with a commented header: a human
     * can read it, a script can skip '#'.
     *
     * Beside the video when the platform allows it, otherwise in
     * [fallbackDir]. It usually does NOT allow it: DCIM is a MEDIA
     * collection, and scoped storage lets an app create only media types
     * there — the .mp4 writes fine and the .csv next to it fails with EPERM
     * (device-verified, API 36). The header names the video either way, so
     * pairing survives the split; only the convenience of adjacency is lost.
     */
    fun write(videoFile: File, fallbackDir: File? = null): File? = try {
        val preferred = File(videoFile.parentFile, videoFile.name + ".frames.csv")
        val sidecar = if (canWrite(preferred)) {
            preferred
        } else {
            val dir = fallbackDir?.also { it.mkdirs() }
                ?: throw java.io.IOException("no writable location for the sidecar")
            Log.i(TAG, "sidecar cannot live beside the video (scoped storage); using $dir")
            File(dir, videoFile.name + ".frames.csv")
        }
        val snapshot = synchronized(frames) { frames.toList() }
        val stoppedWallMs = System.currentTimeMillis()
        sidecar.bufferedWriter().use { out ->
            out.write("# hillview video frame log v1\n")
            out.write("# video=${videoFile.name}\n")
            out.write("# timestamp_source=${timestampSourceName(timestampSource)}\n")
            out.write("# started_wall_ms=$startedWallMs\n")
            out.write("# started_elapsed_realtime_ns=$startedElapsedNs\n")
            out.write("# stopped_wall_ms=$stoppedWallMs\n")
            out.write("# frames=${snapshot.size}\n")
            out.write(
                "# sensor_ts_ns is CaptureResult.SENSOR_TIMESTAMP, logged live: the mp4 " +
                    "rebases its own timestamps, so align by index (or by delta if frames " +
                    "were dropped) against MediaExtractor.getSampleTime.\n",
            )
            out.write(
                "# With timestamp_source=REALTIME these share the clock of the bearings/" +
                    "locations tables and pair by nearest neighbour.\n",
            )
            out.write("frame_index,sensor_ts_ns,exposure_ns,iso\n")
            snapshot.forEachIndexed { i, f ->
                out.write("$i,${f.sensorTimestampNs},${f.exposureNs ?: ""},${f.iso ?: ""}\n")
            }
        }
        Log.i(TAG, "wrote ${snapshot.size} frame rows to ${sidecar.absolutePath}")
        sidecar
    } catch (e: Exception) {
        // A video without its sidecar is still a video; it just cannot be
        // paired later. Never fail the recording over it.
        Log.e(TAG, "sidecar write failed for ${videoFile.name}", e)
        null
    }

    /** What the exposure actually was, for the Stats dialog / logs. */
    fun exposureSummary(): String {
        val snapshot = synchronized(frames) { frames.toList() }
        val exposures = snapshot.mapNotNull { it.exposureNs }
        val isos = snapshot.mapNotNull { it.iso }
        if (exposures.isEmpty()) return "no exposure metadata"
        return "exposure ${exposures.min()}..${exposures.max()} ns, " +
            "iso ${isos.minOrNull()}..${isos.maxOrNull()}"
    }

    /** Probe rather than predict: the rule differs by API level and OEM. */
    private fun canWrite(target: File): Boolean = try {
        java.io.FileOutputStream(target, true).close()
        true
    } catch (e: Exception) {
        false
    }

    private fun timestampSourceName(source: Int?): String = when (source) {
        CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME -> "REALTIME"
        CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_UNKNOWN -> "UNKNOWN"
        null -> "UNREPORTED"
        else -> "OTHER($source)"
    }
}

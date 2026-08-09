package cz.hillview.plugin

import android.content.Context
import android.util.Base64
import android.util.Log
import java.io.File
import java.io.FileOutputStream

/**
 * Streams a clock-calibration video into GeoTrackingDumps/, next to the geo
 * CSV dumps, so whatever pulls the CSVs picks the videos up too.
 *
 * The WebView records the composited canvas (camera frame + burned-in
 * phone-time QR) with MediaRecorder and ships it here as base64 chunks in
 * capture order: begin() -> appendChunk()* -> end(). end() optionally writes
 * a metadata sidecar JSON next to the video, sharing its basename.
 *
 * Only one recording can be open at a time. A begin() while a previous
 * recording never reached end() (page closed mid-recording) closes the
 * orphaned stream but keeps its file — a truncated webm is still analyzable.
 */
class ClockVideoWriter(private val context: Context) {
	companion object {
		private const val TAG = "ClockVideoWriter"
	}

	private var stream: FileOutputStream? = null
	private var file: File? = null

	private fun dumpDir(): File {
		val dir = File(context.getExternalFilesDir(null), "GeoTrackingDumps")
		if (!dir.exists()) {
			dir.mkdirs()
		}
		return dir
	}

	@Synchronized
	fun begin(ext: String): String {
		stream?.let {
			Log.w(TAG, "🎬 begin: closing orphaned stream for ${file?.name}")
			it.close()
		}
		val f = File(dumpDir(), "hillview_clockvideo_${System.currentTimeMillis()}.$ext")
		stream = FileOutputStream(f)
		file = f
		Log.i(TAG, "🎬 Recording clock video to ${f.absolutePath}")
		return f.absolutePath
	}

	@Synchronized
	fun appendChunk(base64Data: String): Int {
		val s = stream ?: throw IllegalStateException("clock_video_chunk without clock_video_begin")
		val bytes = Base64.decode(base64Data, Base64.DEFAULT)
		s.write(bytes)
		return bytes.size
	}

	@Synchronized
	fun end(sidecarJson: String?): String {
		val s = stream ?: throw IllegalStateException("clock_video_end without clock_video_begin")
		val f = file!!
		s.flush()
		s.close()
		stream = null
		file = null
		if (!sidecarJson.isNullOrEmpty()) {
			File(f.parentFile, f.nameWithoutExtension + ".json").writeText(sidecarJson)
		}
		Log.i(TAG, "🎬 Finalized clock video ${f.name} (${f.length()} bytes)")
		return f.absolutePath
	}
}

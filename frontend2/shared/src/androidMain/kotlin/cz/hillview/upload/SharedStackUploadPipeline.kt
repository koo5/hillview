package cz.hillview.upload

import android.content.Context
import android.graphics.BitmapFactory
import android.util.Log
import cz.hillview.capture.CaptureStatsLog
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoUploadLogic
import cz.hillview.plugin.PhotoUploadManager
import cz.hillview.plugin.PhotoUtils
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Capture → the shared-kt upload stack (see /shared-kt/README.md): registers
 * the photo in the shared Room DB (PhotoUploadLogic.registerCapturedPhoto —
 * the same ingestion the Tauri app's addPhotoToDatabase command uses, with
 * this class doing what Rust does there: MD5, dimensions, file size) and
 * pokes PhotoUploadManager, whose WorkManager jobs run the drain (coalescing
 * windows, wifi-only, foreground promotion, status sync). Stats come
 * straight from the shared DB's upload-status counts.
 */
private const val TAG = "hv-SharedStackUpload"

class SharedStackUploadPipeline(
    private val context: Context,
    /**
     * Told once the row exists, so the map can show the photo without
     * waiting for a pan — see CaptureEvents for why this is not a
     * placeholder marker.
     */
    private val captureEvents: cz.hillview.capture.CaptureEvents? = null,
) : UploadPipeline {
    private val _stats = MutableStateFlow(QueueStats())
    override val stats: StateFlow<QueueStats> = _stats.asStateFlow()

    private val uploadLogic by lazy { PhotoUploadLogic(context) }

    /**
     * Attach the IMU window's summary to a photo, once the window has closed.
     *
     * Reads the TRACKING TABLE, not the engine. That is the point: a ±3 s window
     * is incomplete at the shutter, so someone has to look later — but the
     * looking must not become a second line to the hardware. The capture path
     * (which owns the engine, and is the allowlisted place to) asks the engine to
     * PERSIST the window; this reads what landed. `OneStateArchitectureTest`
     * rejected the version where this file called `GeoEngine.get` directly, and
     * was right to: this is neither the hardware boundary, a writer adapter, nor
     * a diagnostic.
     *
     * Best-effort throughout. A photo with no window is a fact about the device
     * or the activity — no gyroscope, or an activity that never asked — and
     * never an error.
     */
    /**
     * How long to wait for the engine's deferred write to record its claim.
     *
     * Generous because missing it costs the payload and the wait costs nothing
     * but a coroutine: the write is scheduled on the engine's Handler for the
     * same instant this pass wakes, so in practice the first poll finds it. A
     * timeout means the process was busy, the activity went away, or the IMU was
     * never running — all of which produce a summary and no payload, which is
     * the honest outcome rather than an error.
     */
    private val IMU_CLAIM_WAIT_MS = 5_000L
    private val IMU_CLAIM_POLL_MS = 100L

    private fun scheduleImuWindow(photoId: String, upload: cz.hillview.upload.PendingUpload) {
        val capturedAt = upload.capturedAtMs ?: return
        val half = cz.hillview.geo.IMU_WINDOW_HALF_MS
        kotlinx.coroutines.CoroutineScope(Dispatchers.IO).launch {
            try {
                val db = cz.hillview.plugin.GeoTrackingDatabase.getDatabase(context)
                // WAIT FOR THE CLAIM, not for a clock. This used to sit out the
                // same deadline the engine's deferred write uses
                // (capturedAt + half + settle) and then read the table — two
                // timers, one on the engine's Handler and one here on
                // Dispatchers.IO, with NO ordering between them. So the
                // post-shutter half of the window was present or absent by luck.
                // The claim row is written in the same coroutine as the samples
                // and after them, so its existence proves they landed.
                val readAt = capturedAt + half + cz.hillview.geo.IMU_SETTLE_MARGIN_MS
                kotlinx.coroutines.delay((readAt - System.currentTimeMillis()).coerceAtLeast(0))
                var claim = db.imuClaimDao().get(capturedAt)
                var waited = 0L
                while (claim == null && waited < IMU_CLAIM_WAIT_MS) {
                    kotlinx.coroutines.delay(IMU_CLAIM_POLL_MS)
                    waited += IMU_CLAIM_POLL_MS
                    claim = db.imuClaimDao().get(capturedAt)
                }
                // The FULL window, whoever stored it: the context number, so a
                // reader can tell "the frame sat in 6 s of quiet" from "we only
                // kept 2 s of it".
                val samples = db.imuDao().getInWindow(capturedAt - half, capturedAt + half)
                val stats = cz.hillview.plugin.summariseImuWindow(samples) ?: return@launch
                // What this photo OWNS: exactly the range it claimed. Attribution
                // is data now — derived from the claim, not inferred from a
                // high-water mark and a nominal window, which overlapped between
                // consecutive captures by seconds.
                val owned = claim?.let { c -> db.imuDao().getInWindow(c.fromMs, c.toMs) } ?: emptyList()
                if (claim == null) {
                    Log.w(TAG, "no IMU claim for $photoId after ${waited}ms — window summary only, no payload")
                }
                val json = cz.hillview.capture.motionProvenanceJson(
                    cz.hillview.capture.SensorSnapshot(
                        capturedAtMs = capturedAt,
                        // The point reading the SHUTTER had, carried through so
                        // this rewrite does not drop it.
                        motion = upload.motionSample,
                        imuWindow = cz.hillview.capture.ImuWindow(
                            sampleCount = stats.sampleCount,
                            startMs = stats.startMs,
                            endMs = stats.endMs,
                            accelPeakMps2 = stats.accelPeakMps2,
                            accelPeakDeviationMps2 = stats.accelPeakDeviationMps2,
                            gyroPeakRadS = stats.gyroPeakRadS,
                            storedCount = owned.size,
                        ),
                    ),
                )
                val dao = PhotoDatabase.getDatabase(context).photoDao()
                dao.updateMotionJson(photoId, json)
                // The raw samples themselves — only the OWNED range, so
                // consecutive photos in a run tile rather than each carrying the
                // same six seconds. Capped at the ring's capacity: a payload
                // larger than the buffer that produced it did not come from here.
                dao.updateImuSamplesJson(
                    photoId,
                    if (owned.size > cz.hillview.plugin.IMU_PAYLOAD_MAX_SAMPLES) {
                        Log.w(TAG, "IMU payload for $photoId is ${owned.size} samples, over the cap — dropped")
                        null
                    } else {
                        cz.hillview.plugin.imuSamplesPayloadJson(owned)
                    },
                )
                Log.i(
                    TAG,
                    "IMU window for $photoId: ${stats.sampleCount} samples " +
                        "${stats.startMs}..${stats.endMs}, owns ${owned.size} " +
                        "(claim ${claim?.fromMs}..${claim?.toMs})",
                )
            } catch (e: Exception) {
                Log.w(TAG, "could not attach the IMU window to $photoId: ${e.message}")
            }
        }
    }

    // The stamp refiner: interpolates a fresh row's location/bearing once
    // the bracketing tracking data lands, updates the row in place, and the
    // upload metadata carries the refined values. The hook feeds its
    // outcomes into the capture stats — where the "was it worth it" numbers
    // (metres moved, degrees turned) accumulate per session.
    private val refiner by lazy {
        cz.hillview.plugin.StampRefiner.get(context).also { r ->
            r.onResult = { result ->
                val wall = System.currentTimeMillis()
                cz.hillview.plugin.EventLog.record(
                    "refine",
                    "${result.outcome} after ${result.waitMs}ms" +
                        (result.movedMeters?.let { " · moved %.2fm".format(it) } ?: "") +
                        (result.turnedDegrees?.let { " · turned %.1f°".format(it) } ?: ""),
                )
                CaptureStatsLog.increment("refine ${result.outcome}", wall)
                CaptureStatsLog.record("refine wait", result.waitMs, wall)
                result.movedMeters?.let {
                    CaptureStatsLog.record("refine Δpos(cm)", (it * 100).toLong(), wall)
                }
                result.turnedDegrees?.let {
                    CaptureStatsLog.record("refine Δbearing(0.1°)", (kotlin.math.abs(it) * 10).toLong(), wall)
                }
            }
        }
    }

    override suspend fun onPhotoCaptured(upload: PendingUpload) {
        try {
            withContext(Dispatchers.IO) {
                // filePath is a locator: an absolute path, or a content:// URI
                // when the capture went through MediaStore. Everything below
                // works off the bytes, so both are handled the same way — and
                // the shared upload path reads them the same way too.
                val bytes = PhotoUtils.readBytesFromPath(context, upload.filePath)
                    ?: throw IllegalStateException("could not read ${upload.filePath}")
                // Decode bounds only — no bitmap allocation.
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)

                // Refinement-eligible photos are ingested with the upload
                // gate armed, so the expedited drain cannot outrun the
                // interpolation (the refiner releases it the moment it is
                // done, win or lose; the deadline frees it after a crash).
                val eligible = cz.hillview.plugin.StampRefiner.isEligible(
                    upload.locationSource, upload.bearingSource,
                )
                val photoId = uploadLogic.registerCapturedPhoto(
                    id = null,
                    filename = upload.filename,
                    path = upload.filePath,
                    // Null stays null: a capture with no position (blank first
                    // run, docs/one-state.md) is registered WITHOUT one, and
                    // uploads without one. `?: 0.0` here used to be Null
                    // Island waiting for the gate to be lifted.
                    latitude = upload.latitude,
                    longitude = upload.longitude,
                    altitude = upload.altitude,
                    bearing = upload.bearing,
                    capturedAt = upload.capturedAtMs ?: System.currentTimeMillis(),
                    // The receiver's accuracy radius. 0.0 is this table's
                    // "absent" sentinel (buildUploadMetadata omits it), so a
                    // fix without one, or a hand-claimed position, sends
                    // nothing rather than a fake zero. This used to be a
                    // constant 0.0 on the theory that EXIF GPSHPositioningError
                    // carried it — but the fast-write path writes no EXIF and
                    // the upload sends the row, so it never left the phone.
                    accuracy = upload.accuracyM?.toDouble() ?: 0.0,
                    width = bounds.outWidth.coerceAtLeast(0),
                    height = bounds.outHeight.coerceAtLeast(0),
                    fileSize = bytes.size.toLong(),
                    fileHash = PhotoUtils.calculateHash(bytes),
                    bearingSource = upload.bearingSource,
                    locationSource = upload.locationSource,
                    locationAgeMs = upload.locationAgeMs,
                    exposureJson = upload.exposureJson,
                    license = upload.license,
                    pitch = upload.pitchDeg,
                    altLocationJson = upload.altLocationJson,
                    attitudeJson = upload.attitudeJson,
                    fixJson = upload.fixJson,
                    lensJson = upload.lensJson,
                    motionJson = upload.motionJson,
                    uploadHoldUntil = if (eligible) {
                        System.currentTimeMillis() + cz.hillview.plugin.StampRefiner.UPLOAD_HOLD_MS
                    } else 0,
                )
                if (eligible) {
                    refiner.refineAsync(
                        photoId,
                        upload.capturedAtMs ?: System.currentTimeMillis(),
                        upload.locationSource,
                        upload.bearingSource,
                    )
                }
                // The IMU window around this exposure, once its later half has
                // happened. Scheduled here because this is the first moment the
                // photo HAS an id, and completed by an update to the row — the
                // same shape as the StampRefiner, which also cannot know
                // everything at the shutter. See GeoEngine.persistImuWindowAround
                // for why the symmetric window cannot be taken inline.
                scheduleImuWindow(photoId, upload)

                PhotoUploadManager(context).startAutomaticUpload("capture")
                // After the insert, never before: a refresh that raced the
                // row would query the database and find nothing, which is
                // exactly the bug this exists to fix.
                captureEvents?.photoStored(photoId)
            }
        } catch (e: Exception) {
            // A photo that can't be ingested must not take the app down —
            // the file is still on disk, and the drain's directory scan or a
            // later retry can pick it up.
            Log.e(TAG, "could not ingest ${upload.filePath}", e)
            _stats.value = _stats.value.copy(lastError = e.message ?: "capture ingest failed")
            return
        }
        refreshStats()
    }

    private var lastStatusSyncMs = 0L

    override suspend fun refreshStats() {
        withContext(Dispatchers.IO) {
            val dao = PhotoDatabase.getDatabase(context).photoDao()

            // While photos sit in server-side processing, re-query their
            // status (rate-limited — the stats poll runs every ~2s) so the
            // visible counts converge without waiting for the next drain.
            // The Tauri app gets the same effect from its my-photos page;
            // background convergence still rides the post-drain sync worker.
            if (dao.getProcessingCount() > 0) {
                val now = System.currentTimeMillis()
                if (now - lastStatusSyncMs > 10_000) {
                    lastStatusSyncMs = now
                    try {
                        uploadLogic.syncProcessingPhotosStatus()
                    } catch (e: Exception) {
                        // The stats poll must never throw; the next drain's
                        // sync worker remains the fallback.
                    }
                }
            }

            _stats.value = QueueStats(
                pending = dao.getPendingUploadCount() + dao.getUploadingCount() +
                    dao.getProcessingCount(),
                done = dao.getCompletedUploadCount(),
                failed = dao.getFailedUploadCount(),
                // The stats poll (~2s) is this value's only reader cadence —
                // coarse is fine for a progress twinkle.
                refining = refiner.inFlight.value,
            )
        }
    }

}

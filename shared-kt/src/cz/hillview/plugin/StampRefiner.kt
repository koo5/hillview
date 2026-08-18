package cz.hillview.plugin

import android.content.Context
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

private const val TAG = "🢄StampRefiner"

/**
 * Table-side stamp refinement: replace a photo row's at-the-time values with
 * interpolated ones once the bracketing data exists. The photos table is the
 * canonical stamp (the upload sends the row, not the file's EXIF), so a
 * refined row reaches the server with no file rewrite — and a photo the
 * upload grabs first simply keeps its at-the-time stamp, which is the
 * designed worst case. Never re-uploads, never blocks the shutter.
 *
 * What refinement means per stream:
 *  - LOCATION (source "gps"): the live stamp is the latest fix, up to one
 *    fix-interval stale. Interpolate linearly between the fixes bracketing
 *    the shutter instant.
 *  - COMPASS BEARING (source "android…"): the live stamp is the single
 *    latest ~10 Hz sample — raw (EMA_ALPHA is currently 1, a pass-through)
 *    and causal. Recompute as the circular mean of a window CENTERED on the
 *    shutter: adds the smoothing the live value doesn't have, with zero
 *    phase lag. (If EnhancedSensorService ever smooths again, its own lag
 *    would remain baked into the samples — these two constants are one
 *    design.) An empty window means the heading wasn't changing (the 1°
 *    dead-band suppresses idle samples) — the at-the-time value stands.
 *  - CAR BEARING (source "gps-kalman"): rows are written per fix with the
 *    mount offset already composed in; interpolate the bracketing rows
 *    along the shortest arc.
 *  - MANUAL anything: never touched — the user placed it.
 */
class StampRefiner private constructor(private val context: Context) {

	companion object {
		@Volatile
		private var INSTANCE: StampRefiner? = null

		fun get(context: Context): StampRefiner =
			INSTANCE ?: synchronized(this) {
				INSTANCE ?: StampRefiner(context.applicationContext)
					.also { INSTANCE = it }
			}

		/** Half-width of the centered compass window (total 600 ms). */
		const val COMPASS_HALF_WINDOW_MS = 300L
		/** Margin past the window end before reading — IO/main hops. */
		const val COMPASS_SETTLE_MARGIN_MS = 150L
		/** How long to wait for the fix AFTER the shutter (~1 Hz cadence). */
		const val BRACKET_TIMEOUT_MS = 4_000L
		const val BRACKET_POLL_MS = 250L
		/**
		 * Fixes further apart than this don't bracket the instant
		 * meaningfully (GPS dropout) — keep the at-the-time value instead
		 * of inventing a straight line across a tunnel.
		 */
		const val MAX_BRACKET_SPAN_MS = 8_000L

		/**
		 * The upload gate an eligible photo is ingested with
		 * (PhotoEntity.uploadHoldUntil = now + this): the drain simply does
		 * not select a photo that is still due for restamping. This is the
		 * PRIMARY mechanism — not a race to be won.
		 *
		 * Which is why the number is nowhere near the refiner's runtime. It
		 * was BRACKET_TIMEOUT + 2 s, i.e. ~1.5 s of headroom over the
		 * refiner's own worst case, so an ordinary GC pause or a dozing
		 * device expired the hold while the refiner was still working and the
		 * two genuinely raced. A deadline is a CRASH BACKSTOP — its job is to
		 * answer "the app died mid-refinement, how long before this photo may
		 * upload anyway", and the honest answer is minutes, not seconds.
		 *
		 * Costing nothing: the refiner clears the hold the instant it
		 * finishes (win or lose) and pokes the drain, so uploads are driven
		 * by completion, never by this expiring. And [clearAllHolds] wipes
		 * stale holds at app start, so an actual crash recovers immediately
		 * rather than waiting this out.
		 */
		const val UPLOAD_HOLD_MS = 60_000L

		// Holds left by a dead process are released by StartupReconciler,
		// alongside the other things a fresh start makes certain.

		/** Whether [refineAsync] would do anything at all for these sources. */
		fun isEligible(locationSource: String?, bearingSource: String?): Boolean =
			locationSource == "gps" ||
				bearingSource?.startsWith("android") == true ||
				bearingSource == "gps-kalman"
	}

	private val database: PhotoDatabase = PhotoDatabase.getDatabase(context)
	private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

	/** How many refinements are in flight — the UI's progress indicator. */
	val inFlight = MutableStateFlow(0)

	/**
	 * Post-refinement hook (any thread): the app records stats/refreshes UI.
	 * shared-kt has no stats sink of its own, so this is the seam.
	 */
	@Volatile
	var onResult: ((RefineResult) -> Unit)? = null

	data class RefineResult(
		val photoId: String,
		/** "applied" | "no-brackets" | "upload-won" | "gone" */
		val outcome: String,
		val waitMs: Long,
		/** How far refinement moved the position, metres (null = location untouched). */
		val movedMeters: Double? = null,
		/** How far it turned the bearing, degrees (null = bearing untouched). */
		val turnedDegrees: Double? = null,
	)

	/**
	 * Schedule refinement for a just-captured photo. Returns false when the
	 * photo isn't eligible at all (manual position AND non-sensor bearing) —
	 * nothing is launched and no indicator flashes.
	 */
	fun refineAsync(
		photoId: String,
		capturedAtMs: Long,
		locationSource: String?,
		bearingSource: String?,
	): Boolean {
		val wantLocation = locationSource == "gps"
		val wantCompass = bearingSource?.startsWith("android") == true
		val wantKalman = bearingSource == "gps-kalman"
		if (!wantLocation && !wantCompass && !wantKalman) return false

		scope.launch {
			inFlight.value = inFlight.value + 1
			// A measured DURATION, so monotonic — it is only ever subtracted.
			val startedAt = android.os.SystemClock.elapsedRealtime()
			try {
				val result = refine(photoId, capturedAtMs, wantLocation, wantCompass, wantKalman)
				onResult?.invoke(result.copy(waitMs = android.os.SystemClock.elapsedRealtime() - startedAt))
			} catch (e: Exception) {
				Log.e(TAG, "refinement of $photoId failed", e)
			} finally {
				inFlight.value = inFlight.value - 1
				// Release the upload gate whatever happened, then wake the
				// drain — the hold made it skip this row, so without a poke
				// the photo would wait for the next trigger.
				try {
					database.photoDao().clearUploadHold(photoId)
					PhotoUploadManager(context).startAutomaticUpload("refine")
				} catch (e: Exception) {
					Log.w(TAG, "hold release for $photoId failed (deadline will free it)", e)
				}
			}
		}
		return true
	}

	private suspend fun refine(
		photoId: String,
		t: Long,
		wantLocation: Boolean,
		wantCompass: Boolean,
		wantKalman: Boolean,
	): RefineResult {
		val bearingDao = database.bearingDao()
		val locationDao = database.locationDao()
		val androidId = database.sourceDao().getSourceIdByName("android")
		val kalmanId = database.sourceDao().getSourceIdByName("gps-kalman")

		// Compass first: its window closes shortly after the shutter.
		var refinedBearing: Double? = null
		if (wantCompass && androidId != null) {
			delay((t + COMPASS_HALF_WINDOW_MS + COMPASS_SETTLE_MARGIN_MS - System.currentTimeMillis()).coerceAtLeast(0))
			val samples = bearingDao.getBearingsInWindow(
				t - COMPASS_HALF_WINDOW_MS, t + COMPASS_HALF_WINDOW_MS, androidId,
			)
			if (samples.isNotEmpty()) {
				refinedBearing = circularMeanDeg(samples.map { it.trueHeading.toDouble() })
			}
		}

		// The fix after the shutter arrives on the ~1 Hz cadence — poll for
		// it (both the location bracket and the kalman bracket need it).
		var refinedLat: Double? = null
		var refinedLon: Double? = null
		var refinedAlt: Double? = null
		if (wantLocation && androidId != null) {
			val after = awaitRow(t) { locationDao.getLocationAfter(t, androidId) }
			val before = locationDao.getLocationAtOrBefore(t, androidId)
			if (before != null && after != null &&
				after.timestamp - before.timestamp <= MAX_BRACKET_SPAN_MS
			) {
				val f = fraction(before.timestamp, after.timestamp, t)
				refinedLat = lerp(before.latitude, after.latitude, f)
				refinedLon = lerp(before.longitude, after.longitude, f)
				if (before.altitude != null && after.altitude != null) {
					refinedAlt = lerp(before.altitude, after.altitude, f)
				}
			}
		}
		if (wantKalman && kalmanId != null) {
			val after = awaitRow(t) { bearingDao.getBearingAfter(t, kalmanId) }
			val before = bearingDao.getBearingAtOrBefore(t, kalmanId)
			if (before != null && after != null &&
				after.timestamp - before.timestamp <= MAX_BRACKET_SPAN_MS
			) {
				val f = fraction(before.timestamp, after.timestamp, t)
				refinedBearing = circularLerpDeg(
					before.trueHeading.toDouble(), after.trueHeading.toDouble(), f,
				)
			}
		}

		if (refinedBearing == null && refinedLat == null) {
			return RefineResult(photoId, "no-brackets", 0)
		}

		// Read-modify-write is safe against the drain because the UPDATE
		// itself re-checks 'pending' — worst case the update matches zero
		// rows and the photo keeps (and has uploaded) its at-the-time stamp.
		val row = database.photoDao().getPhotoById(photoId)
			?: return RefineResult(photoId, "gone", 0)
		val newLat = refinedLat ?: row.latitude
		val newLon = refinedLon ?: row.longitude
		val newAlt = refinedAlt ?: row.altitude
		val newBearing = refinedBearing ?: row.bearing
		val updated = database.photoDao().applyRefinedStamp(
			photoId, newLat, newLon, newAlt, newBearing, System.currentTimeMillis(),
		)
		if (updated == 0) return RefineResult(photoId, "upload-won", 0)

		val moved = if (refinedLat != null) {
			distanceMeters(row.latitude, row.longitude, newLat, newLon)
		} else null
		val turned = if (refinedBearing != null) {
			angularDiffDeg(row.bearing, newBearing)
		} else null
		Log.i(
			TAG,
			"refined $photoId: pos ${row.latitude},${row.longitude} -> $newLat,$newLon " +
				"(${moved?.let { "%.2f m".format(it) } ?: "untouched"}), " +
				"bearing ${row.bearing} -> $newBearing " +
				"(${turned?.let { "%.1f°".format(it) } ?: "untouched"})",
		)
		return RefineResult(photoId, "applied", 0, moved, turned)
	}

	// MONOTONIC deadline: a wall-clock one can be pushed further away by a
	// backward time step, and this loop holds the photo's uploadHoldUntil while
	// it spins. Note the CONTRAST with the window arithmetic in refine(), which
	// stays on the wall clock on purpose — there the reference point is the
	// photo's capture time, a wall-clock instant.
	private suspend fun <T> awaitRow(t: Long, query: () -> T?): T? {
		val deadline = android.os.SystemClock.elapsedRealtime() + BRACKET_TIMEOUT_MS
		while (true) {
			query()?.let { return it }
			if (android.os.SystemClock.elapsedRealtime() >= deadline) return null
			delay(BRACKET_POLL_MS)
		}
	}
}

// The arithmetic, bare for the host tests.

internal fun lerp(a: Double, b: Double, f: Double): Double = a + (b - a) * f

internal fun fraction(from: Long, to: Long, at: Long): Double =
	if (to == from) 0.0 else (at - from).toDouble() / (to - from).toDouble()

/** Mean direction of angles in degrees (vector mean — wraparound-safe). */
internal fun circularMeanDeg(valuesDeg: List<Double>): Double {
	var sinSum = 0.0
	var cosSum = 0.0
	for (v in valuesDeg) {
		val r = Math.toRadians(v)
		sinSum += sin(r)
		cosSum += cos(r)
	}
	return (Math.toDegrees(atan2(sinSum, cosSum)) + 360.0) % 360.0
}

/** Interpolate along the SHORTEST arc — 350°→10° passes through 0, not 180. */
internal fun circularLerpDeg(a: Double, b: Double, f: Double): Double {
	val delta = angularDiffDeg(a, b)
	return ((a + delta * f) % 360.0 + 360.0) % 360.0
}

/** Signed smallest difference b−a, in (−180, 180]. */
internal fun angularDiffDeg(a: Double, b: Double): Double {
	var d = (b - a) % 360.0
	if (d > 180.0) d -= 360.0
	if (d <= -180.0) d += 360.0
	return d
}

// Distance deltas use HeadingFilter's haversine (distanceMeters) — one
// implementation for the whole plugin.

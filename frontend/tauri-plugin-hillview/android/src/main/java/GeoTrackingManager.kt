package cz.hillview.plugin

/*
 GeoTrackingManager is responsible for storing geolocation and orientation datapoints. It should be usable from both ExamplePlugin and a future foreground service.

*/

import android.content.Context
import android.util.Log
import app.tauri.plugin.JSObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.util.concurrent.ConcurrentHashMap

private const val TAG = "Geo"


data class OrientationSensorData(
	val magneticHeading: Float,  // Compass bearing in degrees from magnetic north (0-360°)
	val trueHeading: Float,       // Compass bearing corrected for magnetic declination
	val accuracyLevel: Int,      // Android sensor accuracy constants: -1=unknown, 0=unreliable, 1=low, 2=medium, 3=high
	val pitch: Float,
	val roll: Float,
	val timestamp: Long,
	val source: String      // Identifies which sensor provided the data
)


class GeoTrackingManager(private val context: Context) {
	private val database: PhotoDatabase = PhotoDatabase.getDatabase(context)

	// Cache for source name -> source ID mapping to avoid frequent DB lookups
	private val sourceIdCache = ConcurrentHashMap<String, Int>()

	private val databaseStorageIntervalMs: Long = 10

	private var lastOrientationStorageTime: Long = 0
	private var lastLocationStorageTime: Long = 0

	// GPS-derived heading estimator (car mode). Kept here so the filter state
	// survives across GPS ticks independently of the frontend.
	// NOTE: temporary source tag `gps-kalman-raw` — step 3 composes it with
	// mount offset and writes the composed value under `gps-kalman`.
	private val headingFilter = HeadingFilter()

	private fun rateLimitOrientationStorage(): Boolean {
		val currentTime = System.currentTimeMillis()
		val ok = (currentTime - lastOrientationStorageTime >= databaseStorageIntervalMs)
		lastOrientationStorageTime = currentTime
		return ok
	}

	private fun rateLimitLocationStorage(): Boolean {
		val currentTime = System.currentTimeMillis()
		val ok = (currentTime - lastLocationStorageTime >= databaseStorageIntervalMs)
		lastLocationStorageTime = currentTime
		return ok
	}

	private suspend fun getOrCreateSourceId(sourceName: String): Int {
		// Check cache first
		sourceIdCache[sourceName]?.let { return it }

		// Not in cache, check database
		val existingId = database.sourceDao().getSourceIdByName(sourceName)
		if (existingId != null) {
			sourceIdCache[sourceName] = existingId
			return existingId
		}

		// Create new source
		database.sourceDao().insertSourceByName(sourceName)
		val newId = database.sourceDao().getSourceIdByName(sourceName)
			?: throw IllegalStateException("Failed to create source: $sourceName")
		sourceIdCache[sourceName] = newId
		return newId
	}

	fun storeOrientationSensorData(data: OrientationSensorData) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val sourceId = getOrCreateSourceId(data.source)
				storeBearingEntity(
					BearingEntity(
						timestamp = data.timestamp,
						trueHeading = data.trueHeading,
						magneticHeading = data.magneticHeading,
						accuracyLevel = data.accuracyLevel,
						sourceId = sourceId,
						pitch = data.pitch,
						roll = data.roll
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store orientation sensor data: ${e.message}", e)
			}
		}
	}

	fun storeOrientationManual(params: JSObject) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				// JSObject.getLong is not overridden and JSONObject.getLong throws on missing
				// keys — the `?: System.currentTimeMillis()` default was dead code. Use has()
				// for optional fields. Same pattern below for source and storeLocationManual.
				val timestamp = if (params.has("timestamp")) params.getLong("timestamp") else System.currentTimeMillis()
				// JSObject.getDouble is non-nullable; a missing key throws. Let that propagate
				// (caught below); don't dress it up with a dead Elvis throw.
				val trueHeading = params.getDouble("trueHeading").toFloat()
				// JSObject.getString(key, default) is the two-arg overload that actually
				// honors the default when the key is missing; the single-arg overload returns
				// "" for missing keys, making `?: "manual"` dead code.
				val source = params.getString("source", "manual") ?: "manual"
				val sourceId = getOrCreateSourceId(source)

				storeBearingEntity(
					BearingEntity(
						timestamp = timestamp,
						trueHeading = trueHeading,
						magneticHeading = if (params.has("magneticHeading")) params.getDouble("magneticHeading").toFloat() else null,
						accuracyLevel = if (params.has("accuracyLevel")) params.getInteger("accuracyLevel") else null,
						sourceId = sourceId,
						pitch = if (params.has("pitch")) params.getDouble("pitch").toFloat() else null,
						roll = if (params.has("roll")) params.getDouble("roll").toFloat() else null
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store manual orientation: ${e.message}", e)
				throw e
			}
		}
	}

	private fun storeBearingEntity(entity: BearingEntity) {
		if (!rateLimitOrientationStorage()) {
			return
		}
		CoroutineScope(Dispatchers.IO).launch {
			try {
				database.bearingDao().insertBearing(entity)
			} catch (e: Exception) {
				Log.w(TAG, "Failed to store bearing in database: ${e.message}")
			}
		}
	}


	private fun storeLocationEntity(entity: LocationEntity) {
		if (!rateLimitLocationStorage()) {
			return
		}
		CoroutineScope(Dispatchers.IO).launch {
			try {
				database.locationDao().insertLocation(entity)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store location in database: ${e.message}", e)
			}
		}
	}

	// Current camera-mount offset (degrees) applied to GPS-derived travel heading.
	// Frontend pushes this via set_mount_offset when the user adjusts the shooting
	// angle; defaults to 0 (camera points in the direction of travel).
	@Volatile
	private var mountOffset: Double = 0.0

	fun setMountOffset(offsetDegrees: Double) {
		mountOffset = normalizeBearingDegrees(offsetDegrees)
	}

	fun getMountOffset(): Double = mountOffset

	/**
	 * Run the GPS-derived heading filter on a new location sample and, if it
	 * produced a heading, compose it with the current mount offset and persist
	 * the composed absolute as a `gps-kalman` bearing.
	 *
	 * Returns the composed bearing (0-360°) so the caller can emit it to the
	 * frontend, or null when the filter rejected the sample.
	 */
	fun feedLocationForHeadingFilter(data: PreciseLocationData): Double? {
		val travel = headingFilter.update(
			FilterPosition(
				lat = data.latitude,
				lng = data.longitude,
				speed = data.speed?.toDouble(),
				timestamp = data.timestamp
			)
		) ?: return null
		val composed = normalizeBearingDegrees(travel + mountOffset)
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val sourceId = getOrCreateSourceId("gps-kalman")
				storeBearingEntity(
					BearingEntity(
						timestamp = data.timestamp,
						trueHeading = composed.toFloat(),
						magneticHeading = null,
						accuracyLevel = null,
						sourceId = sourceId,
						pitch = null,
						roll = null
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store gps-kalman bearing: ${e.message}", e)
			}
		}
		return composed
	}

	fun resetHeadingFilter() {
		headingFilter.reset()
	}

	fun storeLocationPreciseLocationData(data: PreciseLocationData) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val source = data.provider ?: "precise"
				val sourceId = getOrCreateSourceId(source)
				storeLocationEntity(
					LocationEntity(
						timestamp = data.timestamp,
						latitude = data.latitude,
						longitude = data.longitude,
						sourceId = sourceId,
						altitude = data.altitude,
						accuracy = data.accuracy,
						verticalAccuracy = data.altitudeAccuracy,
						speed = data.speed,
						bearing = data.bearing
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store location data: ${e.message}", e)
				throw e
			}
		}
	}

	fun storeLocationManual(params: JSObject) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				// See notes in storeOrientationManual for why these patterns changed.
				val timestamp = if (params.has("timestamp")) params.getLong("timestamp") else System.currentTimeMillis()
				val latitude = params.getDouble("latitude")
				val longitude = params.getDouble("longitude")
				val source = params.getString("source", "manual") ?: "manual"
				val sourceId = getOrCreateSourceId(source)

				storeLocationEntity(
					LocationEntity(
						timestamp = timestamp,
						latitude = latitude,
						longitude = longitude,
						sourceId = sourceId,
						altitude = if (params.has("altitude")) params.getDouble("altitude") else null,
						accuracy = if (params.has("accuracy")) params.getDouble("accuracy").toFloat() else null,
						verticalAccuracy = if (params.has("verticalAccuracy")) params.getDouble("verticalAccuracy").toFloat() else null,
						speed = if (params.has("speed")) params.getDouble("speed").toFloat() else null,
						bearing = if (params.has("bearing")) params.getDouble("bearing").toFloat() else null
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store manual location: ${e.message}", e)
				throw e
			}
		}
	}

	/**
	 * Clears old geo tracking data and optionally exports to CSV.
	 * @param forceDump If true, always export to CSV. If false, check auto_export preference.
	 */
	fun dumpAndClear(forceDump: Boolean = false) {
		val now = System.currentTimeMillis()

		// Check if we should dump based on preference or force flag
		val prefs = context.getSharedPreferences("hillview_tracking_prefs", Context.MODE_PRIVATE)
		val autoExportEnabled = prefs.getBoolean("auto_export", false)
		val shouldDump = forceDump || autoExportEnabled

		CoroutineScope(Dispatchers.IO).launch {
			if (shouldDump) {
				// Use app's external files directory (no permissions needed)
				val externalFilesDir = context.getExternalFilesDir(null)
				val hillviewDir = File(externalFilesDir, "GeoTrackingDumps")
				if (!hillviewDir.exists()) {
					hillviewDir.mkdirs()
				}

				val bearingsFn = File(hillviewDir, "hillview_orientations_${now}.csv")
				val locationsFn = File(hillviewDir, "hillview_locations_${now}.csv")

				try {
					val sourceIdToName = buildSourceIdToNameMap()

					val bearings = database.bearingDao().getAllBearings()
					val bearingsCsv = bearingsToCsv(bearings, sourceIdToName)
					bearingsFn.writeText(bearingsCsv)
					Log.i(TAG, "🢄📡 Dumped ${bearings.size} bearings to ${bearingsFn.absolutePath}")

					val locations = database.locationDao().getAllLocations()
					val locationsCsv = locationsToCsv(locations, sourceIdToName)
					locationsFn.writeText(locationsCsv)
					Log.i(TAG, "🢄📡 Dumped ${locations.size} locations to ${locationsFn.absolutePath}")
				} catch (e: Exception) {
					Log.e(TAG, "🢄📡 Failed to dump geo tracking data: ${e.message}", e)
				}
			} else {
				Log.d(TAG, "🢄📡 Skipping geo data dump (auto_export disabled)")
			}

			// Always clear old data
			val cutoff = now - 1000 * 60 * 5

			try {
				database.bearingDao().clearBearingsOlderThan(cutoff)
				database.locationDao().clearLocationsOlderThan(cutoff)
				Log.i(TAG, "🢄📡 Geo tracking tables cleared")
			} catch (e: Exception) {
				Log.e(TAG, "🢄📡 Failed to clear geo tracking tables: ${e.message}", e)
			}
		}
	}

	private suspend fun buildSourceIdToNameMap(): Map<Int, String> {
		// Start with reverse lookup from existing cache
		val idToName = mutableMapOf<Int, String>()
		for ((name, id) in sourceIdCache) {
			idToName[id] = name
		}

		// Query all sources to fill gaps
		val allSources = database.sourceDao().getAllSources()
		for (source in allSources) {
			idToName[source.id] = source.name
		}

		return idToName
	}

	private fun escapeCsv(value: String?): String {
		val str = value ?: ""
		return if (str.contains(",") || str.contains("\"") || str.contains("\n")) {
			"\"${str.replace("\"", "\"\"")}\""
		} else {
			str
		}
	}

	private fun bearingsToCsv(bearings: List<BearingEntity>, sourceIdToName: Map<Int, String>): String {
		val header = "#timestamp,trueHeading,magneticHeading,accuracyLevel,source,pitch,roll\n"
		val rows = bearings.joinToString("\n") { bearing ->
			val sourceName = escapeCsv(sourceIdToName[bearing.sourceId] ?: "unknown")
			"${bearing.timestamp},${bearing.trueHeading},${bearing.magneticHeading ?: ""},${bearing.accuracyLevel ?: ""},${sourceName},${bearing.pitch ?: ""},${bearing.roll ?: ""}"
		}
		return header + rows + "\n"
	}

	private fun locationsToCsv(locations: List<LocationEntity>, sourceIdToName: Map<Int, String>): String {
		val header = "#timestamp,latitude,longitude,source,altitude,accuracy,verticalAccuracy,speed,bearing\n"
		val rows = locations.joinToString("\n") { location ->
			val sourceName = escapeCsv(sourceIdToName[location.sourceId] ?: "unknown")
			"${location.timestamp},${location.latitude},${location.longitude},${sourceName},${location.altitude ?: ""},${location.accuracy ?: ""},${location.verticalAccuracy ?: ""},${location.speed ?: ""},${location.bearing ?: ""}"
		}
		return header + rows + "\n"
	}

}

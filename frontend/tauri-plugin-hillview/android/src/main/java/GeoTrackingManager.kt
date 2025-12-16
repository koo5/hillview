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
	val headingAccuracy: Float,  // Calculated accuracy in degrees (for future use)
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
						headingAccuracy = data.headingAccuracy,
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
				val timestamp = params.getLong("timestamp") ?: System.currentTimeMillis()
				val trueHeading = params.getDouble("trueHeading")?.toFloat()
					?: throw IllegalArgumentException("trueHeading is required")
				val source = params.getString("source") ?: "manual"
				val sourceId = getOrCreateSourceId(source)

				storeBearingEntity(
					BearingEntity(
						timestamp = timestamp,
						trueHeading = trueHeading,
						magneticHeading = if (params.has("magneticHeading")) params.getDouble("magneticHeading").toFloat() else null,
						headingAccuracy = if (params.has("headingAccuracy")) params.getDouble("headingAccuracy").toFloat() else null,
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
				val timestamp = params.getLong("timestamp") ?: System.currentTimeMillis()
				val latitude = params.getDouble("latitude")
					?: throw IllegalArgumentException("latitude is required")
				val longitude = params.getDouble("longitude")
					?: throw IllegalArgumentException("longitude is required")
				val source = params.getString("source") ?: "manual"
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

	fun dumpAndClear() {
		// todo: dump all data and clear all entries older than a certain timestamp

		val now = System.currentTimeMillis()

		// Use app's external files directory (no permissions needed)
		val externalFilesDir = context.getExternalFilesDir(null)
		val hillviewDir = File(externalFilesDir, "GeoTrackingDumps")
		if (!hillviewDir.exists()) {
			hillviewDir.mkdirs()
		}

		val bearingsFn = File(hillviewDir, "bearings_${now}.csv")
		val locationsFn = File(hillviewDir, "locations_${now}.csv")

		CoroutineScope(Dispatchers.IO).launch {
			try {
				// Build reverse source cache for export
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

			val cutoff = now - 5 * 60 * 1000

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
		val header = "#timestamp,trueHeading,magneticHeading,headingAccuracy,accuracyLevel,source,pitch,roll\n"
		val rows = bearings.joinToString("\n") { bearing ->
			val sourceName = escapeCsv(sourceIdToName[bearing.sourceId] ?: "unknown")
			"${bearing.timestamp},${bearing.trueHeading},${bearing.magneticHeading ?: ""},${bearing.headingAccuracy ?: ""},${bearing.accuracyLevel ?: ""},${sourceName},${bearing.pitch ?: ""},${bearing.roll ?: ""}"
		}
		return header + rows + "\n"
	}

	private fun locationsToCsv(locations: List<LocationEntity>, sourceIdToName: Map<Int, String>): String {
		val header = "#timestamp,latitude,longitude,source,altitude,accuracy,verticalAccuracy,speed,bearing\n"
		val rows = locations.joinToString("\n") { location ->
			val sourceName = escapeCsv(sourceIdToName[location.sourceId] ?: "unknown")
			"${location.timestamp},${location.latitude},${location.longitude},${sourceName},${location.altitude ?: ""},${location.accuracy ?: ""},${location.speed ?: ""},${location.bearing ?: ""}"
		}
		return header + rows + "\n"
	}

}

package cz.hillview.plugin

/*
 GeoTrackingManager is responsible for storing geolocation and orientation datapoints. It should be usable from both ExamplePlugin and a future foreground service.

*/

import android.content.Context
import android.util.Log
import cz.hillview.plugin.database.AppDatabase
import cz.hillview.plugin.database.entities.BearingEntity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

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


class GeoTrackingManager {
	private val context: Context;
	private val database: AppDatabase;

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

	fun storeOrientationSensorData(data: OrientationSensorData) {
		storeBearingEntity(
			BearingEntity(
				timestamp = data.timestamp,
				magneticHeading = data.magneticHeading,
				trueHeading = data.trueHeading,
				headingAccuracy = data.headingAccuracy,
				accuracyLevel = data.accuracyLevel,
				source = data.source,
				pitch = data.pitch,
				roll = data.roll
			)
		)
	}

	fun storeOrientationManual(params: JSObject) {
		val timestamp = params.getLong("timestamp")
		val trueHeading = params.getDouble("trueHeading").toFloat()
		val source = params.getString("source")
		storeBearingEntity(
			/* todo: make other fields optional */
			BearingEntity(
				timestamp = timestamp,
				trueHeading = trueHeading,
				source = source
			)
		)
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


	fun storeLocationPreciseLocationData() {

	}

	fun storeLocationManual() {

	}

}

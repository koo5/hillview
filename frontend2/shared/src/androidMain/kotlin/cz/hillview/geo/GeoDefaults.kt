package cz.hillview.geo

/**
 * Starting values for each activity's [GeoConfig] — deliberately HERE, next
 * to the call sites that start the engine, and not inside the engine itself.
 *
 * The engine is told what to run and never decides; these are the defaults a
 * user control replaces. The GPS-interval slider and the eco sub-flags are
 * therefore values flowing through this seam, not new machinery: read the
 * setting, pass a different number.
 *
 * All of them want tuning on real hardware — a phone in a car, in the sun.
 * The comments say what each number is FOR, so a measured change has
 * something to argue with.
 */

/** ~33 Hz. What SENSOR_DELAY has always been; smooth enough for the arrow. */
const val SENSOR_DELAY_NORMAL_US = 30_000

/** ~10 Hz. For when heading matters less than power (map-only viewing). */
const val SENSOR_DELAY_RELAXED_US = 100_000

/** The fused cadence both apps have always used. */
const val GPS_INTERVAL_DEFAULT_MS = 1_000L

/**
 * Capture: the stamp is only as good as the freshest fix, and the refiner
 * interpolates between the two fixes bracketing the shutter — so the fix
 * cadence sets the refinement's resolution. Full rate.
 */
fun captureGeoConfig(gpsIntervalMs: Long = GPS_INTERVAL_DEFAULT_MS) = GeoConfig(
    sensors = true,
    sensorDelayUs = SENSOR_DELAY_NORMAL_US,
    locationIntervalMs = gpsIntervalMs,
)

/**
 * External camera: the whole point is never having a gap, because photos
 * taken in another app are stamped from this record afterwards. Same rates
 * as capture; the difference is that it keeps running with the screen off.
 */
fun externalCameraConfig(gpsIntervalMs: Long = GPS_INTERVAL_DEFAULT_MS) = GeoConfig(
    sensors = true,
    sensorDelayUs = SENSOR_DELAY_NORMAL_US,
    locationIntervalMs = gpsIntervalMs,
    // The sentence above, made true: until 2026-08-19 the sensor service's
    // own lifecycle observer paused the sensors the moment the system camera
    // app came to the front — exactly when this mode needs them. The engine
    // now owns that decision, and this is the one config that says "keep
    // going" (the location-typed foreground service is what permits it).
    sensorsInBackground = true,
)

/**
 * Map viewing with follow-me or the compass arrow on: nobody is stamping
 * anything, so this trades resolution for power — half the fix rate, a
 * third of the sensor rate. Still smooth for an arrow the eye is watching.
 */
fun mapOnlyGeoConfig() = GeoConfig(
    sensors = true,
    sensorDelayUs = SENSOR_DELAY_RELAXED_US,
    locationIntervalMs = 2_000L,
)

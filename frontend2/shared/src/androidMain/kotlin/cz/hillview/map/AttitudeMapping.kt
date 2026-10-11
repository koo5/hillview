package cz.hillview.map

import cz.hillview.plugin.OrientationSensorData

/**
 * One sensor sample as the one state's attitude record.
 *
 * Extracted because it now has two callers and the codebase has been bitten by the
 * alternative: the map's writer adapter builds this to publish, and the engine builds it
 * to keep in its lookup ring. Two hand-written conversions of the same sample would be
 * free to disagree about, say, whether -1 means "no contact" or "never reported" — and
 * the whole reason the ring exists is that a photo's pose and its bearing once described
 * different instants.
 */
internal fun OrientationSensorData.toDeviceAttitude(): DeviceAttitude = DeviceAttitude(
    trueDeg = trueHeading.toDouble(),
    magneticDeg = magneticHeading.toDouble(),
    pitch = pitch.toDouble(),
    roll = roll.toDouble(),
    // Android's -1 doubles as NO_CONTACT and as "never reported"; both mean we cannot
    // rate the heading.
    magnetometerCalibration = accuracyLevel.takeIf { it >= 0 },
    fusedSensorAccuracy = fusedSensorAccuracy.takeIf { it >= 0 },
    detail = detail,
    ts = timestamp,
    elapsedNs = elapsedRealtimeNanos,
)

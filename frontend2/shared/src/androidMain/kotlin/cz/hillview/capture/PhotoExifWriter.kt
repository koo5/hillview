package cz.hillview.capture

import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * Writes the sensor snapshot into the JPEG's EXIF. This is the contract with
 * the backend parser and the pics pipeline — covered by the on-device EXIF
 * golden check (see docs/frontend2-rewrite-plan.md, P1 gate).
 */
object PhotoExifWriter {

    fun write(file: File, snapshot: SensorSnapshot) {
        val exif = ExifInterface(file.absolutePath)

        if (snapshot.latitude != null && snapshot.longitude != null) {
            exif.setLatLong(snapshot.latitude, snapshot.longitude)
        }
        snapshot.altitude?.let { exif.setAltitude(it) }
        snapshot.accuracyM?.let {
            exif.setAttribute(
                ExifInterface.TAG_GPS_H_POSITIONING_ERROR,
                rational(it.toDouble(), 100),
            )
        }
        snapshot.bearingDeg?.let {
            exif.setAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION, rational(it.toDouble(), 10))
            exif.setAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION_REF, "M")
        }

        val capturedAt = Date(snapshot.capturedAtMs)
        val local = SimpleDateFormat("yyyy:MM:dd HH:mm:ss", Locale.US)
        exif.setAttribute(ExifInterface.TAG_DATETIME_ORIGINAL, local.format(capturedAt))
        exif.setAttribute(
            ExifInterface.TAG_SUBSEC_TIME_ORIGINAL,
            (snapshot.capturedAtMs % 1000).toString().padStart(3, '0'),
        )
        exif.setAttribute(
            ExifInterface.TAG_OFFSET_TIME_ORIGINAL,
            SimpleDateFormat("XXX", Locale.US).format(capturedAt),
        )

        // GPS time is UTC by definition.
        val utcDate = SimpleDateFormat("yyyy:MM:dd", Locale.US)
            .apply { timeZone = TimeZone.getTimeZone("UTC") }
        val utcTime = SimpleDateFormat("HH:mm:ss", Locale.US)
            .apply { timeZone = TimeZone.getTimeZone("UTC") }
        exif.setAttribute(ExifInterface.TAG_GPS_DATESTAMP, utcDate.format(capturedAt))
        exif.setAttribute(ExifInterface.TAG_GPS_TIMESTAMP, utcTime.format(capturedAt))

        exif.saveAttributes()
    }

    private fun rational(value: Double, denominator: Int): String =
        "${(abs(value) * denominator).roundToInt()}/$denominator"
}

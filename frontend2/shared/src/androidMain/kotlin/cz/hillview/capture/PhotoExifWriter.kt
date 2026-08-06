package cz.hillview.capture

import android.content.Context
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.IOException
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
        write(ExifInterface(file.absolutePath), snapshot)
    }

    /**
     * MediaStore saves hand back a content:// URI, not a path. ExifInterface
     * can rewrite through a read-write file descriptor, which MediaStore
     * images support.
     */
    fun write(context: Context, uri: Uri, snapshot: SensorSnapshot) {
        context.contentResolver.openFileDescriptor(uri, "rw")?.use { pfd ->
            write(ExifInterface(pfd.fileDescriptor), snapshot)
        } ?: throw IOException("cannot open $uri for EXIF write")
    }

    private fun write(exif: ExifInterface, snapshot: SensorSnapshot) {

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
        // TRUE heading, ref "T", duplicated into DestBearing — matching the
        // Tauri app's Rust writer (photo_exif.rs) exactly: the worker parser
        // reads the magnitude from ImgDirection|Track|DestBearing and ignores
        // the ref, so the ecosystem-wide convention is true north in these
        // tags. (The declination-less magnetic value that used to go here
        // under ref "M" was silently off by local declination for every
        // consumer.)
        snapshot.trueBearingDeg?.let {
            exif.setAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION, rational(it.toDouble(), 100))
            exif.setAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION_REF, "T")
            exif.setAttribute(ExifInterface.TAG_GPS_DEST_BEARING, rational(it.toDouble(), 100))
            exif.setAttribute(ExifInterface.TAG_GPS_DEST_BEARING_REF, "T")
        }

        // Provenance, same shape and tag (UserComment) as the Rust writer.
        val locationSource = if (snapshot.latitude != null) "gps" else null
        if (locationSource != null || snapshot.bearingSource != null) {
            val fields = buildList {
                locationSource?.let { add("\"location_source\":\"$it\"") }
                snapshot.bearingSource?.let { add("\"bearing_source\":\"$it\"") }
            }
            exif.setAttribute(
                ExifInterface.TAG_USER_COMMENT,
                fields.joinToString(",", prefix = "{", postfix = "}"),
            )
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

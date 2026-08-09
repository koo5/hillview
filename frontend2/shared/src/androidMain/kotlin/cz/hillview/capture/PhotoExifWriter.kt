package cz.hillview.capture

import android.content.Context
import android.net.Uri
import android.util.Log
import androidx.exifinterface.media.ExifInterface
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.math.abs
import kotlin.math.roundToInt

private const val TAG = "PhotoExifWriter"

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

        // Provenance, same shape and tag (UserComment) as the Rust writer —
        // plus location_age_ms, which the original never records: how old
        // the stamped fix was at the shutter. Additive keys; readers of the
        // Tauri shape ignore what they don't know.
        val locationSource = snapshot.locationSource
        val exposure = snapshot.exposure
        if (locationSource != null || snapshot.bearingSource != null || exposure != null) {
            val fields = buildList {
                locationSource?.let { add("\"location_source\":\"$it\"") }
                snapshot.bearingSource?.let { add("\"bearing_source\":\"$it\"") }
                if (locationSource == "gps") {
                    snapshot.locationAgeMs?.let { add("\"location_age_ms\":$it") }
                }
                // The exposure-rule story of this shot: what was asked (the
                // rule), what it resolved to (the plan) and the AE reading it
                // scaled from. CameraX stamps what the sensor actually DID
                // into the standard ExposureTime/ISO tags, so this is the
                // half the file cannot otherwise tell you. Absent when AE
                // owned the shot.
                exposure?.let { e ->
                    val exposureFields = buildList {
                        add("\"mode\":\"${e.rule.mode.name.lowercase()}\"")
                        add("\"target_ns\":${e.rule.targetNs}")
                        add("\"ev_bias\":${e.rule.evBias}")
                        add("\"applied_ns\":${e.plan.exposureNs}")
                        add("\"iso\":${e.plan.iso}")
                        add("\"outcome\":\"${e.plan.outcome.name.lowercase()}\"")
                        e.meteredExposureNs?.let { add("\"metered_ns\":$it") }
                        e.meteredIso?.let { add("\"metered_iso\":$it") }
                    }
                    add("\"exposure\":${exposureFields.joinToString(",", prefix = "{", postfix = "}")}")
                }
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

        // TAG_ORIENTATION is deliberately NOT written here. CameraX already
        // stamped it from ImageCapture.targetRotation, and only CameraX can:
        // its buffers are in the raw SENSOR frame, so the correct tag folds
        // in the camera's sensorOrientation and lens facing, neither of which
        // the snapshot knows. (This is why the Tauri app's orientation_code
        // cannot simply be ported — its canvas frames were already
        // display-oriented, so the same physical pose wants a different tag.)
        // What this writer must do is not LOSE it: saveAttributes() rewrites
        // the whole file. A flat 1 in this log for every pose means
        // targetRotation stopped tracking the device — see the
        // MyDeviceOrientationSensor wiring in PhotoCapture.android.kt.
        Log.d(
            TAG,
            "exif orientation (CameraX's, preserved): " +
                "${exif.getAttribute(ExifInterface.TAG_ORIENTATION)} " +
                "at device pose ${snapshot.deviceRotationDeg}°",
        )

        exif.saveAttributes()
    }

    private fun rational(value: Double, denominator: Int): String =
        "${(abs(value) * denominator).roundToInt()}/$denominator"
}

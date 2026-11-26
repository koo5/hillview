package cz.hillview.capture

import android.graphics.Bitmap
import androidx.exifinterface.media.ExifInterface
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.io.FileOutputStream
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.junit.Test
import org.json.JSONObject

/**
 * The EXIF contract, on a real device because it is Android's ExifInterface
 * that has to agree — not a mock of it.
 *
 * This is the contract the backend and the pics pipeline read, and it was
 * got wrong once already: frontend2 used to write the MAGNETIC bearing under
 * ref "M", while every other writer in the ecosystem puts TRUE north in
 * those tags and the worker reads the magnitude without looking at the ref.
 * See docs/tauri-map-ui-contract.md and the Rust writer in
 * frontend/src-tauri/src/photo_exif.rs.
 */
class PhotoExifWriterTest {

    private val snapshot = SensorSnapshot(
        latitude = 50.115,
        longitude = 14.501,
        altitude = 271.0,
        accuracyM = 5f,
        bearingDeg = 0.37f,        // magnetic
        trueBearingDeg = 5.37f,    // + Prague declination
        bearingSource = "android TYPE_ROTATION_VECTOR (UPRIGHT MODE)",
        capturedAtMs = 1_786_012_833_024,
        locationAgeMs = 120,
    )

    private fun jpeg(): File {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val file = File(context.cacheDir, "exif-test-${System.nanoTime()}.jpg")
        // ExifInterface needs a real JPEG to graft onto.
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888)
        FileOutputStream(file).use { bitmap.compress(Bitmap.CompressFormat.JPEG, 90, it) }
        return file
    }

    @Test
    fun writesTrueNorthBearingUnderARefOfT() {
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot)

        val exif = ExifInterface(file.absolutePath)
        val direction = exif.getAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION)
        assertNotNull(direction, "GPSImgDirection must be present — the backend rejects photos without a bearing")
        assertEquals(
            5.37,
            direction.toRational(),
            0.01,
            "the TRUE bearing belongs here, not the magnetic one",
        )
        assertEquals("T", exif.getAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION_REF))
        file.delete()
    }

    @Test
    fun duplicatesTheBearingIntoDestBearingLikeTheRustWriter() {
        // The worker reads the first of ImgDirection / Track / DestBearing it
        // finds, so the Tauri writer fills DestBearing too.
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot)

        val exif = ExifInterface(file.absolutePath)
        assertEquals(
            5.37,
            exif.getAttribute(ExifInterface.TAG_GPS_DEST_BEARING)?.toRational() ?: 0.0,
            0.01,
        )
        assertEquals("T", exif.getAttribute(ExifInterface.TAG_GPS_DEST_BEARING_REF))
        file.delete()
    }

    @Test
    fun writesThePositionItWasGiven() {
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot)

        val exif = ExifInterface(file.absolutePath)
        val latLong = exif.latLong
        assertNotNull(latLong, "position must round-trip")
        assertEquals(50.115, latLong[0], 0.0001)
        assertEquals(14.501, latLong[1], 0.0001)
        assertEquals(271.0, exif.getAltitude(0.0), 0.5)
        file.delete()
    }

    @Test
    fun recordsWhereTheBearingCameFrom() {
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot)

        val comment = ExifInterface(file.absolutePath)
            .getAttribute(ExifInterface.TAG_USER_COMMENT)
        assertNotNull(comment)
        assertTrue(comment.contains("bearing_source"), "provenance is part of the contract: $comment")
        assertTrue(comment.contains("ROTATION_VECTOR"), "the sensor should be named: $comment")
        file.delete()
    }

    /**
     * The gravity vector and the version, not just the angles.
     *
     * With "Write EXIF" on, the worker keeps the file's own UserComment and the
     * upload metadata never speaks. A stamp carrying `attitude` alone reads to
     * `capture_pose` as PRE-VERSIONING, which trusts the angles only when
     * `device_rotation_deg` is 0 — so a landscape or upside-down shot arrived with
     * no pitch and no roll and failed the Panoramax level gates. `capture_timing`
     * carries the `metadata_version` that lifts that, and `inertial` carries the
     * gravity the server prefers over the angles anyway.
     */
    @Test
    fun theExifStampCarriesGravityAndTheMetadataVersion() {
        val file = jpeg()
        PhotoExifWriter.write(
            file,
            snapshot.copy(
                motion = cz.hillview.map.DeviceMotionSample(
                    gravity = listOf(3.802262f, 9.020489f, -0.640069f),
                    atMs = snapshot.capturedAtMs,
                ),
                captureTiming = CaptureTiming(
                    capturedAtSource = "press",
                    metadataVersion = 3,
                ),
            ),
        )

        val comment = ExifInterface(file.absolutePath)
            .getAttribute(ExifInterface.TAG_USER_COMMENT)
        assertNotNull(comment)
        assertTrue(comment.contains("\"inertial\""), "no inertial object: $comment")
        assertTrue(comment.contains("\"gravity\":[3.802262,9.020489,-0.640069]"), comment)
        assertTrue(comment.contains("\"capture_timing\""), "no capture_timing: $comment")
        assertTrue(
            comment.contains("\"metadata_version\":3"),
            "without this the server reads the stamp as pre-versioning: $comment",
        )
        file.delete()
    }

    @Test
    fun landscapeWithoutGravityKeepsTheVersionNeededToReadItsAttitude() {
        val file = jpeg()
        try {
            PhotoExifWriter.write(
                file,
                snapshot.copy(
                    deviceRotationDeg = 270,
                    attitude = cz.hillview.map.DeviceAttitude(
                        trueDeg = 68.5,
                        magneticDeg = 64.25,
                        pitch = 6.5, // the lens is above the horizon
                        roll = 90.0,
                        ts = snapshot.capturedAtMs,
                    ),
                    captureTiming = CaptureTiming(
                        capturedAtSource = "press",
                        metadataVersion = METADATA_VERSION,
                        pressToExposureMs = 77,
                        exposureToJpegMs = 126,
                    ),
                ),
            )

            val rawComment = ExifInterface(file.absolutePath)
                .getAttribute(ExifInterface.TAG_USER_COMMENT)
            assertNotNull(rawComment)
            val comment = JSONObject(rawComment)
            assertTrue(!comment.has("inertial"), "no gravity may be invented")
            val timing = comment.getJSONObject("capture_timing")
            assertEquals(METADATA_VERSION, timing.getInt("metadata_version"))
            assertEquals("press", timing.getString("captured_at_source"))
            assertEquals(77L, timing.getLong("press_to_exposure_ms"))
            assertEquals(126L, timing.getLong("exposure_to_jpeg_ms"))
            val attitude = comment.getJSONObject("attitude")
            assertEquals(270, attitude.getInt("device_rotation_deg"))
            assertEquals(-6.5, attitude.getDouble("pitch_deg"), 0.001)
            assertEquals(90.0, attitude.getDouble("roll_deg"), 0.001)
        } finally {
            file.delete()
        }
    }

    /**
     * ...and a shot with neither still stamps what it does have, rather than
     * nothing. The two objects are additive: the guard that decides whether to
     * write a UserComment at all must not start depending on them.
     */
    @Test
    fun aShotWithNoGravityStillCarriesItsOtherProvenance() {
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot)

        val comment = ExifInterface(file.absolutePath)
            .getAttribute(ExifInterface.TAG_USER_COMMENT)
        assertNotNull(comment)
        assertTrue(comment.contains("bearing_source"), comment)
        assertTrue(!comment.contains("\"inertial\""), "nothing measured it: $comment")
        file.delete()
    }

    /**
     * The fix's radius in the UserComment, not just in GPSHPositioningError.
     *
     * The server reads accuracy only from `location_accuracy_m` there, and with
     * "Write EXIF" on the upload's `accuracy` never reaches it — so a missing
     * key stored NULL, and NULL passes the Panoramax accuracy gate as unknown.
     */
    @Test
    fun theExifStampCarriesTheFixAccuracy() {
        val file = jpeg()
        try {
            PhotoExifWriter.write(file, snapshot.copy(accuracyM = 50f))

            val exif = ExifInterface(file.absolutePath)
            val comment = JSONObject(assertNotNull(exif.getAttribute(ExifInterface.TAG_USER_COMMENT)))
            assertEquals(50.0, comment.getDouble("location_accuracy_m"), 0.001)
            assertEquals(50.0, exif.getAttribute(ExifInterface.TAG_GPS_H_POSITIONING_ERROR)?.toRational() ?: 0.0, 0.01)
        } finally {
            file.delete()
        }
    }

    @Test
    fun anAbsentOrNonsenseAccuracyIsLeftOut() {
        for (accuracy in listOf(null, 0f, -3f, Float.NaN)) {
            val file = jpeg()
            try {
                // A NaN used to throw out of rational() before anything was saved.
                PhotoExifWriter.write(file, snapshot.copy(accuracyM = accuracy))
                val exif = ExifInterface(file.absolutePath)
                // ...and rational()'s abs() wrote -3 as a plausible 3 m.
                assertEquals(
                    null,
                    exif.getAttribute(ExifInterface.TAG_GPS_H_POSITIONING_ERROR),
                    "accuracy=$accuracy",
                )
                val raw = assertNotNull(exif.getAttribute(ExifInterface.TAG_USER_COMMENT))
                // Parsing it is the point for NaN: one bad number must not make
                // the whole provenance unreadable to the server.
                val comment = JSONObject(raw)
                assertTrue(!comment.has("location_accuracy_m"), "accuracy=$accuracy: $raw")
                assertTrue(comment.has("bearing_source"), "accuracy=$accuracy: $raw")
            } finally {
                file.delete()
            }
        }
    }

    @Test
    fun recordsTheExposureRuleStoryWhenOneWasInForce() {
        // The rule/plan/metering triple is the half the file cannot
        // otherwise tell you — CameraX's standard tags say what the sensor
        // DID, UserComment says what was asked and why the answer came out
        // the way it did.
        val file = jpeg()
        PhotoExifWriter.write(
            file,
            snapshot.copy(
                exposure = ExposureStamp(
                    rule = ExposureRule(ExposureMode.Floor, 2_000_000L, -1.0),
                    plan = ExposurePlan(1_958_333L, 50, ExposureOutcome.Faster),
                    meteredExposureNs = 10_000_000L,
                    meteredIso = 100,
                ),
            ),
        )

        val comment = ExifInterface(file.absolutePath)
            .getAttribute(ExifInterface.TAG_USER_COMMENT)
        assertNotNull(comment)
        assertTrue(comment.contains("\"exposure\""), "the exposure block is part of the provenance: $comment")
        assertTrue(comment.contains("\"mode\":\"floor\""), "the rule should be named: $comment")
        assertTrue(comment.contains("\"outcome\":\"faster\""), "the resolution should be named: $comment")
        assertTrue(comment.contains("\"iso\":50"), "the planned gain should be there: $comment")
        assertTrue(comment.contains("\"metered_ns\":10000000"), "the metering it scaled from should be there: $comment")
        // The location/bearing provenance must survive the addition.
        assertTrue(comment.contains("bearing_source"), "provenance is part of the contract: $comment")
        file.delete()
    }

    @Test
    fun anAutoExposedShotCarriesNoExposureBlock() {
        // Under auto exposure AE owned the frame; claiming a rule would be a
        // lie, and the standard tags already say everything true.
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot)

        val comment = ExifInterface(file.absolutePath)
            .getAttribute(ExifInterface.TAG_USER_COMMENT)
        assertNotNull(comment)
        assertTrue(!comment.contains("\"exposure\""), "no rule, no exposure block: $comment")
        file.delete()
    }

    @Test
    fun aPhotoWithoutAHeadingCarriesNoDirectionTags() {
        // Better no bearing than a wrong one — the backend will reject it,
        // which is the honest outcome.
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot.copy(trueBearingDeg = null, bearingDeg = null))

        val exif = ExifInterface(file.absolutePath)
        assertEquals(null, exif.getAttribute(ExifInterface.TAG_GPS_IMG_DIRECTION))
        file.delete()
    }

    @Test
    fun writesSubSecondAndOffsetSoCaptureTimeIsNotAmbiguous() {
        // The one-second EXIF granularity is why the clock-calibration work
        // exists; SubSec and OffsetTime are what make the stamp usable.
        val file = jpeg()
        PhotoExifWriter.write(file, snapshot)

        val exif = ExifInterface(file.absolutePath)
        assertNotNull(exif.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL))
        assertEquals("024", exif.getAttribute(ExifInterface.TAG_SUBSEC_TIME_ORIGINAL))
        assertNotNull(exif.getAttribute(ExifInterface.TAG_OFFSET_TIME_ORIGINAL))
        // GPS timestamps are UTC by definition.
        assertNotNull(exif.getAttribute(ExifInterface.TAG_GPS_DATESTAMP))
        assertNotNull(exif.getAttribute(ExifInterface.TAG_GPS_TIMESTAMP))
        file.delete()
    }

    @Test
    fun preservesTheOrientationCameraXStamped() {
        // The Orientation tag belongs to CameraX — it is the only party that
        // knows the camera's sensorOrientation and lens facing, which the raw
        // sensor-frame buffer needs folded in. This writer's job is purely to
        // not lose it, and saveAttributes() rewriting the whole file makes
        // that a property worth pinning rather than assuming.
        val file = jpeg()
        ExifInterface(file.absolutePath).apply {
            setAttribute(
                ExifInterface.TAG_ORIENTATION,
                ExifInterface.ORIENTATION_ROTATE_90.toString(),
            )
            saveAttributes()
        }

        PhotoExifWriter.write(file, snapshot.copy(deviceRotationDeg = 0))

        assertEquals(
            ExifInterface.ORIENTATION_ROTATE_90,
            ExifInterface(file.absolutePath).getAttributeInt(
                ExifInterface.TAG_ORIENTATION,
                ExifInterface.ORIENTATION_UNDEFINED,
            ),
            "the EXIF rewrite must not drop the rotation CameraX stamped",
        )
        file.delete()
    }

    /** EXIF rationals arrive as "537/100". */
    private fun String.toRational(): Double {
        val parts = split("/")
        return if (parts.size == 2) parts[0].toDouble() / parts[1].toDouble() else toDouble()
    }
}

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

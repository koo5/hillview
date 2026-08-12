package cz.hillview.capture

import android.view.Surface
import cz.hillview.plugin.DeviceOrientation
import kotlin.test.assertEquals
import org.junit.Test

/**
 * The pure-device pose → CameraX targetRotation table, which is where the
 * whole EXIF orientation chain either works or silently doesn't.
 *
 * The load-bearing fact is the INVERSION: turning the phone clockwise turns
 * the display counter-clockwise relative to it, so LANDSCAPE_LEFT (device
 * turned 90° CW, left edge up) maps to ROTATION_270 and not ROTATION_90.
 * Getting that backwards produces photos that are wrong by 180°, which looks
 * plausible enough in a thumbnail to ship.
 *
 * On a device rather than the JVM because Surface is Android's.
 */
class DeviceOrientationRotationTest {

    @Test
    fun mapsEachPoseToTheRotationTheDisplayWouldHave() {
        assertEquals(
            Surface.ROTATION_0,
            DeviceOrientation.toSurfaceRotation(DeviceOrientation.PORTRAIT),
        )
        assertEquals(
            Surface.ROTATION_270,
            DeviceOrientation.toSurfaceRotation(DeviceOrientation.LANDSCAPE_LEFT),
            "device turned 90° clockwise ⇒ display rotated 270°, not 90°",
        )
        assertEquals(
            Surface.ROTATION_180,
            DeviceOrientation.toSurfaceRotation(DeviceOrientation.PORTRAIT_INVERTED),
        )
        assertEquals(
            Surface.ROTATION_90,
            DeviceOrientation.toSurfaceRotation(DeviceOrientation.LANDSCAPE_RIGHT),
        )
    }

    @Test
    fun agreesWithTheDegreesTheSensorReports() {
        // fromDegrees() buckets OrientationEventListener's reading; toDegrees()
        // has to land back in the same bucket or the snapshot's record and the
        // stamped tag describe different poses.
        mapOf(0 to 0, 90 to 90, 180 to 180, 270 to 270).forEach { (reported, expected) ->
            assertEquals(
                expected,
                DeviceOrientation.toDegrees(DeviceOrientation.fromDegrees(reported)),
                "$reported° should round-trip",
            )
        }
    }

    @Test
    fun flatPosesDoNotThrow() {
        // toExifCode() throws on these; the capture path must not, because it
        // runs inside the shutter. MyDeviceOrientationSensor filters them out
        // upstream, but a crash here would be a bad way to find that out.
        assertEquals(0, DeviceOrientation.toDegrees(DeviceOrientation.FLAT_UP))
        assertEquals(0, DeviceOrientation.toDegrees(DeviceOrientation.FLAT_DOWN))
        assertEquals(
            Surface.ROTATION_0,
            DeviceOrientation.toSurfaceRotation(DeviceOrientation.FLAT_DOWN),
        )
    }

    @Test
    fun theExifCodeTableIsUnchangedForTheTauriPath() {
        // The Tauri app still reads toExifCode() through the plugin's
        // device-orientation event; frontend2 does not use it (its buffers are
        // in the sensor frame, so the same pose wants a different tag). Pinned
        // so the frontend2 work cannot quietly redefine the shared meaning.
        assertEquals(1, DeviceOrientation.toExifCode(DeviceOrientation.PORTRAIT))
        assertEquals(6, DeviceOrientation.toExifCode(DeviceOrientation.LANDSCAPE_LEFT))
        assertEquals(3, DeviceOrientation.toExifCode(DeviceOrientation.PORTRAIT_INVERTED))
        assertEquals(8, DeviceOrientation.toExifCode(DeviceOrientation.LANDSCAPE_RIGHT))
    }
}

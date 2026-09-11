package cz.hillview.capture

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * How the device is being HELD — one answer, one writer.
 *
 * The port of the original's `deviceOrientationExif` store
 * (frontend/src/lib/deviceOrientationExif.ts). There the plugin's
 * `device-orientation` event sets it and everything that cares reads it: the
 * orientation the JPEG is given, the debug overlay, and the floating camera
 * button, which rotates so its icon stays upright in the world and thereby
 * SHOWS the orientation the next photo will be understood to have.
 *
 * A separate store from the map's `bearing`, exactly as in the original and
 * for the same reason: this is the phone's physical pose, not the
 * user-facing heading, and mixing them would put a pose into the bearing
 * election. What it shares with the bearing is the rule that matters — ONE
 * home, so that no reader is ever tempted to register a second
 * OrientationEventListener to answer a question this already answers. See
 * docs/one-state.md.
 *
 * Degrees rather than the original's EXIF codes: this capture path already
 * speaks degrees ([SensorSnapshot.deviceRotationDeg],
 * `DeviceOrientation.toDegrees`), and an EXIF code is the JPEG's business,
 * not the UI's. The frame is OrientationEventListener's — 0 natural, 90 the
 * device turned clockwise (its left edge up), 180 inverted, 270
 * counter-clockwise.
 *
 * `null` means nothing is sensing the pose. The sensor runs only while the
 * camera is bound, as in the original, which mounts its listener with
 * CameraCapture and resets the store on unmount; readers treat null as
 * "unrotated", which is what that reset achieves.
 */
class DevicePoseState {
    private val _rotationDeg = MutableStateFlow<Int?>(null)
    val rotationDeg: StateFlow<Int?> = _rotationDeg.asStateFlow()

    /** Written by the capture engine's pose sensor — the app's only one. */
    fun set(rotationDeg: Int?) {
        _rotationDeg.value = rotationDeg
    }
}

/**
 * How far a UI element must be turned to stay upright in the WORLD, given a
 * device held at [deviceRotationDeg] and a display at [screenAngleDeg].
 * Clockwise-positive, in (-180, 180] — the frame Compose's `rotationZ` and
 * the original's CSS `rotate()` share.
 *
 * This is the original's `relativeOrientationExif` derivation
 * (`calculateWebviewRelativeOrientation`, then
 * `getCssRotationFromOrientation`) as arithmetic rather than a 16-row lookup;
 * DevicePoseRotationTest checks it against every row of that table.
 *
 * The two inputs turn in opposite senses, which is the whole subtlety:
 * turning the phone clockwise turns the display counter-clockwise relative to
 * it, so with auto-rotate on the two cancel and the icon sits still. It is
 * under a rotation lock — the normal state for someone out shooting — that
 * the icon has something to say.
 */
fun devicePoseUiRotation(deviceRotationDeg: Int?, screenAngleDeg: Int): Float {
    val deg = deviceRotationDeg ?: 0
    val css = ((-deg - screenAngleDeg) % 360 + 360) % 360
    return (if (css > 180) css - 360 else css).toFloat()
}

/**
 * The next animation target, chosen so the icon turns the SHORT way round.
 *
 * A deliberate divergence: the original animates the CSS value itself, so
 * 180° → -90° sweeps three quarters of a turn backwards. The phone did not do
 * that, and the icon exists to say what the phone did.
 */
fun nextRotationTarget(current: Float, wanted: Float): Float {
    val delta = ((wanted - current + 540f) % 360f + 360f) % 360f - 180f
    return current + delta
}

/** The original's `transform 0.3s ease` on `.camera-button`. */
private const val POSE_ROTATION_MS = 300

/**
 * [devicePoseUiRotation], animated the short way round — what a reader binds
 * to `rotationZ`.
 */
@Composable
fun rememberDevicePoseRotation(deviceRotationDeg: Int?, screenAngleDeg: Int): Float {
    val wanted = devicePoseUiRotation(deviceRotationDeg, screenAngleDeg)
    var target by remember { mutableStateOf(wanted) }
    LaunchedEffect(wanted) { target = nextRotationTarget(target, wanted) }
    val animated by animateFloatAsState(
        targetValue = target,
        animationSpec = tween(POSE_ROTATION_MS),
        label = "device-pose",
    )
    return animated
}

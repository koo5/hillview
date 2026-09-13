package cz.hillview.core.ui

import androidx.compose.runtime.Composable

/**
 * The DISPLAY's rotation away from its natural orientation, in degrees
 * (0/90/180/270).
 *
 * The port of the original's `screenOrientationAngle` store, which it fills
 * from `screen.orientation.angle` on the web and from the plugin's
 * `screen-angle` event under Tauri.
 *
 * Distinct from the device's own pose, and the distinction is the point:
 * under a rotation lock the device keeps turning while this stays put, and
 * the gap between the two is exactly what
 * [cz.hillview.capture.devicePoseUiRotation] renders.
 */
@Composable
expect fun rememberScreenAngleDeg(): Int

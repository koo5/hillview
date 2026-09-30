package cz.hillview.lock

import android.app.Activity
import android.util.Log
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.core.view.WindowInsetsControllerCompat
import cz.hillview.auth.CurrentActivityHolder

private const val TAG = "hv-ControlsLock"

@Composable
actual fun ApplyControlsLock(active: Boolean, options: LockOptions) {
    val activity = CurrentActivityHolder.activity
    DisposableEffect(active, options, activity) {
        if (!active || activity == null) return@DisposableEffect onDispose { }
        val window = activity.window
        val previousBrightness = window.attributes.screenBrightness

        // Unconditional: the run dies with the activity, and the activity
        // stops when the display sleeps.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        if (options.dimScreen) {
            window.attributes = window.attributes.apply {
                // 0 is the dimmest the panel will go, not off — the display
                // must stay on for the camera to stay bound, so this is as
                // dark as a locked phone can be while still shooting.
                screenBrightness = options.brightness.coerceIn(0f, 1f)
            }
        }

        val bars = WindowInsetsControllerCompat(window, window.decorView)
        if (options.hideSystemBars) {
            bars.systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            bars.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        }

        if (options.pinScreen) startPinning(activity)

        onDispose {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            window.attributes = window.attributes.apply {
                screenBrightness = previousBrightness
            }
            if (options.hideSystemBars) {
                bars.show(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            }
            if (options.pinScreen) stopPinning(activity)
        }
    }
}

/**
 * Android's lock task mode, in its unprivileged form: the system asks the
 * user to confirm, then blocks home and recents and strips the shade back.
 * It is the only mechanism that reaches the system gestures at all — a scrim
 * of our own can never see them.
 *
 * It can simply refuse (app pinning disabled on the device, an OEM that does
 * not allow it), and the lock is still worth having without it, so a refusal
 * is logged rather than surfaced.
 */
private fun startPinning(activity: Activity) {
    try {
        activity.startLockTask()
    } catch (e: Exception) {
        Log.w(TAG, "the device would not pin the screen", e)
    }
}

private fun stopPinning(activity: Activity) {
    try {
        activity.stopLockTask()
    } catch (e: Exception) {
        // Already out of it — the user can leave pinning by the system
        // gesture, which is the point of the gesture.
        Log.w(TAG, "not pinned any more", e)
    }
}

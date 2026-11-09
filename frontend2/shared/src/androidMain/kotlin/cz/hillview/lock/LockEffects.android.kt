package cz.hillview.lock

import android.app.Activity
import android.app.ActivityManager
import android.os.SystemClock
import android.util.Log
import android.view.WindowManager
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.core.view.WindowInsetsControllerCompat
import cz.hillview.auth.CurrentActivityHolder
import cz.hillview.plugin.hvTag
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay

private val TAG = hvTag("ControlsLock")

@Composable
actual fun ApplyControlsLock(active: Boolean, options: LockOptions) {
    val activity = CurrentActivityHolder.activity
    DisposableEffect(active, options, activity) {
        if (!active || activity == null) return@DisposableEffect onDispose { }
        val window = activity.window

        // Unconditional: the run dies with the activity, and the activity
        // stops when the display sleeps.
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        // The dim is NOT here any more: it has to wait for the pinning
        // dialog, so it has its own effect below (DIM_AFTER_PIN_PROMPT_MS).

        val bars = WindowInsetsControllerCompat(window, window.decorView)
        if (options.hideSystemBars) {
            bars.systemBarsBehavior =
                WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            bars.hide(androidx.core.view.WindowInsetsCompat.Type.systemBars())
        }

        if (options.pinScreen) startPinning(activity)

        onDispose {
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            if (options.hideSystemBars) {
                bars.show(androidx.core.view.WindowInsetsCompat.Type.systemBars())
            }
            if (options.pinScreen) stopPinning(activity)
        }
    }

    // The dim, on its own clock: with pinning asked for, the system's "Pin
    // this app?" confirmation comes up first, and it used to come up on a
    // screen already taken to the floor. So this waits for the pin to take
    // hold, or DIM_AFTER_PIN_PROMPT_MS for a dialog declined or ignored —
    // see dimNow. Without pinning it dims at once, as it always did.
    LaunchedEffect(active, options, activity) {
        if (!active || activity == null || !options.dimScreen) return@LaunchedEffect
        val window = activity.window
        val previousBrightness = window.attributes.screenBrightness
        try {
            val lockedAt = SystemClock.elapsedRealtime()
            while (!dimNow(options.pinScreen, isPinned(activity), SystemClock.elapsedRealtime() - lockedAt)) {
                delay(PIN_POLL_MS)
            }
            window.attributes = window.attributes.apply {
                // 0 is the dimmest the panel will go, not off — the display
                // must stay on for the camera to stay bound, so this is as
                // dark as a locked phone can be while still shooting.
                screenBrightness = options.brightness.coerceIn(0f, 1f)
            }
            awaitCancellation()
        } finally {
            // Unlocked, or left: back to what it was, dimmed yet or not.
            window.attributes = window.attributes.apply {
                screenBrightness = previousBrightness
            }
        }
    }
}

/** Whether the pin has taken hold — the user confirmed the system's dialog. */
private fun isPinned(activity: Activity): Boolean =
    activity.getSystemService(ActivityManager::class.java)?.lockTaskModeState
        ?.let { it != ActivityManager.LOCK_TASK_MODE_NONE } == true

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

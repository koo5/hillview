package cz.hillview.pip

import android.app.PictureInPictureParams
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.MediaStore
import android.util.Log
import android.util.Rational
import cz.hillview.auth.CurrentActivityHolder

private const val TAG = "hv-Pip"

actual fun pipSupported(): Boolean {
    val activity = CurrentActivityHolder.activity ?: return false
    return activity.packageManager
        .hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE)
}

actual fun enterPipMode() {
    val activity = CurrentActivityHolder.activity ?: run {
        Log.w(TAG, "no live activity to float")
        return
    }
    try {
        // 16:9 landscape: a floating MAP wants width — a portrait sliver
        // shows almost no ground either side of the arrow. The system
        // clamps anything outside roughly 2.39:1…1:2.39 anyway.
        val params = PictureInPictureParams.Builder()
            .setAspectRatio(Rational(16, 9))
            .apply {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    // Smooth the shrink instead of cross-fading a resize.
                    setSeamlessResizeEnabled(true)
                }
            }
            .build()
        activity.enterPictureInPictureMode(params)
    } catch (e: Exception) {
        // Devices can refuse (PiP disabled for the app in system settings,
        // some OEM builds) — the caller has already switched to the
        // external-camera activity, which still records; it just does not
        // float.
        Log.w(TAG, "entering PiP failed", e)
    }
}

actual fun launchSystemCamera() {
    val activity = CurrentActivityHolder.activity ?: return
    try {
        activity.startActivity(
            Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    } catch (e: ActivityNotFoundException) {
        Log.w(TAG, "no camera app to open", e)
    }
}

package cz.hillview.external

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.MediaStore
import android.util.Log
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import cz.hillview.plugin.GeoTrackingDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.withContext

private const val TAG = "ExternalCamera"

private class AndroidExternalCameraController(
    private val context: Context,
) : ExternalCameraController {
    override val running: StateFlow<Boolean> = ExternalCameraService.running
    override val status: StateFlow<String> = ExternalCameraService.statusLine
    private val _notice = MutableStateFlow<String?>(null)
    override val notice: StateFlow<String?> = _notice

    override fun setRunning(on: Boolean) {
        if (!on) {
            ExternalCameraService.stop(context)
            return
        }
        // A location foreground service without the permission would crash on
        // start (Android 14 enforces the type's prerequisites) — say why
        // instead. The capture or map pane is where it gets granted.
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            _notice.value = "Location permission missing — open the capture pane once to grant it."
            return
        }
        _notice.value = null
        ExternalCameraService.start(context)
    }

    override fun openSystemCamera() {
        try {
            context.startActivity(
                Intent(MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        } catch (e: ActivityNotFoundException) {
            Log.w(TAG, "no camera app to open", e)
            _notice.value = "No camera app found on this device."
        }
    }

    override suspend fun tableCounts(): Pair<Int, Int> = withContext(Dispatchers.IO) {
        val db = GeoTrackingDatabase.getDatabase(context)
        db.bearingDao().countBearings() to db.locationDao().countLocations()
    }
}

@Composable
actual fun rememberExternalCameraController(): ExternalCameraController {
    val context = LocalContext.current.applicationContext
    return remember { AndroidExternalCameraController(context) }
}

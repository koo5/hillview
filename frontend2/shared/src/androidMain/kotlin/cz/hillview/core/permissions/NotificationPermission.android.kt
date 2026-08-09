package cz.hillview.core.permissions

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable

@Composable
actual fun rememberNotificationPermissionRequester(): () -> Unit {
    if (Build.VERSION.SDK_INT < 33) return {}
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { /* best-effort: uploads work either way, just without notifications */ }
    return { launcher.launch(Manifest.permission.POST_NOTIFICATIONS) }
}

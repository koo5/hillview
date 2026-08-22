package cz.hillview.core.permissions

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LifecycleResumeEffect

/**
 * Runtime-permission state for one gate. [granted] covers [permissions];
 * [permanentlyDenied] flips when a request comes back denied and the system
 * won't show the dialog again (the "twice denied" / "don't ask again" state)
 * — the only way forward then is the app's system-settings page.
 * Re-checked on every resume, so flipping the permission in system settings
 * and returning is picked up.
 */
@Stable
class PermissionsState internal constructor(
    private val context: Context,
    internal val permissions: List<String>,
) {
    var granted by mutableStateOf(check())
        internal set
    var permanentlyDenied by mutableStateOf(false)
        internal set

    internal var launch: (() -> Unit)? = null

    internal fun check(): Boolean = permissions.all {
        ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
    }

    internal fun refresh() {
        granted = check()
        if (granted) permanentlyDenied = false
    }

    fun request() {
        launch?.invoke()
    }

    fun openAppSettings() {
        context.startActivity(
            Intent(
                Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                Uri.fromParts("package", context.packageName, null),
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}

/**
 * [alsoRequest]: extra permissions bundled into the same system request flow
 * (one dialog cascade on first use) WITHOUT gating [PermissionsState.granted]
 * — e.g. capture asks for location alongside camera, but only camera is
 * required to proceed.
 */
@Composable
fun rememberPermissionsState(
    permissions: List<String>,
    alsoRequest: List<String> = emptyList(),
): PermissionsState {
    val context = LocalContext.current
    val activity = remember(context) { context.findActivity() }
    val state = remember(permissions, alsoRequest) {
        PermissionsState(context.applicationContext, permissions)
    }
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        state.refresh()
        if (!state.granted) {
            // After a real denial, rationale=true means the system will still
            // show the dialog next time; none-true means it won't.
            val canAskAgain = activity != null && state.permissions.any {
                ActivityCompat.shouldShowRequestPermissionRationale(activity, it)
            }
            state.permanentlyDenied = !canAskAgain
        }
    }
    state.launch = { launcher.launch((permissions + alsoRequest).toTypedArray()) }
    LifecycleResumeEffect(state) {
        state.refresh()
        onPauseOrDispose { }
    }
    return state
}

/**
 * The standard "this screen needs a permission" pane: explanation +
 * grant button, degrading to an open-app-settings button on permanent
 * denial. testTags: "<prefix>-grant" / "<prefix>-open-settings".
 */
@Composable
fun PermissionGatePane(
    state: PermissionsState,
    explanation: String,
    testTagPrefix: String,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier.background(Color(0xFF111111)),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(24.dp),
        ) {
            Text(
                text = if (state.permanentlyDenied) {
                    "$explanation Access was denied — enable it in the app's system settings."
                } else {
                    explanation
                },
                color = Color.White,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(bottom = 12.dp),
            )
            if (state.permanentlyDenied) {
                Button(
                    onClick = state::openAppSettings,
                    modifier = Modifier.testTag("$testTagPrefix-open-settings"),
                ) {
                    Text("Open app settings")
                }
            } else {
                Button(
                    onClick = state::request,
                    modifier = Modifier.testTag("$testTagPrefix-grant"),
                ) {
                    Text("Grant access")
                }
            }
        }
    }
}

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

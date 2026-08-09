package cz.hillview.external

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

private class DesktopExternalCameraController : ExternalCameraController {
    override val running: StateFlow<Boolean> = MutableStateFlow(false)
    override val status: StateFlow<String> = MutableStateFlow("—")
    override val notice: StateFlow<String?> =
        MutableStateFlow("External-camera tracking is an Android feature.")

    override fun setRunning(on: Boolean) {}
    override fun openSystemCamera() {}
    override suspend fun tableCounts(): Pair<Int, Int> = 0 to 0
}

@Composable
actual fun rememberExternalCameraController(): ExternalCameraController =
    remember { DesktopExternalCameraController() }

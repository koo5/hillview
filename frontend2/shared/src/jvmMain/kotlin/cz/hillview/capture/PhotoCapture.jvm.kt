package cz.hillview.capture

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

private class DesktopPhotoCapture : PhotoCapture {
    override val state = CaptureState(
        supported = false,
        errorMessage = "Photo capture is only available on Android.",
    )

    override var manualLocation: ManualLocation? = null
    override var manualLocationWins: Boolean = false
    override var shutterNs: Long? = null
    override var ecoPreviewFps: Boolean = false

    override fun capture() {}

    @Composable
    override fun CameraPane(modifier: Modifier) {
        Box(
            modifier = modifier.background(Color(0xFF111111)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = "Camera not available on desktop",
                color = MaterialTheme.colorScheme.onPrimary,
            )
        }
    }
}

@Composable
actual fun rememberPhotoCapture(): PhotoCapture = remember { DesktopPhotoCapture() }

package cz.hillview

import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId

class MainActivity : ComponentActivity() {
    @OptIn(ExperimentalComposeUiApi::class)
    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContent {
            // Expose Compose testTags as resource-ids so uiautomator/Appium can
            // find them, mirroring the old app's data-testid convention.
            Box(Modifier.semantics { testTagsAsResourceId = true }) {
                App()
            }
        }
    }

    // Credential Manager sheets need a live activity window — registered
    // here, read by AndroidCredentialGateway. (The sheet itself pauses the
    // activity; the gateway captures the reference before launching.)
    override fun onResume() {
        super.onResume()
        cz.hillview.auth.CurrentActivityHolder.activity = this
    }

    override fun onPause() {
        super.onPause()
        // PiP pauses the activity while it keeps rendering, so the activity
        // reference must SURVIVE that pause — it is what float mode uses to
        // leave PiP and to launch the camera app. Only a real backgrounding
        // clears it.
        if (isInPictureInPictureMode) return
        if (cz.hillview.auth.CurrentActivityHolder.activity === this) {
            cz.hillview.auth.CurrentActivityHolder.activity = null
        }
    }

    override fun onPictureInPictureModeChanged(
        isInPictureInPictureMode: Boolean,
        newConfig: Configuration,
    ) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        // The UI strips itself down to the bare map in the float window —
        // see MainScreen. Leaving PiP restores the full page.
        cz.hillview.pip.PipState.setInPip(isInPictureInPictureMode)
    }
}

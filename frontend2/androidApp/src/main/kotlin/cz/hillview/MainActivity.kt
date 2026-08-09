package cz.hillview

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
        if (cz.hillview.auth.CurrentActivityHolder.activity === this) {
            cz.hillview.auth.CurrentActivityHolder.activity = null
        }
    }
}

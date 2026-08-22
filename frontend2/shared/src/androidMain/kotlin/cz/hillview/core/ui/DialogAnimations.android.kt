package cz.hillview.core.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.window.DialogWindowProvider

@Composable
actual fun InstantDialogWindow() {
    val view = LocalView.current
    SideEffect {
        // The dialog's compose view hangs off a DialogWindowProvider;
        // android.R.style.Animation is the base style with no enter/exit
        // animations. Applied before the window is first shown, so the
        // open is instant too.
        (view.parent as? DialogWindowProvider)?.window
            ?.setWindowAnimations(android.R.style.Animation)
    }
}

package cz.hillview.core.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color

// Battery is a stated requirement: the default dark scheme uses true black
// surfaces (AMOLED) — the app is a field tool used for hours with the screen
// on.
private val DarkColors = darkColorScheme(
    primary = Color(0xFF8FD694),
    onPrimary = Color(0xFF00390F),
    primaryContainer = Color(0xFF1B5E20),
    onPrimaryContainer = Color(0xFFC8E6C9),
    secondary = Color(0xFFB0BEC5),
    background = Color(0xFF000000),
    onBackground = Color(0xFFE0E0E0),
    surface = Color(0xFF000000),
    onSurface = Color(0xFFE0E0E0),
    surfaceVariant = Color(0xFF121212),
    onSurfaceVariant = Color(0xFFB0B0B0),
    error = Color(0xFFFF8A80),
)

private val LightColors = lightColorScheme(
    primary = Color(0xFF2E7D32),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFC8E6C9),
    onPrimaryContainer = Color(0xFF1B5E20),
)

/**
 * For subtrees that are LIGHT whatever the app theme is — the map's floating
 * control panels, which sit over tiles whose brightness the tile PROVIDER
 * chooses, so they carry their own contrast rather than following ours.
 *
 * A content colour alone is not enough: a TextButton takes its ink from
 * colorScheme.primary, and the dark theme's primary is a pale green tuned for
 * a black background — legible there, washed out on a white panel. Handing
 * the subtree the light scheme fixes every component at once instead of
 * per-widget colour overrides.
 */
@Composable
fun LightPanelTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = LightColors, content = content)
}

@Composable
fun HillviewTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(colorScheme = if (darkTheme) DarkColors else LightColors) {
        // The Surface is not decoration — it is what sets LocalContentColor.
        //
        // MaterialTheme provides a colour SCHEME; it does not touch the
        // content colour, and Material3's default for that is Color.BLACK.
        // So every Text without an explicit colour rendered black, which in
        // light mode looks exactly right and hides the bug — and in dark mode
        // is black on a true-black background, i.e. invisible. That is why
        // only the explicitly-coloured text (the greens, the errors, an
        // OutlinedTextField's own labels) survived dark mode, and why whole
        // rows of settings looked empty rather than wrong.
        //
        // Surface sets background AND contentColorFor(background), so both
        // schemes get a readable pairing from one place.
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background,
            content = content,
        )
    }
}

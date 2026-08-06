package cz.hillview.map

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import cz.hillview.settings.MapSettingsRepository

@Composable
actual fun MapScreen(
    onBack: () -> Unit,
    settings: MapSettingsRepository,
    markerSource: PhotoMarkerSource,
) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("The map is Android-only for now.", style = MaterialTheme.typography.bodyLarge)
            TextButton(onClick = onBack) { Text("< Back") }
        }
    }
}

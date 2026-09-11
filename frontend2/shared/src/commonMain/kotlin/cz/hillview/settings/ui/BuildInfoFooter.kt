package cz.hillview.settings.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.BuildInfo

/** The build identity at the foot of Settings — see [BuildInfo]. */
@Composable
fun BuildInfoFooter(label: String = BuildInfo.label()) {
    Text(
        text = "Build $label",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier
            .fillMaxWidth()
            .padding(top = 8.dp)
            .testTag("settings-build-info"),
    )
}

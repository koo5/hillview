package cz.hillview.map

import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.foundation.Canvas
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import cz.hillview.settings.MAX_MAX_PHOTOS
import cz.hillview.settings.MIN_MAX_PHOTOS
import cz.hillview.settings.MapSettings
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Everything drawn over the map: the bearing arrow (draggable), the sensor
 * controls, and the filters entry point.
 */
@Composable
fun MapOverlayUi(
    onBack: () -> Unit,
    camera: MapCamera,
    settings: MapSettings,
    markerCount: Int,
    hasFix: Boolean,
    sensorHeading: Float?,
    onBearingDrag: (Double) -> Unit,
    onCompassDisabledByDrag: () -> Unit,
    onSettingsChange: ((MapSettings) -> MapSettings) -> Unit,
    onZoom: (Double) -> Unit,
) {
    var showFilters by remember { mutableStateOf(false) }
    var showSensors by remember { mutableStateOf(false) }

    BearingArrow(
        bearingDeg = camera.bearingDeg,
        fullCircleHitArea = settings.bearingMode == BearingMode.Car,
        onDragStart = onCompassDisabledByDrag,
        onBearing = onBearingDrag,
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .padding(12.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top,
        ) {
            Card {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = onBack) { Text("< Back") }
                    Text(
                        text = "${camera.bearingDeg.roundToInt()}° · $markerCount photos" +
                            (if (hasFix) "" else " · no GPS"),
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier
                            .padding(end = 12.dp)
                            .testTag("map-status"),
                    )
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                Card {
                    TextButton(
                        onClick = { showSensors = true },
                        modifier = Modifier.testTag("map-sensors-button"),
                    ) { Text("Sensors") }
                }
                Card(modifier = Modifier.padding(top = 6.dp)) {
                    TextButton(
                        onClick = { showFilters = true },
                        modifier = Modifier.testTag("map-filters-button"),
                    ) { Text("Filters") }
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.End,
        ) {
            Card {
                TextButton(
                    onClick = { onZoom(1.0) },
                    modifier = Modifier.testTag("map-zoom-in"),
                ) { Text("+", style = MaterialTheme.typography.titleLarge) }
            }
            Card(modifier = Modifier.padding(start = 6.dp)) {
                TextButton(
                    onClick = { onZoom(-1.0) },
                    modifier = Modifier.testTag("map-zoom-out"),
                ) { Text("−", style = MaterialTheme.typography.titleLarge) }
            }
        }
    }

    if (showFilters) {
        FiltersDialog(
            settings = settings,
            onDismiss = { showFilters = false },
            onSettingsChange = onSettingsChange,
        )
    }
    if (showSensors) {
        SensorsDialog(
            settings = settings,
            sensorHeading = sensorHeading,
            onDismiss = { showSensors = false },
            onSettingsChange = onSettingsChange,
        )
    }
}

/**
 * Centre dot with an arrow to the range circle. Dragging sets the bearing —
 * the grabbable area is the outer third of the arrow, or the whole circle in
 * car mode (where the arrow may sit anywhere relative to travel, so requiring
 * a precise grab would be cruel). Ported from BearingStateArrow.svelte.
 */
@Composable
private fun BearingArrow(
    bearingDeg: Double,
    fullCircleHitArea: Boolean,
    onDragStart: () -> Unit,
    onBearing: (Double) -> Unit,
) {
    val arrowColor = Color(0xFF0405FA)
    Canvas(
        modifier = Modifier
            .fillMaxSize()
            .testTag("map-bearing-arrow")
            .pointerInput(fullCircleHitArea) {
                val centre = Offset(size.width / 2f, size.height / 2f)
                val radius = min(size.width, size.height) / 2f * 0.75f

                fun bearingOf(position: Offset): Double {
                    val dx = position.x - centre.x
                    val dy = position.y - centre.y
                    return (Math.toDegrees(atan2(dx, -dy).toDouble()) + 360.0) % 360.0
                }

                fun grabbable(position: Offset): Boolean {
                    val distance = hypot(position.x - centre.x, position.y - centre.y)
                    if (fullCircleHitArea) return distance <= radius * 1.15f
                    // Outer third of the arrow, with slack for fingers.
                    return distance in (radius * 0.55f)..(radius * 1.15f)
                }

                var dragging = false
                detectDragGestures(
                    onDragStart = { position ->
                        dragging = grabbable(position)
                        if (dragging) {
                            onDragStart()
                            onBearing(bearingOf(position))
                        }
                    },
                    onDragEnd = { dragging = false },
                    onDragCancel = { dragging = false },
                    onDrag = { change, _ ->
                        if (dragging) {
                            change.consume()
                            onBearing(bearingOf(change.position))
                        }
                    },
                )
            },
    ) {
        val centre = Offset(size.width / 2f, size.height / 2f)
        val radius = min(size.width, size.height) / 2f * 0.75f
        val radians = Math.toRadians(bearingDeg)
        val tip = Offset(
            centre.x + (kotlin.math.sin(radians) * radius).toFloat(),
            centre.y - (kotlin.math.cos(radians) * radius).toFloat(),
        )

        // Range circle — also the drag target in car mode.
        drawCircle(
            color = arrowColor.copy(alpha = if (fullCircleHitArea) 0.35f else 0.18f),
            radius = radius,
            center = centre,
            style = Stroke(width = if (fullCircleHitArea) 6f else 3f),
        )
        drawLine(
            color = arrowColor.copy(alpha = 0.6f),
            start = centre,
            end = tip,
            strokeWidth = 10f,
        )
        drawCircle(color = arrowColor.copy(alpha = 0.7f), radius = 16f, center = tip)
        drawCircle(color = Color.Red.copy(alpha = 0.6f), radius = 9f, center = centre)
    }
}

@Composable
private fun FiltersDialog(
    settings: MapSettings,
    onDismiss: () -> Unit,
    onSettingsChange: ((MapSettings) -> MapSettings) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Done") } },
        title = { Text("Filters") },
        text = {
            Column {
                Text(
                    "Recent photos shown: ${settings.maxPhotos}",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.testTag("filters-max-photos-value"),
                )
                Text(
                    "Scaffolding: the last N photos captured on this device. " +
                        "Browsing photos from the server comes later.",
                    style = MaterialTheme.typography.bodySmall,
                )
                Slider(
                    value = settings.maxPhotos.toFloat(),
                    onValueChange = { value ->
                        onSettingsChange { it.copy(maxPhotos = value.roundToInt()) }
                    },
                    valueRange = MIN_MAX_PHOTOS.toFloat()..MAX_MAX_PHOTOS.toFloat(),
                    modifier = Modifier.testTag("filters-max-photos"),
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text("$MIN_MAX_PHOTOS", style = MaterialTheme.typography.bodySmall)
                    Text("$MAX_MAX_PHOTOS", style = MaterialTheme.typography.bodySmall)
                }
            }
        },
    )
}

/** The five fusion modes of the shared EnhancedSensorService, by its constants. */
private val SENSOR_MODES = listOf(
    4 to "Upright rotation vector",
    0 to "Rotation vector",
    1 to "Game rotation vector",
    2 to "Madgwick AHRS",
    3 to "Complementary filter",
)

@Composable
private fun SensorsDialog(
    settings: MapSettings,
    sensorHeading: Float?,
    onDismiss: () -> Unit,
    onSettingsChange: ((MapSettings) -> MapSettings) -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = onDismiss) { Text("Done") } },
        title = { Text("Sensors") },
        text = {
            Column {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text("Compass", style = MaterialTheme.typography.bodyLarge)
                        Text(
                            text = sensorHeading?.let { "reading ${it.roundToInt()}° true" }
                                ?: "off — the arrow stays where you drag it",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    Switch(
                        checked = settings.compassEnabled,
                        onCheckedChange = { on ->
                            onSettingsChange { it.copy(compassEnabled = on) }
                        },
                        modifier = Modifier.testTag("sensors-compass-toggle"),
                    )
                }

                Text(
                    "Fusion mode",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(top = 12.dp),
                )
                SENSOR_MODES.forEach { (mode, label) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        FilterChip(
                            selected = settings.sensorMode == mode,
                            onClick = { onSettingsChange { it.copy(sensorMode = mode) } },
                            label = { Text(label) },
                            modifier = Modifier
                                .padding(vertical = 2.dp)
                                .testTag("sensors-mode-$mode"),
                        )
                    }
                }

                Text(
                    "Bearing mode",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.padding(top = 12.dp),
                )
                Row {
                    BearingMode.entries.forEach { mode ->
                        FilterChip(
                            selected = settings.bearingMode == mode,
                            onClick = { onSettingsChange { it.copy(bearingMode = mode) } },
                            label = { Text(if (mode == BearingMode.Car) "Car" else "Walking") },
                            modifier = Modifier
                                .padding(end = 6.dp)
                                .testTag("sensors-bearing-${mode.name.lowercase()}"),
                        )
                    }
                }
                Text(
                    "Car mode drags the camera mount offset instead of the heading, " +
                        "and the whole circle is grabbable.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        },
    )
}

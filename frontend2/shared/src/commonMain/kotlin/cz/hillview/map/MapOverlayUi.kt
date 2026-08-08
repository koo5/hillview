package cz.hillview.map

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.layout.layout
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import cz.hillview.settings.MAX_MAX_PHOTOS
import cz.hillview.settings.MIN_MAX_PHOTOS
import cz.hillview.settings.MapSettings
import kotlin.math.roundToInt

/** The blue the Tauri controls use for "on". */
private val ACTIVE_BLUE = Color(0xFF4285F4)
private val ACTIVE_BLUE_BORDER = Color(0xFF3367D6)
private val PANEL_WHITE = Color(0xE6FFFFFF)

/** What the compass button shows — intent and reality are separate. */
enum class TrackingPhase { Inactive, Starting, Active, Error }

data class MapSourceUi(
    val id: String,
    val name: String,
    val enabled: Boolean,
    val loading: Boolean = false,
)

/**
 * Everything drawn over the map, laid out as in the Tauri app: the
 * location/compass pair top-right, and the hunter-controls grid bottom-right
 * whose panels appear only in hunter mode. See
 * docs/tauri-map-ui-contract.md.
 */
@Composable
fun MapOverlayUi(
    settings: MapSettings,
    hunterMode: Boolean,
    sources: List<MapSourceUi>,
    activeFilterCount: Int,
    overrideFilters: Boolean,
    locationTracking: LocationTracking,
    locationFlash: Boolean,
    locationLoading: Boolean,
    powerSavingActive: Boolean,
    trackingWanted: Boolean,
    trackingPhase: TrackingPhase,
    compassUnavailable: Boolean,
    markerCount: Int,
    onToggleHunterMode: () -> Unit,
    onToggleSource: (String) -> Unit,
    onOpenFilters: () -> Unit,
    onToggleOverrideFilters: () -> Unit,
    currentTileProvider: String,
    onPickTileProvider: (String) -> Unit,
    onToggleLocation: () -> Unit,
    onToggleTracking: () -> Unit,
    onSelectBearingMode: (BearingMode) -> Unit,
    onZoom: (Double) -> Unit,
    positionPrompt: Boolean = false,
    onClaimManualPosition: () -> Unit = {},
    onRevertToGps: () -> Unit = {},
    mapOrientation: Double = 0.0,
    onResetNorth: () -> Unit = {},
) {
    Box(Modifier.fillMaxSize().safeContentPadding()) {
        // Top-left: zoom, where Leaflet keeps it (44dp touch targets).
        Column(Modifier.align(Alignment.TopStart).padding(8.dp)) {
            ControlSurface {
                TextButton(
                    onClick = { onZoom(1.0) },
                    modifier = Modifier.size(44.dp).testTag("zoom-in-btn"),
                ) { Text("+", style = MaterialTheme.typography.titleLarge) }
            }
            ControlSurface(Modifier.padding(top = 2.dp)) {
                TextButton(
                    onClick = { onZoom(-1.0) },
                    modifier = Modifier.size(44.dp).testTag("zoom-out-btn"),
                ) { Text("−", style = MaterialTheme.typography.titleLarge) }
            }
            // (The interim "< Back" button is gone: the map is a pane of the
            // Main page now, not a destination — the original never had one.)

            // A turned map needs a way back, or the gesture is a trap: the
            // original never rotates, so it never had to answer this. The
            // needle appears only once the map is off north, points at true
            // north, and puts it back — the badge every map app uses, which
            // means nobody has to be taught it.
            if (kotlin.math.abs(normalizeBearing(mapOrientation).let {
                    if (it > 180) it - 360 else it
                }) >= 1.0
            ) {
                ControlSurface(Modifier.padding(top = 8.dp)) {
                    TextButton(
                        onClick = onResetNorth,
                        modifier = Modifier.size(44.dp).testTag("reset-north-btn"),
                    ) {
                        Text(
                            "↑N",
                            color = Color(0xFFD93025),
                            style = MaterialTheme.typography.labelLarge,
                            modifier = Modifier.rotate(-mapOrientation.toFloat()),
                        )
                    }
                }
            }
        }

        // Top-right pair: location, then compass.
        Row(
            modifier = Modifier.align(Alignment.TopEnd).padding(top = 16.dp, end = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            LocationButton(
                tracking = locationTracking,
                flash = locationFlash,
                loading = locationLoading,
                powerSaving = powerSavingActive,
                onClick = onToggleLocation,
            )
            CompassButton(
                bearingMode = settings.bearingMode,
                wanted = trackingWanted,
                phase = trackingPhase,
                unavailable = compassUnavailable,
                onToggle = onToggleTracking,
                onSelectMode = onSelectBearingMode,
            )
        }

        // Right-edge source tabs — the original's hunter-panel-right:
        // vertical labels on white tabs down the map's right edge, only in
        // hunter mode.
        HunterPanel(
            visible = hunterMode,
            modifier = Modifier.align(Alignment.CenterEnd).padding(end = 2.dp),
        ) {
            Column(
                modifier = Modifier.heightIn(max = 420.dp).padding(2.dp),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                sources.forEach { source ->
                    SourceButton(source, onClick = { onToggleSource(source.id) })
                }
            }
        }

        // Bottom-right hunter grid: the toggle owns the corner, the button
        // panel grows left.
        Column(
            modifier = Modifier.align(Alignment.BottomEnd).padding(bottom = 4.dp, end = 6.dp),
            horizontalAlignment = Alignment.End,
        ) {
            Row(verticalAlignment = Alignment.Bottom) {
                HunterPanel(visible = hunterMode) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(horizontal = 4.dp),
                    ) {
                        FiltersButton(
                            activeFilterCount = activeFilterCount,
                            overridden = overrideFilters,
                            onShortPress = onOpenFilters,
                            onLongPress = onToggleOverrideFilters,
                        )
                        PanelSeparator()
                        Box {
                            var tileMenuOpen by remember { mutableStateOf(false) }
                            TextButton(
                                onClick = { tileMenuOpen = true },
                                modifier = Modifier.testTag("tile-provider-button"),
                            ) { Text("Map ▾") }
                            // A native anchored popup (closes on click-away,
                            // scrolls when the list outgrows the screen) —
                            // the AlertDialog it replaces was neither.
                            androidx.compose.material3.DropdownMenu(
                                expanded = tileMenuOpen,
                                onDismissRequest = { tileMenuOpen = false },
                                modifier = Modifier.testTag("tile-provider-menu"),
                            ) {
                                TILE_PROVIDERS.filterNot { it.devOnly }.forEach { provider ->
                                    androidx.compose.material3.DropdownMenuItem(
                                        text = {
                                            Text(
                                                if (provider.key == currentTileProvider) {
                                                    "✓ ${provider.displayName}"
                                                } else {
                                                    provider.displayName
                                                },
                                            )
                                        },
                                        onClick = {
                                            tileMenuOpen = false
                                            onPickTileProvider(provider.key)
                                        },
                                        modifier = Modifier
                                            .testTag("tile-provider-option-${provider.key}"),
                                    )
                                }
                            }
                        }
                    }
                }

                HunterToggle(active = hunterMode, onClick = onToggleHunterMode)
            }
        }

        // The exploration pill (user-raised, refined): panning is free and
        // changes nothing — this two-sided control is the only way the map
        // position becomes the capture position, and its other side snaps
        // you back to the fix. Deliberately small: it must not obscure the
        // map it is asking about.
        if (positionPrompt) {
            Row(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 76.dp)
                    .background(PANEL_WHITE, RoundedCornerShape(20.dp))
                    .testTag("map-position-prompt"),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                TextButton(
                    onClick = onClaimManualPosition,
                    modifier = Modifier.testTag("accept-manual-position"),
                ) { Text("Capture here") }
                PanelSeparator()
                TextButton(
                    onClick = onRevertToGps,
                    modifier = Modifier.testTag("revert-to-gps"),
                ) { Text("⟲ GPS") }
            }
        }

        Text(
            text = "$markerCount photos",
            style = MaterialTheme.typography.bodySmall,
            color = Color.Black.copy(alpha = 0.7f),
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(8.dp)
                .testTag("map-status"),
        )
    }
}

@Composable
private fun ControlSurface(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    Surface(
        modifier = modifier,
        color = PANEL_WHITE,
        shape = RoundedCornerShape(4.dp),
        shadowElevation = 2.dp,
        content = { content() },
    )
}

/** Panels fade rather than disappear, as in the CSS (opacity + no hit test). */
@Composable
private fun HunterPanel(
    visible: Boolean,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val alpha by animateFloatAsState(if (visible) 1f else 0f, label = "hunter-panel")
    if (alpha == 0f) return
    Surface(
        modifier = modifier.alpha(alpha).padding(bottom = 2.dp),
        color = PANEL_WHITE,
        shape = RoundedCornerShape(8.dp),
        shadowElevation = 2.dp,
    ) {
        content()
    }
}

/**
 * The vertical-tab text swap (the original's `writing-mode: vertical-rl`):
 * report height×width, then rotate the drawing into the swapped bounds.
 */
private fun Modifier.verticalLabel(): Modifier = this
    .layout { measurable, constraints ->
        val placeable = measurable.measure(constraints)
        layout(placeable.height, placeable.width) {
            placeable.place(
                x = -(placeable.width / 2 - placeable.height / 2),
                y = -(placeable.height / 2 - placeable.width / 2),
            )
        }
    }
    .rotate(90f)

@Composable
private fun HunterToggle(active: Boolean, onClick: () -> Unit) {
    Surface(
        color = PANEL_WHITE,
        shape = RoundedCornerShape(topStart = 4.dp, bottomEnd = 8.dp),
        shadowElevation = if (active) 0.dp else 2.dp,
        modifier = Modifier.testTag("hunter-mode-toggle"),
    ) {
        TextButton(onClick = onClick) {
            // The bow icon is inlined lucide art in the original; a caret
            // pair plus a bow glyph reads the same at this size.
            Text(
                text = if (active) "⌄ 🏹" else "⌃ 🏹",
                color = if (active) ACTIVE_BLUE else Color.Black.copy(alpha = 0.6f),
            )
        }
    }
}

@Composable
private fun SourceButton(source: MapSourceUi, onClick: () -> Unit) {
    Surface(
        color = if (source.enabled) ACTIVE_BLUE else Color.White,
        border = androidx.compose.foundation.BorderStroke(
            1.dp,
            if (source.enabled) ACTIVE_BLUE_BORDER else Color(0xFFCCCCCC),
        ),
        shape = RoundedCornerShape(4.dp),
        onClick = onClick,
        modifier = Modifier.testTag("source-toggle-${source.id}"),
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 10.dp),
        ) {
            Text(
                text = source.name,
                color = if (source.enabled) Color.White else Color.Black,
                style = MaterialTheme.typography.labelLarge,
                maxLines = 1,
                modifier = Modifier.verticalLabel(),
            )
            if (source.enabled && source.loading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(20.dp),
                    strokeWidth = 2.dp,
                    color = Color.White,
                )
            }
        }
    }
}

/**
 * Short press opens the modal, long press toggles the override — and when
 * overridden the label is struck through, as in the CSS.
 */
@Composable
private fun FiltersButton(
    activeFilterCount: Int,
    overridden: Boolean,
    onShortPress: () -> Unit,
    onLongPress: () -> Unit,
) {
    Surface(
        color = if (activeFilterCount > 0) Color(0xFF3B82F6) else Color.Transparent,
        shape = RoundedCornerShape(4.dp),
        modifier = Modifier
            .testTag("filters-button")
            .pointerInput(Unit) {
                detectTapGestures(onTap = { onShortPress() }, onLongPress = { onLongPress() })
            },
    ) {
        Text(
            text = "Filters ($activeFilterCount)",
            color = if (activeFilterCount > 0) Color.White else Color.Black,
            textDecoration = if (overridden) TextDecoration.LineThrough else null,
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
        )
    }
}

@Composable
private fun PanelSeparator() {
    Box(
        Modifier
            .padding(horizontal = 4.dp)
            .size(width = 1.dp, height = 24.dp)
            .background(Color.Black.copy(alpha = 0.15f)),
    )
}

/**
 * Tri-state: white when off, blue when following, half-blue in background —
 * "GPS still on (and still flashing on each fix) but the map no longer
 * follows". Green flash on each fix, leaf badge under power saving.
 */
@Composable
private fun LocationButton(
    tracking: LocationTracking,
    flash: Boolean,
    loading: Boolean,
    powerSaving: Boolean,
    onClick: () -> Unit,
) {
    val fill = when (tracking) {
        LocationTracking.Active -> ACTIVE_BLUE
        LocationTracking.Background -> ACTIVE_BLUE.copy(alpha = 0.5f)
        LocationTracking.Off -> PANEL_WHITE
    }
    Box {
        Surface(
            color = fill,
            shape = RoundedCornerShape(4.dp),
            shadowElevation = 2.dp,
            border = androidx.compose.foundation.BorderStroke(2.dp, Color(0xFFDDDDDD)),
            modifier = Modifier
                .alpha(if (tracking == LocationTracking.Off) 0.6f else 1f)
                // Which of the three states this is in must be readable from
                // outside, not just inferable from a colour. The original
                // carries it as `active`/`background` classes, which is what
                // its suite asserts on; this is the same fact by another
                // name, and it is what a screen reader announces too.
                .semantics {
                    stateDescription = when (tracking) {
                        LocationTracking.Off -> "off"
                        LocationTracking.Active -> "active"
                        LocationTracking.Background -> "background"
                    }
                }
                .testTag("track-location-btn"),
        ) {
            TextButton(onClick = onClick, modifier = Modifier.size(width = 60.dp, height = 44.dp)) {
                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(18.dp),
                        strokeWidth = 2.dp,
                        color = ACTIVE_BLUE,
                    )
                } else {
                    Text(
                        text = "◎",
                        color = if (flash) Color(0xFF34D399) else {
                            if (tracking == LocationTracking.Off) Color.Black else Color.White
                        },
                        style = MaterialTheme.typography.titleMedium,
                    )
                }
            }
        }
        if (powerSaving) {
            Surface(
                color = Color(0xFF2EA043),
                shape = RoundedCornerShape(9.dp),
                modifier = Modifier
                    .size(18.dp)
                    .align(Alignment.TopEnd)
                    .testTag("location-power-saving-badge"),
            ) {
                Text("🍃", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

/**
 * Intent (`wanted`) drives "active"; the phase drives loading/error; only
 * walking mode can be unavailable. Long press opens the mode menu.
 */
@Composable
private fun CompassButton(
    bearingMode: BearingMode,
    wanted: Boolean,
    phase: TrackingPhase,
    unavailable: Boolean,
    onToggle: () -> Unit,
    onSelectMode: (BearingMode) -> Unit,
) {
    var menuOpen by remember { mutableStateOf(false) }

    Box {
        Surface(
            color = if (wanted) ACTIVE_BLUE else PANEL_WHITE,
            shape = RoundedCornerShape(4.dp),
            shadowElevation = 2.dp,
            border = androidx.compose.foundation.BorderStroke(
                2.dp,
                if (phase == TrackingPhase.Error) Color(0xFFF44336) else Color(0xFFDDDDDD),
            ),
            modifier = Modifier
                .alpha(if (unavailable) 0.5f else if (phase == TrackingPhase.Starting) 0.7f else 1f)
                .testTag("compass-button")
                .pointerInput(unavailable) {
                    detectTapGestures(
                        onTap = { if (!unavailable) onToggle() },
                        onLongPress = { menuOpen = true },
                    )
                },
        ) {
            Row(
                modifier = Modifier.size(width = 60.dp, height = 44.dp),
                horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "🧭",
                    color = if (wanted) Color.White else Color.Black,
                )
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = if (bearingMode == BearingMode.Car) "🚗" else "🚶",
                        style = MaterialTheme.typography.labelSmall,
                    )
                    Text("⌄", style = MaterialTheme.typography.labelSmall)
                }
            }
        }

        // Anchored dropdown, as the original's CompassModeMenu portal under
        // the button — instant, no dialog-window animation.
        androidx.compose.material3.DropdownMenu(
            expanded = menuOpen,
            onDismissRequest = { menuOpen = false },
            modifier = Modifier.testTag("compass-mode-menu"),
        ) {
            ModeRow(
                title = "Walking Mode",
                subtitle = "Compass bearing",
                selected = bearingMode == BearingMode.Walking,
                testTag = "walking-mode-option",
            ) { onSelectMode(BearingMode.Walking); menuOpen = false }
            ModeRow(
                title = "Car Mode",
                subtitle = "GPS bearing",
                selected = bearingMode == BearingMode.Car,
                testTag = "car-mode-option",
            ) { onSelectMode(BearingMode.Car); menuOpen = false }
        }
    }
}

@Composable
private fun ModeRow(
    title: String,
    subtitle: String,
    selected: Boolean,
    testTag: String,
    onClick: () -> Unit,
) {
    Surface(
        color = if (selected) ACTIVE_BLUE.copy(alpha = 0.15f) else Color.Transparent,
        shape = RoundedCornerShape(4.dp),
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp)
            .testTag(testTag),
    ) {
        TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.fillMaxWidth()) {
                Text(title, style = MaterialTheme.typography.bodyLarge)
                Text(subtitle, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/**
 * Max-photos only for now: the Tauri modal's other groups filter on backend
 * analysis, which frontend2's local marker source has nothing to answer
 * with. The override semantics (long-press) are implemented above.
 */
@Composable
fun FiltersDialog(
    settings: MapSettings,
    activeFilterCount: Int,
    onDismiss: () -> Unit,
    onSettingsChange: ((MapSettings) -> MapSettings) -> Unit,
    onClearFilters: () -> Unit = {},
) {
    // Both trailing controls are disabled until some filter is active —
    // there is nothing to clear, and "show unanalyzed" only *means*
    // anything relative to an analysis that is filtering. The original
    // gates them the same way and its suite asserts it.
    val anyFilterActive = activeFilterCount > 0

    AlertDialog(
        onDismissRequest = onDismiss,
        confirmButton = {
            cz.hillview.core.ui.InstantDialogWindow()
            TextButton(onClick = onDismiss) { Text("Done") }
        },
        dismissButton = {
            TextButton(
                onClick = onClearFilters,
                enabled = anyFilterActive,
                modifier = Modifier.testTag("filters-clear"),
            ) { Text("Clear filters") }
        },
        title = { Text("Filters") },
        text = {
            Column {
                Text(
                    "Max photos in area: ${settings.maxPhotos}",
                    style = MaterialTheme.typography.bodyLarge,
                    modifier = Modifier.testTag("filters-max-photos-value"),
                )
                Text(
                    "Maximum number of photos to load and display on the map",
                    style = MaterialTheme.typography.bodySmall,
                )
                Slider(
                    value = settings.maxPhotos.toFloat(),
                    onValueChange = { v ->
                        onSettingsChange { it.copy(maxPhotos = v.roundToInt()) }
                    },
                    valueRange = MIN_MAX_PHOTOS.toFloat()..MAX_MAX_PHOTOS.toFloat(),
                    modifier = Modifier.testTag("filters-max-photos"),
                )
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Checkbox(
                        checked = settings.showUnanalyzed,
                        onCheckedChange = { v ->
                            onSettingsChange { it.copy(showUnanalyzed = v) }
                        },
                        enabled = anyFilterActive,
                        modifier = Modifier.testTag("filters-show-unanalyzed"),
                    )
                    Text(
                        "Show unanalyzed photos",
                        style = MaterialTheme.typography.bodyMedium,
                        color = if (anyFilterActive) {
                            Color.Unspecified
                        } else {
                            MaterialTheme.colorScheme.onSurface.copy(alpha = 0.38f)
                        },
                    )
                }
                Text(
                    "The analysis filter controls (time of day, scenic score, " +
                        "features…) are still to come; the backend already flags " +
                        "non-matching photos and the map washes them out.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        },
    )
}

package cz.hillview.map

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.safeGestures
import androidx.compose.foundation.layout.windowInsetsPadding
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
import androidx.compose.ui.draw.scale
import androidx.compose.ui.layout.layout
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.dp
import cz.hillview.settings.MAX_MAX_PHOTOS
import cz.hillview.settings.MIN_MAX_PHOTOS
import cz.hillview.settings.MapSettings
import kotlin.math.roundToInt

/** The blue the Tauri controls use for "on". */
private val ACTIVE_BLUE = Color(0xFF4285F4)
private val ACTIVE_BLUE_BORDER = Color(0xFF3367D6)
private val PANEL_WHITE = Color(0xE6FFFFFF)

/**
 * The ink for [PANEL_WHITE] panels, stated rather than inherited.
 *
 * These panels are deliberately WHITE in both app themes — they float over
 * map tiles whose brightness is the tile provider's choice, not ours, so they
 * carry their own contrast with them. But Material's contentColorFor() only
 * knows colours that are in the scheme, and this one is not, so a Surface
 * painted with it leaves LocalContentColor untouched: the text inside took
 * whatever the app theme handed down. That was invisibly fine while the
 * ambient content colour was Material's black default, and became light-grey
 * -on-white the moment the app got a real dark theme. Panels that pick their
 * own background have to pick their own foreground too.
 */
private val PANEL_INK = Color(0xFF202124)

// The dark counterparts. Not pure black: a panel the same colour as a
// near-black basemap reads as a hole in the map rather than a control, so it
// sits slightly above the tiles and carries a hairline besides.
private val PANEL_DARK = Color(0xE61E1E1E)
private val PANEL_DARK_INK = Color(0xFFE8EAED)
private val PANEL_DARK_BORDER = Color(0x33FFFFFF)

/** What the panels are wearing, decided once per [MapChrome]. */
private data class ChromeTone(
    val panel: Color,
    val ink: Color,
    val border: Color?,
    /** Which scheme the panel hands its subtree — see LightPanelTheme. */
    val dark: Boolean,
)

private val LIGHT_TONE = ChromeTone(PANEL_WHITE, PANEL_INK, null, dark = false)
private val DARK_TONE = ChromeTone(PANEL_DARK, PANEL_DARK_INK, PANEL_DARK_BORDER, dark = true)

private val LocalChromeTone = androidx.compose.runtime.staticCompositionLocalOf { LIGHT_TONE }

/**
 * The tone for a provider. OnMixed goes opaque — over aerial imagery the
 * panel cannot borrow the map as a background, and once it is opaque the
 * choice of tone is free, so it follows the app theme.
 */
private fun chromeToneFor(providerKey: String, appIsDark: Boolean): ChromeTone =
    when (TILE_PROVIDERS.firstOrNull { it.key == providerKey }?.chrome ?: MapChrome.OnLight) {
        MapChrome.OnLight -> LIGHT_TONE
        MapChrome.OnDark -> DARK_TONE
        MapChrome.OnMixed ->
            if (appIsDark) DARK_TONE.copy(panel = Color(0xFF1E1E1E))
            else LIGHT_TONE.copy(panel = Color(0xFFFFFFFF))
    }

/** The panel's scheme, so its components choose ink for the panel, not the app. */
@Composable
private fun PanelTheme(content: @Composable () -> Unit) {
    if (LocalChromeTone.current.dark) {
        cz.hillview.core.theme.DarkPanelTheme(content)
    } else {
        cz.hillview.core.theme.LightPanelTheme(content)
    }
}

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
    /**
     * The geo debug readout's lines (empty = off). Rendered here rather
     * than built here: what to say about the chain is a decision for
     * GeoDebugText, which is pure and tested.
     */
    debugLines: List<String> = emptyList(),
    /**
     * Dismisses the readout in place — writes the same persisted setting
     * the Settings switch reads, so the two stay one fact. The original's
     * DebugOverlay is a mess, but it has a close button in its header
     * (closeDebug, DebugOverlay.svelte:50); this readout shipped without
     * one, which meant a trip through Settings to make it go away.
     */
    onCloseDebug: () -> Unit = {},
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
    /** Whether the map position has been CLAIMED — see [fixRole]. */
    mapPositionElected: Boolean = false,
    /** Which of this panel's edges are the screen's — see [PanelEdges]. */
    edges: PanelEdges = PanelEdges.AllScreen,
) {
    val chromeTone = chromeToneFor(
        settings.tileProviderKey,
        androidx.compose.foundation.isSystemInDarkTheme(),
    )
    androidx.compose.runtime.CompositionLocalProvider(LocalChromeTone provides chromeTone) {
    // System insets for the edges that actually touch the screen, and none
    // for the one the split divider is on. Window insets are not clipped to
    // where a composable sits, so the blanket version spent a gesture strip's
    // worth of map against the divider — dead space at an edge no system
    // gesture can reach.
    // A gutter is bought with map, so only the controls that are expensive
    // to hit by accident take one, and only where the edge is the screen's.
    val gutterTop = if (edges.top) CRITICAL_EDGE_GUTTER else 0.dp
    val gutterEnd = if (edges.end) CRITICAL_EDGE_GUTTER else 0.dp
    // safeDrawing, NOT safeContent. The difference is the system's GESTURE
    // strips, and those are about swipes: a tap at the very edge of the
    // screen works fine, it is a horizontal drag from there that the back
    // gesture takes. Insetting every control by a gesture strip cost 30 dp of
    // map down each side on this phone — enough to read a town name in
    // (user-caught, 2026-09-11, pointing at "Velvary" beside the zoom
    // buttons). The controls that DO want that clearance ask for it by name
    // below.
    Box(
        Modifier
            .fillMaxSize()
            .windowInsetsPadding(WindowInsets.safeDrawing.only(screenInsetSides(edges))),
    ) {
        // Top-left: zoom, where Leaflet keeps it (44dp touch targets).
        // Flush, both edges, both orientations: a stray tap here zooms a
        // level and the next one puts it back, so there is nothing worth
        // spending map on (user, 2026-09-11: "since zoom isnt critical, it
        // can, in portrait, sit flush to the left edge of screen"). The
        // system insets still hold it off the status bar and the gesture
        // strips; what is gone is the decorative margin on top of them.
        Column(Modifier.align(Alignment.TopStart)) {
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
            val offNorth = offNorthDeg(mapOrientation)
            if (kotlin.math.abs(offNorth) >= 1.0) {
                ResetNorthButton(
                    offNorthDeg = offNorth,
                    mapOrientation = mapOrientation,
                    onClick = onResetNorth,
                )
            }
        }

        // Top-right pair: location, then compass.
        Row(
            // The one gutter the user called critical: a mis-tap on the
            // screen's edge here turns tracking off. Against the divider
            // there is nothing to mis-tap into, so in portrait it sits at the
            // top of the panel.
            modifier = Modifier
                .align(Alignment.TopEnd)
                // The one control that keeps clear of the gesture strips as
                // well, because it is the one where the slip is expensive:
                // a back-swipe that starts on this button and is read as a
                // tap turns tracking off. The system's own number rather
                // than a guess at it.
                .windowInsetsPadding(WindowInsets.safeGestures.only(screenInsetSides(edges)))
                .padding(top = gutterTop, end = gutterEnd),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            LocationButton(
                role = fixRole(locationTracking, mapPositionElected),
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
        // hunter mode. The original bounds its panel (100vh - 120px) and
        // lets flexbox shrink the buttons (min-height: 0) with ellipsized
        // labels; here the pane is a SPLIT-SHARE of the screen — a fixed cap
        // drew the tabs over the compass button — so the band reserves the
        // corners it must not cover (the location/compass row above, the
        // hunter grid below) and divides what is left among the tabs, which
        // shrink the same way the original's do.
        BoxWithConstraints(
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .fillMaxHeight()
                // Clearances, not edge gutters: the band must not reach
                // into the tracking row above or the hunter row below, and
                // both of those move with the gutters now.
                .padding(top = gutterTop + TRACKING_ROW_RESERVE, bottom = HUNTER_ROW_RESERVE),
            contentAlignment = Alignment.CenterEnd,
        ) {
            val perTab = ((maxHeight - 4.dp - 2.dp * (sources.size - 1)) /
                sources.size.coerceAtLeast(1)).coerceAtLeast(24.dp)
            HunterPanel(visible = hunterMode) {
                Column(
                    modifier = Modifier.padding(2.dp),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    sources.forEach { source ->
                        SourceButton(
                            source,
                            onClick = { onToggleSource(source.id) },
                            modifier = Modifier.heightIn(max = perTab),
                        )
                    }
                }
            }
        }

        // Bottom-right hunter grid: the toggle owns the corner, the button
        // panel grows left.
        Column(
            // No gutter at all, by request: the hunter toggle and the two
            // toolbars that unfold from it sit where the system insets put
            // them and no further. They are the app's own corner, and a
            // mis-tap on one costs a toggle.
            modifier = Modifier.align(Alignment.BottomEnd),
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
                    .padding(top = gutterTop + TRACKING_ROW_RESERVE + 8.dp)
                    .background(LocalChromeTone.current.panel, RoundedCornerShape(20.dp))
                    .testTag("map-position-prompt"),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // A Box background paints pixels without touching the theme,
                // so this subtree is handed the panel's scheme by hand.
                PanelTheme {
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
        }

        Column(
            modifier = Modifier.align(Alignment.BottomStart),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            // The geo debug readout, stacked on the same anchor so it shares
            // the pill's one bottom-left corner instead of claiming another.
            if (debugLines.isNotEmpty()) {
                Row(
                    verticalAlignment = Alignment.Top,
                    modifier = Modifier
                        .background(LocalChromeTone.current.panel, RoundedCornerShape(4.dp))
                        .padding(horizontal = 6.dp, vertical = 3.dp)
                        .testTag("geo-debug"),
                ) {
                    // The one part of the original's DebugOverlay worth
                    // porting: it can be closed where it stands. At the
                    // START of the row, deliberately: the panel re-measures
                    // on every half-second tick (the age strings change
                    // width), so a close button at the row's END drifts with
                    // the longest line — a moving target that a finger (and
                    // a scripted tap against dumped bounds) keeps missing.
                    // The panel's LEFT edge is anchored; this corner stands
                    // still.
                    Text(
                        text = "✕",
                        style = MaterialTheme.typography.labelSmall,
                        color = LocalChromeTone.current.ink,
                        modifier = Modifier
                            .clickable(onClick = onCloseDebug)
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                            .testTag("geo-debug-close"),
                    )
                    Column(Modifier.padding(start = 4.dp)) {
                        debugLines.forEach { line ->
                            Text(
                                text = line,
                                style = MaterialTheme.typography.labelSmall,
                                fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                                color = LocalChromeTone.current.ink,
                            )
                        }
                    }
                }
            }

            // On BARE TILES, unlike everything else here, so it cannot assume a
            // background: the dark tile providers (CartoDB Dark) turned this into
            // black-on-black. Same white pill as the controls, which is legible
            // over any tiles the provider serves — including the bright and dark
            // patches within one map.
            Text(
                text = "$markerCount photos",
                style = MaterialTheme.typography.bodySmall,
                color = LocalChromeTone.current.ink,
                modifier = Modifier
                    .background(LocalChromeTone.current.panel, RoundedCornerShape(4.dp))
                    .padding(horizontal = 6.dp, vertical = 2.dp)
                    .testTag("map-status"),
            )
        }
    }
    }
}

/**
 * The "you are not facing north" alarm.
 *
 * It used to be an ordinary chrome button with a red glyph in it, and it kept
 * being missed (user: "map rotation keeps fooling me") — which is the failure
 * that matters, because a rotated map does not look wrong. It looks like a
 * different place, and every judgement made from it is quietly off by the
 * rotation. So this is now the loudest thing on the map: filled red, larger
 * than its neighbours, breathing so the eye catches it in peripheral vision,
 * and carrying the angle in figures because "off north" is not the same
 * question as "off north by how much".
 *
 * It costs nothing when the map is north-up, which is almost always: the
 * caller does not compose it at all below one degree, so the animation only
 * runs while there is something to shout about.
 */
@Composable
private fun ResetNorthButton(
    offNorthDeg: Double,
    mapOrientation: Double,
    onClick: () -> Unit,
) {
    val pulse = rememberInfiniteTransition(label = "off-north")
    val beat by pulse.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 850, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "off-north-beat",
    )
    Surface(
        // Two channels, because either alone can be missed: a phone in
        // sunlight loses the colour shift, a glance too short to see a full
        // cycle still catches the size change.
        color = lerp(Color(0xFFC5000B), Color(0xFFFF5252), beat),
        contentColor = Color.White,
        shape = RoundedCornerShape(4.dp),
        shadowElevation = 6.dp,
        modifier = Modifier
            .padding(top = 8.dp)
            .scale(1f + 0.07f * beat),
    ) {
        TextButton(
            onClick = onClick,
            contentPadding = PaddingValues(0.dp),
            modifier = Modifier.size(52.dp).testTag("reset-north-btn"),
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    "↑N",
                    color = Color.White,
                    style = MaterialTheme.typography.titleMedium,
                    // Points at TRUE north, so the badge doubles as the
                    // compass rose the rotated map no longer has.
                    modifier = Modifier.rotate(-mapOrientation.toFloat()),
                )
                Text(
                    "${kotlin.math.abs(offNorthDeg).roundToInt()}°",
                    color = Color.White,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
        }
    }
}

/**
 * How far a CRITICAL control keeps from an edge that is the screen's, on top
 * of the system insets.
 *
 * Critical is the whole test, and it is about the cost of the mis-tap rather
 * than about the control's importance. Tracking is the one that qualifies: a
 * stray touch there turns the compass or the receiver off, and nothing on
 * screen necessarily says so afterwards. Zoom, the north badge, the hunter
 * corner and the debug readout are all undone by tapping again, so they sit
 * flush and give the middle of the map back.
 *
 * Zero at the divider in any case — there is nothing to mis-swipe into.
 */
private val CRITICAL_EDGE_GUTTER = 8.dp

/** The tracking row's own height plus a gap — what must stay clear below it. */
private val TRACKING_ROW_RESERVE = 52.dp

/** The hunter toggle row's height plus a gap, likewise. */
private val HUNTER_ROW_RESERVE = 56.dp

/**
 * The inset sides worth applying: the screen's edges only.
 *
 * Used for both inset families here — the panel's own edges do not change
 * when the question does.
 *
 * Window insets describe the WINDOW, and Compose does not clip them to where
 * a composable sits — so asking for all of them inside a half-screen panel
 * pads the divider side against a system gesture that cannot happen there.
 */
private fun screenInsetSides(edges: PanelEdges): WindowInsetsSides {
    val sides = buildList {
        if (edges.top) add(WindowInsetsSides.Top)
        if (edges.bottom) add(WindowInsetsSides.Bottom)
        if (edges.start) add(WindowInsetsSides.Start)
        if (edges.end) add(WindowInsetsSides.End)
    }
    return sides.reduce { a, b -> a + b }
}

@Composable
private fun ControlSurface(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val tone = LocalChromeTone.current
    Surface(
        modifier = modifier,
        color = tone.panel,
        contentColor = tone.ink,
        border = tone.border?.let { androidx.compose.foundation.BorderStroke(1.dp, it) },
        shape = RoundedCornerShape(4.dp),
        shadowElevation = 2.dp,
        content = { PanelTheme { content() } },
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
        color = LocalChromeTone.current.panel,
        contentColor = LocalChromeTone.current.ink,
        border = LocalChromeTone.current.border?.let {
            androidx.compose.foundation.BorderStroke(1.dp, it)
        },
        shape = RoundedCornerShape(8.dp),
        shadowElevation = 2.dp,
    ) {
        PanelTheme { content() }
    }
}

/**
 * The vertical-tab text swap (the original's `writing-mode: vertical-rl`):
 * report height×width, then rotate the drawing into the swapped bounds.
 *
 * The constraints are swapped BEFORE measuring, so the tab's height budget
 * becomes the text's width budget — which is what lets maxLines=1 +
 * Ellipsis truncate a long name when a tab runs short (the original's
 * `text-overflow: ellipsis; max-height: 100%`) instead of overflowing it.
 */
private fun Modifier.verticalLabel(): Modifier = this
    .layout { measurable, constraints ->
        val placeable = measurable.measure(
            Constraints(
                minWidth = constraints.minHeight,
                maxWidth = constraints.maxHeight,
                minHeight = constraints.minWidth,
                maxHeight = constraints.maxWidth,
            ),
        )
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
        color = LocalChromeTone.current.panel,
        contentColor = LocalChromeTone.current.ink,
        shape = RoundedCornerShape(topStart = 4.dp, bottomEnd = 8.dp),
        shadowElevation = if (active) 0.dp else 2.dp,
        modifier = Modifier.testTag("hunter-mode-toggle"),
    ) {
        PanelTheme {
        TextButton(onClick = onClick) {
            // The bow icon is inlined lucide art in the original; a caret
            // pair plus a bow glyph reads the same at this size.
            Text(
                text = if (active) "⌄ 🏹" else "⌃ 🏹",
                color = if (active) ACTIVE_BLUE else LocalChromeTone.current.ink.copy(alpha = 0.6f),
            )
        }
        }
    }
}

@Composable
private fun SourceButton(
    source: MapSourceUi,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        color = if (source.enabled) ACTIVE_BLUE else LocalChromeTone.current.panel,
        border = androidx.compose.foundation.BorderStroke(
            1.dp,
            if (source.enabled) ACTIVE_BLUE_BORDER
            else LocalChromeTone.current.border ?: Color(0xFFCCCCCC),
        ),
        shape = RoundedCornerShape(4.dp),
        onClick = onClick,
        modifier = modifier.testTag("source-toggle-${source.id}"),
    ) {
        Box(
            contentAlignment = Alignment.Center,
            // 0.3rem 0.2rem in the original — the roomier padding this had
            // was eating into the label's budget once tabs began to shrink.
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 5.dp),
        ) {
            Text(
                text = source.name,
                color = if (source.enabled) Color.White else LocalChromeTone.current.ink,
                style = MaterialTheme.typography.labelLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
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
            color = if (activeFilterCount > 0) Color.White else LocalChromeTone.current.ink,
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
            .background(LocalChromeTone.current.ink.copy(alpha = 0.15f)),
    )
}

/**
 * Tri-state: white when off, blue when following, half-blue in background —
 * "GPS still on (and still flashing on each fix) but the map no longer
 * follows". Green flash on each fix, leaf badge under power saving.
 */
@Composable
private fun LocationButton(
    role: FixRole,
    flash: Boolean,
    loading: Boolean,
    powerSaving: Boolean,
    onClick: () -> Unit,
) {
    // Half-lit means the fix has been DEMOTED to alt_location, not merely
    // that the map stopped following — see fixRole.
    //
    // The per-fix flash is on the FILL now, not on the glyph. It used to
    // colour the text, which an emoji ignores — Android draws those from the
    // colour font whatever the paint says — so the flash would have gone
    // silently missing the moment the glyph became 📍. A whole button
    // blinking green is also simply easier to catch out of the corner of an
    // eye than a small mark inside one.
    val fill = when {
        flash -> Color(0xFF34D399)
        role == FixRole.Primary -> ACTIVE_BLUE
        role == FixRole.Alternate -> ACTIVE_BLUE.copy(alpha = 0.5f)
        else -> LocalChromeTone.current.panel
    }
    Box {
        Surface(
            color = fill,
            shape = RoundedCornerShape(4.dp),
            shadowElevation = 2.dp,
            border = androidx.compose.foundation.BorderStroke(
                2.dp,
                LocalChromeTone.current.border ?: Color(0xFFDDDDDD),
            ),
            modifier = Modifier
                // No fade when off. It was 60% opacity, which made the one
                // control that says whether the app knows where you are the
                // faintest thing on the map, and put it out of step with
                // every other control up here (user, 2026-09-11). Off is
                // already said by the fill: chrome instead of blue.
                // Which of the three states this is in must be readable from
                // outside, not just inferable from a colour. The original
                // carries it as `active`/`background` classes, which is what
                // its suite asserts on; this is the same fact by another
                // name, and it is what a screen reader announces too.
                .semantics {
                    stateDescription = when (role) {
                        FixRole.Off -> "off"
                        FixRole.Primary -> "active"
                        FixRole.Alternate -> "background"
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
                    // The app's own word for a fix: the capture pill has
                    // shown 📍 for one since it was written. It replaces ◎,
                    // which was this port tracing the original's LocateFixed
                    // LINE ICON into a geometric character and so standing
                    // alone beside 🧭 and 📷 (user, 2026-09-11). No colour:
                    // an emoji ignores it, and the fill says the state.
                    Text(
                        text = "📍",
                        // Sized like the zoom glyphs next to it, not like a
                        // caption. A 60x44 dp button with a small glyph in
                        // the middle of it reads as a mis-render rather than
                        // as an icon (user, 2026-09-11).
                        style = MaterialTheme.typography.headlineSmall,
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
            color = if (wanted) ACTIVE_BLUE else LocalChromeTone.current.panel,
            shape = RoundedCornerShape(4.dp),
            shadowElevation = 2.dp,
            border = androidx.compose.foundation.BorderStroke(
                2.dp,
                if (phase == TrackingPhase.Error) Color(0xFFF44336)
                else LocalChromeTone.current.border ?: Color(0xFFDDDDDD),
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
                    color = if (wanted) Color.White else LocalChromeTone.current.ink,
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

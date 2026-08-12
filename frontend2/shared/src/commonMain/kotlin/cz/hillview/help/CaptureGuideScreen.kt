package cz.hillview.help

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeContentPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/**
 * The capture-controls guide: the gestures follow native camera-app
 * conventions, but conventions only help people who already know them —
 * this page is the manual (user-requested).
 */
@Composable
fun CaptureGuideScreen(onBack: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .safeContentPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
            .testTag("capture-guide"),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack) { Text("< Back") }
            Text(
                "Capture guide",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(start = 8.dp),
            )
        }

        Section("The viewfinder")
        Entry("Tap", "Focus and expose at that point (a ring shows the attempt). Auto-cancels back to continuous after a few seconds.")
        Entry("Long-press", "Lock focus AND exposure at that point — they stay locked (\"AE/AF locked\" chip) until you tap again.")
        Entry("Pinch", "Zoom. The current ratio shows in a chip while you pinch.")

        Section("The shutter (blue circle)")
        Entry("Tap", "One photo.")
        Entry("Hold, slide, release", "Hold ~half a second and the interval slider unfolds beside your thumb. Slide onto it to pick a repeat interval (bottom = off), release to START the repeating run — the button turns green with a Stop label and counts the run on its badge. Release back on the button to cancel. Tap to stop a running run.")

        Section("The Leaf 🍃 (top right)")
        Entry("Tap", "Toggle power saving on/off.")
        Entry("Hold, slide, release", "The same gesture as the shutter: an fps ladder unfolds. Bottom = the preview refreshes only when you take a photo; then 0.1–1 fps (the preview freezes between beats); then 7–30 fps; top = no throttling. Releasing on the ladder sets the level and turns power saving on.")

        Section("The 📷 menu (bottom left)")
        Entry("Resolutions", "Pin a photo size, or Auto for the camera's best.")
        Entry("Focus Auto / ∞", "∞ pins the lens at infinity — for landscapes and vistas. Any tap on the viewfinder returns to Auto.")

        Section("The ⚡ menu (bottom right)")
        Entry("Rule", "How hard the target time is defended. Pin = exactly that time (it WILL blow out in bright sun — the ISO floor runs out and a pinned shutter has nowhere left to give). Floor = that time or faster, which is the one to use outdoors. Sports = a floor that hands the shutter back, down to 1/125, rather than push ISO past 1600. Auto returns the camera to its own exposure.")
        Entry("Target", "The shutter time the rule aims at (1/125…1/2000) — for crisp shots from a moving vehicle. ISO follows automatically.")
        Entry("Bias", "Deliberate under/overexposure, in stops. This is the knob for shooting into the sun: metering exposes for the average, so a bright sky behind your subject blows out no matter which rule is set — pull -1 or -2.")
        Entry("The grey line", "What the rule last actually resolved to: time, ISO, and whether it held the target, went faster, slowed down, or ran out of room.")
        Entry("Interval runs", "Between repeat shots the camera is handed back to auto-exposure for a moment to take a fresh reading (the preview visibly jumps) — without it, a whole drive would be exposed for whatever the light was when you picked the rule.")

        Section("Location & the info panel")
        Entry("The panel (top left)", "Compass heading, position, altitude, accuracy — plus camera state and upload tallies. Tap its LEFT EDGE (the grip mark) to cycle the backdrop; taps on the rest pass through to focus.")
        Entry("No GPS?", "The shutter stays off without a fix. \"Capture at the map position instead\" stamps photos from wherever you put the map — deliberately, and the shutter sound changes so you notice.")
        Entry("Counts", "The badge on the shutter counts the current run; the bottom-right corner counts this session's photos and shows saves in flight.")
    }
}

@Composable
private fun Section(title: String) {
    Text(
        title,
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.padding(top = 6.dp),
    )
}

@Composable
private fun Entry(gesture: String, meaning: String) {
    Column {
        Text(gesture, style = MaterialTheme.typography.labelLarge)
        Text(
            meaning,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

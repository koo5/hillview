package cz.hillview.map

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.longClick
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.settings.MapSettings
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The map overlay's behaviour, on desktop — no emulator involved, because
 * the whole control layer is commonMain. These replace the manual loop of
 * installing, tapping by testTag and reading a screenshot.
 *
 * The semantics under test come from docs/tauri-map-ui-contract.md.
 */
@OptIn(ExperimentalTestApi::class)
class MapOverlayUiTest {

    /** Everything the overlay needs, with the interesting bits overridable. */
    private class Harness(
        val settings: MapSettings = MapSettings(),
        val hunterMode: Boolean = false,
        val sources: List<MapSourceUi> = listOf(MapSourceUi("device", "Device", enabled = true)),
        val activeFilterCount: Int = 0,
        val overrideFilters: Boolean = false,
        val locationTracking: LocationTracking = LocationTracking.Off,
        val powerSavingActive: Boolean = false,
        val trackingWanted: Boolean = false,
        val trackingPhase: TrackingPhase = TrackingPhase.Inactive,
        val compassUnavailable: Boolean = false,
    ) {
        var hunterToggled = 0
        var toggledSource: String? = null
        var filtersOpened = 0
        var overrideToggled = 0
        var providersOpened = 0
        var locationToggled = 0
        var trackingToggled = 0
        var pickedMode: BearingMode? = null
        var zoomDelta: Double? = null
    }

    private fun androidx.compose.ui.test.ComposeUiTest.overlay(h: Harness) {
        setContent {
            MapOverlayUi(
                settings = h.settings,
                hunterMode = h.hunterMode,
                sources = h.sources,
                activeFilterCount = h.activeFilterCount,
                overrideFilters = h.overrideFilters,
                locationTracking = h.locationTracking,
                locationFlash = false,
                locationLoading = false,
                powerSavingActive = h.powerSavingActive,
                trackingWanted = h.trackingWanted,
                trackingPhase = h.trackingPhase,
                compassUnavailable = h.compassUnavailable,
                markerCount = 3,
                onToggleHunterMode = { h.hunterToggled++ },
                onToggleSource = { h.toggledSource = it },
                onOpenFilters = { h.filtersOpened++ },
                onToggleOverrideFilters = { h.overrideToggled++ },
                onOpenTileProviders = { h.providersOpened++ },
                onToggleLocation = { h.locationToggled++ },
                onToggleTracking = { h.trackingToggled++ },
                onSelectBearingMode = { h.pickedMode = it },
                onZoom = { h.zoomDelta = it },
            )
        }
    }

    @Test
    fun advancedControlsAreHiddenUntilHunterModeIsOn() = runComposeUiTest {
        val h = Harness(hunterMode = false)
        overlay(h)

        // The toggle owns the corner and is always there…
        onNodeWithTag("hunter-mode-toggle").assertIsDisplayed()
        // …but the panels it reveals are not composed at all.
        onNodeWithTag("source-toggle-device").assertDoesNotExist()
        onNodeWithTag("filters-button").assertDoesNotExist()
        onNodeWithTag("tile-provider-button").assertDoesNotExist()
    }

    @Test
    fun hunterModeRevealsTheSourceAndButtonPanels() = runComposeUiTest {
        overlay(Harness(hunterMode = true))

        onNodeWithTag("source-toggle-device").assertIsDisplayed()
        onNodeWithTag("filters-button").assertIsDisplayed()
        onNodeWithTag("tile-provider-button").assertIsDisplayed()
    }

    @Test
    fun theHunterToggleReportsBack() = runComposeUiTest {
        val h = Harness()
        overlay(h)
        onNodeWithTag("hunter-mode-toggle").performClick()
        assertEquals(1, h.hunterToggled)
    }

    @Test
    fun sourceButtonsToggleTheirOwnSource() = runComposeUiTest {
        val h = Harness(hunterMode = true)
        overlay(h)
        onNodeWithTag("source-toggle-device").performClick()
        assertEquals("device", h.toggledSource)
    }

    @Test
    fun shortPressOnFiltersOpensTheModal() = runComposeUiTest {
        val h = Harness(hunterMode = true)
        overlay(h)

        onNodeWithTag("filters-button").performClick()

        assertEquals(1, h.filtersOpened)
        assertEquals(0, h.overrideToggled, "a tap must not touch the override")
    }

    @Test
    fun longPressOnFiltersTogglesTheOverrideInstead() = runComposeUiTest {
        // The hidden gesture from the original: long press overrides the
        // filters rather than opening them.
        val h = Harness(hunterMode = true)
        overlay(h)

        onNodeWithTag("filters-button").performTouchInput { longClick() }

        assertEquals(1, h.overrideToggled)
        assertEquals(0, h.filtersOpened, "a long press must not also open the modal")
    }

    @Test
    fun theTileProviderButtonOpensTheChooser() = runComposeUiTest {
        val h = Harness(hunterMode = true)
        overlay(h)
        onNodeWithTag("tile-provider-button").performClick()
        assertEquals(1, h.providersOpened)
    }

    @Test
    fun tappingTheCompassTogglesTracking() = runComposeUiTest {
        val h = Harness()
        overlay(h)
        onNodeWithTag("compass-button").performClick()
        assertEquals(1, h.trackingToggled)
    }

    @Test
    fun anUnavailableCompassIgnoresTaps() = runComposeUiTest {
        // Walking mode without a usable sensor: the button stays put rather
        // than pretending to start.
        val h = Harness(compassUnavailable = true, settings = MapSettings(bearingMode = BearingMode.Walking))
        overlay(h)

        onNodeWithTag("compass-button").performClick()

        assertEquals(0, h.trackingToggled)
    }

    @Test
    fun longPressOnTheCompassOffersWalkingAndCar() = runComposeUiTest {
        val h = Harness()
        overlay(h)

        onNodeWithTag("compass-button").performTouchInput { longClick() }

        onNodeWithTag("walking-mode-option").assertIsDisplayed()
        onNodeWithTag("car-mode-option").assertIsDisplayed()
        assertEquals(0, h.trackingToggled, "opening the menu must not toggle tracking")
    }

    @Test
    fun pickingCarModeReportsTheChoice() = runComposeUiTest {
        val h = Harness()
        overlay(h)

        onNodeWithTag("compass-button").performTouchInput { longClick() }
        onNodeWithTag("car-mode-option").performClick()

        assertEquals(BearingMode.Car, h.pickedMode)
    }

    @Test
    fun theLocationButtonReportsBack() = runComposeUiTest {
        val h = Harness()
        overlay(h)
        onNodeWithTag("track-location-btn").performClick()
        assertEquals(1, h.locationToggled)
    }

    @Test
    fun theLeafBadgeOnlyAppearsUnderPowerSaving() = runComposeUiTest {
        overlay(Harness(powerSavingActive = false))
        onNodeWithTag("location-power-saving-badge").assertDoesNotExist()
    }

    @Test
    fun theLeafBadgeShowsWhenPowerSavingIsActive() = runComposeUiTest {
        overlay(Harness(powerSavingActive = true))
        onNodeWithTag("location-power-saving-badge").assertIsDisplayed()
    }

    @Test
    fun zoomButtonsStepInBothDirections() = runComposeUiTest {
        val h = Harness()
        overlay(h)

        onNodeWithTag("zoom-in-btn").performClick()
        assertEquals(1.0, h.zoomDelta)

        onNodeWithTag("zoom-out-btn").performClick()
        assertEquals(-1.0, h.zoomDelta)
    }
}

/** The two dialogs the overlay opens. */
@OptIn(ExperimentalTestApi::class)
class MapDialogsTest {

    @Test
    fun theProviderChooserListsOurPaletteAndReportsAPick() = runComposeUiTest {
        var picked: String? = null
        var dismissed = false
        setContent {
            TileProviderDialog(
                currentKey = DEFAULT_TILE_PROVIDER,
                onPick = { picked = it },
                onDismiss = { dismissed = true },
            )
        }

        onNodeWithTag("tile-provider-option-OpenStreetMap.Mapnik").assertIsDisplayed()
        // Dev-only entries stay out of the picker.
        onNodeWithTag("tile-provider-option-oi.jj.internal").assertDoesNotExist()

        onNodeWithTag("tile-provider-option-OpenTopoMap").performClick()

        assertEquals("OpenTopoMap", picked)
        assertTrue(dismissed, "picking a provider closes the chooser")
    }

    @Test
    fun theFiltersDialogShowsTheCurrentPhotoLimit() = runComposeUiTest {
        setContent {
            FiltersDialog(
                settings = MapSettings(maxPhotos = 250),
                activeFilterCount = 0,
                onDismiss = {},
                onSettingsChange = {},
            )
        }
        onNodeWithTag("filters-max-photos-value").assertIsDisplayed()
        onNodeWithTag("filters-max-photos").assertIsDisplayed()
    }

    @Test
    fun theTrailingFilterControlsAreDisabledUntilAFilterIsActive() = runComposeUiTest {
        // "The modal also disables 'clear filters' and 'show unanalyzed'
        // while no filter is active" — there is nothing to clear, and
        // unanalyzed-ness only means something relative to a filter.
        setContent {
            FiltersDialog(
                settings = MapSettings(),
                activeFilterCount = 0,
                onDismiss = {},
                onSettingsChange = {},
            )
        }
        onNodeWithTag("filters-clear").assertIsNotEnabled()
        onNodeWithTag("filters-show-unanalyzed").assertIsNotEnabled()
    }

    @Test
    fun anActiveFilterEnablesClearAndShowUnanalyzed() = runComposeUiTest {
        var cleared = false
        setContent {
            FiltersDialog(
                settings = MapSettings(),
                activeFilterCount = 2,
                onDismiss = {},
                onSettingsChange = {},
                onClearFilters = { cleared = true },
            )
        }
        onNodeWithTag("filters-clear").assertIsEnabled().performClick()
        onNodeWithTag("filters-show-unanalyzed").assertIsEnabled()
        assertTrue(cleared, "the clear button must call back once enabled")
    }

    @Test
    fun showUnanalyzedDefaultsOnAndTogglesThroughSettings() = runComposeUiTest {
        var latest: MapSettings? = null
        setContent {
            FiltersDialog(
                settings = MapSettings(),
                activeFilterCount = 1,
                onDismiss = {},
                onSettingsChange = { transform -> latest = transform(MapSettings()) },
            )
        }
        onNodeWithTag("filters-show-unanalyzed").assertIsOn().performClick()
        assertEquals(false, latest?.showUnanalyzed)
    }
}

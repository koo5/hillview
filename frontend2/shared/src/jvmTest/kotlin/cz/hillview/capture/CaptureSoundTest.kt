package cz.hillview.capture

import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.v2.runComposeUiTest
import cz.hillview.settings.ShutterSound
import cz.hillview.settings.SoundChannel
import cz.hillview.settings.UploadSettings
import cz.hillview.settings.UploadSettingsRepository
import cz.hillview.settings.defaultUploadSettings
import cz.hillview.settings.ui.CaptureSoundSection
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Capture sounds (user, 2026-11-07: the click followed a different volume
 * control on every phone): which cue a shot gets, the synthesized PCM, and
 * the Settings section that picks sound, stream and loudness.
 */
@OptIn(ExperimentalTestApi::class)
class CaptureSoundTest {

    @Test
    fun theWarningOutlivesASilencedShutter() {
        assertEquals(CaptureCue.Click, captureCue(CaptureTone.Normal, ShutterSound.Click, true))
        assertEquals(CaptureCue.Beep, captureCue(CaptureTone.Normal, ShutterSound.Beep, true))
        assertNull(captureCue(CaptureTone.Normal, ShutterSound.Off, true))
        assertEquals(CaptureCue.Warning, captureCue(CaptureTone.Degraded, ShutterSound.Off, true))
        // Warning off: a degraded shot sounds like any other.
        assertEquals(CaptureCue.Click, captureCue(CaptureTone.Degraded, ShutterSound.Click, false))
        assertNull(captureCue(CaptureTone.Degraded, ShutterSound.Off, false))
    }

    @Test
    fun theSynthesizedCuesAreShortBoundedAndRepeatable() {
        for (cue in CaptureCue.entries) {
            val pcm = CaptureCueSynth.pcm(cue)
            val ms = pcm.size * 1000 / CaptureCueSynth.SAMPLE_RATE
            assertTrue(ms in 50..400, "$cue lasts $ms ms")
            val peak = pcm.maxOf { abs(it.toInt()) }
            assertTrue(peak > Short.MAX_VALUE / 2, "$cue is audible (peak $peak)")
            assertTrue(peak < Short.MAX_VALUE, "$cue does not clip")
            assertContentEquals(pcm, CaptureCueSynth.pcm(cue), "$cue is the same every time")
        }
        // The tones fade in and out rather than starting on a step.
        for (cue in listOf(CaptureCue.Beep, CaptureCue.Warning)) {
            val pcm = CaptureCueSynth.pcm(cue)
            assertTrue(abs(pcm.first().toInt()) < 100 && abs(pcm.last().toInt()) < 1_000, "$cue edges")
        }
        assertTrue(CaptureCueSynth.pcm(CaptureCue.Warning).size > CaptureCueSynth.pcm(CaptureCue.Beep).size)
    }

    private class FakeSettings(initial: UploadSettings) : UploadSettingsRepository {
        private val _settings = MutableStateFlow(initial)
        override val settings: StateFlow<UploadSettings> = _settings
        override fun update(transform: (UploadSettings) -> UploadSettings) {
            _settings.value = transform(_settings.value)
        }
    }

    private class RecordingPreview(override val shutterSoundRequiredByLaw: Boolean = false) : CaptureSoundPreview {
        val played = mutableListOf<Triple<CaptureCue, SoundChannel, Float>>()
        override fun play(cue: CaptureCue, channel: SoundChannel, volume: Float) {
            played += Triple(cue, channel, volume)
        }
    }

    @Test
    fun theSectionWritesSoundAndStreamAndTestsWhatIsChosen() = runComposeUiTest {
        val repo = FakeSettings(defaultUploadSettings("https://api/api"))
        val preview = RecordingPreview()
        setContent { CaptureSoundSection(repository = repo, preview = preview) }

        onNodeWithTag("settings-shutter-sound-click").assertIsSelected()
        onNodeWithTag("settings-capture-sound-channel-media").assertIsSelected()
        onNodeWithTag("settings-shutter-sound-required").assertDoesNotExist()

        onNodeWithTag("settings-shutter-sound-beep").performClick()
        onNodeWithTag("settings-capture-sound-channel-alarm").performClick()
        assertEquals(ShutterSound.Beep, repo.settings.value.shutterSound)
        assertEquals(SoundChannel.Alarm, repo.settings.value.captureSoundChannel)

        onNodeWithTag("settings-capture-sound-test-shutter").performClick()
        onNodeWithTag("settings-capture-sound-test-warning").performClick()
        assertEquals(
            listOf(
                Triple(CaptureCue.Beep, SoundChannel.Alarm, 1f),
                Triple(CaptureCue.Warning, SoundChannel.Alarm, 1f),
            ),
            preview.played,
        )
    }

    @Test
    fun withNothingToPlayTheStreamAndLoudnessGo() = runComposeUiTest {
        val repo = FakeSettings(defaultUploadSettings("https://api/api"))
        setContent { CaptureSoundSection(repository = repo, preview = RecordingPreview()) }
        onNodeWithTag("settings-shutter-sound-off").performClick()
        // The warning alone still needs a stream.
        onNodeWithTag("settings-capture-sound-volume").assertExists()
        onNodeWithTag("settings-capture-sound-test-shutter").assertDoesNotExist()
        onNodeWithTag("settings-warn-degraded-position").performClick()
        onNodeWithTag("settings-capture-sound-volume").assertDoesNotExist()
        onNodeWithTag("settings-capture-sound-channel-media").assertDoesNotExist()
    }

    @Test
    fun aLegallyRequiredShutterIsSaidSo() = runComposeUiTest {
        val repo = FakeSettings(defaultUploadSettings("https://api/api"))
        setContent { CaptureSoundSection(repository = repo, preview = RecordingPreview(true)) }
        onNodeWithTag("settings-shutter-sound-required").assertExists()
    }
}

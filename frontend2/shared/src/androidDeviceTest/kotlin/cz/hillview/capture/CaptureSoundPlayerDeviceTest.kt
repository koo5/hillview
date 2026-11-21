package cz.hillview.capture

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import cz.hillview.settings.SoundChannel
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertTrue

/**
 * The capture cues really play on the stream the user chose — asked of the
 * platform's own list of active players, not inferred from our code. The
 * bug this replaced was exactly a sound on a stream nobody picked
 * (user-reported, 2026-11-07).
 */
@RunWith(AndroidJUnit4::class)
class CaptureSoundPlayerDeviceTest {

    private val audio = InstrumentationRegistry.getInstrumentation().targetContext
        .getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private fun playingUsages(): Set<Int> =
        audio.activePlaybackConfigurations.map { it.audioAttributes.usage }.toSet()

    @Test
    fun eachChannelPlaysOnItsOwnUsage() {
        val expected = mapOf(
            SoundChannel.Media to AudioAttributes.USAGE_MEDIA,
            SoundChannel.Notification to AudioAttributes.USAGE_NOTIFICATION,
            SoundChannel.Alarm to AudioAttributes.USAGE_ALARM,
        )
        for ((channel, usage) in expected) {
            // The warning is the longest cue (~330 ms): time to catch it playing.
            CaptureSoundPlayer.shared.play(CaptureCue.Warning, channel, 0.05f)
            val seen = mutableSetOf<Int>()
            val deadline = System.currentTimeMillis() + 300
            while (System.currentTimeMillis() < deadline && usage !in seen) {
                seen += playingUsages()
                Thread.sleep(10)
            }
            assertTrue(usage in seen, "$channel: expected usage $usage among $seen")
            Thread.sleep(400) // let it finish before the next channel
        }
        CaptureSoundPlayer.shared.release()
    }

    @Test
    fun aCueReplaysBackToBack() {
        // Interval shots fire faster than a cue lasts; each must restart it,
        // not throw or go silent.
        repeat(5) {
            CaptureSoundPlayer.shared.play(CaptureCue.Click, SoundChannel.Media, 0.05f)
            Thread.sleep(30)
        }
        val seen = mutableSetOf<Int>()
        CaptureSoundPlayer.shared.play(CaptureCue.Warning, SoundChannel.Media, 0.05f)
        val deadline = System.currentTimeMillis() + 300
        while (System.currentTimeMillis() < deadline && AudioAttributes.USAGE_MEDIA !in seen) {
            seen += playingUsages()
            Thread.sleep(10)
        }
        assertTrue(AudioAttributes.USAGE_MEDIA in seen, "still plays after rapid replays: $seen")
        CaptureSoundPlayer.shared.release()
    }
}

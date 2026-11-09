package cz.hillview.capture

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import cz.hillview.settings.SoundChannel

@Composable
actual fun rememberCaptureSoundPreview(): CaptureSoundPreview? {
    return remember {
        val player = CaptureSoundPlayer.shared
        object : CaptureSoundPreview {
            override val shutterSoundRequiredByLaw = CaptureSoundPlayer.shutterSoundRequiredByLaw()
            override fun play(cue: CaptureCue, channel: SoundChannel, volume: Float) =
                player.play(cue, channel, volume)
        }
    }
}

package cz.hillview.capture

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.util.Log
import cz.hillview.plugin.hvTag
import cz.hillview.settings.SoundChannel

/**
 * Plays the capture cues on the stream the user chose (Settings → Capture
 * sound). One per process: capture and the Settings test button share it,
 * so a test sounds exactly like a shot.
 *
 * Static AudioTracks, one per cue, built on first use and rebuilt when the
 * channel changes: the PCM is a few kilobytes, and a static track replays
 * with no decode and little latency — the click is meant to land at the
 * exposure.
 *
 * Everything runs on the player's own thread. The capture callbacks that
 * call [play] run on the MAIN thread, and AudioTrack's stop / rewind / play
 * are synchronous calls into the audio server: measured on the emulator
 * (2026-11-07) at 4–67 ms a shot, ~300 ms for the first shot (building the
 * track) and again after a channel change — held on the UI thread during an
 * interval run. MediaActionSound, which this replaced, only queued its sound.
 * [prewarm] builds the tracks before the first shot needs them.
 */
class CaptureSoundPlayer private constructor() {

    private var channel: SoundChannel? = null
    private val tracks = mutableMapOf<CaptureCue, AudioTrack>()

    private val thread = java.util.concurrent.Executors.newSingleThreadExecutor { r ->
        Thread(r, "hv-capture-sound").apply { isDaemon = true }
    }

    /** Queue [cue] on the player's thread; returns at once. */
    fun play(cue: CaptureCue, channel: SoundChannel, volume: Float) {
        thread.execute { playNow(cue, channel, volume) }
    }

    /**
     * Build [cues] for [channel] ahead of the first shot, and settle the law
     * check while at it (camera1's getCameraInfo below API 33 is not free).
     */
    fun prewarm(channel: SoundChannel, cues: Collection<CaptureCue> = CaptureCue.entries) {
        thread.execute {
            try {
                requiredByLaw
                if (channel != this.channel) {
                    releaseTracks()
                    this.channel = channel
                }
                cues.forEach { cue -> tracks.getOrPut(cue) { build(cue, channel) } }
            } catch (e: Exception) {
                Log.w(TAG, "capture sound prewarm on $channel failed", e)
            }
        }
    }

    private fun playNow(cue: CaptureCue, channel: SoundChannel, volume: Float) {
        try {
            if (channel != this.channel) {
                releaseTracks()
                this.channel = channel
            }
            val track = tracks.getOrPut(cue) { build(cue, channel) }
            track.setVolume(volume.coerceIn(0f, 1f))
            // A static track replays from the top only once stopped and
            // rewound; a cue still sounding is cut off, which is right for
            // rapid interval shots.
            if (track.playState != AudioTrack.PLAYSTATE_STOPPED) track.stop()
            track.reloadStaticData()
            track.play()
        } catch (e: Exception) {
            Log.w(TAG, "capture cue $cue on $channel failed", e)
        }
    }

    /** Release the tracks, on the player's thread, after anything still queued. */
    fun release() {
        thread.execute { releaseTracks() }
    }

    private fun releaseTracks() {
        tracks.values.forEach { runCatching { it.release() } }
        tracks.clear()
    }

    private fun build(cue: CaptureCue, channel: SoundChannel): AudioTrack {
        val pcm = CaptureCueSynth.pcm(cue)
        val usage = when (channel) {
            SoundChannel.Media -> AudioAttributes.USAGE_MEDIA
            SoundChannel.Notification -> AudioAttributes.USAGE_NOTIFICATION
            SoundChannel.Alarm -> AudioAttributes.USAGE_ALARM
        }
        return AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(usage)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build(),
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(CaptureCueSynth.SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build(),
            )
            .setTransferMode(AudioTrack.MODE_STATIC)
            .setBufferSizeInBytes(pcm.size * 2)
            .build()
            .also { it.write(pcm, 0, pcm.size) }
    }

    companion object {
        private val TAG = hvTag("CaptureSound")

        /** The process's one player (AudioTrack needs no Context). */
        val shared: CaptureSoundPlayer by lazy { CaptureSoundPlayer() }

        /**
         * Whether this phone must play a shutter sound on every photo — some
         * regions require one by law, and the platform knows (CameraX reads
         * MediaActionSound.mustPlayShutterSound on 33+ and camera1's
         * canDisableShutterSound before). Then the system click plays regardless of the settings,
         * since only it is guaranteed to be audible where the law says so.
         */
        fun shutterSoundRequiredByLaw(): Boolean = requiredByLaw

        // Asked once: the answer cannot change while the process runs.
        private val requiredByLaw: Boolean by lazy {
            runCatching { androidx.camera.core.CameraInfo.mustPlayShutterSound() }.getOrDefault(false)
        }
    }
}

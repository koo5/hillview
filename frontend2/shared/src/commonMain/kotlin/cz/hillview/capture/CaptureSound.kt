package cz.hillview.capture

import cz.hillview.settings.ShutterSound
import cz.hillview.settings.SoundChannel
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.random.Random

/** One sound the capture pipeline can make. */
enum class CaptureCue { Click, Beep, Warning }

/**
 * What one capture should sound like, or null for silence.
 *
 * The degraded-position warning is its own switch, so it is the one sound
 * that survives a silenced shutter: it exists for a phone in a pocket, where
 * the screen can't say anything. With the warning off, a degraded capture
 * sounds like any other.
 */
fun captureCue(tone: CaptureTone, shutter: ShutterSound, warnDegraded: Boolean): CaptureCue? {
    val shutterCue = when (shutter) {
        ShutterSound.Click -> CaptureCue.Click
        ShutterSound.Beep -> CaptureCue.Beep
        ShutterSound.Off -> null
    }
    return when (tone) {
        CaptureTone.Normal -> shutterCue
        CaptureTone.Degraded -> if (warnDegraded) CaptureCue.Warning else shutterCue
    }
}

/**
 * The sounds, synthesized: 16-bit mono PCM. Made in code rather than shipped
 * as assets or borrowed from the platform, because the platform's
 * (MediaActionSound, ToneGenerator) each come bound to a stream the app
 * doesn't choose — the whole reason the sounds used to follow a different
 * volume control on every phone.
 */
object CaptureCueSynth {
    const val SAMPLE_RATE = 44_100
    private const val PEAK = 0.8 * Short.MAX_VALUE

    fun pcm(cue: CaptureCue): ShortArray = when (cue) {
        CaptureCue.Click -> click()
        CaptureCue.Beep -> tones(listOf(Tone(1_760.0, 80)))
        // Two lower beeps: unmistakably not the shutter, even half-heard.
        CaptureCue.Warning -> tones(listOf(Tone(880.0, 120), Gap(90), Tone(880.0, 120)))
    }

    private sealed interface Segment
    private data class Tone(val hz: Double, val ms: Int) : Segment
    private data class Gap(val ms: Int) : Segment

    private fun samples(ms: Int) = SAMPLE_RATE * ms / 1000

    private fun tones(segments: List<Segment>): ShortArray {
        val out = ArrayList<Short>()
        for (seg in segments) when (seg) {
            is Gap -> repeat(samples(seg.ms)) { out.add(0) }
            is Tone -> {
                val n = samples(seg.ms)
                val fade = samples(5)
                for (i in 0 until n) {
                    // Raised-cosine edges: a hard start or stop clicks.
                    val edge = when {
                        i < fade -> 0.5 - 0.5 * cos(PI * i / fade)
                        i >= n - fade -> 0.5 - 0.5 * cos(PI * (n - 1 - i) / fade)
                        else -> 1.0
                    }
                    out.add((PEAK * edge * sin(2 * PI * seg.hz * i / SAMPLE_RATE)).roundToInt().toShort())
                }
            }
        }
        return out.toShortArray()
    }

    /**
     * A mechanical shutter: two short transients, open then close, each a
     * burst of noise plus a ringing tick, decaying in a few milliseconds.
     * Seeded noise, so the sound is the same every time.
     */
    private fun click(): ShortArray {
        val total = samples(75)
        val buf = DoubleArray(total)
        val rng = Random(0x5EED)
        fun transient(atMs: Int, gain: Double) {
            val start = samples(atMs)
            val len = samples(14)
            for (i in 0 until len) {
                val idx = start + i
                if (idx >= total) break
                val t = i.toDouble() / SAMPLE_RATE
                val env = exp(-t / 0.0025)
                val noise = rng.nextDouble(-1.0, 1.0)
                val tick = sin(2 * PI * 2_400.0 * t)
                buf[idx] += gain * env * (0.6 * noise + 0.4 * tick)
            }
        }
        transient(0, 1.0)
        transient(45, 0.6)
        return ShortArray(total) { (PEAK * buf[it].coerceIn(-1.0, 1.0)).roundToInt().toShort() }
    }
}

/**
 * The Settings screen's handle on the platform's sound: a test button, and
 * whether this phone must play a shutter sound regardless (some regions
 * require one by law, and the platform says so). Null where there is no
 * capture (desktop).
 */
interface CaptureSoundPreview {
    val shutterSoundRequiredByLaw: Boolean
    fun play(cue: CaptureCue, channel: SoundChannel, volume: Float)
}

package cz.hillview.geo

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertTrue

/**
 * The batching path against real hardware: does the five-argument
 * `registerListener` take, and do samples land in the ring with a SPREAD of
 * timestamps rather than a collapsed one.
 *
 * The second half is the whole point. Batched delivery hands over a burst of
 * samples in one callback, and the wall clock used to be read AT DELIVERY — which
 * would have stamped the entire burst with one millisecond and flattened the
 * timeline that the window, the `dt_us` deltas and the high-water mark are all
 * built on. Nothing in a host test can see that, because nothing in a host test
 * delivers a burst.
 *
 * WHAT AN EMULATOR CANNOT SETTLE, said plainly: it has no hardware FIFO
 * (`fifoMaxEventCount` is 0), so the latency budget is accepted and then ignored,
 * and samples arrive one at a time exactly as before. So a pass here proves the
 * registration is valid and the derived clock is sane; it does NOT prove batching
 * saves power or that a burst is handled correctly. Only a device with a FIFO can
 * show that, and the log line to look for is a non-zero `fifo=` in
 * "IMU ring registered at FASTEST, batching 1000ms (…)".
 */
@RunWith(AndroidJUnit4::class)
class ImuBatchingDeviceTest {

    private val context: Context
        get() = InstrumentationRegistry.getInstrumentation().targetContext

    private fun imuSensors(): List<Sensor> {
        val m = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        return listOfNotNull(
            m.getDefaultSensor(Sensor.TYPE_ACCELEROMETER),
            m.getDefaultSensor(Sensor.TYPE_GYROSCOPE),
        )
    }

    /**
     * Reports the FIFO depth so a run on real hardware says whether batching can
     * do anything at all here. Not an assertion — 0 is a valid answer.
     */
    @Test
    fun theFifoDepthIsReported() {
        val sensors = imuSensors()
        assumeTrue("no accelerometer or gyroscope on this device", sensors.isNotEmpty())
        for (s in sensors) {
            println(
                "IMU FIFO: ${s.name} max=${s.fifoMaxEventCount} " +
                    "reserved=${s.fifoReservedEventCount} minDelay=${s.minDelay}us",
            )
        }
        assertTrue(true)
    }

    /**
     * The five-argument registration is accepted, and the samples that arrive have
     * DISTINCT, increasing wall-clock timestamps derived from each event's own
     * clock.
     *
     * Drives the real engine rather than a listener of its own: the derived clock
     * lives in `GeoEngine`, and a private copy here would test the test.
     */
    @Test
    fun samplesArriveWithASpreadOfTimestamps() {
        assumeTrue("no IMU on this device", imuSensors().isNotEmpty())
        val engine = GeoEngine.get(context)
        // externalCameraConfig, NOT captureGeoConfig, and the reason is worth
        // knowing: `sensorsWanted()` is `active.sensors && (foreground ||
        // active.sensorsInBackground)`, and an instrumented test has no foreground
        // activity. With capture's `sensorsInBackground = false` the engine
        // correctly declined to register anything at all, and the first version of
        // this test skipped on "no samples" while proving nothing. The external
        // config is the one that permits background sensors, which is also the
        // path that most needs covering.
        engine.configure(externalCameraConfig(imuContinuous = true), OWNER_ACTIVITY)
        try {
            // Long enough for the ring to hold a usable span at any delivery rate.
            Thread.sleep(3_000)
            val now = System.currentTimeMillis()
            val summary = engine.persistImuWindow(now - 2_500, now + 500)
            assumeTrue(
                "the platform delivered no IMU samples (synthetic sensors on an emulator)",
                summary != null,
            )
            val s = summary!!
            println(
                "IMU window: ${s.sampleCount} samples ${s.startMs}..${s.endMs} " +
                    "(${s.endMs - s.startMs}ms span), stored=${s.storedCount}",
            )
            assertTrue(s.sampleCount > 1, "only ${s.sampleCount} sample(s) — nothing to spread")
            // THE assertion: a collapsed timeline is the batching bug. Every sample
            // stamped at delivery would give a span of ~0 across a burst.
            assertTrue(
                s.endMs > s.startMs,
                "timestamps collapsed: ${s.sampleCount} samples all at ${s.startMs}",
            )
            // Bounds come from min/max now, so they cannot be inverted even when
            // two sensors' bursts interleave.
            assertTrue(s.endMs >= s.startMs, "window bounds inverted — first/last regression")
        } finally {
            engine.configure(GeoConfig.Off, OWNER_ACTIVITY)
        }
    }
}

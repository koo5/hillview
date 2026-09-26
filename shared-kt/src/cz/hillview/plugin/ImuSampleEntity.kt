package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

/**
 * One raw inertial sample, from the window around a shutter.
 *
 * **Written per CAPTURE, not continuously.** The engine keeps a ring buffer in
 * memory at sensor rate and persists only the window bracketing an exposure, so
 * rows scale with PHOTOS rather than with session length: about a hundred rows
 * a shot at 100 Hz for a one-second window, against roughly 720 000 for two
 * hours of continuous logging. Continuous persistence was considered and
 * rejected on exactly that arithmetic.
 *
 * **Why raw samples at all**, when a photo already records gravity and
 * gravity-free acceleration at the shutter: a single sample cannot describe an
 * EXPOSURE. Motion blur is the integral of movement across the shutter being
 * open, rolling shutter smears differently down the frame, and telling a
 * hand-held wobble from a moving vehicle needs the shape of the signal rather
 * than one number from the middle of it. That is what a window gives and a
 * point never can.
 *
 * `kind` rather than one row per axis-triple, because accelerometer and
 * gyroscope arrive on separate callbacks at rates the platform chooses. Pairing
 * them into one row would mean inventing a correspondence the sensors never
 * claimed — the same class of lie as the invented `0f` pitch this project
 * removed from the bearings table.
 *
 * NOTE ON RETENTION: like `bearings` and `locations`, these rows are cleared
 * five minutes back on every dump, and the dump only WRITES a file when
 * tracking auto-export is on. So the raw window survives a session only with
 * export enabled; the per-photo SUMMARY in the upload's `motion` object travels
 * regardless, and is what a server-side reader gets.
 */
@Entity(
    tableName = "imu_samples",
    // (timestamp, kind, axisSet): two sensors can report the same millisecond,
    // and one sensor can report twice in a millisecond at 200 Hz. Without the
    // third component such a pair would REPLACE rather than accumulate — the
    // bug the bearings table's composite key exists to prevent.
    primaryKeys = ["timestamp", "kind", "sequence"],
    indices = [Index(value = ["timestamp"])],
)
data class ImuSampleEntity(
    /** Wall-clock ms of the sample. */
    val timestamp: Long,
    /** "accel" (m/s², gravity INCLUDED) or "gyro" (rad/s). */
    val kind: String,
    /** Monotonic within a millisecond, so same-ms samples accumulate. */
    val sequence: Int,
    val x: Float,
    val y: Float,
    val z: Float,
    /**
     * The sensor's own timestamp in nanoseconds of the device's monotonic
     * clock — `SensorEvent.timestamp`. Kept beside the wall clock because it is
     * the one that can be compared with an exposure: the wall clock can step
     * (an NTP correction), and a window whose ordering depends on it would
     * reorder mid-capture.
     */
    val elapsedNanos: Long,
)

/** m/s2, for turning a raw accelerometer magnitude into a gravity-free deviation. */
const val STANDARD_GRAVITY_MPS2 = 9.80665

/**
 * What a window of samples says about the frame it brackets.
 *
 * A PURE function over rows, in shared-kt, because two callers need it and
 * neither should own it: the engine summarises the slice it just persisted, and
 * the upload path summarises the slice it reads back out of the table once the
 * window has closed. One implementation means the two cannot disagree about
 * what "peak" meant.
 */
data class ImuWindowStats(
    val sampleCount: Int,
    val startMs: Long,
    val endMs: Long,
    /** Peak raw accelerometer magnitude, m/s2. INCLUDES gravity (~9.81 at rest). */
    val accelPeakMps2: Double? = null,
    /**
     * Peak |magnitude - g| — the gravity-free shake signal, derived from the raw
     * accelerometer rather than needing the linear-acceleration sensor. Near zero
     * for a still phone at ANY orientation, which the raw peak is not.
     */
    val accelPeakDeviationMps2: Double? = null,
    /** Peak angular rate, rad/s — the rotation-blur signal, gravity-free by nature. */
    val gyroPeakRadS: Double? = null,
)

fun summariseImuWindow(samples: List<ImuSampleEntity>): ImuWindowStats? {
    if (samples.isEmpty()) return null
    fun magnitude(s: ImuSampleEntity) = kotlin.math.sqrt(
        s.x.toDouble() * s.x + s.y.toDouble() * s.y + s.z.toDouble() * s.z,
    )
    val accel = samples.filter { it.kind == "accel" }.map(::magnitude)
    val gyro = samples.filter { it.kind == "gyro" }.map(::magnitude)
    return ImuWindowStats(
        sampleCount = samples.size,
        startMs = samples.first().timestamp,
        endMs = samples.last().timestamp,
        accelPeakMps2 = accel.maxOrNull(),
        accelPeakDeviationMps2 = accel.maxOfOrNull { kotlin.math.abs(it - STANDARD_GRAVITY_MPS2) },
        gyroPeakRadS = gyro.maxOrNull(),
    )
}

@Dao
interface ImuDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insertAll(samples: List<ImuSampleEntity>)

    @Query("SELECT * FROM imu_samples ORDER BY timestamp ASC, kind ASC, sequence ASC")
    fun getAllSamples(): List<ImuSampleEntity>

    @Query(
        "SELECT * FROM imu_samples WHERE timestamp BETWEEN :fromMs AND :toMs " +
            "ORDER BY timestamp ASC, kind ASC, sequence ASC",
    )
    fun getInWindow(fromMs: Long, toMs: Long): List<ImuSampleEntity>

    @Query("SELECT COUNT(*) FROM imu_samples")
    fun count(): Int

    @Query("DELETE FROM imu_samples WHERE timestamp < :cutoff")
    fun clearOlderThan(cutoff: Long)
}

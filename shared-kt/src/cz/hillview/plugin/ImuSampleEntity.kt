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

// --- the raw payload that travels with the photo (docs/recon-capture-metadata.md, Phase 5) ---

/**
 * Most samples a single photo's payload may carry.
 *
 * The ring's capacity, deliberately, rather than a byte figure someone picked:
 * `GeoEngine.imuRing` is `ImuRing(capacity = 16_000)`, so no honest window can
 * exceed it and a payload that claims more was not produced by this app. The
 * worker enforces the same number at its door — see the plan doc's "Size"
 * section for why the bound is expressed in samples.
 */
const val IMU_PAYLOAD_MAX_SAMPLES = 16_000

/** Accelerometer resolution is ~1e-3 m/s2; printing more is printing float noise. */
private const val ACCEL_DECIMALS = 3

/** Gyroscope resolution is ~1e-4 rad/s. */
private const val GYRO_DECIMALS = 4

/**
 * Fixed-point with the trailing zeros removed, and never a locale's comma.
 *
 * `String.format` without [java.util.Locale.ROOT] emits `0,012` in a Czech
 * locale, which is not JSON — and this app's author's phone is Czech.
 */
private fun fmt(v: Double, decimals: Int): String {
    val s = String.format(java.util.Locale.ROOT, "%.${decimals}f", v)
    var t = if ('.' in s) s.trimEnd('0').trimEnd('.') else s
    if (t.isEmpty() || t == "-0") t = "0"
    return t
}

private fun decimalsFor(kind: String) = if (kind == "gyro") GYRO_DECIMALS else ACCEL_DECIMALS

/**
 * The raw window as the payload that travels beside the photo: **columnar and
 * delta-encoded**, one object per sensor.
 *
 * ```json
 * {"accel":{"t0_ms":1700000000000,"t0_ns":812340000000,
 *           "dt_us":[2500,2501,...],"x":[...],"y":[...],"z":[...]}}
 * ```
 *
 * - **Columnar**, so a key name appears once per array instead of once per
 *   sample. Row-wise, `{"t":..,"x":..,"y":..,"z":..}` repeated four thousand
 *   times IS most of the bytes.
 * - **`dt_us` holds n-1 GAPS for n samples**, in microseconds, from
 *   [ImuSampleEntity.elapsedNanos] — the monotonic clock, not the wall clock,
 *   because the wall clock can step mid-window under an NTP correction and a
 *   window whose ordering depended on it would reorder. Microseconds because at
 *   400 Hz millisecond resolution puts two or three samples on one instant.
 *   Reconstruct as `t[0] = 0; t[i] = t[i-1] + dt_us[i-1]`.
 * - **`t0_ms` and `t0_ns` are both the FIRST sample's**: the wall clock so the
 *   window can be found in time, the monotonic one so it can be joined to
 *   anything else sampled on that clock (an exposure, another sensor).
 * - **Rounded to what the sensor can resolve.** Not lossy; the digits below it
 *   are noise that gzip cannot compress because it is random.
 * - **Inspectable, not packed.** A base64 float32 blob is about the same size
 *   after gzip and unreadable when a pipeline misbehaves. For a research
 *   artifact that trade goes the other way.
 *
 * Returns null for an empty window — the honest answer on a device with no
 * gyroscope, or for a capture taken before the buffer filled.
 */
fun imuSamplesPayloadJson(samples: List<ImuSampleEntity>): String? {
    if (samples.isEmpty()) return null
    val objects = samples.groupBy { it.kind }.entries
        .sortedBy { it.key }
        .map { (kind, rows) -> kindPayload(kind, rows.sortedBy { it.elapsedNanos }) }
    return objects.joinToString(",", prefix = "{", postfix = "}")
}

private fun kindPayload(kind: String, rows: List<ImuSampleEntity>): String {
    val d = decimalsFor(kind)
    val first = rows.first()
    // n-1 gaps, rounded to whole microseconds. Integer division of the
    // nanosecond difference, so gaps never accumulate a fractional drift.
    val gaps = (1 until rows.size).joinToString(",") {
        ((rows[it].elapsedNanos - rows[it - 1].elapsedNanos) / 1_000).toString()
    }
    fun axis(pick: (ImuSampleEntity) -> Float) =
        rows.joinToString(",") { fmt(pick(it).toDouble(), d) }
    return """"$kind":{"t0_ms":${first.timestamp},"t0_ns":${first.elapsedNanos},""" +
        """"dt_us":[$gaps],"x":[${axis { it.x }}],"y":[${axis { it.y }}],"z":[${axis { it.z }}]}"""
}

/**
 * One capture's CLAIM on the sample stream: the contiguous range of
 * `imu_samples` that this exposure, and no other, is responsible for.
 *
 * **Why a claim table rather than an owner column on every sample.** Attribution
 * has to be DATA — inferring it from a high-water mark and a window's nominal
 * bounds does not work, because the bounds a photo asks for and the samples it
 * actually adds are different things, and consecutive captures interleave. But
 * stamping every sample with its owner costs a 6-byte integer per ROW: ~33 KB
 * per photo in this database and another ~14 characters per row in the CSV dump,
 * which at continuous rates is tens of megabytes an hour. A claim is one row per
 * PHOTO — about 24 bytes — for the same exactness. Roughly a thousandth of the
 * cost, and the user was right to push back on the per-sample version.
 *
 * It works because a capture stores its samples in exactly ONE burst: the
 * pre-shutter summary is read-only (see `GeoEngine.summariseImuWindow`), so the
 * only writer is the deferred symmetric persist, and those fire in shutter order
 * on one Handler. So each capture's contribution is a single contiguous range,
 * and successive ranges tile.
 *
 * It also turns a RACE into a condition. The upload path used to wait out the
 * same deadline as the engine's deferred write and then read the table, with no
 * ordering between the two — so the post-shutter half was present or absent
 * depending on which timer fired first. Now it waits for this row to EXIST.
 */
@Entity(tableName = "imu_claims")
data class ImuClaimEntity(
    /**
     * The shutter this claim belongs to — `SensorSnapshot.capturedAtMs`, which
     * the photo row also carries, so no new identifier has to be invented or
     * threaded through the capture path.
     */
    @androidx.room.PrimaryKey val capturedAtMs: Long,
    /** First sample timestamp this capture stored, inclusive. */
    val fromMs: Long,
    /** Last sample timestamp this capture stored, inclusive. */
    val toMs: Long,
    /** How many rows that range holds, so a reader can verify it got them all. */
    val sampleCount: Int,
)

@Dao
interface ImuClaimDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    fun insert(claim: ImuClaimEntity)

    @Query("SELECT * FROM imu_claims WHERE capturedAtMs = :capturedAtMs")
    fun get(capturedAtMs: Long): ImuClaimEntity?

    @Query("SELECT * FROM imu_claims ORDER BY capturedAtMs ASC")
    fun getAll(): List<ImuClaimEntity>

    /**
     * Cleared on the same schedule as the samples themselves — a claim on rows
     * that have been dumped and deleted describes nothing.
     */
    @Query("DELETE FROM imu_claims WHERE toMs < :cutoff")
    fun clearOlderThan(cutoff: Long)
}

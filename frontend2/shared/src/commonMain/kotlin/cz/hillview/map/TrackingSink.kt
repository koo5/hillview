package cz.hillview.map

/**
 * The persist boundary for the position/bearing funnel — the Kotlin twin of
 * what `updateBearing`/`updateSpatialState` do in the original's
 * `mapState.ts` beyond touching the store: push the election, and write the
 * tracking-table row.
 *
 * A seam because the rules belong in commonMain (testable in jvmTest) while
 * the rows are Android's. Desktop gets [Noop] and behaves exactly as before.
 */
interface TrackingSink {
    /** Which source is PRIMARY from now on (pushed on change only). */
    fun electBearingSource(source: String)
    fun electLocationSource(source: String)

    /** A bearing the app itself produced — see [engineOwnsSource]. */
    fun writeBearingRow(
        bearing: Double,
        source: String,
        detail: String,
        accuracyLevel: Int?,
        now: Long,
    )

    /** A position the USER placed (the map-pan claim). */
    fun writeLocationRow(
        latitude: Double,
        longitude: Double,
        source: String,
        detail: String,
        now: Long,
    )

    object Noop : TrackingSink {
        override fun electBearingSource(source: String) {}
        override fun electLocationSource(source: String) {}
        override fun writeBearingRow(
            bearing: Double,
            source: String,
            detail: String,
            accuracyLevel: Int?,
            now: Long,
        ) {}
        override fun writeLocationRow(
            latitude: Double,
            longitude: Double,
            source: String,
            detail: String,
            now: Long,
        ) {}
    }
}

/** A table row's source and the finer provenance within it. */
data class TableSource(val source: String, val detail: String)

/**
 * Collapse the app's fine-grained bearing/location source into the coarse
 * ELECT-ABLE vocabulary (`android` | `gps-kalman` | `manual`).
 *
 * Port of `toTableSource()` in `frontend/src/lib/mapState.ts`, semantics
 * pinned there by `mapState.test.ts`. The fine name stays in the state (it
 * drives the UI and the EXIF `bearing_source`); it collapses ONLY here, at
 * the boundary where a row is persisted, so "re-query for the elected
 * source" stays `sourceId = electedSourceId` rather than a lookup table.
 */
fun toTableSource(source: String): TableSource = when {
    source == "gps-kalman" -> TableSource("gps-kalman", "")
    source.contains("-compass-") -> TableSource("android", source)
    else -> TableSource("manual", source)
}

/**
 * Sources the GeoEngine records itself, at sensor rate, so the funnel must
 * NOT echo them — an echo would file a second row for a sample already
 * written, at a different millisecond (the composite key would faithfully
 * keep both).
 *
 * Port of `kotlinOwnsSource()` in `mapState.ts`, and the same invariant as
 * `is_sensor_bearing_source()` in `src-tauri/src/device_photos.rs`: a source
 * the funnel echoes is one whose state value is authoritative; a source the
 * engine owns is one whose TABLE row is. Change one, change all three.
 */
fun engineOwnsSource(source: String): Boolean =
    source.startsWith("android") || source == "gps-kalman"

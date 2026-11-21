package cz.hillview.arch

import java.io.File
import kotlin.test.Test
import kotlin.test.fail

/**
 * Raw sensor samples reach the one state in a KNOWN set of places.
 *
 * Pitch changes sign at that boundary: positive down below it, positive up at and
 * above it (see `cz.hillview.map.PitchConvention`). The conversion is one function,
 * and the only way it can be bypassed is a new place that takes a sample and writes
 * it somewhere.
 *
 * The plan this came from left this test optional. It is not, because of what the
 * research that preceded it found: it named ONE entry point into the state, and
 * there were two. The second was a lambda argument three files away from the first,
 * carrying a bare `Double` with no name saying which way it pointed. Nothing about
 * adding a third would remind anyone to come back here, so the list is checked
 * rather than remembered.
 *
 * The check is deliberately coarse — the file names the TYPE, not the field. A text
 * match cannot tell `it.pitch` on a raw sample from `stamp?.pitch` on the state,
 * and guessing wrong in either direction is worse than asking the author of a new
 * file to add a line here saying what it does.
 */
class PitchEntryPointTest {

    /** Where a raw sample may be handled, and what each one does with its pitch. */
    private val allowed = mapOf(
        "map/AttitudeMapping.kt" to
            "THE conversion: builds the state's attitude record, calling statePitchFromSensor",
        "map/MapScreen.android.kt" to
            "the compass callback, the second entry — converts at the call site",
        "geo/GeoEngine.kt" to
            "the attitude ring and the IMU ring; the ring keeps RAW rows, positive down, on purpose",
        "geo/ImuRing.kt" to
            "the ring's own storage — raw rows again, never read as the state's pitch",
        "capture/PhotoCapture.android.kt" to
            "reads the STATE's attitude, not a sample; mentions the type only to name it",
        "map/TrackingSink.android.kt" to
            "writes the bearings table, which is below the boundary and so positive down",
        "map/MapState.kt" to
            "the state itself, and the sink call that converts back",
        "geo/GeoDebugText.kt" to
            "the diagnostics readout — see docs/one-state.md's exception for it",
    )

    @Test
    fun onlyKnownPlacesHandleARawOrientationSample() {
        val roots = kotlinSourceRoots()
        val offenders = roots.flatMap { root ->
            root.walkTopDown()
                .filter { it.isFile && it.extension == "kt" }
                .filterNot { it.path.contains("Test") }
                .filter { "OrientationSensorData" in kotlinCodeOnly(it.readText()) }
                .filterNot { f ->
                    val path = f.path.replace('\\', '/')
                    // shared-kt is BELOW the boundary by design: its sensor code,
                    // its tables and its rings are all positive down, and the plan
                    // of 2026-11-17 decided they stay that way.
                    "/shared-kt/" in path || allowed.keys.any { path.endsWith(it) }
                }
                .map { it.relativeTo(root).path }
                .toList()
        }

        if (offenders.isNotEmpty()) {
            fail(
                "these handle a raw orientation sample and are not in " +
                    "PitchEntryPointTest's list. If one of them puts a pitch into the " +
                    "one state it must call statePitchFromSensor first (positive down " +
                    "to positive up); if it does not, add it with a line saying so:\n" +
                    offenders.joinToString("\n") { "  $it" },
            )
        }
    }

    /**
     * The conversion is reachable and named. A rename that left the entry points
     * calling something else would pass the list above while quietly undoing it.
     */
    @Test
    fun theEntryPointsCallTheConversion() {
        val roots = kotlinSourceRoots()
        listOf("map/AttitudeMapping.kt", "map/MapScreen.android.kt").forEach { name ->
            val file = roots.firstNotNullOfOrNull { root ->
                root.walkTopDown().firstOrNull { f: File ->
                    f.isFile && f.path.replace('\\', '/').endsWith(name)
                }
            } ?: fail("$name has moved — this test and the boundary it guards need rereading")
            val code = kotlinCodeOnly(file.readText())
            if ("statePitchFromSensor" !in code) {
                fail(
                    "$name takes a raw orientation sample but no longer calls " +
                        "statePitchFromSensor, so a positive-down pitch may be reaching " +
                        "the one state, which holds positive up.",
                )
            }
        }
    }
}

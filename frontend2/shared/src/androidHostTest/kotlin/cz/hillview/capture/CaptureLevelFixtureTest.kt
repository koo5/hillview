package cz.hillview.capture

import cz.hillview.plugin.GRAVITY_ROLL_FLOOR
import java.io.File
import kotlin.math.PI
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.sqrt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.fail

/**
 * The same cases `capture_pose.py` and the web app answer, answered here.
 *
 * `backend/common/capture_pose_cases.json` is READ, not copied. Three ports of one
 * piece of arithmetic would otherwise drift, and the drift would show up as photos
 * quietly failing the Panoramax gates on one client and not another. The Python side
 * (`test_capture_pose.py`) and the TypeScript side (`capturePoseMath.test.ts`) both
 * load the same file and assert the same limits against their own constants; this is
 * the third leg of that.
 *
 * It starts from GRAVITY, as the fixture does, and derives what the one state would
 * be holding for that pose — which is the only honest way to test a function that
 * takes angles against a fixture written in vectors.
 */
class CaptureLevelFixtureTest {

    private data class Case(
        val id: String,
        val gravity: List<Double>,
        val pitch: Double,
        val roll: Double?,
        val level: String,
    )

    private val fixture: Map<String, Any?> by lazy { parse(fixtureFile().readText()) }

    @Suppress("UNCHECKED_CAST")
    private fun cases(): List<Case> =
        (listOf("cases", "deviceorientation").flatMap { fixture[it] as List<Map<String, Any?>> })
            .map {
                Case(
                    id = it["id"] as String,
                    gravity = (it["gravity"] as List<Any?>).map { v -> (v as Number).toDouble() },
                    pitch = (it["pitch"] as Number).toDouble(),
                    roll = (it["roll"] as Number?)?.toDouble(),
                    level = it["level"] as String,
                )
            }

    /**
     * The gates are ONE pair of numbers, wherever they are spelled. If this fails,
     * one of the four places has moved and the others have not.
     */
    @Test
    fun theLimitsAreTheFixturesLimits() {
        assertEquals((fixture["max_pitch_deg"] as Number).toDouble(), LEVEL_MAX_PITCH_DEG)
        assertEquals((fixture["max_roll_deg"] as Number).toDouble(), LEVEL_MAX_ROLL_DEG)
    }

    /**
     * ...and so is the roll floor, which this module has to spell out because
     * `CameraPose.kt` is shared-kt and the overlay is common. Duplication that a
     * test checks is a different thing from duplication that nobody checks.
     */
    @Test
    fun theRollFloorIsTheSensorStacksRollFloor() {
        assertEquals((fixture["roll_floor"] as Number).toDouble(), LEVEL_ROLL_FLOOR)
        // Crossed in FLOAT space, which is where the sensor stack's constant lives.
        // Widening 0.26f gives 0.2599999904, so comparing as Doubles would need a
        // tolerance, and a tolerance here would hide the very drift this is for.
        assertEquals(GRAVITY_ROLL_FLOOR, LEVEL_ROLL_FLOOR.toFloat())
    }

    @Test
    fun localPhotoPitchAgreesWithTheBackendForEveryFixturePose() {
        for (case in cases()) {
            val shot = SensorSnapshot(
                capturedAtMs = 1_700_000_000_000L,
                motion = cz.hillview.map.DeviceMotionSample(
                    gravity = case.gravity.map { it.toFloat() },
                    atMs = 1_700_000_000_000L,
                ),
            )
            assertEquals(case.pitch, shot.measuredPitchDeg()!!, 0.01, case.id)
        }
    }

    @Test
    fun everyCaseAgreesWithCapturePose() {
        val rows = cases()
        assertTrue(rows.size >= 29, "the fixture should carry the real series: ${rows.size}")
        val wrong = rows.mapNotNull { case ->
            val g = case.gravity
            val n = sqrt(g.sumOf { it * it })
            // What the one state would hold for this pose: pitch positive UP, and the
            // stamp-style image roll the overlay reads.
            val statePitch = -asin((g[2] / n).coerceIn(-1.0, 1.0)) * 180.0 / PI
            val imageRoll = atan2(g[0], g[1]) * 180.0 / PI

            val gotLevel = captureLevel(statePitch, imageRoll).name.lowercase()
            val gotRoll = if (captureLevel(statePitch, imageRoll) == CaptureLevel.Flat) {
                null
            } else {
                levelRollDeg(imageRoll)
            }
            val complaints = buildList {
                if (gotLevel != case.level) add("level $gotLevel != ${case.level}")
                if (kotlin.math.abs(statePitch - case.pitch) > 0.01) {
                    add("pitch $statePitch != ${case.pitch}")
                }
                val wantRoll = case.roll
                when {
                    wantRoll == null && gotRoll != null -> add("roll $gotRoll, expected none")
                    wantRoll != null && gotRoll == null -> add("no roll, expected $wantRoll")
                    wantRoll != null && gotRoll != null &&
                        kotlin.math.abs(gotRoll - wantRoll) > 0.01 ->
                        add("roll $gotRoll != $wantRoll")
                }
            }
            if (complaints.isEmpty()) null else "${case.id}: ${complaints.joinToString("; ")}"
        }
        if (wrong.isNotEmpty()) fail("disagrees with capture_pose:\n" + wrong.joinToString("\n"))
    }

    /** The wording is the web app's, so one measurement is described one way. */
    @Test
    fun theWordsMatchTheWebApps() {
        assertEquals("Level", captureLevelWords(0.0, 0.0))
        assertEquals("Pointing at the sky", captureLevelWords(80.0, 0.0))
        assertEquals("Pointing at the ground", captureLevelWords(-80.0, 0.0))
        assertEquals("Tilted up 25°", captureLevelWords(25.0, 0.0))
        assertEquals("Horizon tilted 23°", captureLevelWords(3.7, 22.9))
        assertEquals(null, captureLevelWords(null, null))
    }

    private fun fixtureFile(): File {
        var dir: File? = File(".").canonicalFile
        while (dir != null) {
            val f = File(dir, "backend/common/capture_pose_cases.json")
            if (f.isFile) return f
            dir = dir.parentFile
        }
        fail("capture_pose_cases.json not found from ${File(".").canonicalPath}")
    }

    // --- a JSON reader, because this source set has no serialization dependency ---

    private fun parse(text: String): Map<String, Any?> {
        val p = P(text)
        p.ws()
        @Suppress("UNCHECKED_CAST")
        return p.value() as Map<String, Any?>
    }

    private class P(private val s: String) {
        private var i = 0
        fun ws() { while (i < s.length && s[i].isWhitespace()) i++ }
        fun value(): Any? {
            ws()
            return when (s[i]) {
                '{' -> obj()
                '[' -> arr()
                '"' -> str()
                't' -> { i += 4; true }
                'f' -> { i += 5; false }
                'n' -> { i += 4; null }
                else -> num()
            }
        }
        private fun obj(): Map<String, Any?> = buildMap {
            i++; ws()
            if (s[i] == '}') { i++; return@buildMap }
            while (true) {
                ws(); val k = str(); ws(); i++ // ':'
                put(k, value()); ws()
                if (s[i] == ',') { i++ } else { i++; break }
            }
        }
        private fun arr(): List<Any?> = buildList {
            i++; ws()
            if (s[i] == ']') { i++; return@buildList }
            while (true) {
                add(value()); ws()
                if (s[i] == ',') { i++ } else { i++; break }
            }
        }
        private fun str(): String {
            i++ // opening quote
            val b = StringBuilder()
            while (s[i] != '"') {
                if (s[i] == '\\') {
                    i++
                    when (s[i]) {
                        'n' -> b.append('\n'); 't' -> b.append('\t'); 'r' -> b.append('\r')
                        'u' -> { b.append(s.substring(i + 1, i + 5).toInt(16).toChar()); i += 4 }
                        else -> b.append(s[i])
                    }
                } else {
                    b.append(s[i])
                }
                i++
            }
            i++
            return b.toString()
        }
        private fun num(): Double {
            val start = i
            while (i < s.length && (s[i].isDigit() || s[i] in "-+.eE")) i++
            return s.substring(start, i).toDouble()
        }
    }
}

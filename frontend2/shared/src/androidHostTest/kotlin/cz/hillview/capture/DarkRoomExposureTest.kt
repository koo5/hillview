package cz.hillview.capture

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The pitch-black room, as arithmetic: Sports @ 1/2000, no light. This is
 * the loop the phone actually runs — each analysis frame is metered as
 * having come from the CURRENT plan's exposure, and the plan is recomputed
 * from the meter — so if this converges and the device does not, the fault
 * is in the plumbing (analysis stream, request options), never in the
 * numbers. Field report that motivated it: "pitch black, sports with
 * 1/2000 still says 1/2000 and takes pitch black photos."
 */
class DarkRoomExposureTest {

    private val caps = SensorExposureCaps(
        minExposureNs = 100_000L,
        maxExposureNs = 100_000_000L,
        minIso = 50,
        maxIso = 3200,
    )

    private val sports = ExposureRule(ExposureMode.Sports, 500_000L) // 1/2000

    /** One dark frame: luma ~0, credited to whatever the plan last was. */
    private fun converge(meter: SceneMeter, startPlan: ExposurePlan, frames: Int): ExposurePlan {
        var plan = startPlan
        repeat(frames) {
            meter.onFrame(meanLuma = 0.5, exposureNs = plan.exposureNs, iso = plan.iso)
            val (m, iso) = meter.meteredPair()!!
            plan = planExposure(sports, m, iso, caps)
        }
        return plan
    }

    @Test
    fun sportsInAPitchBlackRoomSlidesToItsFloorWithinASecond() {
        val meter = SceneMeter()
        // The rule engages while it is already dark: the first plan comes
        // from whatever AE was doing (long exposure, high gain).
        meter.seedFromAutoExposure(exposureNs = 33_000_000L, iso = 3200)
        val first = planExposure(sports, meter.meteredPair()!!.first, meter.meteredPair()!!.second, caps)

        // Even the FIRST plan is nowhere near the target: AE's own reading
        // already says the room is dark.
        assertEquals(SPORTS_SLOWEST_NS, first.exposureNs, "first plan should already sit at the floor")

        // A second of black frames must keep it there, pinned at max gain.
        val settled = converge(meter, first, frames = 30)
        assertEquals(SPORTS_SLOWEST_NS, settled.exposureNs)
        assertEquals(caps.maxIso, settled.iso)
        assertEquals(ExposureOutcome.Underexposed, settled.outcome)
    }

    /**
     * The harder case: the rule was engaged in the LIGHT (meter believes
     * the scene is bright), then the lights go out. The floor branch of the
     * meter (luma below LUMA_FLOOR steps a fixed stop) has to walk the
     * product up frame by frame until the plan hits the Sports floor.
     */
    @Test
    fun lightsGoingOutWalksThePlanToTheFloorFrameByFrame() {
        val meter = SceneMeter()
        meter.seedFromAutoExposure(exposureNs = 500_000L, iso = 100) // sunny
        var plan = planExposure(sports, meter.meteredPair()!!.first, meter.meteredPair()!!.second, caps)
        assertEquals(sports.targetNs, plan.exposureNs, "in the light the target holds")

        plan = converge(meter, plan, frames = 30)
        assertEquals(SPORTS_SLOWEST_NS, plan.exposureNs, "30 dark frames (~1 s) must reach the floor")
        assertEquals(caps.maxIso, plan.iso)
    }

    /**
     * And the honest part of the field report: 1/125 at ISO 3200 in a
     * genuinely pitch-black room IS a black photo. Sports' contract is
     * "never slower than 1/125"; the mode that photographs a dark room is
     * Auto. The test pins the contract so nobody "fixes" the black photo
     * by silently letting Sports crawl.
     */
    @Test
    fun sportsNeverGoesSlowerThanItsFloorNoMatterHowDark() {
        val meter = SceneMeter()
        meter.seedFromAutoExposure(exposureNs = 100_000_000L, iso = 3200)
        val plan = converge(
            meter,
            planExposure(sports, meter.meteredPair()!!.first, meter.meteredPair()!!.second, caps),
            frames = 120,
        )
        assertTrue(plan.exposureNs <= SPORTS_SLOWEST_NS)
    }
}

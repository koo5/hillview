package cz.hillview.capture

import kotlin.math.abs
import kotlin.math.pow
import kotlin.test.Test
import kotlin.test.assertTrue

/**
 * The exposure loop closed against a synthetic scene: SceneMeter's
 * estimate, planExposure spending it, the "sensor" taking the frame at the
 * plan, and meterCreditedExposure deciding which exposure the frame's luma
 * is credited to.
 *
 * The scenario is the field report this guards (2026-08-21): Sports
 * engaged in dim light — which freezes the AE harvest there — then the
 * scene brightens six stops mid-run with nobody watching the preview.
 * Credit frames to the plan and the loop re-converges to the metering
 * target within a couple of dozen frames; credit them to the frozen
 * harvest (the old precedence) and the fixed point moves to
 * luma = target × (harvest / estimate), which pins the whole run near
 * clipping — the "interval Sports stuck in high exposure" symptom.
 *
 * The scene model is a gamma tone curve, not a linear one, because
 * SceneMeter's damping exists to survive exactly that; the loop has to
 * converge THROUGH the curve, not thanks to its absence.
 */
class SceneMeterLoopTest {

    private val rule = ExposureRule(ExposureMode.Sports, targetNs = 2_000_000L)
    private val caps = SensorExposureCaps(
        minExposureNs = 100_000L,
        maxExposureNs = 100_000_000L,
        minIso = 50,
        maxIso = 6400,
    )

    /** What AE last chose in the dim light the rule was engaged in. */
    private val harvestNs = 33_000_000L
    private val harvestIso = 800

    /**
     * Tone-mapped luma for a scene at an exposure product — gamma 2.2,
     * scaled so the harvest exposes the dim scene exactly to target.
     */
    private fun luma(scene: Double, exposureNs: Long, iso: Int): Double {
        val linear = scene * exposureNs.toDouble() * iso.toDouble()
        return (255.0 * linear.pow(1 / 2.2)).coerceIn(0.0, 255.0)
    }

    /** scene × product == this at a correctly exposed (target-luma) frame. */
    private val correctLinear = (SceneMeter.TARGET_LUMA / 255.0).pow(2.2)

    private fun runLoop(
        frames: Int,
        creditOf: (ExposurePlan) -> Pair<Long, Int>,
    ): List<Double> {
        val meter = SceneMeter()
        // Engaging a rule seeds the meter from AE's own answer.
        meter.seedFromAutoExposure(harvestNs, harvestIso)
        val dimScene = correctLinear / (harvestNs.toDouble() * harvestIso)
        val sunScene = dimScene * 64.0 // six stops brighter
        val lumas = mutableListOf<Double>()
        repeat(frames) {
            val (meteredNs, meteredIso) = meter.meteredPair()!!
            val plan = planExposure(rule, meteredNs, meteredIso, caps)
            val l = luma(sunScene, plan.exposureNs, plan.iso)
            lumas += l
            val credit = creditOf(plan)
            meter.onFrame(l, credit.first, credit.second)
        }
        return lumas
    }

    @Test
    fun creditingThePlanReconvergesAfterSixStopsOfSun() {
        val lumas = runLoop(40) { plan ->
            meterCreditedExposure(plan, harvestNs, harvestIso)!!
        }
        val settled = lumas.last()
        assertTrue(
            abs(settled - SceneMeter.TARGET_LUMA) < 20,
            "the loop should settle at the metering target; ended at luma=$settled " +
                "(walk: ${lumas.map { it.toInt() }})",
        )
    }

    @Test
    fun creditingTheFrozenHarvestPinsTheRunBright() {
        // The old precedence, kept runnable as the WHY of the order: the
        // meter reproduces the dead reading instead of the scene, and no
        // amount of frames brings the run back down.
        val lumas = runLoop(40) { harvestNs to harvestIso }
        val tail = lumas.takeLast(10)
        assertTrue(
            tail.all { it > 150.0 },
            "anchored to dead light the run never approaches the target; " +
                "last frames: ${tail.map { it.toInt() }}",
        )
    }
}

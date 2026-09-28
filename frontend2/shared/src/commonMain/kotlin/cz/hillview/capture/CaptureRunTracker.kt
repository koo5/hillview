package cz.hillview.capture

/**
 * Which capture RUN a photo belongs to — the identifier that makes a sequence
 * reassemblable, and the cheapest thing on the recon metadata list.
 *
 * WHY IT IS NEEDED, measured 2026-09-28. The IMU arrays tile exactly: consecutive
 * photos' owned windows are one sample period apart, with no sample lost, duplicated or
 * shared. But a photo's own array contains its own exposure in **1 case out of 86** —
 * the slice starts a median 2071 ms after the exposure, which sits four photos back at a
 * 0.75 s interval, because photo N owns `[end of N-1's claim, N's press + 3 s]` and N's
 * press is 3 s before that end.
 *
 * So anything that needs inertial samples AT the exposure — rolling-shutter
 * compensation, blur across the 20 ms the shutter was open — has to reassemble the run
 * first. And nothing said which photos formed one: adjacency was inferable only by
 * fetching each gzipped artifact and comparing `t0_ns`, i.e. by downloading the thing
 * you were trying to decide whether to download.
 *
 * WHAT A RUN IS, and why it is not "the interval session". The property a consumer
 * actually needs is CONTIGUOUS INERTIAL COVERAGE, and that is decided by arithmetic
 * rather than by which button was pressed: photo N's window opens at `press - half` and
 * photo N-1 stored up to `press(N-1) + half`, so coverage is continuous exactly while
 * consecutive presses are no more than `2 * half` apart. A manual shot three seconds
 * after another one tiles with it and belongs in the same run; two interval captures
 * either side of a long pause do not. The 4812.9 ms hole in the measured batch was
 * exactly this — a gap between bursts wider than the window.
 *
 * Which also means the id is a HINT about where to look, never a guarantee: the run can
 * still be broken by sensors that were not running. The arrays remain the proof, and a
 * consumer checks them; this only says which ones to fetch.
 *
 * Main-thread only, like the shutter it is driven from.
 */
class CaptureRunTracker(
    /**
     * The longest gap between presses that still leaves the windows touching — the full
     * window width, `2 * IMU_WINDOW_HALF_MS`. Passed in rather than imported because
     * that constant is Android-side and this logic is not.
     */
    private val gapMs: Long,
    private val newId: () -> String,
) {
    private var current: String? = null
    private var lastAtMs = 0L

    /**
     * The run id for a press at [atMs] — a MONOTONIC instant (`elapsedRealtime`), not
     * the wall clock, because a run is a stretch of uninterrupted recording and a user
     * changing their clock must not split or merge one.
     */
    fun idFor(atMs: Long): String {
        val id = current
        val continues = id != null && atMs - lastAtMs in 0..gapMs
        lastAtMs = atMs
        return if (continues) id!! else newId().also { current = it }
    }
}

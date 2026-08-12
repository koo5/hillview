package cz.hillview.capture

/** Tiny lock seam: commonMain has no `synchronized` (JVM-only stdlib). */
internal expect fun <T> statsLocked(block: () -> T): T

/**
 * In-app performance log (user-requested): the numbers that answer the
 * thermal-throughput questions — what a shot costs end to end, what a
 * preview restart costs (keeping the stream running vs periodic
 * restarts), how cadence holds up under heat. Process-lifetime; the
 * Stats dialog renders [snapshotText] as concise copyable text.
 */
object CaptureStatsLog {

    data class Metric(
        val count: Int = 0,
        val lastMs: Long = 0,
        val minMs: Long = Long.MAX_VALUE,
        val maxMs: Long = 0,
        val sumMs: Long = 0,
    ) {
        val avgMs: Long get() = if (count == 0) 0 else sumMs / count
    }

    private val metrics = LinkedHashMap<String, Metric>()
    private val counters = LinkedHashMap<String, Int>()
    private var windowStartMs: Long = 0

    /** Platform-supplied extra lines (thermal status etc.). */
    var platformLines: () -> List<String> = { emptyList() }

    fun record(name: String, ms: Long, nowMs: Long) = statsLocked {
        if (windowStartMs == 0L) windowStartMs = nowMs
        val m = metrics[name] ?: Metric()
        metrics[name] = Metric(
            count = m.count + 1,
            lastMs = ms,
            minMs = minOf(m.minMs, ms),
            maxMs = maxOf(m.maxMs, ms),
            sumMs = m.sumMs + ms,
        )
    }

    fun increment(name: String, nowMs: Long) = statsLocked {
        if (windowStartMs == 0L) windowStartMs = nowMs
        counters[name] = (counters[name] ?: 0) + 1
    }

    fun reset() = statsLocked {
        metrics.clear()
        counters.clear()
        windowStartMs = 0
    }

    fun snapshotText(nowMs: Long): String = statsLocked {
        buildString {
            val windowS = if (windowStartMs == 0L) 0 else (nowMs - windowStartMs) / 1000
            appendLine("window: ${windowS}s")
            metrics.forEach { (name, m) ->
                appendLine(
                    "$name: n=${m.count} last=${m.lastMs} " +
                        "avg=${m.avgMs} min=${m.minMs} max=${m.maxMs} ms"
                )
            }
            counters.forEach { (name, n) -> appendLine("$name: $n") }
            platformLines().forEach { appendLine(it) }
        }.trimEnd()
    }
}

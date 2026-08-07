package cz.hillview.map

/**
 * The map polls its marker sources on a fixed cadence; a source that hits
 * the network answers "is this poll news?" here — yes when the request key
 * changed (viewport moved, limit changed, pick changed, filters changed),
 * or when the window expired. Keeps the poll cadence from hammering the
 * backend's rate-limited endpoints with identical queries.
 */
class RefetchGate(private val windowMs: Long) {
    private var lastKey: String? = null
    private var lastAtMs = 0L

    fun shouldFetch(key: String, nowMs: Long): Boolean =
        key != lastKey || nowMs - lastAtMs >= windowMs

    /** Record only AFTER a fetch succeeds — a failed fetch must retry next poll. */
    fun recordFetch(key: String, nowMs: Long) {
        lastKey = key
        lastAtMs = nowMs
    }
}

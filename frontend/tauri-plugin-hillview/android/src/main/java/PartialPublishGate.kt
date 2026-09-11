package cz.hillview.plugin

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.coroutines.coroutineContext

/**
 * The publish policy for one area load — the same one the Svelte worker
 * (PARTIAL_PUBLISH_THROTTLE_MS) and frontend2 (CompositeMarkerSource) follow:
 *
 *  - the first source to land publishes at once (time-to-first-marker);
 *  - later arrivals are trailing-edge throttled to [throttleMs], so a stream
 *    delivering many small batches re-culls and redraws once per window;
 *  - [settle] (every source done) publishes immediately, dropping any pending
 *    partial, and nothing goes out after it — a partial can never trail the
 *    settled set.
 *
 * Cancelling [scope] (the area was superseded) drops a pending partial with it.
 * [publish] is never run concurrently with itself.
 */
class PartialPublishGate(
    private val scope: CoroutineScope,
    private val throttleMs: Long = DEFAULT_THROTTLE_MS,
    private val now: () -> Long = { System.currentTimeMillis() },
    private val publish: suspend (complete: Boolean) -> Unit
) {
    companion object {
        const val DEFAULT_THROTTLE_MS = 300L
    }

    private val lock = Any()
    private val publishing = Mutex()
    private var lastPublishAt: Long? = null
    private var pending: Job? = null
    private var settled = false

    /** A source landed (or a stream delivered a batch). */
    fun arrived() {
        synchronized(lock) {
            if (settled || pending != null) return
            val last = lastPublishAt
            val wait = if (last == null) 0L else (throttleMs - (now() - last)).coerceAtLeast(0L)
            // LAZY so `pending` is assigned before the body can run and clear it.
            val job = scope.launch(start = CoroutineStart.LAZY) {
                if (wait > 0) delay(wait)
                val me = coroutineContext[Job]
                val go = synchronized(lock) {
                    if (pending === me) pending = null
                    if (settled) false else { lastPublishAt = now(); true }
                }
                if (go) publishing.withLock { if (!settled) publish(false) }
            }
            pending = job
            job.start()
        }
    }

    /** Every source is done: the settled set goes out now, superseding any pending partial. */
    suspend fun settle() {
        val toCancel: Job?
        synchronized(lock) {
            settled = true
            toCancel = pending
            pending = null
            lastPublishAt = now()
        }
        toCancel?.cancel(CancellationException("superseded by the settled publish"))
        publishing.withLock { publish(true) }
    }
}

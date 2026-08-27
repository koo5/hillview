package cz.hillview.map

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.coroutines.coroutineContext

/**
 * Merges the device source with the backend source(s) into the one marker
 * list the map draws. A photo captured on this device and its uploaded twin
 * from the backend collapse by content hash — the backend copy wins, since
 * it carries what only the server knows (featured, analysis filtering,
 * everyone-visible identity).
 *
 * Sources load CONCURRENTLY and publish as they arrive: the merged list is
 * re-derived whenever any child's [PhotoMarkerSource.markers] changes, so a
 * device query that answers in a millisecond is on the map while the
 * backend stream is still connecting, and a slow or failing source never
 * holds the others back. The publish is throttled while sources are still
 * loading (first arrival immediately, then one trailing re-merge per
 * [PUBLISH_THROTTLE_MS]) and flushed the moment the last one settles — see
 * [loading].
 *
 * The merged set is then cut to the map's budget by [cull] — across all
 * sources, so MapSettings.maxPhotos is what gets drawn in total. Both steps
 * are pure functions of the children's current sets, so the final picture
 * does not depend on which source answered first.
 */
class CompositeMarkerSource(
    private val sources: List<PhotoMarkerSource>,
    /** Where the per-source fetches and the publish loop run; outlives any screen. */
    private val scope: CoroutineScope,
    private val cull: MarkerCuller = MarkerCuller.Plain,
    /** MapSettings.maxPhotos, read at each publish so a slider change re-culls. */
    private val maxPhotos: () -> Int = { Int.MAX_VALUE },
    private val publishThrottleMs: Long = PUBLISH_THROTTLE_MS,
) : PhotoMarkerSource {
    private val _markers = MutableStateFlow<List<PhotoMarker>>(emptyList())
    override val markers: StateFlow<List<PhotoMarker>> = _markers.asStateFlow()

    /** Ids of the sources with a fetch in flight; empty means settled. */
    private val _loading = MutableStateFlow<Set<String>>(emptySet())
    val loading: StateFlow<Set<String>> = _loading.asStateFlow()

    // The toggle panel's state (the original's per-source `enabled`): a
    // disabled child neither refreshes (no network spend) nor contributes
    // markers. Missing entries fall back to the descriptor's default.
    private val enabledOverrides = MutableStateFlow<Map<String, Boolean>>(emptyMap())

    private val viewport = MutableStateFlow<MapViewport?>(null)

    // "Something changed, publish" — conflated: however many arrivals land
    // during a cooldown, one trailing publish covers them all.
    private val changes = Channel<Unit>(Channel.CONFLATED)

    // One fetch job per source, keyed by the request it was started for.
    // Written only under [refreshLock] — the map has two callers of
    // refresh() (viewport settle, source toggle) that used to interleave —
    // and read by each job as it ends (a snapshot, hence the StateFlow), to
    // tell whether it is still the job of record for its source.
    private val jobs = MutableStateFlow<Map<String, Job>>(emptyMap())
    private val jobKeys = HashMap<String, String>()
    private val refreshLock = Mutex()

    private fun idOf(index: Int): String = sources[index].descriptor?.id ?: "source-$index"

    init {
        // A child's publish is news, whichever of its siblings is still busy.
        sources.forEach { source ->
            scope.launch { source.markers.collect { changes.trySend(Unit) } }
        }
        scope.launch { publishLoop() }
    }

    override fun sourceDescriptors(): List<MapSourceDescriptor> =
        sources.flatMap { it.sourceDescriptors() }

    override fun setSourceEnabled(id: String, enabled: Boolean) {
        enabledOverrides.update { it + (id to enabled) }
        // Hide/show from the children's cached sets — the next refresh()
        // only adds freshness (and stops spending on a disabled one).
        changes.trySend(Unit)
    }

    private fun isEnabled(source: PhotoMarkerSource): Boolean {
        val d = source.descriptor ?: return true
        return enabledOverrides.value[d.id] ?: d.defaultEnabled
    }

    override var pinnedId: String? = null
        set(value) {
            field = value
            sources.forEach { it.pinnedId = value }
            // The pin survives the cull; re-cut with it.
            changes.trySend(Unit)
        }

    override fun setViewport(viewport: MapViewport) {
        this.viewport.value = viewport
        sources.forEach { it.setViewport(viewport) }
        // The grid is laid over the viewport: re-cut what we have while the
        // fetches for the new area are on their way.
        changes.trySend(Unit)
    }

    /**
     * Start (or keep) a fetch for every enabled source, concurrently, and
     * wait for them. A source already fetching for the SAME viewport and pin
     * is left alone — a toggle mid-stream must not restart the stream; one
     * fetching for a stale request is cancelled and restarted. Returning is
     * "everything settled": the markers published along the way are already
     * on the map, so a caller that gets cancelled while waiting (the map's
     * collectLatest on viewport change) loses nothing — the fetches belong
     * to [scope], not to the caller, and the next refresh() replaces them.
     */
    override suspend fun refresh() {
        val cycle: List<Job> = refreshLock.withLock {
            val key = "${viewport.value}|$pinnedId"
            val started = ArrayList<Job>(sources.size)
            sources.forEachIndexed { index, source ->
                val id = idOf(index)
                val running = jobs.value[id]
                if (!isEnabled(source)) {
                    running?.cancel()
                    return@forEachIndexed
                }
                if (running != null && running.isActive && jobKeys[id] == key) {
                    started += running
                    return@forEachIndexed
                }
                running?.cancel()
                // Recorded as loading BEFORE it runs: a replaced job's exit
                // (see runSource) must never read as its successor settling.
                val job = scope.launch(start = CoroutineStart.LAZY) { runSource(id, source) }
                jobs.update { it + (id to job) }
                jobKeys[id] = key
                _loading.update { it + id }
                job.start()
                started += job
            }
            started
        }
        cycle.forEach { it.join() }
    }

    private suspend fun runSource(id: String, source: PhotoMarkerSource) {
        try {
            source.refresh()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            // Each source guards its own failures (a network hiccup must not
            // blank the device markers); this is the backstop for one that
            // did not — it keeps its last set and the others carry on.
        } finally {
            // Only the job of record settles its source; one cancelled and
            // replaced under the lock leaves the bookkeeping to its successor.
            val self = coroutineContext[Job]
            if (jobs.value[id] === self) {
                jobs.update { it - id }
                _loading.update { it - id }
            }
            // Settling is news too: it ends the cooldown early (see
            // publishLoop) and this token makes sure the final set is cut.
            changes.trySend(Unit)
        }
    }

    /**
     * The publish policy. Each change publishes at once, then holds a
     * cooldown during which further changes conflate into one trailing
     * publish — but only while something is loading: the cooldown ends the
     * moment the sources settle, so the final set is never held back, and
     * an idle map (toggles, pins) publishes without delay.
     */
    private suspend fun publishLoop() {
        for (change in changes) {
            publishNow()
            withTimeoutOrNull(publishThrottleMs) { _loading.first { it.isEmpty() } }
        }
    }

    private fun publishNow() {
        val perSource = LinkedHashMap<String, List<PhotoMarker>>()
        sources.forEachIndexed { index, source ->
            if (isEnabled(source)) perSource[idOf(index)] = source.markers.value
        }
        val collapsed = collapseTwins(perSource)
        val vp = viewport.value
        _markers.value = if (vp == null) {
            // Before the map has said where it looks there is nothing to lay
            // the grid over; the budget is the loaders' own per-source one.
            collapsed.values.flatten()
        } else {
            cull.cull(collapsed, vp, maxPhotos(), setOfNotNull(pinnedId))
        }
    }

    /**
     * The md5 collapse, per source so the cull still knows who is who: of
     * the markers sharing a content hash, exactly one survives, and a device
     * copy always yields to a backend one. Source order is fixed (the
     * constructor's list), so this too is independent of arrival order.
     */
    private fun collapseTwins(perSource: Map<String, List<PhotoMarker>>): Map<String, List<PhotoMarker>> {
        val winnersByMd5 = HashMap<String, PhotoMarker>()
        for (list in perSource.values) {
            for (marker in list) {
                val md5 = marker.fileMd5 ?: continue
                val current = winnersByMd5[md5]
                winnersByMd5[md5] = when {
                    current == null -> marker
                    current.source == "device" && marker.source != "device" -> marker
                    else -> current
                }
            }
        }
        return perSource.mapValues { (_, list) ->
            list.filter { marker ->
                val md5 = marker.fileMd5
                md5 == null || winnersByMd5[md5] === marker
            }
        }
    }

    companion object {
        /**
         * Re-merge cadence while sources are still arriving. Each publish is
         * a recomposition plus a full overlay repaint; ~3/s keeps a
         * multi-batch stream visibly filling in without redrawing per batch.
         */
        const val PUBLISH_THROTTLE_MS = 300L
    }
}

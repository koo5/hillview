package cz.hillview.plugin

import android.util.Log

/**
 * A ring of recent app events, readable IN the app.
 *
 * Everything interesting this app does is already logged — to logcat, which
 * is exactly where you cannot read it: on a phone, in a field, when the
 * question is "did an upload even get triggered in the last hour". This is
 * the same information with somewhere to land.
 *
 * Lives in shared-kt because the most interesting writer is the upload stack
 * itself, which cannot see the app module. Process-lifetime and in-memory:
 * it survives navigation, not a restart, which matches the questions it
 * answers ("what just happened", not "what happened on Tuesday").
 *
 * Deliberately over-shares for now — pruning is easy once it is clear which
 * lines earn their place, and a missing line is the expensive kind of error.
 */
object EventLog {

    /** Roughly a session's worth of interesting moments. */
    private const val CAPACITY = 500

    data class Event(
        val atMs: Long,
        val category: String,
        val message: String,
    )

    private val events = ArrayDeque<Event>(CAPACITY)

    /**
     * Record one. Also goes to logcat, so a tethered debug session sees the
     * same stream in the same order rather than two partial ones.
     */
    fun record(category: String, message: String) {
        val event = Event(System.currentTimeMillis(), category, message)
        synchronized(events) {
            if (events.size >= CAPACITY) events.removeFirst()
            events.addLast(event)
        }
        Log.i("🢄Event", "[$category] $message")
    }

    /** Newest first, which is the order anyone reads a log they are chasing. */
    fun snapshot(): List<Event> = synchronized(events) { events.toList() }.asReversed()

    fun categories(): List<String> =
        synchronized(events) { events.map { it.category }.distinct().sorted() }

    fun clear() {
        synchronized(events) { events.clear() }
    }
}

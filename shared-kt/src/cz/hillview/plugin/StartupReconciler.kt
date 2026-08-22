package cz.hillview.plugin

import android.content.Context
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

private const val TAG = "hv-StartupReconcile"

/**
 * What the app knows the instant it starts: **nothing from before is
 * running.** Every coroutine, worker and refinement that belonged to the
 * previous process died with it.
 *
 * That is a rare piece of certainty and it is worth spending, because the
 * alternative is deadlines. Deadlines exist for the times we cannot tell
 * whether something is still alive — and each one is a compromise between
 * freeing work early and stealing it from a process that is still using it.
 * At startup there is no such doubt, so anything that merely LOOKS in flight
 * can be reclaimed at once instead of waiting a timeout out:
 *
 *  - upload holds left by the stamp refiner (see StampRefiner.UPLOAD_HOLD_MS,
 *    a 60 s crash backstop) — released now, so the photo uploads immediately
 *    instead of a minute from now;
 *  - photos stuck in `uploading` (recovered by a 10-minute stale threshold)
 *    — handed back now, so a crash mid-upload costs seconds, not ten minutes.
 *
 * Deliberately NOT reset: `processing`. That status describes work the SERVER
 * is doing, which genuinely does outlive our process; PhotoStatusSyncWorker
 * reconciles it by asking.
 */
object StartupReconciler {

	/**
	 * @param processStart when this process began. An upload attempt older
	 * than this cannot belong to a live upload, because uploads run in-process.
	 * Pass the value captured in Application.onCreate, not "now" — by the time
	 * this runs a drain from THIS process may already have claimed something,
	 * and it must not be stolen back.
	 */
	fun run(context: Context, processStart: Long) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val dao = PhotoDatabase.getDatabase(context).photoDao()
				val holds = dao.clearAllUploadHolds()
				val uploads = dao.reclaimAbandonedUploads(processStart)
				if (holds > 0 || uploads > 0) {
					Log.i(
						TAG,
						"fresh start: released $holds refinement hold(s), " +
							"reclaimed $uploads abandoned upload(s)",
					)
				}
			} catch (e: Exception) {
				// Every one of these has a deadline behind it, so failing
				// here costs latency, never correctness.
				Log.w(TAG, "startup reconcile failed; deadlines will cover it", e)
			}

			// OUTSIDE that try on purpose. The rows just handed back are
			// waiting on nobody — the job uploading them died with the previous
			// process — so this launch is what parks a fresh one against the
			// current settings; without it a full queue can start the app with
			// no schedule at all, and the next capture is the only thing that
			// would notice.
			//
			// Which makes it the LAST thing that should be skipped because the
			// step above threw. It does throw in practice: the start-time geo
			// dump transacts on this same database, and losing the race costs a
			// SQLITE_BUSY on the reclaim — a latency problem that must not turn
			// into an unscheduled queue.
			PhotoUploadManager(context).reconcile("app_start")
		}
	}
}

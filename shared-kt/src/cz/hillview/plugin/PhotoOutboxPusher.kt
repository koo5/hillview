package cz.hillview.plugin

import android.content.Context
import android.util.Log
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/**
 * Carries the outbox across, one row at a time.
 *
 * It runs as a step inside the upload worker rather than as a schedule of its
 * own — docs/upload-one-funnel.md's rule is one scheduler and one drain, and
 * this is work that belongs to the same drain: it is owed to the same server,
 * about the same photos, and it becomes possible at the moment an upload
 * finishes.
 *
 * Every send is safe to repeat. The rating endpoint is unique per user and
 * photo, and a delete of something already deleted is a no-op the server
 * reports as gone. So a row that fails after the server acted simply gets
 * sent again, which is why nothing here has to be transactional with the
 * network.
 */
class PhotoOutboxPusher(
    private val context: Context,
    private val client: OkHttpClient,
    private val authManager: AuthenticationManager,
) {
    companion object {
        private const val TAG = "hv-PhotoOutboxPusher"

        /** One pass takes a bounded bite; the drain comes round again. */
        private const val BATCH = 50

        /** The wait after a failure, doubling, capped — the upload stack's shape. */
        private val BACKOFF_MS = longArrayOf(0, 30_000, 2 * 60_000, 10 * 60_000, 60 * 60_000)

        internal fun isDueNow(row: PhotoOutboxEntity, now: Long): Boolean {
            if (row.attempts <= 0) return true
            val wait = BACKOFF_MS[row.attempts.coerceAtMost(BACKOFF_MS.size - 1)]
            return now - row.lastAttemptAt >= wait
        }
    }

    private val database = PhotoDatabase.getDatabase(context.applicationContext)
    private val dao = database.outboxDao()
    private val photoDao = database.photoDao()

    /**
     * Push everything this account owes and can name.
     *
     * @return how many rows the server accepted.
     */
    fun pushAll(serverUrl: String): Int {
        val userId = PhotoOutbox.currentUserId(authManager) ?: return 0
        val now = System.currentTimeMillis()
        val due = dao.getPushable(userId, BATCH).filter { isDueNow(it, now) }
        if (due.isEmpty()) return 0
        Log.d(TAG, "pushing ${due.size} outbox row(s)")
        var sent = 0
        for (row in due) {
            if (push(row, serverUrl)) sent++
        }
        return sent
    }

    /**
     * The other half of deleting a photo that was caught mid-upload.
     *
     * Called the moment an upload writes its server id. Sent bytes cannot be
     * recalled, so a deletion asked for while the file was in flight cannot
     * be a cancellation; it becomes a post-condition instead — the photo
     * lands, and is deleted on the far side in the same breath. The window is
     * bounded by this call rather than by whenever the next drain happens to
     * run.
     */
    fun afterUpload(photoId: String, serverUrl: String) {
        val userId = PhotoOutbox.currentUserId(authManager) ?: return
        val row = dao.find(userId, photoId, OUTBOX_KIND_DELETE, "") ?: return
        if (row.valueJson == null || !row.dirty) return
        Log.i(TAG, "photo $photoId was deleted while it uploaded — deleting it server-side now")
        push(row, serverUrl)
    }

    private fun push(row: PhotoOutboxEntity, serverUrl: String): Boolean {
        val serverPhotoId = photoDao.getPhotoById(row.photoId)?.serverPhotoId ?: return false
        // Captured BEFORE the call: what comes back is judged against the
        // revision that was actually sent, so an edit made meanwhile keeps
        // the row dirty instead of being marked clean for a value the server
        // never saw.
        val sentRevision = row.revision
        return try {
            val ok = when (row.kind) {
                OUTBOX_KIND_RATING -> sendRating(row, serverPhotoId, serverUrl)
                OUTBOX_KIND_DELETE -> sendDelete(row, serverPhotoId, serverUrl)
                else -> {
                    // An unknown kind is a NEWER app's row after a downgrade,
                    // or a half-finished feature. Leave it dirty and untouched
                    // rather than dropping something a later version can send.
                    Log.w(TAG, "unknown outbox kind '${row.kind}' — left alone")
                    return false
                }
            }
            if (ok) {
                val cleared = dao.markSynced(
                    row.userId, row.photoId, row.kind, row.itemId, sentRevision,
                )
                if (cleared == 0) {
                    Log.d(TAG, "${row.kind} for ${row.photoId} changed mid-push — staying dirty")
                }
                true
            } else {
                dao.recordFailure(
                    row.userId, row.photoId, row.kind, row.itemId,
                    System.currentTimeMillis(), "server refused",
                )
                false
            }
        } catch (e: Exception) {
            Log.w(TAG, "push of ${row.kind} for ${row.photoId} failed", e)
            dao.recordFailure(
                row.userId, row.photoId, row.kind, row.itemId,
                System.currentTimeMillis(), e.message ?: e::class.java.simpleName,
            )
            false
        }
    }

    private fun sendRating(row: PhotoOutboxEntity, serverPhotoId: String, serverUrl: String): Boolean {
        val url = "$serverUrl/ratings/hillview/$serverPhotoId"
        val wanted = row.valueJson?.let { JSONObject(it).optString("rating") }?.takeIf { it.isNotEmpty() }
        val request = if (wanted == null) {
            // No rating wanted: withdraw it. A 404 means there was none to
            // withdraw, which is the state asked for — so it counts as done.
            authorized(Request.Builder().url(url).delete())
        } else {
            authorized(
                Request.Builder().url(url).post(
                    JSONObject().put("rating", wanted).toString()
                        .toRequestBody("application/json".toMediaType()),
                ),
            )
        } ?: return false
        return client.newCall(request).execute().use { response ->
            response.isSuccessful || (wanted == null && response.code == 404)
        }
    }

    private fun sendDelete(row: PhotoOutboxEntity, serverPhotoId: String, serverUrl: String): Boolean {
        if (row.valueJson == null) {
            // Withdrawn before it was ever sent: there is nothing to ask the
            // server for, and the gate that held the upload back is already
            // open again. Done by having nothing to do.
            return true
        }
        val request = authorized(
            Request.Builder().url("$serverUrl/photos/$serverPhotoId").delete(),
        ) ?: return false
        return client.newCall(request).execute().use { response ->
            // Already gone is the state we wanted.
            response.isSuccessful || response.code == 404
        }
    }

    private fun authorized(builder: Request.Builder): Request? {
        val token = authManager.getTokenInfo().first ?: run {
            Log.d(TAG, "no token — leaving the outbox alone")
            return null
        }
        return builder.addHeader("Authorization", "Bearer $token").build()
    }
}

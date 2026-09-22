package cz.hillview.plugin

import android.content.Context
import android.util.Base64
import android.util.Log
import org.json.JSONObject

/**
 * The one way to say "I want the server to know this about a photo".
 *
 * Everything a caller needs is here: state the wish, read it back, and never
 * touch [PhotoOutboxDao] directly. Reading it back matters as much as writing
 * it — a thumbs-up has to look pressed the instant it is pressed, hours
 * before any signal arrives, so the UI's source of truth is this and not the
 * server's answer.
 *
 * See [PhotoOutboxEntity] for why a row is a state rather than a message, and
 * PhotoOutboxPusher for what carries it across.
 */
class PhotoOutbox(context: Context) {

    private val database = PhotoDatabase.getDatabase(context.applicationContext)
    private val dao = database.outboxDao()
    private val authManager = AuthenticationManager(context.applicationContext)

    companion object {
        private const val TAG = "hv-PhotoOutbox"

        /**
         * The signed-in account id, read out of the access token's `sub`.
         *
         * Decoded, NOT verified, and that is fine because of what it is used
         * for: partitioning local rows so a like queued by one account is
         * never pushed as another. Authorization is the server's decision,
         * made from the token it is sent — never from this string.
         *
         * Null when signed out, which makes every write a no-op and every
         * row ineligible. Nothing is discarded; see the entity's note on
         * keying by user.
         */
        fun currentUserId(authManager: AuthenticationManager): String? {
            val token = authManager.getTokenInfo().first ?: return null
            return try {
                val payload = token.split(".").getOrNull(1) ?: return null
                val json = String(
                    Base64.decode(payload, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP),
                    Charsets.UTF_8,
                )
                JSONObject(json).optString("sub").takeIf { it.isNotEmpty() }
            } catch (e: Exception) {
                Log.w(TAG, "could not read the account id from the token", e)
                null
            }
        }
    }

    fun currentUserId(): String? = currentUserId(authManager)

    /**
     * Set (or clear) the wanted state for one kind, replacing whatever was
     * wanted before.
     *
     * The read and the write are one transaction: two taps racing must leave
     * one row with a revision that moved twice, not two rows or one lost
     * write.
     */
    fun want(photoId: String, kind: String, valueJson: String?, itemId: String = "") {
        val userId = currentUserId() ?: run {
            Log.w(TAG, "signed out — $kind for $photoId not recorded")
            return
        }
        val now = System.currentTimeMillis()
        database.runInTransaction {
            if (dao.find(userId, photoId, kind, itemId) == null) {
                dao.insert(
                    PhotoOutboxEntity(
                        userId = userId,
                        photoId = photoId,
                        kind = kind,
                        itemId = itemId,
                        valueJson = valueJson,
                        changedAt = now,
                    ),
                )
            } else {
                dao.setWanted(userId, photoId, kind, itemId, valueJson, now)
            }
        }
    }

    /** `"thumbs_up"`, `"thumbs_down"`, or null to take the rating back. */
    fun setRating(photoId: String, rating: String?) {
        want(
            photoId,
            OUTBOX_KIND_RATING,
            rating?.let { JSONObject().put("rating", it).toString() },
        )
    }

    /**
     * What the user has said about this photo's rating, whether or not the
     * server has heard yet. Null = no rating wanted.
     */
    fun ratingOf(photoId: String): String? {
        val userId = currentUserId() ?: return null
        val row = dao.find(userId, photoId, OUTBOX_KIND_RATING, "") ?: return null
        val value = row.valueJson ?: return null
        return try {
            JSONObject(value).optString("rating").takeIf { it.isNotEmpty() }
        } catch (e: Exception) {
            null
        }
    }

    /**
     * "Delete this photo from the server."
     *
     * Two halves, and only one of them is here. A photo that has not been
     * uploaded stops being an upload candidate the moment this row exists
     * (the gate in SimplePhotoDao), so it is never sent. One that HAS been
     * uploaded gets the API call from the pusher. A photo caught mid-upload
     * gets both: the bytes land, and the pusher deletes on the far side as
     * soon as the server id exists — see PhotoOutboxPusher.afterUpload.
     */
    fun wantDeleted(photoId: String, wanted: Boolean = true) {
        want(
            photoId,
            OUTBOX_KIND_DELETE,
            if (wanted) JSONObject().toString() else null,
        )
    }

    fun isDeletionWanted(photoId: String): Boolean {
        val userId = currentUserId() ?: return false
        return dao.find(userId, photoId, OUTBOX_KIND_DELETE, "")?.valueJson != null
    }

    /** How much this account still owes the server. */
    fun pendingCount(): Int = currentUserId()?.let { dao.pendingCount(it) } ?: 0
}

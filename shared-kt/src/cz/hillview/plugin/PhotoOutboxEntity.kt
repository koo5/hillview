package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.ForeignKey
import androidx.room.Index

/**
 * What this client wants the SERVER to know about a photo, and has not told it
 * yet.
 *
 * The problem it exists for: a rating, a description, a tag, a voice note, a
 * deletion — things the client would otherwise just call the API for, except
 * that the phone is in a field with no signal, or the photo has not been
 * uploaded yet and so has no server id to name it by. They have to survive
 * both, and they have to arrive exactly once eventually.
 *
 * ## A row is a STATE, not a message
 *
 * This is the decision the whole design rests on. An outbox of MESSAGES would
 * have to keep "liked at 9:01, unliked at 9:02, liked at 9:03" in order, send
 * all three, and cope with the second failing while the third succeeds. An
 * outbox of STATES keys on (user, photo, kind, item) and REPLACES in place, so
 * those three writes leave one row saying "liked" and one call to make.
 * Retrying is free, arriving twice is harmless, and order stops mattering.
 *
 * It works because the APIs this feeds are idempotent by that same key: a
 * rating is unique per user and photo, a description is a scalar, a tag set is
 * a set, a deletion is terminal. [itemId] carries the ones that are genuinely
 * multi-valued (a voice note among several), where "removed" is just another
 * state rather than a different kind of record.
 *
 * ## revision / syncedRevision, not timestamps
 *
 * [revision] rises on every local write; [syncedRevision] records what the
 * server last accepted. Dirty is `syncedRevision < revision`, one comparison.
 * The pusher captures the revision it sent and clears only if it has not
 * moved (PhotoOutboxDao.markSynced), so an edit made WHILE a push is in
 * flight leaves the row dirty instead of being marked clean for a value that
 * was never sent. Two timestamps cannot do that: two edits inside one
 * millisecond, or a clock that steps, and the compare-and-set silently
 * becomes a compare-and-lose.
 *
 * ## Keyed by user, never purged
 *
 * [userId] is part of the key (user-decided, 2026-09-17: "the actions should
 * be keyed by user, no purging"). Signing out leaves the rows alone; they are
 * simply not eligible while somebody else is signed in, and they resume if
 * that account comes back. A like queued as one account can never be pushed
 * as another, which is the whole hazard a shared queue would have.
 *
 * ## Its relationship with the photo row
 *
 * The FK cascades, so this holds only for photos this device still knows
 * about — which is the right lifetime, because a push needs the
 * `serverPhotoId` that lives over there. Local rows are TOMBSTONED (the
 * `deleted` flag) rather than removed, so the cascade does not fire in
 * ordinary use; a path that hard-deletes a photo row is also discarding
 * whatever this had left to say about it.
 *
 * Note what this is NOT: `PhotoEntity.deleted` is what the SERVER says, an
 * observation. A wanted deletion is a row here, an intention. Collapsing the
 * two would let a status sync reporting "not deleted" quietly cancel a
 * deletion the user asked for while offline.
 */
@Entity(
    tableName = "photo_outbox",
    primaryKeys = ["userId", "photoId", "kind", "itemId"],
    foreignKeys = [
        ForeignKey(
            entity = PhotoEntity::class,
            parentColumns = ["id"],
            childColumns = ["photoId"],
            onDelete = ForeignKey.CASCADE,
        ),
    ],
    indices = [
        // The drain's join, and the "is a deletion wanted for this photo"
        // test the upload candidate query runs.
        Index(value = ["photoId"], name = "idx_outbox_photo_id"),
        Index(value = ["userId", "changedAt"], name = "idx_outbox_user_changed"),
    ],
)
data class PhotoOutboxEntity(
    /**
     * The account this belongs to — the access token's `sub`.
     *
     * A LOCAL partition key and nothing more: it decides which rows are
     * eligible while a given account is signed in. It is never an
     * authorization decision, which is the server's business and is made from
     * the token it is sent, not from this string.
     */
    val userId: String,
    val photoId: String,

    /** [OUTBOX_KIND_RATING], [OUTBOX_KIND_DELETE], or whatever comes next. */
    val kind: String,

    /** Empty for the singular kinds; the item's own id for multi-valued ones. */
    val itemId: String = "",

    /**
     * The wanted state, as JSON the [kind] defines — or null, which MEANS
     * "wanted absent" (no rating, note removed). Opaque here on purpose: this
     * table stores states, it does not interpret them.
     */
    val valueJson: String? = null,

    val revision: Long = 1,
    val syncedRevision: Long = 0,
    val changedAt: Long,

    // Failure bookkeeping, for backoff and for showing a stuck row.
    val attempts: Int = 0,
    val lastAttemptAt: Long = 0,
    val lastError: String = "",
) {
    val dirty: Boolean get() = syncedRevision < revision
}

/** A thumbs up/down on a photo: `{"rating":"thumbs_up"}`, or null for none. */
const val OUTBOX_KIND_RATING = "rating"

/**
 * "Delete this from the server." `{}` means wanted; null means withdrawn.
 *
 * Withdrawal only means anything BEFORE the push: once the server has deleted
 * the photo there is nothing to take back, and the row stays as the record
 * that it happened.
 */
const val OUTBOX_KIND_DELETE = "delete"

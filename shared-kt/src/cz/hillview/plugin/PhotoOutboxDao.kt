package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface PhotoOutboxDao {

    @Query(
        """
        SELECT * FROM photo_outbox
        WHERE userId = :userId AND photoId = :photoId AND kind = :kind AND itemId = :itemId
        """,
    )
    fun find(userId: String, photoId: String, kind: String, itemId: String): PhotoOutboxEntity?

    @Insert(onConflict = OnConflictStrategy.ABORT)
    fun insert(row: PhotoOutboxEntity)

    /**
     * Replace the wanted state in place and move the revision on.
     *
     * The revision is bumped HERE rather than passed in, so two writers
     * cannot compute the same next value from the same stale read.
     */
    @Query(
        """
        UPDATE photo_outbox
        SET valueJson = :valueJson, revision = revision + 1, changedAt = :now,
            attempts = 0, lastAttemptAt = 0, lastError = ''
        WHERE userId = :userId AND photoId = :photoId AND kind = :kind AND itemId = :itemId
        """,
    )
    fun setWanted(
        userId: String,
        photoId: String,
        kind: String,
        itemId: String,
        valueJson: String?,
        now: Long,
    )

    /**
     * Rows this account still owes the server, oldest intent first.
     *
     * The join is the eligibility gate: a photo with no `serverPhotoId` has
     * nothing for the API to name, so its rows are simply not selected. When
     * the upload lands the id they become selectable, with no ordering
     * machinery and nothing to wake up — the same shape `uploadHoldUntil`
     * gives the file drain.
     *
     * Backoff is left to the caller (see isEligibleNow's use in the upload
     * loop): the SQL says what is owed, Kotlin says what is due.
     */
    @Query(
        """
        SELECT o.* FROM photo_outbox o
        JOIN photos p ON p.id = o.photoId
        WHERE o.userId = :userId
          AND o.syncedRevision < o.revision
          AND p.serverPhotoId IS NOT NULL
        ORDER BY o.changedAt ASC
        LIMIT :limit
        """,
    )
    fun getPushable(userId: String, limit: Int): List<PhotoOutboxEntity>

    /**
     * Mark accepted — but only the revision that was actually sent.
     *
     * `revision = :sentRevision` is the whole point. A local edit made while
     * the push was in flight has already moved the revision, so this matches
     * nothing and the row stays dirty for the next pass, instead of being
     * called clean for a value the server never saw.
     */
    @Query(
        """
        UPDATE photo_outbox
        SET syncedRevision = :sentRevision, attempts = 0, lastError = ''
        WHERE userId = :userId AND photoId = :photoId AND kind = :kind AND itemId = :itemId
          AND revision = :sentRevision
        """,
    )
    fun markSynced(
        userId: String,
        photoId: String,
        kind: String,
        itemId: String,
        sentRevision: Long,
    ): Int

    @Query(
        """
        UPDATE photo_outbox
        SET attempts = attempts + 1, lastAttemptAt = :now, lastError = :error
        WHERE userId = :userId AND photoId = :photoId AND kind = :kind AND itemId = :itemId
        """,
    )
    fun recordFailure(
        userId: String,
        photoId: String,
        kind: String,
        itemId: String,
        now: Long,
        error: String,
    )

    /** Everything wanted for one photo, for the UI to read its own state back. */
    @Query("SELECT * FROM photo_outbox WHERE userId = :userId AND photoId = :photoId")
    fun forPhoto(userId: String, photoId: String): List<PhotoOutboxEntity>

    @Query("SELECT COUNT(*) FROM photo_outbox WHERE userId = :userId AND syncedRevision < revision")
    fun pendingCount(userId: String): Int

    /** Rows for accounts that are not the one signed in — kept, never pushed. */
    @Query("SELECT COUNT(*) FROM photo_outbox WHERE userId != :userId")
    fun otherAccountCount(userId: String): Int
}

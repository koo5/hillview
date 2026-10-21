package cz.hillview.plugin

import androidx.sqlite.db.SupportSQLiteDatabase
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey
import androidx.room.RoomDatabase

// No foreign key: a physical deletion must leave a pending tombstone.
@Entity(
    tableName = "photo_export_changes",
    indices = [Index(value = ["changeId"], name = "idx_photo_export_changes_change_id")],
)
internal data class PhotoExportChangeEntity(
    @PrimaryKey val photoId: String,
    val changeId: Long,
)

@Entity(tableName = "photo_export_sequence")
internal data class PhotoExportSequenceEntity(
    @PrimaryKey val id: Int,
    val value: Long,
)

/**
 * Durable, coalesced change tracking for the public photo-table export.
 *
 * The triggers cover every Room update path, including raw UPDATE queries and
 * physical deletes. One pending row per photo is enough: the exporter reads the
 * latest photo state, and each change ID lets it acknowledge a snapshot without
 * erasing a newer edit that arrived while the file was being written.
 */
internal object PhotoExportChangeTracking {
    val callback = object : RoomDatabase.Callback() {
        override fun onCreate(db: SupportSQLiteDatabase) {
            create(db, seedExistingPhotos = false)
        }
    }

    fun create(db: SupportSQLiteDatabase, seedExistingPhotos: Boolean) {
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS photo_export_sequence (" +
                "id INTEGER PRIMARY KEY NOT NULL, value INTEGER NOT NULL)",
        )
        db.execSQL(
            "INSERT OR IGNORE INTO photo_export_sequence(id, value) VALUES (1, 0)",
        )
        db.execSQL(
            "CREATE TABLE IF NOT EXISTS photo_export_changes (" +
                "photoId TEXT NOT NULL PRIMARY KEY, changeId INTEGER NOT NULL)",
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS idx_photo_export_changes_change_id " +
                "ON photo_export_changes(changeId)",
        )

        db.execSQL("DROP TRIGGER IF EXISTS photos_export_insert")
        db.execSQL("DROP TRIGGER IF EXISTS photos_export_update")
        db.execSQL("DROP TRIGGER IF EXISTS photos_export_delete")
        db.execSQL("""
            CREATE TRIGGER photos_export_insert AFTER INSERT ON photos BEGIN
                UPDATE photo_export_sequence SET value = value + 1 WHERE id = 1;
                INSERT OR REPLACE INTO photo_export_changes(photoId, changeId)
                    SELECT NEW.id, value FROM photo_export_sequence WHERE id = 1;
            END
        """.trimIndent())
        db.execSQL("""
            CREATE TRIGGER photos_export_update AFTER UPDATE ON photos BEGIN
                UPDATE photo_export_sequence SET value = value + 1 WHERE id = 1;
                INSERT OR REPLACE INTO photo_export_changes(photoId, changeId)
                    SELECT OLD.id, value FROM photo_export_sequence WHERE id = 1;
                UPDATE photo_export_sequence SET value = value + 1
                    WHERE id = 1 AND OLD.id != NEW.id;
                INSERT OR REPLACE INTO photo_export_changes(photoId, changeId)
                    SELECT NEW.id, value FROM photo_export_sequence
                    WHERE id = 1 AND OLD.id != NEW.id;
            END
        """.trimIndent())
        db.execSQL("""
            CREATE TRIGGER photos_export_delete AFTER DELETE ON photos BEGIN
                UPDATE photo_export_sequence SET value = value + 1 WHERE id = 1;
                INSERT OR REPLACE INTO photo_export_changes(photoId, changeId)
                    SELECT OLD.id, value FROM photo_export_sequence WHERE id = 1;
            END
        """.trimIndent())

        if (seedExistingPhotos) {
            // An upgraded install has a previously exported snapshot, but no
            // change ledger. Queue its current rows once to establish the new
            // append-only format. Later exports process only the pending IDs.
            // rowid is unique and stable for this one-time seed. Starting the
            // sequence at its maximum keeps every seed row ordered before all
            // post-migration trigger events, which makes crash recovery able to
            // acknowledge a complete file prefix without skipping a seed row.
            db.execSQL(
                "UPDATE photo_export_sequence SET value = " +
                    "(SELECT IFNULL(MAX(rowid), 0) FROM photos) WHERE id = 1",
            )
            db.execSQL(
                "INSERT OR REPLACE INTO photo_export_changes(photoId, changeId) " +
                    "SELECT id, rowid FROM photos",
            )
        }
    }
}

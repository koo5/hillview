package cz.hillview.plugin

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
@Database(
    entities = [PhotoEntity::class, BearingEntity::class],
    version = 7,
    exportSchema = false
)
abstract class PhotoDatabase : RoomDatabase() {

    abstract fun photoDao(): SimplePhotoDao
    abstract fun bearingDao(): BearingDao

    companion object {
        @Volatile
        private var INSTANCE: PhotoDatabase? = null

        private val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(database: SupportSQLiteDatabase) {
                // Rename timestamp column to capturedAt
                database.execSQL("ALTER TABLE photos RENAME COLUMN timestamp TO capturedAt")
            }
        }

        fun getDatabase(context: Context): PhotoDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    PhotoDatabase::class.java,
                    "hillview_photos_database"
                )
                    .addMigrations(MIGRATION_6_7)
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}

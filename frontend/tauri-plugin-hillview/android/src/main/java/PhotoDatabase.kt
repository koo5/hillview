package io.github.koo5.hillview.plugin

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
@Database(
    entities = [PhotoEntity::class],
    version = 2,
    exportSchema = false
)
abstract class PhotoDatabase : RoomDatabase() {
    
    abstract fun photoDao(): SimplePhotoDao
    
    companion object {
        @Volatile
        private var INSTANCE: PhotoDatabase? = null
        
        fun getDatabase(context: Context): PhotoDatabase {
            return INSTANCE ?: synchronized(this) {
                val instance = Room.databaseBuilder(
                    context.applicationContext,
                    PhotoDatabase::class.java,
                    "hillview_photos_database"
                )
                    .fallbackToDestructiveMigration() // Since no users yet
                    .build()
                INSTANCE = instance
                instance
            }
        }
    }
}
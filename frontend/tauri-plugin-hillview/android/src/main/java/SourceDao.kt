package cz.hillview.plugin

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface SourceDao {

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    fun insertSource(source: SourceEntity): Long

    @Query("SELECT id FROM sources WHERE name = :name")
    fun getSourceIdByName(name: String): Int?

    @Query("INSERT OR IGNORE INTO sources (name) VALUES (:name)")
    fun insertSourceByName(name: String)

    fun getOrCreateSourceId(name: String): Int {
        insertSourceByName(name)
        return getSourceIdByName(name) ?: throw IllegalStateException("Failed to get source ID for $name")
    }

    @Query("SELECT * FROM sources")
    fun getAllSources(): List<SourceEntity>

    @Query("SELECT name FROM sources WHERE id = :id")
    fun getSourceNameById(id: Int): String?

}
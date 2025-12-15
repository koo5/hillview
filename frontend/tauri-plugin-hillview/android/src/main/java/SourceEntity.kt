package cz.hillview.plugin

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "sources",
    indices = [Index(value = ["name"], unique = true)]
)
data class SourceEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Int = 0,
    val name: String
)
package cz.hillview.plugin

import android.util.Log

/**
 * Culling Grid - Smart Photo Selection for Screen Coverage
 *
 * Faithful translation of CullingGrid.ts from TypeScript to Kotlin.
 * Ensures uniform visual distribution across the screen by:
 * 1. Creating a 10x10 virtual grid over the current viewport bounds
 * 2. Round-robin selection: For each source → For each screen cell → Take 1 photo
 * 3. Continue until the limit is reached
 *
 * This prevents visual clustering and ensures good screen coverage across all
 * visible areas, giving users a well-distributed overview of the entire viewport.
 */
class CullingGrid(private val bounds: Bounds) {
    companion object {
        private const val TAG = "CullingGrid"
        private const val GRID_SIZE = 10

        // Source priority levels (lower number = higher priority) - matching TypeScript
        private val SOURCE_PRIORITY = mapOf<SourceId, Priority>(
            "device" to 1,
            "hillview" to 2,
            "other" to 3,
            "mapillary" to 4
        )
    }

    private val latRange: Double = bounds.top_left.lat - bounds.bottom_right.lat
    private val lngRange: Double = bounds.bottom_right.lng - bounds.top_left.lng

    /**
     * Apply priority-based culling with hash deduplication and lazy evaluation
     * Direct translation from TypeScript CullingGrid.cullPhotos()
     */
    fun cullPhotos(photosPerSource: Map<SourceId, List<PhotoData>>, maxPhotos: Int): List<PhotoData> {
        if (photosPerSource.isEmpty() || maxPhotos <= 0) {
            return emptyList()
        }

        Log.d(TAG, "Starting culling with ${photosPerSource.values.sumOf { it.size }} total photos, maxPhotos: $maxPhotos")

        // Create grid cells map
        val gridCells = mutableMapOf<CellKey, CellPhotos>()

        // Sort sources by priority (device first, mapillary last)
        val sortedSources = photosPerSource.keys.sortedBy { sourceId ->
            SOURCE_PRIORITY[sourceId] ?: Int.MAX_VALUE
        }

        Log.d(TAG, "Processing sources in priority order: $sortedSources")

        // Populate grid cells with photos from each source
        for (sourceId in sortedSources) {
            val photos = photosPerSource[sourceId] ?: continue

            for (photo in photos) {
                val cellKey = getCellKey(photo.coord)

                // Get or create cell
                val cellPhotos = gridCells.getOrPut(cellKey) {
                    CellPhotos(mutableListOf(), mutableMapOf())
                }

                // Check for duplicates using file hash
                val shouldSkip = photo.fileHash?.let { hash ->
                    cellPhotos.hashToIndex.containsKey(hash)
                } ?: false

                if (shouldSkip) {
                    continue // Skip duplicate photo
                }

                // Add hash mapping if present
                photo.fileHash?.let { hash ->
                    cellPhotos.hashToIndex[hash] = cellPhotos.photos.size
                }

                cellPhotos.photos.add(photo)
            }
        }

        Log.d(TAG, "Populated ${gridCells.size} grid cells")

        // Round-robin selection across all cells
        val result = mutableListOf<PhotoData>()
        val cellIterators = gridCells.values.map { it.photos.iterator() }.toMutableList()
        var roundNumber = 0

        while (result.size < maxPhotos && cellIterators.isNotEmpty()) {
            roundNumber++
            val iteratorsToRemove = mutableListOf<Int>()

            for (i in cellIterators.indices.reversed()) {
                if (result.size >= maxPhotos) break

                val iterator = cellIterators[i]
                if (iterator.hasNext()) {
                    result.add(iterator.next())
                } else {
                    iteratorsToRemove.add(i)
                }
            }

            // Remove exhausted iterators
            for (index in iteratorsToRemove) {
                cellIterators.removeAt(index)
            }
        }

        Log.d(TAG, "Culling completed: selected ${result.size} photos from ${gridCells.size} cells in $roundNumber rounds")

        return result
    }

    /**
     * Calculate grid cell key for a coordinate
     * Direct translation from TypeScript implementation
     */
    private fun getCellKey(coord: LatLng): CellKey {
        val row = ((bounds.top_left.lat - coord.lat) / latRange * GRID_SIZE).toInt()
            .coerceIn(0, GRID_SIZE - 1)

        val col = ((coord.lng - bounds.top_left.lng) / lngRange * GRID_SIZE).toInt()
            .coerceIn(0, GRID_SIZE - 1)

        return "$row,$col"
    }

    /**
     * Cell photos container with duplicate detection
     */
    private data class CellPhotos(
        val photos: MutableList<PhotoData>,
        val hashToIndex: MutableMap<FileHash, PhotoIndex>
    )
}
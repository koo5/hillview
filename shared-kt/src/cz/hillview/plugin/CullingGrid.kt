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
     *
     * @param picks - Set of photo IDs that must always be included (e.g., currently selected photo)
     */
    fun cullPhotos(photosPerSource: Map<SourceId, List<PhotoData>>, maxPhotos: Int, picks: Set<String> = emptySet()): List<PhotoData> {
        if (photosPerSource.isEmpty() || maxPhotos <= 0) {
            return emptyList()
        }

        Log.d(TAG, "Starting culling with ${photosPerSource.values.sumOf { it.size }} total photos, maxPhotos: $maxPhotos, picks: ${picks.size}")

        // First, extract picked photos - they are always included
        // picks contains UIDs like "hillview-abc123"
        val pickedPhotos = mutableListOf<PhotoData>()
        val pickedUids = mutableSetOf<String>()

        if (picks.isNotEmpty()) {
            for (photos in photosPerSource.values) {
                for (photo in photos) {
                    if (picks.contains(photo.uid) && !pickedUids.contains(photo.uid)) {
                        pickedPhotos.add(photo)
                        pickedUids.add(photo.uid)
                    }
                }
            }
        }

        // Calculate remaining slots after picks
        val remainingSlots = maxPhotos - pickedPhotos.size
        if (remainingSlots <= 0) {
            Log.d(TAG, "${pickedPhotos.size} picked photos fill the limit of $maxPhotos")
            return pickedPhotos.take(maxPhotos)
        }

        // Create grid cells map
        val gridCells = mutableMapOf<CellKey, CellPhotos>()

        // Sort sources by priority (device first, mapillary last)
        val sortedSources = photosPerSource.keys.sortedBy { sourceId ->
            SOURCE_PRIORITY[sourceId] ?: Int.MAX_VALUE
        }

        Log.d(TAG, "Processing sources in priority order: $sortedSources")

        // Populate grid cells with photos from each source
        // Exclude already picked photos
        for (sourceId in sortedSources) {
            val sourcePhotos = photosPerSource[sourceId] ?: continue

            // Device source: sort by most recent first so that when a cell is over-populated,
            // the round-robin selection keeps the most recent photos.
            val photos = if (sourceId == "device") {
                sourcePhotos.sortedByDescending { it.captured_at ?: 0L }
            } else {
                sourcePhotos
            }

            for (photo in photos) {
                // Skip already picked photos
                if (pickedUids.contains(photo.uid)) continue

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
        val regularPhotos = mutableListOf<PhotoData>()
        val cellIterators = gridCells.values.map { it.photos.iterator() }.toMutableList()
        var roundNumber = 0

        while (regularPhotos.size < remainingSlots && cellIterators.isNotEmpty()) {
            roundNumber++
            val iteratorsToRemove = mutableListOf<Int>()

            for (i in cellIterators.indices.reversed()) {
                if (regularPhotos.size >= remainingSlots) break

                val iterator = cellIterators[i]
                if (iterator.hasNext()) {
                    regularPhotos.add(iterator.next())
                } else {
                    iteratorsToRemove.add(i)
                }
            }

            // Remove exhausted iterators
            for (index in iteratorsToRemove) {
                cellIterators.removeAt(index)
            }
        }

        // Combine picked photos first, then regular photos
        val result = pickedPhotos + regularPhotos

        Log.d(TAG, "Culling completed: ${pickedPhotos.size} picks + ${regularPhotos.size} culled = ${result.size} photos from ${gridCells.size} cells in $roundNumber rounds")

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
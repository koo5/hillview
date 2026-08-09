package cz.hillview.plugin

import android.util.Log
import kotlin.math.*

/**
 * Angular Range Culler - Ensures uniform angular coverage around user position
 *
 * Faithful translation of AngularRangeCuller.ts from TypeScript to Kotlin.
 * Creates 36 angular buckets (10 degrees each, 0-360°) and uses round-robin
 * selection to ensure the user can "look" in all directions within range.
 *
 * Uses the photo's existing bearing property (camera direction) for bucketing.
 */
class AngularRangeCuller {
    companion object {
        private const val TAG = "AngularRangeCuller"
        private const val doLog = false
        private const val ANGULAR_BUCKETS = 36 // 10 degrees each
        private const val DEGREES_PER_BUCKET = 360.0 / ANGULAR_BUCKETS
    }

    /**
     * Cull photos for uniform angular coverage around center point
     * Direct translation from TypeScript implementation
     *
     * @param picks - Set of photo IDs that must always be included (e.g., currently selected photo)
     */
    fun cullPhotosInRange(
        photosInArea: List<PhotoData>,
        center: LatLng,
        range: Double,
        maxPhotos: Int,
        picks: Set<String> = emptySet()
    ): List<PhotoData> {
        if (photosInArea.isEmpty() || maxPhotos <= 0) {
            return emptyList()
        }

        if (doLog) Log.d(TAG, "Starting angular range culling with ${photosInArea.size} photos, range: ${range}m, maxPhotos: $maxPhotos, picks: ${picks.size}")

        // First, extract picked photos that are in range - they are always included
        // picks contains UIDs like "hillview-abc123"
        val pickedPhotos = mutableListOf<PhotoData>()
        val pickedUids = mutableSetOf<String>()

        if (picks.isNotEmpty()) {
            for (photo in photosInArea) {
                if (picks.contains(photo.uid) && !pickedUids.contains(photo.uid)) {
                    val distance = calculateDistance(center.lat, center.lng, photo.coord.lat, photo.coord.lng)
                    if (distance <= range) {
                        pickedPhotos.add(photo.copy(range_distance = distance))
                        pickedUids.add(photo.uid)
                    }
                }
            }
        }

        // Calculate remaining slots after picks
        val remainingSlots = maxPhotos - pickedPhotos.size
        if (remainingSlots <= 0) {
            return pickedPhotos.take(maxPhotos)
        }

        // Create angular buckets and filter photos within range
        // Exclude already picked photos
        val buckets = Array(ANGULAR_BUCKETS) { mutableListOf<PhotoData>() }

        for (photo in photosInArea) {
            // Skip already picked photos
            if (pickedUids.contains(photo.uid)) continue

            val distance = calculateDistance(center.lat, center.lng, photo.coord.lat, photo.coord.lng)

            if (distance <= range) {
                val bucketIndex = getBucketIndex(photo.bearing)
                buckets[bucketIndex].add(
                    photo.copy(range_distance = distance)
                )
            }
        }

        // Remove empty buckets initially
        val activeBuckets = buckets.filter { it.isNotEmpty() }.toMutableList()

        if (activeBuckets.isEmpty()) {
            if (doLog) Log.d(TAG, "No regular photos within range of ${range}m, returning ${pickedPhotos.size} picks")
            return pickedPhotos
        }

        if (doLog) Log.d(TAG, "Found photos in ${activeBuckets.size} angular buckets out of $ANGULAR_BUCKETS")

        // Round-robin: outer loop = rounds, inner loop = buckets (exact match to TypeScript)
        val regularPhotos = mutableListOf<PhotoData>()

        for (round in 0 until Int.MAX_VALUE) {
            if (activeBuckets.isEmpty() || regularPhotos.size >= remainingSlots) break

            var bucketIndex = 0

            while (bucketIndex < activeBuckets.size && regularPhotos.size < remainingSlots) {
                // Remove exhausted bucket if no photo at this round
                if (round >= activeBuckets[bucketIndex].size) {
                    // Swap with last and remove (like TypeScript implementation)
                    if (bucketIndex < activeBuckets.size - 1) {
                        activeBuckets[bucketIndex] = activeBuckets[activeBuckets.lastIndex]
                    }
                    activeBuckets.removeAt(activeBuckets.lastIndex)
                    // Don't increment bucketIndex - check the swapped bucket
                } else {
                    // Take photo and move to next bucket
                    regularPhotos.add(activeBuckets[bucketIndex][round])
                    bucketIndex++
                }
            }
        }

        // Combine picked photos first, then regular photos
        val result = pickedPhotos + regularPhotos

        if (doLog) Log.d(TAG, "Angular range culling completed: ${pickedPhotos.size} picks + ${regularPhotos.size} culled = ${result.size} photos")

        return result
    }

    /**
     * Get bucket index for a bearing (0-360 degrees)
     * Direct translation from TypeScript implementation
     */
    private fun getBucketIndex(bearing: Double): Int {
        val normalizedBearing = normalizeBearing(bearing)
        return (normalizedBearing / DEGREES_PER_BUCKET).toInt().coerceIn(0, ANGULAR_BUCKETS - 1)
    }

    /**
     * Normalize bearing to 0-360 range
     * Translation from bearingUtils.ts
     */
    private fun normalizeBearing(bearing: Double): Double {
        var normalized = bearing % 360.0
        if (normalized < 0) {
            normalized += 360.0
        }
        return normalized
    }

    /**
     * Calculate distance between two points using Haversine formula
     * Translation from workerUtils.ts calculateDistance function
     */
    private fun calculateDistance(lat1: Double, lng1: Double, lat2: Double, lng2: Double): Double {
        val R = 6371000.0 // Earth's radius in meters

        val φ1 = Math.toRadians(lat1)
        val φ2 = Math.toRadians(lat2)
        val Δφ = Math.toRadians(lat2 - lat1)
        val Δλ = Math.toRadians(lng2 - lng1)

        val a = sin(Δφ / 2) * sin(Δφ / 2) +
                cos(φ1) * cos(φ2) *
                sin(Δλ / 2) * sin(Δλ / 2)

        val c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c
    }
}

/**
 * Sort photos by bearing for consistent navigation order
 * Translation from AngularRangeCuller.ts sortPhotosByBearing function
 */
fun sortPhotosByBearing(photos: MutableList<PhotoData>) {
    photos.sortWith { a, b ->
        when {
            a.bearing != b.bearing -> a.bearing.compareTo(b.bearing)
            else -> a.uid.compareTo(b.uid) // Stable sort with UID as tiebreaker for cross-source consistency
        }
    }
}

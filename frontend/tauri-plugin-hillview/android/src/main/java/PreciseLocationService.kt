package io.github.koo5.hillview.plugin

import android.annotation.SuppressLint
import android.content.Context
import android.location.Location
import android.os.Looper
import android.util.Log
import com.google.android.gms.location.*
import com.google.android.gms.tasks.CancellationTokenSource

data class PreciseLocationData(
    val latitude: Double,
    val longitude: Double,
    val accuracy: Float,         // Horizontal accuracy radius in meters
    val altitude: Double?,       // Altitude in meters (if available)
    val altitudeAccuracy: Float?, // Vertical accuracy in meters (if available)
    val bearing: Float?,         // Bearing in degrees (if available)
    val bearingAccuracy: Float?, // Bearing accuracy in degrees (if available)
    val speed: Float?,          // Speed in m/s (if available)
    val speedAccuracy: Float?,  // Speed accuracy in m/s (if available)
    val provider: String?,      // Which provider was used (gps, network, fused, etc)
    val timestamp: Long,
    val elapsedRealtimeNanos: Long // For high-precision time calculations
)

class PreciseLocationService(
    private val context: Context,
    private val onLocationUpdate: (PreciseLocationData) -> Unit
) {
    companion object {
        private const val TAG = "PreciseLocationService"
        
        // Update intervals in milliseconds
        private const val UPDATE_INTERVAL = 1000L        // 1 second
        private const val FASTEST_INTERVAL = 500L        // 0.5 seconds
        private const val MAX_WAIT_TIME = 2000L          // 2 seconds
        
        // Accuracy thresholds
        private const val HIGH_ACCURACY_THRESHOLD = 5.0f  // meters
        private const val MEDIUM_ACCURACY_THRESHOLD = 15.0f // meters
    }
    
    private val fusedLocationClient = LocationServices.getFusedLocationProviderClient(context)
    private var locationCallback: LocationCallback? = null
    private var isRequestingUpdates = false
    
    // Create location request with high accuracy settings using the new Builder pattern
    private val locationRequest = LocationRequest.Builder(
        Priority.PRIORITY_HIGH_ACCURACY,
        UPDATE_INTERVAL
    ).apply {
        setMinUpdateIntervalMillis(FASTEST_INTERVAL)
        setMaxUpdateDelayMillis(MAX_WAIT_TIME)
        
        // Request the most accurate location possible
        setWaitForAccurateLocation(true)
        
        // Set the minimum displacement for location updates (0 = no minimum)
        setMinUpdateDistanceMeters(0f)
    }.build()
    
    init {
        Log.i(TAG, "📍 === PRECISE LOCATION SERVICE INITIALIZED ===")
        Log.i(TAG, "📍 Configuration:")
        Log.i(TAG, "  - Update interval: ${UPDATE_INTERVAL}ms")
        Log.i(TAG, "  - Fastest interval: ${FASTEST_INTERVAL}ms")
        Log.i(TAG, "  - Priority: HIGH_ACCURACY (GPS)")
        Log.i(TAG, "  - Wait for accurate location: true")
        
        setupLocationCallback()
    }
    
    private fun setupLocationCallback() {
        locationCallback = object : LocationCallback() {
            override fun onLocationResult(locationResult: LocationResult) {
                locationResult.lastLocation?.let { location ->
                    Log.v(TAG, "📍 Received location update")
                    handleLocationUpdate(location)
                }
            }
            
            override fun onLocationAvailability(availability: LocationAvailability) {
                Log.d(TAG, "📍 Location availability changed: ${availability.isLocationAvailable}")
                if (!availability.isLocationAvailable) {
                    Log.w(TAG, "⚠️ Location is currently unavailable")
                }
            }
        }
    }
    
    private fun handleLocationUpdate(location: Location) {
        val accuracyLevel = when {
            location.accuracy <= HIGH_ACCURACY_THRESHOLD -> "HIGH"
            location.accuracy <= MEDIUM_ACCURACY_THRESHOLD -> "MEDIUM"
            else -> "LOW"
        }
        
        Log.d(TAG, "📍 Location update:")
        Log.d(TAG, "  - Lat/Lng: ${location.latitude}, ${location.longitude}")
        Log.d(TAG, "  - Accuracy: ${location.accuracy}m ($accuracyLevel)")
        Log.d(TAG, "  - Provider: ${location.provider}")
        
        // Log additional data if available
        if (location.hasAltitude()) {
            Log.d(TAG, "  - Altitude: ${location.altitude}m")
        }
        if (location.hasVerticalAccuracy()) {
            Log.d(TAG, "  - Vertical accuracy: ${location.verticalAccuracyMeters}m")
        }
        if (location.hasBearing()) {
            Log.d(TAG, "  - Bearing: ${location.bearing}°")
        }
        if (location.hasBearingAccuracy()) {
            Log.d(TAG, "  - Bearing accuracy: ${location.bearingAccuracyDegrees}°")
        }
        if (location.hasSpeed()) {
            Log.d(TAG, "  - Speed: ${location.speed}m/s (${location.speed * 3.6}km/h)")
        }
        if (location.hasSpeedAccuracy()) {
            Log.d(TAG, "  - Speed accuracy: ${location.speedAccuracyMetersPerSecond}m/s")
        }
        
        // Create precise location data
        val preciseData = PreciseLocationData(
            latitude = location.latitude,
            longitude = location.longitude,
            accuracy = location.accuracy,
            altitude = if (location.hasAltitude()) location.altitude else null,
            altitudeAccuracy = if (location.hasVerticalAccuracy()) location.verticalAccuracyMeters else null,
            bearing = if (location.hasBearing()) location.bearing else null,
            bearingAccuracy = if (location.hasBearingAccuracy()) location.bearingAccuracyDegrees else null,
            speed = if (location.hasSpeed()) location.speed else null,
            speedAccuracy = if (location.hasSpeedAccuracy()) location.speedAccuracyMetersPerSecond else null,
            provider = location.provider,
            timestamp = location.time,
            elapsedRealtimeNanos = location.elapsedRealtimeNanos
        )
        
        // Send update callback
        onLocationUpdate(preciseData)
    }
    
    @SuppressLint("MissingPermission")
    fun startLocationUpdates() {
        if (isRequestingUpdates) {
            Log.w(TAG, "📍 Location updates already active")
            return
        }
        
        Log.i(TAG, "📍 Starting precise location updates")
        
        locationCallback?.let { callback ->
            try {
                fusedLocationClient.requestLocationUpdates(
                    locationRequest,
                    callback,
                    Looper.getMainLooper()
                )
                isRequestingUpdates = true
                Log.i(TAG, "✅ Location updates started successfully")
                
                // Also get the last known location immediately
                getLastKnownLocation()
            } catch (e: SecurityException) {
                Log.e(TAG, "❌ Location permission not granted: ${e.message}")
            } catch (e: Exception) {
                Log.e(TAG, "❌ Failed to start location updates: ${e.message}")
            }
        }
    }
    
    @SuppressLint("MissingPermission")
    private fun getLastKnownLocation() {
        try {
            fusedLocationClient.lastLocation.addOnSuccessListener { location ->
                location?.let {
                    Log.d(TAG, "📍 Got last known location")
                    handleLocationUpdate(it)
                }
            }
        } catch (e: SecurityException) {
            Log.e(TAG, "❌ Location permission not granted for last location")
        }
    }
    
    fun stopLocationUpdates() {
        if (!isRequestingUpdates) {
            Log.w(TAG, "📍 Location updates not active")
            return
        }
        
        Log.i(TAG, "📍 Stopping location updates")
        
        locationCallback?.let { callback ->
            fusedLocationClient.removeLocationUpdates(callback)
            isRequestingUpdates = false
            Log.i(TAG, "✅ Location updates stopped")
        }
    }
    
    @SuppressLint("MissingPermission")
    fun getCurrentLocation(onSuccess: (PreciseLocationData) -> Unit, onFailure: (Exception) -> Unit) {
        Log.d(TAG, "📍 Requesting current location")
        
        val cancellationTokenSource = CancellationTokenSource()
        
        try {
            fusedLocationClient.getCurrentLocation(
                Priority.PRIORITY_HIGH_ACCURACY,
                cancellationTokenSource.token
            ).addOnSuccessListener { location ->
                location?.let {
                    Log.d(TAG, "📍 Got current location")
                    handleLocationUpdate(it)
                    onSuccess(PreciseLocationData(
                        latitude = it.latitude,
                        longitude = it.longitude,
                        accuracy = it.accuracy,
                        altitude = if (it.hasAltitude()) it.altitude else null,
                        altitudeAccuracy = if (it.hasVerticalAccuracy()) it.verticalAccuracyMeters else null,
                        bearing = if (it.hasBearing()) it.bearing else null,
                        bearingAccuracy = if (it.hasBearingAccuracy()) it.bearingAccuracyDegrees else null,
                        speed = if (it.hasSpeed()) it.speed else null,
                        speedAccuracy = if (it.hasSpeedAccuracy()) it.speedAccuracyMetersPerSecond else null,
                        provider = it.provider,
                        timestamp = it.time,
                        elapsedRealtimeNanos = it.elapsedRealtimeNanos
                    ))
                } ?: run {
                    val error = Exception("Location is null")
                    Log.e(TAG, "❌ Current location is null")
                    onFailure(error)
                }
            }.addOnFailureListener { exception ->
                Log.e(TAG, "❌ Failed to get current location: ${exception.message}")
                onFailure(exception)
            }
        } catch (e: SecurityException) {
            Log.e(TAG, "❌ Location permission not granted")
            onFailure(e)
        }
    }
    
    // Note: With the new API, location request is immutable, so we can't update it dynamically
    // This method is kept for compatibility but would require recreating the request
    fun updateLocationRequest(interval: Long? = null, fastestInterval: Long? = null, priority: Int? = null) {
        Log.d(TAG, "📍 Location request parameters cannot be updated with new API")
        Log.d(TAG, "📍 To change parameters, stop and restart location updates with new settings")
        
        // Log the requested changes
        interval?.let { 
            Log.d(TAG, "  - Requested update interval: ${it}ms")
        }
        fastestInterval?.let { 
            Log.d(TAG, "  - Requested fastest interval: ${it}ms")
        }
        priority?.let { 
            Log.d(TAG, "  - Requested priority: ${when(it) {
                Priority.PRIORITY_HIGH_ACCURACY -> "HIGH_ACCURACY"
                Priority.PRIORITY_BALANCED_POWER_ACCURACY -> "BALANCED_POWER_ACCURACY"
                Priority.PRIORITY_LOW_POWER -> "LOW_POWER"
                Priority.PRIORITY_PASSIVE -> "PASSIVE"
                else -> "UNKNOWN"
            }}")
        }
    }
}
package io.github.koo5.hillview.plugin

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.os.Looper
import android.util.Log
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
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
    private val activity: Activity,
    private val onLocationUpdate: (PreciseLocationData) -> Unit
) {
    // Provide context from activity for convenience
    private val context: Context = activity
    
    companion object {
        private const val TAG = "PreciseLocationService"
        
        // Update intervals in milliseconds
        private const val UPDATE_INTERVAL = 1000L        // 1 second
        private const val FASTEST_INTERVAL = 500L        // 0.5 seconds
        private const val MAX_WAIT_TIME = 2000L          // 2 seconds
        
        // Accuracy thresholds
        private const val HIGH_ACCURACY_THRESHOLD = 5.0f  // meters
        private const val MEDIUM_ACCURACY_THRESHOLD = 15.0f // meters
        
        // Permission request code
        private const val LOCATION_PERMISSION_REQUEST_CODE = 1001
    }
    
    private val fusedLocationClient = LocationServices.getFusedLocationProviderClient(activity)
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
        Log.d(TAG, "📍 INIT: Setting up location callback...")
        
        setupLocationCallback()
        Log.d(TAG, "📍 INIT: Location callback setup complete")
        Log.d(TAG, "📍 INIT: locationCallback = $locationCallback")
        Log.d(TAG, "📍 INIT: fusedLocationClient = $fusedLocationClient")
    }
    
    private fun setupLocationCallback() {
        Log.i(TAG, "📍 SETUP: Setting up location callback...")
        locationCallback = object : LocationCallback() {
            override fun onLocationResult(locationResult: LocationResult) {
                Log.i(TAG, "📍 CALLBACK: *** onLocationResult called! ***")
                Log.i(TAG, "📍 CALLBACK: locationResult = $locationResult")
                Log.i(TAG, "📍 CALLBACK: locations count = ${locationResult.locations.size}")
                Log.i(TAG, "📍 CALLBACK: lastLocation = ${locationResult.lastLocation}")
                
                locationResult.lastLocation?.let { location ->
                    Log.i(TAG, "📍 CALLBACK: Processing location update...")
                    handleLocationUpdate(location)
                } ?: run {
                    Log.w(TAG, "📍 CALLBACK: lastLocation is null!")
                }
                
                // Log all locations if there are multiple
                locationResult.locations.forEachIndexed { index, location ->
                    Log.d(TAG, "📍 CALLBACK: Location $index: lat=${location.latitude}, lng=${location.longitude}, accuracy=${location.accuracy}m")
                }
            }
            
            override fun onLocationAvailability(availability: LocationAvailability) {
                Log.i(TAG, "📍 CALLBACK: *** onLocationAvailability called! ***")
                Log.i(TAG, "📍 CALLBACK: Location availability changed: ${availability.isLocationAvailable}")
                if (!availability.isLocationAvailable) {
                    Log.w(TAG, "⚠️ CALLBACK: Location is currently unavailable")
                    Log.w(TAG, "⚠️ CALLBACK: This could mean GPS is turned off or no signal")
                } else {
                    Log.i(TAG, "✅ CALLBACK: Location is available!")
                }
            }
        }
        Log.i(TAG, "📍 SETUP: Location callback setup complete: $locationCallback")
    }
    
    private fun handleLocationUpdate(location: Location) {
        Log.i(TAG, "📍 HANDLE: *** handleLocationUpdate called! ***")
        
        val accuracyLevel = when {
            location.accuracy <= HIGH_ACCURACY_THRESHOLD -> "HIGH"
            location.accuracy <= MEDIUM_ACCURACY_THRESHOLD -> "MEDIUM"
            else -> "LOW"
        }
        
        Log.i(TAG, "📍 HANDLE: Location update details:")
        Log.i(TAG, "📍 HANDLE:   - Lat/Lng: ${location.latitude}, ${location.longitude}")
        Log.i(TAG, "📍 HANDLE:   - Accuracy: ${location.accuracy}m ($accuracyLevel)")
        Log.i(TAG, "📍 HANDLE:   - Provider: ${location.provider}")
        Log.i(TAG, "📍 HANDLE:   - Time: ${location.time}")
        Log.i(TAG, "📍 HANDLE:   - Elapsed realtime: ${location.elapsedRealtimeNanos}")
        
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
        Log.i(TAG, "📍 HANDLE: Creating PreciseLocationData object...")
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
        
        Log.i(TAG, "📍 HANDLE: Calling onLocationUpdate callback...")
        try {
            onLocationUpdate(preciseData)
            Log.i(TAG, "📍 HANDLE: ✅ onLocationUpdate callback completed successfully!")
        } catch (e: Exception) {
            Log.e(TAG, "📍 HANDLE: ❌ Error in onLocationUpdate callback: ${e.message}", e)
        }
    }
    
    // Check if location permissions are granted
    private fun hasLocationPermissions(): Boolean {
        val fineLocationGranted = ContextCompat.checkSelfPermission(
            activity, 
            Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
        
        val coarseLocationGranted = ContextCompat.checkSelfPermission(
            activity, 
            Manifest.permission.ACCESS_COARSE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
        
        return fineLocationGranted || coarseLocationGranted
    }
    
    // Request location permissions
    private fun requestLocationPermissions() {
        Log.i(TAG, "📍 PERM: Requesting location permissions...")
        
        val permissions = arrayOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        
        ActivityCompat.requestPermissions(
            activity, 
            permissions, 
            LOCATION_PERMISSION_REQUEST_CODE
        )
    }
    
    // Handle permission request results
    fun onRequestPermissionsResult(requestCode: Int, @Suppress("UNUSED_PARAMETER") permissions: Array<String>, grantResults: IntArray) {
        if (requestCode == LOCATION_PERMISSION_REQUEST_CODE) {
            Log.i(TAG, "📍 PERM: Permission request result received")
            Log.i(TAG, "📍 PERM: Granted permissions: ${grantResults.count { it == PackageManager.PERMISSION_GRANTED }}/${grantResults.size}")
            
            if (grantResults.isNotEmpty() && grantResults.any { it == PackageManager.PERMISSION_GRANTED }) {
                Log.i(TAG, "📍 PERM: ✅ At least one location permission granted, retrying location updates...")
                startLocationUpdatesInternal()
            } else {
                Log.e(TAG, "📍 PERM: ❌ Location permissions denied! Cannot start location updates.")
            }
        }
    }
    
    // Public method to start location updates with permission handling
    fun startLocationUpdates() {
        Log.i(TAG, "📍 START: ======= startLocationUpdates() called =======")
        Log.i(TAG, "📍 START: Checking location permissions...")
        
        if (!hasLocationPermissions()) {
            Log.w(TAG, "📍 START: ❌ Location permissions not granted!")
            Log.i(TAG, "📍 START: Requesting location permissions...")
            requestLocationPermissions()
            return
        }
        
        Log.i(TAG, "📍 START: ✅ Location permissions are granted, proceeding...")
        startLocationUpdatesInternal()
    }
    
    @SuppressLint("MissingPermission")
    private fun startLocationUpdatesInternal() {
        Log.i(TAG, "📍 START_INTERNAL: ======= startLocationUpdatesInternal() called =======")
        Log.i(TAG, "📍 START_INTERNAL: Current thread: ${Thread.currentThread().name}")
        Log.i(TAG, "📍 START_INTERNAL: Current isRequestingUpdates = $isRequestingUpdates")
        Log.i(TAG, "📍 START_INTERNAL: fusedLocationClient = $fusedLocationClient")
        Log.i(TAG, "📍 START_INTERNAL: locationCallback = $locationCallback")
        Log.i(TAG, "📍 START_INTERNAL: locationRequest = $locationRequest")
        
        if (isRequestingUpdates) {
            Log.w(TAG, "📍 START_INTERNAL: Location updates already active - returning early")
            return
        }
        
        Log.i(TAG, "📍 START_INTERNAL: Checking location permission status...")
        try {
            val hasLocationPermission = context.checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED
            val hasCoarsePermission = context.checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED
            Log.i(TAG, "📍 START_INTERNAL: Fine location permission: $hasLocationPermission")
            Log.i(TAG, "📍 START_INTERNAL: Coarse location permission: $hasCoarsePermission")
            
            if (!hasLocationPermission && !hasCoarsePermission) {
                Log.e(TAG, "📍 START_INTERNAL: ❌ NO LOCATION PERMISSIONS GRANTED!")
                return
            }
        } catch (e: Exception) {
            Log.e(TAG, "📍 START_INTERNAL: Error checking permissions: ${e.message}", e)
        }
        
        Log.i(TAG, "📍 START_INTERNAL: Beginning location update setup...")
        
        locationCallback?.let { callback ->
            Log.i(TAG, "📍 START_INTERNAL: LocationCallback is not null, proceeding...")
            
            try {
                // Check if location services are enabled
                val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as android.location.LocationManager
                val isGpsEnabled = locationManager.isProviderEnabled(android.location.LocationManager.GPS_PROVIDER)
                val isNetworkEnabled = locationManager.isProviderEnabled(android.location.LocationManager.NETWORK_PROVIDER)
                
                Log.i(TAG, "📍 START_INTERNAL: GPS provider enabled: $isGpsEnabled")
                Log.i(TAG, "📍 START_INTERNAL: Network provider enabled: $isNetworkEnabled")
                
                if (!isGpsEnabled && !isNetworkEnabled) {
                    Log.e(TAG, "📍 START_INTERNAL: ❌ NO LOCATION PROVIDERS ENABLED!")
                    Log.e(TAG, "📍 START_INTERNAL: User needs to enable Location Services in Settings")
                }
                
                Log.i(TAG, "📍 START_INTERNAL: Calling fusedLocationClient.requestLocationUpdates()...")
                
                fusedLocationClient.requestLocationUpdates(
                    locationRequest,
                    callback,
                    Looper.getMainLooper()
                )
                isRequestingUpdates = true
                Log.i(TAG, "✅ START_INTERNAL: requestLocationUpdates() call completed successfully!")
                
                // Also get the last known location immediately
                Log.i(TAG, "📍 START_INTERNAL: Getting last known location...")
                getLastKnownLocation()
                
            } catch (e: SecurityException) {
                Log.e(TAG, "❌ START_INTERNAL: SECURITY EXCEPTION - Location permission not granted!")
                Log.e(TAG, "❌ START_INTERNAL: SecurityException message: ${e.message}")
            } catch (e: Exception) {
                Log.e(TAG, "❌ START_INTERNAL: UNEXPECTED EXCEPTION in startLocationUpdatesInternal!")
                Log.e(TAG, "❌ START_INTERNAL: Exception type: ${e.javaClass.simpleName}")
                Log.e(TAG, "❌ START_INTERNAL: Exception message: ${e.message}")
            }
        } ?: run {
            Log.e(TAG, "❌ START_INTERNAL: CRITICAL ERROR - LocationCallback is null!")
        }
    }
    
    @SuppressLint("MissingPermission")
    private fun getLastKnownLocation() {
        Log.i(TAG, "📍 LAST: Getting last known location...")
        try {
            fusedLocationClient.lastLocation
                .addOnSuccessListener { location ->
                    location?.let {
                        Log.i(TAG, "📍 LAST: ✅ Got last known location: lat=${it.latitude}, lng=${it.longitude}")
                        handleLocationUpdate(it)
                    } ?: run {
                        Log.w(TAG, "📍 LAST: ⚠️ Last known location is null")
                        Log.w(TAG, "📍 LAST: This is normal for first-time app usage or if location history is disabled")
                    }
                }
                .addOnFailureListener { exception ->
                    Log.e(TAG, "📍 LAST: ❌ Failed to get last known location: ${exception.message}", exception)
                }
        } catch (e: SecurityException) {
            Log.e(TAG, "📍 LAST: ❌ Location permission not granted for last location: ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "📍 LAST: ❌ Unexpected error getting last known location: ${e.message}", e)
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
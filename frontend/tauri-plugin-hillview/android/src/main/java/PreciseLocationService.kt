package cz.hillview.plugin

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat
import com.google.android.gms.location.*
import com.google.android.gms.location.Priority

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
    private val onLocationUpdate: (PreciseLocationData) -> Unit,
    private val onLocationStopped: (() -> Unit)? = null
) {
    // Provide context from activity for convenience
    private val context: Context = activity

    companion object {
        private const val TAG = "🢄PreciseLocationService"
        private const val doLog = false

        // Update intervals in milliseconds
        private const val UPDATE_INTERVAL = 1000L
        private const val FASTEST_INTERVAL = 1000L
        private const val MAX_WAIT_TIME = 1000L
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
        //setMaxUpdateDelayMillis(MAX_WAIT_TIME)
		//setMaxUpdateAgeMillis(1000*60*60

        // Request the most accurate location possible
        setWaitForAccurateLocation(false)

    }.build()

    init {
        setupLocationCallback()
    }

    private fun setupLocationCallback() {
        locationCallback = object : LocationCallback() {
            override fun onLocationResult(locationResult: LocationResult) {
                /*Log.i(TAG, "📍 CALLBACK: *** onLocationResult called! ***")
                Log.i(TAG, "📍 CALLBACK: locationResult = $locationResult")
                Log.i(TAG, "📍 CALLBACK: locations count = ${locationResult.locations.size}")
                Log.i(TAG, "📍 CALLBACK: lastLocation = ${locationResult.lastLocation}")
                */

                locationResult.lastLocation?.let { location ->
                    //Log.i(TAG, "📍 CALLBACK: Processing location update...")
                    handleLocationUpdate(location)
                } ?: run {
                    Log.w(TAG, "📍 CALLBACK: lastLocation is null!")
                }

                // Log all locations if there are multiple
                locationResult.locations.forEachIndexed { index, location ->
                    //Log.d(TAG, "📍 CALLBACK: Location $index: lat=${location.latitude}, lng=${location.longitude}, accuracy=${location.accuracy}m")
                }
            }

            override fun onLocationAvailability(availability: LocationAvailability) {
                ////Log.i(TAG, "📍 CALLBACK: *** onLocationAvailability called! ***")
                //Log.i(TAG, "📍 isLocationAvailable: ${availability.isLocationAvailable}")
                if (!availability.isLocationAvailable) {
                    //Log.w(TAG, "📍⚠️ CALLBACK: Location is currently unavailable")
                    //Log.w(TAG, "📍⚠️ CALLBACK: This could mean GPS is turned off or no signal")
                } else {
                    //Log.i(TAG, "📍✅ CALLBACK: Location is available!")
                }
            }
        }
        Log.i(TAG, "📍 SETUP: Location callback setup complete: $locationCallback")
    }

    private fun handleLocationUpdate(location: Location) {
        //Log.i(TAG, "📍 HANDLE: *** handleLocationUpdate called! ***")

        // accuracyLevel removed - was only used in commented logging
/*
        Log.i(TAG, "📍 HANDLE: Location update details:")
        Log.i(TAG, "📍 HANDLE:   - Lat/Lng: ${location.latitude}, ${location.longitude}")
        Log.i(TAG, "📍 HANDLE:   - Accuracy: ${location.accuracy}m ($accuracyLevel)")
        Log.i(TAG, "📍 HANDLE:   - Provider: ${location.provider}")
        Log.i(TAG, "📍 HANDLE:   - Time: ${location.time}")
        Log.i(TAG, "📍 HANDLE:   - Elapsed realtime: ${location.elapsedRealtimeNanos}")

        // Log additional data if available
        if (location.hasAltitude()) {
            Log.d(TAG, "📍  - Altitude: ${location.altitude}m")
        }
        if (location.hasVerticalAccuracy()) {
            Log.d(TAG, "📍  - Vertical accuracy: ${location.verticalAccuracyMeters}m")
        }
        if (location.hasBearing()) {
            Log.d(TAG, "📍  - Bearing: ${location.bearing}°")
        }
        if (location.hasBearingAccuracy()) {
            Log.d(TAG, "📍  - Bearing accuracy: ${location.bearingAccuracyDegrees}°")
        }
        if (location.hasSpeed()) {
            Log.d(TAG, "📍  - Speed: ${location.speed}m/s (${location.speed * 3.6}km/h)")
        }
        if (location.hasSpeedAccuracy()) {
            Log.d(TAG, "📍  - Speed accuracy: ${location.speedAccuracyMetersPerSecond}m/s")
        }
  */

        // Create precise location data
        //Log.i(TAG, "📍 HANDLE: Creating PreciseLocationData object...")
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

        //Log.i(TAG, "📍 HANDLE: Calling onLocationUpdate callback...")
        try {
            onLocationUpdate(preciseData)
            //Log.i(TAG, "📍 HANDLE: ✅ onLocationUpdate callback completed successfully!")
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

    // Public method to start location updates
    // Note: Frontend should request permissions via Tauri before calling this
    @Synchronized
    fun startLocationUpdates() {
        Log.i(TAG, "📍 START: ======= startLocationUpdates() called =======")

        if (isRequestingUpdates) {
            Log.i(TAG, "📍 START: ✅ Location updates already active - ignoring duplicate request")
            return
        }

        if (!hasLocationPermissions()) {
            Log.e(TAG, "📍 START: ❌ Location permissions not granted! Frontend should request permissions first.")
            onLocationStopped?.invoke()
            return
        }

        Log.i(TAG, "📍 START: ✅ Location permissions are granted, proceeding...")
        startLocationUpdatesInternal()
    }

    @SuppressLint("MissingPermission")
    private fun startLocationUpdatesInternal() {

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
                Log.i(TAG, "📍✅ START_INTERNAL: requestLocationUpdates() call completed successfully!")

                // Also get the last known location immediately
                Log.i(TAG, "📍 START_INTERNAL: Getting last known location...")
                getLastKnownLocation()

            } catch (e: SecurityException) {
                Log.e(TAG, "📍❌ START_INTERNAL: SECURITY EXCEPTION - Location permission not granted!")
                Log.e(TAG, "📍❌ START_INTERNAL: SecurityException message: ${e.message}")
                onLocationStopped?.invoke()
            } catch (e: Exception) {
                Log.e(TAG, "📍❌ START_INTERNAL: UNEXPECTED EXCEPTION in startLocationUpdatesInternal!")
                Log.e(TAG, "📍❌ START_INTERNAL: Exception type: ${e.javaClass.simpleName}")
                Log.e(TAG, "📍❌ START_INTERNAL: Exception message: ${e.message}")
                onLocationStopped?.invoke()
            }
        } ?: run {
            Log.e(TAG, "📍❌ START_INTERNAL: CRITICAL ERROR - LocationCallback is null!")
        }
    }

    @SuppressLint("MissingPermission")
    private fun getLastKnownLocation() {
        Log.i(TAG, "📍 LAST: Getting last known location...")
        try {
            fusedLocationClient.lastLocation
                .addOnSuccessListener { location ->
                    location?.let {
                        if (doLog) Log.i(TAG, "📍 LAST: ✅ Got last known location: lat=${it.latitude}, lng=${it.longitude}")
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
            Log.i(TAG, "📍✅ Location updates stopped")
            // Notify frontend that location tracking stopped
            onLocationStopped?.invoke()
        }
    }

}

package cz.hillview.plugin

import android.content.Context
import android.util.Log
import com.google.android.gms.location.FusedOrientationProviderClient
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.DeviceOrientationRequest
import com.google.android.gms.location.DeviceOrientation
import com.google.android.gms.location.DeviceOrientationListener
import java.util.concurrent.Executors

/**
 * Device orientation provider using Google Play Services FusedOrientationProviderClient
 * Provides device attitude/quaternion data for enhanced orientation detection
 * Designed to work alongside EnhancedSensorService
 */
class DeviceOrientationProvider(
    private val context: Context
) {
    companion object {
        private const val TAG = "DeviceOrientationProvider"
    }

    private var fusedOrientationProviderClient: FusedOrientationProviderClient? = null
    private var currentOrientation: DeviceOrientation? = null
    private var isStarted = false
    private val executor = Executors.newSingleThreadExecutor()

    private val orientationListener = object : DeviceOrientationListener {
        override fun onDeviceOrientationChanged(orientation: DeviceOrientation) {
            currentOrientation = orientation
            logOrientationData(orientation)
        }
    }

    /**
     * Start the orientation provider - called from ExamplePlugin.startSensor
     */
    fun startOrientationProvider() {
        if (isStarted) {
            Log.d(TAG, "Orientation provider already started")
            return
        }

        try {
            Log.d(TAG, "Starting FusedOrientationProviderClient...")
            fusedOrientationProviderClient = LocationServices.getFusedOrientationProviderClient(context)

            // Create orientation request
            val request = DeviceOrientationRequest.Builder(1000000) // fixme: cant seem to throttle it
                .build()

            // Start requesting orientation updates
            fusedOrientationProviderClient?.requestOrientationUpdates(
                request,
                executor,
                orientationListener
            )?.addOnSuccessListener {
                isStarted = true
                Log.d(TAG, "FusedOrientationProviderClient started successfully")
            }?.addOnFailureListener { exception ->
                Log.e(TAG, "Failed to start orientation updates: ${exception.message}")
            }

        } catch (e: Exception) {
            Log.e(TAG, "Failed to start FusedOrientationProviderClient", e)
        }
    }

    /**
     * Stop the orientation provider
     */
    fun stopOrientationProvider() {
        if (!isStarted) {
            Log.d(TAG, "Orientation provider not started")
            return
        }

        try {
            fusedOrientationProviderClient?.removeOrientationUpdates(orientationListener)
                ?.addOnSuccessListener {
                    Log.d(TAG, "FusedOrientationProviderClient stopped successfully")
                }?.addOnFailureListener { exception ->
                    Log.w(TAG, "Error stopping orientation updates: ${exception.message}")
                }

            currentOrientation = null
            fusedOrientationProviderClient = null
            isStarted = false

        } catch (e: Exception) {
            Log.e(TAG, "Error stopping FusedOrientationProviderClient", e)
        }
    }


    /**
     * Log orientation data for debugging (for now, just logging as requested)
     */
    private fun logOrientationData(orientation: DeviceOrientation) {
        try {

            val attitude = orientation.attitude
            Log.v(TAG, "🔍📊GDO Attitude: $attitude") // fixme: print elements properly

            // Log heading if available
            try {
                val heading = orientation.headingDegrees
                Log.v(TAG, "🔍📊GDO Heading: ${String.format("%.1f", heading)}°")
            } catch (e: Exception) {
                Log.v(TAG, "🔍📊GDO Heading: not available")
            }

        } catch (e: Exception) {
            Log.e(TAG, "Error logging orientation data", e)
        }
    }

    /**
     * Get the attitude quaternion from current device orientation
     * Returns [w, x, y, z] quaternion components or null if not available
     */
    fun getAttitude(): FloatArray? {
        return currentOrientation?.let { orientation ->
            try {
                val attitude = orientation.attitude
                // Convert attitude to float array - structure will be determined at runtime
                // For now, return null until we can inspect the actual attitude object structure
                Log.d(TAG, "Attitude object: $attitude")
                null
            } catch (e: Exception) {
                Log.e(TAG, "Error extracting attitude quaternion", e)
                null
            }
        }
    }

    /**
     * Check if orientation provider is running
     */
    fun isRunning(): Boolean = isStarted
}

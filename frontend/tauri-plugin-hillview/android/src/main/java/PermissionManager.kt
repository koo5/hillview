package cz.hillview.plugin

import android.app.Activity
import android.content.pm.PackageManager
import android.util.Log
import android.webkit.ConsoleMessage
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import app.tauri.plugin.JSObject

class PermissionManager(private val activity: Activity) {
    companion object {
        private const val TAG = "PermissionManager"
        private const val CAMERA_PERMISSION_REQUEST_CODE = 1001
        
        private val permissionLock = Any()
        private var permissionLockHolder: String? = null
    }

    fun acquirePermissionLock(requester: String): Boolean {
        synchronized(permissionLock) {
            if (permissionLockHolder == null) {
                permissionLockHolder = requester
                Log.i(TAG, "🔒 Permission lock acquired by: $requester")
                return true
            } else {
                val holder = permissionLockHolder!!
                if (holder == requester) {
                    Log.i(TAG, "🔒 Permission lock already held by requester: $requester")
                    return true
                }
                // Special overrides: allow camera requests to proceed (matching Rust logic)
                else if (requester == "camera") {
                    Log.i(TAG, "🔒 Permission lock granted to camera (override)")
                    return true
                }
                else if (requester == "camera-native") {
                    Log.i(TAG, "🔒 Permission lock granted to camera-native (override)")
                    return true
                }
                else {
                    Log.i(TAG, "🔒 Permission lock denied to $requester, currently held by: $holder")
                    return false
                }
            }
        }
    }

    fun releasePermissionLock(requester: String): Boolean {
        synchronized(permissionLock) {
            if (permissionLockHolder == requester || permissionLockHolder == null) {
                permissionLockHolder = null
                Log.i(TAG, "🔒 Permission lock released by: $requester")
                return true
            } else {
                Log.w(TAG, "🔒 Permission lock release failed: held by $permissionLockHolder, not $requester")
                return false
            }
        }
    }

    fun getPermissionLockHolder(): String? = permissionLockHolder

    fun hasCameraPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            activity,
            android.Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
    }

    fun requestCameraPermission(): JSObject {
        Log.i(TAG, "🎥 Checking camera permission")

        if (hasCameraPermission()) {
            Log.i(TAG, "🎥 Camera permission already granted")
            val result = JSObject()
            result.put("granted", true)
            return result
        }

        // Check if we can request permission (not permanently denied)
        if (ActivityCompat.shouldShowRequestPermissionRationale(activity, android.Manifest.permission.CAMERA)) {
            Log.i(TAG, "🎥 Should show rationale - permission can be requested")
        } else {
            Log.i(TAG, "🎥 No rationale needed - first time or permanently denied")
        }

        // Try to acquire permission lock
        val lockAcquired = acquirePermissionLock("camera-native")
        if (!lockAcquired) {
            Log.w(TAG, "🎥 Permission system busy, cannot request camera permission right now")
            val result = JSObject()
            result.put("granted", false)
            result.put("error", "Permission system busy")
            return result
        }

        // Request permission from user
        Log.i(TAG, "🎥 Requesting camera permission from user")
        ActivityCompat.requestPermissions(
            activity,
            arrayOf(android.Manifest.permission.CAMERA),
            CAMERA_PERMISSION_REQUEST_CODE
        )

        // Return pending status - actual result will come via callback
        val result = JSObject()
        result.put("pending", true)
        return result
    }

    fun setupWebViewCameraPermissions(webView: WebView, onPermissionRequest: (PermissionRequest) -> Unit) {
        Log.i(TAG, "🢄🎥 Setting up WebView camera permission handling")

        webView.webChromeClient = object : WebChromeClient() {
            // Prevent duplicate console logging by not forwarding to Android logs
            override fun onConsoleMessage(consoleMessage: ConsoleMessage): Boolean {
                // Don't forward console messages to prevent duplication
                // Let WebView handle them naturally in DevTools/Inspector
                return false
            }

            override fun onPermissionRequest(request: PermissionRequest) {
                Log.i(TAG, "🢄🎥 WebView permission request received")
                Log.i(TAG, "🢄🎥 Origin: ${request.origin}")
                Log.i(TAG, "🢄🎥 Resources: ${request.resources?.joinToString(", ")}")

                onPermissionRequest(request)
            }
        }
    }

}
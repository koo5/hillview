package cz.hillview.plugin

import android.app.Activity
import android.app.Application
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Bundle
import android.util.Log
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner

/**
 * Observes app lifecycle (foreground/background) and screen state (on/off)
 * to manage sensor operations efficiently.
 */
class AppLifecycleObserver(
    private val context: Context,
    private val onStateChanged: (AppState) -> Unit
) : Application.ActivityLifecycleCallbacks, DefaultLifecycleObserver {

    companion object {
        private const val TAG = "hv-AppLifecycleObserver"
    }

    data class AppState(
        val isInForeground: Boolean,
        val isScreenOn: Boolean,
        val activeActivity: String?
    ) {
        val shouldPauseSensors: Boolean
            get() = !isInForeground || !isScreenOn
    }

    private var isInForeground = false
    private var isScreenOn = true
    private var activeActivity: String? = null
    private var screenStateReceiver: ScreenStateReceiver? = null

    private val currentState: AppState
        get() = AppState(
            isInForeground = isInForeground,
            isScreenOn = isScreenOn,
            activeActivity = activeActivity
        )

    fun start() {
        Log.i(TAG, "🚀 Starting app lifecycle observer")

        // Register for process lifecycle (foreground/background)
        ProcessLifecycleOwner.get().lifecycle.addObserver(this)

        // Register for screen state changes
        screenStateReceiver = ScreenStateReceiver().also { receiver ->
            val filter = IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(Intent.ACTION_USER_PRESENT) // Screen unlocked
            }
            context.registerReceiver(receiver, filter)
        }

        Log.i(TAG, "✅ Lifecycle observer started")
        // Send initial state
        notifyStateChanged()
    }

    fun stop() {
        Log.i(TAG, "🛑 Stopping app lifecycle observer")

        ProcessLifecycleOwner.get().lifecycle.removeObserver(this)

        screenStateReceiver?.let { receiver ->
            try {
                context.unregisterReceiver(receiver)
            } catch (e: IllegalArgumentException) {
                Log.w(TAG, "Screen receiver already unregistered: ${e.message}")
            }
        }
        screenStateReceiver = null

        Log.i(TAG, "✅ Lifecycle observer stopped")
    }

    // ProcessLifecycleOwner callbacks
    override fun onStart(owner: LifecycleOwner) {
        super.onStart(owner)
        Log.i(TAG, "🟢 App moved to FOREGROUND")
        isInForeground = true
        notifyStateChanged()
    }

    override fun onStop(owner: LifecycleOwner) {
        super.onStop(owner)
        Log.i(TAG, "🔴 App moved to BACKGROUND")
        isInForeground = false
        notifyStateChanged()
    }

    // Activity lifecycle callbacks for detailed tracking
    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) {
        activeActivity = activity::class.java.simpleName
        Log.d(TAG, "📱 Activity created: $activeActivity")
    }

    override fun onActivityStarted(activity: Activity) {
        activeActivity = activity::class.java.simpleName
        Log.d(TAG, "▶️ Activity started: $activeActivity")
    }

    override fun onActivityResumed(activity: Activity) {
        activeActivity = activity::class.java.simpleName
        Log.d(TAG, "⏯️ Activity resumed: $activeActivity")
        notifyStateChanged()
    }

    override fun onActivityPaused(activity: Activity) {
        Log.d(TAG, "⏸️ Activity paused: ${activity::class.java.simpleName}")
        notifyStateChanged()
    }

    override fun onActivityStopped(activity: Activity) {
        Log.d(TAG, "⏹️ Activity stopped: ${activity::class.java.simpleName}")
    }

    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) {
        // No action needed
    }

    override fun onActivityDestroyed(activity: Activity) {
        val activityName = activity::class.java.simpleName
        Log.d(TAG, "🗑️ Activity destroyed: $activityName")
        if (activeActivity == activityName) {
            activeActivity = null
        }
    }

    private fun notifyStateChanged() {
        val state = currentState
        Log.i(TAG, "🔄 State changed: foreground=${state.isInForeground}, screen=${state.isScreenOn}, activity=${state.activeActivity}")
        Log.i(TAG, "🔧 Sensors should be ${if (state.shouldPauseSensors) "PAUSED" else "ACTIVE"}")
        onStateChanged(state)
    }

    /**
     * Broadcast receiver for screen on/off events
     */
    private inner class ScreenStateReceiver : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            when (intent?.action) {
                Intent.ACTION_SCREEN_ON -> {
                    Log.i(TAG, "🔆 Screen turned ON")
                    isScreenOn = true
                    notifyStateChanged()
                }
                Intent.ACTION_SCREEN_OFF -> {
                    Log.i(TAG, "🌙 Screen turned OFF")
                    isScreenOn = false
                    notifyStateChanged()
                }
                Intent.ACTION_USER_PRESENT -> {
                    Log.i(TAG, "🔓 Screen unlocked (user present)")
                    isScreenOn = true
                    notifyStateChanged()
                }
            }
        }
    }
}
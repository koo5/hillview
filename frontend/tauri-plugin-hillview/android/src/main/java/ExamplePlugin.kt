package io.github.koo5.hillview.plugin

import android.app.Activity
import android.util.Log
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import app.tauri.plugin.Invoke

@InvokeArg
class PingArgs {
  var value: String? = null
}

@InvokeArg
class LocationUpdateArgs {
  var latitude: Double = 0.0
  var longitude: Double = 0.0
}

@TauriPlugin
class ExamplePlugin(private val activity: Activity): Plugin(activity) {
    companion object {
        private const val TAG = "HillviewPlugin"
        private var pluginInstance: ExamplePlugin? = null
    }
    
    private val implementation = Example()
    private var sensorService: SensorService? = null
    
    init {
        pluginInstance = this
    }

    @Command
    fun ping(invoke: Invoke) {
        val args = invoke.parseArgs(PingArgs::class.java)

        val ret = JSObject()
        ret.put("value", implementation.pong(args.value ?: "default value :("))
        invoke.resolve(ret)
    }
    
    @Command
    fun startSensor(invoke: Invoke) {
        Log.d(TAG, "🔍 Starting sensor service")
        
        if (sensorService == null) {
            Log.d(TAG, "🔍 Creating new SensorService instance")
            sensorService = SensorService(activity) { sensorData ->
                // Emit sensor data event
                val data = JSObject()
                data.put("magneticHeading", sensorData.magneticHeading)
                data.put("trueHeading", sensorData.trueHeading)
                data.put("headingAccuracy", sensorData.headingAccuracy)
                data.put("pitch", sensorData.pitch)
                data.put("roll", sensorData.roll)
                data.put("timestamp", sensorData.timestamp)
                data.put("sensorSource", sensorData.sensorSource)
                
                Log.v(TAG, "🔍 Emitting sensor data event: magnetic=${sensorData.magneticHeading}, source=${sensorData.sensorSource}")
                
                // Try triggering directly without runOnUiThread
                try {
                    trigger("test-event", data)
                    Log.v(TAG, "🔍 Event triggered directly as test-event")
                } catch (e: Exception) {
                    Log.e(TAG, "🔍 Error triggering event: ${e.message}", e)
                    // If that fails, try on UI thread
                    activity.runOnUiThread {
                        try {
                            trigger("test-event", data)
                            Log.v(TAG, "🔍 Event triggered on UI thread as test-event")
                        } catch (e2: Exception) {
                            Log.e(TAG, "🔍 Error triggering on UI thread: ${e2.message}", e2)
                        }
                    }
                }
            }
        } else {
            Log.d(TAG, "🔍 SensorService already exists")
        }
        
        Log.d(TAG, "🔍 Calling sensorService.startSensor()")
        sensorService?.startSensor()
        Log.d(TAG, "🔍 startSensor command completed")
        invoke.resolve()
    }
    
    @Command
    fun stopSensor(invoke: Invoke) {
        Log.d(TAG, "Stopping sensor service")
        sensorService?.stopSensor()
        invoke.resolve()
    }
    
    @Command
    fun updateSensorLocation(invoke: Invoke) {
        val args = invoke.parseArgs(LocationUpdateArgs::class.java)
        Log.d(TAG, "Updating sensor location: ${args.latitude}, ${args.longitude}")
        
        sensorService?.updateLocation(args.latitude, args.longitude)
        invoke.resolve()
    }
}

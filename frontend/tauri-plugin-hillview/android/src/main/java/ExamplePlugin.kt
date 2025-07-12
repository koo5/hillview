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
    }
    
    private val implementation = Example()
    private var sensorService: SensorService? = null

    @Command
    fun ping(invoke: Invoke) {
        val args = invoke.parseArgs(PingArgs::class.java)

        val ret = JSObject()
        ret.put("value", implementation.pong(args.value ?: "default value :("))
        invoke.resolve(ret)
    }
    
    @Command
    fun startSensor(invoke: Invoke) {
        Log.d(TAG, "Starting sensor service")
        
        if (sensorService == null) {
            sensorService = SensorService(activity) { sensorData ->
                // Emit sensor data event
                val data = JSObject()
                data.put("magneticHeading", sensorData.magneticHeading)
                data.put("trueHeading", sensorData.trueHeading)
                data.put("headingAccuracy", sensorData.headingAccuracy)
                data.put("pitch", sensorData.pitch)
                data.put("roll", sensorData.roll)
                data.put("timestamp", sensorData.timestamp)
                
                trigger("plugin:hillview:sensor-data", data)
            }
        }
        
        sensorService?.startSensor()
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

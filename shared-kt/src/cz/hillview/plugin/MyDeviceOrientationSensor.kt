
package cz.hillview.plugin

import android.content.Context
import android.util.Log
import android.view.OrientationEventListener

class MyDeviceOrientationSensor(
	private val context: Context,
	private val onOrientationChanged: ((DeviceOrientation) -> Unit)?
) {
	companion object {
		private const val TAG = "hv-MyDeviceOrientationSensor"
	}

	private var isSuspended: Boolean = false
	private var isStarted: Boolean = false

	private var deviceOrientationListener: OrientationEventListener? = null
	private var currentDeviceOrientation: DeviceOrientation = DeviceOrientation.PORTRAIT


	fun setSuspended(suspended: Boolean) {
		isSuspended = suspended
		handleConfigChange()
	}

	fun setRunning(running: Boolean) {
		isStarted = running
		handleConfigChange()
	}

	fun triggerDeviceOrientationEvent() {
		Log.d(TAG, "📱 device-orientation triggerOrientationEvent: $currentDeviceOrientation")
		onOrientationChanged?.invoke(currentDeviceOrientation)
	}


	private fun handleConfigChange() {
		Log.d(TAG, "📱 device-orientation handleConfigChange: isStarted=$isStarted, isSuspended=$isSuspended")
		if (isStarted && !isSuspended) {
			handleStartDeviceOrientationSensor()
		} else {
			handleStopDeviceOrientationSensor()
		}
	}

	private fun handleStartDeviceOrientationSensor() {
		Log.d(TAG, "📱 device-orientation handleStartDeviceOrientationSensor")
		if (deviceOrientationListener == null) {
			Log.d(TAG, "📱 device-orientation initiliazing sensor listener")
			deviceOrientationListener = object : OrientationEventListener(context) {
				override fun onOrientationChanged(orientation: Int) {
					//Log.d(TAG, "📱 device-orientation onOrientationChanged")
					val newOrientation = DeviceOrientation.fromDegrees(orientation)
					if (newOrientation != currentDeviceOrientation && newOrientation != DeviceOrientation.FLAT_UP && newOrientation != DeviceOrientation.FLAT_DOWN) {
						Log.d(TAG, "📱 device-orientation exif changed: $currentDeviceOrientation → $newOrientation")
						currentDeviceOrientation = newOrientation
						triggerDeviceOrientationEvent()
					}
				}
			}
			Log.d(TAG, "📱 device-orientation sensor initialized")
		}
		deviceOrientationListener?.enable()
	}

	private fun handleStopDeviceOrientationSensor() {
		Log.d(TAG, "📱 device-orientation handleStopDeviceOrientationSensor")
		deviceOrientationListener?.disable()
	}

}

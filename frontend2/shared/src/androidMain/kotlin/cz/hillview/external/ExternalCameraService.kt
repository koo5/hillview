package cz.hillview.external

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat
import cz.hillview.geo.GeoConfig
import cz.hillview.geo.GeoEngine
import cz.hillview.geo.externalCameraConfig
import cz.hillview.plugin.GeoTrackingManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

private const val TAG = "hv-ExternalCamera"

/**
 * The external-camera mode's engine: sensors and GPS run CONTINUOUSLY into
 * the tracking tables while the user shoots with the SYSTEM camera app —
 * this is the deliberate divergence from the capture activity, which
 * optimizes around capture moments. The tables/CSVs then stamp the external
 * photos retroactively (the pics pipeline's pairing; in-app pairing reads
 * getLocationNearTimestamp).
 *
 * A foreground service with the `location` type, because the whole point is
 * to keep recording while ANOTHER app owns the foreground. Periodic dumps
 * give crash-safety on long sessions: dumpAndClear() exports everything and
 * keeps the trailing five minutes, so consecutive CSVs overlap by up to
 * five minutes and the pipeline dedups on (timestamp, source).
 *
 * Both tables run with "android" elected — starting this mode IS the user
 * act that elects the live sensors. The Kalman heading filter is fed too,
 * so gps-kalman rows exist for a post-hoc car-mode re-election.
 */
class ExternalCameraService : Service() {

	companion object {
		/** The screen's switch state — service-owned, survives navigation. */
		val running = MutableStateFlow(false)

		/** One-line live status for the screen: fix, accuracy, heading. */
		val statusLine = MutableStateFlow("waiting for data…")

		const val ACTION_STOP = "cz.hillview.external.STOP"
		private const val CHANNEL_ID = "external_camera"
		private const val NOTIFICATION_ID = 3001
		private const val DUMP_INTERVAL_MS = 5 * 60 * 1000L

		fun start(context: Context) {
			ContextCompat.startForegroundService(
				context, Intent(context, ExternalCameraService::class.java),
			)
		}

		fun stop(context: Context) {
			context.stopService(Intent(context, ExternalCameraService::class.java))
		}
	}

	private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

	@Volatile private var lastFixLine: String = "no fix yet"

	override fun onBind(intent: Intent?): IBinder? = null

	override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
		if (intent?.action == ACTION_STOP) {
			stopSelf()
			return START_NOT_STICKY
		}
		if (running.value) return START_STICKY

		startInForeground()

		// This service owns PROCESS LIFETIME, not data: it keeps the app
		// alive with a notification while the system camera app is in front.
		// The one GeoEngine owns the hardware and the table writes — the
		// service just tells it what to run. (It used to construct its own
		// sensor and location services, which is how this pane came to show
		// a compass reading that was not the app's.)
		val engine = GeoEngine.get(this)
		engine.configure(externalCameraConfig(), cz.hillview.geo.OWNER_EXTERNAL_SERVICE)
		scope.launch {
			engine.location.collect { fix ->
				fix ?: return@collect
				lastFixLine = "%.6f, %.6f ±%.0f m".format(fix.latitude, fix.longitude, fix.accuracy)
				publishStatus()
			}
		}

		running.value = true
		Log.i(TAG, "external-camera tracking started")

		scope.launch {
			while (isActive) {
				delay(DUMP_INTERVAL_MS)
				// Crash-safety on long sessions; respects the auto_export pref.
				GeoTrackingManager.get(this@ExternalCameraService).dumpAndClear()
			}
		}
		return START_STICKY
	}

	private fun publishStatus() {
		// The FIX only. The heading used to be published here too, straight
		// from the engine's raw sample, and it was the app's second opinion
		// about where the phone points: the pane's stamp line shows the
		// elected bearing (what a photo records, what the map arrow uses),
		// and a second number beside it that answers to different rules is
		// how "the compass is stuck here but fine there" became a puzzle.
		// One value, from the same state as everywhere else; the raw side
		// belongs in the geo debug readout, which exists for it.
		statusLine.value = lastFixLine
	}

	private fun startInForeground() {
		val manager = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
			manager.createNotificationChannel(
				NotificationChannel(
					CHANNEL_ID,
					"External camera tracking",
					NotificationManager.IMPORTANCE_LOW,
				).apply {
					description = "Location and heading recording while shooting with another camera app"
				},
			)
		}
		val openApp = packageManager.getLaunchIntentForPackage(packageName)?.let {
			PendingIntent.getActivity(this, 0, it, PendingIntent.FLAG_IMMUTABLE)
		}
		val stopIntent = PendingIntent.getService(
			this, 1,
			Intent(this, ExternalCameraService::class.java).setAction(ACTION_STOP),
			PendingIntent.FLAG_IMMUTABLE,
		)
		val notification: Notification =
			(if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
				Notification.Builder(this, CHANNEL_ID)
			} else {
				@Suppress("DEPRECATION") Notification.Builder(this)
			})
				.setContentTitle("Recording location & heading")
				.setContentText("For stamping photos from your camera app")
				.setSmallIcon(android.R.drawable.ic_menu_mylocation)
				.setOngoing(true)
				.setContentIntent(openApp)
				.addAction(
					Notification.Action.Builder(null, "Stop", stopIntent).build(),
				)
				.build()
		if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
			startForeground(
				NOTIFICATION_ID, notification,
				ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION,
			)
		} else {
			startForeground(NOTIFICATION_ID, notification)
		}
	}

	override fun onDestroy() {
		scope.cancel()
		// Stop ASKING for the hardware — not turn it off. This used to
		// configure the engine Off on the assumption that MainScreen would
		// then set whatever the next activity wants, which is only true if
		// MainScreen goes second: leaving external for capture, the two race,
		// and losing means the capture pane's compass never starts.
		try {
			GeoEngine.get(this).release(cz.hillview.geo.OWNER_EXTERNAL_SERVICE)
		} catch (e: Exception) {
			Log.w(TAG, "engine stop failed", e)
		}
		// Session end = dump, same contract as the capture pane's release().
		try {
			GeoTrackingManager.get(this).dumpAndClear()
		} catch (e: Exception) {
			Log.w(TAG, "end-of-session dump failed", e)
		}
		running.value = false
		statusLine.value = "stopped"
		Log.i(TAG, "external-camera tracking stopped")
		super.onDestroy()
	}
}

package cz.hillview

import android.app.Application
import cz.hillview.auth.SessionManager
import cz.hillview.di.initKoin
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.koin.android.ext.koin.androidContext
import org.koin.core.context.GlobalContext

// Known environment limit, verified 2026-08-05: on the API-31 emulator image,
// CameraX 1.6's camera-pipe implementation loses still-capture callbacks (its
// frame tracking trips over the emulated camera's timestamps —
// "onOutputStarted was invoked multiple times"); Camera2Config no longer
// selects a legacy implementation in 1.6, and MINIMIZE_LATENCY doesn't help.
// Capture e2e needs an API-34+ image (API 36 verified); the capture watchdog
// in PhotoCapture keeps the shutter usable regardless.
class HillviewApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        // Before anything of ours can claim a photo — see StartupReconciler.
        val processStart = System.currentTimeMillis()
        // Build-configured photo folder (HILLVIEW_FOLDER / debug default) —
        // see androidApp/build.gradle.kts.
        cz.hillview.capture.PhotoStorage.folderBase = BuildConfig.HILLVIEW_FOLDER
        // Native Sign in with Google — empty keeps the button hidden.
        cz.hillview.auth.NativeAuthConfig.googleServerClientId =
            BuildConfig.HILLVIEW_GOOGLE_CLIENT_ID
        // The UploadSettingsRepository (createdAtStart) materializes the
        // upload-settings prefs the shared-kt stack reads.
        initKoin {
            androidContext(this@HillviewApplication)
        }

        // Starting anew means nothing from the previous process is running —
        // no refinement will finish, no upload is in flight. Spend that
        // certainty instead of waiting deadlines out: release refinement
        // holds and hand back photos stuck mid-upload. processStart is
        // captured at the top of onCreate, before anything of ours could
        // have claimed a photo.
        //
        // FIRST, and the geo dump below waits for it. These two used to launch
        // as independent coroutines and race each other; separate database
        // files (v18) mean they can no longer block each other in SQLite, but
        // the order still matters for a plainer reason — this is two fast
        // UPDATEs that the upload schedule depends on, and the dump is a
        // whole-table read plus a CSV write. Cheap work that something waits
        // on goes before expensive work that nothing waits on.
        cz.hillview.plugin.StartupReconciler.run(this, processStart)

        // App-start geo dump, as the Tauri plugin's init does — a crash or
        // swipe-away skips the session-end dump; this catches up (only
        // exports when auto_export is on; clears either way).
        appScope.launch {
            try {
                cz.hillview.plugin.GeoTrackingManager.get(this@HillviewApplication).dumpAndClear()
            } catch (e: Exception) {
                android.util.Log.w("hv-HillviewApp", "start-time geo dump failed", e)
            }
        }

        // Lockstep logout: whichever shared-kt AuthenticationManager instance
        // (upload worker, status sync, UI store) declares the session dead,
        // the Compose UI drops to LoggedOut immediately — the same wiring the
        // Tauri plugin does toward its WebView. The static callback matches
        // the shared prefs' process-wide scope.
        val session = GlobalContext.get().get<SessionManager>()
        cz.hillview.plugin.AuthenticationManager.onSessionExpired = {
            appScope.launch { session.onPlatformSessionExpired() }
        }
    }

    companion object {
        private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    }
}

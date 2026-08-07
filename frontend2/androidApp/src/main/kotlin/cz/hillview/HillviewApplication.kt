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

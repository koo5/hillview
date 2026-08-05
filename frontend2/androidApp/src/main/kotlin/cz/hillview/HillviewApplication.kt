package cz.hillview

import android.app.Application
import cz.hillview.di.initKoin
import org.koin.android.ext.koin.androidContext

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
        // The UploadSettingsRepository (createdAtStart) materializes the
        // upload-settings prefs the shared-kt stack reads.
        initKoin {
            androidContext(this@HillviewApplication)
        }
    }
}

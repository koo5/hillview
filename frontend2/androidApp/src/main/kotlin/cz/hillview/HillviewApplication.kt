package cz.hillview

import android.app.Application
import cz.hillview.core.net.BackendConfig
import cz.hillview.di.initKoin
import cz.hillview.upload.seedUploadSettings
import org.koin.android.ext.koin.androidContext
import org.koin.core.context.GlobalContext

class HillviewApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        initKoin {
            androidContext(this@HillviewApplication)
        }
        // Defaults for the shared-kt upload stack's settings prefs; must run
        // before first login (key registration reads server_url).
        seedUploadSettings(this, GlobalContext.get().get<BackendConfig>())
    }
}

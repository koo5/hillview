package cz.hillview.di

import cz.hillview.auth.AuthApi
import cz.hillview.auth.LoginViewModel
import cz.hillview.auth.SessionManager
import cz.hillview.auth.TokenStore
import cz.hillview.core.net.BackendConfig
import cz.hillview.core.net.createHttpClient
import cz.hillview.core.net.defaultBackendConfig
import org.koin.core.context.startKoin
import org.koin.core.module.Module
import org.koin.core.module.dsl.viewModel
import org.koin.dsl.KoinAppDeclaration
import org.koin.dsl.module

/** Platform-specific bindings: [TokenStore], [cz.hillview.upload.UploadPipeline]. */
expect fun platformModule(): Module

val appModule = module {
    // The API URL has ONE home: the settings repository. defaultBackendConfig()
    // only supplies the platform default for a fresh install (see the
    // repository bindings). Resolved once at startup — a URL edit in settings
    // reaches auth on next app start; the upload stack reads it per drain.
    single<BackendConfig> {
        BackendConfig(get<cz.hillview.settings.UploadSettingsRepository>().settings.value.serverUrl)
    }
    single { createHttpClient() }
    single { AuthApi(get(), get()) }
    single { SessionManager(get(), get()) }
    // Kept for the jvm backend-contract tests; the app's upload path is the
    // platform UploadPipeline (shared-kt stack on Android).
    single { cz.hillview.upload.PhotoUploadApi(get(), get(), get()) }
    // One per process: tracking has to survive moving between the map and
    // capture, which is a different lifetime from either screen.
    single { cz.hillview.map.MapSession() }
    // The live map camera/bearing state — ONE holder, shared by the map
    // pane and the capture pane (follow-me, the manual-position claim),
    // restored from the persisted store at first use. The Tauri app has the
    // same shape: one spatialState store, everything reads and writes it.
    // The sink is the funnel's persist boundary: the election and the
    // tracking row for user-set values are side effects of the state write,
    // so they cannot drift apart. Android binds RoomTrackingSink in its
    // platform module; desktop keeps the no-op default.
    single {
        val sink = getOrNull<cz.hillview.map.TrackingSink>() ?: cz.hillview.map.TrackingSink.Noop
        get<cz.hillview.map.MapStateStore>().load()
            ?.let { (spatial, bearing) -> cz.hillview.map.MapStateHolder(spatial, bearing, sink) }
            ?: cz.hillview.map.MapStateHolder(sink = sink)
    }
    // Shared by the map (greying) and the viewer pane (which photos are in
    // the navigable ring) — see MapFilterState.
    single {
        cz.hillview.map.MapFilterState(
            settings = get(),
            scope = kotlinx.coroutines.CoroutineScope(
                kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.Default,
            ),
        )
    }
    viewModel { LoginViewModel(get(), get()) }
}

fun initKoin(config: KoinAppDeclaration? = null) {
    startKoin {
        config?.invoke(this)
        modules(platformModule(), appModule)
    }
}

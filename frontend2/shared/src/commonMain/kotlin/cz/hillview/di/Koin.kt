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
    viewModel { LoginViewModel(get()) }
}

fun initKoin(config: KoinAppDeclaration? = null) {
    startKoin {
        config?.invoke(this)
        modules(platformModule(), appModule)
    }
}

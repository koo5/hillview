package cz.hillview.di

import android.content.Context
import cz.hillview.auth.StoredTokens
import cz.hillview.auth.TokenStore
import cz.hillview.core.net.backendJson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.koin.android.ext.koin.androidContext
import org.koin.core.module.Module
import org.koin.dsl.module

private class SharedPrefsTokenStore(context: Context) : TokenStore {
    private val prefs = context.getSharedPreferences("hillview_session", Context.MODE_PRIVATE)

    override suspend fun load(): StoredTokens? = withContext(Dispatchers.IO) {
        prefs.getString("tokens", null)?.let {
            try {
                backendJson.decodeFromString(StoredTokens.serializer(), it)
            } catch (e: Exception) {
                null
            }
        }
    }

    override suspend fun save(tokens: StoredTokens) = withContext(Dispatchers.IO) {
        prefs.edit()
            .putString("tokens", backendJson.encodeToString(StoredTokens.serializer(), tokens))
            .apply()
    }

    override suspend fun clear() = withContext(Dispatchers.IO) {
        prefs.edit().remove("tokens").apply()
    }
}

actual fun platformModule(): Module = module {
    single<TokenStore> { SharedPrefsTokenStore(androidContext()) }
    // Captures go to the shared-kt upload stack — the same code the Tauri
    // app runs. See /shared-kt/README.md.
    single<cz.hillview.upload.UploadPipeline> {
        cz.hillview.upload.SharedStackUploadPipeline(androidContext())
    }
}

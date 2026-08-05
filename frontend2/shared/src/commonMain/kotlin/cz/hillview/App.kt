package cz.hillview

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import androidx.navigation3.runtime.NavKey
import androidx.navigation3.runtime.entryProvider
import androidx.navigation3.runtime.rememberNavBackStack
import androidx.navigation3.ui.NavDisplay
import androidx.savedstate.serialization.SavedStateConfiguration
import cz.hillview.auth.ui.LoginScreen
import cz.hillview.capture.CaptureScreen
import cz.hillview.clockvideo.ClockVideoScreen
import cz.hillview.core.theme.HillviewTheme
import cz.hillview.home.HomeScreen
import cz.hillview.nav.CaptureKey
import cz.hillview.nav.ClockVideoKey
import cz.hillview.nav.HomeKey
import cz.hillview.nav.LoginKey
import cz.hillview.nav.SettingsKey
import cz.hillview.settings.ui.SettingsScreen
import kotlinx.serialization.modules.SerializersModule
import kotlinx.serialization.modules.polymorphic
import kotlinx.serialization.modules.subclass

// Registration point for every route key — the back stack serializes across
// process death, and NavKey polymorphism must be declared explicitly.
private val navSavedStateConfig = SavedStateConfiguration {
    serializersModule = SerializersModule {
        polymorphic(NavKey::class) {
            subclass(HomeKey::class)
            subclass(LoginKey::class)
            subclass(ClockVideoKey::class)
            subclass(CaptureKey::class)
            subclass(SettingsKey::class)
        }
    }
}

@Composable
@Preview
fun App() {
    HillviewTheme {
        val backStack = rememberNavBackStack(navSavedStateConfig, HomeKey)
        NavDisplay(
            backStack = backStack,
            onBack = { backStack.removeLastOrNull() },
            entryProvider = entryProvider {
                entry<HomeKey> {
                    HomeScreen(
                        onOpenLogin = { backStack.add(LoginKey) },
                        onOpenClockVideo = { backStack.add(ClockVideoKey) },
                        onOpenCapture = { backStack.add(CaptureKey) },
                        onOpenSettings = { backStack.add(SettingsKey) },
                    )
                }
                entry<SettingsKey> {
                    SettingsScreen(onBack = { backStack.removeLastOrNull() })
                }
                entry<CaptureKey> {
                    CaptureScreen(onBack = { backStack.removeLastOrNull() })
                }
                entry<LoginKey> {
                    LoginScreen(
                        onBack = { backStack.removeLastOrNull() },
                        onLoggedIn = { backStack.removeLastOrNull() },
                    )
                }
                entry<ClockVideoKey> {
                    ClockVideoScreen(onBack = { backStack.removeLastOrNull() })
                }
            },
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background),
        )
    }
}

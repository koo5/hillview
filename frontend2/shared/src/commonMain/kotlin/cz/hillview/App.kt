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
import cz.hillview.clockvideo.ClockVideoScreen
import cz.hillview.core.theme.HillviewTheme
import cz.hillview.main.MainScreen
import cz.hillview.nav.CaptureGuideKey
import cz.hillview.nav.UploadStatusKey
import cz.hillview.nav.EventLogKey
import cz.hillview.nav.CaptureKey
import cz.hillview.nav.ClockVideoKey
import cz.hillview.nav.DevicePhotosKey
import cz.hillview.nav.HomeKey
import cz.hillview.nav.LoginKey
import cz.hillview.nav.MainKey
import cz.hillview.nav.MapKey
import cz.hillview.nav.SettingsKey
import cz.hillview.settings.ui.SettingsScreen
import kotlinx.serialization.modules.SerializersModule
import kotlinx.serialization.modules.polymorphic
import kotlinx.serialization.modules.subclass

// Registration point for every route key — the back stack serializes across
// process death, and NavKey polymorphism must be declared explicitly.
// The legacy keys (Home/Map/Capture) stay registered so a stack persisted
// by a pre-merge build still deserializes; their entries alias to Main.
private val navSavedStateConfig = SavedStateConfiguration {
    serializersModule = SerializersModule {
        polymorphic(NavKey::class) {
            subclass(MainKey::class)
            subclass(HomeKey::class)
            subclass(LoginKey::class)
            subclass(ClockVideoKey::class)
            subclass(CaptureKey::class)
            subclass(SettingsKey::class)
            subclass(DevicePhotosKey::class)
            subclass(MapKey::class)
        }
    }
}

@Composable
@Preview
fun App() {
    HillviewTheme {
        val backStack = rememberNavBackStack(navSavedStateConfig, MainKey)
        // The ONE way off a screen. NavDisplay throws the moment the back
        // stack is empty, and a bare removeLastOrNull() gets there on the
        // second of two pops: a double-tapped "← Back", or the button and
        // the system back gesture landing together (the gesture lives
        // along the same edge as the button) — [Main, X] → [Main] → [] →
        // crash, from any screen. Field-caught on the Uploads screen; the
        // root entry is never popped here, so the second pop is a no-op.
        val pop: () -> Unit = { if (backStack.size > 1) backStack.removeLastOrNull() }
        val main: @Composable () -> Unit = {
            MainScreen(
                onOpenSettings = { backStack.add(SettingsKey) },
                onOpenLogin = { backStack.add(LoginKey) },
                onOpenClockVideo = { backStack.add(ClockVideoKey) },
                onOpenDevicePhotos = { backStack.add(DevicePhotosKey) },
                onOpenCaptureGuide = { backStack.add(CaptureGuideKey) },
                onOpenUploadStatus = { backStack.add(UploadStatusKey) },
                onOpenEventLog = { backStack.add(EventLogKey) },
            )
        }
        NavDisplay(
            backStack = backStack,
            onBack = { pop() },
            entryProvider = entryProvider {
                entry<MainKey> { main() }
                // Legacy aliases — see navSavedStateConfig.
                entry<HomeKey> { main() }
                entry<MapKey> { main() }
                entry<CaptureKey> { main() }
                entry<SettingsKey> {
                    SettingsScreen(
                        onBack = { pop() },
                        onOpenLogin = { backStack.add(LoginKey) },
                    )
                }
                entry<DevicePhotosKey> {
                    cz.hillview.devicephotos.DevicePhotosScreen(
                        onBack = { pop() },
                    )
                }
                entry<LoginKey> {
                    LoginScreen(
                        onBack = { pop() },
                        onLoggedIn = { pop() },
                    )
                }
                entry<EventLogKey> {
                    cz.hillview.diag.EventLogScreen(
                        onBack = { pop() },
                    )
                }
                entry<UploadStatusKey> {
                    cz.hillview.upload.ui.UploadStatusScreen(
                        onBack = { pop() },
                    )
                }
                entry<CaptureGuideKey> {
                    cz.hillview.help.CaptureGuideScreen(
                        onBack = { pop() },
                    )
                }
                entry<ClockVideoKey> {
                    ClockVideoScreen(onBack = { pop() })
                }
            },
            modifier = Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background),
        )
    }
}

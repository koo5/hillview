package cz.hillview

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
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
import cz.hillview.lock.ApplyControlsLock
import cz.hillview.lock.ControlsLock
import cz.hillview.lock.ControlsLockScrim
import cz.hillview.lock.LockSettingsScreen
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
import cz.hillview.nav.LockSettingsKey
import cz.hillview.nav.MapKey
import cz.hillview.nav.SettingsKey
import cz.hillview.settings.lockOptions
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
            subclass(LockSettingsKey::class)
            subclass(EventLogKey::class)
            subclass(UploadStatusKey::class)
            subclass(CaptureGuideKey::class)
        }
    }
}

@Composable
@Preview
fun App() {
    val controlsLock: ControlsLock = org.koin.compose.koinInject()
    val settingsRepo: cz.hillview.settings.MapSettingsRepository = org.koin.compose.koinInject()
    val locked by controlsLock.locked.collectAsState()
    val appSettings by settingsRepo.settings.collectAsState()
    val lockOptions = appSettings.lockOptions()

    // The window effects and the theme both live OUTSIDE the nav display, so
    // locking survives whatever screen happens to be on top — a lock that
    // came off because a settings page was open would protect nothing.
    ApplyControlsLock(active = locked, options = lockOptions)
    HillviewTheme(
        darkTheme = androidx.compose.foundation.isSystemInDarkTheme() ||
            (locked && lockOptions.darkTheme),
    ) {
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
                onOpenLockSettings = { backStack.add(LockSettingsKey) },
            )
        }
        androidx.compose.foundation.layout.Box(Modifier.fillMaxSize()) {
        NavDisplay(
            backStack = backStack,
            onBack = { pop() },
            entryProvider = entryProvider {
                entry<MainKey> { main() }
                // Legacy aliases — see navSavedStateConfig.
                entry<HomeKey> { main() }
                entry<MapKey> { main() }
                entry<CaptureKey> { main() }
                entry<LockSettingsKey> {
                    LockSettingsScreen(onBack = { pop() })
                }
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
        // Over EVERYTHING, including whatever screen the back stack has on
        // top. The pocket does not know which screen is showing.
        if (locked) {
            ControlsLockScrim(onUnlock = { controlsLock.unlock() })
        }
        }
    }
}

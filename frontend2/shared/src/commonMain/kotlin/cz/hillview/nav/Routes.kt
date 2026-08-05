package cz.hillview.nav

import androidx.navigation3.runtime.NavKey
import kotlinx.serialization.Serializable

// Route keys for the whole app; screens beyond P0 arrive with their phases.
// Serializable so the back stack survives process death.

@Serializable
data object HomeKey : NavKey

@Serializable
data object LoginKey : NavKey

@Serializable
data object ClockVideoKey : NavKey

@Serializable
data object CaptureKey : NavKey

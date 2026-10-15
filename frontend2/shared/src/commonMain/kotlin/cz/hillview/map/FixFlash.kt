package cz.hillview.map

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.delay

/** How long the location button stays lit after a fix: the original's 100 ms. */
const val FIX_FLASH_MS = 100L

/**
 * The location button's per-fix flash: lit for [FIX_FLASH_MS] after the
 * latest of [fixes], a count the fix callback bumps once per fix.
 *
 * Keyed on a COUNT, never on the flag itself. It used to be a boolean that
 * the fix callback set and a `LaunchedEffect(flag)` cleared 100 ms later,
 * and that sticks: when the clear lands and the next fix sets the flag again
 * before a frame recomposes, the composition sees `true` twice running, the
 * effect is not restarted, and nothing ever clears it again. The button then
 * stayed green whatever the tracking state under it (user, 2026-10-11: "it
 * stays green no matter how many times i click it"). Without frames — the
 * app in the background while the fix stream keeps running — the gap
 * between the clear and the next fix is seconds wide, not a frame.
 *
 * A count cannot repeat, so every fix restarts the effect, which is what the
 * original's clearTimeout + setTimeout did (Map.svelte:1135).
 */
@Composable
fun rememberFixFlash(fixes: Long): Boolean {
    var lit by remember { mutableStateOf(false) }
    LaunchedEffect(fixes) {
        if (fixes == 0L) return@LaunchedEffect
        lit = true
        delay(FIX_FLASH_MS)
        lit = false
    }
    return lit
}

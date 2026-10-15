package cz.hillview.map

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.v2.runComposeUiTest
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The location button's per-fix flash goes out after every fix, however the
 * fixes fall against the frames (user, 2026-10-11: "it stays green no matter
 * how many times i click it"). See [rememberFixFlash].
 */
@OptIn(ExperimentalTestApi::class)
class FixFlashTest {

    @Test
    fun theFlashGoesOutWhereverTheNextFixLands() = runComposeUiTest {
        mainClock.autoAdvance = false
        var fixes by mutableStateOf(0L)
        var lit = false
        setContent { lit = rememberFixFlash(fixes) }

        assertFalse(lit, "no fix yet, no flash")
        // A second fix at every millisecond offset from the first: the old
        // flag stuck when one landed between the clear and the next frame,
        // a window a frame wide. Stepping one ms at a time, past the
        // flash's own length, walks a fix through every part of it.
        for (gapMs in 1L..2 * FIX_FLASH_MS) {
            fixes++
            mainClock.advanceTimeBy(gapMs, ignoreFrameDuration = true)
            fixes++
            mainClock.advanceTimeBy(FIX_FLASH_MS / 2)
            assertTrue(lit, "gap $gapMs ms: the second fix flashes")
            mainClock.advanceTimeBy(5 * FIX_FLASH_MS)
            assertFalse(lit, "gap $gapMs ms: the flash went out")
        }
    }

    @Test
    fun fixesWithNoFramesBetweenThemFlashOnceAndGoOut() = runComposeUiTest {
        // The background case: the fix stream keeps running while nothing
        // draws, so many fixes land with no recomposition between them.
        mainClock.autoAdvance = false
        var fixes by mutableStateOf(0L)
        var lit = false
        setContent { lit = rememberFixFlash(fixes) }

        repeat(50) { fixes++ }
        mainClock.advanceTimeBy(FIX_FLASH_MS / 2)
        assertTrue(lit)
        mainClock.advanceTimeBy(5 * FIX_FLASH_MS)
        assertFalse(lit)
    }
}

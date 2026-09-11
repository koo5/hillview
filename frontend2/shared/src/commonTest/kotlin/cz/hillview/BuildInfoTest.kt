package cz.hillview

import kotlin.test.Test
import kotlin.test.assertEquals

class BuildInfoTest {

    @Test
    fun aCleanBuildIsVersionCommitAndCommitTime() {
        assertEquals(
            "0.1.0 · a0bc3a1c · 2026-08-27T02:58:11+02:00",
            buildLabel("0.1.0", "a0bc3a1c", "2026-08-27T02:58:11+02:00", dirty = false, dirtyHash = ""),
        )
    }

    @Test
    fun aDirtyTreeSaysSoAndCarriesTheDiffHash() {
        // Two dirty builds of different edits must not read the same.
        assertEquals(
            "0.1.0 · a0bc3a1c+1f2e3d4c (uncommitted) · 2026-08-27T02:58:11+02:00",
            buildLabel("0.1.0", "a0bc3a1c", "2026-08-27T02:58:11+02:00", dirty = true, dirtyHash = "1f2e3d4c"),
        )
    }

    @Test
    fun withoutGitTheBuildIsUnknownNotBlank() {
        assertEquals("dev · unknown build", buildLabel("", "", "", dirty = false, dirtyHash = ""))
    }
}

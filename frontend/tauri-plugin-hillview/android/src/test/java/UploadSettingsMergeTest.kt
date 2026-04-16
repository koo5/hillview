package cz.hillview.plugin

import app.tauri.plugin.JSObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/**
 * Regression tests for set_settings merge semantics.
 *
 * The bug these guard against: JSObject.getBoolean(key) (one-arg) returns `false`
 * for missing keys, and the Elvis fallback `... ?: true` is dead code on a
 * non-nullable Boolean. Result: partial params objects from the frontend
 * silently zeroed out unspecified settings like auto_upload_prompt_enabled and
 * wifi_only on every app restart with no license.
 */
class UploadSettingsMergeTest {

    private val allTrue = MergedUploadSettings(
        autoUploadEnabled = true,
        autoUploadPromptEnabled = true,
        autoUploadLicense = "ccbysa4",
        wifiOnly = true,
        landscapeArmor22 = true,
    )

    @Test
    fun partialParams_preservesUnspecifiedStoredFields() {
        val params = JSObject().apply {
            put("auto_upload_enabled", false)
            // Other keys deliberately missing.
        }

        val merged = mergeUploadSettings(params, allTrue)

        assertFalse("the one field explicitly sent should take effect", merged.autoUploadEnabled)
        assertEquals("missing prompt_enabled must keep previous true", true, merged.autoUploadPromptEnabled)
        assertEquals("missing license must keep previous value", "ccbysa4", merged.autoUploadLicense)
        assertEquals("missing wifi_only must keep previous true", true, merged.wifiOnly)
        assertEquals("missing landscape_armor22 must keep previous true", true, merged.landscapeArmor22)
    }

    @Test
    fun emptyParams_returnsAllPreviousValues() {
        val previous = MergedUploadSettings(
            autoUploadEnabled = true,
            autoUploadPromptEnabled = false,
            autoUploadLicense = "ccbysa4",
            wifiOnly = true,
            landscapeArmor22 = true,
        )

        val merged = mergeUploadSettings(JSObject(), previous)

        assertEquals(previous, merged)
    }

    @Test
    fun fullParams_allFieldsTakeEffect() {
        val previous = MergedUploadSettings(
            autoUploadEnabled = false,
            autoUploadPromptEnabled = true,
            autoUploadLicense = null,
            wifiOnly = false,
            landscapeArmor22 = false,
        )
        val params = JSObject().apply {
            put("auto_upload_enabled", true)
            put("auto_upload_prompt_enabled", false)
            put("wifi_only", true)
            put("landscape_armor22_workaround", true)
        }

        val merged = mergeUploadSettings(params, previous)

        assertEquals(true, merged.autoUploadEnabled)
        assertEquals(false, merged.autoUploadPromptEnabled)
        assertEquals(true, merged.wifiOnly)
        assertEquals(true, merged.landscapeArmor22)
    }

    @Test
    fun explicitFalse_isRespected_notTreatedAsMissing() {
        // Regression: ensure sending false explicitly doesn't get confused with "key missing"
        // and fall back to the previous value.
        val params = JSObject().apply {
            put("auto_upload_enabled", false)
            put("auto_upload_prompt_enabled", false)
            put("wifi_only", false)
            put("landscape_armor22_workaround", false)
        }

        val merged = mergeUploadSettings(params, allTrue)

        assertFalse(merged.autoUploadEnabled)
        assertFalse(merged.autoUploadPromptEnabled)
        assertFalse(merged.wifiOnly)
        assertFalse(merged.landscapeArmor22)
    }

    /**
     * Documents the pitfall that prompted the fix: the one-arg overload returns
     * `false` for a missing key, and Elvis (`?: true`) on a non-nullable Boolean
     * is dead code. If a future refactor reverts the fix, this test makes the
     * misuse visible.
     */
    @Test
    fun documentsPitfall_oneArgGetBoolean_returnsFalseForMissingKey() {
        val empty = JSObject()
        assertFalse(
            "JSObject.getBoolean(key) defaults to false for missing keys; do not use it for settings merges",
            empty.getBoolean("does_not_exist")
        )
    }
}

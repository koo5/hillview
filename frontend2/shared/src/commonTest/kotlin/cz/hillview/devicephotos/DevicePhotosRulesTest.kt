package cz.hillview.devicephotos

import androidx.compose.ui.graphics.Color
import kotlin.test.Test
import kotlin.test.assertEquals

class DevicePhotosRulesTest {

    @Test
    fun fileSizesFormatLikeTheOriginal() {
        // toFixed(2) + parseFloat: two decimals, trailing zeros stripped.
        assertEquals("0 B", formatFileSize(0))
        assertEquals("512 B", formatFileSize(512))
        assertEquals("1 KB", formatFileSize(1024))
        assertEquals("1.5 KB", formatFileSize(1536))
        assertEquals("2.35 MB", formatFileSize((2.35 * 1024 * 1024).toLong()))
        assertEquals("3 GB", formatFileSize(3L * 1024 * 1024 * 1024))
    }

    @Test
    fun statusWordingIsTheOriginalUppercaseQuirksIncluded() {
        assertEquals("Completed", uploadStatusLabel("completed"))
        assertEquals("upload Pending", uploadStatusLabel("pending"))
        assertEquals("Uploading", uploadStatusLabel("uploading"))
        assertEquals("upload Failed", uploadStatusLabel("failed"))
        assertEquals("processing", uploadStatusLabel("processing"))
    }

    @Test
    fun statusColoursAreTheOriginalPalette() {
        assertEquals(Color(0xFF10B981), uploadStatusColor("completed"))
        assertEquals(Color(0xFFF59E0B), uploadStatusColor("pending"))
        assertEquals(Color(0xFF3B82F6), uploadStatusColor("uploading"))
        assertEquals(Color(0xFFEF4444), uploadStatusColor("failed"))
        assertEquals(Color(0xFF6B7280), uploadStatusColor("whatever"))
    }
}

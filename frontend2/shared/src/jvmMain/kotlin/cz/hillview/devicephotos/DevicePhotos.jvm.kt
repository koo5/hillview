package cz.hillview.devicephotos

import androidx.compose.foundation.layout.Box
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

/** Desktop can't capture, so there are no device photos to browse. */
class EmptyDevicePhotoBrowser : DevicePhotoBrowser {
    override suspend fun page(page: Int, pageSize: Int, filter: PhotoFilter): DevicePhotosPage =
        DevicePhotosPage(emptyList(), 0, hasMore = false, counts = StatusCounts(0, 0, 0))

    override suspend fun counts(): Map<PhotoFilter, Int> = emptyMap()

    override suspend fun delete(id: String, alsoFile: Boolean) {}

    override suspend fun retryUploads() {}
}

@Composable
actual fun PhotoThumbnail(locator: String, modifier: Modifier) {
    Box(modifier)
}

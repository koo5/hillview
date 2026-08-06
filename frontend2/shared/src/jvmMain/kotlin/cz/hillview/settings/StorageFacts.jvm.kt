package cz.hillview.settings

/** Desktop has no capture, so the storage choice is inert here. */
actual fun storageFacts(mode: StorageMode, hideFromGallery: Boolean) = StorageFacts(
    inGallery = false,
    fileManagerReachable = true,
    survivesUninstall = true,
    availableHere = false,
    note = "Photo capture is not available on desktop.",
)

package cz.hillview.upload

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * What the capture flow hands photos to. One real implementation:
 * SharedStackUploadPipeline (androidMain) hands captures to the shared-kt
 * stack (PhotoUploadLogic/PhotoUploadManager + WorkManager) — the same
 * battle-tested pipeline the Tauri app runs. See /shared-kt/README.md.
 * (The commonMain UploadQueue this seam once wrapped was retired to
 * /frontend2/attic — one Kotlin upload logic.)
 */
interface UploadPipeline {
    val stats: StateFlow<QueueStats>

    /** Hand a fresh capture to the pipeline. */
    suspend fun onPhotoCaptured(upload: PendingUpload)

    /**
     * Recompute [stats] for implementations that derive them from external
     * state (the shared-kt pipeline reads the Room DB); no-op where the
     * pipeline pushes its own stats.
     */
    suspend fun refreshStats() {}
}

/**
 * Desktop/tests: capture is unsupported on desktop, so there is nothing to
 * upload — the pipeline just records what it was handed.
 */
class NoopUploadPipeline : UploadPipeline {
    private val _stats = MutableStateFlow(QueueStats())
    override val stats: StateFlow<QueueStats> = _stats.asStateFlow()

    override suspend fun onPhotoCaptured(upload: PendingUpload) {
        _stats.value = _stats.value.copy(
            pending = _stats.value.pending + 1,
            lastError = "no upload pipeline on this platform",
        )
    }
}

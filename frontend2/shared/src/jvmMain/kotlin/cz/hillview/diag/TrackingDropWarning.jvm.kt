package cz.hillview.diag

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/** The tracking store lives in shared-kt, which is Android-only: nothing is ever dropped here. */
actual fun trackingDroppedRows(): StateFlow<Long> = never

// One instance: the composable calls this on every recomposition, and a new flow each
// time would restart its collection each time.
private val never = MutableStateFlow(0L)

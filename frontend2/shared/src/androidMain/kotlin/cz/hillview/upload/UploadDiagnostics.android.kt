package cz.hillview.upload

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import androidx.work.WorkInfo
import androidx.work.WorkManager
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoUploadManager
import cz.hillview.plugin.ScheduleAction
import cz.hillview.plugin.UploadGate
import cz.hillview.plugin.UploadQueueSnapshot
import cz.hillview.plugin.decideUploadSchedule
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.koin.core.context.GlobalContext

// The unique names PhotoUploadManager enqueues under. Duplicated as literals
// on purpose: this file only READS them, and a diagnostics page that silently
// followed a rename would report "nothing scheduled" instead of failing.
private const val WORK_NOW = "photo_upload_now"
private const val WORK_BATCH = "photo_upload_batch"

actual suspend fun collectUploadDiagnostics(): UploadDiagnostics = withContext(Dispatchers.IO) {
    val context: Context = GlobalContext.get().get()
    val rows = mutableListOf<DiagRow>()
    val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)

    // ---- the gates, in the order the drain itself checks them ----------
    val autoUpload = prefs.getBoolean("auto_upload_enabled", false)
    rows += DiagRow(
        "Auto-upload", if (autoUpload) "on" else "off",
        if (autoUpload) DiagVerdict.Ok else DiagVerdict.Blocking,
        note = if (autoUpload) null else "Nothing is enqueued while this is off.",
    )

    val licence = prefs.getString("auto_upload_license", null)
    rows += DiagRow(
        "Licence", licence ?: "not accepted",
        if (licence != null) DiagVerdict.Ok else DiagVerdict.Blocking,
        note = if (licence != null) null else "The drain refuses to upload without one.",
    )

    val loggedIn = runCatching {
        GlobalContext.get().get<cz.hillview.auth.SessionManager>().state.value
    }.getOrNull() is cz.hillview.auth.SessionState.LoggedIn
    rows += DiagRow(
        "Signed in", if (loggedIn) "yes" else "no",
        if (loggedIn) DiagVerdict.Ok else DiagVerdict.Blocking,
        note = if (loggedIn) null else "Photos stay queued until you sign in.",
    )

    rows += DiagRow("Server", prefs.getString("server_url", null) ?: "unset")

    // ---- the network rule, and whether reality satisfies it ------------
    val wifiOnly = prefs.getBoolean("wifi_only", false)
    val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    val caps = cm.activeNetwork?.let { cm.getNetworkCapabilities(it) }
    val hasWifi = caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
    val unmetered = caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) == true
    val validated = caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true

    rows += DiagRow(
        "Network rule",
        if (wifiOnly) "Wi-Fi only → requires UNMETERED" else "any connection",
        DiagVerdict.Info,
        note = if (wifiOnly) {
            "WorkManager has no \"Wi-Fi\" constraint — \"Wi-Fi only\" asks for an " +
                "UNMETERED network. A Wi-Fi the system treats as metered (a phone " +
                "hotspot, or one you marked metered) does NOT satisfy it."
        } else null,
    )
    rows += DiagRow(
        "This network",
        buildString {
            append(
                when {
                    caps == null -> "none"
                    hasWifi -> "Wi-Fi"
                    caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "mobile"
                    else -> "other"
                },
            )
            if (caps != null) append(if (unmetered) ", unmetered" else ", metered")
            if (caps != null && !validated) append(", no internet")
        },
        when {
            caps == null -> DiagVerdict.Blocking
            wifiOnly && !unmetered -> DiagVerdict.Blocking
            else -> DiagVerdict.Ok
        },
        note = if (wifiOnly && hasWifi && !unmetered) {
            "This IS Wi-Fi, but marked metered — which is exactly the case the " +
                "constraint refuses. Turn off Wi-Fi-only, or mark this network " +
                "unmetered in Android's network settings."
        } else null,
    )

    // Token life: an expired session is a silent blocker, and "signed in"
    // above only says a session EXISTS.
    val auth = context.getSharedPreferences("hillview_auth", Context.MODE_PRIVATE)
    auth.getString("expires_at", null)?.let { iso ->
        val until = runCatching {
            java.time.Instant.parse(iso).toEpochMilli() - System.currentTimeMillis()
        }.getOrNull()
        rows += DiagRow(
            "Access token",
            when {
                until == null -> iso
                until > 0 -> "valid for ${until / 60_000} min"
                else -> "EXPIRED ${-until / 60_000} min ago (refresh on next use)"
            },
            if (until != null && until <= 0) DiagVerdict.Info else DiagVerdict.Ok,
        )
    }

    // Free space on the volume captures land on: a full disk stops the
    // shutter, and nothing else in the app would say why.
    runCatching {
        val dir = cz.hillview.capture.PhotoStorage.publicDir(
            prefs.getBoolean("hide_from_gallery", false),
        )
        val stat = android.os.StatFs(
            (if (dir.exists()) dir else android.os.Environment.getExternalStorageDirectory()).path,
        )
        val freeMb = stat.availableBytes / (1024 * 1024)
        rows += DiagRow(
            "Free space", "$freeMb MB",
            if (freeMb < 200) DiagVerdict.Blocking else DiagVerdict.Ok,
            note = if (freeMb < 200) "Captures will start failing." else null,
        )
    }

    // ---- the queue ------------------------------------------------------
    val dao = PhotoDatabase.getDatabase(context).photoDao()
    val pending = dao.getPendingUploadCount()
    val failed = dao.getFailedUploadCount()
    rows += DiagRow(
        "Queue",
        "$pending pending · ${dao.getUploadingCount()} uploading · " +
            "${dao.getProcessingCount()} processing · $failed failed · " +
            "${dao.getCompletedUploadCount()} done",
        if (pending == 0 && failed == 0) DiagVerdict.Info else DiagVerdict.Info,
        note = if (pending == 0 && failed == 0) "Nothing waiting to go." else null,
    )

    // ---- the invariant, checked ----------------------------------------
    // Not a WorkManager fact but a JUDGEMENT: the same decision the reconciler
    // makes, compared against what is actually scheduled. This is the row that
    // can say "photos are waiting and NOTHING is scheduled" — which the raw
    // states below cannot, because a finished job reads as a tidy "succeeded"
    // whether or not it left the queue unattended.
    val scheduled = runCatching { PhotoUploadManager(context).scheduledWork() }.getOrNull()
    if (scheduled != null) {
        val decision = decideUploadSchedule(
            gate = UploadGate(
                autoUploadEnabled = autoUpload,
                hasLicense = licence != null,
                wifiOnly = wifiOnly,
            ),
            queue = UploadQueueSnapshot(waiting = pending + failed),
            existing = scheduled,
            leadingEdge = true,
            bypassWifiOnly = false,
        )
        rows += when (decision) {
            is ScheduleAction.Leave -> DiagRow(
                "Schedule", "matches — ${decision.why}", DiagVerdict.Ok,
            )
            is ScheduleAction.CancelAll -> if (scheduled.exists) {
                DiagRow(
                    "Schedule", "stale job queued — ${decision.why}", DiagVerdict.Info,
                    note = "It will be dropped at the next reconcile.",
                )
            } else {
                DiagRow("Schedule", "nothing scheduled — ${decision.why}", DiagVerdict.Ok)
            }
            // Reaching this means the reconciler has not run (or failed) since
            // whatever made the queue non-empty: uploads will NOT resume on
            // their own when the network comes back.
            is ScheduleAction.Ensure -> DiagRow(
                "Schedule", "MISSING — ${decision.why}", DiagVerdict.Blocking,
                note = "Nothing is waiting on the network, so a connection " +
                    "returning will not start an upload. Use Upload now, and " +
                    "report this — the schedule should never need a human.",
            )
        }
    }

    // ---- what WorkManager itself says ----------------------------------
    // State, next run and stop reason are WorkInfo fields: the scheduler is
    // asked rather than modelled.
    val wm = WorkManager.getInstance(context)
    for (name in listOf(WORK_NOW, WORK_BATCH)) {
        val infos = runCatching { wm.getWorkInfosForUniqueWork(name).get() }.getOrNull()
        val info = infos?.firstOrNull()
        if (info == null) {
            rows += DiagRow(name, "never scheduled", DiagVerdict.Info)
            continue
        }
        rows += DiagRow(
            name,
            buildString {
                append(info.state.name.lowercase())
                if (info.runAttemptCount > 0) append(" · attempt ${info.runAttemptCount}")
                if (Build.VERSION.SDK_INT >= 34 || true) {
                    val next = runCatching { info.nextScheduleTimeMillis }.getOrNull()
                    if (next != null && next != Long.MAX_VALUE) {
                        val inMs = next - System.currentTimeMillis()
                        append(
                            if (inMs > 0) " · runs in ${inMs / 1000}s"
                            else " · due (${-inMs / 1000}s ago)",
                        )
                    }
                }
                val stop = runCatching { info.stopReason }.getOrNull()
                if (stop != null && stop != WorkInfo.STOP_REASON_NOT_STOPPED) {
                    append(" · last stopped: ${stopReasonName(stop)}")
                }
            },
            when (info.state) {
                WorkInfo.State.ENQUEUED, WorkInfo.State.RUNNING -> DiagVerdict.Ok
                WorkInfo.State.BLOCKED -> DiagVerdict.Blocking
                else -> DiagVerdict.Info
            },
            note = if (info.state == WorkInfo.State.ENQUEUED && caps != null &&
                wifiOnly && !unmetered
            ) {
                "Enqueued and waiting for its constraint — the network above is why."
            } else null,
        )
    }

    // ---- the last drain, as the worker recorded it ---------------------
    val lastAt = prefs.getLong("last_drain_at", 0L)
    rows += if (lastAt == 0L) {
        DiagRow("Last drain", "never run this install", DiagVerdict.Info)
    } else {
        val ago = (System.currentTimeMillis() - lastAt) / 1000
        DiagRow(
            "Last drain",
            "${ago}s ago · trigger ${prefs.getString("last_drain_trigger", "?")} · " +
                (prefs.getString("last_drain_result", "?") ?: "?"),
            DiagVerdict.Info,
        )
    }

    UploadDiagnostics(rows, System.currentTimeMillis())
}

private fun stopReasonName(reason: Int): String = when (reason) {
    WorkInfo.STOP_REASON_CONSTRAINT_CONNECTIVITY -> "lost connectivity"
    WorkInfo.STOP_REASON_CONSTRAINT_CHARGING -> "lost charging"
    WorkInfo.STOP_REASON_CONSTRAINT_BATTERY_NOT_LOW -> "battery low"
    WorkInfo.STOP_REASON_DEVICE_STATE -> "device state (doze/standby)"
    WorkInfo.STOP_REASON_APP_STANDBY -> "app standby bucket"
    WorkInfo.STOP_REASON_QUOTA -> "out of quota"
    WorkInfo.STOP_REASON_TIMEOUT -> "timed out"
    WorkInfo.STOP_REASON_CANCELLED_BY_APP -> "cancelled by the app"
    WorkInfo.STOP_REASON_USER -> "stopped by the user"
    else -> "reason $reason"
}

actual suspend fun triggerUploadNow(): String = withContext(Dispatchers.IO) {
    val context: Context = GlobalContext.get().get()
    val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
    if (!prefs.getBoolean("auto_upload_enabled", false)) {
        // The shared drain gates on this too, so a button that appeared to
        // work would be lying.
        return@withContext "Auto-upload is off — turn it on in Settings first."
    }
    cz.hillview.plugin.PhotoUploadManager(context).startAutomaticUpload("retry_button")
    "Drain requested (ignores the Wi-Fi-only rule). Watch the queue below."
}

actual suspend fun pingBackend(): String = withContext(Dispatchers.IO) {
    val context: Context = GlobalContext.get().get()
    val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
    val base = prefs.getString("server_url", null)
        ?: return@withContext "No server configured."
    val started = System.currentTimeMillis()
    try {
        val conn = java.net.URI("$base/debug").toURL().openConnection()
            as java.net.HttpURLConnection
        conn.connectTimeout = 5_000
        conn.readTimeout = 5_000
        val code = conn.responseCode
        val ms = System.currentTimeMillis() - started
        conn.disconnect()
        if (code == 200) "Reachable — HTTP $code in ${ms}ms" else "Answered HTTP $code in ${ms}ms"
    } catch (e: Exception) {
        // The message IS the diagnosis here: unknown host, timeout, refused
        // and certificate failures each mean something different.
        "Unreachable after ${System.currentTimeMillis() - started}ms — " +
            "${e::class.simpleName}: ${e.message}"
    }
}

actual fun reconcileUploadSchedule(reason: String) {
    // Best-effort by construction. This is a side effect of events that matter
    // for their own reasons — a login must not fail because the upload schedule
    // could not be reconciled, and the backstop sweep exists precisely so a
    // missed reconcile costs latency rather than correctness. (Host tests
    // exercise SessionManager with no Koin container at all, which is how this
    // was found.)
    try {
        val context: Context = GlobalContext.get().get()
        PhotoUploadManager(context).reconcile(reason)
    } catch (e: Throwable) {
        // The log is guarded too: android.util.Log is not mocked on the host,
        // so an unguarded warning would turn "reconcile unavailable" back into
        // the failed login this whole block exists to prevent.
        runCatching {
            android.util.Log.w("UploadDiagnostics", "reconcile [$reason] skipped: ${e.message}")
        }
    }
}

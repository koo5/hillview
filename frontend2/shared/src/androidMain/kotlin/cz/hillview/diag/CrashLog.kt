package cz.hillview.diag

import android.content.Context
import android.util.Log
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import cz.hillview.plugin.EventLog
import cz.hillview.plugin.hvTag

/**
 * The last crash, kept where the NEXT start can show it.
 *
 * A crash on a phone in the field leaves nothing behind: the process is
 * gone, logcat needs a cable, and the report that reaches the developer is
 * a sentence ("cleared the event log, went back, came back, crash"). This
 * writes the uncaught exception — build, time, thread, full trace — to a
 * file before letting the system's own handler finish the job, and the
 * Event log screen offers it for copying on the next launch. The
 * sentence then arrives with its stack trace.
 */
object CrashLog {
    private val TAG = hvTag("CrashLog")
    private const val FILE = "last-crash.txt"

    fun install(context: Context) {
        val app = context.applicationContext
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                File(app.filesDir, FILE).writeText(report(thread, throwable))
            } catch (e: Throwable) {
                // Nothing to do — a crash handler that crashes helps nobody.
                Log.e(TAG, "could not write crash report", e)
            }
            // The system's handler (the "app has stopped" dialog, the process
            // kill) must still run: swallowing the crash would leave a
            // half-dead process in front of the user.
            previous?.uncaughtException(thread, throwable)
        }
    }

    /** The report from the previous crash, or null when there was none. */
    fun lastReport(context: Context): String? =
        File(context.applicationContext.filesDir, FILE).takeIf { it.exists() }?.readText()

    fun clear(context: Context) {
        File(context.applicationContext.filesDir, FILE).delete()
    }

    /**
     * The deaths OUR handler could not record, read back from the system.
     *
     * [install] covers an uncaught Kotlin exception and gives a full stack trace, which
     * is more than the platform offers for that case. It cannot cover a native crash, an
     * ANR, a low-memory or system kill, or a crash early enough that the handler had not
     * been installed — in all of those `last-crash.txt` stays empty while the app
     * visibly dies, and that silence is indistinguishable from "nothing happened".
     *
     * `getHistoricalProcessExitReasons` closes it, and RETROSPECTIVELY: the system keeps
     * these records, so the first build to read them reports deaths that already
     * happened. Needs API 30; below that the gap stays open and there is nothing to be
     * done about it.
     *
     * The trace is deliberately not read here. `getTraceInputStream` carries an ANR
     * trace, and from API 31 a native tombstone as a protobuf — useful, but one is
     * hundreds of lines and the other needs a schema, and neither belongs in a ring
     * buffer of one-line events. The reason, the subreason and the description are what
     * say WHICH KIND of death it was, which is the question this answers.
     */
    fun recordSystemExitReasons(context: Context) {
        if (android.os.Build.VERSION.SDK_INT < 30) return
        try {
            val am = context.applicationContext
                .getSystemService(Context.ACTIVITY_SERVICE) as? android.app.ActivityManager ?: return
            // 0 = our own package, 0 = any pid, and a handful: the records are ordered
            // newest first, and a crash loop is visible in three or four of them.
            for (info in am.getHistoricalProcessExitReasons(null, 0, 6)) {
                val reason = exitReasonName(info.reason)
                // An ordinary exit is not news. A crash we already captured ourselves is
                // not either — that line is already in the log, with its trace.
                if (info.reason == android.app.ApplicationExitInfo.REASON_EXIT_SELF ||
                    info.reason == android.app.ApplicationExitInfo.REASON_USER_REQUESTED ||
                    info.reason == android.app.ApplicationExitInfo.REASON_CRASH
                ) {
                    continue
                }
                EventLog.record(
                    "exit",
                    "$reason at ${java.util.Date(info.timestamp)}" +
                        (info.description?.let { " — $it" } ?: "") +
                        " (importance ${info.importance}, rss ${info.rss / 1024}MB)",
                )
            }
        } catch (e: Throwable) {
            // Diagnostics must never be the thing that takes the app down.
            Log.w(TAG, "could not read historical exit reasons", e)
        }
    }

    /**
     * Android's reason constants as words. Only the ones that mean something to someone
     * reading a log; anything else arrives as its number, which is still better than a
     * wrong name.
     */
    private fun exitReasonName(reason: Int): String = when (reason) {
        android.app.ApplicationExitInfo.REASON_ANR -> "ANR"
        android.app.ApplicationExitInfo.REASON_CRASH -> "crash (Kotlin)"
        android.app.ApplicationExitInfo.REASON_CRASH_NATIVE -> "crash (native)"
        android.app.ApplicationExitInfo.REASON_LOW_MEMORY -> "killed: low memory"
        android.app.ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE -> "killed: resource use"
        android.app.ApplicationExitInfo.REASON_SIGNALED -> "signalled"
        android.app.ApplicationExitInfo.REASON_DEPENDENCY_DIED -> "dependency died"
        android.app.ApplicationExitInfo.REASON_OTHER -> "killed by the system"
        android.app.ApplicationExitInfo.REASON_PERMISSION_CHANGE -> "permission change"
        android.app.ApplicationExitInfo.REASON_INITIALIZATION_FAILURE -> "failed to start"
        else -> "exit reason $reason"
    }

    private fun report(thread: Thread, throwable: Throwable): String {
        val trace = StringWriter().also { throwable.printStackTrace(PrintWriter(it)) }.toString()
        return buildString {
            append("build: ").append(cz.hillview.BuildInfo.label()).append('\n')
            append("at: ").append(java.util.Date().toString()).append('\n')
            append("thread: ").append(thread.name).append('\n')
            append('\n')
            append(trace)
        }
    }
}

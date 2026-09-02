package cz.hillview.diag

import android.content.Context
import android.util.Log
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter

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
    private const val TAG = "hv-CrashLog"
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

package cz.hillview.core

import android.content.Context
import android.content.Intent
import org.koin.core.context.GlobalContext

actual fun restartApp() {
    val context = GlobalContext.get().get<Context>()
    val launch = context.packageManager.getLaunchIntentForPackage(context.packageName)
        ?: return
    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
    context.startActivity(launch)
    // Hard exit: the new task above starts a FRESH process. WorkManager
    // jobs survive — the system reschedules them.
    Runtime.getRuntime().exit(0)
}

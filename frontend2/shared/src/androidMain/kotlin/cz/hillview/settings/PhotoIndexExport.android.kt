package cz.hillview.settings

import android.content.Context
import cz.hillview.capture.PhotoTableDump
import org.koin.core.context.GlobalContext

private fun context(): Context = GlobalContext.get().get()

actual fun photoTableDumpLabel(): String? = PhotoTableDump.lastDumpLabel(context())

actual suspend fun dumpPhotoTableNow(): String = PhotoTableDump.dumpNowForResult(context())

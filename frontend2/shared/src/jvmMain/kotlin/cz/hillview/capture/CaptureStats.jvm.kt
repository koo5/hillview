package cz.hillview.capture

private val lock = Any()

internal actual fun <T> statsLocked(block: () -> T): T = synchronized(lock) { block() }

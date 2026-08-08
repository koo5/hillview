package cz.hillview.core

/**
 * Kill and relaunch the whole process. The server-URL discipline rests on
 * this: the SETTING and the RUNTIME value are deliberately separate, and
 * the only sanctioned way to move the runtime is a full restart — auth,
 * the upload workers, and every cached client resolve the same URL at
 * startup, so a live switch would leave them pointing at different
 * servers mid-flight (the stranded-client-key incident).
 */
expect fun restartApp()

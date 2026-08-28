package cz.hillview.upload

import java.io.File
import kotlin.test.Test
import kotlin.test.fail

/**
 * The upload stack's rule as a test — docs/upload-one-funnel.md.
 *
 * The schedule is decided in ONE place (PhotoUploadManager.reconcile →
 * decideUploadSchedule) and a row's upload status moves in ONE place (the
 * drain). Before that was true, every upload bug lived in the gap between
 * two components that each thought they owned a decision — a capture that
 * enqueued its own job, a settings save that enqueued another with a
 * different constraint, a stale KEEP job swallowing every later enqueue.
 *
 * Same shape as OneStateArchitectureTest, and for the same reason: a rule
 * that only lives in a document erodes; one that fails the build does not.
 * The walk covers shared-kt too, because the stack lives there and the
 * Tauri app compiles the same files.
 */
class UploadFunnelArchitectureTest {

    private data class Rule(
        val what: String,
        val markers: List<String>,
        /** Path suffixes allowed to contain the markers, and why. */
        val allowed: Map<String, String>,
    )

    private val rules = listOf(
        Rule(
            what = "enqueue WorkManager jobs",
            markers = listOf("enqueueUniqueWork(", "enqueueUniquePeriodicWork(", ".enqueue("),
            allowed = mapOf(
                "plugin/PhotoUploadManager.kt" to "the reconciler — the one scheduling authority",
            ),
        ),
        Rule(
            what = "move a photo's upload status",
            markers = listOf(
                "updateUploadStatus(", "updateUploadFailure(", "updateUploadStatusAndServerId(",
                "claimForUpload(", "reclaimAbandonedUploads(",
            ),
            allowed = mapOf(
                "plugin/PhotoUploadLogic.kt" to "the drain — claims and advances every row it touches",
                "plugin/StartupReconciler.kt" to "hands abandoned 'uploading' rows back before the first reconcile",
                "plugin/SimplePhotoDao.kt" to "declares them",
            ),
        ),
        Rule(
            what = "run the drain directly",
            markers = listOf("doWorkInternal("),
            allowed = mapOf(
                "plugin/PhotoUploadWorker.kt" to "WorkManager's entry point",
                "plugin/PhotoUploadManager.kt" to "the targeted force-upload, one photo, on the reconciler's scope",
                "plugin/PhotoUploadLogic.kt" to "declares it",
            ),
        ),
    )

    @Test
    fun theUploadStackHasOneSchedulerAndOneDrain() {
        val roots = sourceRoots()
        val offenders = mutableListOf<String>()
        for (rule in rules) {
            for (root in roots) {
                root.walkTopDown()
                    .filter { it.isFile && it.extension == "kt" }
                    .filterNot { it.path.contains("Test") }
                    .filterNot { f -> rule.allowed.keys.any { f.path.replace('\\', '/').endsWith(it) } }
                    .forEach { f ->
                        val text = f.readText()
                        val hits = rule.markers.filter(text::contains)
                        if (hits.isNotEmpty()) {
                            offenders += "${f.relativeTo(root.parentFile.parentFile)} may not ${rule.what}: ${hits.joinToString()}"
                        }
                    }
            }
        }
        if (offenders.isNotEmpty()) {
            fail(
                "The upload stack has one scheduler and one drain " +
                    "(docs/upload-one-funnel.md):\n" + offenders.joinToString("\n") { "  $it" },
            )
        }
    }

    /**
     * frontend2/shared/src, frontend2/androidApp/src and shared-kt/src, found
     * from the repo root (the directory holding .git) rather than assumed.
     * Failing loudly when a tree is missing is deliberate: a fitness test
     * that quietly scans nothing reads as a passing check.
     */
    private fun sourceRoots(): List<File> {
        var dir: File? = File(".").absoluteFile
        while (dir != null && !File(dir, ".git").exists()) dir = dir.parentFile
        val repo = dir ?: fail("could not locate the repo root from ${File(".").absolutePath}")
        return listOf("frontend2/shared/src", "frontend2/androidApp/src", "shared-kt/src")
            .map { File(repo, it) }
            .onEach { if (!it.isDirectory) fail("missing source tree: $it") }
    }
}

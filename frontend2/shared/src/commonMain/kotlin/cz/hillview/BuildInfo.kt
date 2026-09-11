package cz.hillview

/**
 * What build is this? Filled in by the platform entry point (HillviewApplication
 * from BuildConfig — see androidApp/build.gradle.kts) and shown in Settings and
 * in logcat (`hv-build`) so a phone can be checked against the source tree.
 *
 * The identity is git CONTENT, not the clock: the commit, and for a dirty tree
 * a hash of the diff. Two builds of the same content carry the same label,
 * which is also what keeps it friendly to Gradle's configuration cache.
 */
object BuildInfo {
    var version: String = ""
    var gitSha: String = ""
    var gitCommitTime: String = ""
    var dirty: Boolean = false
    var dirtyHash: String = ""

    fun label(): String = buildLabel(version, gitSha, gitCommitTime, dirty, dirtyHash)
}

/** `0.1.0 · a0bc3a1c · 2026-08-27T02:58:11+02:00`, `+<hash> (uncommitted)` when dirty. */
fun buildLabel(
    version: String,
    gitSha: String,
    gitCommitTime: String,
    dirty: Boolean,
    dirtyHash: String,
): String {
    val v = version.ifBlank { "dev" }
    if (gitSha.isBlank()) return "$v · unknown build"
    val rev = if (dirty) "$gitSha+${dirtyHash.ifBlank { "?" }} (uncommitted)" else gitSha
    return listOf(v, rev, gitCommitTime).filter { it.isNotBlank() }.joinToString(" · ")
}

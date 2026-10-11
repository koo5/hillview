package cz.hillview.arch

import java.io.File
import kotlin.test.Test
import kotlin.test.fail

/**
 * Every log tag in both apps goes through [cz.hillview.plugin.hvTag], so that
 * `logcat` can be filtered to this project's output and the prefix exists once.
 *
 * WHY A TEST AND NOT A CONVENTION. It was a convention, held by 49 copies of the
 * string `"hv-"`, and three instrumented tests had already lost it — logging
 * under `"UploadCoalescing"` beside app code using `"hv-UploadCoalescing"`.
 * Nothing said so, because nothing was checking.
 *
 * Answering "are they all prefixed?" by hand turned out to be the expensive
 * part. A source regex over-counted (it matched commented-out code, which this
 * project keeps on purpose, and a tag inside a test's string literal); settling
 * it took an AST query. This test replaces that archaeology: the question is now
 * asked on every run, over BOTH source trees, and a new tag that skips the
 * helper fails here instead of quietly weakening the filter.
 *
 * It reads source rather than bytecode because that is where the mistake is
 * made, and it uses [kotlinCodeOnly] so a `"hv-…"` in a comment or a string
 * cannot pass or fail it — the exact distinction the regex got wrong.
 */
class LogTagConventionTest {

    @Test
    fun everyLogTagComesFromTheHelper() {
        val offenders = mutableListOf<String>()
        for (root in sourceRoots()) {
            for (f in root.walkTopDown().filter { it.isFile && it.extension == "kt" }) {
                if (f.name == "LogTag.kt") continue          // the one definition
                val code = kotlinCodeOnly(f.readText())
                // A tag passed as a literal to android.util.Log, on the same
                // line or the next one (the multi-line call shape that hid three
                // of these from a line-oriented search).
                LOG_CALL.findAll(code).forEach { m ->
                    offenders += "${f.name}: Log.${m.groupValues[1]}(\"${m.groupValues[2]}\", …)"
                }
                // ...and a TAG that is still a bare string.
                TAG_LITERAL.findAll(code).forEach { m ->
                    offenders += "${f.name}: val TAG = \"${m.groupValues[1]}\""
                }
            }
        }
        if (offenders.isNotEmpty()) {
            fail(
                "these log tags do not go through hvTag(), so the hv- prefix is " +
                    "a copy rather than a definition:\n  " + offenders.joinToString("\n  "),
            )
        }
    }

    /**
     * The helper has to be reachable from everywhere that logs, which is the
     * reason it lives in shared-kt: both apps compile that tree as source.
     */
    @Test
    fun theHelperLivesWhereBothAppsCanSeeIt() {
        val roots = sourceRoots()
        if (roots.none { it.path.contains("shared-kt") }) {
            fail("shared-kt/src was not scanned, so most tags went unchecked: $roots")
        }
        if (roots.flatMap { it.walkTopDown().filter { f -> f.name == "LogTag.kt" } }.isEmpty()) {
            fail("LogTag.kt is not in a tree both apps compile: $roots")
        }
    }

    private companion object {
        /** `Log.d("hv-X"` / `Log.d(\n    "hv-X"` — a literal where a tag belongs. */
        val LOG_CALL = Regex("""Log\.([dievw])\(\s*"([^"]*)"\s*,""")

        /** `val TAG = "…"`, with or without `const` and any visibility. */
        val TAG_LITERAL = Regex("""val TAG\s*=\s*"([^"]*)"""")
    }

    /**
     * Both trees that log: the shared module's `src/`, and `shared-kt/src/`,
     * which is compiled as source into both apps and holds most of the tags.
     *
     * Found by walking up from the working directory, the same way
     * `OneStateArchitectureTest` does — a test must not depend on where Gradle
     * happened to start it.
     */
    private fun sourceRoots(): List<File> {
        // canonicalFile, not absoluteFile: the latter keeps the "." component,
        // which shifts every parentFile step by one and made this look for
        // shared-kt inside frontend2/.
        var dir: File? = File(".").canonicalFile
        while (dir != null) {
            if (File(dir, "src/commonMain").isDirectory) {
                val module = File(dir, "src")
                // <repo>/frontend2/shared -> <repo>
                val repo = dir.parentFile?.parentFile
                val sharedKt = repo?.let { File(it, "shared-kt/src") }
                return listOfNotNull(module, sharedKt?.takeIf { it.isDirectory })
            }
            dir = dir.parentFile
        }
        fail("could not locate the shared module's src/ from ${File(".").absolutePath}")
    }
}

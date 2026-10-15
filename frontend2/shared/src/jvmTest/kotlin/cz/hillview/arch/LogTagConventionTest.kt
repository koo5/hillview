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
     * NOTHING MAY CALL `Log.isLoggable`, because six of this project's tags are longer
     * than the 23 characters that method still enforces.
     *
     * `Log.isLoggable` throws `IllegalArgumentException` for a tag over 23 characters on
     * API 25 and below, and both apps target that range — frontend2 is minSdk 24, the
     * Tauri plugin minSdk 21. `hv-MyDeviceOrientationSensor` is 28, and five more are
     * over. Ordinary `Log.d/i/w/e` never throw on a long tag, which is why the long tags
     * themselves are not the problem and have cost nothing.
     *
     * So the hazard is narrow and specific: one `if (Log.isLoggable(TAG, VERBOSE))` —
     * a completely ordinary idiom, and the recommended way to gate a chatty log — would
     * crash on an API 21–25 device while looking impeccable in review and working on
     * every modern phone and emulator. This test is what keeps "long tags exist" and "a
     * long tag reaches isLoggable" apart.
     *
     * A caller that genuinely needs the API must bound its own tag; these are not safe
     * for it. The claim this replaced said the cap was gone on the targeted API levels,
     * which was simply wrong (Copilot review, 2026-10-15) — and it was wrong in a
     * comment, where nothing could contradict it.
     */
    @Test
    fun nothingCallsIsLoggableWithTheseTags() {
        val offenders = mutableListOf<String>()
        for (root in sourceRoots()) {
            for (f in root.walkTopDown().filter { it.isFile && it.extension == "kt" }) {
                val code = kotlinCodeOnly(f.readText())
                IS_LOGGABLE.findAll(code).forEach { m ->
                    offenders += "${f.name}: ${m.value.trim()}"
                }
            }
        }
        if (offenders.isNotEmpty()) {
            fail(
                "Log.isLoggable throws on a tag over 23 characters on API <= 25, and six " +
                    "hv- tags are longer than that (hv-MyDeviceOrientationSensor is 28); " +
                    "frontend2 is minSdk 24 and the Tauri plugin minSdk 21, so those " +
                    "devices are in scope. Bound the tag at the call site, or do not gate " +
                    "on isLoggable:\n  " + offenders.joinToString("\n  "),
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

        /** Any `Log.isLoggable(` — see [nothingCallsIsLoggableWithTheseTags]. */
        val IS_LOGGABLE = Regex("""\bLog\s*\.\s*isLoggable\s*\(""")
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

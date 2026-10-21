package cz.hillview.arch

/**
 * A Kotlin file with its comments and string contents blanked out, for the
 * architecture tests to grep.
 *
 * They match on substrings, and the thing they forbid is invariably the thing
 * their own explanation has to NAME — "no reader registers a second
 * OrientationEventListener" is a sentence that would otherwise fail the test
 * it documents. Blanking prose keeps the rules explainable in the files they
 * govern. String contents go too: a hardware call cannot hide in a literal,
 * and a log line quoting the forbidden name is prose by another route.
 *
 * Line structure is preserved (newlines survive) so a hit still reports
 * usefully.
 */
fun kotlinCodeOnly(text: String): String {
    val out = StringBuilder(text.length)
    var i = 0
    var blockDepth = 0
    while (i < text.length) {
        val c = text[i]
        val next = text.getOrNull(i + 1)
        when {
            blockDepth > 0 -> {
                when {
                    c == '/' && next == '*' -> { blockDepth++; i += 2 }
                    // Kotlin block comments nest, so the depth matters.
                    c == '*' && next == '/' -> { blockDepth--; i += 2 }
                    else -> { if (c == '\n') out.append('\n'); i++ }
                }
            }
            c == '/' && next == '*' -> { blockDepth = 1; i += 2 }
            c == '/' && next == '/' -> {
                while (i < text.length && text[i] != '\n') i++
            }
            text.startsWith("\"\"\"", i) -> {
                i += 3
                while (i < text.length && !text.startsWith("\"\"\"", i)) {
                    if (text[i] == '\n') out.append('\n')
                    i++
                }
                i = minOf(i + 3, text.length)
                out.append("\"\"")
            }
            c == '"' -> {
                i++
                while (i < text.length && text[i] != '"') {
                    if (text[i] == '\\') i++
                    i++
                }
                i++
                out.append("\"\"")
            }
            c == '\'' -> {
                i++
                while (i < text.length && text[i] != '\'') {
                    if (text[i] == '\\') i++
                    i++
                }
                i++
                out.append("''")
            }
            else -> { out.append(c); i++ }
        }
    }
    return out.toString()
}

/**
 * Both Kotlin trees this project compiles: the shared module's `src/`, and
 * `shared-kt/src/`, which both apps compile as source.
 *
 * Found by walking up from the working directory — a test must not depend on where
 * Gradle happened to start it. Lives here rather than in one test because two now need
 * it, and a locator held by copies is the shape of mistake this file exists to catch.
 */
fun kotlinSourceRoots(): List<java.io.File> {
    // canonicalFile, not absoluteFile: the latter keeps the "." component, which shifts
    // every parentFile step by one and made this look for shared-kt inside frontend2/.
    var dir: java.io.File? = java.io.File(".").canonicalFile
    while (dir != null) {
        if (java.io.File(dir, "src/commonMain").isDirectory) {
            val module = java.io.File(dir, "src")
            // <repo>/frontend2/shared -> <repo>
            val repo = dir.parentFile?.parentFile
            val sharedKt = repo?.let { java.io.File(it, "shared-kt/src") }
            return listOfNotNull(module, sharedKt?.takeIf { it.isDirectory })
        }
        dir = dir.parentFile
    }
    error("could not locate the shared module's src/ from ${java.io.File(".").absolutePath}")
}

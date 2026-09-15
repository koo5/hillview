package cz.hillview.nav

import cz.hillview.arch.kotlinCodeOnly
import java.io.File
import kotlin.test.Test
import kotlin.test.fail

/**
 * Every route key must be registered in the back stack's serializers module.
 *
 * `NavKey` is a library interface, so it cannot be sealed and the polymorphism
 * cannot be resolved for us: kotlinx.serialization needs each subclass named
 * explicitly. A key that is declared and navigated to but never registered
 * works perfectly — until the activity is stopped. Then `onSaveInstanceState`
 * serializes the back stack, fails to find the subclass, and takes the process
 * down:
 *
 *   SerializationException: Serializer for subclass 'UploadStatusKey' is not
 *   found in the polymorphic scope of 'NavKey'.
 *
 * Which is how it reached a phone (user, 2026-09-15): three keys — EventLog,
 * UploadStatus and CaptureGuide — were added without registration, so opening
 * any of those screens and then backgrounding the app crashed it. Backgrounding
 * mid-upload is exactly when a user is on the upload-status screen, and exactly
 * when a crash costs the most.
 *
 * Nothing about writing a new screen reminds anyone to come back and edit a
 * list in another file, so the list is checked here instead of remembered.
 */
class RouteKeyRegistrationTest {

    @Test
    fun everyRouteKeyIsRegisteredForTheBackStack() {
        val declared = declaredKeys()
        val registered = registeredKeys()

        if (declared.isEmpty()) fail("found no NavKey declarations in Routes.kt — has it moved?")

        val missing = declared - registered
        if (missing.isNotEmpty()) {
            fail(
                "these route keys are not registered in App.kt's serializers module, " +
                    "so backgrounding the app while one of them is on the back stack " +
                    "crashes the process: ${missing.sorted().joinToString()}",
            )
        }

        // The other direction is a typo or a deletion, not a crash, but it is
        // still a lie in a list whose whole job is to be exhaustive.
        val unknown = registered - declared
        if (unknown.isNotEmpty()) {
            fail("App.kt registers keys that Routes.kt does not declare: ${unknown.sorted().joinToString()}")
        }
    }

    /** `data object <Name> : NavKey` in Routes.kt, comments and strings blanked. */
    private fun declaredKeys(): Set<String> {
        val text = kotlinCodeOnly(file("commonMain/kotlin/cz/hillview/nav/Routes.kt").readText())
        return Regex("""data\s+(?:object|class)\s+(\w+)[^\n]*:\s*NavKey""")
            .findAll(text)
            .map { it.groupValues[1] }
            .toSet()
    }

    /** `subclass(<Name>::class)` inside the polymorphic(NavKey::class) block. */
    private fun registeredKeys(): Set<String> {
        val text = kotlinCodeOnly(file("commonMain/kotlin/cz/hillview/App.kt").readText())
        val start = text.indexOf("polymorphic(NavKey::class)")
        if (start < 0) fail("App.kt no longer declares polymorphic(NavKey::class) — did the nav host change?")
        val block = text.substring(start).substringAfter('{').substringBefore('}')
        return Regex("""subclass\((\w+)::class\)""")
            .findAll(block)
            .map { it.groupValues[1] }
            .toSet()
    }

    /**
     * A file under the module's src/, found by walking up from the working
     * directory rather than assuming one — the same approach, and the same
     * loud failure, as OneStateArchitectureTest.
     */
    private fun file(relative: String): File {
        var dir: File? = File(".").absoluteFile
        while (dir != null) {
            val candidate = File(dir, "src/commonMain")
            if (candidate.isDirectory) {
                val found = File(dir, "src/$relative")
                if (found.isFile) return found
                fail("expected $relative under ${File(dir, "src")}")
            }
            dir = dir.parentFile
        }
        fail("could not locate the shared module's src/ from ${File(".").absolutePath}")
    }
}

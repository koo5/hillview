package cz.hillview.capture

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The streaming dump must produce EXACTLY what the materialising one did — the same bytes
 * and the same hash — because the shard hashes are already stored on phones and the file
 * is read by things that are not this app.
 *
 * The reason the whole thing was rewritten: ten thousand rows held ~19 MB of chars, and
 * `toString()` plus `toByteArray()` made two more copies, about 48 MB of peak on a 268 MB
 * heap. That was an OutOfMemoryError in the field, and the second of exactly that shape.
 */
class PhotoTableDumpStreamTest {

    /**
     * THE IDENTITY THAT LETS THE HASH CHANGE SOURCE WITHOUT CHANGING VALUE.
     *
     * `hash(A + B) = hash(A) * 31^|B| + hash(B)`, in wrapping Int arithmetic. If this
     * drifted, every stored shard hash would miss and every phone would rewrite its
     * entire table once — silently, and only the first time, so it would be very hard to
     * attribute afterwards.
     */
    @Test
    fun theIncrementalHashIsStringHashCode() {
        val random = Random(20261014)
        repeat(200) {
            val parts = List(random.nextInt(1, 12)) {
                // Include the characters a CSV cell actually carries, and empties, which
                // contribute nothing to the hash but do advance the power of 31.
                val n = random.nextInt(0, 40)
                (0 until n).map { "abcXYZ019 ,\"\n{}:".random(random) }.joinToString("")
            }
            val incremental = ConcatHash().also { h -> parts.forEach { h.append(it) } }.value()
            assertEquals(parts.joinToString("").hashCode(), incremental, "parts=$parts")
        }
    }

    /** An empty run hashes like an empty string, not like something. */
    @Test
    fun nothingHashesLikeTheEmptyString() {
        assertEquals("".hashCode(), ConcatHash().value())
        assertEquals("".hashCode(), ConcatHash().append("").value())
    }

    /**
     * The header is still the header, and a row still ends in one newline — the shape a
     * reader keys on. Cheap, and it is what an extraction refactor gets wrong.
     */
    @Test
    fun theHeaderNamesEveryColumnOnce() {
        val header = photoTableHeader()
        assertTrue(header.startsWith("#"), header)
        assertTrue(header.endsWith("\n"), header)
        val names = header.removePrefix("#").trimEnd('\n').split(",")
        assertEquals(PHOTO_DUMP_COLUMNS, names)
        assertEquals(names.size, names.toSet().size, "a column name is repeated")
    }
}

package cz.hillview.capture

import cz.hillview.plugin.PhotoEntity
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * The CSV that has to be readable when the app is gone.
 *
 * The header and the column ORDER are the contract — whoever opens this file
 * has nothing else to go on — so they are pinned here rather than left to
 * whatever the writer happens to emit.
 */
class PhotoTableCsvTest {

    private fun photo(
        id: String = "p1",
        filename: String = "hillview_1.jpg",
        path: String = "/storage/emulated/0/DCIM/Hillview2/hillview_1.jpg",
    ) = PhotoEntity(
        id = id,
        filename = filename,
        path = path,
        latitude = 50.11692,
        longitude = 14.48837,
        altitude = 231.5,
        bearing = 137.5,
        capturedAt = 1_757_000_000_000L,
        accuracy = 4.2,
        width = 4000,
        height = 3000,
        fileSize = 5_242_880L,
        createdAt = 1_757_000_000_123L,
    )

    private fun lines(csv: String) = csv.trimEnd('\n').split("\n")

    @Test
    fun theHeaderNamesEveryColumnTheRowsWrite() {
        val csv = photoTableCsv(listOf(photo()))
        val rows = lines(csv)
        assertEquals("#" + PHOTO_DUMP_COLUMNS.joinToString(","), rows[0])
        assertEquals(PHOTO_DUMP_COLUMNS.size, rows[1].split(",").size)
    }

    @Test
    fun anEmptyTableStillWritesItsHeader() {
        // A file with only a header says "no photos"; an absent file says
        // nothing, and the two must not look alike.
        assertEquals("#" + PHOTO_DUMP_COLUMNS.joinToString(",") + "\n", photoTableCsv(emptyList()))
    }

    @Test
    fun theStampIsThereAndTheTimeIsReadable() {
        val cells = lines(photoTableCsv(listOf(photo())))[1].split(",")
        val by = { name: String -> cells[PHOTO_DUMP_COLUMNS.indexOf(name)] }
        assertEquals("p1", by("id"))
        assertEquals("hillview_1.jpg", by("filename"))
        assertEquals("50.11692", by("latitude"))
        assertEquals("14.48837", by("longitude"))
        assertEquals("137.5", by("bearing"))
        assertEquals("1757000000000", by("capturedAt"))
        // The epoch alone is not readable by a person opening a spreadsheet.
        assertEquals("2025-09-04T15:33:20Z", by("capturedAtUtc"))
    }

    /** Unset stays empty rather than becoming a number that means something. */
    @Test
    fun absentValuesAreEmptyCells() {
        val cells = lines(photoTableCsv(listOf(photo())))[1].split(",")
        val by = { name: String -> cells[PHOTO_DUMP_COLUMNS.indexOf(name)] }
        assertEquals("", by("pitch"))
        assertEquals("", by("serverPhotoId"))
        assertEquals("", by("license"))
        assertEquals("", by("altLocationJson"))
        assertEquals("0", by("deleted"))
    }

    /**
     * The altitude a photo never had and the altitude that happens to BE zero
     * are different facts, and the column has to keep them apart: an ellipsoid
     * height is legitimately 0 or below (see PhotoEntity.altitude, where the
     * old non-null 0.0 sentinel threw both away).
     */
    @Test
    fun anUnknownAltitudeIsEmptyAndAMeasuredZeroIsNot() {
        val altitudeOf = { entity: PhotoEntity ->
            lines(photoTableCsv(listOf(entity)))[1]
                .split(",")[PHOTO_DUMP_COLUMNS.indexOf("altitude")]
        }
        assertEquals("231.5", altitudeOf(photo()))
        assertEquals("", altitudeOf(photo().copy(altitude = null)))
        // And a photo with NO position (v22) has empty coordinate cells, not
        // Null Island — the reader must be able to tell "none" from "0, 0".
        val cells = lines(photoTableCsv(listOf(photo().copy(latitude = null, longitude = null))))[1].split(",")
        assertEquals("", cells[PHOTO_DUMP_COLUMNS.indexOf("latitude")])
        assertEquals("", cells[PHOTO_DUMP_COLUMNS.indexOf("longitude")])
        assertEquals("0.0", altitudeOf(photo().copy(altitude = 0.0)))
        assertEquals("-61.4", altitudeOf(photo().copy(altitude = -61.4)))
    }

    /**
     * The JSON columns are the reason quoting matters: they are full of
     * commas and quotes, and an unquoted one would shift every later column
     * on that row.
     */
    @Test
    fun jsonColumnsSurviveIntact() {
        val json = """{"mode":"floor","target_ns":2000000}"""
        val csv = photoTableCsv(listOf(photo().copy(exposureJson = json)))
        assertTrue(csv.contains("\"{\"\"mode\"\":\"\"floor\"\",\"\"target_ns\"\":2000000}\""), csv)
    }

    /**
     * Read back with an ordinary RFC 4180 parser, which is what anyone
     * opening this file will use. A filename with a comma in it is the case
     * that would silently shift every later column of that row.
     */
    @Test
    fun aRowSurvivesBeingParsedBack() {
        val csv = photoTableCsv(
            listOf(photo(filename = "a,b.jpg").copy(uploadError = "said \"no\"")),
        )
        val cells = parseCsvRow(lines(csv)[1])
        assertEquals(PHOTO_DUMP_COLUMNS.size, cells.size)
        assertEquals("a,b.jpg", cells[PHOTO_DUMP_COLUMNS.indexOf("filename")])
        assertEquals("said \"no\"", cells[PHOTO_DUMP_COLUMNS.indexOf("uploadError")])
        assertEquals("50.11692", cells[PHOTO_DUMP_COLUMNS.indexOf("latitude")])
    }

    /** RFC 4180, minus the multi-line cells this writer never emits mid-row. */
    private fun parseCsvRow(line: String): List<String> {
        val cells = mutableListOf<String>()
        val cell = StringBuilder()
        var quoted = false
        var i = 0
        while (i < line.length) {
            val c = line[i]
            when {
                quoted && c == '"' && line.getOrNull(i + 1) == '"' -> { cell.append('"'); i++ }
                c == '"' -> quoted = !quoted
                c == ',' && !quoted -> { cells.add(cell.toString()); cell.clear() }
                else -> cell.append(c)
            }
            i++
        }
        cells.add(cell.toString())
        return cells
    }

    @Test
    fun quotingIsOnlyAppliedWhereItIsNeeded() {
        assertEquals("plain", escapeCsvCell("plain"))
        assertEquals("", escapeCsvCell(null))
        assertEquals("\"a,b\"", escapeCsvCell("a,b"))
        assertEquals("\"say \"\"hi\"\"\"", escapeCsvCell("say \"hi\""))
        assertEquals("\"two\nlines\"", escapeCsvCell("two\nlines"))
        assertEquals("\"cr\rhere\"", escapeCsvCell("cr\rhere"))
    }

    @Test
    fun everyPhotoGetsALine() {
        val csv = photoTableCsv((1..5).map { photo(id = "p$it") })
        assertEquals(6, lines(csv).size)
    }
}

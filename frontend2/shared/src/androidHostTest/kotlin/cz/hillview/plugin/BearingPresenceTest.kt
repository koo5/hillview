package cz.hillview.plugin

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * The loaders keep 0.0 as the wire default for a missing heading; has_bearing
 * is what tells "unknown" from "due north". Both facts are pinned here.
 */
class BearingPresenceTest {
    private val stream = StreamPhotoLoader()
    private val panoramax = PanoramaxPhotoLoader()
    private val panoramaxSource = SourceConfig(
        id = "panoramax", name = "Panoramax", type = "panoramax", enabled = true,
        color = "#3a8", url = "https://api.panoramax.xyz",
    )

    private fun streamPhoto(vararg fields: Pair<String, JsonElement>) = buildJsonObject {
        put("id", "p1")
        putJsonObject("geometry") { putJsonArray("coordinates") { add(14.4); add(50.0) } }
        fields.forEach { (k, v) -> put(k, v) }
    }

    private fun panoramaxItem(vararg props: Pair<String, JsonElement>) = buildJsonObject {
        put("id", "x1")
        putJsonObject("geometry") { put("type", "Point"); putJsonArray("coordinates") { add(14.4); add(50.0) } }
        putJsonObject("properties") { props.forEach { (k, v) -> put(k, v) } }
    }

    @Test
    fun aStreamPhotoWithoutAHeadingSaysSo() {
        val p = stream.parsePhotoJson(streamPhoto())
        assertFalse(p.has_bearing)
        assertEquals(0.0, p.bearing) // the wire default, unchanged
    }

    @Test
    fun aStreamPhotoShotDueNorthKeepsItsHeading() {
        val p = stream.parsePhotoJson(streamPhoto("bearing" to JsonPrimitive(0)))
        assertTrue(p.has_bearing)
        assertEquals(0.0, p.bearing)
    }

    @Test
    fun mapillarysCompassAngleIsAHeadingToo() {
        val p = stream.parsePhotoJson(streamPhoto("compass_angle" to JsonPrimitive(90.5)))
        assertTrue(p.has_bearing)
        assertEquals(90.5, p.bearing)
    }

    @Test
    fun anUnorientedPanoramaxItemSaysSo() {
        val p = panoramax.convertPanoramaxItem(panoramaxItem(), panoramaxSource)
        assertNotNull(p)
        assertFalse(p.has_bearing)
        assertEquals(0.0, p.bearing)
    }

    @Test
    fun aPanoramaxAzimuthOfZeroIsAHeading() {
        val p = panoramax.convertPanoramaxItem(panoramaxItem("view:azimuth" to JsonPrimitive(0)), panoramaxSource)
        assertNotNull(p)
        assertTrue(p.has_bearing)
        assertEquals(0.0, p.bearing)
    }

    @Test
    fun aHeadinglessPhotoStaysOutOfTheRangeSetUnlessPicked() {
        val centre = LatLng(50.0, 14.4)
        fun photo(id: String, recorded: Boolean) = PhotoData(
            id = id, uid = "hillview-$id", source_type = "stream", coord = centre,
            bearing = 0.0, has_bearing = recorded, source = "hillview",
        )
        val culler = AngularRangeCuller()
        val photos = listOf(photo("north", true), photo("unknown", false))

        assertEquals(listOf("north"), culler.cullPhotosInRange(photos, centre, 1000.0, 10, emptySet()).map { it.id })
        assertEquals(
            listOf("unknown", "north"),
            culler.cullPhotosInRange(photos, centre, 1000.0, 10, setOf("hillview-unknown")).map { it.id },
        )
    }

    @Test
    fun aPanoramaxYawStandsInForTheAzimuth() {
        val p = panoramax.convertPanoramaxItem(panoramaxItem("pers:yaw" to JsonPrimitive(270)), panoramaxSource)
        assertNotNull(p)
        assertTrue(p.has_bearing)
        assertEquals(270.0, p.bearing)
    }
}

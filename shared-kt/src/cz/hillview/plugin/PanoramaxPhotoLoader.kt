package cz.hillview.plugin

import android.util.Log
import kotlinx.coroutines.delay
import kotlinx.serialization.json.*
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import java.util.concurrent.TimeUnit
import kotlin.math.max
import kotlin.math.min

/**
 * Panoramax Photo Loader - one-shot HTTP GET against a Panoramax STAC instance.
 *
 * Kotlin sibling of PanoramaxSourceLoader.ts. Maintains the same 1s leading-edge
 * throttle policy: lastFireTime lives on the companion object so it is shared
 * across loader instances. PhotoOperations processes sources sequentially in a
 * single coroutine, so cross-instance contention is minimal — the @Volatile
 * read/write is sufficient.
 *
 * Field mapping mirrors convertPanoramaxItem in the TS loader; STAC "Item" naming
 * is used in code to avoid collision with QueryOptions.features in the analysis
 * filter type.
 */
class PanoramaxPhotoLoader {
	data class HiddenContent(val photoIds: Set<String>, val userIds: Set<String>) {
		companion object {
			val EMPTY = HiddenContent(emptySet(), emptySet())
		}
	}

	companion object {
		private const val TAG = "PanoramaxPhotoLoader"
		private const val doLog = false
		private const val CONNECTION_TIMEOUT_SECONDS = 30L
		private const val READ_TIMEOUT_SECONDS = 60L
		private const val MIN_INTERVAL_MS = 1000L
		private const val DEFAULT_LIMIT = 1000
		private const val ABORT_POLL_MS = 50L

		@Volatile
		private var lastFireTime: Long = 0L

		// Hidden-content cache, mirroring PanoramaxSourceLoader.ts. Stays null
		// until the first authenticated load; invalidateHidden() is called from
		// PhotoWorkerService when the frontend sends PANORAMAX_HIDDEN_INVALIDATE.
		@Volatile
		private var hiddenContent: HiddenContent? = null
		private val hiddenLock = Any()

		fun invalidateHidden() {
			synchronized(hiddenLock) {
				hiddenContent = null
			}
		}

		fun hiddenSnapshotForTests(): HiddenContent? = hiddenContent

		private val isoDateFormatTz = ThreadLocal.withInitial {
			SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).apply {
				timeZone = TimeZone.getTimeZone("UTC")
			}
		}
		private val isoDateFormatFracTz = ThreadLocal.withInitial {
			SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).apply {
				timeZone = TimeZone.getTimeZone("UTC")
			}
		}

		fun resetThrottleForTests() {
			lastFireTime = 0L
		}
	}

	private val client = OkHttpClient.Builder()
		.connectTimeout(CONNECTION_TIMEOUT_SECONDS, TimeUnit.SECONDS)
		.readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
		.build()

	private val json = Json {
		ignoreUnknownKeys = true
		coerceInputValues = true
	}

	suspend fun loadPhotos(
		source: SourceConfig,
		bounds: Bounds?,
		maxPhotos: Int,
		shouldAbort: () -> Boolean,
		hillviewBackendUrl: String? = null,
		authToken: String? = null
	): List<PhotoData> {
		if (bounds == null) {
			if (doLog) Log.d(TAG, "loadPhotos: ${source.id} called without bounds — no-op")
			return emptyList()
		}
		val instanceBase = source.url
			?: throw IllegalArgumentException("Panoramax source missing instance URL")

		if (!waitThrottleSlot(shouldAbort)) return emptyList()
		if (shouldAbort()) return emptyList()
		lastFireTime = System.currentTimeMillis()

		// Resolve hidden content in parallel with the search fetch.
		val hidden = ensureHiddenContent(hillviewBackendUrl, authToken)

		val url = buildSearchUrl(instanceBase, bounds, max(1, min(maxPhotos, DEFAULT_LIMIT)))
		if (doLog) Log.d(TAG, "GET $url")

		val request = Request.Builder()
			.url(url)
			.header("Accept", "application/json")
			.build()

		try {
			client.newCall(request).execute().use { response ->
				if (!response.isSuccessful) {
					Log.e(TAG, "Panoramax API ${response.code} ${response.message} for ${source.id}")
					return emptyList()
				}
				val body = response.body?.string() ?: return emptyList()
				if (shouldAbort()) return emptyList()

				val root = try {
					json.parseToJsonElement(body).jsonObject
				} catch (e: Exception) {
					Log.e(TAG, "Failed to parse Panoramax response for ${source.id}: ${e.message}")
					return emptyList()
				}

				val items = root["features"]?.jsonArray ?: return emptyList()
				var droppedHidden = 0
				val photos = items.mapNotNull { itemElement ->
					try {
						val itemObj = itemElement.jsonObject
						val itemId = itemObj["id"]?.jsonPrimitive?.contentOrNull
						if (itemId != null && hidden.photoIds.contains(itemId)) {
							droppedHidden++
							return@mapNotNull null
						}
						val producerId = producerIdFromItem(itemObj)
						if (producerId != null && hidden.userIds.contains(producerId)) {
							droppedHidden++
							return@mapNotNull null
						}
						convertPanoramaxItem(itemObj, source)
					} catch (e: Exception) {
						Log.w(TAG, "Skipping malformed Panoramax item: ${e.message}")
						null
					}
				}
				if (doLog) Log.d(TAG, "Got ${photos.size} photos for ${source.id} (filtered $droppedHidden hidden)")
				return photos
			}
		} catch (e: Exception) {
			Log.e(TAG, "Panoramax fetch error for ${source.id}: ${e.message}")
			return emptyList()
		}
	}

	private suspend fun ensureHiddenContent(
		hillviewBackendUrl: String?,
		authToken: String?
	): HiddenContent {
		hiddenContent?.let { return it }
		if (hillviewBackendUrl.isNullOrBlank() || authToken.isNullOrBlank()) {
			// Anonymous / unknown URL: don't cache so login self-heals on next pan.
			return HiddenContent.EMPTY
		}
		val base = hillviewBackendUrl.trimEnd('/')
		val photoIds = mutableSetOf<String>()
		val userIds = mutableSetOf<String>()
		val photosReq = Request.Builder()
			.url("$base/hidden/photos?photo_source=panoramax")
			.header("Authorization", "Bearer $authToken")
			.header("Accept", "application/json")
			.build()
		val usersReq = Request.Builder()
			.url("$base/hidden/users?target_user_source=panoramax")
			.header("Authorization", "Bearer $authToken")
			.header("Accept", "application/json")
			.build()
		try {
			client.newCall(photosReq).execute().use { resp ->
				if (resp.isSuccessful) {
					val body = resp.body?.string()
					if (body != null) {
						val arr = json.parseToJsonElement(body).jsonArray
						for (row in arr) {
							row.jsonObject["photo_id"]?.jsonPrimitive?.contentOrNull?.let { photoIds.add(it) }
						}
					}
				}
			}
			client.newCall(usersReq).execute().use { resp ->
				if (resp.isSuccessful) {
					val body = resp.body?.string()
					if (body != null) {
						val arr = json.parseToJsonElement(body).jsonArray
						for (row in arr) {
							row.jsonObject["target_user_id"]?.jsonPrimitive?.contentOrNull?.let { userIds.add(it) }
						}
					}
				}
			}
		} catch (e: Exception) {
			Log.w(TAG, "Failed to load Panoramax hidden content: ${e.message}")
			return HiddenContent.EMPTY
		}
		val loaded = HiddenContent(photoIds = photoIds, userIds = userIds)
		synchronized(hiddenLock) {
			hiddenContent = loaded
		}
		return loaded
	}

	private fun producerIdFromItem(item: JsonObject): String? {
		val providers = item["providers"]?.jsonArray ?: return null
		val producer = providers.firstOrNull { p ->
			p.jsonObject["roles"]?.jsonArray?.any { r ->
				r.jsonPrimitive.contentOrNull == "producer"
			} == true
		}?.jsonObject ?: providers.firstOrNull()?.jsonObject
		return producer?.get("id")?.jsonPrimitive?.contentOrNull
	}

	private suspend fun waitThrottleSlot(shouldAbort: () -> Boolean): Boolean {
		val elapsed = System.currentTimeMillis() - lastFireTime
		val remaining = MIN_INTERVAL_MS - elapsed
		if (remaining <= 0) return true
		val deadline = System.currentTimeMillis() + remaining
		if (doLog) Log.d(TAG, "throttle wait ${remaining}ms")
		while (System.currentTimeMillis() < deadline) {
			if (shouldAbort()) return false
			delay(ABORT_POLL_MS)
		}
		return true
	}

	private fun buildSearchUrl(instanceBase: String, bounds: Bounds, limit: Int): String {
		val trimmed = instanceBase.trimEnd('/')
		val w = min(bounds.top_left.lng, bounds.bottom_right.lng)
		val e = max(bounds.top_left.lng, bounds.bottom_right.lng)
		val s = min(bounds.top_left.lat, bounds.bottom_right.lat)
		val n = max(bounds.top_left.lat, bounds.bottom_right.lat)

		return "$trimmed/api/search".toHttpUrl().newBuilder()
			.addQueryParameter("bbox", "$w,$s,$e,$n")
			.addQueryParameter("limit", limit.toString())
			.build()
			.toString()
	}

	private fun convertPanoramaxItem(item: JsonObject, source: SourceConfig): PhotoData? {
		val id = item["id"]?.jsonPrimitive?.contentOrNull ?: return null
		val coords = item["geometry"]?.jsonObject?.get("coordinates")?.jsonArray ?: return null
		if (coords.size < 2) return null
		val lng = coords[0].jsonPrimitive.doubleOrNull ?: return null
		val lat = coords[1].jsonPrimitive.doubleOrNull ?: return null

		val props = item["properties"]?.jsonObject ?: JsonObject(emptyMap())
		val assets = item["assets"]?.jsonObject

		val bearing = props["view:azimuth"]?.jsonPrimitive?.doubleOrNull
			?: props["pers:yaw"]?.jsonPrimitive?.doubleOrNull
			?: 0.0

		val thumbUrl = assets?.get("thumb")?.jsonObject?.get("href")?.jsonPrimitive?.contentOrNull
			?: props["geovisio:thumbnail"]?.jsonPrimitive?.contentOrNull
		val sdUrl = assets?.get("sd")?.jsonObject?.get("href")?.jsonPrimitive?.contentOrNull
		val hdUrl = assets?.get("hd")?.jsonObject?.get("href")?.jsonPrimitive?.contentOrNull
			?: props["geovisio:image"]?.jsonPrimitive?.contentOrNull

		val sizes = mutableMapOf<String, PhotoSize>()
		if (thumbUrl != null) sizes["thumb"] = PhotoSize(url = thumbUrl, width = 0, height = 0)
		if (sdUrl != null) sizes["sd"] = PhotoSize(url = sdUrl, width = 0, height = 0)
		if (hdUrl != null) sizes["full"] = PhotoSize(url = hdUrl, width = 0, height = 0)

		val capturedAtRaw = props["datetime"]?.jsonPrimitive?.contentOrNull
			?: props["created"]?.jsonPrimitive?.contentOrNull
		val capturedAt = capturedAtRaw?.let { parseIsoToTimestamp(it) }

		val filename = props["original_file:name"]?.jsonPrimitive?.contentOrNull ?: "$id.jpg"

		val providers = item["providers"]?.jsonArray
		val producer = providers?.firstOrNull { p ->
			p.jsonObject["roles"]?.jsonArray?.any {
				it.jsonPrimitive.contentOrNull == "producer"
			} == true
		}?.jsonObject ?: providers?.firstOrNull()?.jsonObject
		val producerId = producer?.get("id")?.jsonPrimitive?.contentOrNull
		val producerName = producer?.get("name")?.jsonPrimitive?.contentOrNull
			?: props["geovisio:producer"]?.jsonPrimitive?.contentOrNull
		val creator = if (producerId != null && producerName != null) {
			Creator(id = producerId, username = producerName)
		} else null

		val license = props["license"]?.jsonPrimitive?.contentOrNull

		val previewUrl = thumbUrl ?: hdUrl ?: sdUrl ?: ""

		return PhotoData(
			id = id,
			uid = "${source.id}-$id",
			source_type = source.type,
			filename = filename,
			url = previewUrl,
			coord = LatLng(lat = lat, lng = lng),
			bearing = bearing,
			altitude = 0.0,
			source = source.id,
			sizes = if (sizes.isEmpty()) null else sizes,
			is_device_photo = false,
			captured_at = capturedAt,
			creator = creator,
			license = license
		)
	}

	private fun parseIsoToTimestamp(raw: String): Long? {
		raw.toLongOrNull()?.let { return it }
		val formats = listOf(isoDateFormatFracTz.get(), isoDateFormatTz.get())
		for (fmt in formats) {
			try {
				return fmt?.parse(raw)?.time
			} catch (_: Exception) {
				// try next format
			}
		}
		return null
	}
}

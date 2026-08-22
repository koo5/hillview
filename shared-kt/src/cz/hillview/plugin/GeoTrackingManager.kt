package cz.hillview.plugin

/*
 GeoTrackingManager is responsible for storing geolocation and orientation datapoints. It should be usable from both ExamplePlugin and a future foreground service.

*/

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import android.util.Log
// app.tauri import removed with the carve-out to GeoTrackingCommands.kt —
// this file compiles in both apps (shared-kt).
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.util.concurrent.ConcurrentHashMap

private const val TAG = "hv-Geo"


data class OrientationSensorData(
	val magneticHeading: Float,  // Compass bearing in degrees from magnetic north (0-360°)
	val trueHeading: Float,       // Compass bearing corrected for magnetic declination
	val accuracyLevel: Int,      // Android sensor accuracy constants: -1=unknown, 0=unreliable, 1=low, 2=medium, 3=high
	val pitch: Float,
	val roll: Float,
	val timestamp: Long,
	val source: String,     // Elect-able identity — "android" for the sensor stack
	val detail: String? = null  // Which fusion mode produced it, within that source
)


class GeoTrackingManager(private val context: Context) {
	companion object {
		@Volatile
		private var INSTANCE: GeoTrackingManager? = null

		/**
		 * hillview_tracking_prefs key holding the user-picked SAF tree URI
		 * that CSV exports are created in; absent = the app-private
		 * GeoTrackingDumps/ default. Written by the settings UI (frontend2's
		 * GeoExport.android.kt), read by [dumpAndClear] — see writeExportCsv.
		 */
		const val EXPORT_TREE_URI_PREF = "export_tree_uri"

		/**
		 * "primary:DCIM/Hillview" → "DCIM/Hillview": the label a person
		 * recognizes as the folder they picked. Non-primary volumes keep
		 * their id prefix ("1234-ABCD:tracking") — it is what distinguishes
		 * an SD card, and inventing a nicer name would be a guess.
		 */
		fun exportFolderDisplayName(treeUriString: String): String = try {
			val id = DocumentsContract.getTreeDocumentId(Uri.parse(treeUriString))
			id.removePrefix("primary:").ifEmpty { id }
		} catch (e: Exception) {
			treeUriString
		}

		/**
		 * The one manager per process — use this, not the constructor.
		 *
		 * The election (like the mount offset and the heading filter state) is
		 * a fact about the SESSION, not about an object: the user elects one
		 * primary source, and every stream's rows have to be stamped with it.
		 * frontend2 held two instances, the map pane's and the capture pane's,
		 * so the pane that PUBLISHED the election and the pane that wrote the
		 * fix rows disagreed — every fix taken while the map position was
		 * elected went to disk with no election recorded at all, which is
		 * precisely the row the two-step lookup has to be able to drop.
		 * (Caught by GeoElectionBehaviourTest.theElectionReachesTheTables.)
		 *
		 * The application context, so an Activity-scoped caller cannot leak
		 * one into a process-lived field.
		 */
		fun get(context: Context): GeoTrackingManager =
			INSTANCE ?: synchronized(this) {
				INSTANCE ?: GeoTrackingManager(context.applicationContext)
					.also { INSTANCE = it }
			}
	}

	// The sensor store, in its own file since v18 — see GeoTrackingDatabase.
	private val database: GeoTrackingDatabase = GeoTrackingDatabase.getDatabase(context)

	// Cache for source name -> source ID mapping to avoid frequent DB lookups
	private val sourceIdCache = ConcurrentHashMap<String, Int>()

	private val databaseStorageIntervalMs: Long = 10

	// Storage gates, keyed by sourceId — one per table. The rules they hold,
	// and the two bugs the single shared gate had, are in SourceRateGate.
	private val orientationGate = SourceRateGate(databaseStorageIntervalMs)
	private val locationGate = SourceRateGate(databaseStorageIntervalMs)

	// The elected (primary) source for each table, held as a NAME and resolved to
	// an id at insert time, where sourceIdCache makes the lookup free.
	//
	// Pushed by the app that owns the UI, exactly like setMountOffset: only it
	// knows which stream the user chose, and only it knows not to elect a stream
	// that has not started producing yet (a compass tapped on but still warming
	// up is not the elected source until its first reading lands).
	//
	// Every row is stamped with this, whichever stream wrote it. That is what
	// lets a background stream be re-elected post-hoc to correct a bad choice,
	// and what keeps a row self-describing under the five-minute truncation and
	// across CSV files. It replaces the old "-background" source suffix, which
	// encoded the same fact by mangling the name.
	//
	// Rows written in the few milliseconds either side of a switch may carry
	// either era: the writers are independent coroutines reading a volatile.
	// Post-hoc re-election does not care about a boundary that fuzzy — and the
	// frontend hands the election to the command that writes a row alongside it,
	// so the row that *causes* an election is never mislabelled.
	@Volatile
	private var electedBearingSource: String? = null

	@Volatile
	private var electedLocationSource: String? = null

	fun setElectedBearingSource(name: String?) {
		electedBearingSource = name
		Log.d(TAG, "elected bearing source = $name")
	}

	fun setElectedLocationSource(name: String?) {
		electedLocationSource = name
		Log.d(TAG, "elected location source = $name")
	}

	/**
	 * Record a position under a named source, resolving the source id off the
	 * caller's thread. This is the shape both apps need when the user places
	 * themselves by hand: electing the map position has to WRITE that position,
	 * or the thing the app is using is recorded nowhere and the election points
	 * at a source with no rows. Tauri does this on every map pan.
	 */
	fun storeLocationNamed(
		timestamp: Long,
		latitude: Double,
		longitude: Double,
		source: String,
		detail: String? = null,
	) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val sourceId = getOrCreateSourceId(source)
				storeLocationEntity(
					LocationEntity(
						timestamp = timestamp,
						latitude = latitude,
						longitude = longitude,
						sourceId = sourceId,
						detail = detail,
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store $source location: ${e.message}", e)
			}
		}
	}

	// GPS-derived heading estimator (car mode). Kept here so the filter state
	// survives across GPS ticks independently of the frontend.
	// NOTE: temporary source tag `gps-kalman-raw` — step 3 composes it with
	// mount offset and writes the composed value under `gps-kalman`.
	private val headingFilter = HeadingFilter()

	internal suspend fun getOrCreateSourceId(sourceName: String): Int {
		// Check cache first
		sourceIdCache[sourceName]?.let { return it }

		// Not in cache, check database
		val existingId = database.sourceDao().getSourceIdByName(sourceName)
		if (existingId != null) {
			sourceIdCache[sourceName] = existingId
			return existingId
		}

		// Create new source
		database.sourceDao().insertSourceByName(sourceName)
		val newId = database.sourceDao().getSourceIdByName(sourceName)
			?: throw IllegalStateException("Failed to create source: $sourceName")
		sourceIdCache[sourceName] = newId
		return newId
	}

	fun storeOrientationSensorData(data: OrientationSensorData) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val sourceId = getOrCreateSourceId(data.source)
				storeBearingEntity(
					BearingEntity(
						timestamp = data.timestamp,
						trueHeading = data.trueHeading,
						magneticHeading = data.magneticHeading,
						accuracyLevel = data.accuracyLevel,
						sourceId = sourceId,
						detail = data.detail,
						pitch = data.pitch,
						roll = data.roll
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store orientation sensor data: ${e.message}", e)
			}
		}
	}

	// storeOrientationManual / storeLocationManual (the JSObject-taking Tauri
	// command handlers) moved to the app-side GeoTrackingCommands.kt as
	// extension functions — they are the only Tauri coupling this class had.
	// The three members below are `internal` (not private) so they can reach
	// back in.

	internal fun storeBearingEntity(entity: BearingEntity) {
		if (!orientationGate.allow(entity.sourceId)) {
			return
		}
		CoroutineScope(Dispatchers.IO).launch {
			try {
				// Every bearing write funnels through here, so the election is
				// stamped in exactly one place and no caller can forget it.
				val elected = electedBearingSource?.let { getOrCreateSourceId(it) }
				database.bearingDao().insertBearing(entity.copy(electedSourceId = elected))
			} catch (e: Exception) {
				Log.w(TAG, "Failed to store bearing in database: ${e.message}")
			}
		}
	}


	internal fun storeLocationEntity(entity: LocationEntity) {
		if (!locationGate.allow(entity.sourceId)) {
			return
		}
		CoroutineScope(Dispatchers.IO).launch {
			try {
				// Single stamping point — see storeBearingEntity.
				val elected = electedLocationSource?.let { getOrCreateSourceId(it) }
				database.locationDao().insertLocation(entity.copy(electedSourceId = elected))
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store location in database: ${e.message}", e)
			}
		}
	}

	// Current camera-mount offset (degrees) applied to GPS-derived travel heading.
	// Frontend pushes this via set_mount_offset when the user adjusts the shooting
	// angle; defaults to 0 (camera points in the direction of travel).
	@Volatile
	private var mountOffset: Double = 0.0

	fun setMountOffset(offsetDegrees: Double) {
		mountOffset = normalizeBearingDegrees(offsetDegrees)
	}

	fun getMountOffset(): Double = mountOffset

	/**
	 * Run the GPS-derived heading filter on a new location sample and, if it
	 * produced a heading, compose it with the current mount offset and persist
	 * the composed absolute as a `gps-kalman` bearing.
	 *
	 * Returns the composed bearing (0-360°) so the caller can emit it to the
	 * frontend, or null when the filter rejected the sample.
	 */
	fun feedLocationForHeadingFilter(data: PreciseLocationData): Double? {
		val travel = headingFilter.update(
			FilterPosition(
				lat = data.latitude,
				lng = data.longitude,
				speed = data.speed?.toDouble(),
				timestamp = data.timestamp
			)
		) ?: return null
		val composed = normalizeBearingDegrees(travel + mountOffset)
		CoroutineScope(Dispatchers.IO).launch {
			try {
				val sourceId = getOrCreateSourceId("gps-kalman")
				storeBearingEntity(
					BearingEntity(
						timestamp = data.timestamp,
						trueHeading = composed.toFloat(),
						magneticHeading = null,
						accuracyLevel = null,
						sourceId = sourceId,
						pitch = null,
						roll = null
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store gps-kalman bearing: ${e.message}", e)
			}
		}
		return composed
	}

	fun resetHeadingFilter() {
		headingFilter.reset()
	}

	fun storeLocationPreciseLocationData(data: PreciseLocationData) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				// The Android location API is one elect-able source; which
				// provider inside it produced the fix ("fused"/"gps"/"network")
				// is provenance, so it moves to `detail`. Fixes taken while the
				// user has panned away are no longer renamed — they keep this
				// name and simply are not the elected source, which the row
				// records for itself.
				val sourceId = getOrCreateSourceId("android")
				storeLocationEntity(
					LocationEntity(
						timestamp = data.timestamp,
						latitude = data.latitude,
						longitude = data.longitude,
						sourceId = sourceId,
						detail = data.provider,
						altitude = data.altitude,
						accuracy = data.accuracy,
						verticalAccuracy = data.altitudeAccuracy,
						speed = data.speed,
						bearing = data.bearing
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store location data: ${e.message}", e)
				throw e
			}
		}
	}

	// (storeLocationManual moved to GeoTrackingCommands.kt — see note above.)

	/**
	 * Clears old geo tracking data and optionally exports to CSV.
	 * @param forceDump If true, always export to CSV. If false, check auto_export preference.
	 */
	fun dumpAndClear(forceDump: Boolean = false) {
		val now = System.currentTimeMillis()

		// Check if we should dump based on preference or force flag
		val prefs = context.getSharedPreferences("hillview_tracking_prefs", Context.MODE_PRIVATE)
		val autoExportEnabled = prefs.getBoolean("auto_export", false)
		val shouldDump = forceDump || autoExportEnabled

		CoroutineScope(Dispatchers.IO).launch {
			if (shouldDump) {
				try {
					val sourceIdToName = buildSourceIdToNameMap()

					val bearings = database.bearingDao().getAllBearings()
					val bearingsAt = writeExportCsv(
						"hillview_orientations_${now}.csv",
						bearingsToCsv(bearings, sourceIdToName),
					)
					Log.i(TAG, "🢄📡 Dumped ${bearings.size} bearings to $bearingsAt")

					val locations = database.locationDao().getAllLocations()
					val locationsAt = writeExportCsv(
						"hillview_locations_${now}.csv",
						locationsToCsv(locations, sourceIdToName),
					)
					Log.i(TAG, "🢄📡 Dumped ${locations.size} locations to $locationsAt")
					EventLog.record(
						"export",
						"${bearings.size} bearings + ${locations.size} locations → $locationsAt",
					)
				} catch (e: Exception) {
					Log.e(TAG, "🢄📡 Failed to dump geo tracking data: ${e.message}", e)
					EventLog.record("export", "CSV dump FAILED: ${e.message}")
				}
			} else {
				Log.d(TAG, "🢄📡 Skipping geo data dump (auto_export disabled)")
			}

			// Always clear old data
			val cutoff = now - 1000 * 60 * 5

			try {
				database.bearingDao().clearBearingsOlderThan(cutoff)
				database.locationDao().clearLocationsOlderThan(cutoff)
				Log.i(TAG, "🢄📡 Geo tracking tables cleared")
			} catch (e: Exception) {
				Log.e(TAG, "🢄📡 Failed to clear geo tracking tables: ${e.message}", e)
			}
		}
	}

	/**
	 * Where an exported CSV lands, and the reason it is a choice at all:
	 * the default — the app's external-files GeoTrackingDumps/ — needs no
	 * permission but DIES WITH THE APP (Android deletes Android/data/<pkg>
	 * on uninstall) and is unreachable to file managers since Android 11.
	 * A CSV cannot simply go somewhere durable instead: public typed
	 * directories refuse non-media files, and unprompted writes into
	 * Documents/ would litter a folder the user never asked us into. So
	 * durability is the USER'S call, made through the system folder picker
	 * (ACTION_OPEN_DOCUMENT_TREE): the picked tree URI is persisted as
	 * `export_tree_uri` in hillview_tracking_prefs, and while it is set and
	 * its grant alive, exports are created there via DocumentsContract —
	 * any folder the picker offers, including ones this app could never
	 * touch directly. Framework APIs only, deliberately: shared-kt must
	 * compile in both apps without new dependencies. The Tauri app has no
	 * picker UI, never sets the pref, and keeps its old behaviour exactly.
	 *
	 * @return a human-readable locator of where the bytes actually went.
	 */
	private fun writeExportCsv(displayName: String, content: String): String {
		val prefs = context.getSharedPreferences("hillview_tracking_prefs", Context.MODE_PRIVATE)
		val treeUriString = prefs.getString(EXPORT_TREE_URI_PREF, null)
		if (treeUriString != null) {
			try {
				val treeUri = Uri.parse(treeUriString)
				val parent = DocumentsContract.buildDocumentUriUsingTree(
					treeUri,
					DocumentsContract.getTreeDocumentId(treeUri),
				)
				val fileUri = DocumentsContract.createDocument(
					context.contentResolver, parent, "text/csv", displayName,
				) ?: throw java.io.IOException("createDocument returned null")
				context.contentResolver.openOutputStream(fileUri)?.use {
					it.write(content.toByteArray(Charsets.UTF_8))
				} ?: throw java.io.IOException("openOutputStream returned null")
				return exportFolderDisplayName(treeUriString) + "/" + displayName
			} catch (e: SecurityException) {
				// The grant is dead — the folder was deleted, or this is a
				// reinstall (persisted grants do not survive one). Retrying
				// every dump forever would fail every 5 minutes in external
				// mode, so the choice is dropped, loudly.
				prefs.edit().remove(EXPORT_TREE_URI_PREF).apply()
				Log.w(TAG, "🢄📡 export folder grant lost — back to app-private", e)
				EventLog.record(
					"export",
					"chosen folder unreachable (${e.message}) — exports back to app-private",
				)
			} catch (e: Exception) {
				// Transient (provider hiccup, storage full there): fall back
				// for THIS file, keep the choice.
				Log.w(TAG, "🢄📡 export to chosen folder failed, using app-private", e)
			}
		}
		val dir = File(context.getExternalFilesDir(null), "GeoTrackingDumps")
		if (!dir.exists()) dir.mkdirs()
		val file = File(dir, displayName)
		file.writeText(content)
		return file.absolutePath
	}

	private suspend fun buildSourceIdToNameMap(): Map<Int, String> {
		// Start with reverse lookup from existing cache
		val idToName = mutableMapOf<Int, String>()
		for ((name, id) in sourceIdCache) {
			idToName[id] = name
		}

		// Query all sources to fill gaps
		val allSources = database.sourceDao().getAllSources()
		for (source in allSources) {
			idToName[source.id] = source.name
		}

		return idToName
	}

	private fun escapeCsv(value: String?): String {
		val str = value ?: ""
		return if (str.contains(",") || str.contains("\"") || str.contains("\n")) {
			"\"${str.replace("\"", "\"\"")}\""
		} else {
			str
		}
	}

	private fun bearingsToCsv(bearings: List<BearingEntity>, sourceIdToName: Map<Int, String>): String {
		// `detail` is appended, not slotted next to `source`: readers key on the
		// header name, so a column added at the end never shifts an existing one.
		val header = "#timestamp,trueHeading,magneticHeading,accuracyLevel,source,pitch,roll,detail,elected\n"
		val rows = bearings.joinToString("\n") { bearing ->
			val sourceName = escapeCsv(sourceIdToName[bearing.sourceId] ?: "unknown")
			// Blank when no election was recorded — a reader that finds it blank
			// should fall back to source-blind behaviour for that row.
			val elected = escapeCsv(bearing.electedSourceId?.let { sourceIdToName[it] })
			"${bearing.timestamp},${bearing.trueHeading},${bearing.magneticHeading ?: ""},${bearing.accuracyLevel ?: ""},${sourceName},${bearing.pitch ?: ""},${bearing.roll ?: ""},${escapeCsv(bearing.detail)},${elected}"
		}
		return header + rows + "\n"
	}

	private fun locationsToCsv(locations: List<LocationEntity>, sourceIdToName: Map<Int, String>): String {
		val header = "#timestamp,latitude,longitude,source,altitude,accuracy,verticalAccuracy,speed,bearing,detail,elected\n"
		val rows = locations.joinToString("\n") { location ->
			val sourceName = escapeCsv(sourceIdToName[location.sourceId] ?: "unknown")
			val elected = escapeCsv(location.electedSourceId?.let { sourceIdToName[it] })
			"${location.timestamp},${location.latitude},${location.longitude},${sourceName},${location.altitude ?: ""},${location.accuracy ?: ""},${location.verticalAccuracy ?: ""},${location.speed ?: ""},${location.bearing ?: ""},${escapeCsv(location.detail)},${elected}"
		}
		return header + rows + "\n"
	}

}

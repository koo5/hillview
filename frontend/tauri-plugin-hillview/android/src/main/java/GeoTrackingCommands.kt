package cz.hillview.plugin

/*
 Tauri-bridge command handlers, split out of GeoTrackingManager (2026-08) so
 that class can live in shared-kt — frontend2 has no Tauri runtime. Bodies
 are verbatim; member functions became extension functions on
 GeoTrackingManager, call sites unchanged. Same TAG so log output is
 unchanged. Surplus imports kept until the final formatting pass.
*/

import android.content.Context
import android.util.Log
import app.tauri.plugin.JSObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File
import java.util.concurrent.ConcurrentHashMap

private const val TAG = "Geo"

	fun GeoTrackingManager.storeOrientationManual(params: JSObject) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				// JSObject.getLong is not overridden and JSONObject.getLong throws on missing
				// keys — the `?: System.currentTimeMillis()` default was dead code. Use has()
				// for optional fields. Same pattern below for source and storeLocationManual.
				val timestamp = if (params.has("timestamp")) params.getLong("timestamp") else System.currentTimeMillis()
				// JSObject.getDouble is non-nullable; a missing key throws. Let that propagate
				// (caught below); don't dress it up with a dead Elvis throw.
				val trueHeading = params.getDouble("trueHeading").toFloat()
				// JSObject.getString(key, default) is the two-arg overload that actually
				// honors the default when the key is missing; the single-arg overload returns
				// "" for missing keys, making `?: "manual"` dead code.
				val source = params.getString("source", "manual") ?: "manual"
				val sourceId = getOrCreateSourceId(source)

				storeBearingEntity(
					BearingEntity(
						timestamp = timestamp,
						trueHeading = trueHeading,
						magneticHeading = if (params.has("magneticHeading")) params.getDouble("magneticHeading").toFloat() else null,
						accuracyLevel = if (params.has("accuracyLevel")) params.getInteger("accuracyLevel") else null,
						sourceId = sourceId,
						pitch = if (params.has("pitch")) params.getDouble("pitch").toFloat() else null,
						roll = if (params.has("roll")) params.getDouble("roll").toFloat() else null
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store manual orientation: ${e.message}", e)
				throw e
			}
		}
	}

	fun GeoTrackingManager.storeLocationManual(params: JSObject) {
		CoroutineScope(Dispatchers.IO).launch {
			try {
				// See notes in storeOrientationManual for why these patterns changed.
				val timestamp = if (params.has("timestamp")) params.getLong("timestamp") else System.currentTimeMillis()
				val latitude = params.getDouble("latitude")
				val longitude = params.getDouble("longitude")
				val source = params.getString("source", "manual") ?: "manual"
				val sourceId = getOrCreateSourceId(source)

				storeLocationEntity(
					LocationEntity(
						timestamp = timestamp,
						latitude = latitude,
						longitude = longitude,
						sourceId = sourceId,
						altitude = if (params.has("altitude")) params.getDouble("altitude") else null,
						accuracy = if (params.has("accuracy")) params.getDouble("accuracy").toFloat() else null,
						verticalAccuracy = if (params.has("verticalAccuracy")) params.getDouble("verticalAccuracy").toFloat() else null,
						speed = if (params.has("speed")) params.getDouble("speed").toFloat() else null,
						bearing = if (params.has("bearing")) params.getDouble("bearing").toFloat() else null
					)
				)
			} catch (e: Exception) {
				Log.e(TAG, "Failed to store manual location: ${e.message}", e)
				throw e
			}
		}
	}

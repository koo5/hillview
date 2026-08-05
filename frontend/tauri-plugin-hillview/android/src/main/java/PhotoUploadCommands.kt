package cz.hillview.plugin

import android.app.*
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.net.ConnectivityManager
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.json.JSONArray
import app.tauri.plugin.JSObject
import app.tauri.plugin.Invoke
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.*
import java.util.concurrent.TimeUnit
import androidx.work.ListenableWorker

// Database imports for duplicate handling
import cz.hillview.plugin.PhotoDatabase
import cz.hillview.plugin.PhotoEntity
import cz.hillview.plugin.PhotoUploadLogic.ServerPhotoStatus

// Tauri-bridge command handlers, split out of PhotoUploadLogic (2026-08) so
// the rest of that file can live in shared-kt — frontend2 has no Tauri
// runtime. Bodies are verbatim; member functions became extension functions
// on PhotoUploadLogic, call sites unchanged. Surplus imports above are kept
// until the final formatting pass.

// Same tag as PhotoUploadLogic so log output is unchanged.
private const val TAG = "🢄Upload"





    /**
     * Handle get_processing_photo_ids cmd from frontend.
     * Returns list of serverPhotoIds for photos in "processing" state.
     */
    fun PhotoUploadLogic.handleGetProcessingPhotoIds(invoke: Invoke) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val processingPhotos = photoDao.getProcessingPhotos()
                val serverPhotoIds = processingPhotos.mapNotNull { it.serverPhotoId }

                val result = JSObject()
                result.put("success", true)
                result.put("photo_ids", JSONArray(serverPhotoIds))
                invoke.resolve(result)

            } catch (e: Exception) {
                Log.e(TAG, "Error getting processing photo IDs", e)
                val error = JSObject()
                error.put("success", false)
                error.put("error", e.message)
                invoke.resolve(error)
            }
        }
    }

    /**
     * Handle create_edit cmd from frontend.
     * Creates an edit action for a photo (e.g., setting anonymization override).
     * Params: { photo_id: string, action: string, value: any }
     */
    fun PhotoUploadLogic.handleCreateEdit(invoke: Invoke, params: JSObject) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val photoId = params.getString("photo_id")
                val action = params.getString("action")

                // Build action JSON
                val actionJson = JSONObject()
                actionJson.put("action", action)

                // Handle value - can be null, array, or object
                if (params.has("value")) {
                    if (params.isNull("value")) {
                        actionJson.put("value", JSONObject.NULL)
                    } else {
                        // Try to get as JSONArray first, then as other types
                        try {
                            val valueArray = params.getJSONArray("value")
                            actionJson.put("value", valueArray)
                        } catch (e: Exception) {
                            // Not an array, try other types
                            actionJson.put("value", params.get("value"))
                        }
                    }
                } else {
                    actionJson.put("value", JSONObject.NULL)
                }

                val editId = createEdit(photoId, actionJson)

                val result = JSObject()
                result.put("success", true)
                result.put("edit_id", editId)
                invoke.resolve(result)

            } catch (e: Exception) {
                Log.e(TAG, "Error creating edit", e)
                val error = JSObject()
                error.put("success", false)
                error.put("error", e.message)
                invoke.resolve(error)
            }
        }
    }

    /**
     * Handle check_photo_file_exists cmd from frontend.
     * Checks if the photo file exists on disk.
     * Params: { photo_id: string }
     */
    fun PhotoUploadLogic.handleCheckPhotoFileExists(invoke: Invoke, params: JSObject) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val photoId = params.getString("photo_id")

                val photo = photoDao.getPhotoById(photoId)

                val result = JSObject()
                if (photo == null) {
                    result.put("success", false)
                    result.put("error", "Photo not found in database")
                } else {
                    val fileExists = PhotoUtils.pathExists(context, photo.path)
                    result.put("success", true)
                    result.put("exists", fileExists)
                    result.put("path", photo.path)
                }
                invoke.resolve(result)

            } catch (e: Exception) {
                Log.e(TAG, "Error checking photo file exists", e)
                val error = JSObject()
                error.put("success", false)
                error.put("error", e.message)
                invoke.resolve(error)
            }
        }
    }

    /**
     * Handle get_photo_id_by_server_photo_id cmd from frontend.
     * Returns the device photo ID for a given server photo ID.
     * Params: { server_photo_id: string }
     */
    fun PhotoUploadLogic.handleGetPhotoIdByServerPhotoId(invoke: Invoke, params: JSObject) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val serverPhotoId = params.getString("server_photo_id")

                val photo = photoDao.getPhotoByServerPhotoId(serverPhotoId)

                val result = JSObject()
                if (photo != null) {
                    result.put("success", true)
                    result.put("photo_id", photo.id)
                } else {
                    result.put("success", false)
                    result.put("error", "Photo not found for server ID: $serverPhotoId")
                }
                invoke.resolve(result)

            } catch (e: Exception) {
                Log.e(TAG, "Error getting photo ID by server photo ID", e)
                val error = JSObject()
                error.put("success", false)
                error.put("error", e.message)
                invoke.resolve(error)
            }
        }
    }

    /**
     * Handle get_photo_anonymization_state cmd from frontend.
     * Returns the effective anonymization state after applying pending edits.
     * Params: { photo_id: string }
     * Returns: { success: true, state: "auto" | "none" | "custom", value: null | "[]" | "[{...}]" }
     */
    fun PhotoUploadLogic.handleGetPhotoAnonymizationState(invoke: Invoke, params: JSObject) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val photoId = params.getString("photo_id")

                val anonState = getPhotoAnonymizationState(photoId)

                if (anonState == null) {
                    val error = JSObject()
                    error.put("success", false)
                    error.put("error", "Photo not found in database")
                    invoke.resolve(error)
                    return@launch
                }

                val result = JSObject()
                result.put("success", true)
                result.put("state", anonState.state)
                if (anonState.value != null) {
                    result.put("value", anonState.value)
                } else {
                    result.put("value", JSONObject.NULL)
                }
                invoke.resolve(result)

            } catch (e: Exception) {
                Log.e(TAG, "Error getting photo anonymization state", e)
                val error = JSObject()
                error.put("success", false)
                error.put("error", e.message)
                invoke.resolve(error)
            }
        }
    }

    /**
     * Handle update_photo_statuses cmd from frontend.
     * Params: { statuses: [{ id, processing_status, error }] }
     */
    fun PhotoUploadLogic.handleUpdatePhotoStatuses(invoke: Invoke, params: JSObject) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val statusesArray = params.getJSONArray("statuses")
                val updatedCount = updatePhotoStatusesFromJson(statusesArray)

                val result = JSObject()
                result.put("success", true)
                result.put("updated_count", updatedCount)
                invoke.resolve(result)

            } catch (e: Exception) {
                Log.e(TAG, "Error updating photo statuses", e)
                val error = JSObject()
                error.put("success", false)
                error.put("error", e.message)
                invoke.resolve(error)
            }
        }
    }

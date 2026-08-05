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

// DuplicateFileException / WorkerBusyException moved to shared-kt UploadProtocol.kt (same package).

/**
 * Secure Upload Manager for Android Background Uploads
 *
 * Implements the three-phase secure upload process for PhotoEntity records:
 * 1. Request upload authorization from API server (using PhotoEntity geolocation)
 * 2. Generate client signature and upload to worker (using worker_url from auth response)
 * 3. Worker verifies JWT and forwards results to API server
 *
 * This ensures that even compromised workers cannot impersonate users.
 *
 * Also provides foreground service capabilities for persistent uploads with notifications.
 */
class PhotoUploadLogic(private val context: Context) {
	private val database: PhotoDatabase = PhotoDatabase.getDatabase(context)
	private val photoDao = database.photoDao()
	private val editDao = database.editDao()

	companion object {
		private const val TAG = "🢄Upload"
		private const val doLog = false
		private const val PREFS_NAME = "hillview_upload_prefs"
		private const val PREF_SERVER_URL = "server_url"

		// Close the pooled connection to the Fly edge after this many successful
		// uploads. Fly routes per connection; a sequential upload drain rides one
		// keep-alive connection and stays pinned to one worker machine until its
		// 30-photo queue fills and 503s the whole pass. A fresh connection gets a
		// fresh machine choice (busy machines sit at their connection soft_limit
		// thanks to the API's standing /await pingbacks), so the drain migrates to
		// a new/woken machine instead of stalling on a full one.
		private const val RECONNECT_EVERY_N_UPLOADS = 5

		// Foreground service constants
		private const val NOTIFICATION_ID = 2001
		private const val CHANNEL_ID = "photo_upload_foreground"
		const val ACTION_START_UPLOAD = "start_upload"
		const val ACTION_STOP_UPLOAD = "stop_upload"

		private val workerMutex = Mutex()
	}

	private val client = OkHttpClient.Builder()
		.connectTimeout(100, TimeUnit.SECONDS)
		.writeTimeout(300, TimeUnit.SECONDS)
		.readTimeout(300, TimeUnit.SECONDS)
		.build()

	// Worker machine pinning (mirrors uploadProtocol.ts): /ready returns the
	// answering machine's fly_machine_id; a busy machine's 503 carries
	// fly-replay, so the Fly edge transparently re-runs the preflight on a
	// sibling (waking a stopped one if needed — validated live 2026-07-13) and
	// we receive the sibling's ready + id instead. Pin uploads to that machine
	// via fly-force-instance-id; clear on busy/IO failure so the next preflight
	// re-discovers. Never persisted — machine ids churn on every deploy.
	@Volatile
	private var pinnedWorkerMachine: String? = null

	private val prefs: SharedPreferences by lazy { context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }
	private val authManager by lazy { AuthenticationManager(context) }
	private val clientCrypto by lazy { ClientCryptoManager(context) }
	private val uploadProtocol by lazy {
		UploadProtocol(client, object : UploadTokenProvider {
			override suspend fun getValidToken() = authManager.getValidToken()
			override suspend fun forceRefreshToken() = authManager.forceRefreshToken()
		})
	}
	private val notificationHelper by lazy { NotificationHelper(context) }



	// UploadAuthorizationResponse moved to shared-kt UploadProtocol.kt.


	suspend fun doWorkInternal(triggerSource: String, photoId: String?, onProgress: ((String) -> Unit)? = null, onBeforePhoto: (suspend () -> Unit)? = null): androidx.work.ListenableWorker.Result {
		workerMutex.withLock {

			try {

				Log.d(
					TAG,
					"doWork - starting unified upload processing (triggered by: $triggerSource), specific photo ID: $photoId"
				)

				// For scheduled runs, scan for new photos first // we want to avoid this when invoked just to upload currently captured photo
				if (triggerSource == "scheduled") {
					Log.d(
						TAG,
						"Scheduled run detected - scanning for new photos"
					)
					scanForNewPhotos()
				}

				// Process any pending edits before upload loop
				processPendingEdits()

				// Process photos one at a time with validation on each iteration

				val seen = mutableSetOf<String>()
				var uploadedCount = 0
				// Snapshot denominator for the progress notification: the same
				// candidate predicate the loop uses — status/staleness in SQL
				// (getUploadableCandidates) + backoff via isEligibleNow.
				// Validation drops are loop-only, so N can be a touch high, never low.
				val nowSnap = System.currentTimeMillis()
				val total = photoDao.getUploadableCandidates(
					nowSnap - 1000 * 60 * 10,
					nowSnap - 1000 * 60 * 60
				).count { isEligibleNow(it, triggerSource, nowSnap) }

				var workerBusy = false
				var networkDeferred = false
				while (true) {
					// Stop promptly when WorkManager cancels this run (e.g. the
					// wifi-only constraint stopped holding mid-drain) — everything
					// below is blocking I/O that never notices cancellation by itself.
					currentCoroutineContext().ensureActive()

					// Check auto-upload setting on each iteration
					val prefs = context.getSharedPreferences("hillview_upload_prefs", Context.MODE_PRIVATE)
					val autoUploadEnabled = prefs.getBoolean("auto_upload_enabled", false)

					// Bulk drains obey the auto-upload toggle per photo — WorkManager
					// jobs (and their retry chains) are persistent and can outlive a
					// toggle flip by hours, so the enqueue-time gate in
					// startAutomaticUpload is not enough. An explicitly targeted
					// photoId is a manual action and proceeds regardless.
					if (!autoUploadEnabled && photoId.isNullOrEmpty()) {
						Log.d(
							TAG,
							"Auto upload disabled, stopping upload work"
						)
						break
					}

					// Enforce wifi-only at the point of upload, not only at
					// enqueue. The WorkManager UNMETERED constraint gates job
					// START: a drain that began on wifi keeps running after the
					// network switches to mobile data (the stop signal arrives
					// with latency and blocking I/O ignores it), and a job
					// enqueued back when wifi_only was still off carries its
					// permissive CONNECTED constraint forever under KEEP. The
					// manual retry button keeps its documented bypass.
					if (prefs.getBoolean("wifi_only", false)
						&& triggerSource != "retry_button"
						&& isActiveNetworkMetered()
					) {
						Log.d(TAG, "wifi-only is set and active network is metered — deferring drain")
						networkDeferred = true
						break
					}

					// sleep a bit
					Thread.sleep(100L)

					// Re-check app background state each iteration so a drain the
					// user backgrounds mid-way promotes to a foreground service.
					onBeforePhoto?.invoke()

					// Get next photo to upload (pending priority over failed)
					val photo: PhotoEntity?

					if (!photoId.isNullOrEmpty())
					{
						photo = photoDao.getPhotoById(photoId)
					}
					else
					{
						val now = System.currentTimeMillis()
						val uploadingStaleThreshold = now - 1000 * 60 * 10  // 10 minutes
						val processingStaleThreshold = now - 1000 * 60 * 60 // 1 hour
						photo = photoDao.getNextPhotoForUpload(seen, uploadingStaleThreshold, processingStaleThreshold)
					}

					if (photo == null) {
						Log.d(TAG, "No more photos to upload")
						break
					}

					seen.add(photo.id);

					Log.d(
						TAG,
						"Next photo to process: ${photo.filename} (status: ${photo.uploadStatus})"
					)

					// For failed uploads, skip until the backoff has elapsed
					// (manual retry bypasses). Same predicate the snapshot count
					// uses — see isEligibleNow.
					if (!isEligibleNow(photo, triggerSource, System.currentTimeMillis())) {
						Log.d(
							TAG,
							"Skipping retry for ${photo.filename} - not enough time elapsed"
						)
						continue
					}

					// Validate auth token on each iteration
					val authToken = authManager.getValidToken()
					if (authToken == null) {
						Log.w(
							TAG,
							"🔐 No valid auth token available, stopping upload work"
						)
						break
					}

					// Process this photo
					try {
						if (!validatePhotoForUpload(photo)) {
							continue
						}

						val action = if (photo.uploadStatus == "failed") "retry" else "upload"
						Log.d(
							TAG,
							"Attempting $action for ${photo.filename} with hash: ${photo.fileHash}"
						)

						onProgress?.invoke("Uploading photo ${uploadedCount + 1} of ${maxOf(total, uploadedCount + 1)}...")
						photoDao.updateUploadStatus(photo.id, "uploading", System.currentTimeMillis())

						val serverPhotoId = secureUploadPhoto(photo)

						if (serverPhotoId != null) {
							uploadedCount++
							Log.d(
								TAG,
								"✅ Successfully ${action}ed ${photo.filename}, server ID: $serverPhotoId"
							)
							photoDao.updateUploadStatusAndServerId(
								photo.id,
								"processing",
								serverPhotoId,
								System.currentTimeMillis()
							)
							if (uploadedCount % RECONNECT_EVERY_N_UPLOADS == 0) {
								// Drop the pooled edge connection so the next upload
								// re-load-balances — see RECONNECT_EVERY_N_UPLOADS.
								Log.d(TAG, "🔌 Cycling worker connection after $uploadedCount uploads")
								client.connectionPool.evictAll()
							}
						} else {
							Log.w(
								TAG,
								"❌ Failed to $action ${photo.filename}"
							)
							photoDao.updateUploadFailure(
								photo.id,
								"failed",
								photo.retryCount + 1,
								System.currentTimeMillis(),
								"$action failed"
							)
						}

					} catch (e: DuplicateFileException) {
						// Duplicate already handled - database already updated to "completed"
						Log.i(TAG, "✅ Duplicate file handled for ${photo.filename}")
						// Continue to next photo
					} catch (e: WorkerBusyException) {
						// Worker upload queue is full — restore the photo's prior
						// status (no retryCount burn, original uploadedAt) and abort
						// the whole pass instead of draining the rest of the queue
						// at a worker that will reject every body.
						Log.w(TAG, "⏳ Worker busy, aborting upload pass: ${e.message}")
						photoDao.updateUploadStatus(photo.id, photo.uploadStatus, photo.uploadedAt)
						workerBusy = true
						break
					} catch (e: CancellationException) {
						// WorkManager stopped this run (network constraint lost,
						// shutdown). Not a failure of THIS photo: restore its prior
						// status instead of burning a retry, then let the
						// cancellation propagate so the drain actually stops — the
						// generic catch below used to swallow it and keep looping,
						// marking every remaining photo "failed".
						photoDao.updateUploadStatus(photo.id, photo.uploadStatus, photo.uploadedAt)
						throw e
					} catch (e: Exception) {
						Log.e(
							TAG,
							"💥 Error during upload for ${photo.filename}",
							e
						)
						photoDao.updateUploadFailure(
							photo.id,
							"failed",
							photo.retryCount + 1,
							System.currentTimeMillis(),
							e.message ?: "Unknown error"
						)
					}
				}


				// Status sync for "processing" photos runs as its own WorkManager
				// job (PhotoStatusSyncWorker) instead of inline here. While the
				// sync's network round-trip ran inside this worker, the job
				// lingered in RUNNING for seconds after the final null
				// getNextPhotoForUpload query — and ExistingWorkPolicy.KEEP
				// silently dropped the capture triggers that arrived in that
				// window, leaving the session's last photo stuck in "pending".
				if (photoDao.getProcessingPhotos().isNotEmpty()) {
					PhotoUploadManager(context).schedulePostUploadStatusSync()
				}

				if (workerBusy) {
					Log.d(TAG, "Worker busy — letting WorkManager reschedule the drain")
					return ListenableWorker.Result.retry()
				}

				if (networkDeferred) {
					Log.d(TAG, "Metered network with wifi-only — letting WorkManager reschedule the drain")
					return ListenableWorker.Result.retry()
				}

				Log.d(TAG, "Photo upload worker completed successfully")
				return ListenableWorker.Result.success()

			} catch (e: CancellationException) {
				// Stopped by WorkManager — propagate so the run counts as
				// stopped, not failed; WorkManager re-runs it when the
				// constraints hold again.
				throw e
			} catch (e: Exception) {
				Log.e(TAG, "Photo upload worker failed", e)
				return ListenableWorker.Result.retry()
			}
		}
	}


	private fun scanForNewPhotos() {
		Log.d(TAG, "Scanning for new photos")

		val directories = getPhotoDirectories()
		var newPhotosFound = 0
		var scanErrors = 0

		for (directory in directories) {
			if (!directory.exists()) {
				Log.d(TAG, "Directory does not exist: ${directory.path}")
				continue
			}

			val imageFiles = directory.listFiles { file ->
				file.isFile && file.extension.lowercase() in listOf("jpg", "jpeg", "png", "webp")
			} ?: continue

			Log.d(
				TAG,
				"Found ${imageFiles.size} image files in ${directory.path}"
			)

			for (file in imageFiles) {
				try {

					Log.w(TAG, "Processing file: ${file.path}")

					// Calculate file hash for duplicate detection
					val fileHash = PhotoUtils.calculateFileHash(file)
					if (fileHash == null) {
						Log.w(
							TAG,
							"Failed to calculate hash for ${file.path}"
						)
						scanErrors++
						continue
					}

					// Check for duplicates by path or hash
					val existingByPath = photoDao.getPhotoByPath(file.path)
					val existingByHash = photoDao.getPhotoByHash(fileHash)

					if (existingByPath != null || existingByHash != null) {
						// Photo already exists, skip
						continue
					}

					// Create metadata for new photo with EXIF data
					val photoEntity = PhotoUtils.createPhotoEntityFromFile(file, fileHash)
					photoDao.insertPhoto(photoEntity)
					newPhotosFound++
					Log.d(
						TAG,
						"Added new photo to database: ${file.name}"
					)

				} catch (e: Exception) {
					Log.w(
						TAG,
						"Failed to process photo ${file.path}: ${e.message}"
					)
					scanErrors++
				}

				Log.w(TAG, "loop..");
			}
		}

		Log.d(
			TAG,
			"Scan complete. Added $newPhotosFound new photos, $scanErrors errors"
		)
	}


	/**
	 * Process pending edits from the edits table.
	 * Edits are actions like setting anonymization override that trigger re-uploads.
	 */
	private fun processPendingEdits() {
		val pendingEdits = editDao.getPendingEdits()
		if (pendingEdits.isEmpty()) {
			return
		}

		Log.d(TAG, "Processing ${pendingEdits.size} pending edits")

		for (edit in pendingEdits) {
			try {
				val actionJson = JSONObject(edit.actionJson)
				val action = actionJson.optString("action")

				when (action) {
					"set_anonymization_override" -> {
						// value can be: null (auto-detect), [] (skip), [{...}] (manual rectangles)
						val override: String? = if (actionJson.isNull("value")) {
							null
						} else {
							actionJson.getJSONArray("value").toString()
						}

						Log.d(TAG, "Processing set_anonymization_override for photo ${edit.photoId}: $override")
						photoDao.updateAnonymizationOverride(edit.photoId, override)
					}
					else -> {
						Log.w(TAG, "Unknown edit action: $action")
					}
				}

				editDao.markProcessed(edit.id, System.currentTimeMillis())
				Log.d(TAG, "Edit ${edit.id} processed successfully")

			} catch (e: Exception) {
				Log.e(TAG, "Error processing edit ${edit.id}: ${e.message}", e)
				// Don't mark as processed - will retry next time
			}
		}
	}


	/**
	 * Upload photo securely.
	 * @return Server photo ID on success, null on failure
	 */
	suspend fun secureUploadPhoto(photo: PhotoEntity): String? = withContext(Dispatchers.IO) {
		try {
			Log.d(TAG, "Starting secure upload for photo: ${photo.filename}")

			if (!PhotoUtils.pathExists(context, photo.path)) {
				Log.e(TAG, "Photo file does not exist: ${photo.path}")
				return@withContext null
			}

			// Step 1: Request upload authorization (includes PhotoEntity geolocation)
			// Note: Uses photo.fileSize from database, doesn't need to read file yet
			val authResponse = requestUploadAuthorization(photo)
			Log.d(TAG, "Upload authorized, response: $authResponse")

			// Store server photo ID mapping immediately after authorization,
			// so the frontend can look up the device photo while upload is in progress
			photoDao.updateServerPhotoId(photo.id, authResponse.photo_id)

			// Step 2: Generate client signature using authorization timestamp
			val signatureData =
				generateClientSignature(authResponse.photo_id, photo.filename, authResponse.upload_authorized_at)
			if (signatureData == null) {
				Log.e(TAG, "Failed to generate client signature for: ${photo.filename}")
				return@withContext null
			}

			Log.d(TAG, "Client signature generated for: ${photo.filename} with key ${signatureData.keyId}")

			// Step 3: Upload to worker (using worker_url from auth response)
			val fileBytes = PhotoUtils.readBytesFromPath(context, photo.path)
			if (fileBytes == null) {
				Log.e(TAG, "Failed to read photo file for upload: ${photo.path}")
				return@withContext null
			}

			val uploadSuccess = uploadToWorker(
				fileBytes,
				photo.filename,
				authResponse.upload_jwt,
				signatureData.signature,
				authResponse.worker_url,
				photo.id,
				photo.anonymizationOverride
			)

			return@withContext if (uploadSuccess) authResponse.photo_id else null

		} catch (e: DuplicateFileException) {
			// Let this propagate - it's already handled in requestUploadAuthorization
			// and the database is already updated to "completed"
			throw e
		} catch (e: WorkerBusyException) {
			// Let this propagate - the drain loop aborts the whole pass on it
			throw e
		} catch (e: CancellationException) {
			// Worker stopped mid-upload — not an upload failure, let the
			// drain loop restore the photo's status and stop.
			throw e
		} catch (e: java.net.ConnectException) {
			Log.w(TAG, "🌐 Connection failed for ${photo.filename}: Server unreachable (${e.message})")
			return@withContext null
		} catch (e: java.net.SocketTimeoutException) {
			Log.w(TAG, "⏱️ Upload timeout for ${photo.filename}: ${e.message}")
			return@withContext null
		} catch (e: java.net.UnknownHostException) {
			Log.w(TAG, "🔍 DNS lookup failed for ${photo.filename}: ${e.message}")
			return@withContext null
		} catch (e: IOException) {
			Log.w(TAG, "📡 Network I/O error for ${photo.filename}: ${e.message}")
			return@withContext null
		} catch (e: Exception) {
			Log.e(TAG, "💥 Unexpected error in secure upload: ${photo.filename}", e)
			return@withContext null
		}
	}


	/**
	 * Request upload authorization from API server using PhotoEntity data
	 */
	private suspend fun requestUploadAuthorization(photo: PhotoEntity): UploadAuthorizationResponse {
		val serverUrl = getServerUrl() ?: throw Exception("Server URL not configured")
		val contentType = PhotoUtils.getContentType(photo.filename)

		// Convert timestamp to ISO format for captured_at
		val capturedAt = PhotoUtils.formatTimestampToIso(photo.capturedAt)

		// Get client key ID for authorization
		val keyInfo = clientCrypto.getPublicKeyInfo()
			?: throw Exception("Failed to get client key info - ensure crypto keys are available")

		val license = prefs.getString("auto_upload_license", null)
		if (license == null) {
			Log.d(TAG, "No upload license configured, skipping upload")
			throw Exception("No upload license configured")
		}

		try {
			return uploadProtocol.requestUploadAuthorization(
				serverUrl = serverUrl,
				job = UploadJobData(
					filename = photo.filename,
					fileSize = photo.fileSize,
					contentType = contentType,
					fileMd5 = photo.fileHash,
					version = photo.version,
					latitude = photo.latitude,
					longitude = photo.longitude,
					altitude = photo.altitude,
					bearing = photo.bearing,
					capturedAtIso = capturedAt,
				),
				clientKeyId = keyInfo.keyId,
				license = license,
			)
		} catch (e: DuplicateFileException) {
			// Mark the local photo as completed since it already exists on the server
			photoDao.updateUploadStatus(photo.id, "completed", System.currentTimeMillis())
			throw e
		}
	}

	/**
	 * Generate client signature for upload using authorization timestamp
	 */
	private fun generateClientSignature(photoId: String, filename: String, authTimestamp: Long): SignatureData? {
		return clientCrypto.signUploadData(photoId, filename, authTimestamp)
	}

	/**
	 * Upload file to worker with JWT and client signature
	 * @param anonymizationOverride JSON string controlling anonymization:
	 *   - null: auto-detect faces/plates (default)
	 *   - "[]": skip anonymization
	 *   - "[{...}]": manual blur rectangles
	 */
	private suspend fun uploadToWorker(
		fileBytes: ByteArray,
		filename: String,
		uploadJwt: String,
		signature: String,
		workerUrl: String,
		photoId: String,
		anonymizationOverride: String? = null
	): Boolean = uploadProtocol.uploadToWorker(
		fileBytes = fileBytes,
		filename = filename,
		contentType = PhotoUtils.getContentType(filename),
		uploadJwt = uploadJwt,
		signature = signature,
		workerUrl = workerUrl,
		anonymizationOverride = anonymizationOverride,
		heartbeat = {
			try {
				val database = PhotoDatabase.getDatabase(context)
				database.photoDao().updateUploadHeartbeat(photoId, System.currentTimeMillis())
				Log.v(TAG, "Updated upload heartbeat for $filename")
			} catch (e: Exception) {
				Log.w(TAG, "Failed to update heartbeat for $filename: ${e.message}")
			}
		},
	)


	private fun getServerUrl(): String? {
		return prefs.getString(PREF_SERVER_URL, null)
	}



    private fun getPhotoDirectories(): List<File> {
        val directories = mutableListOf<File>()

        // Get external storage path
        //val externalStorage = System.getenv("EXTERNAL_STORAGE") ?: "/storage/emulated/0"
        val externalStorage = "/storage/emulated/0"
        val picturesDir = File(externalStorage, "Pictures")

        // Add Hillview directories in Pictures (where photos are actually saved)
        directories.add(File(picturesDir, "Hillview"))    // /storage/emulated/0/Pictures/Hillview
        //directories.add(File(picturesDir, ".Hillview"))   // /storage/emulated/0/Pictures/.Hillview (hidden)

        Log.d(TAG, "Scanning photo directories: ${directories.map { it.path }}")
        return directories
    }


    private suspend fun validatePhotoForUpload(photo: PhotoEntity): Boolean {
        // Check if file still exists (works for both file paths and content:// URIs)
        if (!PhotoUtils.pathExists(context, photo.path)) {
            Log.w(TAG, "Photo file no longer exists: ${photo.path}, marking as failed")
            photoDao.updateUploadFailure(
                photo.id,
                "failed",
                photo.retryCount + 1,
                System.currentTimeMillis(),
                "File no longer exists"
            )
            return false
        }

        // Validate MD5 hash
        if (photo.fileHash.isEmpty() || photo.fileHash.length != 32 || !photo.fileHash.matches(Regex("[a-fA-F0-9]{32}"))) {
            Log.w(TAG, "Invalid MD5 hash for ${photo.filename}: '${photo.fileHash}' (length: ${photo.fileHash.length})")
            photoDao.updateUploadFailure(
                photo.id,
                "failed",
                photo.retryCount + 1,
                System.currentTimeMillis(),
                "Invalid MD5 hash: ${photo.fileHash}"
            )
            return false
        }

        return true
    }

    /**
     * Metered = mobile data (or wifi the user flagged as metered / a metered
     * VPN). The drain loop's per-photo wifi-only check — see the comment
     * there for why the WorkManager constraint alone is not enough.
     */
    private fun isActiveNetworkMetered(): Boolean {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return cm.isActiveNetworkMetered
    }

    /**
     * Whether a candidate photo may be uploaded right now. The single source
     * for the backoff rule, shared by the drain loop's skip and the progress
     * count's denominator so they can't drift. Pure — no DB writes / file I/O
     * (unlike validatePhotoForUpload).
     */
    private fun isEligibleNow(photo: PhotoEntity, triggerSource: String, now: Long): Boolean {
        if (photo.uploadStatus == "failed" && triggerSource != "retry_button") {
            if (now - photo.lastUploadAttempt < calculateBackoffTime(photo.retryCount)) return false
        }
        return true
    }

    private fun calculateBackoffTime(retryCount: Int): Long {
        // Exponential backoff: 1min, 2min, 4min, 8min, 16min, 32min, 1hr, 2hr, 4hr, 8hr, 16hr, 1.3days, 2.6days, 5.2days, 7days (max)
        val baseDelay = 60_000L // 1 minute
        val maxDelay = 7 * 24 * 60 * 60 * 1000L // 7 days in milliseconds
        val exponentialDelay = baseDelay * (1L shl retryCount)
        return minOf(exponentialDelay, maxDelay)
    }

    /**
     * Sync processing status for photos in "processing" state.
     * Sends batch request to POST /api/photos/status and updates local DB.
     */
    internal suspend fun syncProcessingPhotosStatus() = withContext(Dispatchers.IO) {
        val processingPhotos = photoDao.getProcessingPhotos()

        if (processingPhotos.isEmpty()) {
            Log.d(TAG, "No processing photos to sync")
            return@withContext
        }

        Log.d(TAG, "Syncing status for ${processingPhotos.size} processing photos")

        // Build map of serverPhotoId -> local photo for quick lookup (filter nulls)
        val photosByServerId = processingPhotos.filter { it.serverPhotoId != null }.associateBy { it.serverPhotoId!! }
        val serverPhotoIds = processingPhotos.mapNotNull { it.serverPhotoId }

        // Batch query server for statuses
        val serverStatuses = queryPhotoStatuses(serverPhotoIds)
        if (serverStatuses == null) {
            Log.w(TAG, "Failed to query photo statuses")
            return@withContext
        }

        // Update local DB
        updatePhotosFromServerStatuses(serverStatuses, photosByServerId)
    }

    /**
     * Query server for photo statuses in batch.
     * Handles auth token internally.
     */
    private suspend fun queryPhotoStatuses(photoIds: List<String>): List<ServerPhotoStatus>? {
        val serverUrl = getServerUrl()
        if (serverUrl == null) {
            Log.w(TAG, "Server URL not configured")
            return null
        }

        val authToken = authManager.getValidToken()
        if (authToken == null) {
            Log.w(TAG, "No valid auth token")
            return null
        }

        val json = JSONObject().apply {
            put("photo_ids", org.json.JSONArray(photoIds))
        }

        val request = Request.Builder()
            .url("$serverUrl/photos/status")
            .addHeader("Authorization", "Bearer $authToken")
            .post(json.toString().toRequestBody("application/json".toMediaType()))
            .build()

        return try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    Log.w(TAG, "Photo status query failed: ${response.code}")
                    return null
                }

                val responseJson = JSONObject(response.body!!.string())
                val photosArray = responseJson.getJSONArray("photos")
                val statuses = mutableListOf<ServerPhotoStatus>()

                for (i in 0 until photosArray.length()) {
                    val photoJson = photosArray.getJSONObject(i)
                    statuses.add(ServerPhotoStatus(
                        id = photoJson.getString("id"),
                        processingStatus = photoJson.optString("processing_status", ""),
                        error = if (photoJson.isNull("error")) null else photoJson.optString("error"),
                        deleted = photoJson.optBoolean("deleted", false)
                    ))
                }

                Log.d(TAG, "Got ${statuses.size} photo statuses from server")
                statuses
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error querying photo statuses: ${e.message}")
            null
        }
    }

    /**
     * Update local photos based on server statuses.
     */
    private fun updatePhotosFromServerStatuses(
        serverStatuses: List<ServerPhotoStatus>,
        photosByServerId: Map<String, PhotoEntity>
    ) {
        for (status in serverStatuses) {
            val localPhoto = photosByServerId[status.id] ?: continue

            // Check deleted flag first
            if (status.deleted) {
                Log.i(TAG, "🗑️ Photo ${localPhoto.filename} deleted on server")
                photoDao.updateDeleted(localPhoto.id, true)
                continue
            }

            when (status.processingStatus) {
                "completed" -> {
                    Log.i(TAG, "✅ Photo ${localPhoto.filename} completed on server")
                    photoDao.updateUploadStatus(localPhoto.id, "completed", System.currentTimeMillis())
                }
                "error" -> {
                    Log.w(TAG, "❌ Photo ${localPhoto.filename} failed on server: ${status.error}")
                    photoDao.updateUploadFailure(
                        localPhoto.id,
                        "failed",
                        localPhoto.retryCount + 1,
                        System.currentTimeMillis(),
                        status.error ?: "Server processing error"
                    )
                }
                "authorized" -> {
                    Log.d(TAG, "⏳ Photo ${localPhoto.filename} still just authorized.")
                }
            }
        }
    }

    /**
     * Update local photo statuses from frontend-provided data.
     * Called by Tauri command when "my photos" page fetches server data.
     * @return Number of photos updated
     */
    fun updatePhotoStatusesFromFrontend(statuses: List<ServerPhotoStatus>): Int {
        val processingPhotos = photoDao.getProcessingPhotos()
        val photosByServerId = processingPhotos.filter { it.serverPhotoId != null }.associateBy { it.serverPhotoId!! }

        var updatedCount = 0
        for (status in statuses) {
            if (photosByServerId.containsKey(status.id)) {
                updatedCount++
            }
        }

        updatePhotosFromServerStatuses(statuses, photosByServerId)
        Log.d(TAG, "Updated $updatedCount photos from frontend")
        return updatedCount
    }

    data class ServerPhotoStatus(
        val id: String,
        val processingStatus: String,
        val error: String?,
        val deleted: Boolean = false
    )

    /**
     * Handle get_processing_photo_ids cmd from frontend.
     * Returns list of serverPhotoIds for photos in "processing" state.
     */
    fun handleGetProcessingPhotoIds(invoke: Invoke) {
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
    fun handleCreateEdit(invoke: Invoke, params: JSObject) {
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

                val editEntity = EditEntity(
                    photoId = photoId,
                    actionJson = actionJson.toString(),
                    createdAt = System.currentTimeMillis()
                )

                val editId = editDao.insertEdit(editEntity)
                Log.d(TAG, "Created edit $editId for photo $photoId: $actionJson")

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
    fun handleCheckPhotoFileExists(invoke: Invoke, params: JSObject) {
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
    fun handleGetPhotoIdByServerPhotoId(invoke: Invoke, params: JSObject) {
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
    fun handleGetPhotoAnonymizationState(invoke: Invoke, params: JSObject) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val photoId = params.getString("photo_id")

                val photo = photoDao.getPhotoById(photoId)

                if (photo == null) {
                    val error = JSObject()
                    error.put("success", false)
                    error.put("error", "Photo not found in database")
                    invoke.resolve(error)
                    return@launch
                }

                // Start with the current stored value
                var currentOverride: String? = photo.anonymizationOverride

                // Apply any pending edits to compute effective state
                val pendingEdits = editDao.getPendingEditsForPhoto(photoId)
                for (edit in pendingEdits) {
                    try {
                        val actionJson = org.json.JSONObject(edit.actionJson)
                        val action = actionJson.optString("action")
                        if (action == "set_anonymization_override") {
                            currentOverride = if (actionJson.isNull("value")) {
                                null
                            } else {
                                actionJson.getJSONArray("value").toString()
                            }
                        }
                    } catch (e: Exception) {
                        Log.w(TAG, "Error parsing edit action for state computation: ${e.message}")
                    }
                }

                // Determine state type
                val state = when {
                    currentOverride == null -> "auto"
                    currentOverride == "[]" -> "none"
                    else -> "custom"
                }

                val result = JSObject()
                result.put("success", true)
                result.put("state", state)
                if (currentOverride != null) {
                    result.put("value", currentOverride)
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
    fun handleUpdatePhotoStatuses(invoke: Invoke, params: JSObject) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val statusesArray = params.getJSONArray("statuses")
                val statuses = mutableListOf<ServerPhotoStatus>()

                for (i in 0 until statusesArray.length()) {
                    val obj = statusesArray.getJSONObject(i)
                    statuses.add(ServerPhotoStatus(
                        id = obj.getString("id"),
                        processingStatus = obj.optString("processing_status", ""),
                        error = if (obj.isNull("error")) null else obj.optString("error")
                    ))
                }

                val updatedCount = updatePhotoStatusesFromFrontend(statuses)

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

}

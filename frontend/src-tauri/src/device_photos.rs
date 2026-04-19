#[cfg(all(target_os = "android", debug_assertions))]
use crate::photo_exif::verify_exif_in_saved_file;
#[cfg(target_os = "android")]
use crate::photo_exif::{create_exif_segment_structured, validate_photo_metadata};
use crate::types::PhotoMetadata;
#[cfg(target_os = "android")]
use img_parts::ImageEXIF;
use log::info;
#[cfg(target_os = "android")]
use log::warn;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;
use std::sync::OnceLock;
use std::time::Instant;
use tauri::command;
#[cfg(target_os = "android")]
use tauri_plugin_hillview::HillviewExt;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DevicePhotoMetadata {
	pub id: String,
	pub filename: String,
	pub path: String,
	pub latitude: f64,
	pub longitude: f64,
	pub altitude: Option<f64>,
	pub bearing: Option<f64>,
	pub captured_at: i64,
	pub accuracy: f64,
	pub width: u32,
	pub height: u32,
	pub file_size: u64,
	pub created_at: Option<i64>,
}

// Memory safety constants
const MAX_CHUNK_AGE_SECS: u64 = 300; // 5 minute TTL for chunks
const MAX_SINGLE_PHOTO_SIZE_MB: usize = 100; // 100 MB max per photo
const MAX_IMAGE_DIMENSION: u32 = 10000; // Max 10000x10000 pixels

/// Photo chunk with creation timestamp for TTL management
struct ChunkedPhoto {
	data: Vec<u8>,
	created_at: Instant,
}

// Global storage for photo chunks with TTL
static PHOTO_CHUNKS: OnceLock<Mutex<HashMap<String, ChunkedPhoto>>> = OnceLock::new();

/// Clean up stale chunks that have exceeded the TTL
fn cleanup_stale_chunks(chunks: &mut HashMap<String, ChunkedPhoto>) {
	let now = Instant::now();
	let stale_keys: Vec<String> = chunks
		.iter()
		.filter(|(_, chunk)| now.duration_since(chunk.created_at).as_secs() > MAX_CHUNK_AGE_SECS)
		.map(|(key, _)| key.clone())
		.collect();

	for key in stale_keys {
		if let Some(removed) = chunks.remove(&key) {
			log::warn!(
				"🢄⚠️ Removed stale photo chunk: {} ({} bytes, age: {}s)",
				key,
				removed.data.len(),
				now.duration_since(removed.created_at).as_secs()
			);
		}
	}
}

/// Validate image data before processing
/// Returns (width, height) on success, error message on failure
fn validate_image_data(data: &[u8]) -> Result<(u32, u32), String> {
	// Check size limit
	let size_mb = data.len() / (1024 * 1024);
	if size_mb > MAX_SINGLE_PHOTO_SIZE_MB {
		return Err(format!(
			"Image too large: {} MB (max {} MB)",
			size_mb, MAX_SINGLE_PHOTO_SIZE_MB
		));
	}

	// Use imagesize crate for efficient dimension extraction without loading full image
	match imagesize::blob_size(data) {
		Ok(size) => {
			let width = size.width as u32;
			let height = size.height as u32;

			if width > MAX_IMAGE_DIMENSION || height > MAX_IMAGE_DIMENSION {
				return Err(format!(
					"Image dimensions too large: {}x{} (max {}x{})",
					width, height, MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION
				));
			}

			Ok((width, height))
		}
		Err(e) => Err(format!("Failed to determine image dimensions: {:?}", e)),
	}
}

/// Save photo to storage. Tries all methods in order based on preference.
/// Returns the path (file path or content:// URI).
#[cfg(target_os = "android")]
fn save_to_pictures_directory(
	app_handle: &tauri::AppHandle,
	filename: &str,
	image_data: &[u8],
	hide_from_gallery: bool,
	preferred_storage: &str,
) -> Result<String, String> {
	let folder_name = if hide_from_gallery {
		".Hillview"
	} else {
		"Hillview"
	};

	// Public folder: /storage/emulated/0/DCIM/Hillview (visible in gallery, persists after uninstall)
	let public_pictures_dir = "/storage/emulated/0/DCIM";
	let public_pictures_path = std::path::Path::new(public_pictures_dir).join(folder_name);

	// Private folder: /storage/emulated/0/Android/data/{package}/files/Pictures (app-private, deleted on uninstall)
	let private_pictures_dir = format!(
		"/storage/emulated/0/Android/data/{}/files/Pictures",
		env!("ANDROID_PACKAGE_NAME")
	);
	let private_pictures_path = std::path::Path::new(&private_pictures_dir).join(folder_name);

	let try_public_folder = || -> Result<String, String> {
		info!("🢄📁 Trying public folder: {:?}", public_pictures_path);
		match save_to_directory(
			&public_pictures_path,
			filename,
			image_data,
			hide_from_gallery,
		) {
			Ok(photo_path) => {
				info!("🢄✅ Photo saved to public folder: {:?}", photo_path);
				Ok(photo_path.to_string_lossy().to_string())
			}
			Err(e) => Err(format!("Public folder failed: {}", e)),
		}
	};

	let try_private_folder = || -> Result<String, String> {
		info!("🢄📁 Trying private folder: {:?}", private_pictures_path);
		match save_to_directory(
			&private_pictures_path,
			filename,
			image_data,
			hide_from_gallery,
		) {
			Ok(photo_path) => {
				info!("🢄✅ Photo saved to private folder: {:?}", photo_path);
				Ok(photo_path.to_string_lossy().to_string())
			}
			Err(e) => Err(format!("Private folder failed: {}", e)),
		}
	};

	let try_mediastore = || -> Result<String, String> {
		info!("🢄📁 Trying MediaStore API");
		let response = app_handle
			.hillview()
			.save_photo_to_media_store(filename.to_string(), image_data.to_vec(), hide_from_gallery)
			.map_err(|e| format!("MediaStore plugin error: {}", e))?;

		if response.success {
			let path = response
				.path
				.ok_or_else(|| "MediaStore returned success but no path/URI".to_string())?;
			info!("🢄✅ Photo saved via MediaStore: {}", path);
			Ok(path)
		} else {
			Err(response
				.error
				.unwrap_or_else(|| "Unknown MediaStore error".to_string()))
		}
	};

	// Define the order of methods to try based on preferred_storage
	let methods: Vec<(&str, Box<dyn Fn() -> Result<String, String>>)> = match preferred_storage {
		"public_folder" => vec![
			(
				"public_folder",
				Box::new(try_public_folder) as Box<dyn Fn() -> Result<String, String>>,
			),
			("private_folder", Box::new(try_private_folder)),
			("mediastore_api", Box::new(try_mediastore)),
		],
		"private_folder" => vec![
			(
				"private_folder",
				Box::new(try_private_folder) as Box<dyn Fn() -> Result<String, String>>,
			),
			("public_folder", Box::new(try_public_folder)),
			("mediastore_api", Box::new(try_mediastore)),
		],
		"mediastore_api" => vec![
			(
				"mediastore_api",
				Box::new(try_mediastore) as Box<dyn Fn() -> Result<String, String>>,
			),
			("public_folder", Box::new(try_public_folder)),
			("private_folder", Box::new(try_private_folder)),
		],
		_ => vec![
			(
				"public_folder",
				Box::new(try_public_folder) as Box<dyn Fn() -> Result<String, String>>,
			),
			("private_folder", Box::new(try_private_folder)),
			("mediastore_api", Box::new(try_mediastore)),
		],
	};

	let mut last_error = String::new();
	for (name, method) in methods {
		match method() {
			Ok(path) => return Ok(path),
			Err(e) => {
				warn!("🢄⚠️ {} failed: {}", name, e);
				last_error = e;
			}
		}
	}

	Err(format!(
		"All storage methods failed. Last error: {}",
		last_error
	))
}

fn save_to_directory(
	pictures_path: &std::path::Path,
	filename: &str,
	image_data: &[u8],
	hide_from_gallery: bool,
) -> Result<std::path::PathBuf, std::io::Error> {
	#[cfg(unix)]
	use std::os::unix::fs::PermissionsExt;

	info!("🢄create_dir_all: {:?}", pictures_path);
	std::fs::create_dir_all(&pictures_path)?;

	// Create .nomedia file if hiding from gallery
	if hide_from_gallery {
		let nomedia_file = pictures_path.join(".nomedia");
		let _ = std::fs::write(nomedia_file, ""); // Empty file signals to skip this folder
	}

	// Save the file
	let photo_path = pictures_path.join(filename);
	info!("🢄Saving photo to: {:?}", photo_path);
	std::fs::write(&photo_path, image_data)?;

	info!(
		"🢄Saved photo to directory: {:?} (hidden: {})",
		photo_path, hide_from_gallery
	);

	// Set readable permissions for other apps on Unix systems
	#[cfg(unix)]
	{
		let mut perms = std::fs::metadata(&photo_path)?.permissions();
		perms.set_mode(0o644); // rw-r--r--
		std::fs::set_permissions(&photo_path, perms)?;
	}

	// Verify save by reading the file back
	let verified_size = std::fs::File::open(&photo_path)?.metadata()?.len();
	if verified_size != image_data.len() as u64 {
		return Err(std::io::Error::new(
			std::io::ErrorKind::Other,
			format!(
				"Verification failed: wrote {} bytes but file has {} bytes",
				image_data.len(),
				verified_size
			),
		));
	}
	info!("🢄✓ Verified save: {} bytes", verified_size);

	Ok(photo_path)
}

/// Store photo chunk using base64 encoding (Android doesn't support raw binary IPC)
#[command(rename_all = "snake_case")]
pub fn store_photo_chunk(
	photo_id: String,
	chunk_base64: String,
	is_first_chunk: bool,
) -> Result<(), String> {
	use base64::{Engine as _, engine::general_purpose::STANDARD};

	// Decode base64 to bytes
	let chunk = STANDARD.decode(&chunk_base64)
		.map_err(|e| format!("Failed to decode base64: {}", e))?;

	info!(
		"🢄📦 store_photo_chunk: photo_id={}, is_first={}, chunk_size={}",
		photo_id, is_first_chunk, chunk.len()
	);

	let chunks_mutex = PHOTO_CHUNKS.get_or_init(|| Mutex::new(HashMap::new()));
	let mut chunks = chunks_mutex
		.lock()
		.map_err(|e| format!("Failed to lock chunks: {}", e))?;

	// Clean up stale chunks on each new chunk operation
	cleanup_stale_chunks(&mut chunks);

	if is_first_chunk {
		// Initialize new photo with first chunk and timestamp
		chunks.insert(
			photo_id,
			ChunkedPhoto {
				data: chunk,
				created_at: Instant::now(),
			},
		);
	} else {
		// Append to existing photo
		if let Some(existing) = chunks.get_mut(&photo_id) {
			// Check if appending would exceed size limit
			let new_size = existing.data.len() + chunk.len();
			if new_size > MAX_SINGLE_PHOTO_SIZE_MB * 1024 * 1024 {
				return Err(format!(
					"Photo {} would exceed size limit: {} MB (max {} MB)",
					photo_id,
					new_size / (1024 * 1024),
					MAX_SINGLE_PHOTO_SIZE_MB
				));
			}
			existing.data.extend(chunk);
		} else {
			return Err(format!("Photo ID {} not found for chunk append", photo_id));
		}
	}

	Ok(())
}

#[command(rename_all = "snake_case")]
#[allow(unused_variables)]
pub async fn save_photo_with_metadata(
	app_handle: tauri::AppHandle,
	photo_id: String,
	metadata: PhotoMetadata,
	filename: String,
	hide_from_gallery: bool,
	preferred_storage: Option<String>,
) -> Result<crate::device_photos::DevicePhotoMetadata, String> {
	// Step 1: Get stored image data
	let image_data = {
		let chunks_mutex = PHOTO_CHUNKS.get_or_init(|| Mutex::new(HashMap::new()));
		let mut chunks = chunks_mutex
			.lock()
			.map_err(|e| format!("Failed to lock chunks: {}", e))?;
		let chunked_photo = chunks
			.remove(&photo_id)
			.ok_or_else(|| format!("Photo data not found for ID: {}", photo_id))?;
		chunked_photo.data
	};

	info!(
		"🢄Retrieved {} bytes for photo ID: {}",
		image_data.len(),
		photo_id
	);

	// Call the internal function with the image data
	#[cfg(target_os = "android")]
	{
		let storage = preferred_storage.unwrap_or_else(|| "public_folder".to_string());
		save_photo_from_bytes(
			app_handle,
			photo_id,
			metadata,
			image_data,
			filename,
			hide_from_gallery,
			storage,
		)
		.await
	}

	#[cfg(not(target_os = "android"))]
	{
		Err("Photo saving not implemented for non-Android platforms".to_string())
	}
}

#[cfg(target_os = "android")]
async fn save_photo_from_bytes(
	app_handle: tauri::AppHandle,
	photo_id: String,
	mut metadata: PhotoMetadata,
	image_data: Vec<u8>,
	filename: String,
	hide_from_gallery: bool,
	preferred_storage: String,
) -> Result<crate::device_photos::DevicePhotoMetadata, String> {
	// Determine the final bearing before spawning the blocking task
	metadata.bearing = determine_final_bearing(&app_handle, &metadata).await;

	// Do everything in one background thread
	tokio::task::spawn_blocking(
		move || -> Result<crate::device_photos::DevicePhotoMetadata, String> {
			info!(
				"🢄Processing {} bytes for photo ID: {}",
				image_data.len(),
				photo_id
			);

			// Validate image data before processing (efficient - doesn't load full image)
			let (width, height) = validate_image_data(&image_data)?;

			// Process EXIF data synchronously and get dimensions
			let (processed_data, validated_metadata) = {
				let validated_metadata = validate_photo_metadata(metadata.clone());

				// Parse the JPEG
				let mut jpeg = img_parts::jpeg::Jpeg::from_bytes(image_data.clone().into())
					.map_err(|e| format!("Failed to parse JPEG: {:?}", e))?;

				// Create EXIF segment - use structured version
				let exif_segment = create_exif_segment_structured(&validated_metadata);

				// Set the EXIF data
				jpeg.set_exif(Some(exif_segment.into()));

				// Convert back to bytes
				let mut output = Vec::new();
				let mut output_cursor = std::io::Cursor::new(&mut output);
				jpeg.encoder()
					.write_to(&mut output_cursor)
					.map_err(|e| format!("Failed to write JPEG: {:?}", e))?;

				(output, validated_metadata)
			};

			// Save the photo file (blocking I/O or MediaStore)
			let file_path = save_to_pictures_directory(
				&app_handle,
				&filename,
				&processed_data,
				hide_from_gallery,
				&preferred_storage,
			)?;

			// Verify EXIF data in debug builds (only for file paths, not content:// URIs)
			#[cfg(debug_assertions)]
			{
				if !file_path.starts_with("content://") {
					info!("🔍 Verifying EXIF data in saved photo: {}", file_path);
					let file_path_clone = std::path::PathBuf::from(&file_path);
					let metadata_clone = validated_metadata.clone();
					tokio::spawn(async move {
						verify_exif_in_saved_file(&file_path_clone, &metadata_clone).await;
					});
				}
			}

			// Get file size - we already know it from processed_data
			let file_size = processed_data.len() as u64;

			// Calculate hash from processed data (CPU intensive)
			let hash_bytes = md5::compute(&processed_data);
			let file_hash = format!("{:x}", hash_bytes);

			// Add to database (still in background thread)
			{
				use tauri_plugin_hillview::HillviewExt;

				// Send to Android database - use our photo_id
				let plugin_photo = tauri_plugin_hillview::shared_types::DevicePhotoMetadata {
					id: photo_id.clone(), // Use the photo_id from frontend
					filename: filename.clone(),
					path: file_path.clone(),
					metadata: tauri_plugin_hillview::shared_types::PhotoMetadata {
						latitude: validated_metadata.latitude,
						longitude: validated_metadata.longitude,
						altitude: validated_metadata.altitude,
						bearing: validated_metadata.bearing,
						captured_at: validated_metadata.captured_at,
						accuracy: validated_metadata.accuracy,
						location_source: validated_metadata.location_source.clone(),
						bearing_source: validated_metadata.bearing_source.clone(),
					},
					width,
					height,
					file_size,
					file_hash: Some(file_hash.clone()),
					created_at: None, // Let the plugin set the created_at timestamp
				};

				let final_photo_id = match app_handle
					.hillview()
					.add_photo_to_database(plugin_photo.clone())
				{
					Ok(response) => {
						if response.success {
							let id = response.photo_id.unwrap_or_else(|| String::from("unknown"));
							info!("📱 Photo saved to Android database with ID: {}", id);
							id
						} else {
							return Err(format!(
								"Failed to save photo to Android database: {:?}",
								response.error
							));
						}
					}
					Err(e) => {
						return Err(format!("Error saving photo to Android database: {}", e));
					}
				};

				// Create the return value with the ID from Kotlin
				let device_photo = crate::device_photos::DevicePhotoMetadata {
					id: final_photo_id,
					filename,
					path: file_path,
					latitude: validated_metadata.latitude,
					longitude: validated_metadata.longitude,
					altitude: validated_metadata.altitude,
					bearing: validated_metadata.bearing,
					captured_at: validated_metadata.captured_at,
					accuracy: validated_metadata.accuracy,
					width,
					height,
					file_size,
					created_at: plugin_photo.created_at,
				};

				// Trigger immediate upload worker to process the new photo. The naming is wrong at this point.
				match app_handle.hillview().retry_failed_uploads() {
					Ok(_) => {
					}
					Err(e) => {
						info!("📤[UPLOAD_TRIGGER] Failed to trigger upload worker: {}", e);
					}
				}

				Ok(device_photo)
			}

			#[cfg(not(target_os = "android"))]
			{
				Err("Photo saving not implemented for non-Android platforms".to_string())
			}
		},
	)
	.await
	.map_err(|e| format!("Background task failed: {}", e))?
}

#[cfg(target_os = "android")]
async fn determine_final_bearing(
	app_handle: &tauri::AppHandle,
	metadata: &PhotoMetadata,
) -> Option<f64> {
	// Check if we should use database bearing instead of frontend bearing
	let final_bearing = if is_sensor_bearing_source(&metadata.bearing_source) {
		info!("🢄📡 Bearing source '{}' indicates sensor data, looking up database bearing for timestamp {}",
			metadata.bearing_source, metadata.captured_at);

		match app_handle
			.hillview()
			.get_bearing_for_timestamp(metadata.captured_at * 1000)
		{
			// Convert to milliseconds
			Ok(response) => {
				info!("🢄📡 Database bearing lookup response: success={}, found={:?}, true_heading={:?}",
					response.success, response.found, response.true_heading);
				if response.success {
					if let Some(found) = response.found {
						if found {
							if let Some(true_heading) = response.true_heading {
								info!("🢄📡 Found database bearing: {}° (replacing frontend bearing: {}°)",
									true_heading, metadata.bearing.unwrap_or(-1.0));
								Some(true_heading)
							} else {
								info!("🢄📡 Database bearing found but no trueHeading, using frontend bearing");
								metadata.bearing
							}
						} else {
							info!("🢄📡 No database bearing found for timestamp, using frontend bearing");
							metadata.bearing
						}
					} else {
						info!("🢄📡 Database bearing lookup returned success but no 'found' field, using frontend bearing");
						metadata.bearing
					}
				} else {
					info!("🢄📡 Database bearing lookup failed, using frontend bearing");
					metadata.bearing
				}
			}
			Err(e) => {
				info!(
					"🢄📡 Error looking up database bearing: {}, using frontend bearing",
					e
				);
				metadata.bearing
			}
		}
	} else {
		info!(
			"🢄📡 Bearing source '{}' has no Kotlin-side history, using frontend bearing",
			metadata.bearing_source
		);
		metadata.bearing
	};
	final_bearing
}

/// Helper function to determine if a bearing source is produced Kotlin-side
/// at high frequency — in that case the DB is the authoritative time-indexed
/// source and the frontend value is likely stale by the JS-bridge latency.
/// Sources we own: compass/sensor fusion (walking mode) and gps-kalman (car
/// mode, since the filter was ported to Kotlin).
#[cfg(any(target_os = "android", test))]
#[allow(dead_code)] // unused on non-android non-test builds
fn is_sensor_bearing_source(bearing_source: &str) -> bool {
	let source_lower = bearing_source.to_lowercase();

	source_lower.contains("sensor")
		|| source_lower.contains("compass")
		|| source_lower.contains("tauri")
		|| source_lower.contains("gyro")
		|| source_lower.contains("magnetometer")
		|| source_lower.contains("rotation")
		|| source_lower.contains("magnetic")
		|| source_lower.contains("enhanced")
		|| source_lower.contains("gps-kalman")
}

#[cfg(test)]
mod tests {
	use super::is_sensor_bearing_source;

	#[test]
	fn matches_kotlin_owned_sources() {
		assert!(is_sensor_bearing_source("tauri-compass-true"));
		assert!(is_sensor_bearing_source("enhanced-sensor"));
		assert!(is_sensor_bearing_source("magnetometer"));
		assert!(is_sensor_bearing_source("rotation-vector"));
		assert!(is_sensor_bearing_source("gyro-fusion"));
		assert!(is_sensor_bearing_source("gps-kalman"));
	}

	#[test]
	fn is_case_insensitive() {
		assert!(is_sensor_bearing_source("GPS-KALMAN"));
		assert!(is_sensor_bearing_source("Tauri-Compass"));
	}

	#[test]
	fn rejects_unrelated_sources() {
		assert!(!is_sensor_bearing_source("manual"));
		assert!(!is_sensor_bearing_source("photo"));
		assert!(!is_sensor_bearing_source("url"));
		assert!(!is_sensor_bearing_source("arrow_drag"));
		assert!(!is_sensor_bearing_source(""));
	}
}

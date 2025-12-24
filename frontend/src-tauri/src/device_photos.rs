use img_parts::ImageEXIF;
use log::{info, warn};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;
use std::sync::OnceLock;
use tauri::command;
use tauri_plugin_hillview::HillviewExt;
use crate::photo_exif::{create_exif_segment_structured, validate_photo_metadata};
#[cfg(debug_assertions)]
use crate::photo_exif::verify_exif_in_saved_file;
use crate::types::PhotoMetadata;

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

#[derive(Debug, Serialize)]
pub struct ProcessedPhoto {
	pub data: Vec<u8>,
	pub metadata: PhotoMetadata,
}


// Global storage for photo chunks
static PHOTO_CHUNKS: OnceLock<Mutex<HashMap<String, Vec<u8>>>> = OnceLock::new();


/// Save photo to storage. Tries direct file I/O first, falls back to MediaStore.
/// Returns the path (file path or content:// URI).
#[cfg(target_os = "android")]
fn save_to_pictures_directory(
	app_handle: &tauri::AppHandle,
	filename: &str,
	image_data: &[u8],
	hide_from_gallery: bool,
) -> Result<String, String> {
	let folder_name = if hide_from_gallery { ".Hillview" } else { "Hillview" };
	let public_pictures_dir = "/storage/emulated/0/DCIM";
	let public_pictures_path = std::path::Path::new(public_pictures_dir).join(folder_name);

	// Try direct file I/O first (works on some devices)
	match save_to_directory(&public_pictures_path, filename, image_data, hide_from_gallery) {
		Ok(photo_path) => {
			info!("🢄✅ Photo saved via direct I/O: {:?}", photo_path);
			Ok(photo_path.to_string_lossy().to_string())
		}
		Err(e) => {
			warn!("🢄⚠️ Direct I/O failed ({}), falling back to MediaStore...", e);

			// Fall back to MediaStore API
			let response = app_handle
				.hillview()
				.save_photo_to_media_store(filename.to_string(), image_data.to_vec(), hide_from_gallery)
				.map_err(|e| format!("MediaStore plugin error: {}", e))?;

			if response.success {
				let path = response.path.ok_or_else(|| "MediaStore returned success but no path/URI".to_string())?;
				info!("🢄✅ Photo saved via MediaStore: {}", path);
				Ok(path)
			} else {
				Err(response.error.unwrap_or_else(|| "Unknown MediaStore error".to_string()))
			}
		}
	}
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

	info!("🢄Saved photo to directory: {:?} (hidden: {})", photo_path, hide_from_gallery);

	// Set readable permissions for other apps on Unix systems
	#[cfg(unix)]
	{
		let mut perms = std::fs::metadata(&photo_path)?.permissions();
		perms.set_mode(0o644); // rw-r--r--
		std::fs::set_permissions(&photo_path, perms)?;
	}

	Ok(photo_path)
}


#[command(rename_all = "snake_case")]
pub fn store_photo_chunk(photo_id: String, chunk: Vec<u8>, is_first_chunk: bool) -> Result<(), String> {
	let chunks_mutex = PHOTO_CHUNKS.get_or_init(|| Mutex::new(HashMap::new()));
	let mut chunks = chunks_mutex.lock().map_err(|e| format!("Failed to lock chunks: {}", e))?;

	if is_first_chunk {
		// Initialize new photo with first chunk
		chunks.insert(photo_id, chunk);
	} else {
		// Append to existing photo
		if let Some(existing) = chunks.get_mut(&photo_id) {
			existing.extend(chunk);
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
) -> Result<crate::device_photos::DevicePhotoMetadata, String> {
	// Step 1: Get stored image data
	let image_data = {
		let chunks_mutex = PHOTO_CHUNKS.get_or_init(|| Mutex::new(HashMap::new()));
		let mut chunks = chunks_mutex.lock().map_err(|e| format!("Failed to lock chunks: {}", e))?;
		chunks.remove(&photo_id).ok_or_else(|| format!("Photo data not found for ID: {}", photo_id))?
	};

	info!("🢄Retrieved {} bytes for photo ID: {}", image_data.len(), photo_id);

	// Call the internal function with the image data
	#[cfg(target_os = "android")]
	{
		save_photo_from_bytes(app_handle, photo_id, metadata, image_data, filename, hide_from_gallery).await
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
) -> Result<crate::device_photos::DevicePhotoMetadata, String> {
	// Determine the final bearing before spawning the blocking task
	metadata.bearing = determine_final_bearing(&app_handle, &metadata).await;

	// Do everything in one background thread
	tokio::task::spawn_blocking(move || -> Result<crate::device_photos::DevicePhotoMetadata, String> {
		info!("🢄Processing {} bytes for photo ID: {}", image_data.len(), photo_id);

		// Process EXIF data synchronously and get dimensions
		let (processed_data, width, height, validated_metadata) = {
			let validated_metadata = validate_photo_metadata(metadata.clone());

			// Parse the JPEG
			let mut jpeg = img_parts::jpeg::Jpeg::from_bytes(image_data.clone().into())
				.map_err(|e| format!("Failed to parse JPEG: {:?}", e))?;

			// Get dimensions from the original image data using image crate
			let img = image::load_from_memory(&image_data)
				.map_err(|e| format!("Failed to load image from memory: {}", e))?;
			let (width, height) = (img.width(), img.height());

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

			(output, width, height, validated_metadata)
		};

		// Save the photo file (blocking I/O or MediaStore)
		let file_path = save_to_pictures_directory(&app_handle, &filename, &processed_data, hide_from_gallery)?;

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

			let final_photo_id = match app_handle.hillview().add_photo_to_database(plugin_photo.clone()) {
				Ok(response) => {
					if response.success {
						let id = response.photo_id.unwrap_or_else(|| String::from("unknown"));
						info!("📱 Photo saved to Android database with ID: {}", id);
						id
					} else {
						return Err(format!("Failed to save photo to Android database: {:?}", response.error));
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

			// Trigger immediate upload worker to process the new photo
			match app_handle.hillview().retry_failed_uploads() {
				Ok(_) => {
					info!(
						"📤[UPLOAD_TRIGGER] Upload worker triggered for new photo: {}",
						device_photo.filename
					);
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
	})
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

		match app_handle.hillview().get_bearing_for_timestamp(metadata.captured_at * 1000) { // Convert to milliseconds
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
				info!("🢄📡 Error looking up database bearing: {}, using frontend bearing", e);
				metadata.bearing
			}
		}
	} else {
		info!("🢄📡 Bearing source '{}' indicates manual input, using frontend bearing", metadata.bearing_source);
		metadata.bearing
	};
	final_bearing
}


/// Helper function to determine if a bearing source indicates sensor data
#[cfg(target_os = "android")]
fn is_sensor_bearing_source(bearing_source: &str) -> bool {
	let source_lower = bearing_source.to_lowercase();

	// Check for sensor-related keywords
	source_lower.contains("sensor") ||
	source_lower.contains("compass") ||
	source_lower.contains("tauri") ||
	source_lower.contains("gyro") ||
	source_lower.contains("magnetometer") ||
	source_lower.contains("rotation") ||
	source_lower.contains("magnetic") ||
	source_lower.contains("enhanced")
}


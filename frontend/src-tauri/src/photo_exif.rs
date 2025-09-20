use chrono;
use img_parts::{jpeg::Jpeg, ImageEXIF};
use log::info;
use serde::{Deserialize, Serialize};
use serde_json;
use std::io::Cursor;
use tauri::command;

#[derive(Debug, Serialize, Deserialize)]
struct ProvenanceData {
	location_source: String,
	bearing_source: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PhotoMetadata {
	pub latitude: f64,
	pub longitude: f64,
	pub altitude: Option<f64>,
	pub bearing: Option<f64>,
	pub timestamp: i64,
	pub accuracy: f64,
	pub location_source: String,
	pub bearing_source: String,
}

#[derive(Debug, Serialize)]
pub struct ProcessedPhoto {
	pub data: Vec<u8>,
	pub metadata: PhotoMetadata,
}

fn calculate_gps_entry_count(metadata: &PhotoMetadata) -> u16 {
	let mut count = 5u16; // VersionID, LatRef, Lat, LonRef, Lon
	if metadata.altitude.is_some() {
		count += 2; // AltRef, Alt
	}
	if metadata.bearing.is_some() {
		count += 4; // ImgDirectionRef, ImgDirection, DestBearingRef, DestBearing
	}
	count
}

fn calculate_gps_data_size(metadata: &PhotoMetadata) -> u32 {
	let mut size = 0u32;

	// GPS entries are always present: VersionID, LatRef, Lat, LonRef, Lon
	// Latitude and longitude rationals: 3 rationals * 8 bytes each = 24 bytes each
	size += 48; // lat (24) + lon (24)

	// Optional altitude: 1 rational = 8 bytes
	if metadata.altitude.is_some() {
		size += 8;
	}

	// Optional bearing: 2 rationals (ImgDirection + DestBearing) = 16 bytes
	if metadata.bearing.is_some() {
		size += 16;
	}

	size
}

fn create_exif_segment_simple(metadata: &PhotoMetadata) -> Vec<u8> {
	info!(
		"Creating EXIF for: lat={}, lon={}, alt={:?}, bearing={:?}",
		metadata.latitude, metadata.longitude, metadata.altitude, metadata.bearing
	);

	let mut exif_data = Vec::new();

	// Don't include "Exif\0\0" - img-parts adds it automatically
	let tiff_start = 0;

	// TIFF header (little-endian)
	exif_data.extend_from_slice(&[0x49, 0x49]); // II
	exif_data.extend_from_slice(&[0x2A, 0x00]); // 42
	exif_data.extend_from_slice(&[0x08, 0x00, 0x00, 0x00]); // IFD0 offset (8 from TIFF start)

	// IFD0 at offset 8 from TIFF - two entries: GPS IFD and UserComment
	exif_data.extend_from_slice(&[0x02, 0x00]); // 2 entries

	// GPS IFD Pointer (tag 0x8825)
	exif_data.extend_from_slice(&[0x25, 0x88]); // Tag 0x8825
	exif_data.extend_from_slice(&[0x04, 0x00]); // Type: LONG
	exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
	let gps_ifd_offset: u32 = 0x32; // GPS IFD offset from TIFF start (moved to make room)
	exif_data.extend_from_slice(&gps_ifd_offset.to_le_bytes());

	// Create JSON provenance data using proper serialization
	let provenance = ProvenanceData {
		location_source: metadata.location_source.clone(),
		bearing_source: metadata.bearing_source.clone(),
	};
	let provenance_json = serde_json::to_string(&provenance)
		.map_err(|e| format!("Failed to serialize provenance data: {}", e))
		.unwrap_or_else(|_| r#"{"location_source":"unknown","bearing_source":"unknown"}"#.to_string());

	// EXIF UserComment has 8-byte character code header + comment text
	let mut user_comment = b"ASCII\0\0\0".to_vec(); // Character code

	// Limit UserComment size to prevent EXIF issues (max 65535 bytes per EXIF spec)
	const MAX_COMMENT_SIZE: usize = 1000; // Conservative limit
	let comment_bytes = if provenance_json.len() > MAX_COMMENT_SIZE {
		info!("Warning: Provenance data too long ({}), truncating to {} bytes",
			  provenance_json.len(), MAX_COMMENT_SIZE);
		&provenance_json.as_bytes()[..MAX_COMMENT_SIZE]
	} else {
		provenance_json.as_bytes()
	};

	user_comment.extend_from_slice(comment_bytes);

	// UserComment (tag 0x9286)
	exif_data.extend_from_slice(&[0x86, 0x92]); // Tag 0x9286
	exif_data.extend_from_slice(&[0x07, 0x00]); // Type: UNDEFINED
	exif_data.extend_from_slice(&(user_comment.len() as u32).to_le_bytes()); // Count
	if user_comment.len() <= 4 {
		// Fits in the offset field
		let mut padded = user_comment.clone();
		padded.resize(4, 0);
		exif_data.extend_from_slice(&padded);
	} else {
		// Store offset to comment data - calculate dynamically
		let gps_data_size = calculate_gps_data_size(metadata);
		let gps_entry_count = calculate_gps_entry_count(metadata);
		let gps_ifd_size = 2 + (gps_entry_count as u32 * 12) + 4; // count + entries + next IFD
		let comment_offset = gps_ifd_offset + gps_ifd_size + gps_data_size;
		exif_data.extend_from_slice(&comment_offset.to_le_bytes());
	}

	// Next IFD offset (none)
	exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);

	// Pad to GPS IFD location
	while exif_data.len() < tiff_start + gps_ifd_offset as usize {
		exif_data.push(0x00);
	}

	// Count GPS entries
	let gps_entry_count = calculate_gps_entry_count(metadata);
	exif_data.extend_from_slice(&gps_entry_count.to_le_bytes());

	// GPS entries must be in ascending tag order

	// GPSVersionID (tag 0x0000) - required by some parsers
	exif_data.extend_from_slice(&[0x00, 0x00]); // Tag
	exif_data.extend_from_slice(&[0x01, 0x00]); // Type: BYTE
	exif_data.extend_from_slice(&[0x04, 0x00, 0x00, 0x00]); // Count: 4
	exif_data.extend_from_slice(&[0x02, 0x03, 0x00, 0x00]); // Version 2.3.0.0

	// GPSLatitudeRef (tag 0x0001)
	exif_data.extend_from_slice(&[0x01, 0x00]); // Tag
	exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
	exif_data.extend_from_slice(&[0x02, 0x00, 0x00, 0x00]); // Count: 2
	if metadata.latitude >= 0.0 {
		exif_data.extend_from_slice(b"N\0\0\0");
	} else {
		exif_data.extend_from_slice(b"S\0\0\0");
	}

	// GPSLatitude
	let lat_abs = metadata.latitude.abs();
	let lat_deg = lat_abs.floor() as u32;
	let lat_min = ((lat_abs - lat_deg as f64) * 60.0).floor() as u32;
	let lat_sec = ((lat_abs - lat_deg as f64 - lat_min as f64 / 60.0) * 3600.0 * 100.0) as u32;

	info!(
		"GPS Lat: {} = {}° {}' {}/100\"",
		lat_abs, lat_deg, lat_min, lat_sec
	);

	exif_data.extend_from_slice(&[0x02, 0x00]); // Tag
	exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
	exif_data.extend_from_slice(&[0x03, 0x00, 0x00, 0x00]); // Count: 3
														 // Calculate offset for latitude data (after all GPS IFD entries + next IFD pointer)
														 // Each entry is 12 bytes, plus 2 for count, plus 4 for next IFD = base GPS IFD size
	let gps_ifd_size = 2 + (gps_entry_count as u32 * 12) + 4;
	let lat_offset = gps_ifd_offset + gps_ifd_size;
	exif_data.extend_from_slice(&lat_offset.to_le_bytes());

	// GPSLongitudeRef
	exif_data.extend_from_slice(&[0x03, 0x00]); // Tag
	exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
	exif_data.extend_from_slice(&[0x02, 0x00, 0x00, 0x00]); // Count: 2
														 // Handle standard longitude (-180 to +180)
	if metadata.longitude >= 0.0 {
		exif_data.extend_from_slice(b"E\0\0\0");
	} else {
		exif_data.extend_from_slice(b"W\0\0\0");
	}

	// GPSLongitude
	// Use absolute value for longitude (ref indicates direction)
	let lon_proper = metadata.longitude.abs();
	let lon_deg = lon_proper.floor() as u32;
	let lon_min = ((lon_proper - lon_deg as f64) * 60.0).floor() as u32;
	let lon_sec = ((lon_proper - lon_deg as f64 - lon_min as f64 / 60.0) * 3600.0 * 100.0) as u32;

	info!(
		"GPS Lon: {} (proper: {}) = {}° {}' {}/100\"",
		metadata.longitude, lon_proper, lon_deg, lon_min, lon_sec
	);

	exif_data.extend_from_slice(&[0x04, 0x00]); // Tag
	exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
	exif_data.extend_from_slice(&[0x03, 0x00, 0x00, 0x00]); // Count: 3
	let lon_offset = lat_offset + 24; // After latitude data
	exif_data.extend_from_slice(&lon_offset.to_le_bytes());

	let mut next_offset = lon_offset + 24;

	// Optional altitude
	if metadata.altitude.is_some() {
		// GPSAltitudeRef
		exif_data.extend_from_slice(&[0x05, 0x00]); // Tag
		exif_data.extend_from_slice(&[0x01, 0x00]); // Type: BYTE
		exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
		exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]); // 0 = above sea level

		// GPSAltitude
		exif_data.extend_from_slice(&[0x06, 0x00]); // Tag
		exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
		exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
		exif_data.extend_from_slice(&next_offset.to_le_bytes());
		next_offset += 8;
	}

	// Optional bearing
	if metadata.bearing.is_some() {
		// GPSImgDirectionRef
		exif_data.extend_from_slice(&[0x10, 0x00]); // Tag 0x0010
		exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
		exif_data.extend_from_slice(&[0x02, 0x00, 0x00, 0x00]); // Count: 2
		exif_data.extend_from_slice(b"T\0\0\0"); // True North

		// GPSImgDirection
		exif_data.extend_from_slice(&[0x11, 0x00]); // Tag 0x0011
		exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
		exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
		exif_data.extend_from_slice(&next_offset.to_le_bytes());
		next_offset += 8;

		// GPSDestBearingRef
		exif_data.extend_from_slice(&[0x17, 0x00]); // Tag 0x0017
		exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
		exif_data.extend_from_slice(&[0x02, 0x00, 0x00, 0x00]); // Count: 2
		exif_data.extend_from_slice(b"T\0\0\0"); // True North

		// GPSDestBearing
		exif_data.extend_from_slice(&[0x18, 0x00]); // Tag 0x0018
		exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
		exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
		exif_data.extend_from_slice(&next_offset.to_le_bytes());
	}

	// Next IFD offset (none)
	exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);

	// Pad to latitude data offset
	while exif_data.len() < tiff_start + lat_offset as usize {
		exif_data.push(0x00);
	}

	// Latitude rationals (degrees, minutes, seconds)
	exif_data.extend_from_slice(&lat_deg.to_le_bytes());
	exif_data.extend_from_slice(&1u32.to_le_bytes());
	exif_data.extend_from_slice(&lat_min.to_le_bytes());
	exif_data.extend_from_slice(&1u32.to_le_bytes());
	exif_data.extend_from_slice(&lat_sec.to_le_bytes());
	exif_data.extend_from_slice(&100u32.to_le_bytes());

	// Longitude rationals
	exif_data.extend_from_slice(&lon_deg.to_le_bytes());
	exif_data.extend_from_slice(&1u32.to_le_bytes());
	exif_data.extend_from_slice(&lon_min.to_le_bytes());
	exif_data.extend_from_slice(&1u32.to_le_bytes());
	exif_data.extend_from_slice(&lon_sec.to_le_bytes());
	exif_data.extend_from_slice(&100u32.to_le_bytes());

	// Altitude rational
	if let Some(altitude) = metadata.altitude {
		let alt_num = (altitude.abs() * 1000.0) as u32;
		exif_data.extend_from_slice(&alt_num.to_le_bytes());
		exif_data.extend_from_slice(&1000u32.to_le_bytes());
	}

	// Bearing rationals (both ImgDirection and DestBearing)
	if let Some(bearing) = metadata.bearing {
		let bearing_num = (bearing * 100.0) as u32;
		// ImgDirection
		exif_data.extend_from_slice(&bearing_num.to_le_bytes());
		exif_data.extend_from_slice(&100u32.to_le_bytes());
		// DestBearing (same value)
		exif_data.extend_from_slice(&bearing_num.to_le_bytes());
		exif_data.extend_from_slice(&100u32.to_le_bytes());
	}

	// Add UserComment data if it was placed by offset
	if user_comment.len() > 4 {
		// Use same calculation as above
		let gps_data_size = calculate_gps_data_size(metadata);
		let gps_entry_count = calculate_gps_entry_count(metadata);
		let gps_ifd_size = 2 + (gps_entry_count as u32 * 12) + 4;
		let comment_offset = gps_ifd_offset + gps_ifd_size + gps_data_size;

		// Pad to comment offset
		while exif_data.len() < tiff_start + comment_offset as usize {
			exif_data.push(0x00);
		}
		// Write the UserComment data
		exif_data.extend_from_slice(&user_comment);
	}

	// Log final EXIF size and structure for debugging
	info!("🢄Created simple EXIF: {} bytes", exif_data.len());
	info!(
		"EXIF structure: TIFF at {}, IFD0 at {}, GPS IFD at {}, lat data at {}, lon data at {}",
		tiff_start,
		tiff_start + 8,
		tiff_start + gps_ifd_offset as usize,
		tiff_start + lat_offset as usize,
		tiff_start + lon_offset as usize
	);

	exif_data
}

#[command]
pub async fn embed_photo_metadata(
	image_data: Vec<u8>,
	metadata: PhotoMetadata,
) -> Result<ProcessedPhoto, String> {
	// Parse the JPEG
	let mut jpeg = Jpeg::from_bytes(image_data.clone().into())
		.map_err(|e| format!("Failed to parse JPEG: {:?}", e))?;

	// Create EXIF segment - use simple version for now
	let exif_segment = create_exif_segment_simple(&metadata);

	// Set the EXIF data
	jpeg.set_exif(Some(exif_segment.into()));

	// Convert back to bytes
	let mut output = Vec::new();
	let mut output_cursor = Cursor::new(&mut output);
	jpeg.encoder()
		.write_to(&mut output_cursor)
		.map_err(|e| format!("Failed to write JPEG: {:?}", e))?;

	Ok(ProcessedPhoto {
		data: output,
		metadata,
	})
}

#[cfg(target_os = "android")]
fn save_to_pictures_directory(
	filename: &str,
	image_data: &[u8],
	hide_from_gallery: bool,
) -> Result<std::path::PathBuf, std::io::Error> {
	#[cfg(unix)]
	use std::os::unix::fs::PermissionsExt;

	// Get the Pictures directory path
	let pictures_dir = if cfg!(target_os = "android") {
		// On Android, use /storage/emulated/0/Pictures directly
		// EXTERNAL_STORAGE often points to /sdcard which is a symlink but may not work properly
		"/storage/emulated/0/Pictures".to_string()
	} else {
		// On desktop, use the standard Pictures directory
		dirs::picture_dir()
			.map(|p| p.to_string_lossy().to_string())
			.unwrap_or_else(|| std::env::var("HOME").unwrap() + "/Pictures")
	};

	// Use dot folder if hiding from gallery
	let folder_name = if hide_from_gallery {
		".Hillview"
	} else {
		"Hillview"
	};
	let pictures_path = std::path::Path::new(&pictures_dir).join(folder_name);

	info!("🢄create_dir_all: {:?}", pictures_path);

	// Create the Hillview subdirectory in Pictures
	std::fs::create_dir_all(&pictures_path)?;

	info!(
		"🢄hide_from_gallery: {}, pictures_path: {:?}",
		hide_from_gallery, pictures_path
	);

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
		"🢄Saved photo to Pictures directory: {:?} (hidden: {})",
		photo_path, hide_from_gallery
	);

	// Set readable permissions for other apps on Unix systems
	#[cfg(unix)]
	{
		info!("🢄Setting permissions...");
		let mut perms = std::fs::metadata(&photo_path)?.permissions();
		perms.set_mode(0o644); // rw-r--r--
		std::fs::set_permissions(&photo_path, perms)?;
	}

	Ok(photo_path)
}

#[command]
#[allow(unused_variables)]
pub async fn save_photo_with_metadata(
	app_handle: tauri::AppHandle,
	image_data: Vec<u8>,
	metadata: PhotoMetadata,
	filename: String,
	hide_from_gallery: bool,
) -> Result<crate::device_photos::DevicePhotoMetadata, String> {
	// Process the photo with EXIF data
	let processed = embed_photo_metadata(image_data, metadata.clone()).await?;

	// Verify EXIF was embedded correctly
	info!(
		"Embedded EXIF metadata: lat={}, lon={}, alt={:?}, bearing={:?}",
		metadata.latitude, metadata.longitude, metadata.altitude, metadata.bearing
	);

	// Determine where to save the photo
	// Always save to Pictures directory - use dot folder if hiding from gallery
	#[cfg(target_os = "android")]
	let file_path = save_to_pictures_directory(&filename, &processed.data, hide_from_gallery)
		.map_err(|e| format!("Failed to save to Pictures directory: {}", e))?;

	#[cfg(not(target_os = "android"))]
	{
		return Err("Photo saving not implemented for non-Android platforms".to_string());
	}

	// Verify EXIF can be read back
	#[cfg(all(target_os = "android", debug_assertions))]
	{
		// Try reading with img-parts first to verify structure
		if let Ok(file_data) = std::fs::read(&file_path) {
			if let Ok(jpeg) = Jpeg::from_bytes(file_data.into()) {
				if let Some(exif) = jpeg.exif() {
					info!("🢄EXIF segment found, size: {} bytes", exif.len());
					// Log first few bytes for debugging
					if exif.len() > 16 {
						info!("🢄EXIF header: {:?}", &exif[0..16]);
					}
					// Check if it starts with "Exif\0\0" or directly with TIFF header
					let has_exif_header = exif.len() >= 6 && &exif[0..6] == b"Exif\0\0";
					let has_tiff_header =
						exif.len() >= 2 && (&exif[0..2] == b"II" || &exif[0..2] == b"MM");
					info!(
						"EXIF format check: has_exif_header={}, has_tiff_header={}",
						has_exif_header, has_tiff_header
					);
				} else {
					info!("🢄Warning: No EXIF segment found in saved file");
				}
			}
		}

		match read_photo_exif(file_path.to_string_lossy().to_string()).await {
			Ok(read_metadata) => {
				info!(
					"Verified EXIF after save: lat={}, lon={}, alt={:?}, bearing={:?}, location_source={}, bearing_source={}",
					read_metadata.latitude,
					read_metadata.longitude,
					read_metadata.altitude,
					read_metadata.bearing,
					read_metadata.location_source,
					read_metadata.bearing_source
				);
			}
			Err(e) => {
				info!("🢄Warning: Could not verify EXIF after save: {}", e);
			}
		}
	}

	#[cfg(target_os = "android")]
	{
		use tauri_plugin_hillview::HillviewExt;

		// Get file metadata for the photo
		let file_metadata = std::fs::metadata(&file_path)
			.map_err(|e| format!("Failed to get file metadata: {}", e))?;

		// Get dimensions from the JPEG data we already have in memory
		let img = image::load_from_memory(&processed.data)
			.map_err(|e| format!("Failed to load image from memory: {}", e))?;
		let (width, height) = (img.width(), img.height());

		// Calculate MD5 hash from the bytes we already have
		let hash_bytes = md5::compute(&processed.data);
		let file_hash = format!("{:x}", hash_bytes);

		// Send to Android database - let Kotlin generate the ID
		let plugin_photo = tauri_plugin_hillview::shared_types::DevicePhotoMetadata {
			id: String::new(), // Empty - Kotlin will generate this
			filename: filename.clone(),
			path: file_path.to_string_lossy().to_string(),
			metadata: tauri_plugin_hillview::shared_types::PhotoMetadata {
				latitude: metadata.latitude,
				longitude: metadata.longitude,
				altitude: metadata.altitude,
				bearing: metadata.bearing,
				timestamp: metadata.timestamp,
				accuracy: metadata.accuracy,
				location_source: metadata.location_source.clone(),
				bearing_source: metadata.bearing_source.clone(),
			},
			width,
			height,
			file_size: file_metadata.len(),
			created_at: chrono::Utc::now().timestamp(),
			file_hash: Some(file_hash.clone()),
		};

		let photo_id = match app_handle.hillview().add_photo_to_database(plugin_photo.clone()) {
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
			id: photo_id,
			filename,
			path: file_path.to_string_lossy().to_string(),
			latitude: metadata.latitude,
			longitude: metadata.longitude,
			altitude: metadata.altitude,
			bearing: metadata.bearing,
			timestamp: metadata.timestamp,
			accuracy: metadata.accuracy,
			width,
			height,
			file_size: file_metadata.len(),
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
}

#[command]
pub async fn read_device_photo(path: String) -> Result<Vec<u8>, String> {
	use std::fs;

	fs::read(&path).map_err(|e| format!("Failed to read photo: {}", e))
}

#[command]
pub async fn read_photo_exif(path: String) -> Result<PhotoMetadata, String> {
	// First try using img-parts to extract EXIF data
	let file_data = std::fs::read(&path).map_err(|e| format!("Failed to read file: {}", e))?;

	let jpeg =
		Jpeg::from_bytes(file_data.into()).map_err(|e| format!("Failed to parse JPEG: {:?}", e))?;

	let exif_data = jpeg
		.exif()
		.ok_or_else(|| "No EXIF data found".to_string())?;

	// img-parts may return EXIF data with or without "Exif\0\0" header
	let tiff_data = if exif_data.len() >= 6 && &exif_data[0..6] == b"Exif\0\0" {
		// Has "Exif\0\0" header, skip it
		exif_data[6..].to_vec()
	} else if exif_data.len() >= 2 && (&exif_data[0..2] == b"II" || &exif_data[0..2] == b"MM") {
		// Starts directly with TIFF header
		exif_data.to_vec()
	} else {
		return Err("Invalid EXIF format".to_string());
	};

	let exif_reader = exif::Reader::new()
		.read_raw(tiff_data)
		.map_err(|e| format!("Failed to read EXIF: {:?}", e))?;

	let mut metadata = PhotoMetadata {
		latitude: 0.0,
		longitude: 0.0,
		altitude: None,
		bearing: None,
		timestamp: 0,
		accuracy: 0.0,
		location_source: "unknown".to_string(),
		bearing_source: "unknown".to_string(),
	};

	// Read GPS coordinates - try PRIMARY first (GPS IFD is usually linked from PRIMARY)
	if let Some(lat_field) = exif_reader.get_field(exif::Tag::GPSLatitude, exif::In::PRIMARY) {
		if let Some(lat_ref_field) =
			exif_reader.get_field(exif::Tag::GPSLatitudeRef, exif::In::PRIMARY)
		{
			if let exif::Value::Rational(ref coords) = &lat_field.value {
				if coords.len() >= 3 {
					// Log the raw rational values
					info!(
						"GPS lat rationals: deg={}/{}, min={}/{}, sec={}/{}",
						coords[0].num,
						coords[0].denom,
						coords[1].num,
						coords[1].denom,
						coords[2].num,
						coords[2].denom
					);

					let degrees = coords[0].to_f64();
					let minutes = coords[1].to_f64();
					let seconds = coords[2].to_f64();
					info!(
						"GPS lat as floats: deg={}, min={}, sec={}",
						degrees, minutes, seconds
					);
					metadata.latitude = degrees + minutes / 60.0 + seconds / 3600.0;

					if let exif::Value::Ascii(ref s) = &lat_ref_field.value {
						if !s.is_empty() && s[0].starts_with(b"S") {
							metadata.latitude = -metadata.latitude;
						}
					}
				}
			}
		}
	}

	if let Some(lon_field) = exif_reader.get_field(exif::Tag::GPSLongitude, exif::In::PRIMARY) {
		if let Some(lon_ref_field) =
			exif_reader.get_field(exif::Tag::GPSLongitudeRef, exif::In::PRIMARY)
		{
			if let exif::Value::Rational(ref coords) = &lon_field.value {
				if coords.len() >= 3 {
					// Log the raw rational values
					info!(
						"GPS lon rationals: deg={}/{}, min={}/{}, sec={}/{}",
						coords[0].num,
						coords[0].denom,
						coords[1].num,
						coords[1].denom,
						coords[2].num,
						coords[2].denom
					);

					let degrees = coords[0].to_f64();
					let minutes = coords[1].to_f64();
					let seconds = coords[2].to_f64();
					info!(
						"GPS lon as floats: deg={}, min={}, sec={}",
						degrees, minutes, seconds
					);
					metadata.longitude = degrees + minutes / 60.0 + seconds / 3600.0;

					if let exif::Value::Ascii(ref s) = &lon_ref_field.value {
						if !s.is_empty() && s[0].starts_with(b"W") {
							metadata.longitude = -metadata.longitude;
						}
					}
				}
			}
		}
	}

	// Read altitude
	if let Some(alt_field) = exif_reader.get_field(exif::Tag::GPSAltitude, exif::In::PRIMARY) {
		if let exif::Value::Rational(ref alt) = &alt_field.value {
			if !alt.is_empty() {
				metadata.altitude = Some(alt[0].to_f64());
			}
		}
	}

	// Read bearing (GPSImgDirection)
	if let Some(bearing_field) =
		exif_reader.get_field(exif::Tag::GPSImgDirection, exif::In::PRIMARY)
	{
		if let exif::Value::Rational(ref bearing) = &bearing_field.value {
			if !bearing.is_empty() {
				info!(
					"GPS bearing rational: {}/{}",
					bearing[0].num, bearing[0].denom
				);
				metadata.bearing = Some(bearing[0].to_f64());
				info!("🢄GPS bearing as float: {}", bearing[0].to_f64());
			}
		}
	}

	// Read timestamp
	if let Some(date_field) = exif_reader.get_field(exif::Tag::DateTime, exif::In::PRIMARY) {
		if let exif::Value::Ascii(ref date_str) = &date_field.value {
			if !date_str.is_empty() {
				// Parse EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
				if let Ok(dt) = chrono::NaiveDateTime::parse_from_str(
					std::str::from_utf8(&date_str[0]).unwrap_or(""),
					"%Y:%m:%d %H:%M:%S",
				) {
					metadata.timestamp = dt.and_utc().timestamp();
				}
			}
		}
	}

	// Read UserComment for provenance data
	if let Some(comment_field) = exif_reader.get_field(exif::Tag::UserComment, exif::In::PRIMARY) {
		if let exif::Value::Undefined(ref comment_bytes, _) = &comment_field.value {
			if comment_bytes.len() > 8 {
				// Skip the 8-byte character code header
				let comment_text = &comment_bytes[8..];
				if let Ok(comment_str) = std::str::from_utf8(comment_text) {
					// Try to parse as JSON
					if let Ok(provenance) = serde_json::from_str::<ProvenanceData>(comment_str) {
						metadata.location_source = provenance.location_source;
						metadata.bearing_source = provenance.bearing_source;
						info!("🢄Successfully read provenance from UserComment: location_source={}, bearing_source={}",
							  metadata.location_source, metadata.bearing_source);
					} else {
						info!("🢄UserComment found but not valid JSON provenance: {}", comment_str);
					}
				}
			}
		}
	}

	Ok(metadata)
}

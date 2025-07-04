use chrono::{DateTime, Utc, Timelike};
use img_parts::{jpeg::Jpeg, ImageEXIF};
use serde::{Deserialize, Serialize};
use std::io::Cursor;
use tauri::{command, Manager};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PhotoMetadata {
    pub latitude: f64,
    pub longitude: f64,
    pub altitude: Option<f64>,
    pub bearing: Option<f64>,
    pub timestamp: i64,
    pub accuracy: f64,
}

#[derive(Debug, Serialize)]
pub struct ProcessedPhoto {
    pub data: Vec<u8>,
    pub metadata: PhotoMetadata,
}

fn create_exif_segment(metadata: &PhotoMetadata) -> Vec<u8> {
    let mut exif_data = Vec::new();
    
    // EXIF header
    exif_data.extend_from_slice(&[0xFF, 0xE1]); // APP1 marker
    let size_placeholder = exif_data.len();
    exif_data.extend_from_slice(&[0x00, 0x00]); // Size placeholder
    exif_data.extend_from_slice(b"Exif\0\0"); // Exif identifier
    
    // TIFF header (little-endian)
    exif_data.extend_from_slice(&[0x49, 0x49]); // II (little-endian)
    exif_data.extend_from_slice(&[0x2A, 0x00]); // 42
    exif_data.extend_from_slice(&[0x08, 0x00, 0x00, 0x00]); // IFD0 offset
    
    // IFD0
    let ifd0_start = exif_data.len();
    exif_data.extend_from_slice(&[0x02, 0x00]); // 2 entries
    
    // GPS IFD Pointer (tag 0x8825)
    exif_data.extend_from_slice(&[0x25, 0x88]); // Tag
    exif_data.extend_from_slice(&[0x04, 0x00]); // Type: LONG
    exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count
    let gps_ifd_offset: u32 = 0x26; // Offset to GPS IFD
    exif_data.extend_from_slice(&gps_ifd_offset.to_le_bytes());
    
    // DateTime (tag 0x0132)
    let datetime = DateTime::<Utc>::from_timestamp(metadata.timestamp, 0)
        .unwrap_or_else(|| Utc::now())
        .format("%Y:%m:%d %H:%M:%S")
        .to_string();
    exif_data.extend_from_slice(&[0x32, 0x01]); // Tag
    exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
    exif_data.extend_from_slice(&[0x14, 0x00, 0x00, 0x00]); // Count (20 bytes)
    let datetime_offset: u32 = 0x80; // Offset to datetime string
    exif_data.extend_from_slice(&datetime_offset.to_le_bytes());
    
    // Next IFD offset (0 = no next IFD)
    exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);
    
    // GPS IFD
    while exif_data.len() < ifd0_start + gps_ifd_offset as usize {
        exif_data.push(0x00);
    }
    
    let gps_entry_count = if metadata.bearing.is_some() && metadata.altitude.is_some() { 9 } 
                         else if metadata.bearing.is_some() || metadata.altitude.is_some() { 7 } 
                         else { 6 };
    exif_data.extend_from_slice(&(gps_entry_count as u16).to_le_bytes());
    
    // GPSVersionID (tag 0x0000)
    exif_data.extend_from_slice(&[0x00, 0x00]); // Tag
    exif_data.extend_from_slice(&[0x01, 0x00]); // Type: BYTE
    exif_data.extend_from_slice(&[0x04, 0x00, 0x00, 0x00]); // Count
    exif_data.extend_from_slice(&[0x02, 0x03, 0x00, 0x00]); // Version 2.3.0.0
    
    // GPSLatitudeRef (tag 0x0001)
    exif_data.extend_from_slice(&[0x01, 0x00]); // Tag
    exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
    exif_data.extend_from_slice(&[0x02, 0x00, 0x00, 0x00]); // Count
    let lat_ref = if metadata.latitude >= 0.0 { b"N\0" } else { b"S\0" };
    exif_data.extend_from_slice(&[lat_ref[0], lat_ref[1], 0x00, 0x00]);
    
    // GPSLatitude (tag 0x0002)
    let lat_abs = metadata.latitude.abs();
    let lat_deg = lat_abs.floor() as u32;
    let lat_min = ((lat_abs - lat_deg as f64) * 60.0).floor() as u32;
    let lat_sec = ((lat_abs - lat_deg as f64 - lat_min as f64 / 60.0) * 3600.0 * 10000.0) as u32;
    
    exif_data.extend_from_slice(&[0x02, 0x00]); // Tag
    exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
    exif_data.extend_from_slice(&[0x03, 0x00, 0x00, 0x00]); // Count
    let lat_offset: u32 = 0x100;
    exif_data.extend_from_slice(&lat_offset.to_le_bytes());
    
    // GPSLongitudeRef (tag 0x0003)
    exif_data.extend_from_slice(&[0x03, 0x00]); // Tag
    exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
    exif_data.extend_from_slice(&[0x02, 0x00, 0x00, 0x00]); // Count
    let lon_ref = if metadata.longitude >= 0.0 { b"E\0" } else { b"W\0" };
    exif_data.extend_from_slice(&[lon_ref[0], lon_ref[1], 0x00, 0x00]);
    
    // GPSLongitude (tag 0x0004)
    let lon_abs = metadata.longitude.abs();
    let lon_deg = lon_abs.floor() as u32;
    let lon_min = ((lon_abs - lon_deg as f64) * 60.0).floor() as u32;
    let lon_sec = ((lon_abs - lon_deg as f64 - lon_min as f64 / 60.0) * 3600.0 * 10000.0) as u32;
    
    exif_data.extend_from_slice(&[0x04, 0x00]); // Tag
    exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
    exif_data.extend_from_slice(&[0x03, 0x00, 0x00, 0x00]); // Count
    let lon_offset: u32 = 0x118;
    exif_data.extend_from_slice(&lon_offset.to_le_bytes());
    
    // GPSTimeStamp (tag 0x0007)
    let dt = DateTime::<Utc>::from_timestamp(metadata.timestamp, 0)
        .unwrap_or(DateTime::<Utc>::from_timestamp(0, 0).unwrap());
    let hour = dt.hour();
    let minute = dt.minute();
    let second = dt.second();
    
    exif_data.extend_from_slice(&[0x07, 0x00]); // Tag
    exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
    exif_data.extend_from_slice(&[0x03, 0x00, 0x00, 0x00]); // Count
    let time_offset: u32 = 0x130;
    exif_data.extend_from_slice(&time_offset.to_le_bytes());
    
    // Optional: GPSAltitude (tag 0x0006)
    if let Some(_altitude) = metadata.altitude {
        exif_data.extend_from_slice(&[0x06, 0x00]); // Tag
        exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
        exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count
        let alt_offset: u32 = 0x148;
        exif_data.extend_from_slice(&alt_offset.to_le_bytes());
    }
    
    // Optional: GPSImgDirectionRef (tag 0x000E) - True/Magnetic North
    if metadata.bearing.is_some() {
        exif_data.extend_from_slice(&[0x0E, 0x00]); // Tag
        exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
        exif_data.extend_from_slice(&[0x02, 0x00, 0x00, 0x00]); // Count
        exif_data.extend_from_slice(b"T\0\0\0"); // True North (use "M" for Magnetic)
    }
    
    // Optional: GPSImgDirection (tag 0x0010) for bearing
    if let Some(_bearing) = metadata.bearing {
        exif_data.extend_from_slice(&[0x10, 0x00]); // Tag
        exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
        exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count
        let bearing_offset: u32 = 0x150;
        exif_data.extend_from_slice(&bearing_offset.to_le_bytes());
    }
    
    // Next IFD offset (0 = no next IFD)
    exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);
    
    // Add padding and data
    while exif_data.len() < ifd0_start + datetime_offset as usize {
        exif_data.push(0x00);
    }
    exif_data.extend_from_slice(datetime.as_bytes());
    exif_data.push(0x00); // Null terminator
    
    // Add GPS coordinate data
    while exif_data.len() < ifd0_start + lat_offset as usize {
        exif_data.push(0x00);
    }
    // Latitude degrees, minutes, seconds as rationals
    exif_data.extend_from_slice(&lat_deg.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&lat_min.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&lat_sec.to_le_bytes());
    exif_data.extend_from_slice(&10000u32.to_le_bytes());
    
    // Longitude degrees, minutes, seconds as rationals
    exif_data.extend_from_slice(&lon_deg.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&lon_min.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&lon_sec.to_le_bytes());
    exif_data.extend_from_slice(&10000u32.to_le_bytes());
    
    // Time rationals
    exif_data.extend_from_slice(&hour.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&minute.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&second.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    
    // Altitude rational
    if let Some(altitude) = metadata.altitude {
        let alt_num = (altitude * 1000.0) as u32;
        exif_data.extend_from_slice(&alt_num.to_le_bytes());
        exif_data.extend_from_slice(&1000u32.to_le_bytes());
    }
    
    // Bearing rational
    if let Some(bearing) = metadata.bearing {
        let bearing_num = (bearing * 100.0) as u32;
        exif_data.extend_from_slice(&bearing_num.to_le_bytes());
        exif_data.extend_from_slice(&100u32.to_le_bytes());
    }
    
    // Update segment size
    let segment_size = (exif_data.len() - 2) as u16;
    exif_data[size_placeholder] = (segment_size >> 8) as u8;
    exif_data[size_placeholder + 1] = (segment_size & 0xFF) as u8;
    
    exif_data
}

#[command]
pub async fn embed_photo_metadata(
    image_data: Vec<u8>,
    metadata: PhotoMetadata,
) -> Result<ProcessedPhoto, String> {
    // Parse the JPEG
    let mut jpeg = Jpeg::from_bytes(image_data.clone().into()).map_err(|e| format!("Failed to parse JPEG: {:?}", e))?;
    
    // Create EXIF segment
    let exif_segment = create_exif_segment(&metadata);
    
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
fn save_to_android_gallery(image_data: &[u8], filename: &str, _metadata: &PhotoMetadata) -> Result<(), std::io::Error> {
    use std::os::unix::fs::PermissionsExt;
    
    // Get the Pictures directory path
    // On Android, this typically maps to /storage/emulated/0/Pictures
    let pictures_dir = std::env::var("EXTERNAL_STORAGE")
        .unwrap_or_else(|_| "/storage/emulated/0".to_string());
    let pictures_path = std::path::Path::new(&pictures_dir).join("Pictures").join("Hillview");
    
    // Create the Hillview subdirectory in Pictures
    std::fs::create_dir_all(&pictures_path)?;
    
    // Save the file
    let gallery_path = pictures_path.join(filename);
    std::fs::write(&gallery_path, image_data)?;
    
    // Set readable permissions for other apps
    let mut perms = std::fs::metadata(&gallery_path)?.permissions();
    perms.set_mode(0o644); // rw-r--r--
    std::fs::set_permissions(&gallery_path, perms)?;
    
    // Note: On newer Android versions (API 29+), we would need to use MediaStore API
    // through JNI for proper gallery integration. This direct file approach works
    // for Android 9 and below, or with legacy storage permissions.
    
    Ok(())
}

#[command]
pub async fn save_photo_with_metadata(
    app_handle: tauri::AppHandle,
    image_data: Vec<u8>,
    metadata: PhotoMetadata,
    filename: String,
    save_to_gallery: bool,
) -> Result<crate::device_photos::DevicePhotoMetadata, String> {
        
    // Process the photo with EXIF data
    let processed = embed_photo_metadata(image_data, metadata.clone()).await?;
    
    // Get app data directory
    let app_dir = app_handle.path().app_data_dir()
        .map_err(|_| "Failed to get app data directory".to_string())?;
    
    // Create photos directory
    let photos_dir = app_dir.join("captured_photos");
    std::fs::create_dir_all(&photos_dir)
        .map_err(|e| format!("Failed to create photos directory: {}", e))?;
    
    // Save the file to app directory
    let file_path = photos_dir.join(&filename);
    std::fs::write(&file_path, &processed.data)
        .map_err(|e| format!("Failed to save photo: {}", e))?;
    
    // Save to Android gallery if requested
    #[cfg(target_os = "android")]
    if save_to_gallery {
        save_to_android_gallery(&processed.data, &filename, &metadata)
            .map_err(|e| format!("Failed to save to gallery: {}", e))?;
    }
    
    // Add to device photos database with dimensions
    let device_photo = crate::device_photos::add_device_photo_to_db(
        app_handle,
        file_path.to_string_lossy().to_string(),
        metadata,
    ).await?;
    
    Ok(device_photo)
}

#[command]
pub async fn read_device_photo(path: String) -> Result<Vec<u8>, String> {
    use std::fs;
    
    fs::read(&path)
        .map_err(|e| format!("Failed to read photo: {}", e))
}

#[command]
pub async fn read_photo_exif(path: String) -> Result<PhotoMetadata, String> {
    use std::fs::File;
    use std::io::BufReader;
    
    let file = File::open(&path)
        .map_err(|e| format!("Failed to open file: {}", e))?;
    let mut reader = BufReader::new(file);
    
    let exif = exif::Reader::new()
        .read_from_container(&mut reader)
        .map_err(|e| format!("Failed to read EXIF: {}", e))?;
    
    let mut metadata = PhotoMetadata {
        latitude: 0.0,
        longitude: 0.0,
        altitude: None,
        bearing: None,
        timestamp: 0,
        accuracy: 0.0,
    };
    
    // Read GPS coordinates
    if let Some(lat_field) = exif.get_field(exif::Tag::GPSLatitude, exif::In::PRIMARY) {
        if let Some(lat_ref_field) = exif.get_field(exif::Tag::GPSLatitudeRef, exif::In::PRIMARY) {
            if let exif::Value::Rational(ref coords) = &lat_field.value {
                if coords.len() >= 3 {
                    let degrees = coords[0].to_f64();
                    let minutes = coords[1].to_f64();
                    let seconds = coords[2].to_f64();
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
    
    if let Some(lon_field) = exif.get_field(exif::Tag::GPSLongitude, exif::In::PRIMARY) {
        if let Some(lon_ref_field) = exif.get_field(exif::Tag::GPSLongitudeRef, exif::In::PRIMARY) {
            if let exif::Value::Rational(ref coords) = &lon_field.value {
                if coords.len() >= 3 {
                    let degrees = coords[0].to_f64();
                    let minutes = coords[1].to_f64();
                    let seconds = coords[2].to_f64();
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
    if let Some(alt_field) = exif.get_field(exif::Tag::GPSAltitude, exif::In::PRIMARY) {
        if let exif::Value::Rational(ref alt) = &alt_field.value {
            if !alt.is_empty() {
                metadata.altitude = Some(alt[0].to_f64());
            }
        }
    }
    
    // Read bearing (GPSImgDirection)
    if let Some(bearing_field) = exif.get_field(exif::Tag::GPSImgDirection, exif::In::PRIMARY) {
        if let exif::Value::Rational(ref bearing) = &bearing_field.value {
            if !bearing.is_empty() {
                metadata.bearing = Some(bearing[0].to_f64());
            }
        }
    }
    
    // Read timestamp
    if let Some(date_field) = exif.get_field(exif::Tag::DateTime, exif::In::PRIMARY) {
        if let exif::Value::Ascii(ref date_str) = &date_field.value {
            if !date_str.is_empty() {
                // Parse EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
                if let Ok(dt) = chrono::NaiveDateTime::parse_from_str(
                    std::str::from_utf8(&date_str[0]).unwrap_or(""),
                    "%Y:%m:%d %H:%M:%S"
                ) {
                    metadata.timestamp = dt.and_utc().timestamp();
                }
            }
        }
    }
    
    Ok(metadata)
}
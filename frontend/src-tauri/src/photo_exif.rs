use chrono::{DateTime, Utc, Timelike};
use img_parts::{jpeg::Jpeg, ImageEXIF};
use serde::{Deserialize, Serialize};
use std::io::Cursor;
use tauri::{command, Manager};
use log::info;

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

fn create_exif_segment_simple(metadata: &PhotoMetadata) -> Vec<u8> {
    info!("Creating EXIF for: lat={}, lon={}, alt={:?}, bearing={:?}", 
          metadata.latitude, metadata.longitude, metadata.altitude, metadata.bearing);
    
    let mut exif_data = Vec::new();
    
    // Don't include "Exif\0\0" - img-parts adds it automatically
    let tiff_start = 0;
    
    // TIFF header (little-endian)
    exif_data.extend_from_slice(&[0x49, 0x49]); // II
    exif_data.extend_from_slice(&[0x2A, 0x00]); // 42
    exif_data.extend_from_slice(&[0x08, 0x00, 0x00, 0x00]); // IFD0 offset (8 from TIFF start)
    
    // IFD0 at offset 8 from TIFF - just one entry pointing to GPS IFD
    exif_data.extend_from_slice(&[0x01, 0x00]); // 1 entry
    
    // GPS IFD Pointer
    exif_data.extend_from_slice(&[0x25, 0x88]); // Tag 0x8825
    exif_data.extend_from_slice(&[0x04, 0x00]); // Type: LONG
    exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
    let gps_ifd_offset: u32 = 0x1A; // GPS IFD offset from TIFF start
    exif_data.extend_from_slice(&gps_ifd_offset.to_le_bytes());
    
    // Next IFD offset (none)
    exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);
    
    // Pad to GPS IFD location
    while exif_data.len() < tiff_start + gps_ifd_offset as usize {
        exif_data.push(0x00);
    }
    
    // Count GPS entries
    let mut gps_entry_count = 4u16; // LatRef, Lat, LonRef, Lon
    if metadata.altitude.is_some() {
        gps_entry_count += 2; // AltRef, Alt
    }
    if metadata.bearing.is_some() {
        gps_entry_count += 2; // ImgDirectionRef, ImgDirection
    }
    exif_data.extend_from_slice(&gps_entry_count.to_le_bytes());
    
    // GPSLatitudeRef
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
    
    info!("GPS Lat: {} = {}° {}' {}/100\"", lat_abs, lat_deg, lat_min, lat_sec);
    
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
    // Handle longitude in 0-360 range (where > 180 means West)
    if metadata.longitude <= 180.0 {
        exif_data.extend_from_slice(b"E\0\0\0");
    } else {
        exif_data.extend_from_slice(b"W\0\0\0");
    }
    
    // GPSLongitude
    // Convert from 0-360 to proper longitude if needed
    let lon_proper = if metadata.longitude > 180.0 {
        360.0 - metadata.longitude  // Convert to proper West longitude
    } else {
        metadata.longitude
    };
    let lon_deg = lon_proper.floor() as u32;
    let lon_min = ((lon_proper - lon_deg as f64) * 60.0).floor() as u32;
    let lon_sec = ((lon_proper - lon_deg as f64 - lon_min as f64 / 60.0) * 3600.0 * 100.0) as u32;
    
    info!("GPS Lon: {} (proper: {}) = {}° {}' {}/100\"", metadata.longitude, lon_proper, lon_deg, lon_min, lon_sec);
    
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
        exif_data.extend_from_slice(&[0x11, 0x00]); // Tag
        exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
        exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
        exif_data.extend_from_slice(&next_offset.to_le_bytes());
        next_offset += 8;
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
    
    // Bearing rational
    if let Some(bearing) = metadata.bearing {
        let bearing_num = (bearing * 100.0) as u32;
        exif_data.extend_from_slice(&bearing_num.to_le_bytes());
        exif_data.extend_from_slice(&100u32.to_le_bytes());
    }
    
    // Log final EXIF size and structure for debugging
    info!("Created simple EXIF: {} bytes", exif_data.len());
    info!("EXIF structure: TIFF at {}, IFD0 at {}, GPS IFD at {}, lat data at {}, lon data at {}",
          tiff_start, tiff_start + 8, tiff_start + gps_ifd_offset as usize,
          tiff_start + lat_offset as usize, tiff_start + lon_offset as usize);
    
    exif_data
}

fn create_exif_segment(metadata: &PhotoMetadata) -> Vec<u8> {
    let mut exif_data = Vec::new();
    
    // Start with Exif identifier (img-parts will add the APP1 marker)
    exif_data.extend_from_slice(b"Exif\0\0"); // Exif identifier
    
    let tiff_start = exif_data.len(); // Start of TIFF data
    
    // TIFF header (little-endian)
    exif_data.extend_from_slice(&[0x49, 0x49]); // II (little-endian)
    exif_data.extend_from_slice(&[0x2A, 0x00]); // 42
    exif_data.extend_from_slice(&[0x08, 0x00, 0x00, 0x00]); // IFD0 offset
    
    // IFD0
    exif_data.extend_from_slice(&[0x02, 0x00]); // 2 entries
    
    // GPS IFD Pointer (tag 0x8825)
    exif_data.extend_from_slice(&[0x25, 0x88]); // Tag
    exif_data.extend_from_slice(&[0x04, 0x00]); // Type: LONG
    exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count
    let gps_ifd_offset: u32 = 0x26; // Offset to GPS IFD (relative to TIFF header)
    exif_data.extend_from_slice(&gps_ifd_offset.to_le_bytes());
    
    // DateTime (tag 0x0132)
    let datetime = DateTime::<Utc>::from_timestamp(metadata.timestamp, 0)
        .unwrap_or_else(|| Utc::now())
        .format("%Y:%m:%d %H:%M:%S")
        .to_string();
    exif_data.extend_from_slice(&[0x32, 0x01]); // Tag
    exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
    exif_data.extend_from_slice(&[0x14, 0x00, 0x00, 0x00]); // Count (20 bytes)
    let datetime_offset: u32 = 0x80; // Offset to datetime string (relative to TIFF header)
    exif_data.extend_from_slice(&datetime_offset.to_le_bytes());
    
    // Next IFD offset (0 = no next IFD)
    exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);
    
    // GPS IFD
    while exif_data.len() < tiff_start + gps_ifd_offset as usize {
        exif_data.push(0x00);
    }
    
    // Count GPS entries: 6 base + optional altitude (2) + optional bearing (2)
    let mut gps_entry_count = 6; // GPSVersionID, LatRef, Lat, LonRef, Lon, TimeStamp
    if metadata.altitude.is_some() {
        gps_entry_count += 2; // AltitudeRef + Altitude
    }
    if metadata.bearing.is_some() {
        gps_entry_count += 2; // ImgDirectionRef + ImgDirection
    }
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
    // Handle longitude in 0-360 range (where > 180 means West)
    let lon_ref = if metadata.longitude <= 180.0 { b"E\0" } else { b"W\0" };
    exif_data.extend_from_slice(&[lon_ref[0], lon_ref[1], 0x00, 0x00]);
    
    // GPSLongitude (tag 0x0004)
    // Convert from 0-360 to proper longitude if needed
    let lon_proper = if metadata.longitude > 180.0 {
        360.0 - metadata.longitude  // Convert to proper West longitude
    } else {
        metadata.longitude
    };
    let lon_deg = lon_proper.floor() as u32;
    let lon_min = ((lon_proper - lon_deg as f64) * 60.0).floor() as u32;
    let lon_sec = ((lon_proper - lon_deg as f64 - lon_min as f64 / 60.0) * 3600.0 * 10000.0) as u32;
    
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
    
    // Optional: GPSAltitudeRef (tag 0x0005)
    if metadata.altitude.is_some() {
        exif_data.extend_from_slice(&[0x05, 0x00]); // Tag
        exif_data.extend_from_slice(&[0x01, 0x00]); // Type: BYTE
        exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count
        exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]); // 0 = above sea level
    }
    
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
    while exif_data.len() < tiff_start + datetime_offset as usize {
        exif_data.push(0x00);
    }
    exif_data.extend_from_slice(datetime.as_bytes());
    exif_data.push(0x00); // Null terminator
    
    // Add GPS coordinate data
    while exif_data.len() < tiff_start + lat_offset as usize {
        exif_data.push(0x00);
    }
    // Latitude degrees, minutes, seconds as rationals
    info!("Writing lat rationals: deg={}/1, min={}/1, sec={}/10000", lat_deg, lat_min, lat_sec);
    exif_data.extend_from_slice(&lat_deg.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&lat_min.to_le_bytes());
    exif_data.extend_from_slice(&1u32.to_le_bytes());
    exif_data.extend_from_slice(&lat_sec.to_le_bytes());
    exif_data.extend_from_slice(&10000u32.to_le_bytes());
    
    // Longitude degrees, minutes, seconds as rationals
    info!("Writing lon rationals: deg={}/1, min={}/1, sec={}/10000", lon_deg, lon_min, lon_sec);
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
    
    // Log final EXIF size for debugging
    info!("Created EXIF segment: total size = {} bytes, TIFF data size = {} bytes", 
          exif_data.len(), exif_data.len() - tiff_start);
    
    exif_data
}

#[command]
pub async fn embed_photo_metadata(
    image_data: Vec<u8>,
    metadata: PhotoMetadata,
) -> Result<ProcessedPhoto, String> {
    // Parse the JPEG
    let mut jpeg = Jpeg::from_bytes(image_data.clone().into()).map_err(|e| format!("Failed to parse JPEG: {:?}", e))?;
    
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
fn save_to_android_gallery(image_data: &[u8], filename: &str, _metadata: &PhotoMetadata) -> Result<std::path::PathBuf, std::io::Error> {
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
    info!("Saved photo to gallery: {:?}", gallery_path);
    
    // Set readable permissions for other apps
    let mut perms = std::fs::metadata(&gallery_path)?.permissions();
    perms.set_mode(0o644); // rw-r--r--
    std::fs::set_permissions(&gallery_path, perms)?;
    
    // Note: On newer Android versions (API 29+), we would need to use MediaStore API
    // through JNI for proper gallery integration. This direct file approach works
    // for Android 9 and below, or with legacy storage permissions.
    
    // Trigger media scan to make the photo appear in gallery
    // This is a workaround - ideally we'd use MediaScannerConnection through JNI
    info!("Photo saved to gallery at: {:?}", gallery_path);
    
    Ok(gallery_path)
}

fn save_to_app_storage(app_handle: &tauri::AppHandle, filename: &str, data: &[u8]) -> Result<std::path::PathBuf, String> {
    // Get app data directory
    let app_dir = app_handle.path().app_data_dir()
        .map_err(|_| "Failed to get app data directory".to_string())?;
    
    // Create photos directory
    let photos_dir = app_dir.join("captured_photos");
    std::fs::create_dir_all(&photos_dir)
        .map_err(|e| format!("Failed to create photos directory: {}", e))?;
    
    // Save the file
    let file_path = photos_dir.join(filename);
    std::fs::write(&file_path, data)
        .map_err(|e| format!("Failed to save photo: {}", e))?;
    
    Ok(file_path)
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
    
    // Verify EXIF was embedded correctly
    info!("Embedded EXIF metadata: lat={}, lon={}, alt={:?}, bearing={:?}", 
          metadata.latitude, metadata.longitude, metadata.altitude, metadata.bearing);
    
    // Determine where to save the photo
    let file_path = if cfg!(target_os = "android") && save_to_gallery {
        // On Android with save_to_gallery enabled, save directly to gallery
        info!("Saving directly to Android gallery with metadata: lat={}, lon={}, alt={:?}, bearing={:?}", 
              metadata.latitude, metadata.longitude, metadata.altitude, metadata.bearing);
        
        #[cfg(target_os = "android")]
        {
            save_to_android_gallery(&processed.data, &filename, &metadata)
                .map_err(|e| format!("Failed to save to gallery: {}", e))?
        }
        #[cfg(not(target_os = "android"))]
        {
            unreachable!("This branch should never be reached on non-Android platforms")
        }
    } else {
        // Save to app private storage
        save_to_app_storage(&app_handle, &filename, &processed.data)?
    };
    
    // Verify EXIF can be read back
    #[cfg(debug_assertions)]
    {
        // Try reading with img-parts first to verify structure
        if let Ok(file_data) = std::fs::read(&file_path) {
            if let Ok(jpeg) = Jpeg::from_bytes(file_data.into()) {
                if let Some(exif) = jpeg.exif() {
                    info!("EXIF segment found, size: {} bytes", exif.len());
                    // Log first few bytes for debugging
                    if exif.len() > 16 {
                        info!("EXIF header: {:?}", &exif[0..16]);
                    }
                    // Check if it starts with "Exif\0\0" or directly with TIFF header
                    let has_exif_header = exif.len() >= 6 && &exif[0..6] == b"Exif\0\0";
                    let has_tiff_header = exif.len() >= 2 && (&exif[0..2] == b"II" || &exif[0..2] == b"MM");
                    info!("EXIF format check: has_exif_header={}, has_tiff_header={}", has_exif_header, has_tiff_header);
                } else {
                    info!("Warning: No EXIF segment found in saved file");
                }
            }
        }
        
        match read_photo_exif(file_path.to_string_lossy().to_string()).await {
            Ok(read_metadata) => {
                info!("Verified EXIF after save: lat={}, lon={}, alt={:?}, bearing={:?}", 
                      read_metadata.latitude, read_metadata.longitude, 
                      read_metadata.altitude, read_metadata.bearing);
            }
            Err(e) => {
                info!("Warning: Could not verify EXIF after save: {}", e);
            }
        }
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
    // First try using img-parts to extract EXIF data
    let file_data = std::fs::read(&path)
        .map_err(|e| format!("Failed to read file: {}", e))?;
    
    let jpeg = Jpeg::from_bytes(file_data.into())
        .map_err(|e| format!("Failed to parse JPEG: {:?}", e))?;
    
    let exif_data = jpeg.exif()
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
    };
    
    // Read GPS coordinates
    if let Some(lat_field) = exif_reader.get_field(exif::Tag::GPSLatitude, exif::In::PRIMARY) {
        if let Some(lat_ref_field) = exif_reader.get_field(exif::Tag::GPSLatitudeRef, exif::In::PRIMARY) {
            if let exif::Value::Rational(ref coords) = &lat_field.value {
                if coords.len() >= 3 {
                    // Log the raw rational values
                    info!("GPS lat rationals: deg={}/{}, min={}/{}, sec={}/{}", 
                          coords[0].num, coords[0].denom,
                          coords[1].num, coords[1].denom,
                          coords[2].num, coords[2].denom);
                    
                    let degrees = coords[0].to_f64();
                    let minutes = coords[1].to_f64();
                    let seconds = coords[2].to_f64();
                    info!("GPS lat as floats: deg={}, min={}, sec={}", degrees, minutes, seconds);
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
        if let Some(lon_ref_field) = exif_reader.get_field(exif::Tag::GPSLongitudeRef, exif::In::PRIMARY) {
            if let exif::Value::Rational(ref coords) = &lon_field.value {
                if coords.len() >= 3 {
                    // Log the raw rational values
                    info!("GPS lon rationals: deg={}/{}, min={}/{}, sec={}/{}", 
                          coords[0].num, coords[0].denom,
                          coords[1].num, coords[1].denom,
                          coords[2].num, coords[2].denom);
                    
                    let degrees = coords[0].to_f64();
                    let minutes = coords[1].to_f64();
                    let seconds = coords[2].to_f64();
                    info!("GPS lon as floats: deg={}, min={}, sec={}", degrees, minutes, seconds);
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
    if let Some(bearing_field) = exif_reader.get_field(exif::Tag::GPSImgDirection, exif::In::PRIMARY) {
        if let exif::Value::Rational(ref bearing) = &bearing_field.value {
            if !bearing.is_empty() {
                info!("GPS bearing rational: {}/{}", bearing[0].num, bearing[0].denom);
                metadata.bearing = Some(bearing[0].to_f64());
                info!("GPS bearing as float: {}", bearing[0].to_f64());
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
                    "%Y:%m:%d %H:%M:%S"
                ) {
                    metadata.timestamp = dt.and_utc().timestamp();
                }
            }
        }
    }
    
    Ok(metadata)
}
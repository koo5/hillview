use chrono;
#[cfg(debug_assertions)]
use img_parts::{jpeg::Jpeg, ImageEXIF};
use log::{info, warn};
use serde::{Deserialize, Serialize};
use crate::types::PhotoMetadata;

// EXIF tag constants for readability
#[cfg(target_os = "android")]
mod exif_tags {
    // IFD0 tags
    pub const ORIENTATION: u16 = 0x0112;
    pub const DATE_TIME: u16 = 0x0132;
    pub const DATE_TIME_ORIGINAL: u16 = 0x9003;
    pub const GPS_IFD_POINTER: u16 = 0x8825;
    pub const USER_COMMENT: u16 = 0x9286;

    // GPS tags
    pub const GPS_VERSION_ID: u16 = 0x0000;
    pub const GPS_LATITUDE_REF: u16 = 0x0001;
    pub const GPS_LATITUDE: u16 = 0x0002;
    pub const GPS_LONGITUDE_REF: u16 = 0x0003;
    pub const GPS_LONGITUDE: u16 = 0x0004;
    pub const GPS_ALTITUDE_REF: u16 = 0x0005;
    pub const GPS_ALTITUDE: u16 = 0x0006;
    pub const GPS_IMG_DIRECTION_REF: u16 = 0x0010;
    pub const GPS_IMG_DIRECTION: u16 = 0x0011;
    pub const GPS_DEST_BEARING_REF: u16 = 0x0017;
    pub const GPS_DEST_BEARING: u16 = 0x0018;
}

// EXIF data types
#[cfg(target_os = "android")]
#[derive(Debug)]
#[allow(dead_code)]
enum ExifValue {
    Short(u16),
    Long(u32),
    Rational(u32, u32),
    Ascii(String),
    Undefined(Vec<u8>),
    Rationals(Vec<(u32, u32)>),
}

// EXIF entry structure
#[cfg(target_os = "android")]
#[derive(Debug)]
struct ExifEntry {
    tag: u16,
    value: ExifValue,
}

// Builder for maintaining EXIF structure
#[cfg(target_os = "android")]
struct ExifBuilder {
    ifd0_entries: Vec<ExifEntry>,
    gps_entries: Vec<ExifEntry>,
    user_comment: Option<Vec<u8>>,
}


#[derive(Debug, Serialize, Deserialize)]
struct ProvenanceData {
	location_source: String,
	bearing_source: String,
}

#[cfg(target_os = "android")]
impl ExifBuilder {
    fn new() -> Self {
        Self {
            ifd0_entries: Vec::new(),
            gps_entries: Vec::new(),
            user_comment: None,
        }
    }

    fn add_orientation(&mut self, orientation: u16) {
        self.ifd0_entries.push(ExifEntry {
            tag: exif_tags::ORIENTATION,
            value: ExifValue::Short(orientation),
        });
    }

    fn add_timestamps(&mut self, timestamp: i64) {
        let datetime = chrono::DateTime::from_timestamp(timestamp, 0)
            .unwrap_or_else(|| chrono::Utc::now());
        let datetime_str = datetime.format("%Y:%m:%d %H:%M:%S").to_string();

        // Add both DateTime and DateTimeOriginal
        self.ifd0_entries.push(ExifEntry {
            tag: exif_tags::DATE_TIME,
            value: ExifValue::Ascii(datetime_str.clone()),
        });

        self.ifd0_entries.push(ExifEntry {
            tag: exif_tags::DATE_TIME_ORIGINAL,
            value: ExifValue::Ascii(datetime_str),
        });
    }

    fn add_gps_data(&mut self, lat: f64, lon: f64, alt: Option<f64>) {
        // GPS Version
        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_VERSION_ID,
            value: ExifValue::Undefined(vec![2, 3, 0, 0]),
        });

        // Latitude
        let lat_ref = if lat >= 0.0 { "N" } else { "S" };
        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_LATITUDE_REF,
            value: ExifValue::Ascii(lat_ref.to_string()),
        });

        let lat_abs = lat.abs();
        let lat_deg = lat_abs.floor() as u32;
        let lat_min = ((lat_abs - lat_deg as f64) * 60.0).floor() as u32;
        let lat_sec = ((lat_abs - lat_deg as f64 - lat_min as f64 / 60.0) * 3600.0 * 100.0) as u32;

        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_LATITUDE,
            value: ExifValue::Rationals(vec![(lat_deg, 1), (lat_min, 1), (lat_sec, 100)]),
        });

        // Longitude
        let lon_ref = if lon >= 0.0 { "E" } else { "W" };
        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_LONGITUDE_REF,
            value: ExifValue::Ascii(lon_ref.to_string()),
        });

        let lon_abs = lon.abs();
        let lon_deg = lon_abs.floor() as u32;
        let lon_min = ((lon_abs - lon_deg as f64) * 60.0).floor() as u32;
        let lon_sec = ((lon_abs - lon_deg as f64 - lon_min as f64 / 60.0) * 3600.0 * 100.0) as u32;

        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_LONGITUDE,
            value: ExifValue::Rationals(vec![(lon_deg, 1), (lon_min, 1), (lon_sec, 100)]),
        });

        // Altitude (optional)
        if let Some(altitude) = alt {
            self.gps_entries.push(ExifEntry {
                tag: exif_tags::GPS_ALTITUDE_REF,
                value: ExifValue::Short(0), // 0 = above sea level
            });

            let alt_num = (altitude.abs() * 1000.0) as u32;
            self.gps_entries.push(ExifEntry {
                tag: exif_tags::GPS_ALTITUDE,
                value: ExifValue::Rational(alt_num, 1000),
            });
        }
    }

    fn add_bearing(&mut self, bearing: f64) {
        let bearing_num = (bearing * 100.0) as u32;

        // GPS Image Direction
        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_IMG_DIRECTION_REF,
            value: ExifValue::Ascii("T".to_string()), // True North
        });

        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_IMG_DIRECTION,
            value: ExifValue::Rational(bearing_num, 100),
        });

        // GPS Destination Bearing (same value)
        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_DEST_BEARING_REF,
            value: ExifValue::Ascii("T".to_string()), // True North
        });

        self.gps_entries.push(ExifEntry {
            tag: exif_tags::GPS_DEST_BEARING,
            value: ExifValue::Rational(bearing_num, 100),
        });
    }

    fn add_provenance(&mut self, location_source: &str, bearing_source: &str) {
        let provenance = ProvenanceData {
            location_source: location_source.to_string(),
            bearing_source: bearing_source.to_string(),
        };

        if let Ok(provenance_json) = serde_json::to_string(&provenance) {
            let mut user_comment = b"ASCII\0\0\0".to_vec(); // Character code

            // Limit size to prevent EXIF issues
            const MAX_COMMENT_SIZE: usize = 1000;
            let comment_bytes = if provenance_json.len() > MAX_COMMENT_SIZE {
                info!("Warning: Provenance data too long, truncating");
                &provenance_json.as_bytes()[..MAX_COMMENT_SIZE]
            } else {
                provenance_json.as_bytes()
            };

            user_comment.extend_from_slice(comment_bytes);
            self.user_comment = Some(user_comment);
        }
    }

    fn build(mut self) -> Vec<u8> {
        // Sort entries by tag for proper EXIF format
        self.ifd0_entries.sort_by_key(|e| e.tag);
        self.gps_entries.sort_by_key(|e| e.tag);

        let mut exif_data = Vec::new();

        // TIFF header (little-endian)
        exif_data.extend_from_slice(&[0x49, 0x49]); // II
        exif_data.extend_from_slice(&[0x2A, 0x00]); // 42
        exif_data.extend_from_slice(&[0x08, 0x00, 0x00, 0x00]); // IFD0 offset

        // Calculate IFD0 entries (including GPS pointer and UserComment)
        let mut ifd0_entry_count = self.ifd0_entries.len() as u16;

        // Add GPS IFD pointer if we have GPS data
        let has_gps = !self.gps_entries.is_empty();
        if has_gps {
            ifd0_entry_count += 1;
        }

        // Add UserComment if we have it
        let has_user_comment = self.user_comment.is_some();
        if has_user_comment {
            ifd0_entry_count += 1;
        }

        // Write IFD0
        exif_data.extend_from_slice(&ifd0_entry_count.to_le_bytes());

        // Calculate offsets dynamically
        let ifd0_base = 8;
        let ifd0_size = 2 + (ifd0_entry_count as u32 * 12) + 4; // count + entries + next IFD
        let gps_ifd_offset = ifd0_base + ifd0_size;

        // Write IFD0 entries
        for entry in &self.ifd0_entries {
            self.write_ifd_entry(&mut exif_data, entry, gps_ifd_offset);
        }

        // Write GPS IFD pointer
        if has_gps {
            exif_data.extend_from_slice(&exif_tags::GPS_IFD_POINTER.to_le_bytes());
            exif_data.extend_from_slice(&[0x04, 0x00]); // Type: LONG
            exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
            exif_data.extend_from_slice(&gps_ifd_offset.to_le_bytes());
        }

        // Write UserComment entry if needed
        if let Some(ref comment) = self.user_comment {
            exif_data.extend_from_slice(&exif_tags::USER_COMMENT.to_le_bytes());
            exif_data.extend_from_slice(&[0x07, 0x00]); // Type: UNDEFINED
            exif_data.extend_from_slice(&(comment.len() as u32).to_le_bytes());

            if comment.len() <= 4 {
                let mut padded = comment.clone();
                padded.resize(4, 0);
                exif_data.extend_from_slice(&padded);
            } else {
                // Calculate offset for comment data (after GPS data)
                let gps_size = if has_gps {
                    2 + (self.gps_entries.len() as u32 * 12) + 4 + self.calculate_gps_data_size()
                } else { 0 };
                let comment_offset = gps_ifd_offset + gps_size;
                exif_data.extend_from_slice(&comment_offset.to_le_bytes());
            }
        }

        // Next IFD offset (none)
        exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);

        // Write GPS IFD if needed
        if has_gps {
            // Pad to GPS IFD offset
            while exif_data.len() < gps_ifd_offset as usize {
                exif_data.push(0x00);
            }

            // Write GPS entries
            exif_data.extend_from_slice(&(self.gps_entries.len() as u16).to_le_bytes());

            let gps_data_offset = gps_ifd_offset + 2 + (self.gps_entries.len() as u32 * 12) + 4;
            let mut current_data_offset = gps_data_offset;

            for entry in &self.gps_entries {
                current_data_offset = self.write_gps_entry(&mut exif_data, entry, current_data_offset);
            }

            // GPS IFD next pointer
            exif_data.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]);

            // Write GPS data values
            self.write_gps_data_values(&mut exif_data, gps_data_offset);
        }

        // Write UserComment data if it's stored by offset
        if let Some(ref comment) = self.user_comment {
            if comment.len() > 4 {
                let gps_size = if has_gps {
                    2 + (self.gps_entries.len() as u32 * 12) + 4 + self.calculate_gps_data_size()
                } else { 0 };
                let comment_offset = gps_ifd_offset + gps_size;

                // Pad to comment offset
                while exif_data.len() < comment_offset as usize {
                    exif_data.push(0x00);
                }
                exif_data.extend_from_slice(comment);
            }
        }

        info!("🢄Created structured EXIF: {} bytes", exif_data.len());
        exif_data
    }

    fn write_ifd_entry(&self, exif_data: &mut Vec<u8>, entry: &ExifEntry, _base_offset: u32) {
        exif_data.extend_from_slice(&entry.tag.to_le_bytes());

        match &entry.value {
            ExifValue::Short(val) => {
                exif_data.extend_from_slice(&[0x03, 0x00]); // Type: SHORT
                exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
                exif_data.extend_from_slice(&val.to_le_bytes());
                exif_data.extend_from_slice(&[0x00, 0x00]); // Padding
            }
            ExifValue::Ascii(val) => {
                let bytes = val.as_bytes();
                let count = bytes.len() + 1; // Include null terminator
                exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
                exif_data.extend_from_slice(&(count as u32).to_le_bytes());

                if count <= 4 {
                    let mut padded = bytes.to_vec();
                    padded.push(0); // Null terminator
                    padded.resize(4, 0);
                    exif_data.extend_from_slice(&padded);
                } else {
                    // For longer strings, we'd need to handle offsets
                    // For now, truncate to fit in 4 bytes
                    let mut truncated = bytes[..3.min(bytes.len())].to_vec();
                    truncated.push(0);
                    truncated.resize(4, 0);
                    exif_data.extend_from_slice(&truncated);
                }
            }
            _ => {
                // Handle other types as needed
                exif_data.extend_from_slice(&[0x00; 8]); // Placeholder
            }
        }
    }

    fn write_gps_entry(&self, exif_data: &mut Vec<u8>, entry: &ExifEntry, mut data_offset: u32) -> u32 {
        exif_data.extend_from_slice(&entry.tag.to_le_bytes());

        match &entry.value {
            ExifValue::Undefined(val) => {
                exif_data.extend_from_slice(&[0x01, 0x00]); // Type: BYTE
                exif_data.extend_from_slice(&(val.len() as u32).to_le_bytes());
                if val.len() <= 4 {
                    let mut padded = val.clone();
                    padded.resize(4, 0);
                    exif_data.extend_from_slice(&padded);
                } else {
                    exif_data.extend_from_slice(&data_offset.to_le_bytes());
                    data_offset += val.len() as u32;
                }
            }
            ExifValue::Ascii(val) => {
                let bytes = val.as_bytes();
                let count = bytes.len() + 1;
                exif_data.extend_from_slice(&[0x02, 0x00]); // Type: ASCII
                exif_data.extend_from_slice(&(count as u32).to_le_bytes());

                if count <= 4 {
                    let mut padded = bytes.to_vec();
                    padded.push(0);
                    padded.resize(4, 0);
                    exif_data.extend_from_slice(&padded);
                } else {
                    exif_data.extend_from_slice(&data_offset.to_le_bytes());
                    data_offset += count as u32;
                }
            }
            ExifValue::Short(val) => {
                exif_data.extend_from_slice(&[0x03, 0x00]); // Type: SHORT
                exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
                exif_data.extend_from_slice(&val.to_le_bytes());
                exif_data.extend_from_slice(&[0x00, 0x00]);
            }
            ExifValue::Rational(_, _) => {
                exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
                exif_data.extend_from_slice(&[0x01, 0x00, 0x00, 0x00]); // Count: 1
                exif_data.extend_from_slice(&data_offset.to_le_bytes());
                data_offset += 8;
            }
            ExifValue::Rationals(vals) => {
                exif_data.extend_from_slice(&[0x05, 0x00]); // Type: RATIONAL
                exif_data.extend_from_slice(&(vals.len() as u32).to_le_bytes());
                exif_data.extend_from_slice(&data_offset.to_le_bytes());
                data_offset += (vals.len() as u32) * 8;
            }
            _ => {
                exif_data.extend_from_slice(&[0x00; 8]); // Placeholder
            }
        }

        data_offset
    }

    fn write_gps_data_values(&self, exif_data: &mut Vec<u8>, mut _offset: u32) {
        for entry in &self.gps_entries {
            match &entry.value {
                ExifValue::Rational(num, denom) => {
                    exif_data.extend_from_slice(&num.to_le_bytes());
                    exif_data.extend_from_slice(&denom.to_le_bytes());
                }
                ExifValue::Rationals(vals) => {
                    for (num, denom) in vals {
                        exif_data.extend_from_slice(&num.to_le_bytes());
                        exif_data.extend_from_slice(&denom.to_le_bytes());
                    }
                }
                ExifValue::Undefined(val) if val.len() > 4 => {
                    exif_data.extend_from_slice(val);
                }
                ExifValue::Ascii(val) if val.len() + 1 > 4 => {
                    exif_data.extend_from_slice(val.as_bytes());
                    exif_data.push(0); // Null terminator
                }
                _ => {} // Data already written inline
            }
        }
    }

    fn calculate_gps_data_size(&self) -> u32 {
        let mut size = 0u32;
        for entry in &self.gps_entries {
            match &entry.value {
                ExifValue::Rational(_, _) => size += 8,
                ExifValue::Rationals(vals) => size += (vals.len() as u32) * 8,
                ExifValue::Undefined(val) if val.len() > 4 => size += val.len() as u32,
                ExifValue::Ascii(val) if val.len() + 1 > 4 => size += val.len() as u32 + 1,
                _ => {} // Data stored inline
            }
        }
        size
    }
}

#[cfg(target_os = "android")]
pub fn create_exif_segment_structured(metadata: &PhotoMetadata) -> Vec<u8> {
    info!(
        "Creating structured EXIF for: lat={}, lon={}, alt={:?}, bearing={:?}, orientation={:?}",
        metadata.latitude, metadata.longitude, metadata.altitude, metadata.bearing, metadata.orientation_code
    );

    let mut builder = ExifBuilder::new();

    // Add orientation if provided
    if let Some(orientation) = metadata.orientation_code {
        builder.add_orientation(orientation);
    }

    // Add timestamps
    builder.add_timestamps(metadata.captured_at);

    // Add GPS data
    builder.add_gps_data(metadata.latitude, metadata.longitude, metadata.altitude);

    // Add bearing if provided
    if let Some(bearing) = metadata.bearing {
        builder.add_bearing(bearing);
    }

    // Add provenance data
    builder.add_provenance(&metadata.location_source, &metadata.bearing_source);

    builder.build()
}

/**
 * Validate and normalize EXIF orientation value
 * Ensures only valid EXIF orientation values (1, 3, 6, 8) are used
 */
pub fn validate_orientation_code(code: Option<u16>) -> u16 {
    match code {
        Some(1) | Some(3) | Some(6) | Some(8) => code.unwrap(),
        Some(invalid) => {
            warn!("Invalid EXIF orientation code: {}, defaulting to 1 (normal)", invalid);
            1
        }
        None => {
            info!("No orientation code provided, defaulting to 1 (normal)");
            1
        }
    }
}

/**
 * Validate PhotoMetadata and sanitize values
 * Ensures all metadata values are within acceptable ranges
 */
pub fn validate_photo_metadata(mut metadata: PhotoMetadata) -> PhotoMetadata {
    // Validate orientation
    metadata.orientation_code = Some(validate_orientation_code(metadata.orientation_code));

    // Validate latitude/longitude ranges
    if metadata.latitude < -90.0 || metadata.latitude > 90.0 {
        warn!("Invalid latitude: {}, clamping to valid range", metadata.latitude);
        metadata.latitude = metadata.latitude.clamp(-90.0, 90.0);
    }

    if metadata.longitude < -180.0 || metadata.longitude > 180.0 {
        warn!("Invalid longitude: {}, normalizing to valid range", metadata.longitude);
        // Normalize longitude to -180 to 180 range
        metadata.longitude = ((metadata.longitude + 180.0) % 360.0) - 180.0;
    }

    // Validate bearing range (0-360)
    if let Some(bearing) = metadata.bearing {
        if bearing < 0.0 || bearing >= 360.0 {
            warn!("Invalid bearing: {}, normalizing to 0-360 range", bearing);
            metadata.bearing = Some(((bearing % 360.0) + 360.0) % 360.0);
        }
    }

    // Validate timestamp (reasonable range: 1970 to 2100)
    let min_timestamp = 0i64; // 1970-01-01
    let max_timestamp = 4102444800000i64; // 2100-01-01 in milliseconds
    if metadata.captured_at < min_timestamp || metadata.captured_at > max_timestamp {
        warn!("Invalid captured_at: {}", metadata.captured_at);
    }

    // Validate accuracy (should be positive)
    if metadata.accuracy < 0.0 {
        warn!("Invalid accuracy: {}, setting to 0", metadata.accuracy);
        metadata.accuracy = 0.0;
    }

    // Validate altitude (reasonable range: -500m to 10000m)
    if let Some(altitude) = metadata.altitude {
        if altitude < -500.0 || altitude > 10000.0 {
            warn!("Suspicious altitude: {} meters, keeping but flagging", altitude);
            // Keep the value but log it - could be valid in extreme cases
        }
    }

    metadata
}

#[allow(dead_code)]
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

#[allow(dead_code)]
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

/*
#[allow(dead_code)]
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
*/

/// Debug function to verify EXIF data can be read back from saved photos
/// Available in debug builds for troubleshooting EXIF issues
#[cfg(debug_assertions)]
pub async fn verify_exif_in_saved_file(file_path: &std::path::Path, expected_metadata: &PhotoMetadata) {

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
				"✅ EXIF Verification SUCCESS: lat={}, lon={}, alt={:?}, bearing={:?}, orientation={:?}, location_source={}, bearing_source={}",
				read_metadata.latitude,
				read_metadata.longitude,
				read_metadata.altitude,
				read_metadata.bearing,
				read_metadata.orientation_code,
				read_metadata.location_source,
				read_metadata.bearing_source
			);

			// Verify key values match expectations
			let lat_diff = (read_metadata.latitude - expected_metadata.latitude).abs();
			let lon_diff = (read_metadata.longitude - expected_metadata.longitude).abs();

			if lat_diff > 0.000001 {
				warn!("❌ EXIF MISMATCH: Latitude expected={}, read={}, diff={}",
					expected_metadata.latitude, read_metadata.latitude, lat_diff);
			}

			if lon_diff > 0.000001 {
				warn!("❌ EXIF MISMATCH: Longitude expected={}, read={}, diff={}",
					expected_metadata.longitude, read_metadata.longitude, lon_diff);
			}

			if read_metadata.orientation_code != expected_metadata.orientation_code {
				warn!("❌ EXIF MISMATCH: Orientation expected={:?}, read={:?}",
					expected_metadata.orientation_code, read_metadata.orientation_code);
			}

			if let (Some(expected_bearing), Some(read_bearing)) = (expected_metadata.bearing, read_metadata.bearing) {
				let bearing_diff = (read_bearing - expected_bearing).abs();
				if bearing_diff > 0.1 {
					warn!("❌ EXIF MISMATCH: Bearing expected={}, read={}, diff={}",
						expected_bearing, read_bearing, bearing_diff);
				}
			}

			if read_metadata.location_source != expected_metadata.location_source {
				warn!("❌ EXIF MISMATCH: Location source expected='{}', read='{}'",
					expected_metadata.location_source, read_metadata.location_source);
			}

			if read_metadata.bearing_source != expected_metadata.bearing_source {
				warn!("❌ EXIF MISMATCH: Bearing source expected='{}', read='{}'",
					expected_metadata.bearing_source, read_metadata.bearing_source);
			}
		}
		Err(e) => {
			warn!("🢄❌ EXIF VERIFICATION FAILED: Could not read EXIF after save: {}", e);
		}
	}
}

#[cfg(debug_assertions)]
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
		captured_at: 0,
		accuracy: 0.0,
		location_source: "unknown".to_string(),
		bearing_source: "unknown".to_string(),
		orientation_code: None,
	};

	// Read orientation
	if let Some(orientation_field) = exif_reader.get_field(exif::Tag::Orientation, exif::In::PRIMARY) {
		if let exif::Value::Short(ref orientation_vals) = &orientation_field.value {
			if !orientation_vals.is_empty() {
				metadata.orientation_code = Some(orientation_vals[0]);
				info!("🢄EXIF orientation: {}", orientation_vals[0]);
			}
		}
	}

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
					metadata.captured_at = dt.and_utc().timestamp();
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


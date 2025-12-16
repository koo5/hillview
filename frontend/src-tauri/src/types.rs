use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PhotoMetadata {
	pub latitude: f64,
	pub longitude: f64,
	pub altitude: Option<f64>,
	pub bearing: Option<f64>,
	pub captured_at: i64,
	pub accuracy: f64,
	pub location_source: String,
	pub bearing_source: String,
	pub orientation_code: Option<u16>, // EXIF orientation value (1, 3, 6, 8)
}

use serde::{Deserialize, Serialize};

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

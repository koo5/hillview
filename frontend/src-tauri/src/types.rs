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
	// Background-tracking alternative location: when the photo was captured with
	// a manual (panned) primary location while background GPS was still running,
	// the live GPS fix is carried here and written ONLY into the EXIF UserComment
	// (never into the primary GPS tags or the Android DB row). Lets a reviewer
	// later promote it to the primary location server-side. None for normal captures.
	#[serde(default, skip_serializing_if = "Option::is_none")]
	pub alt_location: Option<AltLocation>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct AltLocation {
	pub lat: f64,
	pub lng: f64,
	pub ts: i64,
	pub accuracy: Option<f64>,
	pub source: String, // e.g. "gps-background"
}

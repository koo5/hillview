/// Shared photo types between main app and plugin
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DevicePhotoMetadata {
    pub id: String,
    pub filename: String,
    pub path: String,
    #[serde(flatten)]
    pub metadata: PhotoMetadata,
    pub width: u32,
    pub height: u32,
    pub file_size: u64,
    pub created_at: i64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub file_hash: Option<String>,
}

impl DevicePhotoMetadata {
    /// Helper to access metadata fields directly
    pub fn latitude(&self) -> f64 { self.metadata.latitude }
    pub fn longitude(&self) -> f64 { self.metadata.longitude }
    pub fn altitude(&self) -> Option<f64> { self.metadata.altitude }
    pub fn bearing(&self) -> Option<f64> { self.metadata.bearing }
    pub fn capturedAt(&self) -> i64 { self.metadata.timestamp }
    pub fn accuracy(&self) -> f64 { self.metadata.accuracy }
}

/// Response from Android addPhotoToDatabase command
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AddPhotoResponse {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub photo_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PingRequest {
  pub value: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PingResponse {
  pub value: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SensorData {
  pub magnetic_heading: f32,
  pub true_heading: f32,
  pub heading_accuracy: f32,
  pub pitch: f32,
  pub roll: f32,
  pub timestamp: u64,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocationUpdate {
  pub latitude: f64,
  pub longitude: f64,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AutoUploadResponse {
  pub success: bool,
  pub enabled: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UploadStatusResponse {
  pub auto_upload_enabled: bool,
  pub auto_upload_prompt_enabled: bool,
  pub pending_uploads: i32,
  pub failed_uploads: i32,
  pub error: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UploadConfig {
  pub server_url: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BasicResponse {
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PhotoUploadResponse {
  pub success: bool,
  pub photo_id: String,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AuthTokenResponse {
  pub token: Option<String>,
  pub expires_at: Option<String>,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DevicePhotosResponse {
  pub photos: Vec<serde_json::Value>,
  pub last_updated: i64,  // This will be renamed to lastUpdated by serde
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PhotoScanResponse {
  pub photos_added: i32,
  pub scan_errors: i32,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct FileImportResponse {
  pub success: bool,
  pub selected_files: Vec<String>,
  pub imported_count: i32,
  pub failed_count: Option<i32>,
  pub failed_files: Option<Vec<String>>,
  pub import_errors: Option<Vec<String>>,
  pub scan_result: Option<serde_json::Value>,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PhotoWorkerResponse {
  pub success: bool,
  pub response_json: Option<String>,
  pub error: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BearingLookupResponse {
  pub success: bool,
  pub found: Option<bool>,
  pub magnetic_heading: Option<f64>,
  pub true_heading: Option<f64>,
  pub accuracy: Option<i32>,
  pub source: Option<String>,
  pub pitch: Option<f64>,
  pub roll: Option<f64>,
  pub timestamp: Option<i64>,
  pub error: Option<String>,
}

// Push Notification Models

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PushDistributorInfo {
  pub package_name: String,
  pub display_name: String,
  pub is_available: bool,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PushDistributorsResponse {
  pub distributors: Vec<PushDistributorInfo>,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PushRegistrationStatusResponse {
  pub status: String, // "not_configured", "registered", "distributor_missing", "registration_failed", "disabled"
  pub status_message: String,
  pub selected_distributor: Option<String>,
  pub push_endpoint: Option<String>,
  pub last_error: Option<String>,
  pub push_enabled: bool,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SelectDistributorRequest {
  pub package_name: String, // Empty string means "disabled"
}


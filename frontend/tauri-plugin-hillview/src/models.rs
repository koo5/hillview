use serde::{Deserialize, Serialize};
use tauri::plugin::PermissionState;

#[derive(Debug, Deserialize, Serialize)]
pub struct PingRequest {
  pub value: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct PingResponse {
  pub value: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SensorData {
  pub magnetic_heading: f32,
  pub true_heading: f32,
  pub heading_accuracy: f32,
  pub pitch: f32,
  pub roll: f32,
  pub timestamp: u64,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct LocationUpdate {
  pub latitude: f64,
  pub longitude: f64,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct AutoUploadResponse {
  pub success: bool,
  pub enabled: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct UploadStatusResponse {
  pub auto_upload_enabled: bool,
  pub auto_upload_prompt_enabled: bool,
  pub pending_uploads: i32,
  pub failed_uploads: i32,
  pub error: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct UploadConfig {
  pub server_url: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct BasicResponse {
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct PhotoUploadResponse {
  pub success: bool,
  pub photo_id: String,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct AuthTokenResponse {
  pub token: Option<String>,
  pub expires_at: Option<String>,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct DevicePhotosResponse {
  pub photos: Vec<serde_json::Value>,
  pub last_updated: i64,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct PhotoScanResponse {
  pub photos_added: i32,
  pub scan_errors: i32,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
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
pub struct PhotoWorkerResponse {
  pub success: bool,
  pub response_json: Option<String>,
  pub error: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
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
pub struct PushDistributorInfo {
  pub package_name: String,
  pub display_name: String,
  pub is_available: bool,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct PushDistributorsResponse {
  pub distributors: Vec<PushDistributorInfo>,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
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
pub struct SelectDistributorRequest {
  pub package_name: String, // Empty string means "disabled"
}

// Notification Models

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct PermissionResponse {
  pub granted: bool,
  pub success: bool,
  pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct NotificationSettingsResponse {
  pub enabled: bool,
  pub success: bool,
  pub error: Option<String>,
}

// Permission-related models

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TauriPermissionResponse {
  pub post_notification: PermissionState,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize)]
pub struct TauriPermissionStringResponse {
  pub post_notification: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RequestPermission {
  pub post_notification: bool,
}


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
  pub pending_uploads: i32,
  pub failed_uploads: i32,
  pub error: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UploadConfig {
  pub server_url: Option<String>,
  pub auth_token: Option<String>,
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

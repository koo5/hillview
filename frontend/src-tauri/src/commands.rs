use log::info;
use tauri::AppHandle;
use serde::Serialize;
// Remove unused serde imports since we're using types from plugin
// Removed unused imports: AppHandle, Runtime

const GIT_HASH: &str = env!("GIT_HASH");
const GIT_BRANCH: &str = env!("GIT_BRANCH");
const BUILD_TIME: &str = env!("BUILD_TIME");

#[tauri::command]
pub fn log(message: String) {
	info!("🢄{}", message);
}

#[tauri::command]
pub fn get_build_commit_hash() -> String {
	GIT_HASH.to_string()
}

#[tauri::command]
pub fn get_build_branch() -> String {
	GIT_BRANCH.to_string()
}

#[tauri::command]
pub fn get_build_ts() -> String {
	BUILD_TIME.to_string()
}

#[tauri::command]
pub fn is_debug_mode() -> bool {
	cfg!(debug_assertions)
}

#[derive(Serialize)]
pub struct NativeCameraResult {
	pub success: bool,
	pub photo_id: Option<String>,
	pub error: Option<String>,
}

#[cfg(mobile)]
#[tauri::command]
pub async fn take_native_photo(app: AppHandle) -> NativeCameraResult {
	use tauri_plugin_camera::CameraExt;

	info!("🢄 take_native_photo: Starting native camera capture");

	match app.camera().take_picture() {
		Ok(response) => {
			info!("🢄 take_native_photo: Got photo {}x{}", response.width, response.height);

			// TODO: Get current location from Kotlin plugin
			// TODO: Process image through save_photo_from_bytes pipeline
			// For now, just return success to test the camera plugin works

			NativeCameraResult {
				success: true,
				photo_id: Some(format!("native_{}", chrono::Utc::now().timestamp_millis())),
				error: None,
			}
		}
		Err(e) => {
			info!("🢄 take_native_photo: Error - {:?}", e);
			NativeCameraResult {
				success: false,
				photo_id: None,
				error: Some(format!("{:?}", e)),
			}
		}
	}
}

#[cfg(not(mobile))]
#[tauri::command]
pub async fn take_native_photo(_app: AppHandle) -> NativeCameraResult {
	info!("🢄 take_native_photo: Not available on desktop");
	NativeCameraResult {
		success: false,
		photo_id: None,
		error: Some("Native camera not available on desktop".to_string()),
	}
}

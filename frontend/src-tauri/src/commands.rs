use log::info;
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

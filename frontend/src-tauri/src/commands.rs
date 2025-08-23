use log::info;
// Remove unused serde imports since we're using types from plugin
use tauri::{AppHandle, Runtime};
use std::sync::Mutex;

const GIT_HASH: &str = env!("GIT_HASH");
const GIT_BRANCH: &str = env!("GIT_BRANCH");
const BUILD_TIME: &str = env!("BUILD_TIME");

// Permission mutex for ensuring only one permission dialog at a time
static PERMISSION_MUTEX: Mutex<Option<String>> = Mutex::new(None);

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

// Authentication data structures
// Re-export types from plugin to avoid duplication
pub use tauri_plugin_hillview::{BasicResponse, AuthTokenResponse};

// Authentication Commands

#[tauri::command]
#[allow(unused_variables)]
pub async fn store_auth_token<R: Runtime>(
    app: AppHandle<R>,
    token: String,
    expires_at: String,
) -> Result<BasicResponse, String> {
    #[cfg(target_os = "android")]
    {
        use tauri_plugin_hillview::HillviewExt;
        match app.hillview().store_auth_token(token, expires_at) {
            Ok(response) => Ok(response),
            Err(e) => Err(format!("Failed to store auth token: {}", e)),
        }
    }
    
    #[cfg(not(target_os = "android"))]
    {
        // For non-Android platforms, we could use secure storage or just return success
        // For now, just return success for web/desktop
        Ok(BasicResponse {
            success: true,
            error: None,
        })
    }
}

#[tauri::command]
#[allow(unused_variables)]
pub async fn get_auth_token<R: Runtime>(
    app: AppHandle<R>,
) -> Result<AuthTokenResponse, String> {
    #[cfg(target_os = "android")]
    {
        use tauri_plugin_hillview::HillviewExt;
        match app.hillview().get_auth_token() {
            Ok(response) => Ok(response),
            Err(e) => Err(format!("Failed to get auth token: {}", e)),
        }
    }
    
    #[cfg(not(target_os = "android"))]
    {
        // For non-Android platforms, return no token
        Ok(AuthTokenResponse {
            token: None,
            expires_at: None,
            success: true,
            error: None,
        })
    }
}

#[tauri::command]
#[allow(unused_variables)]
pub async fn clear_auth_token<R: Runtime>(
    app: AppHandle<R>,
) -> Result<BasicResponse, String> {
    #[cfg(target_os = "android")]
    {
        use tauri_plugin_hillview::HillviewExt;
        match app.hillview().clear_auth_token() {
            Ok(response) => Ok(response),
            Err(e) => Err(format!("Failed to clear auth token: {}", e)),
        }
    }
    
    #[cfg(not(target_os = "android"))]
    {
        // For non-Android platforms, just return success
        Ok(BasicResponse {
            success: true,
            error: None,
        })
    }
}

// Permission Mutex Commands

#[tauri::command]
pub fn acquire_permission_lock(requester: String) -> bool {
    info!("🢄Permission lock request from: {}", requester);
    let mut guard = PERMISSION_MUTEX.lock().unwrap();
    if guard.is_none() {
        *guard = Some(requester.clone());
        info!("🢄Permission lock acquired by: {}", requester);
        true
    } else {
        let holder = guard.as_ref().unwrap();
        info!("🢄Permission lock denied to {}, currently held by: {}", requester, holder);
        false
    }
}

#[tauri::command]
pub fn release_permission_lock(requester: String) -> Result<(), String> {
    info!("🢄Permission lock release request from: {}", requester);
    let mut guard = PERMISSION_MUTEX.lock().unwrap();
    match guard.as_ref() {
        Some(holder) if holder == &requester => {
            *guard = None;
            info!("🢄Permission lock released by: {}", requester);
            Ok(())
        }
        Some(holder) => {
            let error = format!("Lock held by {}, not {}", holder, requester);
            info!("🢄Permission lock release failed: {}", error);
            Err(error)
        }
        None => {
            let error = "No lock held".to_string();
            info!("🢄Permission lock release failed: {}", error);
            Err(error)
        }
    }
}

#[tauri::command]
pub fn get_permission_lock_holder() -> Option<String> {
    let guard = PERMISSION_MUTEX.lock().unwrap();
    let holder = guard.clone();
    if let Some(ref h) = holder {
        info!("🢄Permission lock currently held by: {}", h);
    } else {
        info!("🢄Permission lock is available");
    }
    holder
}

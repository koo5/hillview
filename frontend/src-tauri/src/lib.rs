mod commands;
mod device_photos;
mod photo_exif;
use log::info;
#[cfg(debug_assertions)]
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    //setup_logging();
    info!("🢄Starting application");

    // Print Android-specific info for debugging
    #[cfg(target_os = "android")]
    {
        info!("🢄Running on Android");
        info!("🢄Android environment info:");
        if let Ok(home) = std::env::var("HOME") {
            info!("🢄HOME: {}", home);
        }
        if let Ok(path) = std::env::var("PATH") {
            info!("🢄PATH: {}", path);
        }
        info!("🢄Current dir: {:?}", std::env::current_dir());
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_hillview::init())
        .invoke_handler(tauri::generate_handler![
            commands::log,
            commands::is_debug_mode,
            commands::get_build_commit_hash,
            commands::get_build_branch,
            commands::get_build_ts,
            commands::store_auth_token,
            commands::get_auth_token,
            commands::clear_auth_token,
            commands::acquire_permission_lock,
            commands::release_permission_lock,
            commands::get_permission_lock_holder,
            photo_exif::embed_photo_metadata,
            photo_exif::save_photo_with_metadata,
            photo_exif::read_device_photo,
            photo_exif::read_photo_exif,
            device_photos::load_device_photos_db,
            device_photos::save_device_photos_db,
            device_photos::add_device_photo_to_db,
            device_photos::refresh_device_photos,
            device_photos::delete_device_photo
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                // Only initialize log plugin if logger hasn't been set yet
                // This prevents crashes when the process persists but Activity restarts
                match app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Debug)
                        .build(),
                ) {
                    Ok(_) => info!("🢄Log plugin initialized successfully"),
                    Err(e) => {
                        // Logger already initialized, this is expected on Activity restart
                        info!("🢄Log plugin already initialized (process persisted): {}", e);
                    }
                }
            }

            #[cfg(debug_assertions)]
            {
                let do_open_devtools = std::env::var("TAURI_OPEN_DEVTOOLS")
                    .map(|v| v.eq_ignore_ascii_case("true"))
                    .unwrap_or(false);
                if do_open_devtools {
                    if let Some(main_window) = app.get_webview_window("main") {
                        main_window.open_devtools();
                    }
                }
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

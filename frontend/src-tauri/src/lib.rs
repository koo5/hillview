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
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
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
            photo_exif::embed_photo_metadata,
            photo_exif::store_photo_chunk,
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
            // Tauri log plugin disabled to prevent duplicate console logs
            // (JavaScript console already visible in WebView, Sentry handles errors)
            if cfg!(debug_assertions) {
                info!("🢄Debug mode enabled, console logs available in WebView");
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

            // Suppress unused variable warning in release mode
            #[cfg(not(debug_assertions))]
            {
                let _ = app;
            }

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

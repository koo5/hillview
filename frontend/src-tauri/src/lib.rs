mod commands;
mod photo_exif;
mod device_photos;
mod sensor_plugin;
use log::info;

/*
fn setup_logging() {
    #[cfg(target_os = "android")]
    {
        use android_logger::Config as AndroidConfig;
        android_logger::init_once(
            AndroidConfig::default()
                .with_max_level(LevelFilter::Debug)
                .with_tag("hillview")
        );

        // Log several messages at different levels for testing
        log::trace!("TRACE: Android logging initialized with YellowApp tag");
        log::debug!("DEBUG: Android logging initialized with YellowApp tag");
        log::info!("INFO: Android logging initialized with YellowApp tag");
        log::warn!("WARN: Android logging initialized with YellowApp tag");
        log::error!("ERROR: Android logging initialized with YellowApp tag");
    }

    #[cfg(not(target_os = "android"))]
    {
        env_logger::Builder::new()
            .filter_level(LevelFilter::Debug)
            //add milliseconds to the logs
            .format_timestamp(Some(env_logger::fmt::TimestampPrecision::Millis))
            .init();
        info!("Desktop logging initialized");
    }
}
*/

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {

    //setup_logging();
    info!("Starting application");

    // Print Android-specific info for debugging
    #[cfg(target_os = "android")]
    {
        info!("Running on Android");
        info!("Android environment info:");
        if let Ok(home) = std::env::var("HOME") {
            info!("HOME: {}", home);
        }
        if let Ok(path) = std::env::var("PATH") {
            info!("PATH: {}", path);
        }
        info!("Current dir: {:?}", std::env::current_dir());
   }
  tauri::Builder::default()
    .plugin(tauri_plugin_geolocation::init())
    .plugin(tauri_plugin_fs::init())
    .plugin(sensor_plugin::init())
    .invoke_handler(tauri::generate_handler![
            commands::log,
            commands::is_debug_mode,
            commands::get_build_commit_hash,
            commands::get_build_branch,
            commands::get_build_ts,
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
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Debug)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

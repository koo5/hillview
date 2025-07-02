mod photo_exif;
mod device_photos;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_geolocation::init())
    .plugin(tauri_plugin_fs::init())
    .invoke_handler(tauri::generate_handler![
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
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

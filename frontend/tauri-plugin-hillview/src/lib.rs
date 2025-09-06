use tauri::{
  plugin::{Builder, TauriPlugin},
  Manager, Runtime,
};

pub use models::*;

#[cfg(desktop)]
mod desktop;
#[cfg(mobile)]
mod mobile;

mod commands;
mod error;
mod models;

pub use error::{Error, Result};

#[cfg(desktop)]
use desktop::Hillview;
#[cfg(mobile)]
use mobile::Hillview;

/// Extensions to [`tauri::App`], [`tauri::AppHandle`] and [`tauri::Window`] to access the hillview APIs.
pub trait HillviewExt<R: Runtime> {
  fn hillview(&self) -> &Hillview<R>;
}

impl<R: Runtime, T: Manager<R>> crate::HillviewExt<R> for T {
  fn hillview(&self) -> &Hillview<R> {
    self.state::<Hillview<R>>().inner()
  }
}

/// Initializes the plugin.
pub fn init<R: Runtime>() -> TauriPlugin<R> {
  Builder::new("hillview")
    .invoke_handler(tauri::generate_handler![
      commands::ping,
      commands::start_sensor,
      commands::stop_sensor,
      commands::update_sensor_location,
      commands::start_precise_location_listener,
      commands::stop_precise_location_listener,
      commands::set_auto_upload_enabled,
      commands::get_upload_status,
      commands::set_upload_config,
      commands::upload_photo,
      commands::retry_failed_uploads,
      // Authentication commands
      commands::store_auth_token,
      commands::get_auth_token,
      commands::clear_auth_token,
      // Photo database bridge commands
      commands::get_device_photos,
      commands::refresh_photo_scan,
      commands::import_photos,
      ])
    .setup(|app, api| {
      #[cfg(mobile)]
      let hillview = mobile::init(app, api)?;
      #[cfg(desktop)]
      let hillview = desktop::init(app, api)?;
      app.manage(hillview);
      Ok(())
    })
    .build()
}

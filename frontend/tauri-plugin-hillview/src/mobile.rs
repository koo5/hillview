use serde::de::DeserializeOwned;
use tauri::{
  plugin::{PluginApi, PluginHandle},
  AppHandle, Runtime,
};

use crate::models::*;

#[cfg(target_os = "ios")]
tauri::ios_plugin_binding!(init_plugin_hillview);

// initializes the Kotlin or Swift plugin classes
pub fn init<R: Runtime, C: DeserializeOwned>(
  _app: &AppHandle<R>,
  api: PluginApi<R, C>,
) -> crate::Result<Hillview<R>> {
  #[cfg(target_os = "android")]
  let handle = api.register_android_plugin("io.github.koo5.hillview.plugin", "ExamplePlugin")?;
  #[cfg(target_os = "ios")]
  let handle = api.register_ios_plugin(init_plugin_hillview)?;
  Ok(Hillview(handle))
}

/// Access to the hillview APIs.
pub struct Hillview<R: Runtime>(PluginHandle<R>);

impl<R: Runtime> Hillview<R> {
  pub fn ping(&self, payload: PingRequest) -> crate::Result<PingResponse> {
    self
      .0
      .run_mobile_plugin("ping", payload)
      .map_err(Into::into)
  }
  
  pub fn start_sensor(&self, mode: Option<i32>) -> crate::Result<()> {
    #[derive(serde::Serialize)]
    struct Args {
      mode: Option<i32>,
    }
    
    self
      .0
      .run_mobile_plugin("startSensor", Args { mode })
      .map_err(Into::into)
  }
  
  pub fn stop_sensor(&self) -> crate::Result<()> {
    self
      .0
      .run_mobile_plugin("stopSensor", ())
      .map_err(Into::into)
  }
  
  pub fn update_sensor_location(&self, location: LocationUpdate) -> crate::Result<()> {
    self
      .0
      .run_mobile_plugin("updateSensorLocation", location)
      .map_err(Into::into)
  }
}

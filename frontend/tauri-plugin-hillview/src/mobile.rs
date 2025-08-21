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
  
  pub fn set_auto_upload_enabled(&self, enabled: bool) -> crate::Result<AutoUploadResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      enabled: bool,
    }
    
    self
      .0
      .run_mobile_plugin("setAutoUploadEnabled", Args { enabled })
      .map_err(Into::into)
  }
  
  pub fn get_upload_status(&self) -> crate::Result<UploadStatusResponse> {
    self
      .0
      .run_mobile_plugin("getUploadStatus", ())
      .map_err(Into::into)
  }
  
  pub fn set_upload_config(&self, config: UploadConfig) -> crate::Result<BasicResponse> {
    self
      .0
      .run_mobile_plugin("setUploadConfig", config)
      .map_err(Into::into)
  }
  
  pub fn upload_photo(&self, photo_id: String) -> crate::Result<PhotoUploadResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      photo_id: String,
    }
    
    self
      .0
      .run_mobile_plugin("uploadPhoto", Args { photo_id })
      .map_err(Into::into)
  }
  
  pub fn retry_failed_uploads(&self) -> crate::Result<BasicResponse> {
    self
      .0
      .run_mobile_plugin("retryFailedUploads", ())
      .map_err(Into::into)
  }
  
  // Authentication methods
  
  pub fn store_auth_token(&self, token: String, expires_at: String) -> crate::Result<BasicResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      token: String,
      expires_at: String,
    }
    
    self
      .0
      .run_mobile_plugin("storeAuthToken", Args { token, expires_at })
      .map_err(Into::into)
  }
  
  pub fn get_auth_token(&self) -> crate::Result<AuthTokenResponse> {
    self
      .0
      .run_mobile_plugin("getAuthToken", ())
      .map_err(Into::into)
  }
  
  pub fn clear_auth_token(&self) -> crate::Result<BasicResponse> {
    self
      .0
      .run_mobile_plugin("clearAuthToken", ())
      .map_err(Into::into)
  }
  
  pub fn start_precise_location_listener(&self) -> crate::Result<()> {
    self
      .0
      .run_mobile_plugin("startPreciseLocationListener", ())
      .map_err(Into::into)
  }
  
  pub fn stop_precise_location_listener(&self) -> crate::Result<()> {
    self
      .0
      .run_mobile_plugin("stopPreciseLocationListener", ())
      .map_err(Into::into)
  }
}

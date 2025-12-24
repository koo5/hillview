use log::info;
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
  let handle = api.register_android_plugin("cz.hillview.plugin", "ExamplePlugin")?;
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

  pub fn set_auto_upload_enabled(&self, enabled: bool, prompt_enabled: bool) -> crate::Result<AutoUploadResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      enabled: bool,
      prompt_enabled: bool,
    }

    self
      .0
      .run_mobile_plugin("setAutoUploadEnabled", Args { enabled, prompt_enabled })
      .map_err(Into::into)
  }

  pub fn get_upload_status(&self) -> crate::Result<UploadStatusResponse> {
    self
      .0
      .run_mobile_plugin("getUploadStatus", ())
      .map_err(Into::into)
  }

// todo delete me
  pub fn set_upload_config(&self, config: UploadConfig) -> crate::Result<BasicResponse> {
    self
      .0
      .run_mobile_plugin("setUploadConfig", config)
      .map_err(Into::into)
  }


// todo rename to try_uploads
  pub fn retry_failed_uploads(&self) -> crate::Result<BasicResponse> {
    self
      .0
      .run_mobile_plugin("tryUploads", ())
      .map_err(Into::into)
  }

  // Authentication methods

  pub fn store_auth_token(&self, token: String, expires_at: String, refresh_token: Option<String>, refresh_expiry: Option<String>) -> crate::Result<BasicResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      token: String,
      expires_at: String,
      refresh_token: Option<String>,
      refresh_expiry: Option<String>,
    }

    self
      .0
      .run_mobile_plugin("storeAuthToken", Args { token, expires_at, refresh_token, refresh_expiry })
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

  pub fn get_device_photos(&self) -> crate::Result<crate::models::DevicePhotosResponse> {
    self
      .0
      .run_mobile_plugin("getDevicePhotos", ())
      .map_err(Into::into)
  }

  pub fn refresh_photo_scan(&self) -> crate::Result<crate::models::PhotoScanResponse> {
    self
      .0
      .run_mobile_plugin("refreshPhotoScan", ())
      .map_err(Into::into)
  }

  pub fn import_photos(&self) -> crate::Result<crate::models::FileImportResponse> {
    self
      .0
      .run_mobile_plugin("importPhotos", ())
      .map_err(Into::into)
  }

  pub fn register_client_public_key(&self) -> crate::Result<BasicResponse> {
    self
      .0
      .run_mobile_plugin("registerClientPublicKey", ())
      .map_err(Into::into)
  }

  pub fn add_photo_to_database(&self, photo: crate::shared_types::DevicePhotoMetadata) -> crate::Result<crate::shared_types::AddPhotoResponse> {
    // Convert to the format expected by Android (flattened structure)
    let android_photo = serde_json::json!({
      "id": photo.id,
      "filename": photo.filename,
      "path": photo.path,
      "latitude": photo.metadata.latitude,
      "longitude": photo.metadata.longitude,
      "altitude": photo.metadata.altitude,
      "bearing": photo.metadata.bearing,
      "captured_at": photo.metadata.captured_at,
      "accuracy": photo.metadata.accuracy,
      "width": photo.width,
      "height": photo.height,
      "file_size": photo.file_size,
      "created_at": photo.created_at,
      "file_hash": photo.file_hash
    });

    self
      .0
      .run_mobile_plugin("addPhotoToDatabase", android_photo)
      .map_err(Into::into)
  }

  pub fn share_photo(&self, title: Option<String>, text: Option<String>, url: String) -> crate::Result<BasicResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      title: Option<String>,
      text: Option<String>,
      url: String,
    }

    self
      .0
      .run_mobile_plugin("sharePhoto", Args { title, text, url })
      .map_err(Into::into)
  }

  pub fn photo_worker_process(&self, message_json: String) -> crate::Result<PhotoWorkerResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      message_json: String,
    }

    self
      .0
      .run_mobile_plugin("photoWorkerProcess", Args { message_json })
      .map_err(Into::into)
  }

  pub fn get_bearing_for_timestamp(&self, timestamp: i64) -> crate::Result<BearingLookupResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      timestamp: i64,
    }

    self
      .0
      .run_mobile_plugin("getBearingForTimestamp", Args { timestamp })
      .map_err(Into::into)
  }

  // Push Notification methods

  pub fn get_push_distributors(&self) -> crate::Result<PushDistributorsResponse> {
    self
      .0
      .run_mobile_plugin("getPushDistributors", ())
      .map_err(Into::into)
  }

  pub fn get_push_registration_status(&self) -> crate::Result<PushRegistrationStatusResponse> {
    self
      .0
      .run_mobile_plugin("getPushRegistrationStatus", ())
      .map_err(Into::into)
  }

  pub fn select_push_distributor(&self, package_name: String) -> crate::Result<BasicResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      package_name: String,
    }

    self
      .0
      .run_mobile_plugin("selectPushDistributor", Args { package_name })
      .map_err(Into::into)
  }

  // Notification settings methods

  pub fn get_notification_settings(&self) -> crate::Result<NotificationSettingsResponse> {
    self
      .0
      .run_mobile_plugin("getNotificationSettings", ())
      .map_err(Into::into)
  }

  pub fn set_notification_settings(&self, enabled: bool) -> crate::Result<BasicResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      enabled: bool,
    }

    self
      .0
      .run_mobile_plugin("setNotificationSettings", Args { enabled })
      .map_err(Into::into)
  }

  // Tauri permission system methods

  pub fn check_tauri_permissions(&self) -> crate::Result<crate::models::TauriPermissionResponse> {
    self
      .0
      .run_mobile_plugin("checkPermissions", ())
      .map_err(Into::into)
  }

  pub fn request_tauri_permission(&self, permission: String) -> crate::Result<crate::models::TauriPermissionResponse> {
    info!("🢄🔐request_tauri_permission for permission: {}", permission);

    self.0
      .run_mobile_plugin::<crate::models::TauriPermissionResponse>(
        "requestPermissions",
        crate::models::RequestPermission { permissions: vec![permission] }
      )
      .map_err(Into::into)
  }

  pub fn test_show_notification(&self, title: String, message: String) -> crate::Result<BasicResponse> {
    #[derive(serde::Serialize)]
    struct Args {
      title: String,
      message: String,
    }

    self
      .0
      .run_mobile_plugin("testShowNotification", Args { title, message })
      .map_err(Into::into)
  }

  pub fn get_intent_data(&self) -> crate::Result<serde_json::Value> {
    self
      .0
      .run_mobile_plugin("getIntentData", ())
      .map_err(Into::into)
  }

  pub fn cmd(&self, command: String, params: Option<serde_json::Value>) -> crate::Result<serde_json::Value> {
    #[derive(serde::Serialize)]
    struct Args {
      command: String,
      params: Option<serde_json::Value>,
    }

    self
      .0
      .run_mobile_plugin("cmd", Args { command, params })
      .map_err(Into::into)
  }

  pub fn save_photo_to_media_store(
    &self,
    filename: String,
    image_data: Vec<u8>,
    hide_from_gallery: bool,
  ) -> crate::Result<crate::models::SavePhotoToMediaStoreResponse> {
    #[derive(serde::Serialize)]
    #[serde(rename_all = "camelCase")]
    struct Args {
      filename: String,
      image_data: Vec<u8>,
      hide_from_gallery: bool,
    }

    self
      .0
      .run_mobile_plugin("savePhotoToMediaStore", Args { filename, image_data, hide_from_gallery })
      .map_err(Into::into)
  }

}

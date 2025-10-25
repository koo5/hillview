use serde::de::DeserializeOwned;
use tauri::{plugin::PluginApi, AppHandle, Runtime};

use crate::models::*;

pub fn init<R: Runtime, C: DeserializeOwned>(
  app: &AppHandle<R>,
  _api: PluginApi<R, C>,
) -> crate::Result<Hillview<R>> {
  Ok(Hillview(app.clone()))
}

/// Access to the hillview APIs.
pub struct Hillview<R: Runtime>(AppHandle<R>);

impl<R: Runtime> Hillview<R> {
  pub fn ping(&self, payload: PingRequest) -> crate::Result<PingResponse> {
    Ok(PingResponse {
      value: payload.value,
    })
  }

  pub fn photo_worker_process(&self, _message_json: String) -> crate::Result<PhotoWorkerResponse> {
    // Desktop doesn't support photo worker - return error
    Err(crate::Error::from("Photo worker is only available on mobile devices"))
  }

  // Push notification methods - desktop stubs
  pub fn get_push_distributors(&self) -> crate::Result<PushDistributorsResponse> {
    Err(crate::Error::from("Push notifications are only available on mobile devices"))
  }

  pub fn get_push_registration_status(&self) -> crate::Result<PushRegistrationStatusResponse> {
    Err(crate::Error::from("Push notifications are only available on mobile devices"))
  }

  pub fn select_push_distributor(&self, _package_name: String) -> crate::Result<BasicResponse> {
    Err(crate::Error::from("Push notifications are only available on mobile devices"))
  }
}

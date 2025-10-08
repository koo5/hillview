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
}

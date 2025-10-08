use tauri::{AppHandle, command, Runtime};

use crate::models::*;
use crate::Result;
use crate::HillviewExt;

#[command]
pub(crate) async fn ping<R: Runtime>(
    app: AppHandle<R>,
    payload: PingRequest,
) -> Result<PingResponse> {
    app.hillview().ping(payload)
}

#[command]
#[allow(unused_variables)]
pub(crate) async fn start_sensor<R: Runtime>(
    app: AppHandle<R>,
    mode: Option<i32>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        app.hillview().start_sensor(mode)?;
        return Ok(());
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Sensor API is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn stop_sensor<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        _app.hillview().stop_sensor()?;
    }

    Ok(())
}

#[command]
pub(crate) async fn update_sensor_location<R: Runtime>(
    _app: AppHandle<R>,
    _location: LocationUpdate,
) -> Result<()> {
    #[cfg(mobile)]
    {
        _app.hillview().update_sensor_location(_location)?;
    }

    Ok(())
}

#[command]
#[allow(unused_variables)]
pub(crate) async fn set_auto_upload_enabled<R: Runtime>(
    app: AppHandle<R>,
    enabled: bool,
    prompt_enabled: bool,
) -> Result<AutoUploadResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().set_auto_upload_enabled(enabled, prompt_enabled);
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Auto upload is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn get_upload_status<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<UploadStatusResponse> {
    #[cfg(mobile)]
    {
        return _app.hillview().get_upload_status();
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Upload status is only available on mobile devices"));
    }
}

#[command]
#[allow(unused_variables)]
pub(crate) async fn set_upload_config<R: Runtime>(
    app: AppHandle<R>,
    config: UploadConfig,
) -> Result<BasicResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().set_upload_config(config);
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Upload config is only available on mobile devices"));
    }
}


#[command]
pub(crate) async fn retry_failed_uploads<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<BasicResponse> {
    #[cfg(mobile)]
    {
        return _app.hillview().retry_failed_uploads();
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Retry uploads is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn start_precise_location_listener<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        _app.hillview().start_precise_location_listener()?;
        return Ok(());
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Precise location is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn stop_precise_location_listener<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        _app.hillview().stop_precise_location_listener()?;
        return Ok(());
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Precise location is only available on mobile devices"));
    }
}

// Authentication Commands

#[command]
#[allow(unused_variables)]
pub(crate) async fn store_auth_token<R: Runtime>(
    app: AppHandle<R>,
    token: String,
    refresh_token: Option<String>,
    expires_at: String,
    refresh_expiry: Option<String>,
) -> Result<BasicResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().store_auth_token(token, expires_at, refresh_token, refresh_expiry);
    }

    #[cfg(desktop)]
    {
        // For desktop, just return success for now
        // In a real app, you might use secure storage
        return Ok(BasicResponse {
            success: true,
            error: None,
        });
    }
}

#[command]
pub(crate) async fn get_auth_token<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<AuthTokenResponse> {
    #[cfg(mobile)]
    {
        return _app.hillview().get_auth_token();
    }

    #[cfg(desktop)]
    {
        // For desktop, return no token
        return Ok(AuthTokenResponse {
            token: None,
            expires_at: None,
            success: true,
            error: None,
        });
    }
}

#[command]
pub(crate) async fn clear_auth_token<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<BasicResponse> {
    #[cfg(mobile)]
    {
        return _app.hillview().clear_auth_token();
    }

    #[cfg(desktop)]
    {
        // For desktop, just return success
        return Ok(BasicResponse {
            success: true,
            error: None,
        });
    }
}

#[command]
pub(crate) async fn get_device_photos<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
) -> Result<crate::models::DevicePhotosResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().get_device_photos();
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Device photos are only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn refresh_photo_scan<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
) -> Result<crate::models::PhotoScanResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().refresh_photo_scan();
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Photo scanning is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn import_photos<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
) -> Result<crate::models::FileImportResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().import_photos();
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Photo import is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn register_client_public_key<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
) -> Result<BasicResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().register_client_public_key();
    }

    #[cfg(desktop)]
    {
        return Ok(BasicResponse {
            success: true,
            error: None,
        });
    }
}

#[command]
pub(crate) async fn add_photo_to_database<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
    #[allow(unused_variables)] photo: crate::shared_types::DevicePhotoMetadata,
) -> Result<crate::shared_types::AddPhotoResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().add_photo_to_database(photo);
    }

    #[cfg(desktop)]
    {
        // Desktop doesn't have Android database - return error
        return Err(crate::Error::from("Photo database sync is only available on Android"));
    }
}

#[command]
pub(crate) async fn share_photo<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
    title: Option<String>,
    text: Option<String>,
    url: String,
) -> Result<BasicResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().share_photo(title, text, url);
    }

    #[cfg(desktop)]
    {
        // Desktop fallback - copy to clipboard or open in browser
        return Err(crate::Error::from("Native sharing is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn photo_worker_process<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
    message_json: String,
) -> Result<crate::models::PhotoWorkerResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().photo_worker_process(message_json);
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Photo worker is only available on mobile devices"));
    }
}

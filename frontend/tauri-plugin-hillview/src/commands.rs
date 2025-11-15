use log::info;
use tauri::{AppHandle, command, Runtime};

use crate::models::*;
use crate::Result;
use crate::HillviewExt;

#[command(rename_all = "snake_case")]
pub(crate) async fn ping<R: Runtime>(
    app: AppHandle<R>,
    payload: PingRequest,
) -> Result<PingResponse> {
    app.hillview().ping(payload)
}

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
pub(crate) async fn stop_sensor<R: Runtime>(
    _app: AppHandle<R>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        _app.hillview().stop_sensor()?;
    }

    Ok(())
}

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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


#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[command(rename_all = "snake_case")]
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

#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn share_photo<R: Runtime>(
    app: AppHandle<R>,
    title: Option<String>,
    text: Option<String>,
    url: String,
) -> Result<BasicResponse> {
    app.hillview().share_photo(title, text, url)
}

#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn photo_worker_process<R: Runtime>(
    app: AppHandle<R>,
    message_json: String,
) -> Result<crate::models::PhotoWorkerResponse> {
    app.hillview().photo_worker_process(message_json)
}

// Push Notification Commands

#[command(rename_all = "snake_case")]
pub(crate) async fn get_push_distributors<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
) -> Result<crate::models::PushDistributorsResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().get_push_distributors();
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Push notifications are only available on mobile devices"));
    }
}

#[command(rename_all = "snake_case")]
pub(crate) async fn get_push_registration_status<R: Runtime>(
    #[allow(unused_variables)] app: AppHandle<R>,
) -> Result<crate::models::PushRegistrationStatusResponse> {
    #[cfg(mobile)]
    {
        return app.hillview().get_push_registration_status();
    }

    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Push notifications are only available on mobile devices"));
    }
}

#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn select_push_distributor<R: Runtime>(
    app: AppHandle<R>,
    request: crate::models::SelectDistributorRequest,
) -> Result<BasicResponse> {
    app.hillview().select_push_distributor(request.package_name)
}

// Notification Commands


#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn get_notification_settings<R: Runtime>(
    app: AppHandle<R>,
) -> Result<crate::models::NotificationSettingsResponse> {
    app.hillview().get_notification_settings()
}

#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn set_notification_settings<R: Runtime>(
    app: AppHandle<R>,
    enabled: bool,
) -> Result<crate::models::BasicResponse> {
    app.hillview().set_notification_settings(enabled)
}

// Tauri permission system commands

#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn check_tauri_permissions<R: Runtime>(
    app: AppHandle<R>,
) -> Result<crate::models::TauriPermissionStringResponse> {
    // Convert PermissionState to String for serialization
    let response = app.hillview().check_tauri_permissions()?;
    Ok(crate::models::TauriPermissionStringResponse {
        post_notification: format!("{:?}", response.post_notification),
    })
}

#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn request_post_notification_permission<R: Runtime>(
    app: AppHandle<R>,
) -> Result<String> {
	// logging doesnt seem to work here in plugin?
	info!("🢄🔔request_post_notification_permission invoking app.hillview().request_post_notification_permission()...");
	//Err(crate::Error::from("🢄🔔request_post_notification_permission is currently disabled"))
    let permission_state = app.hillview().request_post_notification_permission()?;
    Ok(format!("{:?}", permission_state))
}

#[cfg(mobile)]
#[command(rename_all = "snake_case")]
pub(crate) async fn test_show_notification<R: Runtime>(
    app: AppHandle<R>,
    title: String,
    message: String,
) -> Result<crate::models::BasicResponse> {
    app.hillview().test_show_notification(title, message)
}

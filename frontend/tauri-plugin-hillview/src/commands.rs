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
pub(crate) async fn start_sensor<R: Runtime>(
    _app: AppHandle<R>,
    mode: Option<i32>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        _app.hillview().start_sensor(mode)?;
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
pub(crate) async fn set_auto_upload_enabled<R: Runtime>(
    _app: AppHandle<R>,
    enabled: bool,
) -> Result<AutoUploadResponse> {
    #[cfg(mobile)]
    {
        return _app.hillview().set_auto_upload_enabled(enabled);
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
pub(crate) async fn set_upload_config<R: Runtime>(
    _app: AppHandle<R>,
    config: UploadConfig,
) -> Result<BasicResponse> {
    #[cfg(mobile)]
    {
        return _app.hillview().set_upload_config(config);
    }
    
    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Upload config is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn upload_photo<R: Runtime>(
    _app: AppHandle<R>,
    photo_id: String,
) -> Result<PhotoUploadResponse> {
    #[cfg(mobile)]
    {
        return _app.hillview().upload_photo(photo_id);
    }
    
    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Photo upload is only available on mobile devices"));
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

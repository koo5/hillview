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

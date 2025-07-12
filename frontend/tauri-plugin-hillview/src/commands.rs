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
    app: AppHandle<R>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        app.hillview().start_sensor()?;
        return Ok(());
    }
    
    #[cfg(desktop)]
    {
        return Err(crate::Error::from("Sensor API is only available on mobile devices"));
    }
}

#[command]
pub(crate) async fn stop_sensor<R: Runtime>(
    app: AppHandle<R>,
) -> Result<()> {
    #[cfg(mobile)]
    {
        app.hillview().stop_sensor()?;
    }
    
    Ok(())
}

#[command]
pub(crate) async fn update_sensor_location<R: Runtime>(
    app: AppHandle<R>,
    location: LocationUpdate,
) -> Result<()> {
    #[cfg(mobile)]
    {
        app.hillview().update_sensor_location(location)?;
    }
    
    Ok(())
}

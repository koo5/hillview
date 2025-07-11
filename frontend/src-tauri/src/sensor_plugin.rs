use serde::{Deserialize, Serialize};
use tauri::{
    plugin::{Builder, TauriPlugin},
    Runtime, Manager,
};

#[cfg(target_os = "android")]
use tauri::plugin::PluginHandle;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct SensorData {
    pub magnetic_heading: f32,
    pub true_heading: f32,
    pub heading_accuracy: f32,
    pub pitch: f32,
    pub roll: f32,
    pub timestamp: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct LocationUpdate {
    pub latitude: f64,
    pub longitude: f64,
}

#[derive(Default)]
struct SensorPlugin<R: Runtime> {
    #[allow(dead_code)]
    app_handle: Option<tauri::AppHandle<R>>,
}

#[tauri::command]
async fn start_sensor<R: Runtime>(
    _app: tauri::AppHandle<R>,
    _plugin: tauri::State<'_, SensorPlugin<R>>,
) -> Result<(), String> {
    #[cfg(target_os = "android")]
    {
        start_sensor_android(_app)?;
    }
    
    #[cfg(not(target_os = "android"))]
    {
        return Err("Sensor API is only available on Android".to_string());
    }
    
    Ok(())
}

#[tauri::command]
async fn stop_sensor<R: Runtime>(
    _app: tauri::AppHandle<R>,
    _plugin: tauri::State<'_, SensorPlugin<R>>,
) -> Result<(), String> {
    #[cfg(target_os = "android")]
    {
        stop_sensor_android(_app)?;
    }
    
    Ok(())
}

#[tauri::command]
async fn update_location<R: Runtime>(
    _app: tauri::AppHandle<R>,
    _plugin: tauri::State<'_, SensorPlugin<R>>,
    location: LocationUpdate,
) -> Result<(), String> {
    #[cfg(target_os = "android")]
    {
        update_location_android(_app, location.latitude, location.longitude)?;
    }
    
    Ok(())
}

#[cfg(target_os = "android")]
fn start_sensor_android<R: Runtime>(app: tauri::AppHandle<R>) -> Result<(), String> {
    use jni::objects::{JObject, JValue};
    
    app.run_on_android_context(move |env, activity, _webview| {
        // Get the activity class
        let activity_class = env.get_object_class(&activity)?;
        
        // Check if our sensor service exists
        let sensor_service_class = match env.find_class("io/github/koo5/hillview/SensorService") {
            Ok(class) => class,
            Err(_) => {
                // Create sensor service class dynamically
                return Err("Sensor service not implemented yet".into());
            }
        };
        
        // Get or create sensor service instance
        let get_sensor_method = env.get_method_id(
            &activity_class,
            "getSensorService",
            "()Lio/github/koo5/hillview/SensorService;",
        );
        
        let sensor_service = if get_sensor_method.is_ok() {
            env.call_method(
                &activity,
                "getSensorService",
                "()Lio/github/koo5/hillview/SensorService;",
                &[],
            )?
            .l()?
        } else {
            // Create new instance
            let constructor = env.get_method_id(
                &sensor_service_class,
                "<init>",
                "(Landroid/content/Context;)V",
            )?;
            
            let sensor_instance = env.new_object(
                &sensor_service_class,
                constructor,
                &[JValue::Object(&activity)],
            )?;
            
            // Store in activity (would need to add this method)
            sensor_instance
        };
        
        // Start sensor with callback
        env.call_method(
            &sensor_service,
            "startSensor",
            "(Ljava/lang/String;)V",
            &[JValue::Object(&JObject::from(env.new_string("tauriSensorCallback")?))],
        )?;
        
        Ok::<(), jni::errors::Error>(())
    })
    .map_err(|e| format!("Failed to start sensor: {:?}", e))?;
    
    Ok(())
}

#[cfg(target_os = "android")]
fn stop_sensor_android<R: Runtime>(app: tauri::AppHandle<R>) -> Result<(), String> {
    app.run_on_android_context(move |env, activity, _webview| {
        let activity_class = env.get_object_class(&activity)?;
        
        let get_sensor_method = env.get_method_id(
            &activity_class,
            "getSensorService",
            "()Lio/github/koo5/hillview/SensorService;",
        );
        
        if get_sensor_method.is_ok() {
            let sensor_service = env.call_method(
                &activity,
                "getSensorService",
                "()Lio/github/koo5/hillview/SensorService;",
                &[],
            )?
            .l()?;
            
            env.call_method(&sensor_service, "stopSensor", "()V", &[])?;
        }
        
        Ok::<(), jni::errors::Error>(())
    })
    .map_err(|e| format!("Failed to stop sensor: {:?}", e))?;
    
    Ok(())
}

#[cfg(target_os = "android")]
fn update_location_android<R: Runtime>(
    app: tauri::AppHandle<R>,
    latitude: f64,
    longitude: f64,
) -> Result<(), String> {
    app.run_on_android_context(move |env, activity, _webview| {
        let activity_class = env.get_object_class(&activity)?;
        
        let get_sensor_method = env.get_method_id(
            &activity_class,
            "getSensorService",
            "()Lio/github/koo5/hillview/SensorService;",
        );
        
        if get_sensor_method.is_ok() {
            let sensor_service = env.call_method(
                &activity,
                "getSensorService",
                "()Lio/github/koo5/hillview/SensorService;",
                &[],
            )?
            .l()?;
            
            env.call_method(
                &sensor_service,
                "updateLocation",
                "(DD)V",
                &[JValue::Double(latitude), JValue::Double(longitude)],
            )?;
        }
        
        Ok::<(), jni::errors::Error>(())
    })
    .map_err(|e| format!("Failed to update location: {:?}", e))?;
    
    Ok(())
}

pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("sensor")
        .invoke_handler(tauri::generate_handler![
            start_sensor,
            stop_sensor,
            update_location
        ])
        .setup(|app, _api| {
            app.manage(SensorPlugin::<R> {
                app_handle: Some(app.clone()),
            });
            
            // Set up sensor data receiver on Android
            #[cfg(target_os = "android")]
            {
                setup_sensor_receiver(app.clone());
            }
            
            Ok(())
        })
        .build()
}

#[cfg(target_os = "android")]
fn setup_sensor_receiver<R: Runtime>(app: tauri::AppHandle<R>) {
    // This would set up JNI callbacks to receive sensor data
    // For now, we'll emit events from the Android side
}
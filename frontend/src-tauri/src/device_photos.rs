use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tauri::{command, Manager};
use image::GenericImageView;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DevicePhotoMetadata {
    pub id: String,
    pub filename: String,
    pub path: String,
    pub latitude: f64,
    pub longitude: f64,
    pub altitude: Option<f64>,
    pub bearing: Option<f64>,
    pub timestamp: i64,
    pub accuracy: f64,
    pub width: u32,
    pub height: u32,
    pub file_size: u64,
    pub created_at: i64,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct DevicePhotosDb {
    pub photos: Vec<DevicePhotoMetadata>,
    pub last_updated: i64,
}

impl DevicePhotosDb {
    fn new() -> Self {
        Self {
            photos: Vec::new(),
            last_updated: chrono::Utc::now().timestamp(),
        }
    }
}

#[command]
pub async fn load_device_photos_db(app_handle: tauri::AppHandle) -> Result<DevicePhotosDb, String> {
        
    let app_dir = app_handle.path().app_data_dir()
        .map_err(|_| "Failed to get app data directory".to_string())?;
    
    let db_path = app_dir.join("device_photos.json");
    
    if !db_path.exists() {
        return Ok(DevicePhotosDb::new());
    }
    
    let content = std::fs::read_to_string(&db_path)
        .map_err(|e| format!("Failed to read database: {}", e))?;
    
    serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse database: {}", e))
}

#[command]
pub async fn save_device_photos_db(app_handle: tauri::AppHandle, db: DevicePhotosDb) -> Result<(), String> {
        
    let app_dir = app_handle.path().app_data_dir()
        .map_err(|_| "Failed to get app data directory".to_string())?;
    
    let db_path = app_dir.join("device_photos.json");
    
    let content = serde_json::to_string_pretty(&db)
        .map_err(|e| format!("Failed to serialize database: {}", e))?;
    
    std::fs::write(&db_path, content)
        .map_err(|e| format!("Failed to write database: {}", e))
}

#[command]
pub async fn add_device_photo_to_db(
    app_handle: tauri::AppHandle,
    photo_path: String,
    metadata: crate::photo_exif::PhotoMetadata,
) -> Result<DevicePhotoMetadata, String> {
    // Get image dimensions
    let img = image::open(&photo_path)
        .map_err(|e| format!("Failed to open image for dimensions: {}", e))?;
    let (width, height) = img.dimensions();
    
    // Get file size
    let file_metadata = std::fs::metadata(&photo_path)
        .map_err(|e| format!("Failed to get file metadata: {}", e))?;
    let file_size = file_metadata.len();
    
    // Extract filename from path
    let path_buf = PathBuf::from(&photo_path);
    let filename = path_buf.file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown.jpg")
        .to_string();
    
    let device_photo = DevicePhotoMetadata {
        id: format!("device_{}_{}", chrono::Utc::now().timestamp_millis(), uuid::Uuid::new_v4()),
        filename,
        path: photo_path,
        latitude: metadata.latitude,
        longitude: metadata.longitude,
        altitude: metadata.altitude,
        bearing: metadata.bearing,
        timestamp: metadata.timestamp,
        accuracy: metadata.accuracy,
        width,
        height,
        file_size,
        created_at: chrono::Utc::now().timestamp(),
    };
    
    // Load existing db, add photo, and save
    let mut db = load_device_photos_db(app_handle.clone()).await.unwrap_or_else(|_| DevicePhotosDb::new());
    db.photos.push(device_photo.clone());
    db.last_updated = chrono::Utc::now().timestamp();
    
    save_device_photos_db(app_handle, db).await?;
    
    Ok(device_photo)
}

#[command]
pub async fn refresh_device_photos(app_handle: tauri::AppHandle) -> Result<DevicePhotosDb, String> {
        
    let app_dir = app_handle.path().app_data_dir()
        .map_err(|_| "Failed to get app data directory".to_string())?;
    
    let photos_dir = app_dir.join("captured_photos");
    if !photos_dir.exists() {
        return Ok(DevicePhotosDb::new());
    }
    
    let mut db = load_device_photos_db(app_handle.clone()).await.unwrap_or_else(|_| DevicePhotosDb::new());
    
    // Remove photos that no longer exist
    db.photos.retain(|photo| std::path::Path::new(&photo.path).exists());
    
    // Scan for new photos (this is simplified - in reality you'd want to check if photos are already in db)
    // For now, we'll just update the timestamp
    db.last_updated = chrono::Utc::now().timestamp();
    
    save_device_photos_db(app_handle, db.clone()).await?;
    
    Ok(db)
}

#[command]
pub async fn delete_device_photo(app_handle: tauri::AppHandle, photo_id: String) -> Result<(), String> {
    let mut db = load_device_photos_db(app_handle.clone()).await?;
    
    // Find and remove the photo
    if let Some(index) = db.photos.iter().position(|p| p.id == photo_id) {
        let photo = &db.photos[index];
        
        // Delete the actual file
        if let Err(e) = std::fs::remove_file(&photo.path) {
            eprintln!("Failed to delete photo file: {}", e);
        }
        
        // Remove from database
        db.photos.remove(index);
        db.last_updated = chrono::Utc::now().timestamp();
        
        save_device_photos_db(app_handle, db).await?;
    }
    
    Ok(())
}
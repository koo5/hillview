use image::GenericImageView;
use log::{info, warn, error};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::collections::HashSet;
use tauri::{command, Manager};

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

/// Get the base Pictures directory path for the current platform
fn get_pictures_base_dir() -> Result<PathBuf, String> {
    if cfg!(target_os = "android") {
        let external_storage = std::env::var("EXTERNAL_STORAGE")
            .unwrap_or_else(|_| "/storage/emulated/0".to_string());
        Ok(Path::new(&external_storage).to_path_buf())
    } else {
        dirs::picture_dir()
            .ok_or_else(|| "Could not determine Pictures directory".to_string())
    }
}

/// Get both Hillview directories (visible and hidden)
fn get_hillview_directories() -> Result<(PathBuf, PathBuf), String> {
    let base = get_pictures_base_dir()?;
    let visible = base.join("Hillview");
    let hidden = base.join(".Hillview");
    Ok((visible, hidden))
}

/// Get the target directory for new photos based on user preference
#[allow(dead_code)]
fn get_target_directory(hide_from_gallery: bool) -> Result<PathBuf, String> {
    let (visible, hidden) = get_hillview_directories()?;
    Ok(if hide_from_gallery { hidden } else { visible })
}

/// Get the database file path
fn get_database_path(app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    let app_dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|_| "Failed to get app data directory".to_string())?;
    Ok(app_dir.join("device_photos.json"))
}

#[command]
pub async fn load_device_photos_db(app_handle: tauri::AppHandle) -> Result<DevicePhotosDb, String> {
    let db_path = get_database_path(&app_handle)?;

    if !db_path.exists() {
        info!("Device photos database not found, creating new one");
        return Ok(DevicePhotosDb::new());
    }

    let content = std::fs::read_to_string(&db_path)
        .map_err(|e| {
            error!("Failed to read device photos database: {}", e);
            format!("Failed to read database: {}", e)
        })?;

    serde_json::from_str(&content)
        .map_err(|e| {
            error!("Failed to parse device photos database: {}", e);
            format!("Failed to parse database: {}", e)
        })
}

#[command]
pub async fn save_device_photos_db(
    app_handle: tauri::AppHandle,
    db: DevicePhotosDb,
) -> Result<(), String> {
    let db_path = get_database_path(&app_handle)?;

    // Ensure parent directory exists
    if let Some(parent) = db_path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create database directory: {}", e))?;
    }

    let content = serde_json::to_string_pretty(&db)
        .map_err(|e| {
            error!("Failed to serialize device photos database: {}", e);
            format!("Failed to serialize database: {}", e)
        })?;

    std::fs::write(&db_path, content)
        .map_err(|e| {
            error!("Failed to write device photos database: {}", e);
            format!("Failed to write database: {}", e)
        })?;

    info!("Device photos database saved with {} photos", db.photos.len());
    Ok(())
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
    let filename = path_buf
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown.jpg")
        .to_string();

    let device_photo = DevicePhotoMetadata {
        id: format!(
            "device_{}_{}",
            chrono::Utc::now().timestamp_millis(),
            uuid::Uuid::new_v4()
        ),
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
    let mut db = load_device_photos_db(app_handle.clone())
        .await
        .unwrap_or_else(|_| DevicePhotosDb::new());
    db.photos.push(device_photo.clone());
    db.last_updated = chrono::Utc::now().timestamp();

    save_device_photos_db(app_handle, db).await?;

    info!("Added device photo to database: id: {}, path: {}, filename: {}, dimensions: {}x{}, size: {} bytes, lat: {}, lon: {}, alt: {:?}, bearing: {:?}, timestamp: {}, accuracy: {}",
          device_photo.id, device_photo.path, device_photo.filename, device_photo.width, device_photo.height,
          device_photo.file_size, device_photo.latitude, device_photo.longitude, device_photo.altitude,
          device_photo.bearing, device_photo.timestamp, device_photo.accuracy);

    Ok(device_photo)
}

/// Scan a directory for image files
fn scan_directory_for_images(dir: &Path) -> Result<Vec<PathBuf>, std::io::Error> {
    let mut image_files = Vec::new();
    
    if !dir.exists() {
        return Ok(image_files);
    }
    
    let entries = std::fs::read_dir(dir)?;
    
    for entry in entries {
        let entry = entry?;
        let path = entry.path();
        
        if path.is_file() {
            if let Some(extension) = path.extension() {
                let ext = extension.to_string_lossy().to_lowercase();
                if matches!(ext.as_str(), "jpg" | "jpeg" | "png" | "webp") {
                    image_files.push(path);
                }
            }
        }
    }
    
    Ok(image_files)
}

/// Create DevicePhotoMetadata from a file path
async fn create_device_photo_metadata(file_path: &Path) -> Result<DevicePhotoMetadata, String> {
    let path_str = file_path.to_string_lossy().to_string();
    
    // Get basic file info
    let metadata = std::fs::metadata(file_path)
        .map_err(|e| format!("Failed to read file metadata: {}", e))?;
    let file_size = metadata.len();
    
    // Get filename
    let filename = file_path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("unknown")
        .to_string();
    
    // Try to get image dimensions
    let (width, height) = match image::open(file_path) {
        Ok(img) => {
            let (w, h) = img.dimensions();
            (w, h)
        }
        Err(e) => {
            warn!("Failed to read image dimensions for {}: {}", path_str, e);
            (0, 0)
        }
    };
    
    // Try to read EXIF data for GPS info
    let (latitude, longitude, altitude, bearing, timestamp, accuracy) = 
        match crate::photo_exif::read_photo_exif(path_str.clone()).await {
            Ok(exif_data) => (
                exif_data.latitude,
                exif_data.longitude,
                exif_data.altitude,
                exif_data.bearing,
                exif_data.timestamp,
                exif_data.accuracy,
            ),
            Err(_) => {
                // No EXIF data, use defaults
                (0.0, 0.0, None, None, chrono::Utc::now().timestamp(), 0.0)
            }
        };
    
    Ok(DevicePhotoMetadata {
        id: format!(
            "device_{}_{}_{}", 
            chrono::Utc::now().timestamp_millis(),
            uuid::Uuid::new_v4(),
            filename
        ),
        filename,
        path: path_str,
        latitude,
        longitude,
        altitude,
        bearing,
        timestamp,
        accuracy,
        width,
        height,
        file_size,
        created_at: chrono::Utc::now().timestamp(),
    })
}

#[command]
pub async fn refresh_device_photos(app_handle: tauri::AppHandle) -> Result<DevicePhotosDb, String> {
    info!("Starting device photos refresh");
    
    // Get both directories to scan
    let (visible_dir, hidden_dir) = get_hillview_directories()?;
    let directories_to_scan = [&visible_dir, &hidden_dir];
    
    // Load existing database
    let mut db = load_device_photos_db(app_handle.clone())
        .await
        .unwrap_or_else(|e| {
            warn!("Failed to load existing database, creating new: {}", e);
            DevicePhotosDb::new()
        });
    
    // Remove photos that no longer exist on filesystem
    let initial_count = db.photos.len();
    db.photos.retain(|photo| {
        let exists = Path::new(&photo.path).exists();
        if !exists {
            info!("Removing deleted photo from database: {}", photo.path);
        }
        exists
    });
    let removed_count = initial_count - db.photos.len();
    
    // Build set of existing paths for quick lookup
    let existing_paths: HashSet<String> = db.photos.iter()
        .map(|p| p.path.clone())
        .collect();
    
    // Scan both directories for new photos
    let mut new_photos_added = 0;
    let mut scan_errors = 0;
    
    for dir in directories_to_scan {
        if !dir.exists() {
            continue;
        }
        
        info!("Scanning directory: {:?}", dir);
        
        match scan_directory_for_images(dir) {
            Ok(image_files) => {
                info!("Found {} image files in {:?}", image_files.len(), dir);
                
                for file_path in image_files {
                    let path_str = file_path.to_string_lossy().to_string();
                    
                    // Skip if already in database
                    if existing_paths.contains(&path_str) {
                        continue;
                    }
                    
                    // Create metadata for new photo
                    match create_device_photo_metadata(&file_path).await {
                        Ok(photo_metadata) => {
                            info!("Adding new photo to database: {}", photo_metadata.filename);
                            db.photos.push(photo_metadata);
                            new_photos_added += 1;
                        }
                        Err(e) => {
                            warn!("Failed to create metadata for {}: {}", path_str, e);
                            scan_errors += 1;
                        }
                    }
                }
            }
            Err(e) => {
                error!("Failed to scan directory {:?}: {}", dir, e);
                scan_errors += 1;
            }
        }
    }
    
    // Update timestamp
    db.last_updated = chrono::Utc::now().timestamp();
    
    // Save updated database
    save_device_photos_db(app_handle, db.clone()).await?;
    
    info!(
        "Device photos refresh complete: {} photos total, {} new added, {} removed, {} scan errors",
        db.photos.len(), new_photos_added, removed_count, scan_errors
    );
    
    Ok(db)
}

#[command]
pub async fn delete_device_photo(
    app_handle: tauri::AppHandle,
    photo_id: String,
) -> Result<(), String> {
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

import React, { useState, useEffect } from 'react';
import { PhotoUploader } from './components/PhotoUploader';
import { PhotoGallery } from './components/PhotoGallery';
import { Map } from './components/Map';
import { PhotoData, MapState } from './types';
import { Camera, Upload, X, Compass } from 'lucide-react';

import { geoPicsUrl } from 'data.ts';

function parseCoordinate(coord: string): number {
  try {
    const parts = coord.replace('[', '').replace(']', '').split(',').map(p => p.trim());
    const degrees = parseFloat(parts[0]);
    const minutes = parseFloat(parts[1]);
    let seconds = 0;
    if (parts[2].includes('/')) {
      const [num, denom] = parts[2].split('/').map(Number);
      seconds = num / denom;
    } else {
      seconds = parseFloat(parts[2]);
    }
    return degrees + minutes / 60 + seconds / 3600;
  } catch (error) {
    console.error('Error parsing coordinate:', coord, error);
    return 0;
  }
}

function parseFraction(value: string): number {
  if (!value) return 0;
  if (value.includes('/')) {
    const [numerator, denominator] = value.split('/').map(Number);
    return numerator / denominator;
  }
  return parseFloat(value) || 0;
}

function createPhotoData(item: APIPhotoData, loadThumbnail: boolean = false): PhotoData {
  return {
    id: Math.random().toString(36).substring(7),
    file: item.file,
    thumbnail: loadThumbnail ? `${geoPicsUrl}/${encodeURIComponent(item.file)}` : '',
    latitude: parseCoordinate(item.latitude),
    longitude: parseCoordinate(item.longitude),
    direction: parseFraction(item.bearing),
    altitude: parseFraction(item.altitude),
    loaded: loadThumbnail
  };
}

// Calculate initial visible distance based on zoom level
function calculateInitialVisibleDistance(zoom: number): number {
  const baseDistance = 2; // km at zoom level 13
  const baseZoom = 13;
  return baseDistance * Math.pow(2, baseZoom - zoom);
}

// Format coordinates to a human-readable string
function formatCoordinate(coord: number, isLatitude: boolean): string {
  const direction = isLatitude ? (coord >= 0 ? 'N' : 'S') : (coord >= 0 ? 'E' : 'W');
  const absCoord = Math.abs(coord);
  return `${absCoord.toFixed(6)}°${direction}`;
}

function App() {
  const [photos, setPhotos] = useState<PhotoData[]>([]);
  const [mapState, setMapState] = useState<MapState>({
    center: [51.505, -0.09],
    zoom: 13,
    bearing: 0,
    maxDistance: calculateInitialVisibleDistance(13)
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState({ current: 0, total: 0 });
  const [showUploader, setShowUploader] = useState(false);

  // Load thumbnails for photos that are within or near the visible area
  useEffect(() => {
    const FOV_ANGLE = 60; // Field of view in degrees
    const MAX_DISTANCE = mapState.maxDistance; // Use dynamic max distance
    const BUFFER_ANGLE = 30; // Additional angle buffer for preloading
    const BUFFER_DISTANCE = MAX_DISTANCE * 0.25; // Additional distance buffer for preloading (25% of max distance)

    const loadThumbnailsForVisiblePhotos = async () => {
      const photosToLoad = photos.filter(photo => {
        if (photo.loaded) return false;

        // Calculate distance and bearing to the photo
        const R = 6371; // Earth's radius in km
        const lat1 = mapState.center[0] * Math.PI / 180;
        const lon1 = mapState.center[1] * Math.PI / 180;
        const lat2 = photo.latitude * Math.PI / 180;
        const lon2 = photo.longitude * Math.PI / 180;

        // Calculate distance
        const dLat = lat2 - lat1;
        const dLon = lon2 - lon1;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                  Math.cos(lat1) * Math.cos(lat2) * 
                  Math.sin(dLon/2) * Math.sin(dLon/2);
        const distance = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

        // Calculate bearing
        const y = Math.sin(dLon) * Math.cos(lat2);
        const x = Math.cos(lat1) * Math.sin(lat2) -
                 Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
        let bearing = Math.atan2(y, x) * 180 / Math.PI;
        bearing = (bearing + 360) % 360;

        // Calculate relative bearing
        let relativeBearing = (bearing - mapState.bearing + 360) % 360;
        if (relativeBearing > 180) relativeBearing -= 360;

        // Check if photo is within the expanded visible area
        return Math.abs(relativeBearing) < (FOV_ANGLE / 2 + BUFFER_ANGLE) &&
               distance < (MAX_DISTANCE + BUFFER_DISTANCE);
      });

      if (photosToLoad.length === 0) return;

      // Update photos with thumbnails
      setPhotos(prevPhotos => {
        const newPhotos = [...prevPhotos];
        photosToLoad.forEach(photo => {
          const index = newPhotos.findIndex(p => p.id === photo.id);
          if (index !== -1) {
            newPhotos[index] = {
              ...newPhotos[index],
              thumbnail: `${geoPicsUrl}/${encodeURIComponent(photo.file)}`,
              loaded: true
            };
          }
        });
        return newPhotos;
      });
    };

    loadThumbnailsForVisiblePhotos();
  }, [photos, mapState]);

  useEffect(() => {
    const fetchPhotos = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${geoPicsUrl}/files.json`, {
          headers: { 'Accept': 'application/json' }
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data: APIPhotoData[] = await response.json();
        if (!Array.isArray(data)) {
          throw new Error('Expected an array of photos, but received: ' + typeof data);
        }

        // Create photo objects without loading thumbnails
        const initialPhotos = data.map(item => createPhotoData(item, false));
        setPhotos(initialPhotos);
        setProgress({ current: 0, total: data.length });
        setError(null);
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
        console.error('Error fetching photos:', error);
        setError(`Failed to load photos: ${errorMessage}`);
      } finally {
        setLoading(false);
      }
    };

    fetchPhotos();
  }, []);

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-8">
            <div className="flex items-center">
              <Camera className="w-8 h-8 text-blue-600 mr-2" />
              <h1 className="text-2xl font-bold text-gray-900">Photo Mapper</h1>
            </div>
            <div className="flex items-center space-x-4 text-sm text-gray-600">
              <div className="flex items-center">
                <span className="font-medium">Position:</span>
                <span className="ml-2">{formatCoordinate(mapState.center[0], true)}, {formatCoordinate(mapState.center[1], false)}</span>
              </div>
              <div className="flex items-center">
                <Compass className="w-4 h-4 mr-1" />
                <span className="font-medium">Viewing:</span>
                <span className="ml-2">{mapState.bearing.toFixed(1)}°</span>
              </div>
            </div>
          </div>
          <button
            onClick={() => setShowUploader(true)}
            className="flex items-center px-3 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            <Upload className="w-4 h-4 mr-2" />
            <span>Upload Photos</span>
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}
        {loading && progress.total > 0 && (
          <div className="mb-4">
            <div className="p-4 bg-blue-100 border border-blue-400 text-blue-700 rounded">
              Loading photo thumbnails... {progress.current} of {progress.total}
            </div>
            <div className="mt-2 h-2 bg-blue-200 rounded-full">
              <div 
                className="h-full bg-blue-600 rounded-full transition-all duration-300"
                style={{ width: `${(progress.current / progress.total) * 100}%` }}
              />
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-6 h-[600px]">
          <div className="bg-white rounded-lg shadow-lg overflow-hidden">
            <PhotoGallery photos={photos} mapState={mapState} />
          </div>
          <div className="bg-white rounded-lg shadow-lg overflow-hidden">
            <Map photos={photos} onMapStateChange={setMapState} />
          </div>
        </div>
      </main>

      {/* Upload Modal */}
      {showUploader && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
            <div className="flex justify-between items-center p-4 border-b">
              <h2 className="text-lg font-semibold">Upload Photos</h2>
              <button
                onClick={() => setShowUploader(false)}
                className="text-gray-500 hover:text-gray-700"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4">
              <PhotoUploader
                onPhotosLoaded={(newPhotos) => {
                  setPhotos(prev => [...prev, ...newPhotos]);
                  setShowUploader(false);
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
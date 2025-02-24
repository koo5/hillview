import React, { useMemo, useState, useRef } from 'react';
import { PhotoData, MapState } from '../types';
import { ChevronDown, ChevronUp, Download, AlertCircle, RefreshCw } from 'lucide-react';

const geoPicsUrl = import.meta.env.VITE_REACT_APP_GEO_PICS_URL;

interface Props {
  photos: PhotoData[];
  mapState: MapState;
}

interface RetryState {
  attempts: number;
  timeout: number | null;
}

const FOV_ANGLE = 60; // Field of view in degrees
const MAX_RELATIVE_ANGLE = 30; // Maximum angle difference to show in gallery
const DOWNLOAD_TIMEOUT = 30000; // 30 seconds timeout for downloads
const MAX_VISIBLE_PHOTOS = 3; // Maximum number of visible photos
const MAX_HORIZONTAL_OFFSET = 25; // Maximum percentage a photo can move horizontally

// Retry configuration
const MAX_RETRIES = 5;
const INITIAL_RETRY_DELAY = 1000; // 1 second
const MAX_RETRY_DELAY = 32000; // 32 seconds

function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371; // Earth's radius in kilometers
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = 
    Math.sin(dLat/2) * Math.sin(dLat/2) +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * 
    Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

function calculateBearing(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const lat1Rad = lat1 * Math.PI / 180;
  const lat2Rad = lat2 * Math.PI / 180;
  
  const y = Math.sin(dLon) * Math.cos(lat2Rad);
  const x = Math.cos(lat1Rad) * Math.sin(lat2Rad) -
            Math.sin(lat1Rad) * Math.cos(lat2Rad) * Math.cos(dLon);
  
  let bearing = Math.atan2(y, x) * 180 / Math.PI;
  return (bearing + 360) % 360;
}

function calculatePhotoPosition(distance: number, relativeBearing: number, maxDistance: number): { x: number; scale: number; z: number; y: number } {
  // Convert distance to a 0-1 scale
  const normalizedDistance = Math.min(distance, maxDistance) / maxDistance;
  
  // Calculate horizontal position based on bearing with reduced spread
  const normalizedBearing = relativeBearing / (FOV_ANGLE / 2); // -1 to 1
  const x = Math.sign(normalizedBearing) * Math.pow(Math.abs(normalizedBearing), 1.5) * MAX_HORIZONTAL_OFFSET * 0.25;
  
  // Calculate vertical position (closer = higher)
  const y = normalizedDistance * 40; // Adjust this value to control vertical spread
  
  // Calculate scale based on distance (closer = larger)
  const scale = 1 + (1 - normalizedDistance) * 0.7;
  
  // Calculate z-index (closer = higher)
  const z = Math.floor((1 - normalizedDistance) * 1000);
  
  return { x, scale, z, y };
}

export function PhotoGallery({ photos, mapState }: Props) {
  const [showDebug, setShowDebug] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloadingPhoto, setDownloadingPhoto] = useState<string | null>(null);
  const [loadingStates, setLoadingStates] = useState<Record<string, RetryState>>({});
  const imageRefs = useRef<Record<string, HTMLImageElement>>({});

  const retryLoad = (photo: PhotoData) => {
    const state = loadingStates[photo.id] || { attempts: 0, timeout: null };
    
    if (state.attempts >= MAX_RETRIES) {
      console.error(`Max retries (${MAX_RETRIES}) reached for photo:`, photo.file);
      return;
    }

    if (state.timeout) {
      clearTimeout(state.timeout);
    }

    const delay = Math.min(
      INITIAL_RETRY_DELAY * Math.pow(2, state.attempts),
      MAX_RETRY_DELAY
    );

    const timeoutId = window.setTimeout(() => {
      if (imageRefs.current[photo.id]) {
        const img = imageRefs.current[photo.id];
        const currentSrc = img.src;
        img.src = '';
        img.src = currentSrc;
      }
    }, delay);

    setLoadingStates(prev => ({
      ...prev,
      [photo.id]: {
        attempts: state.attempts + 1,
        timeout: timeoutId
      }
    }));
  };

  const { visiblePhotos, totalInCircle } = useMemo(() => {
    // First, calculate all photos within the visible range (circle)
    const inCircle = photos.filter(photo => {
      const distance = calculateDistance(
        mapState.center[0],
        mapState.center[1],
        photo.latitude,
        photo.longitude
      );
      return distance <= mapState.maxDistance;
    });

    // Then, calculate which photos are visible based on direction and distance
    const visible = inCircle
      .map(photo => {
        const distance = calculateDistance(
          mapState.center[0],
          mapState.center[1],
          photo.latitude,
          photo.longitude
        );

        const bearing = calculateBearing(
          mapState.center[0],
          mapState.center[1],
          photo.latitude,
          photo.longitude
        );

        // Calculate relative angle to map bearing
        let relativeBearing = (bearing - mapState.bearing + 360) % 360;
        if (relativeBearing > 180) relativeBearing -= 360;

        // Calculate the absolute angle difference between viewer direction and photo direction
        const directionDiff = Math.abs(((photo.direction - mapState.bearing + 180 + 360) % 360) - 180);

        const { x, scale, z, y } = calculatePhotoPosition(distance, relativeBearing, mapState.maxDistance);

        return {
          ...photo,
          distance,
          relativeBearing,
          directionDiff,
          x,
          y,
          scale,
          z,
          visible: Math.abs(relativeBearing) <= FOV_ANGLE / 2 && // Within field of view
                  directionDiff <= MAX_RELATIVE_ANGLE // Camera pointing in similar direction
        };
      })
      .filter(p => p.visible)
      .sort((a, b) => {
        // Primary sort by direction difference
        const directionDiffA = a.directionDiff || 0;
        const directionDiffB = b.directionDiff || 0;
        if (directionDiffA !== directionDiffB) {
          return directionDiffA - directionDiffB;
        }
        // Secondary sort by distance (closer photos on top)
        return (a.distance || 0) - (b.distance || 0);
      })
      .slice(0, MAX_VISIBLE_PHOTOS);

    return {
      visiblePhotos: visible,
      totalInCircle: inCircle.length
    };
  }, [photos, mapState]);

  const handleDownload = async (photo: PhotoData) => {
    if (downloadingPhoto === photo.file) return;
    
    setDownloadingPhoto(photo.file);
    setDownloadError(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), DOWNLOAD_TIMEOUT);

      const response = await fetch(
        `${geoPicsUrl}/${encodeURIComponent(photo.file)}`,
        {
          signal: controller.signal,
          headers: {
            'Accept': 'image/jpeg',
          }
        }
      );

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = photo.file;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Error downloading photo:', error);
      setDownloadError(
        error instanceof Error ? error.message : 'Failed to download photo'
      );
    } finally {
      setDownloadingPhoto(null);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 bg-gray-50 border-b flex justify-between items-center">
        <div>
          <h2 className="text-lg font-semibold">
            Visible Photos ({totalInCircle})
          </h2>
          <p className="text-sm text-gray-600">
            Showing closest photos within {FOV_ANGLE}° field of view and {mapState.maxDistance.toFixed(1)}km range
          </p>
        </div>
        <button
          onClick={() => setShowDebug(!showDebug)}
          className="flex items-center px-2 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300 transition-colors"
        >
          {showDebug ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          <span className="ml-1">Debug</span>
        </button>
      </div>

      <div className="flex flex-1">
        <div className={`flex-1 relative overflow-hidden bg-gray-900 perspective ${showDebug ? 'border-r border-gray-200' : ''}`}>
          <div className="absolute inset-0 flex items-center justify-center">
            {visiblePhotos.map(photo => {
              const translateX = `${photo.x}%`;
              const translateY = `${photo.y}%`;
              const scale = photo.scale;
              const loadingState = loadingStates[photo.id];
              const isRetrying = loadingState && loadingState.timeout !== null;
              
              return (
                <div
                  key={photo.id}
                  className="absolute transition-all duration-300"
                  style={{
                    transform: `translate(${translateX}, ${translateY}) scale(${scale})`,
                    zIndex: photo.z,
                    width: '300px',
                    height: '200px'
                  }}
                >
                  <div className="relative w-full h-full group">
                    {(!photo.loaded || isRetrying) && (
                      <div className="absolute inset-0 rounded-lg loading-background flex items-center justify-center">
                        {isRetrying && (
                          <div className="bg-black bg-opacity-50 rounded-full p-2">
                            <RefreshCw className="w-6 h-6 text-white animate-spin" />
                          </div>
                        )}
                      </div>
                    )}
                    <img
                      ref={el => {
                        if (el) imageRefs.current[photo.id] = el;
                      }}
                      src={photo.thumbnail}
                      alt=""
                      className={`w-full h-full object-cover rounded-lg shadow-lg transition-opacity duration-300 ${!photo.loaded ? 'opacity-0' : 'opacity-100'}`}
                      style={{
                        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1), 0 1px 3px rgba(0, 0, 0, 0.08)'
                      }}
                      onError={() => {
                        if (!loadingStates[photo.id] || loadingStates[photo.id].attempts < MAX_RETRIES) {
                          retryLoad(photo);
                        }
                      }}
                      onLoad={() => {
                        setLoadingStates(prev => ({
                          ...prev,
                          [photo.id]: { attempts: 0, timeout: null }
                        }));
                      }}
                    />
                    <div className="absolute bottom-0 left-0 right-0 bg-black bg-opacity-50 text-white text-xs p-2 rounded-b-lg opacity-0 group-hover:opacity-100 transition-opacity">
                      <p>{(photo.distance || 0).toFixed(2)}km away</p>
                      <p>{Math.abs(photo.relativeBearing || 0).toFixed(1)}° from center</p>
                      <p>Direction diff: {photo.directionDiff?.toFixed(1)}°</p>
                      {loadingState?.attempts > 0 && (
                        <p className="text-yellow-300">
                          Retry attempt: {loadingState.attempts}/{MAX_RETRIES}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {showDebug && (
          <div className="w-64 bg-white overflow-y-auto border-l">
            <div className="p-3 bg-gray-50 border-b sticky top-0">
              <h3 className="font-medium">Debug Information</h3>
              {downloadError && (
                <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-red-700 text-xs flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <p>{downloadError}</p>
                </div>
              )}
            </div>
            <div className="divide-y">
              {visiblePhotos.map(photo => (
                <div 
                  key={photo.id} 
                  className="p-3 text-xs hover:bg-gray-50 transition-colors cursor-pointer group"
                  onClick={() => handleDownload(photo)}
                >
                  <div className="font-medium mb-1 truncate flex items-center justify-between">
                    <span>{photo.file}</span>
                    {downloadingPhoto === photo.file ? (
                      <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-600 rounded-full animate-spin" />
                    ) : (
                      <Download className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                    )}
                  </div>
                  <div className="space-y-1 text-gray-600">
                    <p>Distance: {photo.distance?.toFixed(2)}km</p>
                    <p>Bearing: {photo.direction.toFixed(1)}°</p>
                    <p>Relative: {photo.relativeBearing?.toFixed(1)}°</p>
                    <p>Direction diff: {photo.directionDiff?.toFixed(1)}°</p>
                    <p>Position: {photo.x?.toFixed(1)}%, {photo.y?.toFixed(1)}%</p>
                    <p>Scale: {photo.scale?.toFixed(2)}</p>
                    <p>Z-Index: {photo.z}</p>
                    {loadingStates[photo.id]?.attempts > 0 && (
                      <p className="text-yellow-600">
                        Retries: {loadingStates[photo.id].attempts}/{MAX_RETRIES}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, useMap, useMapEvents, Circle } from 'react-leaflet';
import { PhotoData, MapState } from '../types';
import { RotateCcw, RotateCw, ArrowLeftCircle, ArrowRightCircle } from 'lucide-react';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Create directional arrow icon
const createDirectionalArrow = (direction: number, color: string) => {
  // Create an SVG with an arrow pointing in the specified direction
  const svg = `
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="10" fill="${color}" fill-opacity="0.2" stroke="${color}" stroke-width="2"/>
      <path 
        transform="rotate(${direction} 12 12)"
        d="M12 6l4 6h-8z"
        fill="${color}"
      />
    </svg>
  `;

  return L.divIcon({
    className: 'photo-direction-arrow',
    html: svg,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
};

interface Props {
  photos: PhotoData[];
  onMapStateChange: (state: MapState) => void;
}

// Calculate visible distance based on zoom level
function calculateVisibleDistance(map: L.Map): number {
  const center = map.getCenter();
  const pointC = map.latLngToContainerPoint(center);
  
  // Get a point 100 pixels to the right of center
  const pointR = L.point(pointC.x + 100, pointC.y);
  
  // Convert back to LatLng
  const latLngR = map.containerPointToLatLng(pointR);
  
  // Calculate the distance between these points
  const distanceKm = center.distanceTo(latLngR) / 1000;
  
  // Scale the distance to match the circle radius (200px)
  return (distanceKm * 2);
}

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
  bearing = (bearing + 360) % 360;
  return bearing;
}

function MapEventHandler({ onMapStateChange, photos }: { onMapStateChange: (state: MapState) => void; photos: PhotoData[] }) {
  const map = useMap();
  const bearingRef = useRef(0);

  const updateMapState = useCallback(() => {
    if (!map) return;
    const center = map.getCenter();
    onMapStateChange({
      center: [center.lat, center.lng],
      zoom: map.getZoom(),
      bearing: bearingRef.current,
      maxDistance: calculateVisibleDistance(map)
    });
  }, [map, onMapStateChange]);

  const rotateBearing = useCallback((degrees: number) => {
    if (!map) return;

    const newBearing = ((bearingRef.current + degrees + 360) % 360);
    bearingRef.current = newBearing;
    
    updateMapState();
  }, [map, updateMapState]);

  const rotateToNextPhoto = useCallback((direction: 'left' | 'right') => {
    if (!map) return;

    const center = map.getCenter();
    const currentBearing = bearingRef.current;
    const maxDistance = calculateVisibleDistance(map);

    // Calculate relative bearings to all photos within the visible range
    const photoBearings = photos
      .map(photo => {
        const distance = calculateDistance(
          center.lat,
          center.lng,
          photo.latitude,
          photo.longitude
        );

        // Skip photos outside the visible range
        if (distance > maxDistance) {
          return null;
        }

        const bearing = calculateBearing(
          center.lat,
          center.lng,
          photo.latitude,
          photo.longitude
        );
        
        // Calculate relative bearing (-180 to 180)
        let relativeBearing = ((bearing - currentBearing + 180 + 360) % 360) - 180;
        
        // For right rotation, we want the next photo clockwise
        // For left rotation, we want the next photo counterclockwise
        if (direction === 'right') {
          // If the relative bearing is negative, add 360 to make it positive for comparison
          if (relativeBearing < 0) relativeBearing += 360;
        } else {
          // If the relative bearing is positive, subtract 360 to make it negative for comparison
          if (relativeBearing > 0) relativeBearing -= 360;
        }

        return {
          photo,
          bearing,
          relativeBearing,
          distance
        };
      })
      .filter((item): item is NonNullable<typeof item> => 
        item !== null && (
          direction === 'right' ? 
            item.relativeBearing > 0 : // For right rotation, find positive relative bearings
            item.relativeBearing < 0   // For left rotation, find negative relative bearings
        )
      )
      .sort((a, b) => 
        direction === 'right' ?
          a.relativeBearing - b.relativeBearing : // Sort ascending for right rotation
          b.relativeBearing - a.relativeBearing   // Sort descending for left rotation
      );

    if (photoBearings.length > 0) {
      const nextPhoto = photoBearings[0];
      const rotationNeeded = nextPhoto.relativeBearing;
      rotateBearing(direction === 'right' ? rotationNeeded : -rotationNeeded);
    }
  }, [map, photos, rotateBearing]);

  // Expose functions to window for button access
  (window as any).rotateBearing = rotateBearing;
  (window as any).rotateToNextPhoto = rotateToNextPhoto;

  useMapEvents({
    moveend: updateMapState,
    zoomend: updateMapState,
  });

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        rotateBearing(-5);
      } else if (e.key === 'ArrowRight') {
        rotateBearing(5);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [rotateBearing]);

  return null;
}

function VisibilityCircle({ center, maxDistance }: { center: [number, number]; maxDistance: number }) {
  return (
    <Circle
      center={center}
      radius={maxDistance * 1000} // Convert km to meters
      pathOptions={{
        color: '#4A90E2',
        fillColor: '#4A90E2',
        fillOpacity: 0.1,
        weight: 1
      }}
    />
  );
}

function PhotoMarkers({ photos, bearing }: { photos: PhotoData[]; bearing: number }) {
  const map = useMap();
  const initialFitDone = useRef(false);

  useEffect(() => {
    if (photos.length > 0 && !initialFitDone.current && map) {
      const validPhotos = photos.filter(
        photo => !isNaN(photo.latitude) && !isNaN(photo.longitude)
      );

      if (validPhotos.length > 0) {
        const bounds = L.latLngBounds(validPhotos.map(p => [p.latitude, p.longitude]));
        map.fitBounds(bounds, { padding: [50, 50] });
        initialFitDone.current = true;
      }
    }
  }, [photos, map]);

  return (
    <>
      {photos.map(photo => {
        if (isNaN(photo.latitude) || isNaN(photo.longitude)) {
          return null;
        }

        // Calculate the difference between the viewer's bearing and the photo's direction
        let bearingDiff = ((photo.direction - bearing + 360) % 360);
        if (bearingDiff > 180) bearingDiff = bearingDiff - 360;

        // Choose color based on bearing difference
        let color;
        if (Math.abs(bearingDiff) <= 60) {
          color = '#4CAF50'; // Green for in view
        } else if (Math.abs(bearingDiff) >= 150) {
          color = '#F44336'; // Red for opposite direction
        } else {
          color = '#FF9800'; // Orange for out of view
        }

        return (
          <Marker
            key={photo.id}
            position={[photo.latitude, photo.longitude]}
            icon={createDirectionalArrow(photo.direction, color)}
            title={`Photo at ${photo.latitude.toFixed(6)}, ${photo.longitude.toFixed(6)}
Direction: ${photo.direction.toFixed(1)}°
Relative to viewer: ${bearingDiff.toFixed(1)}°`}
          />
        );
      })}
    </>
  );
}

function FOVOverlay({ bearing }: { bearing: number }) {
  const width = 300;
  const height = 300;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = 100; // Radius of the circle
  const arrowLength = radius - 20; // Length of the direction arrow

  // Calculate arrow endpoint using bearing
  const radians = (bearing - 90) * Math.PI / 180; // -90 to point up at 0 degrees
  const arrowX = centerX + Math.cos(radians) * arrowLength;
  const arrowY = centerY + Math.sin(radians) * arrowLength;

  return (
    <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 30000 }}>
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          className="transition-transform duration-200"
        >
          {/* Draw the circle */}
          <circle
            cx={centerX}
            cy={centerY}
            r={radius}
            fill="rgba(74, 144, 226, 0.1)"
            stroke="rgb(74, 144, 226)"
            strokeWidth="2"
          />

          {/* Draw the direction arrow */}
          <line
            x1={centerX}
            y1={centerY}
            x2={arrowX}
            y2={arrowY}
            stroke="rgb(74, 144, 226)"
            strokeWidth="3"
            markerEnd="url(#arrowhead)"
          />

          {/* Arrow head definition */}
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="9"
              refY="3.5"
              orient="auto"
            >
              <polygon
                points="0 0, 10 3.5, 0 7"
                fill="rgb(74, 144, 226)"
              />
            </marker>
          </defs>

          {/* Add a small dot at the center */}
          <circle
            cx={centerX}
            cy={centerY}
            r="3"
            fill="rgb(74, 144, 226)"
          />
        </svg>
      </div>
    </div>
  );
}

export function Map({ photos, onMapStateChange }: Props) {
  const [bearing, setBearing] = useState(0);
  const [mapState, setMapState] = useState<MapState>({
    center: [51.505, -0.09],
    zoom: 13,
    bearing: 0,
    maxDistance: 2
  });

  const handleMapStateChange = useCallback((state: MapState) => {
    setBearing(state.bearing);
    setMapState(state);
    onMapStateChange(state);
  }, [onMapStateChange]);

  return (
    <div className="relative w-full h-full">
      <MapContainer
        center={[51.505, -0.09]}
        zoom={13}
        className="w-full h-full"
      >
        <MapEventHandler onMapStateChange={handleMapStateChange} photos={photos} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <VisibilityCircle center={mapState.center} maxDistance={mapState.maxDistance} />
        <PhotoMarkers photos={photos} bearing={bearing} />
      </MapContainer>
      
      <FOVOverlay bearing={bearing} />
      
      <div className="absolute bottom-4 left-4 flex gap-2">
        <button
          onClick={() => (window as any).rotateToNextPhoto('left')}
          className="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
          title="Rotate to next photo on the left"
          style={{ zIndex: 30000 }}
        >
          <ArrowLeftCircle className="w-5 h-5 text-gray-700" />
        </button>
        <button
          onClick={() => (window as any).rotateBearing(-15)}
          className="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
          title="Rotate view 15° counterclockwise"
          style={{ zIndex: 30000 }}
        >
          <RotateCcw className="w-5 h-5 text-gray-700" />
        </button>
        <button
          onClick={() => (window as any).rotateBearing(15)}
          className="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
          title="Rotate view 15° clockwise"
          style={{ zIndex: 30000 }}
        >
          <RotateCw className="w-5 h-5 text-gray-700" />
        </button>
        <button
          onClick={() => (window as any).rotateToNextPhoto('right')}
          className="p-2 bg-white rounded-full shadow-lg hover:bg-gray-100 transition-colors"
          title="Rotate to next photo on the right"
          style={{ zIndex: 30000 }}
        >
          <ArrowRightCircle className="w-5 h-5 text-gray-700" />
        </button>
      </div>

      <div className="absolute bottom-4 right-4 bg-white p-2 rounded shadow">
        <p className="text-sm">Use ← → arrow keys or buttons to rotate the view direction</p>
      </div>
    </div>
  );
}
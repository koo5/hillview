# Hillview Frontend Architecture Design

## Overview
Hillview is a web-based photo mapping application with support for multiple photo sources, real-time map interactions, and mobile capabilities via Tauri.

**Development Environment:** This project uses Bun as the package manager and runtime instead of npm.

## Core Architecture

### 1. Data Layer
```
Photo Sources → State Management → Processing Layer → Presentation Layer
```

#### Photo Sources
- **Hillview Server** - Main photo database via JSON API (`hillview` source)
- **Mapillary** - Street-view photos from Mapillary API (`mapillary` source)  
- **Device Photos** - Local photos with GPS metadata (`device` source)

*Note: There is no separate 'User Uploads' source - user photos are handled within the hillview source.*

#### State Management (Svelte Stores)
- **Spatial State** - Map center, zoom, bounds
- **Visual State** - Bearing, view direction
- **Photo Sources** - Configuration and raw photo data
- **Processed Data** - Filtered and indexed photos

### 2. Processing Layer (Web Workers)

#### Photo Worker (`new.worker.ts`)
**Responsibilities:**
- Load photos from all configured sources
- Spatial indexing and filtering
- Real-time bounds-based filtering
- Photo prioritization and sorting
- Source merging and deduplication

**Architecture:**
```typescript
// Worker handles all heavy processing and data loading
class PhotoWorker {
  // Data loading - Worker loads JSON directly, not frontend
  loadFromSources(sources: SourceConfig[])
  
  // Spatial operations
  updateBounds(bounds: Bounds)
  getPhotosInBounds(): PhotoData[]
  
  // Filtering and sorting
  filterBySource(sourceIds: string[])
  sortByBearing() // Returns bearing-sorted array for efficient lookups (no parameters)
}
```

**Key Architecture Principle:** The worker loads the JSON data directly, not the frontend thread calling worker methods. The worker is responsible for all photo loading, filtering, and merging.

#### Photo Navigation Logic
```typescript
// Frontend derives navigation from bearing-sorted array
const bearingSortedPhotos = photosInArea; // Already sorted by worker via sortByBearing()
const currentBearing = visualState.bearing;

// Find the photo closest to current bearing
const photoInFrontIndex = findClosestPhotoIndex(bearingSortedPhotos, currentBearing);
const photoInFront = bearingSortedPhotos[photoInFrontIndex];

// photosToLeft and photosToRight are lists of photos relative to photoInFront
const photosToLeft = bearingSortedPhotos.slice(0, photoInFrontIndex);
const photosToRight = bearingSortedPhotos.slice(photoInFrontIndex + 1);
```

**Navigation Architecture Notes:**
- No `sortByDistance()` - maybe only `sortByBearing()` for frontend lookups
- `sortByBearing()` takes no parameters - creates a bearing-sorted array for efficient lookups
- No `findPhotoAtBearing(bearing: number)` function - just `photosToLeft`/`photosToRight` as lists
- Navigation uses pre-sorted arrays rather than bearing-based searches

### 3. Presentation Layer

#### Map System
- **Leaflet Integration** - Core mapping functionality
- **Optimized Markers** - Efficient marker rendering system
- **Photo Overlays** - Display photos on map
- **Interactive Controls** - Zoom, pan, rotate

#### Photo Gallery
- **Reactive Display** - Updates with map movement
- **Photo Navigation** - Directional photo browsing
- **Detail Views** - Full-size photo display

## Rendering Architecture

### 1. Map Rendering Pipeline

```
Spatial State → Worker Filtering → Marker Creation → DOM Updates
```

#### Optimized Marker System (`optimizedMarkers.ts`)
- **Marker Pooling** - Reuse marker instances
- **Pre-rendered Sprites** - Arrow atlas for directions
- **Efficient Updates** - Only update changed markers
- **CSS-based Styling** - Fast visual updates

#### Performance Optimizations
- **Web Worker Processing** - Keep main thread responsive
- **Spatial Indexing** - Fast bounds-based queries
- **Marker Recycling** - Minimize DOM manipulations
- **Atlas Textures** - Batch sprite rendering

### 2. State Flow Architecture

#### Reactive State System
```typescript
// Worker-centric data flow
sources → worker loads JSON → worker filters → photosInArea → markers

// Visual state for immediate updates  
visualState → bearing → photo navigation lookups (no worker needed)
```

#### Store Dependencies
```
sources (configuration changes)
└── triggers worker to load JSON data directly
    └── worker filters and merges all sources
        └── spatialState bounds updates trigger worker filtering
            └── photosInArea updated (bearing-sorted via sortByBearing())
                └── visiblePhotos computed
                    └── map markers updated

visualState (bearing)
└── immediate marker color updates
└── photo navigation calculations (lookup into sorted array)
    └── photoInFront, photosToLeft, photosToRight derived
```

## Current Implementation Issue

**Problem:** Photos load into `hillview_photos` store (3834 photos) but worker has 0 photos, resulting in 0 map markers.

**Root Cause:** Frontend loads photos into stores but never sends them to worker. The architecture should have the worker load photos directly from sources.

**Solution:** Refactor so worker loads JSON data directly from configured sources, becoming the single source of truth for all photo data.


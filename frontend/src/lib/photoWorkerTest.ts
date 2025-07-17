import { photoWorkerService } from './photoWorkerService';
import { LatLng } from 'leaflet';

// Simple test function to verify web worker functionality
export async function testPhotoWorker() {
  console.log('Testing PhotoWorkerService...');
  
  try {
    // Initialize the service
    await photoWorkerService.initialize();
    console.log('✓ PhotoWorkerService initialized');
    
    // Create test photos
    const testPhotos = [
      {
        id: 'test1',
        source_type: 'hillview',
        file: 'test1.jpg',
        url: 'test1.jpg',
        coord: new LatLng(50.0617, 14.5146),
        bearing: 45,
        altitude: 100,
        source: { id: 'hillview' }
      },
      {
        id: 'test2',
        source_type: 'hillview',
        file: 'test2.jpg',
        url: 'test2.jpg',
        coord: new LatLng(50.0618, 14.5147),
        bearing: 90,
        altitude: 110,
        source: { id: 'hillview' }
      },
      {
        id: 'test3',
        source_type: 'mapillary',
        file: 'test3.jpg',
        url: 'test3.jpg',
        coord: new LatLng(50.0619, 14.5148),
        bearing: 135,
        altitude: 120,
        source: { id: 'mapillary' }
      }
    ];
    
    // Load test photos
    await photoWorkerService.loadPhotos(testPhotos);
    console.log('✓ Test photos loaded');
    
    // Test bounds update
    const testBounds = {
      top_left: new LatLng(50.0620, 14.5145),
      bottom_right: new LatLng(50.0616, 14.5149)
    };
    
    await photoWorkerService.updateMapBounds(testBounds);
    console.log('✓ Map bounds updated');
    
    // Test source configuration
    const testSources = [
      { id: 'hillview', enabled: true },
      { id: 'mapillary', enabled: true }
    ];
    
    await photoWorkerService.updateSources(testSources);
    console.log('✓ Sources configured');
    
    // Test range update
    await photoWorkerService.updateRange(5000);
    console.log('✓ Range updated');
    
    // Set up callbacks to capture results
    let photosUpdateReceived = false;
    let bearingUpdateReceived = false;
    
    photoWorkerService.onPhotosUpdate((photos) => {
      console.log('✓ Photos update received:', photos.length, 'photos');
      photosUpdateReceived = true;
    });
    
    photoWorkerService.onBearingUpdate((result) => {
      console.log('✓ Bearing update received:', result);
      bearingUpdateReceived = true;
    });
    
    // Test bearing update
    const testCenter = { lat: 50.0617, lng: 14.5146 };
    await photoWorkerService.updateBearingAndCenter(45, testCenter);
    console.log('✓ Bearing updated');
    
    // Give web worker a moment to process
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Check if callbacks were triggered
    if (photosUpdateReceived && bearingUpdateReceived) {
      console.log('✓ All callbacks triggered successfully');
    } else {
      console.log('⚠ Some callbacks not triggered:', { photosUpdateReceived, bearingUpdateReceived });
    }
    
    console.log('✓ PhotoWorkerService test completed successfully');
    return true;
    
  } catch (error) {
    console.error('✗ PhotoWorkerService test failed:', error);
    return false;
  }
}

// Export test function for use in development
(window as any).testPhotoWorker = testPhotoWorker;
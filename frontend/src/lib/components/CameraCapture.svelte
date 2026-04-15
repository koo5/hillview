<script lang="ts">
	import {Car, ArrowRight, Compass} from 'lucide-svelte';
	import {createEventDispatcher, onDestroy, onMount} from 'svelte';
	import {TAURI} from '$lib/tauri';
	import {invoke} from '@tauri-apps/api/core';
	import {get} from 'svelte/store';
	import {playShutterSound} from '$lib/utils/shutterSound';
	import {app, mockCamera, fakeCamera} from "$lib/data.svelte.js";
	import DualCaptureButton from './DualCaptureButton.svelte';
	import CaptureQueueStatus from './CaptureQueueStatus.svelte';
	import CaptureQueueIndicator from './CaptureQueueIndicator.svelte';
	import CameraOverlay from './CameraOverlay.svelte';
	import AutoUploadPrompt from './AutoUploadPrompt.svelte';
	import VerticalSlider from './VerticalSlider.svelte';
	import {captureQueue} from '$lib/captureQueue';
	import {injectPlaceholder, removePlaceholder} from '$lib/placeholderInjector';
	import {generatePhotoId, type PlaceholderLocation} from '$lib/utils/placeholderUtils';
	import {bearingMode, bearingState, spatialState} from '$lib/mapState';
	import {needsCalibration, shouldShowSwitchToCarModeHint, shouldShowBearingTrackingHint, shouldShowLocationTrackingHint, hideBearingTrackingHint, hideLocationTrackingHint} from '$lib/hints.svelte';
	import {showCalibrationView} from '$lib/data.svelte.js';
	import {createPermissionManager} from '$lib/permissionManager';
	import {
		availableCameras,
		selectedCameraId,
		selectedResolution,
		cameraEnumerationSupported,
		enumerateCameraDevices,
		getCameraSupportedResolutions,
		getPreferredBackCamera,
		type CameraDevice,
		type Resolution
	} from '$lib/cameraDevices.svelte.js';
	import {tauriCamera, isCameraPermissionCheckAvailable} from '$lib/tauri';
	import {addPluginListener, type PluginListener} from '@tauri-apps/api/core';

	// Store to track which cameras are loading resolutions
	import {writable} from 'svelte/store';
	import {
		deviceOrientationExif, relativeOrientationExif,
		type ExifOrientation
	} from "$lib/deviceOrientationExif";
	import {enableBearingTracking, selectBearingMode} from "$lib/bearingTracking";
	import {enableLocationTracking} from "$lib/locationManager";
	import CompassButtonInner from "$lib/components/CompassButtonInner.svelte";
	import LocationButtonInner from "$lib/components/LocationButtonInner.svelte";


	const dispatch = createEventDispatcher();


	const permissionManager = createPermissionManager('camera');

	// Store unlisten functions for cleanup
	let cameraPermissionUnlisten: PluginListener | null = null;
	let deviceOrientationUnlisten: PluginListener | null = null;

	// show or hide the whole capture UI, parent component controls this
	export let show = false;


	// updated with $bearingState && $spatialState
	let locationData: {
		latitude?: number;
		longitude?: number;
		altitude?: number | null;
		accuracy?: number;
		bearing?: number | null;
		location_source: 'gps' | 'map';
		bearing_source: string;
	} | null = null;


	// TODO - this should be set if location tracking fails, but we need to figure out the exact semantics
	//  - we know that location tracking is automatically enabled when the camera modal is opened,
	// and the location tracking service should be able to produce errors if it can't get a fix.
	// but it should be nulled when location is set by map panning.
	let locationError: string | null = null;

	// TODO - this is probably redundant
	let locationReady = false;


	let video: HTMLVideoElement;

	let stream: MediaStream | null = null;
	let facing: 'user' | 'environment' = 'environment';
	let cameraReady = false;
	let cameraError: string | null = null;
	let zoomSupported = false;
	let zoomLevel = 1;
	let minZoom = 1;
	let maxZoom = 1;
	let videoTrack: MediaStreamTrack | null = null;

	// Focus distance state
	let focusDistanceSupported = false;
	let focusDistance = 1;
	let minFocusDistance = 0;
	let maxFocusDistance = 1;

	// Tap-to-focus state (actually tap-to-meter for exposure)
	let focusSupported = false;
	let focusIndicator: { x: number; y: number; visible: boolean } = { x: 0, y: 0, visible: false };
	let focusTimeout: ReturnType<typeof setTimeout> | null = null;
	let wasShowingBeforeHidden = false;
	let permissionCheckInterval: number | null = null;
	let cameraPermissionPollInterval: ReturnType<typeof setInterval> | null = null;
	let hasRequestedPermission = false;
	let retryCount = 0;
	let maxRetries = 5;
	let retryDelay = 1000; // Start with 1 second
	let retryTimeout: number | null = null;
	let permissionRetryInterval: number | null = null;
	let showCameraSelector = false;
	let photoCapturedCount = 0; // Track captures for auto-upload prompt
	let switchingCamera = false; // Flag to prevent automatic startup during manual camera switching
	let isBlinking = false; // Flag for camera blink effect
	let absoluteOrientationSensor: AbsoluteOrientationSensor | null = null;
	let showCalibrationHint: boolean = false;

	let blinkTimeout: ReturnType<typeof setTimeout> | null = null;
	let calibrationHintTimeout: ReturnType<typeof setTimeout> | null = null;

	// Mock camera state
	let mockCanvas: HTMLCanvasElement;
	const resolutionsLoading = writable<Set<string>>(new Set());

	function triggerCameraBlink() {
		isBlinking = true;
		if (blinkTimeout) {
			clearTimeout(blinkTimeout);
		}
		blinkTimeout = setTimeout(() => {
			isBlinking = false;
			blinkTimeout = null;
		}, 50); // 50ms blink duration
	}

	async function checkCameraPermission(): Promise<PermissionState | null> {
		try {
			if ('permissions' in navigator && 'query' in navigator.permissions) {
				const result = await navigator.permissions.query({name: 'camera' as PermissionName});
				return result.state;
			}
		} catch (error) {
			console.log('🢄Permission API not supported or error:', error);
		}
		return null;
	}


	function scheduleRetry() {
		if (retryTimeout) {
			clearTimeout(retryTimeout);
		}

		if (retryCount < maxRetries && show) {
			retryCount++;
			const delay = Math.min(retryDelay * retryCount, 5000); // Cap at 5 seconds
			console.log(`Scheduling camera retry ${retryCount}/${maxRetries} in ${delay}ms`);

			retryTimeout = window.setTimeout(() => {
				if (show && !stream) {
					startCamera();
				}
			}, delay);
		}
	}

	let needsPermission = false;
	let needsStoragePermission = false;
	let storagePermissionChecked = true;

	async function checkStoragePermission() {
		if (!TAURI || storagePermissionChecked) return true;

		try {
			console.log('🢄[STORAGE] Checking storage permission...');
			const permissionStatus = await invoke('plugin:hillview|check_tauri_permissions');
			console.log('🢄[STORAGE] Permission status:', JSON.stringify(permissionStatus));

			// Check if we have write_external_storage permission
			if (permissionStatus && typeof permissionStatus === 'object' && 'write_external_storage' in permissionStatus) {
				const writePermission = (permissionStatus as any).write_external_storage;
				const hasPermission = writePermission === 'Granted';
				needsStoragePermission = !hasPermission;
				storagePermissionChecked = true;
				console.log('🢄[STORAGE] Storage permission granted:', hasPermission);
				return hasPermission;
			}

			// If permission field not found, assume we need to request it
			needsStoragePermission = true;
			storagePermissionChecked = true;
			return false;
		} catch (error) {
			console.warn('🢄[STORAGE] Failed to check storage permission:', error);
			// On error, assume permission is available (for non-Android or fallback)
			storagePermissionChecked = true;
			return true;
		}
	}

	async function requestStoragePermission() {
		if (!TAURI) return;

		try {
			console.log('🢄[STORAGE] Requesting storage permission...');
			const result = await invoke('plugin:hillview|request_tauri_permission', {
				permission: 'write_external_storage'
			});
			console.log('🢄[STORAGE] Permission request result:', result);

			// Check if permission was granted
			const granted = result === 'Granted' || result === 'granted';
			needsStoragePermission = !granted;

			if (granted) {
				console.log('🢄[STORAGE] Storage permission granted, checking camera...');
				// Now that storage permission is granted, proceed to camera check
				checkAndStartCamera();
			}
		} catch (error) {
			console.error('🢄[STORAGE] Failed to request storage permission:', error);
		}
	}

	async function checkAndStartCamera() {
		console.log('🢄[CAMERA] Checking camera permission before auto-start...');

		// Check camera permission status using Tauri if available
		if (isCameraPermissionCheckAvailable() && tauriCamera) {
			const hasPermission = await tauriCamera.checkCameraPermission();
			console.log('🢄[CAMERA] Camera permission status from Tauri:', hasPermission);

			if (hasPermission) {
				console.log('🢄[CAMERA] Permission granted, starting camera immediately');
				await startCamera();
				return;
			} else {
				console.log('🢄[CAMERA] Permission not granted, showing Enable Camera button');
				cameraError = 'Camera access required';
				needsPermission = true;
				return;
			}
		}

		// Try to acquire permission lock first
		const lockAcquired = await permissionManager.acquireLock();
		if (!lockAcquired) {
			console.log('🢄[CAMERA] Permission system busy (location tracking?), will retry later');
			// Schedule retry with interval
			if (!permissionRetryInterval) {
				permissionRetryInterval = window.setInterval(() => {
					if (show && !stream && !cameraReady) {
						checkAndStartCamera();
					} else {
						// Clean up interval if conditions no longer apply
						if (permissionRetryInterval) {
							clearInterval(permissionRetryInterval);
							permissionRetryInterval = null;
						}
					}
				}, 1000);
			}
			return;
		}

		// Clear retry interval since we successfully acquired the lock
		if (permissionRetryInterval) {
			clearInterval(permissionRetryInterval);
			permissionRetryInterval = null;
		}

		await startCamera();

		await permissionManager.releaseLock();

	}

	async function startCamera() {
		console.log('🢄[CAMERA] Starting camera...');
		try {
			// Check for camera support
			if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
				throw new Error('Camera API not supported');
			}

			// Stop any existing stream
			if (stream) {
				console.log('🢄[CAMERA] Stopping existing stream');
				stopStream();
			}

			// Clear any previous errors
			cameraError = null;

			// Mark that we're about to request permission
			hasRequestedPermission = true;

			// Use probe-then-enumerate pattern for better compatibility
			let constraints: MediaStreamConstraints;

			// Check for saved resolution, default to 1440p if none saved
			const savedResolution = get(selectedResolution);
			const targetWidth = savedResolution?.width || 2560;

			// Use saved resolution or 1440p default
			constraints = {
				video: {
					facingMode: {ideal: facing},
					width: {ideal: targetWidth},
					frameRate: 10
				}
			};
			console.log('🢄[CAMERA] Probing with resolution width', targetWidth, 'for initial permission:', facing, 'constraints:', JSON.stringify(constraints));

			try {
				stream = await navigator.mediaDevices.getUserMedia(constraints);
				console.log('🢄[CAMERA] Got media stream:', stream);
			} catch (constraintError) {
				// If we get OverconstrainedError, try with absolute minimal constraints
				if (constraintError instanceof DOMException && constraintError.name === 'OverconstrainedError') {
					console.log('🢄[CAMERA] Constraints failed, retrying with absolute minimal constraints');

					// Clear any problematic resolution
					const currentResolution = get(selectedResolution);
					if (currentResolution) {
						selectedResolution.set(null);
					}

					// Retry with absolutely minimal constraints
					const fallbackConstraints = {
						video: {
							frameRate: 10
						}
					};

					console.log('🢄[CAMERA] Retrying with minimal constraints:', fallbackConstraints);
					stream = await navigator.mediaDevices.getUserMedia(fallbackConstraints);
					console.log('🢄[CAMERA] Got media stream with minimal constraints:', stream);
				} else {
					// Re-throw if it's not a constraint issue
					throw constraintError;
				}
			}

			if (video) {
				console.log('🢄[CAMERA] Setting video source');

				// Set video attributes for mobile compatibility
				video.muted = true;  // Mobile autoplay safety
				video.setAttribute('playsinline', 'true');
				video.srcObject = stream;

				// Wait for metadata to load
				await new Promise((resolve) => {
					video.onloadedmetadata = () => {
						console.log('🢄[CAMERA] Video metadata loaded');
						resolve(undefined);
					};
				});

				await video.play();
				//console.log('🢄[CAMERA] Video playing - clearing error state');
				//console.log('🢄[CAMERA] Before clear: cameraError =', cameraError, 'needsPermission =', needsPermission, 'cameraReady =', cameraReady);

				// Playwright synthetic fallback: if the fake device produces 0x0 frames,
				// generate a canvas-based MediaStream so capture still works in tests.
				if ((navigator as any).webdriver && video.videoWidth === 0 && video.videoHeight === 0) {
					console.log('🢄[CAMERA] Playwright detected with 0x0 video, creating synthetic stream');
					const synCanvas = document.createElement('canvas');
					synCanvas.width = 640;
					synCanvas.height = 480;
					const ctx = synCanvas.getContext('2d')!;
					ctx.fillStyle = '#226688';
					ctx.fillRect(0, 0, 640, 480);
					ctx.fillStyle = '#ffffff';
					ctx.font = '24px sans-serif';
					ctx.fillText('Playwright fake camera', 160, 240);
					const synStream = synCanvas.captureStream(1);
					stream!.getTracks().forEach(t => t.stop());
					stream = synStream;
					video.srcObject = synStream;
					await video.play();
				}

				cameraReady = true;
				cameraError = null;
				needsPermission = false;
				retryCount = 0; // Reset retry count on success
				//console.log('🢄[CAMERA] After clear: cameraError =', cameraError, 'needsPermission =', needsPermission, 'cameraReady =', cameraReady);

				// Reset permission request flag on success
				hasRequestedPermission = false;

				// Release permission lock on success
				await permissionManager.releaseLock();

				// Clear any pending retries
				if (retryTimeout) {
					clearTimeout(retryTimeout);
					retryTimeout = null;
				}

				// Stop camera permission polling since camera stream is verified working
				if (cameraPermissionPollInterval) {
					console.log('🢄[CAMERA] Camera stream verified working - stopping permission polling interval');
					clearInterval(cameraPermissionPollInterval);
					cameraPermissionPollInterval = null;
				}

				// Always enumerate cameras for the selector (after permission granted)
				console.log('🢄[CAMERA] Enumerating cameras and selecting best back camera');

				try {
					//console.log('🢄[CAMERA] Starting camera enumeration...');
					const cameras = await enumerateCameraDevices();
					console.log('🢄[CAMERA] Camera enumeration completed. Found cameras:', cameras.length);
					console.log('🢄[CAMERA] Available cameras:', JSON.stringify(
						cameras.map(c => ({label: c.label, id: c.deviceId.slice(0, 8) + '...'}))));
					console.log('🢄[CAMERA] cameraEnumerationSupported:', get(cameraEnumerationSupported));
					console.log('🢄[CAMERA] availableCameras store length:', get(availableCameras).length);

					// Find which camera we're actually using and sync selectedCameraId
					let actualDeviceId: string | null = null;
					if (videoTrack) {
						const settings = videoTrack.getSettings();
						actualDeviceId = settings.deviceId || null;
						console.log('🢄[CAMERA] Actually using camera device:', actualDeviceId?.slice(0, 8) + '...');
					}

					// Find the camera that matches what we're actually using
					const activeCamera = actualDeviceId ? cameras.find(c => c.deviceId === actualDeviceId) : null;
					if (activeCamera) {
						console.log('🢄[CAMERA] Syncing selectedCameraId with actually active camera:', activeCamera.label);
						selectedCameraId.set(activeCamera.deviceId);
					} else {
						// Fallback: just pick the first back camera if we can't determine which one is active
						const bestCamera = getPreferredBackCamera(cameras);
						if (bestCamera) {
							console.log('🢄[CAMERA] Fallback: Setting selectedCameraId to best back camera:', bestCamera.label);
							selectedCameraId.set(bestCamera.deviceId);
						} else {
							console.log('🢄[CAMERA] No suitable back camera found');
							selectedCameraId.set(null);
						}
					}

					// Keep any stored resolution for next startup
				} catch (error) {
					console.log('🢄[CAMERA] Camera enumeration failed, but stream is working:', error);
				}

				detectCameraCapabilities();

				requestAnimationFrame(() => {
					doCalibrationHint();
				});
			} else {
				console.error('🢄[CAMERA] Video element not found!');
				throw new Error('Video element not available');
			}
		} catch (error) {
			console.error('🢄[CAMERA] Camera error:', error);
			cameraError = error instanceof Error ? error.message : 'Failed to access camera';
			cameraReady = false;

			// Check if this is a permission error
			if (error instanceof DOMException &&
				(error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError')) {
				hasRequestedPermission = true;
				console.log('🢄[CAMERA] Permission denied by user');
				// Release lock - permission dialog is done, user can try again later
				await permissionManager.releaseLock();
			} else {
				// For non-permission errors, release lock and schedule a retry
				await permissionManager.releaseLock();
				scheduleRetry();
			}
		}
	}


	async function setZoom(level: number) {
		if (!videoTrack || !zoomSupported) return;

		try {
			await videoTrack.applyConstraints({
				advanced: [{zoom: level} as any]
			} as MediaTrackConstraints);
			zoomLevel = level;
		} catch (error) {
			console.error('🢄Failed to set zoom:', error);
		}
	}


	async function setFocusDistance(distance: number) {
		if (!videoTrack || !focusDistanceSupported) return;

		try {
			await videoTrack.applyConstraints({
				advanced: [{
					focusMode: 'manual',
					focusDistance: distance
				} as any]
			} as MediaTrackConstraints);
			focusDistance = distance;
		} catch (error) {
			console.error('📷 Failed to set focus distance:', error);
		}
	}

	function resetCameraCapabilities() {
		videoTrack = null;
		zoomSupported = false;
		zoomLevel = 1;
		minZoom = 1;
		maxZoom = 1;
		focusDistanceSupported = false;
		focusDistance = 1;
		minFocusDistance = 0;
		maxFocusDistance = 1;
		focusSupported = false;
		focusIndicator = { x: 0, y: 0, visible: false };
		if (focusTimeout) {
			clearTimeout(focusTimeout);
			focusTimeout = null;
		}
	}

	function stopStream() {
		if (stream) {
			stream.getTracks().forEach(track => track.stop());
			stream = null;
		}
		resetCameraCapabilities();
	}

	function detectCameraCapabilities() {
		if (!stream || !stream.getVideoTracks) return;

		videoTrack = stream.getVideoTracks()[0];
		if (!videoTrack) return;

		const capabilities = videoTrack.getCapabilities() as any;
		const settings = videoTrack.getSettings() as any;
		console.log('📷 [CAMERA] Video track capabilities:', JSON.stringify(capabilities));

		// Check zoom support
		if ('zoom' in capabilities && capabilities.zoom) {
			zoomSupported = true;
			minZoom = capabilities.zoom.min || 1;
			maxZoom = capabilities.zoom.max || 1;
			zoomLevel = settings.zoom || 1;
		}

		// Check focus distance support (manual focus)
		if ('focusDistance' in capabilities && capabilities.focusDistance) {
			focusDistanceSupported = true;
			minFocusDistance = capabilities.focusDistance.min || 0;
			maxFocusDistance = capabilities.focusDistance.max || 10;
			focusDistance = settings.focusDistance || minFocusDistance;
			console.log('📷 [CAMERA] Focus distance supported:', minFocusDistance, '-', maxFocusDistance, 'm');
		}

		// Check tap-to-meter support (exposure metering via pointsOfInterest)
		if ('focusMode' in capabilities && capabilities.focusMode) {
			focusSupported = capabilities.focusMode.includes('single-shot') || capabilities.focusMode.includes('manual');
			console.log('📷 [CAMERA] Focus modes:', capabilities.focusMode);
		}
	}

	async function handleTapToFocus(event: MouseEvent | TouchEvent) {
		if (!focusSupported || !videoTrack) return;

		// Get tap coordinates relative to video element
		const rect = video.getBoundingClientRect();
		let clientX: number, clientY: number;

		if ('touches' in event) {
			clientX = event.touches[0].clientX;
			clientY = event.touches[0].clientY;
		} else {
			clientX = event.clientX;
			clientY = event.clientY;
		}

		// Calculate normalized coordinates (0-1)
		const x = (clientX - rect.left) / rect.width;
		const y = (clientY - rect.top) / rect.height;

		// Show focus indicator
		focusIndicator = { x: clientX, y: clientY, visible: true };

		// Clear previous timeout
		if (focusTimeout) clearTimeout(focusTimeout);

		try {
			// Apply focus at the tapped point
			await videoTrack.applyConstraints({
				advanced: [{
					focusMode: 'single-shot',
					pointsOfInterest: [{ x, y }]
				} as any]
			});
			console.log('🢄[CAMERA] Focus applied at:', JSON.stringify(
				{ x: x.toFixed(2), y: y.toFixed(2) }));
		} catch (err) {
			console.warn('🢄[CAMERA] Tap-to-focus failed:', err);
		}

		// Hide indicator after animation
		focusTimeout = setTimeout(() => {
			focusIndicator = { ...focusIndicator, visible: false };
		}, 800);
	}

	async function selectCamera(camera: CameraDevice) {
		console.log('🢄[CAMERA] Selecting camera:', camera.label);

		// Set flag to prevent automatic startup from interfering
		switchingCamera = true;

		// Hide the dropdown
		showCameraSelector = false;

		// Set the selected camera in the store
		selectedCameraId.set(camera.deviceId);

		// Clear selected resolution when switching cameras
		selectedResolution.set(null);

		// Always restart camera when switching, regardless of current state
		console.log('🢄[CAMERA] Switching to camera:', camera.label);

		// Stop current stream if it exists
		stopStream();

		cameraReady = false;
		cameraError = null;

		// Start with new camera using device-specific constraints
		try {
			await startCameraWithDevice(camera.deviceId);
		} catch (error) {
			console.error('🢄[CAMERA] Failed to switch camera:', error);
			cameraError = `Failed to switch to ${camera.label}`;
		} finally {
			// Clear the flag once camera switching is complete
			switchingCamera = false;
		}
	}

	async function startCameraWithDevice(deviceId: string, resolution?: Resolution) {
		console.log('🢄[CAMERA] Starting camera with specific device:', deviceId.slice(0, 8) + '...');

		// Clear any previous errors
		cameraError = null;

		let constraints: MediaStreamConstraints;

		if (resolution && resolution.width) {
			// Use specific resolution without device constraint
			constraints = {
				video: {
					facingMode: {ideal: 'environment'},
					width: {ideal: resolution.width}
				}
			};
			console.log('🢄[CAMERA] Using environment camera with width:', resolution.width);
		} else {
			// Use environment camera with 1440p default resolution
			constraints = {
				video: {
					facingMode: {ideal: 'environment'},
					width: {ideal: 2560}
				}
			};
			console.log('🢄[CAMERA] Using environment camera with default 1440p resolution');
		}

		try {
			console.log('🢄[CAMERA] Requesting specific camera with constraints:', JSON.stringify(constraints));
			stream = await navigator.mediaDevices.getUserMedia(constraints);
			console.log('🢄[CAMERA] Got device-specific stream:', stream);

			if (video) {
				console.log('🢄[CAMERA] Video element available, setting video source');
				video.muted = true;
				video.setAttribute('playsinline', 'true');
				video.srcObject = stream;
				console.log('🢄[CAMERA] Video srcObject set, waiting for metadata...');

				await new Promise((resolve, reject) => {
					const timeout = setTimeout(() => {
						console.log('🢄[CAMERA] Metadata loading timeout after 5 seconds');
						reject(new Error('Video metadata loading timeout'));
					}, 5000);

					video.onloadedmetadata = () => {
						console.log('🢄[CAMERA] Video metadata loaded');
						clearTimeout(timeout);
						resolve(undefined);
					};

					video.onerror = (error) => {
						console.log('🢄[CAMERA] Video error:', error);
						clearTimeout(timeout);
						reject(error);
					};
				});

				console.log('🢄[CAMERA] Attempting to play video...');
				await video.play();
				console.log('🢄[CAMERA] Device-specific video playing');
				cameraReady = true;
				cameraError = null;
				needsPermission = false;

				detectCameraCapabilities();
			} else {
				console.error('📷 [CAMERA] Video element not available in startCameraWithDevice!');
				throw new Error('Video element not available');
			}
		} catch (error) {
			console.error('🢄[CAMERA] Device-specific camera error:', error);

			// If device-specific constraints fail, fall back to basic camera
			if (error instanceof DOMException && error.name === 'OverconstrainedError') {
				console.log('🢄[CAMERA] Device constraints failed, falling back to basic camera');
				// Clear problematic selections
				selectedCameraId.set(null);
				if (resolution) {
					selectedResolution.set(null);
				}
				// Restart with basic constraints
				await startCamera();
			} else {
				throw error;
			}
		}
	}

	async function selectResolution(resolution: Resolution) {
		console.log('🢄[CAMERA] Selecting resolution:', resolution.label);

		// Set flag to prevent automatic startup from interfering
		switchingCamera = true;

		// Set the selected resolution in the store
		selectedResolution.set(resolution);

		const currentSelectedId = get(selectedCameraId);
		if (!currentSelectedId) {
			console.log('🢄[CAMERA] No camera selected, cannot apply resolution');
			switchingCamera = false;
			return;
		}

		// Always restart camera when switching resolution
		console.log('🢄[CAMERA] Switching to resolution:', resolution.label);

		// Stop current stream if it exists
		stopStream();

		cameraReady = false;
		cameraError = null;

		// Start with new resolution using device-specific constraints
		try {
			await startCameraWithDevice(currentSelectedId, resolution);
		} catch (error) {
			console.error('🢄[CAMERA] Failed to switch resolution:', error);
			cameraError = `Failed to switch to ${resolution.label}`;
		} finally {
			// Clear the flag once resolution switching is complete
			switchingCamera = false;
		}
	}

	async function handleCapture(event: CustomEvent<{ mode: 'slow' | 'fast' }>) {
		if ((!video && !$fakeCamera) || !cameraReady || !locationData ||
			locationData.latitude === undefined || locationData.longitude === undefined) {
			console.warn('🢄📍 Cannot capture: camera not ready or no location');
			return;
		}

		//console.log('🢄Capture event:', JSON.stringify(event.detail));

		const sharedId = generatePhotoId(); // Generate shared ID for entire pipeline
		const {mode} = event.detail;

		const timestamp = Date.now();
		const captureStartTime = performance.now();

		// Inject placeholder for immediate display
		const validLocation: PlaceholderLocation = {
			latitude: locationData.latitude!,
			longitude: locationData.longitude!,
			altitude: locationData.altitude,
			accuracy: locationData.accuracy || 1,
			bearing: locationData.bearing!,  // Assert non-null since bearingState always provides it
			location_source: locationData.location_source,
			bearing_source: locationData.bearing_source,
		};

		injectPlaceholder(validLocation, sharedId);

		// Dispatch capture start event
		dispatch('captureStart', {
			location: locationData,
			timestamp,
			mode,
			sharedId // Use sharedId instead of temp_id
		});

		console.log(`TIMING 🕐 PHOTO CAPTURE START: ${captureStartTime.toFixed(1)}ms`);

		try {

			// Get ImageData directly from canvas
			const canvasStartTime = performance.now();
			let canvas: HTMLCanvasElement;
			let context: CanvasRenderingContext2D | null;

			if ($fakeCamera && mockCanvas) {
				// Fake camera: draw a fresh frame and use the mock canvas directly
				drawMockFrame();
				canvas = mockCanvas;
				context = canvas.getContext('2d');
			} else {
				canvas = document.createElement('canvas');
				canvas.width = video.videoWidth;
				canvas.height = video.videoHeight;
				context = canvas.getContext('2d');
			}

			if (!context) {
				console.error('🢄Capture error: Unable to get canvas context');
				return;
			}

			// Draw video frame to canvas (skip for fake - already drawn)
			const drawStartTime = performance.now();
			const drawStartTimestamp = Date.now();
			if (!$fakeCamera) {
				context.drawImage(video, 0, 0);
			}

			// mockCamera: overlay timestamp to make each capture unique
			if ($mockCamera && !$fakeCamera) {
				const now = new Date();
				const ms = String(now.getMilliseconds()).padStart(3, '0');
				const timeStr = now.toLocaleTimeString(undefined, { hour12: false }) + '.' + ms;
				context.fillStyle = 'rgba(0, 0, 0, 0.5)';
				context.fillRect(0, 0, canvas.width, 40);
				context.fillStyle = '#00ff88';
				context.font = 'bold 28px monospace';
				context.textAlign = 'left';
				context.textBaseline = 'top';
				context.fillText(timeStr, 8, 8);
			}
			const drawEndTime = performance.now();
			const drawEndTimestamp = Date.now();
			console.log(`🢄handleCapture TIMING: captured_at: ${timestamp}, drawStartTimestamp: ${drawStartTimestamp}, drawEndTimestamp: ${drawEndTimestamp}, drawTime: ${(drawEndTime - drawStartTime).toFixed(1)}ms`);

			// Get ImageData from canvas
			const getDataStartTime = performance.now();
			const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
			const getDataEndTime = performance.now();
			console.log(`TIMING 📊 GET IMAGE DATA: ${(getDataEndTime - getDataStartTime).toFixed(1)}ms, size: ${imageData.data.length} bytes`);

			// Add to capture queue with ImageData
			await captureQueue.add({
				id: sharedId, // Use sharedId for the entire pipeline
				image_data: imageData,
				location: validLocation,
				captured_at: timestamp,
				mode,
				placeholder_id: sharedId, // Use sharedId as placeholder ID too
				orientation_code: get(relativeOrientationExif) // Current device orientation
			});

			// Trigger auto-upload prompt check
			photoCapturedCount++;
			console.log(`🢄photoCapturedCount: ${photoCapturedCount}`);

			const captureEndTime = performance.now();
			console.log(`TIMING ✅ PHOTO CAPTURE COMPLETE: ${(captureEndTime - captureStartTime).toFixed(1)}ms total`);

			triggerCameraBlink();
			playShutterSound();

		} catch (error) {
			const captureErrorTime = performance.now();
			console.log(`TIMING ❌ PHOTO CAPTURE ERROR: ${(captureErrorTime - captureStartTime).toFixed(1)}ms before error`);
			// Get detailed error information
			const errorInfo = {
				name: (error as any)?.name,
				message: (error as any)?.message,
				code: (error as any)?.code,
				stack: (error as any)?.stack
			};
			console.error('🢄Capture error details:', JSON.stringify(errorInfo, null, 2));
			console.error('🢄Capture error object:', error);

			// Remove placeholder on error
			removePlaceholder(sharedId);
		}

	}


	function handleVisibilityChange() {
		if (document.hidden) {
			// App is going to background
			wasShowingBeforeHidden = show && !!stream;
			if (stream) {
				console.log('🢄App going to background, stopping camera');
				stopStream();
				cameraReady = false;
			}
			// Clear any pending retries when going to background
			if (retryTimeout) {
				clearTimeout(retryTimeout);
				retryTimeout = null;
			}
		} else {
			// App is coming back to foreground
			if (wasShowingBeforeHidden && show) {
				console.log('🢄App returning to foreground, restarting camera');
				// Reset retry count for fresh attempt when returning from background
				retryCount = 0;
				cameraError = null;
				needsPermission = false;
				startCamera();
			}
			wasShowingBeforeHidden = false;
		}
	}

	async function handleCameraSelectorToggle() {
		showCameraSelector = !showCameraSelector;

		// If opening the selector, load resolutions for the currently active camera only
		if (showCameraSelector) {

			// Get the actual active camera from the video track, not the stored selection
			let activeDeviceId: string | null = null;
			if (videoTrack) {
				const settings = videoTrack.getSettings();
				activeDeviceId = settings.deviceId || null;
				console.log('🢄[CAMERA] Active camera from video track:', JSON.stringify(activeDeviceId));
			} else {
				console.log('🢄[CAMERA] No active video track found');
			}

			const availableCamerasList = get(availableCameras);

			console.log('🢄[CAMERA] Camera selector opened, loading resolutions for active camera...');
			console.log('🢄[CAMERA] activeDeviceId from video track:', JSON.stringify(activeDeviceId));
			console.log('🢄[CAMERA] availableCameras count:', availableCamerasList.length);
			console.log('🢄[CAMERA] availableCameras IDs:', JSON.stringify(availableCamerasList.map(c => c.deviceId.slice(0, 8) + '...')));
			console.log('🢄[CAMERA] availableCameras full IDs:', JSON.stringify(availableCamerasList.map(c => c.deviceId)));

			// If no cameras have been enumerated yet, trigger enumeration first
			if (availableCamerasList.length === 0) {
				console.log('🢄[CAMERA] No cameras enumerated yet, triggering enumeration...');
				try {
					await enumerateCameraDevices();
					console.log('🢄[CAMERA] Camera enumeration completed from selector');
				} catch (error) {
					console.log('🢄[CAMERA] Camera enumeration failed from selector:', error);
					return;
				}
			}

			if (activeDeviceId) {
				// Refresh the list after potential enumeration
				const refreshedCamerasList = get(availableCameras);
				const activeCamera = refreshedCamerasList.find(cam => cam.deviceId === activeDeviceId);

				if (activeCamera) {
					// Update the stored selectedCameraId to match the actual active camera
					console.log('🢄[CAMERA] Syncing selectedCameraId with active camera:', activeCamera.label);
					selectedCameraId.set(activeDeviceId);
					resolutionsLoading.update(loading => {
						if (!loading.has(activeCamera.deviceId)) {
							// Mark as loading
							const newLoading = new Set(loading);
							newLoading.add(activeCamera.deviceId);
							return newLoading;
						}
						return loading;
					});

					// Load hardcoded resolutions for active camera
					try {
						const resolutions = await getCameraSupportedResolutions(activeCamera.deviceId);
						activeCamera.resolutions = resolutions;
						console.log(`🢄[CAMERA] Found ${resolutions.length} resolutions for active camera: ${activeCamera.label}`);

						// Update the store to trigger UI update
						availableCameras.update(cams => [...cams]);
					} catch (error) {
						console.log(`🢄[CAMERA] Failed to get resolutions for active camera ${activeCamera.label}:`, error);
						activeCamera.resolutions = [];
					} finally {
						// Remove from loading set
						resolutionsLoading.update(loading => {
							const newLoading = new Set(loading);
							newLoading.delete(activeCamera.deviceId);
							return newLoading;
						});
					}
				} else {
					console.log('🢄[CAMERA] Active camera from video track not found in enumerated cameras list');
					console.log('🢄[CAMERA] This might indicate an enumeration issue or the camera was disconnected');
				}
			} else {
				console.log('🢄[CAMERA] No active camera selected, skipping resolution enumeration');
			}
		}
	}

	function handleClickOutside(event: MouseEvent) {
		if (showCameraSelector) {
			const target = event.target as Element;
			const selectorContainer = document.querySelector('.camera-selector-container');

			if (selectorContainer && !selectorContainer.contains(target)) {
				showCameraSelector = false;
			}
		}
	}

	// Try to auto-start camera with permission lock coordination
	$: if (show) {
		if ($fakeCamera) {
			// Fake camera mode - synthetic canvas, no real stream
			if (stream) {
				stopStream();
				cameraReady = false;
			}
			if (mockRafId === null) {
				startMockCamera();
			}
		} else {
			// Real camera mode - stop fake if running
			if (mockRafId !== null) {
				stopMockCamera();
				cameraReady = false;
			}
			if (!stream && !cameraError && !cameraReady && !hasRequestedPermission && !switchingCamera) {
				console.log('🢄[CAMERA] Modal shown, checking storage permission first...');
				retryCount = 0;
				checkStoragePermission().then(hasStorage => {
					if (hasStorage) {
						checkAndStartCamera();
					} else {
						console.log('🢄[STORAGE] Storage permission needed, showing storage permission button');
					}
				});
			}
		}
	} else if (!show && (stream || mockRafId !== null)) {
		// Stop camera when modal closes
		console.log('🢄Modal hidden, stopping camera');
		stopStream();
		stopMockCamera();
		cameraReady = false;
		cameraError = null;
		needsPermission = false;
		hasRequestedPermission = false;
		if (permissionCheckInterval) {
			clearInterval(permissionCheckInterval);
			permissionCheckInterval = null;
		}
		if (retryTimeout) {
			clearTimeout(retryTimeout);
			retryTimeout = null;
		}
		retryCount = 0;
	}

	// Subscribe to bearingState and spatialState to update locationData
	$: if ($bearingState && $spatialState) {
		locationData = {
			latitude: $spatialState.center.lat,
			longitude: $spatialState.center.lng,
			altitude: null,
			accuracy: undefined,
			bearing: $bearingState.bearing,
			location_source: $spatialState.source || 'unknown',
			bearing_source: $bearingState.source || 'unknown',
		};
		locationReady = true;
		locationError = null;
	}

	// Debug: Log camera selector button visibility conditions
	// $: {
	//     console.log('🢄[CAMERA] Button visibility check:');
	//     console.log('🢄[CAMERA]   - cameraEnumerationSupported:', $cameraEnumerationSupported);
	//     console.log('🢄[CAMERA]   - availableCameras.length:', $availableCameras.length);
	//     console.log('🢄[CAMERA]   - show button:', $cameraEnumerationSupported && $availableCameras.length > 0);
	// }


	function updateDeviceOrientationExif(o: ExifOrientation) {
		if (o !== get(deviceOrientationExif)) {
			deviceOrientationExif.set(o);
			console.log('🢄[CAMERA] Device orientation changed, EXIF orientation set to', o);
		}
	}

	;

	function doCalibrationHint()
	{
		showCalibrationHint = true;
		if (calibrationHintTimeout) {
			clearTimeout(calibrationHintTimeout);
		}
		calibrationHintTimeout = setTimeout(() =>
		{
			showCalibrationHint = false;
			calibrationHintTimeout = null;
		}, 4000);
	}

	let mockRafId: number | null = null;

	function startMockCamera() {
		console.log('🢄[CAMERA] Starting mock camera');
		cameraError = null;
		needsPermission = false;
		cameraReady = true;

		function loop() {
			drawMockFrame();
			mockRafId = requestAnimationFrame(loop);
		}
		mockRafId = requestAnimationFrame(loop);
	}

	function drawMockFrame() {
		if (!mockCanvas) return;
		const ctx = mockCanvas.getContext('2d');
		if (!ctx) return;

		const w = mockCanvas.width;
		const h = mockCanvas.height;

		// Background
		ctx.fillStyle = '#1a1a2e';
		ctx.fillRect(0, 0, w, h);

		// Grid lines
		ctx.strokeStyle = 'rgba(100, 100, 200, 0.3)';
		ctx.lineWidth = 1;
		for (let x = 0; x < w; x += 40) {
			ctx.beginPath();
			ctx.moveTo(x, 0);
			ctx.lineTo(x, h);
			ctx.stroke();
		}
		for (let y = 0; y < h; y += 40) {
			ctx.beginPath();
			ctx.moveTo(0, y);
			ctx.lineTo(w, y);
			ctx.stroke();
		}

		// Timestamp
		const now = new Date();
		const ms = String(now.getMilliseconds()).padStart(3, '0');
		const timeStr = now.toLocaleTimeString(undefined, { hour12: false }) + '.' + ms;
		const dateStr = now.toLocaleDateString();

		ctx.fillStyle = '#00ff88';
		ctx.font = 'bold 48px monospace';
		ctx.textAlign = 'center';
		ctx.textBaseline = 'middle';
		ctx.fillText(timeStr, w / 2, h / 2 - 30);

		ctx.fillStyle = '#88aaff';
		ctx.font = '24px monospace';
		ctx.fillText(dateStr, w / 2, h / 2 + 20);

		ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
		ctx.font = '16px monospace';
		ctx.fillText('MOCK CAMERA', w / 2, h / 2 + 60);
	}

	function stopMockCamera() {
		if (mockRafId !== null) {
			cancelAnimationFrame(mockRafId);
			mockRafId = null;
		}
	}

	onMount(async () => {

		document.addEventListener('visibilitychange', handleVisibilityChange);
		document.addEventListener('click', handleClickOutside);

		if (TAURI) {
			try {
				deviceOrientationUnlisten = await addPluginListener('hillview', 'device-orientation', (data: any) => {
					console.log('🢄🔍📡 Received device-orientation event from plugin:', JSON.stringify(data));
					updateDeviceOrientationExif(data.exif_code);
				});
				await invoke('plugin:hillview|cmd', {command: 'start_device_orientation_sensor'});
				await invoke('plugin:hillview|cmd', {command: 'trigger_device_orientation_event'});
			} catch (error) {
				console.warn("🢄[CAMERA] device-orientation error:", error);
			}
		} else if ('AbsoluteOrientationSensor' in window) {
			try {
				console.log('🢄[CAMERA] Initializing AbsoluteOrientationSensor for device orientation...');
				absoluteOrientationSensor = new window.AbsoluteOrientationSensor({
					frequency: 100,
					referenceFrame: "screen"
				});
				absoluteOrientationSensor.addEventListener("reading", () => {
					console.log('🢄[CAMERA] AbsoluteOrientationSensor reading event');
					//DeviceOrientationEvent.webkitCompassHeading?
				});
				absoluteOrientationSensor.addEventListener("error", (error) => {
					console.log(error);
				});
				absoluteOrientationSensor.start();
				console.log('🢄[CAMERA] AbsoluteOrientationSensor started successfully');
			} catch (error) {
				console.warn("🢄[CAMERA]", error);
			}
		} else {
			console.log('🢄[CAMERA] AbsoluteOrientationSensor not available in this browser');
		}


		// Listen for native camera permission granted event
		if (isCameraPermissionCheckAvailable()) {
			cameraPermissionUnlisten = await addPluginListener('hillview', 'camera-permission-granted', async (event) => {
				console.log('🢄[CAMERA] CAMERA PERMISSION Event data:', JSON.stringify(event));

				if (show && cameraError) {
					console.log('🢄[CAMERA] Conditions met - retrying camera after native permission granted');
					cameraError = null;
					needsPermission = false;
					hasRequestedPermission = false;
					retryCount = 0;
					try {
						await startCamera();
						console.log('🢄[CAMERA] startCamera() completed after permission event');
					} catch (err) {
						console.error('🢄[CAMERA] startCamera() failed after permission event:', err);
					}
				} else {
					console.log('🢄[CAMERA] Not retrying camera - show:', show, 'cameraError:', cameraError);
				}
			});

			console.log('🢄[CAMERA] Camera permission event listener setup complete');

		} else {
			console.log('🢄[CAMERA] Camera permission check not available - skipping event listener');
		}

		// Start simple permission polling from Kotlin
		if (isCameraPermissionCheckAvailable() && tauriCamera) {
			cameraPermissionPollInterval = setInterval(async () => {
				const hasPermission = await tauriCamera!.checkCameraPermission();
				if (hasPermission && cameraError === 'Camera access required') {
					console.log('🢄[CAMERA POLL] Permission granted, retrying camera');
					cameraError = null;
					needsPermission = false;
					await startCamera();
				}
			}, 1000);
		}
	});

	onDestroy(() => {
		if (TAURI) {
			invoke('plugin:hillview|cmd', {command: 'stop_device_orientation_sensor'})
				.catch(err => console.warn('🢄[CAMERA] Failed to stop device orientation sensor:', err));
		}
		if (absoluteOrientationSensor) {
			absoluteOrientationSensor.stop();
		}
		stopStream();
		stopMockCamera();
		if (permissionCheckInterval) {
			clearInterval(permissionCheckInterval);
		}
		if (retryTimeout) {
			clearTimeout(retryTimeout);
		}
		if (permissionRetryInterval) {
			clearInterval(permissionRetryInterval);
		}
		if (cameraPermissionPollInterval) {
			clearInterval(cameraPermissionPollInterval);
		}
		if (blinkTimeout) {
			clearTimeout(blinkTimeout);
		}
		if (calibrationHintTimeout) {
			clearTimeout(calibrationHintTimeout);
		}
		if (focusTimeout) {
			clearTimeout(focusTimeout);
		}
		// Properly unregister plugin listeners
		if (deviceOrientationUnlisten) {
			console.log('🢄[CAMERA] Cleaning up device orientation event listener');
			deviceOrientationUnlisten.unregister();
			deviceOrientationUnlisten = null;
		}
		if (cameraPermissionUnlisten) {
			console.log('🢄[CAMERA] Cleaning up camera permission event listener');
			cameraPermissionUnlisten.unregister();
			cameraPermissionUnlisten = null;
		}
		document.removeEventListener('visibilitychange', handleVisibilityChange);
		document.removeEventListener('click', handleClickOutside);
		updateDeviceOrientationExif(1);

		// Clean up permission manager
		permissionManager.cleanup();

	});
</script>

{#if show}
	<div class="camera-container">
		<div class="camera-content">
			<div class="camera-view">
				<!-- Debug: cameraError = {cameraError}, needsPermission = {needsPermission}, cameraReady = {cameraReady} -->

				{#if $fakeCamera}
					<!-- Fake camera canvas (synthetic frames, no real stream) -->
					<canvas
						bind:this={mockCanvas}
						class="camera-video"
						class:blink={isBlinking}
						width="640"
						height="480"
						style:display={(cameraError) ? 'none' : 'block'}
					></canvas>
				{:else}
					<!-- Always render video element so it's available for binding -->
					<video
						bind:this={video}
						class="camera-video"
						class:blink={isBlinking}
						playsinline
						style:display={(cameraError || needsStoragePermission) ? 'none' : 'block'}
						on:click={handleTapToFocus}
						on:touchstart|preventDefault={handleTapToFocus}
					>
						<track kind="captions"/>
					</video>
				{/if}

				<!-- Tap-to-focus indicator -->
				{#if focusIndicator.visible}
					<div
						class="focus-indicator"
						style="left: {focusIndicator.x}px; top: {focusIndicator.y}px;"
					></div>
				{/if}

				{#if needsStoragePermission && storagePermissionChecked}
					<div class="camera-error">
						<p>💾 Storage permission required to save photos</p>
						<button class="retry-button" on:click={requestStoragePermission}>
							Grant Storage Permission
						</button>
					</div>
				{:else if cameraError}
					<div class="camera-error">
						<p>📷 {cameraError}</p>
						<button class="retry-button" on:click={async () => {

                            console.log('🢄[CAMERA] Enable Camera button clicked');

                            // Try native permission request first if available
                            if (isCameraPermissionCheckAvailable() && tauriCamera) {
                                try {
                                    console.log('🢄[CAMERA] Using native permission request');
                                    const permissionResult = await tauriCamera.requestCameraPermission();

                                    if (permissionResult.granted) {
                                        console.log('🢄[CAMERA] Native permission granted, starting camera');
                                        cameraError = null;
                                        needsPermission = false;
                                        hasRequestedPermission = false;
                                        if (permissionCheckInterval) {
                                            clearInterval(permissionCheckInterval);
                                            permissionCheckInterval = null;
                                        }
                                        retryCount = 0;
                                        await startCamera();
                                        return;
                                    } else {
                                        console.log('🢄[CAMERA] Native permission denied:', permissionResult.error);
                                        cameraError = permissionResult.error || 'Camera permission denied';
                                        needsPermission = true;
                                        return;
                                    }
                                } catch (error) {
                                    console.warn('🢄[CAMERA] Native permission request failed, falling back to WebView:', error);
                                }
                            }

                            // Fallback to WebView permission flow
                            console.log('🢄[CAMERA] Using WebView permission flow');

                            // Try to acquire permission lock before starting camera
                            const lockAcquired = await permissionManager.acquireLock();
                            if (!lockAcquired) {
                                console.log('🢄[CAMERA] Permission system busy, cannot start camera right now');
                                return;
                            }

                            cameraError = null;
                            needsPermission = false;
                            hasRequestedPermission = false;
                            if (permissionCheckInterval) {
                                clearInterval(permissionCheckInterval);
                                permissionCheckInterval = null;
                            }
                            retryCount = 0;
                            startCamera();
                        }}
						data-testid="allow-camera-btn">
							{needsPermission ? 'Allow Camera' : 'Try Again'}
						</button>
					</div>
				{/if}

				<!-- Location overlay -->
				{#if !cameraError}
					<CameraOverlay
						{locationData}
						{locationError}
						{locationReady}
						{showCalibrationHint}
					/>
				{/if}

				<!-- Auto-upload prompt (shows after photo capture) -->
				<AutoUploadPrompt
					photoCaptured={photoCapturedCount}
				/>

				<!-- Calibrate Compass button - shows when compass accuracy is low -->
				{#if $needsCalibration}
					<button
						class="calibrate-compass-button"
						on:click={() => showCalibrationView.set(true)}
						data-testid="calibrate-compass-btn"
					>
						Calibrate Compass
					</button>
				{:else if $shouldShowSwitchToCarModeHint}
					<button
						class="switch-to-car-mode-button"
						on:click={() => selectBearingMode('car')}
						data-testid="switch-to-car-mode-btn"
					>
						<div class="hint-title">
<!--							<Car size={16}/>-->
							In a car?
						</div>
						<div class="compass-button-preview target">
							<CompassButtonInner bearingMode="car"/>
						</div>
					</button>
				{/if}

				<!-- Bearing tracking hint -->
				{#if $shouldShowBearingTrackingHint}
					<div class="tracking-hint" data-testid="bearing-tracking-hint">
						<div class="hint-message">
							<span>Turn on bearing tracking?</span>
						</div>
						<button class="compass-button-preview target" on:click={() => enableBearingTracking()} data-testid="enable-bearing-hint">
							<CompassButtonInner bearingMode={$bearingMode}/>
						</button>
						<button
							class="dismiss-hint-btn"
							on:click={() => hideBearingTrackingHint.set(true)}
							data-testid="dismiss-bearing-hint"
						>
							Do not show again
						</button>
					</div>
				{/if}

				<!-- Location tracking hint -->
				{#if $shouldShowLocationTrackingHint}
					<div class="tracking-hint" data-testid="location-tracking-hint">
						<div class="hint-message">
							<span>Turn on location tracking?</span>
						</div>
						<button class="location-button-preview target" on:click={() => enableLocationTracking()} data-testid="enable-location-hint">
							<LocationButtonInner showSpinner={false} />
						</button>
						<button
							class="dismiss-hint-btn"
							on:click={() => hideLocationTrackingHint.set(true)}
							data-testid="dismiss-location-hint"
						>
							Do not show again
						</button>
					</div>
				{/if}
			</div>

			{#if zoomSupported && cameraReady}
				<VerticalSlider
					class="zoom-slider-position"
					id="zoom-slider"
					value={zoomLevel}
					min={minZoom}
					max={maxZoom}
					step={0.1}
					label="{zoomLevel.toFixed(1)}x"
					ariaLabel="Camera zoom"
					on:change={(e) => setZoom(e.detail)}
				/>
			{/if}

			{#if focusDistanceSupported && cameraReady}
				<VerticalSlider
					class="focus-slider-position"
					id="focus-slider"
					value={focusDistance}
					min={minFocusDistance}
					max={maxFocusDistance}
					step={0.01}
					label="focus"
					ariaLabel="Focus distance"
					thumbColor="#4a90e2"
					on:change={(e) => setFocusDistance(e.detail)}
				/>
			{/if}


			<!-- Camera selector button (lower-left) -->
			<div class="camera-selector-container">
				<button
					class="camera-selector-button"
					on:click={handleCameraSelectorToggle}
					aria-label="Select camera"
				>
					📷
				</button>

				{#if showCameraSelector}
					<div class="camera-selector-dropdown">
						{#if $availableCameras.length > 0}
							{#each $availableCameras as camera}
								<div class="camera-group">
									<button
										class="camera-option"
										class:selected={$selectedCameraId === camera.deviceId}
										on:click={() => selectCamera(camera)}
										data-testid="camera-option-{camera.deviceId}"
									>
											<span class="camera-facing">
												{#if camera.facingMode === 'front'}🤳{:else if camera.facingMode === 'back'}📷{:else}📹{/if}
											</span>
										<span class="camera-label">
												{camera.label}
											{#if camera.isPreferred}⭐{/if}
											</span>
									</button>

									{#if $selectedCameraId === camera.deviceId}
										<div class="resolution-options">
											{#if $resolutionsLoading.has(camera.deviceId)}
												<div class="resolution-loading">
													🔄 Loading resolutions...
												</div>
											{:else if camera.resolutions && camera.resolutions.length > 0}
												{#each camera.resolutions as resolution}
													<button
														class="resolution-option"
														class:selected={$selectedResolution?.width === resolution.width}
														on:click={() => selectResolution(resolution)}
														data-testid="resolution-option-{resolution.width}x{resolution.height}"
													>
														{resolution.label}
													</button>
												{/each}
											{:else if camera.resolutions && camera.resolutions.length === 0}
												<div class="resolution-error">
													No resolutions available
												</div>
											{/if}
										</div>
									{/if}
								</div>
							{/each}
						{:else}
							<div class="camera-error-message">
								{#if !$cameraEnumerationSupported}
									<div class="error-icon">⚠️</div>
									<div class="error-text">
										<div class="error-title">Camera enumeration not supported</div>
										<div class="error-subtitle">enumeration failed.</div>
									</div>
								{:else}
									<div class="error-icon">📷</div>
									<div class="error-text">
										<div class="error-title">No cameras found</div>
										<div class="error-subtitle">Make sure camera permissions are granted</div>
									</div>
								{/if}
							</div>
						{/if}
					</div>
				{/if}
			</div>


			{#if !cameraError && !needsPermission}
				<div class="shutter-container">
					<DualCaptureButton
						disabled={!cameraReady || !locationData}
						on:capture={handleCapture}
					/>
				</div>
			{/if}

			{#if $app.debug === 5}
				<div class="queue-status-overlay">
					<CaptureQueueStatus/>
				</div>
			{/if}

			<!-- Capture queue indicator (always visible when queue has items) -->
			<div class="queue-indicator-overlay">
				<CaptureQueueIndicator/>
			</div>
		</div>
	</div>
{/if}

<style>
	.camera-container {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		background: black;
	}

	.camera-content {
		background: linear-gradient(135deg, #000000, #a1a1a1);
		width: 100%;
		height: 100%;
		max-width: 100vw;
		max-height: 100vh;
		display: flex;
		flex-direction: column;
		position: relative;
	}


	.camera-view {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
		overflow: hidden;
	}

	.camera-video {
		width: 100%;
		height: 100%;
		object-fit: contain;
		transition: opacity 0.05s ease-in-out;
	}

	.camera-video.blink {
		opacity: 0.3;
	}

	.focus-indicator {
		position: fixed;
		width: 70px;
		height: 70px;
		border: 2px solid rgba(255, 255, 255, 0.9);
		border-radius: 50%;
		transform: translate(-50%, -50%);
		pointer-events: none;
		z-index: 1003;
		animation: focus-pulse 0.8s ease-out forwards;
	}

	@keyframes focus-pulse {
		0% {
			transform: translate(-50%, -50%) scale(1.5);
			opacity: 0;
			border-width: 3px;
		}
		30% {
			transform: translate(-50%, -50%) scale(1);
			opacity: 1;
			border-width: 2px;
		}
		100% {
			transform: translate(-50%, -50%) scale(0.8);
			opacity: 0;
			border-width: 1px;
		}
	}

	.camera-error {
		text-align: center;
		color: white;
		padding: 2rem;
	}

	.camera-error p {
		margin-bottom: 1rem;
		font-size: 1.1rem;
	}

	.retry-button {
		padding: 0.75rem 1.5rem;
		background: #4a90e2;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 1rem;
		transition: background 0.2s;
	}

	.retry-button:hover {
		background: #3a7bc8;
	}

	.calibrate-compass-button {
		position: absolute;
		bottom: 0px;
		left: 50%;
		transform: translate(-50%, -50%);
		padding: 0.75rem 1rem;
		background: #e24a4a;
		color: white;
		border: none;
		border-radius: 6px;
		cursor: pointer;
		font-size: 1rem;
		transition: background 0.2s;
		z-index: 1010;
	}

	.calibrate-compass-button:hover {
		background: #c83a3a;
	}

	.switch-to-car-mode-button {
		position: absolute;
		bottom: 150px;
		right: 0px;
		padding: 0.175rem 0.1rem;
		background: rgba(180, 0, 0, 0.5);
		backdrop-filter: blur(10px);
		color: white;
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 8px;
		cursor: pointer;
		font-size: 0.9rem;
		transition: background 0.2s;
		z-index: 1010;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
	}

	.switch-to-car-mode-button:hover {
		background: rgba(0, 0, 0, 0.9);
		border-color: rgba(255, 255, 255, 0.4);
	}

	.switch-to-car-mode-button .hint-title {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}

	.camera-selector-container {
		position: absolute;
		z-index: 1003;
		left: calc(0px + var(--safe-area-inset-left, 0px));
		bottom: 6px;
	}

	.shutter-container {
		position: absolute;
		z-index: 50;
		bottom: 6px;
		left: 50%;
		transform: translateX(-50%);
	}

	.camera-selector-button {
		background: rgba(255, 255, 255, 0.2);
		border: none;
		color: white;
		cursor: pointer;
		border-radius: 50%;
		font-size: 1.5rem;
		transition: background 0.2s;
		backdrop-filter: blur(10px);
		border: 1px solid rgba(255, 255, 255, 0.3);
	}

	.camera-selector-button:hover {
		background: rgba(255, 255, 255, 0.3);
	}

	.camera-selector-dropdown {
		position: absolute;
		bottom: 100%;
		left: 0;
		background: rgba(0, 0, 0, 0.9);
		border-radius: 8px;
		min-width: 250px;
		max-width: 350px;
		backdrop-filter: blur(20px);
		border: 1px solid rgba(255, 255, 255, 0.2);
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
		max-height: 400px;
		overflow-y: scroll;
	}

	.camera-group {
		margin-bottom: 0.1rem;
	}

	.camera-group:last-child {
		margin-bottom: 0;
	}

	.camera-option {
		display: flex;
		align-items: center;
		gap: 0.1rem;
		width: 100%;
		padding: 0.1rem;
		background: transparent;
		border: none;
		color: white;
		cursor: pointer;
		border-radius: 6px;
		transition: background 0.2s;
		text-align: left;
	}

	.camera-option:hover {
		background: rgba(255, 255, 255, 0.1);
	}

	.camera-option.selected {
		background: rgba(74, 144, 226, 0.3);
		border: 1px solid rgba(74, 144, 226, 0.5);
	}

	.camera-facing {
		font-size: 1.2rem;
		flex-shrink: 0;
	}

	.camera-label {
		font-size: 0.9rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		flex: 1;
	}

	.resolution-options {
		margin-top: 0.5rem;
		padding-left: 2rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.resolution-option {
		display: block;
		width: 100%;
		padding: 0.5rem 0.75rem;
		background: rgba(255, 255, 255, 0.05);
		border: none;
		color: rgba(255, 255, 255, 0.8);
		cursor: pointer;
		border-radius: 4px;
		transition: all 0.2s;
		text-align: left;
		font-size: 0.8rem;
	}

	.resolution-option:hover {
		background: rgba(255, 255, 255, 0.1);
		color: white;
	}

	.resolution-option.selected {
		background: rgba(74, 144, 226, 0.3);
		border: 1px solid rgba(74, 144, 226, 0.5);
		color: white;
	}

	.resolution-loading,
	.resolution-error {
		padding: 0.5rem 0.75rem;
		text-align: center;
		font-size: 0.8rem;
		color: rgba(255, 255, 255, 0.6);
		font-style: italic;
	}

	.resolution-loading {
		animation: pulse 2s infinite;
	}

	@keyframes pulse {
		0%, 100% {
			opacity: 0.6;
		}
		50% {
			opacity: 1;
		}
	}

	.camera-error-message {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem;
		color: rgba(255, 255, 255, 0.8);
		background: rgba(255, 255, 255, 0.05);
		border-radius: 6px;
		margin: 0.5rem;
	}

	.error-icon {
		font-size: 1.5rem;
		flex-shrink: 0;
	}

	.error-text {
		flex: 1;
	}

	.error-title {
		font-size: 0.9rem;
		font-weight: 500;
		margin-bottom: 0.25rem;
		color: white;
	}

	.error-subtitle {
		font-size: 0.8rem;
		color: rgba(255, 255, 255, 0.6);
		line-height: 1.3;
	}


	/* Positioning for vertical sliders */
	:global(.zoom-slider-position) {
		left: calc(0px + var(--safe-area-inset-left, 0px));
		bottom: 67px;
	}

	:global(.focus-slider-position) {
		right: calc(16px + var(--safe-area-inset-right, 0px));
		bottom: 67px;
	}

	.queue-status-overlay {
		position: absolute;
		top: 80px;
		right: 20px;
		z-index: 1001;
	}

	.queue-indicator-overlay {
		position: absolute;
		bottom: 6px;
		right: 0px;
		z-index: 1001;
	}

	.compass-button-preview {
		border: 2px solid #ddd;
		border-radius: 4px;
		padding: 8px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.compass-button-preview.target {
		background: #4285F4;
		border-color: #4285F4;
		color: white;
		animation: pulse-hint 2s infinite;
	}

	.location-button-preview {
		border: 2px solid #ddd;
		border-radius: 4px;
		padding: 8px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.location-button-preview.target {
		background: #4285F4;
		border-color: #4285F4;
		color: white;
		animation: pulse-hint 2s infinite;
	}

	.tracking-hint {
		position: absolute;
		bottom: 60px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(255, 255, 255, 0.95);
		backdrop-filter: blur(10px);
		border-radius: 8px;
		padding: 0.75rem 1rem;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.5rem;
		z-index: 1010;
		border: 1px solid rgba(0, 0, 0, 0.1);
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
	}

	.tracking-hint .hint-message {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		color: #333;
		font-size: 0.9rem;
	}

	.tracking-hint .dismiss-hint-btn {
		background: transparent;
		border: 1px solid rgba(0, 0, 0, 0.2);
		color: rgba(0, 0, 0, 0.6);
		padding: 0.3rem 0.6rem;
		border-radius: 4px;
		font-size: 0.75rem;
		cursor: pointer;
		transition: all 0.2s;
	}

	.tracking-hint .dismiss-hint-btn:hover {
		background: rgba(0, 0, 0, 0.05);
		color: #333;
		border-color: rgba(0, 0, 0, 0.3);
	}

	/* Landscape mode: apply bottom safe area insets */
	@media (orientation: landscape) {
		.camera-selector-container {
			bottom: calc(6px + var(--safe-area-inset-bottom, 0px));
		}

		.shutter-container {
			bottom: calc(6px + var(--safe-area-inset-bottom, 0px));
		}

		.calibrate-compass-button {
			bottom: calc(0px + var(--safe-area-inset-bottom, 0px));
		}

		.switch-to-car-mode-button {
			bottom: calc(150px + var(--safe-area-inset-bottom, 0px));
			right: calc(0px + var(--safe-area-inset-right, 0px));
		}

		:global(.zoom-slider-position) {
			bottom: calc(67px + var(--safe-area-inset-bottom, 0px));
		}

		:global(.focus-slider-position) {
			bottom: calc(67px + var(--safe-area-inset-bottom, 0px));
		}

		.queue-indicator-overlay {
			bottom: calc(6px + var(--safe-area-inset-bottom, 0px));
			right: calc(0px + var(--safe-area-inset-right, 0px));
		}

		.tracking-hint {
			bottom: calc(60px + var(--safe-area-inset-bottom, 0px));
		}
	}

</style>

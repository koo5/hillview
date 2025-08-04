import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock navigator.geolocation
Object.defineProperty(navigator, 'geolocation', {
  value: {
    getCurrentPosition: vi.fn(),
    watchPosition: vi.fn(),
    clearWatch: vi.fn(),
  },
  writable: true,
});

// Mock Leaflet for tests
vi.mock('leaflet', () => ({
  LatLng: vi.fn().mockImplementation((lat, lng) => ({ lat, lng })),
  Map: vi.fn(),
  TileLayer: vi.fn(),
  Marker: vi.fn(),
  Icon: vi.fn(),
  DivIcon: vi.fn(),
}));

// Mock Tauri API
vi.mock('@tauri-apps/api', () => ({
  invoke: vi.fn(),
  app: {
    getVersion: vi.fn().mockResolvedValue('1.0.0'),
  },
  window: {
    getCurrent: vi.fn(),
  },
}));

// Mock Tauri plugins
vi.mock('@tauri-apps/plugin-geolocation', () => ({
  getCurrentPosition: vi.fn(),
  watchPosition: vi.fn(),
  clearWatch: vi.fn(),
}));

vi.mock('tauri-plugin-hillview-api', () => ({
  ping: vi.fn().mockResolvedValue('pong'),
  startSensor: vi.fn().mockResolvedValue(undefined),
  stopSensor: vi.fn().mockResolvedValue(undefined),
  registerListener: vi.fn().mockResolvedValue(undefined),
  updateSensorLocation: vi.fn().mockResolvedValue(undefined),
}));
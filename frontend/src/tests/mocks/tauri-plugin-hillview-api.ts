import { vi } from 'vitest';

// Mock implementation of tauri-plugin-hillview-api
export const ping = vi.fn().mockResolvedValue('pong');
export const startSensor = vi.fn().mockResolvedValue(undefined);
export const stopSensor = vi.fn().mockResolvedValue(undefined);
export const registerListener = vi.fn().mockResolvedValue(undefined);
export const updateSensorLocation = vi.fn().mockResolvedValue(undefined);

export default {
  ping,
  startSensor,
  stopSensor,
  registerListener,
  updateSensorLocation,
};
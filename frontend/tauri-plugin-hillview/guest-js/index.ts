import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'

export interface SensorData {
  magneticHeading: number  // Compass bearing in degrees from magnetic north (0-360°)
  trueHeading: number      // Compass bearing corrected for magnetic declination
  headingAccuracy: number
  pitch: number
  roll: number
  timestamp: number
  sensorSource?: string    // Identifies which sensor provided the data
}

export async function ping(value: string): Promise<string | null> {
  return await invoke<{value?: string}>('plugin:hillview|ping', {
    payload: {
      value,
    },
  }).then((r) => (r.value ? r.value : null));
}

export async function startSensor(): Promise<void> {
  return await invoke('plugin:hillview|start_sensor')
}

export async function stopSensor(): Promise<void> {
  return await invoke('plugin:hillview|stop_sensor')
}

export async function updateSensorLocation(latitude: number, longitude: number): Promise<void> {
  return await invoke('plugin:hillview|update_sensor_location', {
    location: {
      latitude,
      longitude
    }
  })
}

export async function onSensorData(callback: (data: SensorData) => void) {
  return await listen<SensorData>('plugin:hillview:sensor-data', (event) => {
    callback(event.payload)
  })
}

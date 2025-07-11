// Android native sensor interface
// Uses the Rotation Vector sensor for accurate bearing regardless of phone orientation

interface AndroidSensorData {
    magneticHeading: number;
    trueHeading: number;
    headingAccuracy: number;
    pitch: number;
    roll: number;
    timestamp: number;
    error?: string;
}

interface AndroidSensorInterface {
    startSensor(callback: string): void;
    stopSensor(): void;
    updateLocation(latitude: number, longitude: number): void;
}

declare global {
    interface Window {
        AndroidSensor?: AndroidSensorInterface;
        __androidSensorCallback?: (data: AndroidSensorData) => void;
    }
}

export class AndroidSensorService {
    private static instance: AndroidSensorService | null = null;
    private callbacks: Set<(data: AndroidSensorData) => void> = new Set();
    private isRunning = false;
    private lastData: AndroidSensorData | null = null;

    private constructor() {
        // Set up global callback
        if (typeof window !== 'undefined') {
            window.__androidSensorCallback = (data: AndroidSensorData) => {
                this.handleSensorData(data);
            };
        }
    }

    static getInstance(): AndroidSensorService {
        if (!AndroidSensorService.instance) {
            AndroidSensorService.instance = new AndroidSensorService();
        }
        return AndroidSensorService.instance;
    }

    isAvailable(): boolean {
        return typeof window !== 'undefined' && 
               window.AndroidSensor !== undefined &&
               /Android/i.test(navigator.userAgent);
    }

    start(callback: (data: AndroidSensorData) => void): boolean {
        if (!this.isAvailable()) {
            console.warn('Android sensor service not available');
            return false;
        }

        this.callbacks.add(callback);

        if (!this.isRunning) {
            try {
                window.AndroidSensor!.startSensor('window.__androidSensorCallback');
                this.isRunning = true;
                console.log('Android sensor service started');
            } catch (error) {
                console.error('Failed to start Android sensor:', error);
                return false;
            }
        }

        // Send last known data if available
        if (this.lastData) {
            callback(this.lastData);
        }

        return true;
    }

    stop(callback?: (data: AndroidSensorData) => void): void {
        if (callback) {
            this.callbacks.delete(callback);
        }

        if (this.callbacks.size === 0 && this.isRunning) {
            try {
                window.AndroidSensor!.stopSensor();
                this.isRunning = false;
                console.log('Android sensor service stopped');
            } catch (error) {
                console.error('Failed to stop Android sensor:', error);
            }
        }
    }

    updateLocation(latitude: number, longitude: number): void {
        if (this.isAvailable() && this.isRunning) {
            try {
                window.AndroidSensor!.updateLocation(latitude, longitude);
            } catch (error) {
                console.error('Failed to update location for sensor:', error);
            }
        }
    }

    private handleSensorData(data: AndroidSensorData): void {
        if (data.error) {
            console.error('Android sensor error:', data.error);
            return;
        }

        this.lastData = data;
        
        // Notify all callbacks
        this.callbacks.forEach(callback => {
            try {
                callback(data);
            } catch (error) {
                console.error('Error in sensor callback:', error);
            }
        });
    }

    getLastData(): AndroidSensorData | null {
        return this.lastData;
    }
}

// Export singleton instance
export const androidSensor = AndroidSensorService.getInstance();
import { invoke } from '@tauri-apps/api/core';
import { TAURI_MOBILE } from './tauri';

export class PermissionManager {
    private componentName: string;
    private hasLock: boolean = false;

    constructor(componentName: string) {
        this.componentName = componentName;
    }

    async acquireLock(): Promise<boolean> {
        if (this.hasLock) {
            console.log(`🢄[PermissionManager] ${this.componentName} already has lock`);
            return true;
        }

        try {
            const acquired = await invoke<boolean>('acquire_permission_lock', {
                requester: this.componentName
            });
            
            this.hasLock = acquired;
            
            if (acquired) {
                console.log(`🢄[PermissionManager] Lock acquired by ${this.componentName}`);
            } else {
                console.log(`🢄[PermissionManager] Lock denied to ${this.componentName} - held by another component`);
            }
            
            return acquired;
        } catch (error) {
            console.error(`🢄[PermissionManager] Failed to acquire lock for ${this.componentName}:`, error);
            return false;
        }
    }

    async releaseLock(): Promise<void> {
        if (!this.hasLock) {
            console.log(`🢄[PermissionManager] ${this.componentName} does not have lock to release`);
            return;
        }

        try {
            await invoke('release_permission_lock', {
                requester: this.componentName
            });
            
            this.hasLock = false;
            console.log(`🢄[PermissionManager] Lock released by ${this.componentName}`);
        } catch (error) {
            console.error(`🢄[PermissionManager] Failed to release lock for ${this.componentName}:`, error);
            // Reset our local state even if the backend call failed
            this.hasLock = false;
        }
    }

    async waitForLock(retryIntervalMs: number = 500, maxRetries: number = 60): Promise<boolean> {
        let retries = 0;
        
        while (retries < maxRetries) {
            if (await this.acquireLock()) {
                return true;
            }
            
            console.log(`🢄[PermissionManager] ${this.componentName} waiting for lock (attempt ${retries + 1}/${maxRetries})`);
            await new Promise(resolve => setTimeout(resolve, retryIntervalMs));
            retries++;
        }
        
        console.warn(`🢄[PermissionManager] ${this.componentName} gave up waiting for lock after ${maxRetries} attempts`);
        return false;
    }

    async getCurrentLockHolder(): Promise<string | null> {
        try {
            const holder = await invoke<string | null>('get_permission_lock_holder');
            return holder;
        } catch (error) {
            console.error(`🢄[PermissionManager] Failed to get lock holder:`, error);
            return null;
        }
    }

    get hasPermissionLock(): boolean {
        return this.hasLock;
    }

    get name(): string {
        return this.componentName;
    }

    // Cleanup method to be called when component is destroyed
    async cleanup(): Promise<void> {
        await this.releaseLock();
    }
}

// Utility function to create a scoped permission manager
export function createPermissionManager(componentName: string): PermissionManager {
    return new PermissionManager(componentName);
}

// Global function to check current lock holder (useful for debugging)
export async function getCurrentPermissionLockHolder(): Promise<string | null> {
    try {
        return await invoke<string | null>('get_permission_lock_holder');
    } catch (error) {
        console.error('🢄[PermissionManager] Failed to get current lock holder:', error);
        return null;
    }
}
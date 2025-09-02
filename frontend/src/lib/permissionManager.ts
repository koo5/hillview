import { invoke } from '@tauri-apps/api/core';
import {TAURI} from "$lib/tauri";

export class PermissionManager {
    private componentName: string;
    private hasLock: boolean = false;

    constructor(componentName: string) {
        this.componentName = componentName;
    }

    async acquireLock(): Promise<boolean> {
		if (!TAURI)
			return true;

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
		if (!TAURI)
			return;

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

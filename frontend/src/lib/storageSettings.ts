import { localStorageSharedStore } from './svelte-shared-store';

export type StorageMethod = 'private_folder' | 'mediastore_api';

export interface StorageSettings {
	preferred_storage: StorageMethod;
}

export const storageSettings = localStorageSharedStore<StorageSettings>('storageSettings', {
	preferred_storage: 'private_folder'
});

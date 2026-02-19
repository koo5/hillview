// Service worker upload handler
// Used by src/service-worker.ts for Background Sync

import { swSecureUploader } from './serviceWorkerSecureUpload';
import { browserPhotoStorage } from './photoStorage';

class ServiceWorkerUploadHandler {
    async uploadPendingPhotos(): Promise<void> {
        console.log('[SW Upload] Starting background upload with secure flow');

        try {
            // Get next photo to upload
            let photo = await browserPhotoStorage.getNextPhotoForUpload();
            let successCount = 0;
            let failCount = 0;

            while (photo) {
                // Mark as uploading
                await browserPhotoStorage.markPhotoAsUploading(photo.id);

                // Upload using secure flow
                const result = await swSecureUploader.uploadPhoto(photo);

                if (result.success && result.photoId) {
                    await browserPhotoStorage.markPhotoAsUploaded(photo.id, result.photoId);
                    successCount++;
                } else {
                    await browserPhotoStorage.markPhotoAsFailed(photo.id, result.error || 'Unknown error');
                    failCount++;
                }

                // Get next photo
                photo = await browserPhotoStorage.getNextPhotoForUpload();
            }

            console.log(`[SW Upload] Complete: ${successCount} uploaded, ${failCount} failed`);

            // Register retry sync if there were failures
            if (failCount > 0 && 'registration' in self) {
                const reg = self.registration as ServiceWorkerRegistration;
                if ('sync' in reg) {
                    await (reg.sync as any).register('photo-upload-retry');
                }
            }
        } catch (error) {
            console.error('[SW Upload] Error:', error);
            throw error; // Re-throw to trigger sync retry
        }
    }
}

export const swUploader = new ServiceWorkerUploadHandler();
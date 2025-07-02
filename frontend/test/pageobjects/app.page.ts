import { $ } from '@wdio/globals';

class AppPage {
    get mapContainer() {
        return $('[data-testid="map-container"]');
    }

    get cameraButton() {
        return $('[data-testid="camera-button"]');
    }

    get galleryButton() {
        return $('[data-testid="gallery-button"]');
    }

    get uploadButton() {
        return $('[data-testid="upload-button"]');
    }

    async waitForAppToLoad() {
        await this.mapContainer.waitForExist({ timeout: 10000 });
    }

    async openCamera() {
        await this.cameraButton.click();
    }

    async openGallery() {
        await this.galleryButton.click();
    }
}

export default new AppPage();
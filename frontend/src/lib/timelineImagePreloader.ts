import type { PhotoData } from './types/photoTypes';
import { getGalleryImage } from './galleryImage';

interface PreloadState {
	active: boolean;
	photos: PhotoData[];
	cursor: number;
	availablePhotos: PhotoData[];
	clientWidth: number | undefined;
	frontUid: string | undefined;
	readyUrl: string | undefined;
	saveData: boolean;
}

/** A single speculative request at a time; completed images use the browser cache. */
export class TimelineImagePreloader {
	private queue: string[] = [];
	private loading: HTMLImageElement | null = null;
	private completed = new Set<string>();
	private failed = new Set<string>();
	private previousUid: string | undefined;
	private direction = 1;
	private disposed = false;

	update(state: PreloadState) {
		if (this.disposed) return;
		const current = state.photos[state.cursor];
		if (!state.active || !current) {
			this.previousUid = undefined;
			this.direction = 1;
			this.setQueue([]);
			return;
		}

		// Compare photo identities, since loading an earlier chunk shifts the cursor.
		if (current.uid !== this.previousUid) {
			const previousIndex = state.photos.findIndex(p => p.uid === this.previousUid);
			this.direction = previousIndex < 0 ? 1 : Math.sign(state.cursor - previousIndex);
			this.previousUid = current.uid;
		}

		const available = new Map(state.availablePhotos.map(p => [p.uid, p]));
		const front = available.get(current.uid);
		if (state.saveData || !state.clientWidth || !front || state.frontUid !== current.uid
			|| state.readyUrl !== getGalleryImage(front, state.clientWidth).url) {
			this.setQueue([]);
			return;
		}
		this.remember(state.readyUrl);

		const urls: string[] = [];
		for (const offset of [this.direction, -this.direction, 2 * this.direction]) {
			const indexPhoto = state.photos[state.cursor + offset];
			// The timeline index only has thumbs. Wait for pinned worker metadata.
			const photo = indexPhoto && available.get(indexPhoto.uid);
			if (!photo || photo.is_placeholder) continue;
			const { url } = getGalleryImage(photo, state.clientWidth);
			if (url && url !== state.readyUrl && !urls.includes(url)) urls.push(url);
		}
		this.setQueue(urls);
	}

	private setQueue(urls: string[]) {
		this.queue = urls;
		// A failed candidate can be retried after leaving and re-entering the window.
		this.failed = new Set([...this.failed].filter(url => urls.includes(url)));
		this.pump();
	}

	private pump() {
		if (this.disposed || this.loading) return;
		const url = this.queue.find(url => !this.completed.has(url) && !this.failed.has(url));
		if (!url) return;
		const image = new Image();
		this.loading = image;
		image.fetchPriority = 'low';
		const finish = (success: boolean) => {
			image.onload = image.onerror = null;
			this.loading = null;
			if (success) {
				this.remember(url);
			} else if (this.queue.includes(url)) {
				this.failed.add(url);
			}
			this.pump();
		};
		image.onload = () => finish(true);
		image.onerror = () => finish(false);
		image.src = url;
	}

	private remember(url: string) {
		// Retain recent URL history, not decoded bitmaps.
		this.completed.delete(url);
		this.completed.add(url);
		if (this.completed.size > 32) this.completed.delete(this.completed.values().next().value!);
	}

	dispose() {
		this.disposed = true;
		this.queue = [];
		if (this.loading) {
			this.loading.onload = this.loading.onerror = null;
			this.loading.removeAttribute('src');
			this.loading = null;
		}
		this.completed.clear();
		this.failed.clear();
	}
}

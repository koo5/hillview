import type {Bounds, PhotoData, PhotoId, SourceConfig, WorkerMessage, WorkerResponse} from './photoWorkerTypes';
import {loadJsonPhotos} from './utils/photoParser';
import {MapillaryWorkerHandler} from './mapillaryWorkerHandler';
import {updatePhotoBearingDiffData} from './utils/bearingUtils';
import {calculateCenterFromBounds, getDistance, isInBounds} from './utils/distanceUtils';


const    MAX_PHOTOS_IN_AREA = 700;
const    MAX_PHOTOS_IN_RANGE = 200;


class Processors {
	enqueueInternal = null;

	data = {
		config: {
			recalculateBearingDiffForAllPhotosInArea: false,
		},
		sources: [],
		area: {},
		bearing: {},
	};
	aborted: boolean = false;

	photosInArea: PhotoData[] = [];
	currentRange = 0;




	// Configuration

	public async configUpdated() {
		//...


		this.enqueueInternal('sourcesUpdated');
	}

	public async sourcesUpdated() {



		this.enqueueInternal('areaUpdated');
	}

	public async areaUpdated() {

		let sourcesToAwait = [];
		let sourcesToAsync = [];

		const enabledSources = this.data.sources.filter(source => source.enabled);

		for (const source of enabledSources) {
			const lastLoadDuration = this.lastLoadDurations[source.id] || 0;
			if (lastLoadDuration < 100) {
				sourcesToAwait.push(source);
			} else {
				sourcesToAsync.push(source);
			}
		}
		Promise.all(sourcesToAsync.map(source => this.loadPhotosAsync(source)));
		let results = await Promise.all(sourcesToAwait.map(async (source) => await this.loadPhotosAwait(source)));

		if (results.length > 0) {
			this.photosInArea = this.cullPhotos(results.flat(), this.data.area.bounds, MAX_PHOTOS_IN_AREA);
			this.enqueueInternal('bearingUpdated');
		}
	}

	public async bearingUpdated() {

	}


	public async loadPhotosAsync(source: SourceConfig): Promise<PhotoData[]> {
		const lastLoadStartTime = Date.now();
		const photos = await this.loadPhotos(source);
		this.lastLoadDurations[source.id] = Date.now() - lastLoadStartTime;
		return photos;
	}

}
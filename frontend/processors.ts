
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

	// Configuration

	public async configUpdated() {
		//...


		enqueueInternal('sourcesUpdated');
	}

	public async sourcesUpdated() {

	}

	public async areaUpdated() {

	}

	public async bearingUpdated() {

	}


}
class Processors {
    const    data = {
        config: {
            recalculateBearingDiffForAllPhotosInArea: false,
        },
        sources: [],
        area: {},
        bearing: {},
    };
    aborted: boolean = false;

    // Configuration
    const    MAX_PHOTOS_IN_AREA = 700;
    const    MAX_PHOTOS_IN_RANGE = 200;


    public async configUpdated() {

    }

    public async sourcesUpdated() {

    }

    public async areaUpdated() {

    }

    public async bearingUpdated() {

    }


}
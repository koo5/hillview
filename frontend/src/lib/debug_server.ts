import Dexie, { type Table } from 'dexie';

interface StateRecord {
    id?: number;
    ts: number;
    center: any;
    zoom: number;
    top_left: any;
    bottom_right: any;
    range: number;
    bearing: number;
}

export class SpaceDatabase extends Dexie {
    state!: Table<StateRecord>;

    constructor() {
        super('space');
        this.version(1).stores({
            state: '++id, ts'
        });
    }
}

export const space_db = new SpaceDatabase();

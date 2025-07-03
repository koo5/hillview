import Dexie from 'dexie';

export const space_db = new Dexie('space');
space_db.version(1).stores({
    state: 'id++, ts, data',
});

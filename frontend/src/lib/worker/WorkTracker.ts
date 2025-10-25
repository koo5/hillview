interface WorkItem {
    lastUpdateId: number;
    lastProcessedId: number;
}

export class WorkTracker<T extends WorkItem> {
    private items = new Map<string, T>();

    constructor(keys: string[], createItem: () => T) {
        for (const key of keys) {
            this.items.set(key, createItem());
        }
    }

    getItem(key: string): T | undefined {
        return this.items.get(key);
    }

    markUpdated(key: string): void {
        const item = this.items.get(key);
        if (!item) {
            throw new Error(`WorkTracker item "${key}" does not exist`);
        }
        item.lastUpdateId++;
    }

    markProcessed(key: string): void {
        const item = this.items.get(key);
        if (!item) {
            throw new Error(`WorkTracker item "${key}" does not exist`);
        }
        item.lastProcessedId = item.lastUpdateId;
    }

    hasPendingWork(key: string): boolean {
        const item = this.items.get(key);
        if (!item) {
            throw new Error(`WorkTracker item "${key}" does not exist`);
        }
        return item.lastUpdateId > item.lastProcessedId;
    }

    getAllPendingKeys(): string[] {
        const pending: string[] = [];
        for (const [key, item] of this.items) {
            if (item.lastUpdateId > item.lastProcessedId) {
                pending.push(key);
            }
        }
        return pending;
    }

    getAllItems(): Map<string, T> {
        return new Map(this.items);
    }
}
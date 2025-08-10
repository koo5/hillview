/**
 * Async message queue that allows waiting for messages
 * 
 * When getNextMessage() is called but queue is empty, it returns a Promise.
 * When addMessage() is called, it can immediately resolve waiting Promises
 * instead of queuing, enabling async iterator-like behavior.
 */
export class MessageQueue {
    private queue: any[] = [];
    private waitingResolvers: ((value: any) => void)[] = [];

    addMessage(message: any): void {
        if (this.waitingResolvers.length > 0) {
            // Immediately resolve the oldest waiting Promise
            const resolver = this.waitingResolvers.shift()!;
            resolver(message);
        } else {
            // No one waiting, add to queue
            this.queue.push(message);
        }
    }

    async getNextMessage(): Promise<any> {
        if (this.queue.length > 0) {
            return this.queue.shift();
        }
        
        // Queue is empty, wait for next message
        return new Promise((resolve) => {
            this.waitingResolvers.push(resolve);
        });
    }

    hasMore(): boolean {
        return this.queue.length > 0;
    }

    clear(): void {
        this.queue = [];
        // Reject all waiting promises with a cancellation
        this.waitingResolvers.forEach(resolve => resolve(null));
        this.waitingResolvers = [];
    }

    size(): number {
        return this.queue.length;
    }
}
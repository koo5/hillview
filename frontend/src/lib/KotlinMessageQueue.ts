/**
 * Kotlin Message Queue - General polling system for Kotlin-frontend communication
 *
 * Works around Tauri event delivery issues by polling for messages every 100ms.
 * Can be used for photo worker updates, camera events, or any other Kotlin messages.
 */

import { invoke } from '@tauri-apps/api/core';

export interface QueuedMessage {
    type: string;
    payload: any;
    timestamp: number;
}

export interface MessageHandler {
    (message: QueuedMessage): void;
}

export class KotlinMessageQueue {
    private handlers = new Map<string, MessageHandler[]>();
    private pollingInterval: ReturnType<typeof setInterval> | null = null;
    private isPolling = false;

    constructor() {
        console.log('🔔 KotlinMessageQueue: Initialized');
    }

    /**
     * Start polling for messages every 100ms
     */
    startPolling(): void {
        if (this.isPolling) return;

        console.log('🔔 KotlinMessageQueue: Starting polling every 100ms');
        this.isPolling = true;

        this.pollingInterval = setInterval(() => {
            this.pollMessages();
        }, 450);
    }

    /**
     * Stop polling for messages
     */
    stopPolling(): void {
        if (!this.isPolling) return;

        console.log('🔔 KotlinMessageQueue: Stopping polling');
        this.isPolling = false;

        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
            this.pollingInterval = null;
        }
    }

    /**
     * Register a handler for a specific message type
     */
    on(messageType: string, handler: MessageHandler): void {
        if (!this.handlers.has(messageType)) {
            this.handlers.set(messageType, []);
        }
        this.handlers.get(messageType)!.push(handler);
        //console.log(`🔔 KotlinMessageQueue: Registered handler for ${messageType}`);
    }

    /**
     * Remove a handler for a specific message type
     */
    off(messageType: string, handler: MessageHandler): void {
        const handlers = this.handlers.get(messageType);
        if (handlers) {
            const index = handlers.indexOf(handler);
            if (index !== -1) {
                handlers.splice(index, 1);
                console.log(`🔔 KotlinMessageQueue: Removed handler for ${messageType}`);
            }
        }
    }

    /**
     * Poll for messages from Kotlin
     */
    private async pollMessages(): Promise<void> {
        try {
            const response = await invoke<{ messages: any[], count: number }>('plugin:hillview|poll_messages');

            if (response.count > 0) {
                console.log(`🔔 KotlinMessageQueue: Received ${response.count} messages`);

                for (const messageData of response.messages) {
                    const message: QueuedMessage = {
                        type: messageData.type,
                        payload: messageData.payload,
                        timestamp: messageData.timestamp
                    };

                    this.handleMessage(message);
                }
            }

        } catch (error) {
            console.error('🔔 KotlinMessageQueue: Error polling messages:', error);
        }
    }

    /**
     * Handle a received message by calling registered handlers
     */
    private handleMessage(message: QueuedMessage): void {
        const handlers = this.handlers.get(message.type);
        if (handlers && handlers.length > 0) {
            console.log(`🔔 KotlinMessageQueue: Handling message type: ${message.type}`);

            for (const handler of handlers) {
                try {
                    handler(message);
                } catch (error) {
                    console.error(`🔔 KotlinMessageQueue: Error in handler for ${message.type}:`, error);
                }
            }
        } else {
            console.warn(`🔔 KotlinMessageQueue: No handlers for message type: ${message.type}`);
        }
    }
}

// Global instance
export const kotlinMessageQueue = new KotlinMessageQueue();

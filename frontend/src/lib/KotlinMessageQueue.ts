/**
 * Kotlin Message Queue - General polling system for Kotlin-frontend communication
 *
 * Works around Tauri event delivery issues by polling for messages every 100ms.
 * Can be used for photo worker updates, camera events, or any other Kotlin messages.
 */

import { invoke } from '@tauri-apps/api/core';
import { browser } from '$app/environment';
import { TAURI } from '$lib/tauri';

export interface QueuedMessage {
    type: string;
    payload: any;
    timestamp: number;
}

export interface MessageHandler {
    // May be async — handleMessage attaches a .catch so rejections are logged, not
    // surfaced as unhandled rejections (the 'auth-expired' handler is async).
    (message: QueuedMessage): void | Promise<void>;
}

export class KotlinMessageQueue {
    private handlers = new Map<string, MessageHandler[]>();
    /**
     * Message types that must never be silently dropped (e.g. native session expiry,
     * which must reach AndroidTokenManager to keep JS auth in lockstep). If one is
     * polled before its handler is registered, it is buffered in pendingCritical and
     * re-delivered when the handler appears — instead of being warned-and-dropped like
     * ordinary messages.
     */
    private static readonly CRITICAL_TYPES = new Set<string>(['auth-expired']);
    private pendingCritical = new Map<string, QueuedMessage[]>();
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
        }, 150);
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

        // Deliver any critical messages that arrived before this handler existed.
        const pending = this.pendingCritical.get(messageType);
        if (pending && pending.length > 0) {
            console.warn(`🔔 KotlinMessageQueue: Re-delivering ${pending.length} buffered '${messageType}' message(s) to newly-registered handler`);
            this.pendingCritical.delete(messageType);
            for (const message of pending) {
                this.handleMessage(message);
            }
        }
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
                //console.log(`🔔 KotlinMessageQueue: Received ${response.count} messages`);

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
            //console.log(`🔔 KotlinMessageQueue: Handling message type: ${message.type}`);

            for (const handler of handlers) {
                try {
                    // Sync handlers run synchronously here; an async handler returns a
                    // promise whose rejection the synchronous try/catch can't see, so
                    // attach a .catch to log it rather than leak an unhandled rejection.
                    const result = handler(message);
                    if (result instanceof Promise) {
                        result.catch((error) => {
                            console.error(`🔔 KotlinMessageQueue: Error in async handler for ${message.type}:`, error);
                        });
                    }
                } catch (error) {
                    console.error(`🔔 KotlinMessageQueue: Error in handler for ${message.type}:`, error);
                }
            }
        } else if (KotlinMessageQueue.CRITICAL_TYPES.has(message.type)) {
            // Must not be lost: buffer and re-deliver when a handler registers.
            // Loud (error) because reaching here means a handler-registration ordering bug.
            console.error(`🔔 KotlinMessageQueue: No handler for CRITICAL message '${message.type}' — buffering for redelivery (its handler must register before polling)`);
            if (!this.pendingCritical.has(message.type)) {
                this.pendingCritical.set(message.type, []);
            }
            this.pendingCritical.get(message.type)!.push(message);
        } else {
            console.warn(`🔔 KotlinMessageQueue: No handlers for message type: ${message.type}`);
        }
    }
}

// Global instance - only create in browser context to avoid SSR logs
export const kotlinMessageQueue: KotlinMessageQueue = (browser && TAURI)
    ? new KotlinMessageQueue()
    : (null as unknown as KotlinMessageQueue);

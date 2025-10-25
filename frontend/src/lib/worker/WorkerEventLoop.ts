import { MessageQueue } from '../MessageQueue';
import { MessageRouter, type MessageHandlers } from './MessageRouter';
import type { ProcessManager } from './ProcessManager';
import type { FrontendState } from './FrontendState';

/**
 * WorkerEventLoop - Main Worker Orchestration
 *
 * This class manages the main event loop that coordinates all worker activity:
 * 1. Processes messages from the MessageQueue using MessageRouter
 * 2. Detects when there's pending work using FrontendState
 * 3. Starts new processes via ProcessManager when no active processes are running
 * 4. Handles blocking/waiting logic to avoid busy spinning
 *
 * The loop alternates between:
 * - Processing incoming messages (highest priority)
 * - Starting new processes for pending work (when not blocked)
 * - Waiting for new messages when idle
 *
 * Blocking Logic:
 * - If there are active processes running, don't start new ones (except higher priority)
 * - If blocked and no messages, wait for next message instead of spinning
 * - Clear blocked state when new messages arrive
 */

export class WorkerEventLoop {
    private messageQueue: MessageQueue;
    private messageRouter: MessageRouter;
    private processManager: ProcessManager;
    private frontendState: FrontendState;
    private isBlocked = false;
    private running = false;

    constructor(
        messageQueue: MessageQueue,
        messageHandlers: MessageHandlers,
        processManager: ProcessManager,
        frontendState: FrontendState
    ) {
        this.messageQueue = messageQueue;
        this.messageRouter = new MessageRouter(messageHandlers);
        this.processManager = processManager;
        this.frontendState = frontendState;
    }

    async start(): Promise<void> {
        if (this.running) {
            console.warn('WorkerEventLoop: Already running');
            return;
        }

        this.running = true;
        console.log('WorkerEventLoop: Starting main event loop');

        this.processManager.startProcessMonitor();

        try {
            while (this.running) {
                await this.processMessageBatch();
                await this.startPendingWork();
            }
        } catch (error) {
            console.error('WorkerEventLoop: Fatal error in main loop:', error);
            throw error;
        } finally {
            this.processManager.stopProcessMonitor();
        }
    }

    stop(): void {
        this.running = false;
        console.log('WorkerEventLoop: Stopping event loop');
    }

    private async processMessageBatch(): Promise<void> {
        while (true) {
            const needsProcessing = this.frontendState.hasPendingWork();
            const hasQueuedMessages = this.messageQueue.hasMore();

            console.log(`WorkerEventLoop: Loop iteration - needsProcessing: ${needsProcessing}, hasQueuedMessages: ${hasQueuedMessages}`);

            if (!needsProcessing && !hasQueuedMessages) {
                // Nothing to do, wait for next message
                const message = await this.messageQueue.getNextMessage();
                if (message) {
                    this.processMessage(message);
                    this.isBlocked = false;
                }
                continue;
            }

            if (hasQueuedMessages) {
                // Process queued messages first
                const message = await this.messageQueue.getNextMessage();
                if (message) {
                    this.processMessage(message);
                    this.isBlocked = false;
                }
                continue;
            }

            if (this.isBlocked) {
                // We're blocked by running processes, wait for next message instead of spinning
                const message = await this.messageQueue.getNextMessage();
                if (message) {
                    this.processMessage(message);
                    this.isBlocked = false;
                }
                continue;
            }

            // No more messages but we have unprocessed updates
            break;
        }
    }

    private processMessage(message: any): void {
        if (!message) {
            console.log('WorkerEventLoop: Got null message, ignoring');
            return;
        }

        console.log(`WorkerEventLoop: Processing message ${message.type} (id: ${message.id})`);
        this.messageRouter.routeMessage(message);
    }

    private async startPendingWork(): Promise<void> {
        const canStartNewProcesses = !this.processManager.hasActiveProcesses();

        if (!canStartNewProcesses) {
            this.isBlocked = true;
            console.log('WorkerEventLoop: Cannot process - processes running, setting blocked flag');
            return;
        }

        const pendingWork = this.frontendState.getPendingWorkByPriority();

        if (pendingWork.length === 0) {
            console.log('WorkerEventLoop: No pending work to start');
            return;
        }

        // Start the highest priority work
        const workType = pendingWork[0];
        const messageId = workType === 'config'
            ? this.frontendState.getConfigUpdateId()
            : this.frontendState.getAreaUpdateId();

        console.log(`WorkerEventLoop: Starting ${workType} process for message ${messageId}`);

        // This would need to be connected to PhotoOperations via dependency injection
        // For now, just log what we would do
        this.processManager.startProcess(workType, messageId);

        this.isBlocked = false; // We successfully started work
    }
}
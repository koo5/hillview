import { get } from 'svelte/store';
import { MinHeap } from './priorityQueue';

export type ProcessingEventType = 
  | 'filter_area'
  | 'calculate_distances' 
  | 'update_bearing_and_center'
  | 'fetch_mapillary';

export interface ProcessingEvent {
  id: string;
  type: ProcessingEventType;
  timestamp: number;
  data: any;
  priority: 'high' | 'normal' | 'low';
  mode: 'replace' | 'queue';
  abortSignal?: AbortSignal;
}

interface QueueOptions {
  maxQueueSize?: number;
  debounceMs?: number;
  onProcess: (event: ProcessingEvent) => Promise<void>;
  enablePreemption?: boolean;
}

const PRIORITY_VALUES = {
  high: 0,
  normal: 1,
  low: 2
} as const;

// Operations that should not be preempted
const NON_PREEMPTABLE_TYPES: ProcessingEventType[] = ['filter_area', 'update_bearing_and_center'];

export class PhotoProcessingQueue {
  private priorityQueue: MinHeap<ProcessingEvent>;
  private timers: Map<ProcessingEventType, NodeJS.Timeout> = new Map();
  private processing: Set<string> = new Set();
  private currentTask: ProcessingEvent | null = null;
  private abortController: AbortController | null = null;
  private eventCounter = 0;
  private lastProcessedTime: Map<ProcessingEventType, number> = new Map();
  private queueSizeWarningThreshold = 5; // Warn earlier
  private maxEventAge = 2000; // Drop events older than 2 seconds
  
  constructor(private options: QueueOptions) {
    this.options.maxQueueSize = options.maxQueueSize || 100;
    this.options.debounceMs = options.debounceMs || 50;
    this.options.enablePreemption = options.enablePreemption ?? true;
    
    // Initialize priority queue with custom comparator
    this.priorityQueue = new MinHeap<ProcessingEvent>((a, b) => {
      const priorityDiff = PRIORITY_VALUES[a.priority] - PRIORITY_VALUES[b.priority];
      return priorityDiff !== 0 ? priorityDiff : a.timestamp - b.timestamp;
    });
    
    // Start periodic cleanup
    this.startPeriodicCleanup();
  }
  
  private cleanupInterval: NodeJS.Timeout | null = null;
  
  private startPeriodicCleanup(): void {
    // Run cleanup every second
    this.cleanupInterval = setInterval(() => {
      this.cullStaleEvents();
      
      // Emergency clear if queue is too large
      if (this.priorityQueue.size > this.options.maxQueueSize! * 0.8) {
        console.error(`PhotoProcessingQueue: Emergency clear - queue size ${this.priorityQueue.size}`);
        this.logQueueStatus();
        
        // Remove oldest half of events
        const events = this.priorityQueue.toArray();
        events.sort((a, b) => a.timestamp - b.timestamp);
        const toRemove = events.slice(0, Math.floor(events.length / 2));
        toRemove.forEach(event => {
          this.priorityQueue.removeWhere(e => e.id === event.id);
        });
      }
    }, 1000);
  }

  enqueue(type: ProcessingEventType, data: any, options: Partial<ProcessingEvent> = {}) {
    // First, clean up stale events
    this.cullStaleEvents();
    
    const event: ProcessingEvent = {
      id: `${type}_${++this.eventCounter}`,
      type,
      timestamp: Date.now(),
      data,
      priority: options.priority || 'normal',
      mode: options.mode || 'replace',
      ...options
    };

    if (event.mode === 'replace') {
      // Remove existing events of this type from queue AND timers
      this.priorityQueue.removeWhere(e => e.type === type);
      
      // Cancel existing timer
      const existingTimer = this.timers.get(type);
      if (existingTimer) {
        clearTimeout(existingTimer);
        this.timers.delete(type);
      }
      
      // For high-frequency events like bearing updates, skip if too recent
      const lastProcessed = this.lastProcessedTime.get(type);
      if (type === 'update_bearing_and_center' && lastProcessed && Date.now() - lastProcessed < 32) {
        // Skip if processed within last frame (60fps = 16ms)
        return;
      }
      
      // Set debounce timer using event-specific config or fallback to default
      const eventConfig = EVENT_CONFIGS[type];
      const debounceTime = eventConfig?.debounceMs ?? this.options.debounceMs;
      
      const timer = setTimeout(() => {
        // Double-check event isn't stale before inserting
        if (Date.now() - event.timestamp < this.maxEventAge) {
          this.priorityQueue.insert(event, PRIORITY_VALUES[event.priority]);
          this.processNext();
        }
        this.timers.delete(type);
      }, debounceTime);
      
      this.timers.set(type, timer);
      
      // Warn if queue is getting large
      if (this.priorityQueue.size > this.queueSizeWarningThreshold) {
        console.warn(`PhotoProcessingQueue: Queue size (${this.priorityQueue.size}) exceeds warning threshold`);
        this.logQueueStatus();
      }
    } else {
      // For queue mode, add immediately if under limit
      if (this.priorityQueue.size < this.options.maxQueueSize!) {
        this.priorityQueue.insert(event, PRIORITY_VALUES[event.priority]);
        this.processNext();
      } else {
        console.warn(`Queue full for ${type}, dropping event`);
      }
    }
    
    // Check for preemption opportunity
    if (this.options.enablePreemption && this.currentTask && event.priority === 'high') {
      // Don't check preemption if the new event type is non-preemptable
      if (!NON_PREEMPTABLE_TYPES.includes(event.type)) {
        this.checkPreemption(event);
      }
    }
  }

  private async processNext() {
    // Don't start new task if already processing
    if (this.currentTask && !this.abortController?.signal.aborted) {
      return;
    }
    
    // Clean up stale events before processing
    this.cullStaleEvents();
    
    const nextEvent = this.priorityQueue.extractMin();
    if (!nextEvent) return;
    
    // Skip if event is too old
    if (Date.now() - nextEvent.timestamp > this.maxEventAge) {
      console.log(`Dropping stale ${nextEvent.type} event (age: ${Date.now() - nextEvent.timestamp}ms)`);
      // Try next event
      setTimeout(() => this.processNext(), 0);
      return;
    }
    
    this.currentTask = nextEvent;
    this.abortController = new AbortController();
    this.processing.add(nextEvent.id);
    
    try {
      // Track processing time
      const startTime = Date.now();
      
      // Pass abort signal to processor
      await this.options.onProcess({
        ...nextEvent,
        abortSignal: this.abortController.signal
      } as any);
      
      // Record successful processing
      this.lastProcessedTime.set(nextEvent.type, Date.now());
      
      const processingTime = Date.now() - startTime;
      if (processingTime > 100) {
        console.warn(`Slow processing for ${nextEvent.type}: ${processingTime}ms`);
      }
    } catch (error) {
      if (error instanceof Error && error.name !== 'AbortError') {
        console.error(`Error processing ${nextEvent.type}:`, error);
      }
    } finally {
      this.processing.delete(nextEvent.id);
      this.currentTask = null;
      this.abortController = null;
      
      // Process next item
      if (this.priorityQueue.size > 0) {
        setTimeout(() => this.processNext(), 0);
      }
    }
  }
  
  private checkPreemption(newEvent: ProcessingEvent) {
    if (!this.currentTask || !this.abortController) return;
    
    // Don't preempt non-preemptable operations
    if (NON_PREEMPTABLE_TYPES.includes(this.currentTask.type)) return;
    
    // Only preempt if new event has higher priority
    if (PRIORITY_VALUES[newEvent.priority] < PRIORITY_VALUES[this.currentTask.priority]) {
      console.log(`Preempting ${this.currentTask.type} with ${newEvent.type}`);
      this.abortController.abort();
      
      // Re-queue current task with lower priority
      this.priorityQueue.insert(
        { ...this.currentTask, priority: 'low' },
        PRIORITY_VALUES.low
      );
    }
  }

  // Cancel all pending events of a specific type
  cancel(type: ProcessingEventType) {
    const timer = this.timers.get(type);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(type);
    }
    
    // Remove events from priority queue
    this.priorityQueue.removeWhere(e => e.type === type);
    
    // Cancel current task if it matches
    if (this.currentTask?.type === type && this.abortController) {
      this.abortController.abort();
    }
  }

  // Get queue status
  getStatus() {
    const status: Record<string, number> = {};
    const allEvents = this.priorityQueue.toArray();
    
    for (const event of allEvents) {
      status[event.type] = (status[event.type] || 0) + 1;
    }
    
    return {
      queued: status,
      queueSize: this.priorityQueue.size,
      processing: this.processing.size,
      currentTask: this.currentTask?.type || null,
      hasPendingTimers: this.timers.size > 0,
      lastProcessedTimes: Object.fromEntries(this.lastProcessedTime)
    };
  }
  
  // Aggressively remove stale events
  private cullStaleEvents(): void {
    const now = Date.now();
    const removed = this.priorityQueue.removeWhere(event => {
      const age = now - event.timestamp;
      if (age > this.maxEventAge) {
        console.log(`Culling stale ${event.type} event (age: ${age}ms)`);
        return true;
      }
      return false;
    });
    
    if (removed.length > 0) {
      console.log(`Culled ${removed.length} stale events from queue`);
    }
  }
  
  // Log detailed queue status for debugging
  private logQueueStatus(): void {
    const events = this.priorityQueue.toArray();
    const now = Date.now();
    
    console.group('PhotoProcessingQueue Status');
    console.log('Queue size:', this.priorityQueue.size);
    console.log('Current task:', this.currentTask?.type || 'none');
    console.log('Pending timers:', Array.from(this.timers.keys()));
    
    console.log('Queued events:');
    events.forEach(event => {
      console.log(`  - ${event.type} (priority: ${event.priority}, age: ${now - event.timestamp}ms)`);
    });
    
    console.log('Last processed times:');
    this.lastProcessedTime.forEach((time, type) => {
      console.log(`  - ${type}: ${now - time}ms ago`);
    });
    console.groupEnd();
  }
  
  // Clear entire queue (emergency reset)
  clearQueue(): void {
    console.warn('PhotoProcessingQueue: Clearing entire queue!');
    
    // Cancel all timers
    this.timers.forEach(timer => clearTimeout(timer));
    this.timers.clear();
    
    // Abort current task
    if (this.abortController) {
      this.abortController.abort();
    }
    
    // Clear the queue
    while (!this.priorityQueue.isEmpty()) {
      this.priorityQueue.extractMin();
    }
    
    // Reset state
    this.processing.clear();
    this.currentTask = null;
    this.abortController = null;
  }
  
  // Clean up resources
  destroy(): void {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
      this.cleanupInterval = null;
    }
    this.clearQueue();
  }
}

// Event type configurations
export const EVENT_CONFIGS: Record<ProcessingEventType, { debounceMs: number; mode: 'replace' | 'queue' }> = {
  filter_area: { debounceMs: 500, mode: 'replace' },  // Increased for heavy operation
  calculate_distances: { debounceMs: 100, mode: 'replace' },
  update_bearing_and_center: { debounceMs: 16, mode: 'replace' }, // One frame at 60fps
  fetch_mapillary: { debounceMs: 1000, mode: 'replace' }
};
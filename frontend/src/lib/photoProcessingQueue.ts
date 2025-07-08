import { get } from 'svelte/store';
import { MinHeap } from './priorityQueue';

export type ProcessingEventType = 
  | 'filter_area'
  | 'calculate_distances' 
  | 'update_bearings'
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
const NON_PREEMPTABLE_TYPES: ProcessingEventType[] = ['filter_area', 'update_bearings'];

export class PhotoProcessingQueue {
  private priorityQueue: MinHeap<ProcessingEvent>;
  private timers: Map<ProcessingEventType, NodeJS.Timeout> = new Map();
  private processing: Set<string> = new Set();
  private currentTask: ProcessingEvent | null = null;
  private abortController: AbortController | null = null;
  private eventCounter = 0;
  
  constructor(private options: QueueOptions) {
    this.options.maxQueueSize = options.maxQueueSize || 100;
    this.options.debounceMs = options.debounceMs || 50;
    this.options.enablePreemption = options.enablePreemption ?? true;
    
    // Initialize priority queue with custom comparator
    this.priorityQueue = new MinHeap<ProcessingEvent>((a, b) => {
      const priorityDiff = PRIORITY_VALUES[a.priority] - PRIORITY_VALUES[b.priority];
      return priorityDiff !== 0 ? priorityDiff : a.timestamp - b.timestamp;
    });
  }

  enqueue(type: ProcessingEventType, data: any, options: Partial<ProcessingEvent> = {}) {
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
      // Remove existing events of this type from queue
      this.priorityQueue.removeWhere(e => e.type === type);
      
      // Cancel existing timer
      const existingTimer = this.timers.get(type);
      if (existingTimer) {
        clearTimeout(existingTimer);
      }
      
      // Set debounce timer
      const timer = setTimeout(() => {
        this.priorityQueue.insert(event, PRIORITY_VALUES[event.priority]);
        this.timers.delete(type);
        this.processNext();
      }, this.options.debounceMs);
      
      this.timers.set(type, timer);
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
    
    const nextEvent = this.priorityQueue.extractMin();
    if (!nextEvent) return;
    
    this.currentTask = nextEvent;
    this.abortController = new AbortController();
    this.processing.add(nextEvent.id);
    
    try {
      // Pass abort signal to processor
      await this.options.onProcess({
        ...nextEvent,
        abortSignal: this.abortController.signal
      } as any);
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
      hasPendingTimers: this.timers.size > 0
    };
  }
}

// Event type configurations
export const EVENT_CONFIGS: Record<ProcessingEventType, { debounceMs: number; mode: 'replace' | 'queue' }> = {
  filter_area: { debounceMs: 300, mode: 'replace' },  // Increased for heavy operation
  calculate_distances: { debounceMs: 100, mode: 'replace' },
  update_bearings: { debounceMs: 50, mode: 'replace' },
  fetch_mapillary: { debounceMs: 1000, mode: 'replace' }
};
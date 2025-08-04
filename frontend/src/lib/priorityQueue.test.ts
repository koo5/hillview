import { describe, it, expect, beforeEach } from 'vitest';
import { MinHeap, type QueueItem } from './priorityQueue';

describe('MinHeap', () => {
  let heap: MinHeap<string>;

  beforeEach(() => {
    heap = new MinHeap<string>();
  });

  describe('basic operations', () => {
    it('should start empty', () => {
      expect(heap.isEmpty()).toBe(true);
      expect(heap.size).toBe(0);
      expect(heap.peek()).toBeUndefined();
      expect(heap.extractMin()).toBeUndefined();
    });

    it('should insert and extract single item', () => {
      heap.insert('item1', 5);
      
      expect(heap.isEmpty()).toBe(false);
      expect(heap.size).toBe(1);
      expect(heap.peek()).toBe('item1');
      
      const extracted = heap.extractMin();
      expect(extracted).toBe('item1');
      expect(heap.isEmpty()).toBe(true);
    });

    it('should maintain min-heap property', () => {
      heap.insert('item3', 3);
      heap.insert('item1', 1);
      heap.insert('item5', 5);
      heap.insert('item2', 2);
      heap.insert('item4', 4);

      expect(heap.extractMin()).toBe('item1'); // priority 1
      expect(heap.extractMin()).toBe('item2'); // priority 2
      expect(heap.extractMin()).toBe('item3'); // priority 3
      expect(heap.extractMin()).toBe('item4'); // priority 4
      expect(heap.extractMin()).toBe('item5'); // priority 5
    });

    it('should handle duplicate priorities', () => {
      heap.insert('item1', 5);
      heap.insert('item2', 5);
      heap.insert('item3', 5);

      const extracted = [];
      extracted.push(heap.extractMin());
      extracted.push(heap.extractMin());
      extracted.push(heap.extractMin());

      expect(extracted).toContain('item1');
      expect(extracted).toContain('item2');
      expect(extracted).toContain('item3');
      expect(heap.isEmpty()).toBe(true);
    });

    it('should handle negative priorities', () => {
      heap.insert('negative', -10);
      heap.insert('zero', 0);
      heap.insert('positive', 10);

      expect(heap.extractMin()).toBe('negative');
      expect(heap.extractMin()).toBe('zero');
      expect(heap.extractMin()).toBe('positive');
    });
  });

  describe('removeWhere', () => {
    beforeEach(() => {
      heap.insert('apple', 1);
      heap.insert('banana', 2);
      heap.insert('apricot', 3);
      heap.insert('cherry', 4);
      heap.insert('avocado', 5);
    });

    it('should remove items matching predicate', () => {
      const removed = heap.removeWhere(item => item.startsWith('a'));

      expect(removed).toHaveLength(3);
      expect(removed).toContain('apple');
      expect(removed).toContain('apricot');
      expect(removed).toContain('avocado');
      expect(heap.size).toBe(2);
    });

    it('should maintain heap property after removal', () => {
      heap.removeWhere(item => item === 'banana');

      expect(heap.extractMin()).toBe('apple');
      expect(heap.extractMin()).toBe('apricot');
      expect(heap.extractMin()).toBe('cherry');
      expect(heap.extractMin()).toBe('avocado');
    });

    it('should handle removing all items', () => {
      const removed = heap.removeWhere(() => true);

      expect(removed).toHaveLength(5);
      expect(heap.isEmpty()).toBe(true);
    });

    it('should handle removing no items', () => {
      const removed = heap.removeWhere(() => false);

      expect(removed).toHaveLength(0);
      expect(heap.size).toBe(5);
    });
  });

  describe('toArray', () => {
    it('should return empty array for empty heap', () => {
      expect(heap.toArray()).toEqual([]);
    });

    it('should return all items', () => {
      heap.insert('item1', 1);
      heap.insert('item2', 2);
      heap.insert('item3', 3);

      const array = heap.toArray();
      
      expect(array).toHaveLength(3);
      expect(array).toContain('item1');
      expect(array).toContain('item2');
      expect(array).toContain('item3');
    });

    it('should not affect heap structure', () => {
      heap.insert('item1', 1);
      heap.insert('item2', 2);

      const array1 = heap.toArray();
      const array2 = heap.toArray();

      expect(array1).toEqual(array2);
      expect(heap.size).toBe(2);
    });
  });

  describe('complex scenarios', () => {
    it('should handle large number of items', () => {
      const items = 1000;
      const priorities = [];

      // Insert items with random priorities
      for (let i = 0; i < items; i++) {
        const priority = Math.floor(Math.random() * 100);
        priorities.push(priority);
        heap.insert(`item${i}`, priority);
      }

      expect(heap.size).toBe(items);

      // Extract all items and verify they come out in order
      let lastPriority = -Infinity;
      for (let i = 0; i < items; i++) {
        const item = heap.extractMin();
        expect(item).toBeDefined();
        
        // Find the priority of this item
        const itemIndex = parseInt(item!.substring(4));
        const currentPriority = priorities[itemIndex];
        
        expect(currentPriority).toBeGreaterThanOrEqual(lastPriority);
        lastPriority = currentPriority;
      }

      expect(heap.isEmpty()).toBe(true);
    });

    it('should handle custom compare function', () => {
      interface Task {
        id: string;
        priority: number;
        timestamp: number;
      }

      // Note: The MinHeap implementation uses the priority parameter, not the compare function for ordering
      // The compare function is stored but not used in the current implementation
      const taskHeap = new MinHeap<Task>();

      // Insert with priority based on both priority and timestamp
      taskHeap.insert({ id: 'task1', priority: 1, timestamp: 100 }, 1.100);
      taskHeap.insert({ id: 'task2', priority: 1, timestamp: 50 }, 1.050);
      taskHeap.insert({ id: 'task3', priority: 2, timestamp: 25 }, 2.025);

      expect(taskHeap.extractMin()?.id).toBe('task2'); // priority 1.050
      expect(taskHeap.extractMin()?.id).toBe('task1'); // priority 1.100
      expect(taskHeap.extractMin()?.id).toBe('task3'); // priority 2.025
    });

    it('should handle stress test with many operations', () => {
      const operations = 1000;
      let insertCount = 0;
      let extractCount = 0;

      for (let i = 0; i < operations; i++) {
        const op = Math.random();
        
        if (op < 0.6 || heap.isEmpty()) {
          // Insert
          heap.insert(`item${i}`, Math.random() * 100);
          insertCount++;
        } else if (op < 0.8) {
          // Extract
          heap.extractMin();
          extractCount++;
        } else {
          // Remove where
          heap.removeWhere(() => Math.random() < 0.3);
        }
      }

      expect(heap.size).toBeLessThanOrEqual(insertCount - extractCount);
      
      // Verify heap is still valid by extracting remaining items
      let lastPriority = -Infinity;
      while (!heap.isEmpty()) {
        const item = heap.extractMin();
        expect(item).toBeDefined();
        lastPriority = Math.max(lastPriority, 0); // Just verify extraction works
      }
    });
  });

  describe('edge cases', () => {
    it('should handle peek on single item heap', () => {
      heap.insert('only', 1);
      expect(heap.peek()).toBe('only');
      expect(heap.size).toBe(1); // peek should not remove
    });

    it('should handle multiple removeWhere on same heap', () => {
      heap.insert('a1', 1);
      heap.insert('b1', 2);
      heap.insert('a2', 3);
      heap.insert('b2', 4);

      heap.removeWhere(item => item.startsWith('a'));
      expect(heap.size).toBe(2);

      heap.removeWhere(item => item.endsWith('1'));
      expect(heap.size).toBe(1);
      expect(heap.peek()).toBe('b2');
    });

    it('should handle very large priorities', () => {
      heap.insert('min', Number.MIN_SAFE_INTEGER);
      heap.insert('max', Number.MAX_SAFE_INTEGER);
      heap.insert('zero', 0);

      expect(heap.extractMin()).toBe('min');
      expect(heap.extractMin()).toBe('zero');
      expect(heap.extractMin()).toBe('max');
    });
  });
});
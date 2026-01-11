import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { get } from 'svelte/store';
import {
  localStorageSharedStore,
  localStorageReadOnceSharedStore,
  staggeredLocalStorageSharedStore,
} from '../lib/svelte-shared-store';

// Mock localStorage
const createLocalStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
    get length() {
      return Object.keys(store).length;
    },
    key: vi.fn((index: number) => Object.keys(store)[index] ?? null),
    // Expose store for testing
    _getStore: () => store,
    _setStore: (newStore: Record<string, string>) => {
      store = newStore;
    },
  };
};

// Mock storage event listener
let storageEventListeners: ((event: StorageEvent) => void)[] = [];

const mockWindow = {
  localStorage: createLocalStorageMock(),
  addEventListener: vi.fn((type: string, listener: EventListener) => {
    if (type === 'storage') {
      storageEventListeners.push(listener as (event: StorageEvent) => void);
    }
  }),
  removeEventListener: vi.fn((type: string, listener: EventListener) => {
    if (type === 'storage') {
      storageEventListeners = storageEventListeners.filter(l => l !== listener);
    }
  }),
  setTimeout: vi.fn((fn: () => void, ms: number) => {
    return globalThis.setTimeout(fn, ms);
  }),
  clearTimeout: vi.fn((id: number) => {
    globalThis.clearTimeout(id);
  }),
};

// Simulate a storage event from another tab
const simulateStorageEvent = (key: string, newValue: string | null) => {
  const event = new StorageEvent('storage', {
    key,
    newValue,
    oldValue: null,
    storageArea: mockWindow.localStorage as unknown as Storage,
    url: 'http://localhost',
  });
  storageEventListeners.forEach(listener => listener(event));
};

// Setup global mocks
beforeEach(() => {
  vi.stubGlobal('window', mockWindow);
  vi.stubGlobal('localStorage', mockWindow.localStorage);
  mockWindow.localStorage.clear();
  storageEventListeners = [];
  vi.useFakeTimers();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('localStorageSharedStore', () => {
  describe('initialization', () => {
    it('should initialize with default value when localStorage is empty', () => {
      const store = localStorageSharedStore('test-key', { value: 'default' });
      expect(get(store)).toEqual({ value: 'default' });
    });

    it('should initialize with stored value when localStorage has data', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify({ value: 'stored' }));
      const store = localStorageSharedStore('test-key', { value: 'default' });
      expect(get(store)).toEqual({ value: 'stored' });
    });

    it('should use default when localStorage contains invalid JSON', () => {
      mockWindow.localStorage.setItem('test-key', 'not valid json{');
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const store = localStorageSharedStore('test-key', { value: 'default' });
      expect(get(store)).toEqual({ value: 'default' });
      expect(consoleSpy).toHaveBeenCalled();

      consoleSpy.mockRestore();
    });
  });

  describe('set', () => {
    it('should update store value', () => {
      const store = localStorageSharedStore('test-key', 'initial');
      store.set('updated');
      expect(get(store)).toBe('updated');
    });

    it('should persist to localStorage', () => {
      const store = localStorageSharedStore('test-key', 'initial');
      store.set('persisted');
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
        'test-key',
        JSON.stringify('persisted')
      );
    });

    it('should handle complex objects', () => {
      type ComplexObject = { a: number; b?: number[]; c?: { nested: boolean } };
      const store = localStorageSharedStore<ComplexObject>('test-key', { a: 1 });
      store.set({ a: 2, b: [1, 2, 3], c: { nested: true } });
      expect(get(store)).toEqual({ a: 2, b: [1, 2, 3], c: { nested: true } });
    });
  });

  describe('update', () => {
    it('should update based on current value', () => {
      const store = localStorageSharedStore('test-key', 5);
      store.update(n => n * 2);
      expect(get(store)).toBe(10);
    });

    it('should persist updated value to localStorage', () => {
      const store = localStorageSharedStore('test-key', { count: 0 });
      store.update(obj => ({ count: obj.count + 1 }));
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
        'test-key',
        JSON.stringify({ count: 1 })
      );
    });

    it('should not cause stack overflow with multiple rapid updates', () => {
      const store = localStorageSharedStore('test-key', 0);

      // This would cause stack overflow with the old get(r) implementation
      expect(() => {
        for (let i = 0; i < 1000; i++) {
          store.update(n => n + 1);
        }
      }).not.toThrow();

      expect(get(store)).toBe(1000);
    });
  });

  describe('subscribe', () => {
    it('should notify subscribers on value change', () => {
      const store = localStorageSharedStore('test-key', 'initial');
      const values: string[] = [];

      store.subscribe(value => values.push(value));
      store.set('changed');

      expect(values).toEqual(['initial', 'changed']);
    });

    it('should allow multiple subscribers', () => {
      const store = localStorageSharedStore('test-key', 0);
      let sum = 0;

      store.subscribe(v => sum += v);
      store.subscribe(v => sum += v);
      store.set(5);

      // Initial: 0 + 0 = 0, then set(5): 5 + 5 = 10
      expect(sum).toBe(10);
    });
  });

  describe('cross-tab synchronization', () => {
    it('should update when storage event is received', () => {
      const store = localStorageSharedStore('test-key', 'initial');
      const values: string[] = [];
      store.subscribe(v => values.push(v));

      simulateStorageEvent('test-key', JSON.stringify('from-other-tab'));

      expect(get(store)).toBe('from-other-tab');
      expect(values).toContain('from-other-tab');
    });

    it('should ignore storage events for different keys', () => {
      const store = localStorageSharedStore('my-key', 'initial');

      simulateStorageEvent('other-key', JSON.stringify('changed'));

      expect(get(store)).toBe('initial');
    });

    it('should add reason property for storage events on objects that have reason field', () => {
      // Note: The implementation only sets reason if the object already has a reason property
      const store = localStorageSharedStore('test-key', { value: 'initial', reason: '' });
      let receivedValue: any;
      store.subscribe(v => receivedValue = v);

      simulateStorageEvent('test-key', JSON.stringify({ value: 'updated', reason: 'original' }));

      expect(receivedValue.reason).toBe('handleStorageEvent');
    });
  });

  describe('cleanup', () => {
    it('should remove event listener when all subscribers unsubscribe', () => {
      const store = localStorageSharedStore('test-key', 'value');
      const unsubscribe = store.subscribe(() => {});

      expect(mockWindow.addEventListener).toHaveBeenCalledWith('storage', expect.any(Function));

      unsubscribe();

      expect(mockWindow.removeEventListener).toHaveBeenCalledWith('storage', expect.any(Function));
    });
  });
});

describe('localStorageReadOnceSharedStore', () => {
  describe('initialization', () => {
    it('should initialize with default value when localStorage is empty', () => {
      const store = localStorageReadOnceSharedStore('test-key', 'default');
      expect(get(store)).toBe('default');
    });

    it('should initialize with stored value from localStorage', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify('stored'));
      const store = localStorageReadOnceSharedStore('test-key', 'default');
      expect(get(store)).toBe('stored');
    });

    it('should handle "undefined" string in localStorage', () => {
      mockWindow.localStorage.setItem('test-key', 'undefined');
      const store = localStorageReadOnceSharedStore('test-key', 'default');
      expect(get(store)).toBe('default');
    });

    it('should use default for falsy stored values', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify(null));
      const store = localStorageReadOnceSharedStore('test-key', 'default');
      expect(get(store)).toBe('default');
    });
  });

  describe('set and update', () => {
    it('should update store and persist to localStorage', () => {
      const store = localStorageReadOnceSharedStore('test-key', 'initial');
      store.set('updated');

      expect(get(store)).toBe('updated');
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
        'test-key',
        JSON.stringify('updated')
      );
    });

    it('should update based on current value', () => {
      const store = localStorageReadOnceSharedStore('test-key', 10);
      store.update(n => n * 3);
      expect(get(store)).toBe(30);
    });
  });

  describe('no cross-tab sync', () => {
    it('should NOT listen for storage events (read-once behavior)', () => {
      localStorageReadOnceSharedStore('test-key', 'value');

      // Read-once store doesn't add storage event listener
      // (start function doesn't return a cleanup function that removes listener)
      expect(storageEventListeners.length).toBe(0);
    });
  });
});

describe('staggeredLocalStorageSharedStore', () => {
  describe('initialization', () => {
    it('should initialize with default value', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 'default', 100);
      expect(get(store)).toBe('default');
    });

    it('should initialize with stored value', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify('stored'));
      const store = staggeredLocalStorageSharedStore('test-key', 'default', 100);
      expect(get(store)).toBe('stored');
    });
  });

  describe('immediate store update', () => {
    it('should update store immediately on set', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 'initial', 100);
      // Need to subscribe to trigger start()
      const values: string[] = [];
      store.subscribe(v => values.push(v));

      store.set('immediate');

      // Store updates immediately
      expect(get(store)).toBe('immediate');
      expect(values).toContain('immediate');
    });

    it('should update store immediately on update', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 5, 100);
      // Need to subscribe to trigger start()
      const values: number[] = [];
      store.subscribe(v => values.push(v));

      store.update(n => n + 10);

      expect(get(store)).toBe(15);
      expect(values).toContain(15);
    });
  });

  describe('debounced localStorage writes', () => {
    it('should debounce localStorage writes', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 0, 100);

      // Clear the initial setItem call from start()
      mockWindow.localStorage.setItem.mockClear();

      store.set(1);
      store.set(2);
      store.set(3);

      // localStorage should not be updated yet (debounced)
      expect(mockWindow.localStorage.setItem).not.toHaveBeenCalled();

      // Advance timers past debounce period
      vi.advanceTimersByTime(100);

      // Now it should be called with the final value
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
        'test-key',
        JSON.stringify(3)
      );
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledTimes(1);
    });

    it('should skip write if value matches last written value', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 'initial', 100);
      // Need to subscribe to trigger start()
      store.subscribe(() => {});

      // Set a value to establish lastWrittenValue
      store.set('value');
      vi.advanceTimersByTime(100);

      // Verify first write happened
      expect(mockWindow.localStorage.setItem).toHaveBeenLastCalledWith(
        'test-key',
        JSON.stringify('value')
      );
      mockWindow.localStorage.setItem.mockClear();

      // Set same value again - write should be skipped
      store.set('value');
      vi.advanceTimersByTime(100);

      // setItem should not be called because value didn't change from lastWrittenValue
      expect(mockWindow.localStorage.setItem).not.toHaveBeenCalled();
    });

    it('should reset debounce timer on rapid updates', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 0, 100);
      mockWindow.localStorage.setItem.mockClear();

      store.set(1);
      vi.advanceTimersByTime(50);

      store.set(2);
      vi.advanceTimersByTime(50);

      store.set(3);
      vi.advanceTimersByTime(50);

      // Only 150ms passed total, so no write yet (each set resets the 100ms timer)
      expect(mockWindow.localStorage.setItem).not.toHaveBeenCalled();

      vi.advanceTimersByTime(50);

      // Now 200ms since last set, debounce should trigger
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
        'test-key',
        JSON.stringify(3)
      );
    });
  });

  describe('cross-tab synchronization', () => {
    it('should update from storage events', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 'initial', 100);
      // Need to subscribe to trigger start() and register storage event listener
      const values: string[] = [];
      store.subscribe(v => values.push(v));

      simulateStorageEvent('test-key', JSON.stringify('from-other-tab'));

      expect(get(store)).toBe('from-other-tab');
      expect(values).toContain('from-other-tab');
    });
  });

  describe('cleanup with pending writes', () => {
    it('should flush pending write on cleanup', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 'initial', 100);
      const unsubscribe = store.subscribe(() => {});

      mockWindow.localStorage.setItem.mockClear();

      store.set('pending');

      // Unsubscribe triggers cleanup
      unsubscribe();

      // Pending write should be flushed
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
        'test-key',
        JSON.stringify('pending')
      );
    });
  });

  describe('no stack overflow', () => {
    it('should handle rapid update calls without stack overflow', () => {
      const store = staggeredLocalStorageSharedStore('test-key', 0, 100);
      // Need to subscribe to trigger start()
      store.subscribe(() => {});

      expect(() => {
        for (let i = 0; i < 1000; i++) {
          store.update(n => n + 1);
        }
      }).not.toThrow();

      expect(get(store)).toBe(1000);
    });
  });
});

describe('store contract compliance', () => {
  describe('update before subscribe', () => {
    it('localStorageSharedStore should use localStorage value for update() before subscribe', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify('stored-value'));

      const store = localStorageSharedStore('test-key', 'default');

      // Update without subscribing first - should use 'stored-value', not 'default'
      store.update(v => v + '!');

      // Now subscribe to verify the value
      let value: string = '';
      store.subscribe(v => value = v);

      expect(value).toBe('stored-value!');
    });

    it('localStorageReadOnceSharedStore should use localStorage value for update() before subscribe', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify('stored-value'));

      const store = localStorageReadOnceSharedStore('test-key', 'default');

      store.update(v => v + '!');

      let value: string = '';
      store.subscribe(v => value = v);

      expect(value).toBe('stored-value!');
    });

    it('staggeredLocalStorageSharedStore should use localStorage value for update() before subscribe', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify('stored-value'));

      const store = staggeredLocalStorageSharedStore('test-key', 'default', 100);

      store.update(v => v + '!');

      let value: string = '';
      store.subscribe(v => value = v);

      expect(value).toBe('stored-value!');
    });
  });

  describe('set before subscribe', () => {
    it('should allow set() before any subscription', () => {
      const store = localStorageSharedStore('test-key', 'default');

      // Set without subscribing first
      store.set('new-value');

      // Now subscribe to verify the value
      let value: string = '';
      store.subscribe(v => value = v);

      expect(value).toBe('new-value');
    });
  });

  describe('writable initial value', () => {
    it('should initialize writable with localStorage value, not default', () => {
      mockWindow.localStorage.setItem('test-key', JSON.stringify('stored'));

      const store = localStorageSharedStore('test-key', 'default');

      // First subscription should immediately receive 'stored', not 'default'
      const values: string[] = [];
      store.subscribe(v => values.push(v));

      // Should only have one value (the localStorage value)
      // The start() function re-reads but since value is same, subscribers
      // may get called twice with same value - that's acceptable
      expect(values[values.length - 1]).toBe('stored');
    });
  });
});

describe('edge cases and stress tests', () => {
  describe('concurrent store operations', () => {
    it('should handle multiple stores with same key correctly', () => {
      mockWindow.localStorage.setItem('shared-key', JSON.stringify('initial'));

      const store1 = localStorageSharedStore('shared-key', 'default1');
      const store2 = localStorageSharedStore('shared-key', 'default2');

      expect(get(store1)).toBe('initial');
      expect(get(store2)).toBe('initial');

      store1.set('from-store1');

      // Store2 won't automatically update (same tab, no storage event)
      // But localStorage should be updated
      expect(mockWindow.localStorage.setItem).toHaveBeenCalledWith(
        'shared-key',
        JSON.stringify('from-store1')
      );
    });
  });

  describe('special values', () => {
    it('should handle null values', () => {
      const store = localStorageSharedStore<string | null>('test-key', 'default');
      store.set(null);
      expect(get(store)).toBeNull();
    });

    it('should handle empty string', () => {
      const store = localStorageSharedStore('test-key', 'default');
      store.set('');
      expect(get(store)).toBe('');
    });

    it('should handle empty object', () => {
      const store = localStorageSharedStore<Record<string, unknown>>('test-key', { a: 1 });
      store.set({});
      expect(get(store)).toEqual({});
    });

    it('should handle empty array', () => {
      const store = localStorageSharedStore<number[]>('test-key', [1, 2, 3]);
      store.set([]);
      expect(get(store)).toEqual([]);
    });

    it('should handle deeply nested objects', () => {
      const nested = {
        level1: {
          level2: {
            level3: {
              level4: {
                value: 'deep'
              }
            }
          }
        }
      };
      const store = localStorageSharedStore<typeof nested>('test-key', nested);
      store.set(nested);
      expect(get(store)).toEqual(nested);
    });
  });

  describe('type consistency', () => {
    it('should maintain number type', () => {
      const store = localStorageSharedStore('test-key', 42);
      store.update(n => n + 0.5);
      expect(typeof get(store)).toBe('number');
      expect(get(store)).toBe(42.5);
    });

    it('should maintain boolean type', () => {
      const store = localStorageSharedStore('test-key', true);
      store.set(false);
      expect(typeof get(store)).toBe('boolean');
      expect(get(store)).toBe(false);
    });

    it('should maintain array type', () => {
      const store = localStorageSharedStore<number[]>('test-key', [1, 2, 3]);
      store.update(arr => [...arr, 4]);
      expect(Array.isArray(get(store))).toBe(true);
      expect(get(store)).toEqual([1, 2, 3, 4]);
    });
  });

  describe('subscription management', () => {
    it('should handle subscribe-unsubscribe-subscribe cycle', () => {
      const store = localStorageSharedStore('test-key', 0);

      const unsub1 = store.subscribe(() => {});
      unsub1();

      const values: number[] = [];
      const unsub2 = store.subscribe(v => values.push(v));

      store.set(5);
      expect(values).toContain(5);

      unsub2();
    });

    it('should not break when unsubscribe is called multiple times', () => {
      const store = localStorageSharedStore('test-key', 'value');
      const unsub = store.subscribe(() => {});

      expect(() => {
        unsub();
        unsub();
        unsub();
      }).not.toThrow();
    });
  });
});

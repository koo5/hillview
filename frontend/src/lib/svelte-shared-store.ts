import { writable, type Writable } from 'svelte/store';

export function localStorageSharedStore<T>(name: string, default_: T): Writable<T> {
 function setStorage(value: T): void {
  const str = JSON.stringify(value);
  //console.log('🢄SAVE', name, str);
  window.localStorage.setItem(name, str);
 }

 function getStorage(): T {
  const item = window.localStorage.getItem(name);
  let result: T = default_;
  try {
   //console.log('🢄LOAD', name, item);
   if (item !== null) {
    result = JSON.parse(item) as T;
   }
  } catch (e) {
   console.error('🢄trying to parse: "' + item + '"');
   console.error('🢄',e);
  }
  if (result && typeof result === 'object' && 'reason' in result) {
   (result as any).reason = 'getStorage';
  }
  return result;
 }

 // Initialize from localStorage immediately to ensure update() works before subscribe
 let currentValue: T = getStorage();

 function start(): () => void {
  function handleStorageEvent({ key, newValue }: StorageEvent): void {
   if (key !== name) {
    return;
   }
   let v = JSON.parse(newValue!);
   if (typeof v === 'object' && Object.hasOwnProperty.call(v, 'reason')) {
    v.reason = 'handleStorageEvent';
   }
   currentValue = v;
   set(v);
  }

  // Re-read in case localStorage changed between creation and first subscribe
  currentValue = getStorage();
  set(currentValue);
  window.addEventListener('storage', handleStorageEvent);

  return () => window.removeEventListener('storage', handleStorageEvent);
 }

 // Initialize writable with the localStorage value (not default)
 const { subscribe, set, update } = writable<T>(currentValue, start);

 let r = {
  subscribe,
  set(value: T): void {
   currentValue = value;
   setStorage(value);
   set(value);
  },
  update(fn: (value: T) => T): void {
   const value2 = fn(currentValue);
   currentValue = value2;
   setStorage(value2);
   set(value2);
  },
 };
 return r;
}




export function localStorageReadOnceSharedStore<T>(name: string, default_: T): Writable<T> {
 function setStorage(value: T): void {
  const str = JSON.stringify(value);
  //console.log('🢄SAVE', name, str);
  window.localStorage.setItem(name, str);
 }

 function getStorage(): T {
  const item = window.localStorage.getItem(name);
  let result: T = default_;
  try {
   if (item !== 'undefined' && item) result = JSON.parse(item) as T;
   if (!result) result = default_;
  } catch (e) {
   console.log('🢄trying to parse: "' + item + '"');
   console.log(e);
  }
  return result;
 }

 // Initialize from localStorage immediately to ensure update() works before subscribe
 let currentValue: T = getStorage();

 function start(): void {
  // Re-read in case localStorage changed between creation and first subscribe
  currentValue = getStorage();
  set(currentValue);
 }

 // Initialize writable with the localStorage value (not default)
 const { subscribe, set, update } = writable<T>(currentValue, start);

 let r = {
  subscribe,
  set(value: T): void {
   currentValue = value;
   setStorage(value);
   set(value);
  },
  update(fn: (value: T) => T): void {
   const value2 = fn(currentValue);
   currentValue = value2;
   setStorage(value2);
   set(value2);
  },
 };
 return r;
}


/**
 * Optimized localStorage store with debounced writes for frequently changing values
 * Updates the store immediately for UI responsiveness, but debounces localStorage writes
 * to prevent excessive I/O and improve performance
 */
export function staggeredLocalStorageSharedStore<T>(
  name: string,
  default_: T,
  debounceMs: number = 500
): Writable<T> {
  let writeTimeout: number | null = null;
  let lastWrittenValue: T | null = null;

  function setStorage(value: T): void {
    const str = JSON.stringify(value);
    window.localStorage.setItem(name, str);
    lastWrittenValue = value;
  }

  function getStorage(): T {
    const item = window.localStorage.getItem(name);
    let result: T = default_;
    try {
      if (item !== null) {
        result = JSON.parse(item) as T;
      }
    } catch (e) {
      console.error('🢄trying to parse: "' + item + '"');
      console.error('🢄',e);
    }
    if (result && typeof result === 'object' && 'reason' in result) {
      (result as any).reason = 'getStorage';
    }
    return result;
  }

  // Initialize from localStorage immediately to ensure update() works before subscribe
  let currentValue: T = getStorage();
  // Track if value has been modified before first subscription
  let modifiedBeforeSubscribe = false;

  function debouncedSetStorage(value: T): void {
    // Skip write if value hasn't actually changed from what we last wrote
    if (lastWrittenValue !== null && JSON.stringify(lastWrittenValue) === JSON.stringify(value)) {
      return;
    }

    // Clear existing timeout
    if (writeTimeout) {
      clearTimeout(writeTimeout);
    }

    // Schedule debounced write
    writeTimeout = window.setTimeout(() => {
      setStorage(value);
      writeTimeout = null;
    }, debounceMs);
  }

  function start(): () => void {
    function handleStorageEvent({ key, newValue }: StorageEvent): void {
      if (key !== name) {
        return;
      }
      let v = JSON.parse(newValue!);
      if (typeof v === 'object' && Object.hasOwnProperty.call(v, 'reason')) {
        v.reason = 'handleStorageEvent';
      }
      currentValue = v;
      set(v);
    }

    // Only re-read from localStorage if the value hasn't been modified before subscribe
    // This ensures update() works correctly even before any subscriptions
    if (!modifiedBeforeSubscribe) {
      currentValue = getStorage();
    }
    set(currentValue);
    window.addEventListener('storage', handleStorageEvent);

    return () => {
      window.removeEventListener('storage', handleStorageEvent);
      // Flush any pending writes on cleanup
      if (writeTimeout) {
        clearTimeout(writeTimeout);
        if (lastWrittenValue === null || JSON.stringify(lastWrittenValue) !== JSON.stringify(currentValue)) {
          setStorage(currentValue);
        }
      }
    };
  }

  // Initialize writable with the localStorage value (not default)
  const { subscribe, set, update } = writable<T>(currentValue, start);

  let r = {
    subscribe,
    set(value: T): void {
      modifiedBeforeSubscribe = true;
      currentValue = value;
      // Update store immediately for UI responsiveness
      set(value);
      // Debounce localStorage write
      debouncedSetStorage(value);
    },
    update(fn: (value: T) => T): void {
      modifiedBeforeSubscribe = true;
      const newValue = fn(currentValue);
      currentValue = newValue;
      // Update store immediately
      set(newValue);
      // Debounce localStorage write
      debouncedSetStorage(newValue);
    },
  };

  return r;
}

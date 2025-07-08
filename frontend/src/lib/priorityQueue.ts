export interface QueueItem<T> {
  data: T;
  priority: number;
}

export class MinHeap<T> {
  private heap: QueueItem<T>[] = [];
  
  constructor(private compareFunction?: (a: T, b: T) => number) {}
  
  get size(): number {
    return this.heap.length;
  }
  
  isEmpty(): boolean {
    return this.heap.length === 0;
  }
  
  peek(): T | undefined {
    return this.heap[0]?.data;
  }
  
  insert(data: T, priority: number): void {
    const item: QueueItem<T> = { data, priority };
    this.heap.push(item);
    this.bubbleUp(this.heap.length - 1);
  }
  
  extractMin(): T | undefined {
    if (this.heap.length === 0) return undefined;
    if (this.heap.length === 1) return this.heap.pop()!.data;
    
    const min = this.heap[0];
    this.heap[0] = this.heap.pop()!;
    this.bubbleDown(0);
    return min.data;
  }
  
  // Remove all items matching predicate
  removeWhere(predicate: (item: T) => boolean): T[] {
    const removed: T[] = [];
    const newHeap: QueueItem<T>[] = [];
    
    for (const item of this.heap) {
      if (predicate(item.data)) {
        removed.push(item.data);
      } else {
        newHeap.push(item);
      }
    }
    
    // Rebuild heap
    this.heap = [];
    for (const item of newHeap) {
      this.insert(item.data, item.priority);
    }
    
    return removed;
  }
  
  private bubbleUp(index: number): void {
    while (index > 0) {
      const parentIndex = Math.floor((index - 1) / 2);
      
      if (this.heap[parentIndex].priority <= this.heap[index].priority) {
        break;
      }
      
      [this.heap[parentIndex], this.heap[index]] = [this.heap[index], this.heap[parentIndex]];
      index = parentIndex;
    }
  }
  
  private bubbleDown(index: number): void {
    while (true) {
      const leftChild = 2 * index + 1;
      const rightChild = 2 * index + 2;
      let smallest = index;
      
      if (leftChild < this.heap.length && 
          this.heap[leftChild].priority < this.heap[smallest].priority) {
        smallest = leftChild;
      }
      
      if (rightChild < this.heap.length && 
          this.heap[rightChild].priority < this.heap[smallest].priority) {
        smallest = rightChild;
      }
      
      if (smallest === index) break;
      
      [this.heap[index], this.heap[smallest]] = [this.heap[smallest], this.heap[index]];
      index = smallest;
    }
  }
  
  toArray(): T[] {
    return this.heap.map(item => item.data);
  }
}
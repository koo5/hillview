import asyncio
import datetime
from collections import defaultdict
from typing import Dict

class AsyncRateLimiter:
    """Async rate limiter that doesn't block the event loop"""
    
    def __init__(self, rate_limit_seconds: float = 1.0):
        self.rate_limit_seconds = rate_limit_seconds
        self.last_request: Dict[str, datetime.datetime] = {}
        self.waiting_queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.active_tasks: Dict[str, asyncio.Task] = {}
    
    async def acquire(self, client_id: str) -> None:
        """Acquire rate limit permission for client_id"""
        now = datetime.datetime.now()
        
        # Check if we need to wait
        if client_id in self.last_request:
            time_since_last = (now - self.last_request[client_id]).total_seconds()
            if time_since_last < self.rate_limit_seconds:
                # Add to queue and wait
                await self.waiting_queues[client_id].put(asyncio.current_task())
                
                # Start queue processor if not running
                if client_id not in self.active_tasks:
                    self.active_tasks[client_id] = asyncio.create_task(
                        self._process_queue(client_id)
                    )
                
                # Wait for our turn
                return await asyncio.sleep(0)  # Will be woken up by queue processor
        
        # Update last request time
        self.last_request[client_id] = now
    
    async def _process_queue(self, client_id: str):
        """Process waiting queue for a client"""
        queue = self.waiting_queues[client_id]
        
        try:
            while True:
                # Wait for the rate limit period
                await asyncio.sleep(self.rate_limit_seconds)
                
                if queue.empty():
                    break
                
                # Process next request
                task = await queue.get()
                if task and not task.done():
                    self.last_request[client_id] = datetime.datetime.now()
                    # Wake up the waiting task (simplified approach)
                    
        finally:
            # Clean up
            if client_id in self.active_tasks:
                del self.active_tasks[client_id]

# Global rate limiter instance
mapillary_rate_limiter = AsyncRateLimiter(rate_limit_seconds=1.0)
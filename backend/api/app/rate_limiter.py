import asyncio
import datetime
import time
from collections import defaultdict
from typing import Dict, Optional
from fastapi import HTTPException, Request, status
import logging

logger = logging.getLogger(__name__)

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

class AuthRateLimiter:
    """Rate limiter specifically for authentication endpoints with anti-brute-force features."""
    
    def __init__(self):
        # Track failed login attempts: {identifier: [(timestamp, attempt_count)]}
        self.failed_attempts: Dict[str, list] = defaultdict(list)
        # Track general rate limits: {identifier: [timestamps]}
        self.request_history: Dict[str, list] = defaultdict(list)
        # Lock for thread safety
        self.lock = asyncio.Lock()
    
    async def check_rate_limit(
        self, 
        identifier: str, 
        max_requests: int = 10, 
        window_seconds: int = 60
    ) -> bool:
        """Check if request is within rate limit."""
        async with self.lock:
            now = time.time()
            history = self.request_history[identifier]
            
            # Remove old entries outside the time window
            history[:] = [t for t in history if now - t < window_seconds]
            
            if len(history) >= max_requests:
                return False
            
            # Add current request
            history.append(now)
            return True
    
    async def check_auth_rate_limit(
        self, 
        identifier: str,
        max_attempts: int = 5,
        window_minutes: int = 15,
        lockout_minutes: int = 30
    ) -> None:
        """Check authentication rate limit with progressive delays."""
        async with self.lock:
            now = datetime.datetime.utcnow()
            attempts = self.failed_attempts[identifier]
            
            # Clean old attempts
            cutoff_time = now - datetime.timedelta(minutes=window_minutes)
            attempts[:] = [(t, c) for t, c in attempts if t > cutoff_time]
            
            # Check if account is in lockout period
            if attempts:
                last_attempt_time, attempt_count = attempts[-1]
                
                # Progressive lockout based on attempts
                if attempt_count >= max_attempts * 3:  # 15+ attempts
                    lockout_until = last_attempt_time + datetime.timedelta(minutes=lockout_minutes * 3)
                    if now < lockout_until:
                        remaining = int((lockout_until - now).total_seconds())
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Account locked. Try again in {remaining} seconds.",
                            headers={"Retry-After": str(remaining)}
                        )
                elif attempt_count >= max_attempts * 2:  # 10+ attempts
                    lockout_until = last_attempt_time + datetime.timedelta(minutes=lockout_minutes)
                    if now < lockout_until:
                        remaining = int((lockout_until - now).total_seconds())
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Too many failed attempts. Try again in {remaining} seconds.",
                            headers={"Retry-After": str(remaining)}
                        )
                elif attempt_count >= max_attempts:  # 5+ attempts
                    lockout_until = last_attempt_time + datetime.timedelta(minutes=5)
                    if now < lockout_until:
                        remaining = int((lockout_until - now).total_seconds())
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Too many attempts. Try again in {remaining} seconds.",
                            headers={"Retry-After": str(remaining)}
                        )
    
    async def record_failed_attempt(self, identifier: str) -> None:
        """Record a failed authentication attempt."""
        async with self.lock:
            now = datetime.datetime.utcnow()
            attempts = self.failed_attempts[identifier]
            
            # Count recent attempts
            recent_count = len(attempts)
            
            # Add new attempt with incremented count
            if attempts:
                _, last_count = attempts[-1]
                attempts.append((now, last_count + 1))
            else:
                attempts.append((now, 1))
            
            logger.warning(f"Failed login attempt #{recent_count + 1} for {identifier}")
    
    async def clear_failed_attempts(self, identifier: str) -> None:
        """Clear failed attempts after successful login."""
        async with self.lock:
            if identifier in self.failed_attempts:
                del self.failed_attempts[identifier]
                logger.info(f"Cleared failed attempts for {identifier}")
    
    def get_identifier(self, request: Request, username: Optional[str] = None) -> str:
        """Get a unique identifier for rate limiting."""
        # Combine IP address and username for more accurate tracking
        client_ip = request.client.host if request.client else "unknown"
        if username:
            return f"{client_ip}:{username}"
        return client_ip

# Global rate limiter instances
mapillary_rate_limiter = AsyncRateLimiter(rate_limit_seconds=1.0)
auth_rate_limiter = AuthRateLimiter()

async def check_auth_rate_limit(request: Request, username: Optional[str] = None) -> None:
    """Check authentication-specific rate limits."""
    identifier = auth_rate_limiter.get_identifier(request, username)
    await auth_rate_limiter.check_auth_rate_limit(identifier)
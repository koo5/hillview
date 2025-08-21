import asyncio
import datetime
import time
from collections import defaultdict
from typing import Dict, Optional, Callable
from fastapi import HTTPException, Request, status
import logging
import os
from .config import rate_limit_config

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
        max_attempts: Optional[int] = None,
        window_minutes: Optional[int] = None,
        lockout_minutes: Optional[int] = None
    ) -> None:
        """Check authentication rate limit with progressive delays."""
        # Use config values if not provided
        if max_attempts is None:
            max_attempts = rate_limit_config.auth_max_attempts
        if window_minutes is None:
            window_minutes = rate_limit_config.auth_window_minutes
        if lockout_minutes is None:
            lockout_minutes = rate_limit_config.auth_lockout_minutes
        
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
mapillary_rate_limiter = AsyncRateLimiter(rate_limit_seconds=rate_limit_config.mapillary_rate_limit_seconds)
auth_rate_limiter = AuthRateLimiter()

async def check_auth_rate_limit(request: Request, username: Optional[str] = None) -> None:
    """Check authentication-specific rate limits."""
    identifier = auth_rate_limiter.get_identifier(request, username)
    await auth_rate_limiter.check_auth_rate_limit(identifier)

class GeneralRateLimiter:
    """General-purpose rate limiter for API endpoints with configurable limits."""
    
    def __init__(self):
        # Track request history: {identifier: [(timestamp, endpoint_type)]}
        self.request_history: Dict[str, list] = defaultdict(list)
        self.lock = asyncio.Lock()
        
        # Load rate limits from central config
        self.limits = rate_limit_config.to_general_limits_dict()
    
    def get_identifier(self, request: Request, user_id: Optional[str] = None, limit_type: str = 'general_api') -> str:
        """Get identifier for rate limiting based on limit type."""
        limit_config = self.limits.get(limit_type, self.limits['general_api'])
        
        if limit_config['per_user'] and user_id:
            return f"user:{user_id}"
        else:
            # Use IP address
            client_ip = request.client.host if request.client else "unknown"
            return f"ip:{client_ip}"
    
    async def check_rate_limit(
        self,
        request: Request,
        limit_type: str,
        user_id: Optional[str] = None
    ) -> bool:
        """Check if request is within rate limit for the specified limit type."""
        async with self.lock:
            limit_config = self.limits.get(limit_type)
            if not limit_config:
                logger.warning(f"Unknown rate limit type: {limit_type}")
                return True
            
            identifier = self.get_identifier(request, user_id, limit_type)
            now = time.time()
            window_seconds = limit_config['window_hours'] * 3600
            max_requests = limit_config['max_requests']
            
            # Get request history for this identifier
            history = self.request_history[identifier]
            
            # Remove old entries outside the time window
            history[:] = [t for t in history if now - t < window_seconds]
            
            if len(history) >= max_requests:
                logger.warning(f"Rate limit exceeded for {identifier}, limit_type: {limit_type}, count: {len(history)}")
                return False
            
            # Add current request
            history.append(now)
            return True
    
    async def enforce_rate_limit(
        self,
        request: Request,
        limit_type: str,
        user_id: Optional[str] = None
    ) -> None:
        """Enforce rate limit and raise HTTPException if exceeded."""
        if not await self.check_rate_limit(request, limit_type, user_id):
            limit_config = self.limits[limit_type]
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {limit_config['max_requests']} requests per {limit_config['window_hours']} hour(s)",
                headers={"Retry-After": str(limit_config['window_hours'] * 3600)}
            )

# Global rate limiter instances
mapillary_rate_limiter = AsyncRateLimiter(rate_limit_seconds=rate_limit_config.mapillary_rate_limit_seconds)
auth_rate_limiter = AuthRateLimiter()
general_rate_limiter = GeneralRateLimiter()

# Dependency functions for different endpoint types
async def rate_limit_photo_upload(request: Request, user_id: str) -> None:
    """Rate limit photo upload endpoints."""
    await general_rate_limiter.enforce_rate_limit(request, 'photo_upload', user_id)

async def rate_limit_photo_operations(request: Request, user_id: str) -> None:
    """Rate limit photo operation endpoints."""
    await general_rate_limiter.enforce_rate_limit(request, 'photo_operations', user_id)

async def rate_limit_user_profile(request: Request, user_id: str) -> None:
    """Rate limit user profile endpoints."""
    await general_rate_limiter.enforce_rate_limit(request, 'user_profile', user_id)

async def rate_limit_general_api(request: Request, user_id: Optional[str] = None) -> None:
    """Rate limit general API endpoints."""
    await general_rate_limiter.enforce_rate_limit(request, 'general_api', user_id)

async def rate_limit_public_read(request: Request) -> None:
    """Rate limit public read endpoints."""
    await general_rate_limiter.enforce_rate_limit(request, 'public_read')
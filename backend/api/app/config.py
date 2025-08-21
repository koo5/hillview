"""
Central configuration management for the Hillview backend API.

This module handles all environment variable loading and provides
typed configuration objects for different parts of the application.
"""

import os
import logging
from typing import Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for different types of rate limiting."""
    
    # Mapillary API rate limiting
    mapillary_rate_limit_seconds: float = 1.0
    
    # Authentication rate limiting
    auth_max_attempts: int = 5
    auth_window_minutes: int = 15
    auth_lockout_minutes: int = 30
    
    # Photo upload limits (per user)
    photo_upload_max_requests: int = 10
    photo_upload_window_hours: int = 1
    
    # Photo operations limits (per user)
    photo_ops_max_requests: int = 100
    photo_ops_window_hours: int = 1
    
    # User profile limits (per user)
    user_profile_max_requests: int = 50
    user_profile_window_hours: int = 1
    
    # General API limits (per IP)
    general_api_max_requests: int = 200
    general_api_window_hours: int = 1
    
    # Public read limits (per IP)
    public_read_max_requests: int = 500
    public_read_window_hours: int = 1
    
    @classmethod
    def from_env(cls) -> 'RateLimitConfig':
        """Load configuration from environment variables."""
        return cls(
            # Mapillary
            mapillary_rate_limit_seconds=float(os.getenv('MAPILLARY_RATE_LIMIT_SECONDS', '1.0')),
            
            # Authentication
            auth_max_attempts=int(os.getenv('AUTH_MAX_ATTEMPTS', '5')),
            auth_window_minutes=int(os.getenv('AUTH_WINDOW_MINUTES', '15')),
            auth_lockout_minutes=int(os.getenv('AUTH_LOCKOUT_MINUTES', '30')),
            
            # Photo upload
            photo_upload_max_requests=int(os.getenv('RATE_LIMIT_PHOTO_UPLOAD', '10')),
            photo_upload_window_hours=int(os.getenv('RATE_LIMIT_PHOTO_UPLOAD_WINDOW', '1')),
            
            # Photo operations
            photo_ops_max_requests=int(os.getenv('RATE_LIMIT_PHOTO_OPS', '100')),
            photo_ops_window_hours=int(os.getenv('RATE_LIMIT_PHOTO_OPS_WINDOW', '1')),
            
            # User profile
            user_profile_max_requests=int(os.getenv('RATE_LIMIT_USER_PROFILE', '50')),
            user_profile_window_hours=int(os.getenv('RATE_LIMIT_USER_PROFILE_WINDOW', '1')),
            
            # General API
            general_api_max_requests=int(os.getenv('RATE_LIMIT_GENERAL_API', '200')),
            general_api_window_hours=int(os.getenv('RATE_LIMIT_GENERAL_API_WINDOW', '1')),
            
            # Public read
            public_read_max_requests=int(os.getenv('RATE_LIMIT_PUBLIC_READ', '500')),
            public_read_window_hours=int(os.getenv('RATE_LIMIT_PUBLIC_READ_WINDOW', '1')),
        )
    
    def to_general_limits_dict(self) -> Dict[str, Dict[str, Any]]:
        """Convert to the format expected by GeneralRateLimiter."""
        return {
            'photo_upload': {
                'max_requests': self.photo_upload_max_requests,
                'window_hours': self.photo_upload_window_hours,
                'per_user': True
            },
            'photo_operations': {
                'max_requests': self.photo_ops_max_requests,
                'window_hours': self.photo_ops_window_hours,
                'per_user': True
            },
            'user_profile': {
                'max_requests': self.user_profile_max_requests,
                'window_hours': self.user_profile_window_hours,
                'per_user': True
            },
            'general_api': {
                'max_requests': self.general_api_max_requests,
                'window_hours': self.general_api_window_hours,
                'per_user': False  # Per IP
            },
            'public_read': {
                'max_requests': self.public_read_max_requests,
                'window_hours': self.public_read_window_hours,
                'per_user': False  # Per IP
            }
        }
    
    def log_configuration(self) -> None:
        """Log all rate limit configurations."""
        logger.info("=== Rate Limit Configuration ===")
        logger.info(f"Mapillary API: {self.mapillary_rate_limit_seconds} seconds between requests")
        logger.info(f"Authentication: {self.auth_max_attempts} attempts per {self.auth_window_minutes} minutes, lockout: {self.auth_lockout_minutes} minutes")
        
        logger.info("General API Rate Limits:")
        limits_dict = self.to_general_limits_dict()
        for limit_type, config in limits_dict.items():
            scope = "per user" if config['per_user'] else "per IP"
            logger.info(f"  {limit_type}: {config['max_requests']} requests per {config['window_hours']} hour(s) ({scope})")
        
        logger.info("=== End Rate Limit Configuration ===")


# Global configuration instance
rate_limit_config = RateLimitConfig.from_env()
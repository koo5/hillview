"""
Central configuration management for the Hillview backend API.

This module handles all environment variable loading and provides
typed configuration objects for different parts of the application.
"""

# Import environment initialization first
from . import env_init

import os
import logging
from typing import Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

def is_rate_limiting_disabled() -> bool:
	"""Check if rate limiting is globally disabled."""
	return os.getenv("NO_LIMITS", "false").lower() in ("true", "1", "yes")

def get_cors_origins() -> List[str]:
	"""Get the allowed CORS origins for the application."""
	return [
		"http://localhost:8212",
		"http://localhost:4173",
		"http://127.0.0.1:8212",
		"http://tauri.localhost",
		"https://hillview.cz",
		"https://api.hillview.cz",
		"https://api.ipv4.hillview.cz",
	]

@dataclass
class RateLimitConfig:
	"""Configuration for different types of rate limiting."""

	# Mapillary API rate limiting
	mapillary_rate_limit_seconds: float

	# Authentication rate limiting
	auth_max_attempts: int
	auth_window_minutes: int
	auth_lockout_minutes: int

	# Photo upload limits (per user)
	photo_upload_max_requests: int
	photo_upload_window_hours: int

	# Photo operations limits (per user)
	photo_ops_max_requests: int
	photo_ops_window_hours: int

	# User profile limits (per user)
	user_profile_max_requests: int
	user_profile_window_hours: int

	# General API limits (per IP)
	general_api_max_requests: int
	general_api_window_hours: int

	# Public read limits (per IP)
	public_read_max_requests: int
	public_read_window_hours: int

	# Activity feed limits (per IP)
	activity_recent_max_requests: int
	activity_recent_window_hours: int

	# User registration limits (per IP)
	user_registration_max_requests: int
	user_registration_window_hours: int

	# Debug endpoints limits (per IP)
	debug_max_requests: int
	debug_window_hours: int

	@classmethod
	def from_env(cls) -> 'RateLimitConfig':
		"""Load configuration from environment variables."""

		logger.info("Loading rate limit configuration from environment variables")

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
			general_api_max_requests=int(os.getenv('RATE_LIMIT_GENERAL_API', '6000')),
			general_api_window_hours=int(os.getenv('RATE_LIMIT_GENERAL_API_WINDOW', '1')),

			# Public read
			public_read_max_requests=int(os.getenv('RATE_LIMIT_PUBLIC_READ', '500')),
			public_read_window_hours=int(os.getenv('RATE_LIMIT_PUBLIC_READ_WINDOW', '1')),

			# Activity feed
			activity_recent_max_requests=int(os.getenv('RATE_LIMIT_ACTIVITY_RECENT', '1000')),
			activity_recent_window_hours=int(os.getenv('RATE_LIMIT_ACTIVITY_RECENT_WINDOW', '1')),

			# User registration
			user_registration_max_requests=int(os.getenv('RATE_LIMIT_USER_REGISTRATION', '30')),
			user_registration_window_hours=int(os.getenv('RATE_LIMIT_USER_REGISTRATION_WINDOW', '1')),

			# Debug endpoints
			debug_max_requests=int(os.getenv('RATE_LIMIT_DEBUG', '2000')),
			debug_window_hours=int(os.getenv('RATE_LIMIT_DEBUG_WINDOW', '1')),
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
			},
			'activity_recent': {
				'max_requests': self.activity_recent_max_requests,
				'window_hours': self.activity_recent_window_hours,
				'per_user': False  # Per IP
			},
			'user_registration': {
				'max_requests': self.user_registration_max_requests,
				'window_hours': self.user_registration_window_hours,
				'per_user': False  # Per IP
			},
			'debug': {
				'max_requests': self.debug_max_requests,
				'window_hours': self.debug_window_hours,
				'per_user': False  # Per IP
			}
		}

	def log_configuration(self) -> None:
		"""Log all rate limit configurations."""
		if is_rate_limiting_disabled():
			logger.info("RATE LIMITING IS GLOBALLY DISABLED (NO_LIMITS=true)")
			return

		logger.info("=== Rate Limit Configuration ===")
		logger.info(f"Mapillary API: {self.mapillary_rate_limit_seconds} seconds between requests")
		logger.info(f"Authentication: {self.auth_max_attempts} attempts per {self.auth_window_minutes} minutes, lockout: {self.auth_lockout_minutes} minutes")

		logger.info("General API Rate Limits:")
		limits_dict = self.to_general_limits_dict()
		for limit_type, config in limits_dict.items():
			scope = "per user" if config['per_user'] else "per IP"
			logger.info(f"  {limit_type}: {config['max_requests']} requests per {config['window_hours']} hour(s) ({scope})")

		logger.info("=== End Rate Limit Configuration ===")

# Global configuration instance - now environment is loaded
rate_limit_config = RateLimitConfig.from_env()


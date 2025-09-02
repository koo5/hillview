"""Security audit logging service for tracking authentication events and security incidents."""
import logging
from datetime import datetime, timedelta, timezone
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.utc import utcnow, utc_minus_timedelta
from typing import Optional, Dict, Any
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))

# Import models dynamically to avoid import issues during startup
def get_security_audit_model():
	from common.models import SecurityAuditLog
	return SecurityAuditLog

def get_user_model():
	from common.models import User
	return User

logger = logging.getLogger(__name__)

class SecurityAuditService:
	"""Service for logging security events and analyzing patterns."""
	
	@staticmethod
	async def log_event(
		db: AsyncSession,
		event_type: str,
		user_identifier: Optional[str] = None,
		ip_address: Optional[str] = None,
		user_agent: Optional[str] = None,
		event_details: Optional[Dict[str, Any]] = None,
		severity: str = 'info',
		user_id: Optional[str] = None
	) -> None:
		"""Log a security event to the audit table."""
		try:
			SecurityAuditLog = get_security_audit_model()
			audit_log = SecurityAuditLog(
				event_type=event_type,
				user_identifier=user_identifier,
				ip_address=ip_address,
				user_agent=user_agent,
				event_details=event_details,
				severity=severity,
				user_id=user_id
			)
			db.add(audit_log)
			await db.commit()
			
			# Log to application logs as well for immediate monitoring
			log_level = getattr(logging, severity.upper(), logging.INFO)
			logger.log(log_level, f"Security Event: {event_type} | User: {user_identifier} | IP: {ip_address}")
			
		except Exception as e:
			logger.error(f"Failed to log security event: {str(e)}")
			await db.rollback()
	
	@staticmethod
	async def log_failed_login(
		db: AsyncSession,
		request: Request,
		username: str,
		attempt_count: int = 1,
		lockout_until: Optional[datetime] = None
	) -> None:
		"""Log a failed login attempt with additional context."""
		event_details = {
			"attempt_count": attempt_count,
			"user_agent": request.headers.get("user-agent", "unknown"),
			"referer": request.headers.get("referer"),
		}
		
		if lockout_until:
			event_details["lockout_until"] = lockout_until.isoformat()
			severity = "warning" if attempt_count >= 5 else "info"
		else:
			severity = "info"
		
		await SecurityAuditService.log_event(
			db=db,
			event_type="login_failed",
			user_identifier=username,
			ip_address=request.client.host if request.client else None,
			user_agent=request.headers.get("user-agent"),
			event_details=event_details,
			severity=severity
		)
	
	@staticmethod
	async def log_successful_login(
		db: AsyncSession,
		request: Request,
		user,  # User type - imported dynamically
		auth_method: str = "password"
	) -> None:
		"""Log a successful login."""
		event_details = {
			"auth_method": auth_method,
			"user_agent": request.headers.get("user-agent", "unknown"),
			"username": user.username,
			"user_role": user.role.value if user.role else "unknown"
		}
		
		await SecurityAuditService.log_event(
			db=db,
			event_type="login_success",
			user_identifier=user.username,
			ip_address=request.client.host if request.client else None,
			user_agent=request.headers.get("user-agent"),
			event_details=event_details,
			severity="info",
			user_id=user.id
		)
	
	@staticmethod
	async def log_password_change(
		db: AsyncSession,
		user,  # User type - imported dynamically
		request: Optional[Request] = None
	) -> None:
		"""Log a password change event."""
		await SecurityAuditService.log_event(
			db=db,
			event_type="password_change",
			user_identifier=user.username,
			ip_address=request.client.host if request and request.client else None,
			user_agent=request.headers.get("user-agent") if request else None,
			event_details={"user_role": user.role.value if user.role else "unknown"},
			severity="info",
			user_id=user.id
		)
	
	@staticmethod
	async def log_account_lockout(
		db: AsyncSession,
		request: Request,
		username: str,
		lockout_duration_minutes: int,
		attempt_count: int
	) -> None:
		"""Log an account lockout event."""
		event_details = {
			"lockout_duration_minutes": lockout_duration_minutes,
			"total_attempts": attempt_count,
			"user_agent": request.headers.get("user-agent", "unknown")
		}
		
		await SecurityAuditService.log_event(
			db=db,
			event_type="account_lockout",
			user_identifier=username,
			ip_address=request.client.host if request.client else None,
			user_agent=request.headers.get("user-agent"),
			event_details=event_details,
			severity="warning"
		)
	
	@staticmethod
	async def get_recent_failed_attempts(
		db: AsyncSession,
		user_identifier: str,
		ip_address: Optional[str] = None,
		hours: int = 24
	) -> int:
		"""Get count of recent failed login attempts for analysis."""
		try:
			cutoff_time = utc_minus_timedelta(timedelta(hours=hours))
			
			SecurityAuditLog = get_security_audit_model()
			query = select(SecurityAuditLog).where(
				and_(
					SecurityAuditLog.event_type == "login_failed",
					SecurityAuditLog.timestamp >= cutoff_time,
					SecurityAuditLog.user_identifier == user_identifier
				)
			)
			
			if ip_address:
				query = query.where(SecurityAuditLog.ip_address == ip_address)
			
			result = await db.execute(query)
			return len(result.scalars().all())
			
		except Exception as e:
			logger.error(f"Error checking recent failed attempts: {str(e)}")
			return 0
	
	@staticmethod
	async def get_suspicious_ips(
		db: AsyncSession,
		hours: int = 24,
		min_attempts: int = 10
	) -> list:
		"""Get IPs with suspicious activity patterns."""
		try:
			cutoff_time = utc_minus_timedelta(timedelta(hours=hours))
			
			# This would need raw SQL for proper aggregation
			# For now, return empty list and recommend external monitoring
			return []
			
		except Exception as e:
			logger.error(f"Error analyzing suspicious IPs: {str(e)}")
			return []
	
	@staticmethod
	async def cleanup_old_logs(
		db: AsyncSession,
		days_to_keep: int = 90
	) -> int:
		"""Clean up old audit logs to prevent table growth."""
		try:
			cutoff_date = utc_minus_timedelta(timedelta(days=days_to_keep))
			
			# Delete old logs except critical events
			from sqlalchemy import delete
			SecurityAuditLog = get_security_audit_model()
			stmt = delete(SecurityAuditLog).where(
				and_(
					SecurityAuditLog.timestamp < cutoff_date,
					SecurityAuditLog.severity.in_(['info'])  # Keep warnings and critical
				)
			)
			
			result = await db.execute(stmt)
			await db.commit()
			
			deleted_count = result.rowcount
			if deleted_count > 0:
				logger.info(f"Cleaned up {deleted_count} old audit log entries")
			
			return deleted_count
			
		except Exception as e:
			logger.error(f"Error cleaning up audit logs: {str(e)}")
			await db.rollback()
			return 0

# Global instance
security_audit = SecurityAuditService()
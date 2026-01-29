"""SQLAlchemy 2.0 typed models for Hillview backend."""
from datetime import datetime
from typing import Optional, List, Any
import uuid
import enum

from sqlalchemy import String, Float, Integer, Boolean, DateTime, Text, JSON, Enum, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from .database import Base


class UserRole(enum.Enum):
	USER = "user"
	ADMIN = "admin"
	MODERATOR = "moderator"


class PhotoRatingType(enum.Enum):
	THUMBS_UP = "thumbs_up"
	THUMBS_DOWN = "thumbs_down"


def generate_uuid() -> str:
	return str(uuid.uuid4())


class User(Base):
	__tablename__ = "users"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	email: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
	username: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
	hashed_password: Mapped[Optional[str]] = mapped_column(String)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)
	is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
	is_test: Mapped[bool] = mapped_column(Boolean, default=False)
	role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
	created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())

	# OAuth related fields
	oauth_provider: Mapped[Optional[str]] = mapped_column(String)  # "google", "github", etc.
	oauth_id: Mapped[Optional[str]] = mapped_column(String)

	# User's photos
	photos: Mapped[List["Photo"]] = relationship(back_populates="owner")

	# Auto-upload settings
	auto_upload_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
	auto_upload_folder: Mapped[Optional[str]] = mapped_column(String)


class Photo(Base):
	__tablename__ = "photos"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	filename: Mapped[Optional[str]] = mapped_column(String)  # Secure filename for storage
	original_filename: Mapped[Optional[str]] = mapped_column(String)  # Original filename for display
	file_md5: Mapped[Optional[str]] = mapped_column(String, index=True)  # MD5 hash for duplicate detection

	# Location data
	geometry: Mapped[Any] = mapped_column(Geometry('POINT', srid=4326), nullable=True)  # PostGIS geometry for spatial queries
	altitude: Mapped[Optional[float]] = mapped_column(Float)
	compass_angle: Mapped[Optional[float]] = mapped_column(Float)  # Same as bearing

	# Image dimensions
	width: Mapped[Optional[int]] = mapped_column(Integer)
	height: Mapped[Optional[int]] = mapped_column(Integer)

	# Metadata
	captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))  # UTC timestamps without timezone
	uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	record_created_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	description: Mapped[Optional[str]] = mapped_column(Text)
	is_public: Mapped[bool] = mapped_column(Boolean, default=True)

	# Processing status and data
	# authorized, completed, error
	processing_status: Mapped[Optional[str]] = mapped_column(String)

	error: Mapped[Optional[str]] = mapped_column(Text)  # Detailed error message if any operation fails
	exif_data: Mapped[Optional[dict]] = mapped_column(JSON)
	detected_objects: Mapped[Optional[dict]] = mapped_column(JSON)
	sizes: Mapped[Optional[dict]] = mapped_column(JSON)

	# Client signature fields for secure uploads
	client_signature: Mapped[Optional[str]] = mapped_column(Text)  # Base64-encoded ECDSA signature from client
	client_public_key_id: Mapped[Optional[str]] = mapped_column(String)  # References the client's key used for signing
	upload_authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # When upload was authorized

	# Worker identity tracking for audit trail
	processed_by_worker: Mapped[Optional[str]] = mapped_column(String)  # Worker ID/signature that processed this photo
	processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # When worker completed processing

	# Relationships
	owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
	owner: Mapped["User"] = relationship(back_populates="photos")


class CachedRegion(Base):
	__tablename__ = "cached_regions"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	bbox: Mapped[Any] = mapped_column(Geometry('POLYGON', srid=4326))  # WGS84 bounding box
	last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	is_complete: Mapped[bool] = mapped_column(Boolean, default=False)  # True if entire region is cached
	photo_count: Mapped[int] = mapped_column(Integer, default=0)
	total_requests: Mapped[int] = mapped_column(Integer, default=1)  # How many times this region was requested

	# Mapillary pagination info
	has_more: Mapped[bool] = mapped_column(Boolean, default=True)  # Whether more data exists from Mapillary


class MapillaryPhotoCache(Base):
	__tablename__ = "mapillary_photo_cache"

	mapillary_id: Mapped[str] = mapped_column(String, primary_key=True)  # Mapillary's photo ID
	geometry: Mapped[Any] = mapped_column(Geometry('POINT', srid=4326))  # WGS84 point location

	# Mapillary data fields
	compass_angle: Mapped[Optional[float]] = mapped_column(Float)
	computed_compass_angle: Mapped[Optional[float]] = mapped_column(Float)
	computed_rotation: Mapped[Optional[float]] = mapped_column(Float)
	computed_altitude: Mapped[Optional[float]] = mapped_column(Float)
	captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
	is_pano: Mapped[bool] = mapped_column(Boolean, default=False)
	thumb_1024_url: Mapped[Optional[str]] = mapped_column(String)

	# Creator information
	creator_username: Mapped[Optional[str]] = mapped_column(String(255))
	creator_id: Mapped[Optional[str]] = mapped_column(String(255))

	# Cache metadata
	cached_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	region_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("cached_regions.id"))

	# Store full Mapillary response for future compatibility
	raw_data: Mapped[Optional[dict]] = mapped_column(JSON)


class TokenBlacklist(Base):
	__tablename__ = "token_blacklist"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	token: Mapped[str] = mapped_column(String, unique=True, index=True)
	user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
	blacklisted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # When the token would naturally expire
	reason: Mapped[Optional[str]] = mapped_column(String)  # logout, password_change, account_disabled, etc.

	# Relationship
	user: Mapped["User"] = relationship()


class SecurityAuditLog(Base):
	__tablename__ = "security_audit_log"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	event_type: Mapped[str] = mapped_column(String, index=True)  # 'login_failed', 'login_success', 'password_change', etc.
	user_identifier: Mapped[Optional[str]] = mapped_column(String, index=True)  # username, email, or user_id
	ip_address: Mapped[Optional[str]] = mapped_column(String, index=True)
	user_agent: Mapped[Optional[str]] = mapped_column(String)
	event_details: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional context like attempt count, etc.
	severity: Mapped[str] = mapped_column(String, default='info')  # 'info', 'warning', 'critical'
	timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

	# Optional user relationship for successful authentications
	user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
	user: Mapped[Optional["User"]] = relationship()


class HiddenPhoto(Base):
	__tablename__ = "hidden_photos"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
	photo_source: Mapped[str] = mapped_column(String(20))  # 'mapillary' or 'hillview'
	photo_id: Mapped[str] = mapped_column(String(255))
	hidden_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	reason: Mapped[Optional[str]] = mapped_column(String(100))
	extra_data: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional context like creator info, etc.

	# Relationships
	user: Mapped["User"] = relationship()

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraint to prevent duplicate hides
		{"schema": None}  # Placeholder - actual constraints in migration
	)


class HiddenUser(Base):
	__tablename__ = "hidden_users"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	hiding_user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
	target_user_source: Mapped[str] = mapped_column(String(20))  # 'mapillary' or 'hillview'
	target_user_id: Mapped[str] = mapped_column(String(255))  # User ID from the source platform
	hidden_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	reason: Mapped[Optional[str]] = mapped_column(String(100))
	extra_data: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional context about the hidden user

	# Relationships
	hiding_user: Mapped["User"] = relationship()

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraints and checks defined in migration
		{"schema": None}  # Placeholder - actual constraints in migration
	)


class PhotoRating(Base):
	__tablename__ = "photo_ratings"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
	photo_source: Mapped[str] = mapped_column(String(20))  # 'mapillary' or 'hillview'
	photo_id: Mapped[str] = mapped_column(String(255))
	rating: Mapped[PhotoRatingType] = mapped_column(Enum(PhotoRatingType))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

	# Relationships
	user: Mapped["User"] = relationship()

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraint to prevent duplicate ratings per user per photo
		{"schema": None}  # Placeholder - actual constraints in migration
	)


class FlaggedPhoto(Base):
	__tablename__ = "flagged_photos"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	flagging_user_id: Mapped[Optional[str]] = mapped_column(String)  # Keep user ID for audit, no FK constraint
	photo_source: Mapped[str] = mapped_column(String(20))  # 'mapillary' or 'hillview'
	photo_id: Mapped[str] = mapped_column(String(255))
	flagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	reason: Mapped[Optional[str]] = mapped_column(Text)  # Text field for longer reason descriptions
	extra_data: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional context like creator info, etc.
	resolved: Mapped[bool] = mapped_column(Boolean, default=False)  # Admin can mark as resolved
	resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # When resolved
	resolved_by: Mapped[Optional[str]] = mapped_column(String)  # Admin user ID who resolved it

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraint to prevent duplicate flags
		{"schema": None}  # Placeholder - actual constraints in migration
	)


class UserPublicKey(Base):
	__tablename__ = "user_public_keys"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
	key_id: Mapped[str] = mapped_column(String, index=True)  # Client-generated key identifier
	public_key_pem: Mapped[str] = mapped_column(Text)  # PEM-formatted ECDSA P-256 public key
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # When key was created on client
	registered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())  # When registered with server
	is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # For key rotation/revocation

	# Relationships
	user: Mapped["User"] = relationship()

	# Ensure unique key_id per user
	__table_args__ = (
		{"schema": None}  # Actual unique constraint in migration: (user_id, key_id)
	)


class ContactMessage(Base):
	__tablename__ = "contact_messages"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	contact_info: Mapped[str] = mapped_column(String(500))  # Email or other contact method
	message: Mapped[str] = mapped_column(Text)
	user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id"))  # Optional - for logged in users
	ip_address: Mapped[Optional[str]] = mapped_column(String(45))  # Store IP for spam prevention
	user_agent: Mapped[Optional[str]] = mapped_column(String(1000))  # Store user agent for context
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	status: Mapped[str] = mapped_column(String(20), default='new')  # new, read, replied, archived
	admin_notes: Mapped[Optional[str]] = mapped_column(Text)  # For admin use
	replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
	replied_by: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id"))  # Admin user ID who replied

	# Relationships
	user: Mapped[Optional["User"]] = relationship(foreign_keys=[user_id], back_populates=None)
	replied_by_user: Mapped[Optional["User"]] = relationship(foreign_keys=[replied_by], back_populates=None)


class PushRegistration(Base):
	__tablename__ = "push_registrations"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	client_key_id: Mapped[str] = mapped_column(String, unique=True, index=True)  # From ClientCryptoManager
	push_endpoint: Mapped[str] = mapped_column(Text)  # URL for sending push messages
	distributor_package: Mapped[Optional[str]] = mapped_column(String)  # Package name of distributor app
	created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())


class Notification(Base):
	__tablename__ = "notifications"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Use BIGSERIAL for high volume
	user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
	client_key_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("push_registrations.client_key_id", ondelete="CASCADE"), index=True)
	type: Mapped[str] = mapped_column(String(50))  # 'user_upload', 'photo_liked', 'follow', etc.
	title: Mapped[str] = mapped_column(Text)
	body: Mapped[str] = mapped_column(Text)
	action_type: Mapped[Optional[str]] = mapped_column(String(50))  # 'open_profile', 'open_photo', etc.
	action_data: Mapped[Optional[dict]] = mapped_column(JSON)  # {user_id: "123", photo_id: "456"}
	read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
	created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # Auto-cleanup old notifications

	# Relationships
	user: Mapped[Optional["User"]] = relationship()
	push_registration: Mapped[Optional["PushRegistration"]] = relationship(foreign_keys=[client_key_id])

	__table_args__ = (
		CheckConstraint(
			'(user_id IS NOT NULL AND client_key_id IS NULL) OR (user_id IS NULL AND client_key_id IS NOT NULL)',
			name='notifications_user_or_key_check'
		),
	)

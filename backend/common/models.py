from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime, Text, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from geoalchemy2 import Geometry
from .database import Base
import uuid
import enum

class UserRole(enum.Enum):
	USER = "user"
	ADMIN = "admin"
	MODERATOR = "moderator"

class PhotoRatingType(enum.Enum):
	THUMBS_UP = "thumbs_up"
	THUMBS_DOWN = "thumbs_down"

def generate_uuid():
	return str(uuid.uuid4())

class User(Base):
	__tablename__ = "users"

	id = Column(String, primary_key=True, default=generate_uuid)
	email = Column(String, unique=True, index=True)
	username = Column(String, unique=True, index=True)
	hashed_password = Column(String, nullable=True)
	is_active = Column(Boolean, default=True)
	is_verified = Column(Boolean, default=False)
	is_test = Column(Boolean, default=False)
	role = Column(Enum(UserRole), default=UserRole.USER)
	created_at = Column(DateTime(timezone=True), server_default=func.now())
	updated_at = Column(DateTime(timezone=True), onupdate=func.now())

	# OAuth related fields
	oauth_provider = Column(String, nullable=True)  # "google", "github", etc.
	oauth_id = Column(String, nullable=True)

	# User's photos
	photos = relationship("Photo", back_populates="owner")

	# Auto-upload settings
	auto_upload_enabled = Column(Boolean, default=False)
	auto_upload_folder = Column(String, nullable=True)

class Photo(Base):
	__tablename__ = "photos"

	id = Column(String, primary_key=True, default=generate_uuid)
	filename = Column(String)  # Secure filename for storage
	original_filename = Column(String)  # Original filename for display
	file_md5 = Column(String, nullable=True, index=True)  # MD5 hash for duplicate detection

	# Location data
	geometry = Column(Geometry('POINT', srid=4326), nullable=True)  # PostGIS geometry for spatial queries
	altitude = Column(Float, nullable=True)
	compass_angle = Column(Float, nullable=True)  # Same as bearing

	# Image dimensions
	width = Column(Integer, nullable=True)
	height = Column(Integer, nullable=True)

	# Metadata
	captured_at = Column(DateTime(timezone=False), nullable=True)  # UTC timestamps without timezone
	uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
	record_created_ts = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
	description = Column(Text, nullable=True)
	is_public = Column(Boolean, default=True)

	# Processing status and data

	# authorized, completed, error
	processing_status = Column(String)


	error = Column(Text, nullable=True)  # Detailed error message if any operation fails
	exif_data = Column(JSON, nullable=True)
	detected_objects = Column(JSON, nullable=True)
	sizes = Column(JSON, nullable=True)

	# Client signature fields for secure uploads
	client_signature = Column(Text, nullable=True)  # Base64-encoded ECDSA signature from client
	client_public_key_id = Column(String, nullable=True)  # References the client's key used for signing
	upload_authorized_at = Column(DateTime(timezone=True), nullable=True)  # When upload was authorized

	# Worker identity tracking for audit trail
	processed_by_worker = Column(String, nullable=True)  # Worker ID/signature that processed this photo
	processed_at = Column(DateTime(timezone=True), nullable=True)  # When worker completed processing

	# Relationships
	owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
	owner = relationship("User", back_populates="photos")

class CachedRegion(Base):
	__tablename__ = "cached_regions"

	id = Column(String, primary_key=True, default=generate_uuid)
	bbox = Column(Geometry('POLYGON', srid=4326))  # WGS84 bounding box
	last_updated = Column(DateTime(timezone=True), server_default=func.now())
	is_complete = Column(Boolean, default=False)  # True if entire region is cached
	photo_count = Column(Integer, default=0)
	total_requests = Column(Integer, default=1)  # How many times this region was requested

	# Mapillary pagination info
	has_more = Column(Boolean, default=True)  # Whether more data exists from Mapillary

	# Relationships
	cached_photos = relationship("MapillaryPhotoCache", back_populates="region")

class MapillaryPhotoCache(Base):
	__tablename__ = "mapillary_photo_cache"

	mapillary_id = Column(String, primary_key=True)  # Mapillary's photo ID
	geometry = Column(Geometry('POINT', srid=4326))  # WGS84 point location

	# Mapillary data fields
	compass_angle = Column(Float, nullable=True)
	computed_compass_angle = Column(Float, nullable=True)
	computed_rotation = Column(Float, nullable=True)
	computed_altitude = Column(Float, nullable=True)
	captured_at = Column(DateTime(timezone=True), nullable=True)
	is_pano = Column(Boolean, default=False)
	thumb_1024_url = Column(String, nullable=True)

	# Creator information
	creator_username = Column(String(255), nullable=True)
	creator_id = Column(String(255), nullable=True)

	# Cache metadata
	cached_at = Column(DateTime(timezone=True), server_default=func.now())
	region_id = Column(String, ForeignKey("cached_regions.id"))

	# Store full Mapillary response for future compatibility
	raw_data = Column(JSON, nullable=True)

	# Relationships
	region = relationship("CachedRegion", back_populates="cached_photos")

class TokenBlacklist(Base):
	__tablename__ = "token_blacklist"

	id = Column(String, primary_key=True, default=generate_uuid)
	token = Column(String, unique=True, index=True, nullable=False)
	user_id = Column(String, ForeignKey("users.id"), nullable=False)
	blacklisted_at = Column(DateTime(timezone=True), server_default=func.now())
	expires_at = Column(DateTime(timezone=True), nullable=False)  # When the token would naturally expire
	reason = Column(String, nullable=True)  # logout, password_change, account_disabled, etc.

	# Relationship
	user = relationship("User")

class SecurityAuditLog(Base):
	__tablename__ = "security_audit_log"

	id = Column(String, primary_key=True, default=generate_uuid)
	event_type = Column(String, nullable=False, index=True)  # 'login_failed', 'login_success', 'password_change', etc.
	user_identifier = Column(String, nullable=True, index=True)  # username, email, or user_id
	ip_address = Column(String, nullable=True, index=True)
	user_agent = Column(String, nullable=True)
	event_details = Column(JSON, nullable=True)  # Additional context like attempt count, etc.
	severity = Column(String, nullable=False, default='info')  # 'info', 'warning', 'critical'
	timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

	# Optional user relationship for successful authentications
	user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
	user = relationship("User")

class HiddenPhoto(Base):
	__tablename__ = "hidden_photos"

	id = Column(String, primary_key=True, default=generate_uuid)
	user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
	photo_source = Column(String(20), nullable=False)  # 'mapillary' or 'hillview'
	photo_id = Column(String(255), nullable=False)
	hidden_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
	reason = Column(String(100), nullable=True)
	extra_data = Column(JSON, nullable=True)  # Additional context like creator info, etc.

	# Relationships
	user = relationship("User")

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraint to prevent duplicate hides
		{"schema": None}  # Placeholder - actual constraints in migration
	)

class HiddenUser(Base):
	__tablename__ = "hidden_users"

	id = Column(String, primary_key=True, default=generate_uuid)
	hiding_user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
	target_user_source = Column(String(20), nullable=False)  # 'mapillary' or 'hillview'
	target_user_id = Column(String(255), nullable=False)  # User ID from the source platform
	hidden_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
	reason = Column(String(100), nullable=True)
	extra_data = Column(JSON, nullable=True)  # Additional context about the hidden user

	# Relationships
	hiding_user = relationship("User")

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraints and checks defined in migration
		{"schema": None}  # Placeholder - actual constraints in migration
	)

class PhotoRating(Base):
	__tablename__ = "photo_ratings"

	id = Column(String, primary_key=True, default=generate_uuid)
	user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
	photo_source = Column(String(20), nullable=False)  # 'mapillary' or 'hillview'
	photo_id = Column(String(255), nullable=False)
	rating = Column(Enum(PhotoRatingType), nullable=False)
	created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

	# Relationships
	user = relationship("User")

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraint to prevent duplicate ratings per user per photo
		{"schema": None}  # Placeholder - actual constraints in migration
	)

class FlaggedPhoto(Base):
	__tablename__ = "flagged_photos"

	id = Column(String, primary_key=True, default=generate_uuid)
	flagging_user_id = Column(String, nullable=True)  # Keep user ID for audit, no FK constraint
	photo_source = Column(String(20), nullable=False)  # 'mapillary' or 'hillview'
	photo_id = Column(String(255), nullable=False)
	flagged_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
	reason = Column(Text, nullable=True)  # Text field for longer reason descriptions
	extra_data = Column(JSON, nullable=True)  # Additional context like creator info, etc.
	resolved = Column(Boolean, default=False, nullable=False)  # Admin can mark as resolved
	resolved_at = Column(DateTime(timezone=True), nullable=True)  # When resolved
	resolved_by = Column(String, nullable=True)  # Admin user ID who resolved it

	# Table constraints are defined in the migration
	__table_args__ = (
		# Unique constraint to prevent duplicate flags
		{"schema": None}  # Placeholder - actual constraints in migration
	)

class UserPublicKey(Base):
	__tablename__ = "user_public_keys"

	id = Column(String, primary_key=True, default=generate_uuid)
	user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
	key_id = Column(String, nullable=False, index=True)  # Client-generated key identifier
	public_key_pem = Column(Text, nullable=False)  # PEM-formatted ECDSA P-256 public key
	created_at = Column(DateTime(timezone=True), nullable=False)  # When key was created on client
	registered_at = Column(DateTime(timezone=True), server_default=func.now())  # When registered with server
	is_active = Column(Boolean, default=True)  # For key rotation/revocation

	# Relationships
	user = relationship("User")

	# Ensure unique key_id per user
	__table_args__ = (
		{"schema": None}  # Actual unique constraint in migration: (user_id, key_id)
	)


class ContactMessage(Base):
	__tablename__ = "contact_messages"

	id = Column(Integer, primary_key=True)
	contact_info = Column(String(500), nullable=False)  # Email or other contact method
	message = Column(Text, nullable=False)
	user_id = Column(String, ForeignKey("users.id"), nullable=True)  # Optional - for logged in users
	ip_address = Column(String(45), nullable=True)  # Store IP for spam prevention
	user_agent = Column(String(1000), nullable=True)  # Store user agent for context
	created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
	status = Column(String(20), default='new', nullable=False)  # new, read, replied, archived
	admin_notes = Column(Text, nullable=True)  # For admin use
	replied_at = Column(DateTime(timezone=True), nullable=True)
	replied_by = Column(String, ForeignKey("users.id"), nullable=True)  # Admin user ID who replied

	# Relationships
	user = relationship("User", foreign_keys=[user_id], back_populates=None)
	replied_by_user = relationship("User", foreign_keys=[replied_by], back_populates=None)


class PushRegistration(Base):
	__tablename__ = "push_registrations"

	id = Column(String, primary_key=True, default=generate_uuid)
	client_key_id = Column(String, nullable=False, unique=True, index=True)  # From ClientCryptoManager
	push_endpoint = Column(Text, nullable=False)  # URL for sending push messages
	distributor_package = Column(String, nullable=True)  # Package name of distributor app
	created_at = Column(DateTime(timezone=True), server_default=func.now())
	updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Notification(Base):
	__tablename__ = "notifications"

	id = Column(Integer, primary_key=True)  # Use BIGSERIAL for high volume
	user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
	type = Column(String(50), nullable=False)  # 'user_upload', 'photo_liked', 'follow', etc.
	title = Column(Text, nullable=False)
	body = Column(Text, nullable=False)
	action_type = Column(String(50), nullable=True)  # 'open_profile', 'open_photo', etc.
	action_data = Column(JSON, nullable=True)  # {user_id: "123", photo_id: "456"}
	read_at = Column(DateTime(timezone=True), nullable=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now())
	expires_at = Column(DateTime(timezone=True), nullable=True)  # Auto-cleanup old notifications

	# Relationships
	user = relationship("User")

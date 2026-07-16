"""SQLAlchemy 2.0 typed models for Hillview backend."""
from datetime import datetime
from typing import Optional, List, Any
import uuid
import enum

from sqlalchemy import String, Float, Integer, Boolean, DateTime, Text, JSON, Enum, ForeignKey, CheckConstraint, ARRAY, Index, text
from sqlalchemy.dialects.postgresql import JSONB
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

	# Composite index for the capture-time "timeline walk" feature
	# (GET /api/hillview/timeline): keyset range ordered by
	# (effective_at, coalesce(original_filename, ''), id) within one or more
	# owners. effective_at = captured_at, else upload time — kept current by a DB
	# trigger (migration 022). The original_filename tiebreak (migration 023)
	# orders burst shots that share a 1-second captured_at; COALESCE keeps null
	# filenames in the keyset walk. Declared here too (not just in the migration)
	# so --autogenerate doesn't try to drop it.
	__table_args__ = (
		Index('ix_photos_owner_effective_at_filename_id', 'owner_id', 'effective_at',
			func.coalesce(text('original_filename'), ''), 'id'),
	)

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
	# Capture time if known, else upload time (naive UTC). Maintained by a DB
	# trigger (migration 022); indexed for the capture-time timeline walk.
	effective_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False))
	record_created_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
	title: Mapped[Optional[str]] = mapped_column(Text)  # concise headline (og:title, <title>, schema.org name)
	description: Mapped[Optional[str]] = mapped_column(Text)  # longer body text
	keywords: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))  # alt names / search synonyms (schema.org keywords)
	# Reverse-geocoded place (backfilled out-of-band; see scripts/backfill_places.py)
	geocode: Mapped[Optional[dict]] = mapped_column(JSONB)  # raw {address, display_name} — re-derive without re-geocoding
	place_name: Mapped[Optional[str]] = mapped_column(Text)  # display label e.g. "Prosek, Praha"
	place_slug: Mapped[Optional[str]] = mapped_column(Text, index=True)  # grouping key for place pages
	place_parent_name: Mapped[Optional[str]] = mapped_column(Text)  # hub display e.g. "Praha"
	place_parent_slug: Mapped[Optional[str]] = mapped_column(Text, index=True)  # hub grouping key e.g. "praha-cz"
	# Not a privacy control, despite the name — is_listed would be honest: it only
	# filters DB queries (e.g. the visibility clause in hillview_routes.py). Every
	# derivative is written to the same unauthenticated pics pool regardless, so an
	# is_public=False photo's bytes stay fetchable by anyone with the URL — making
	# it real needs signed URLs or an auth check at the file layer.
	is_public: Mapped[bool] = mapped_column(Boolean, default=True)

	# Processing status and data
	# authorized, completed, error
	processing_status: Mapped[Optional[str]] = mapped_column(String)

	error: Mapped[Optional[str]] = mapped_column(Text)  # Detailed error message if any operation fails
	retry_after_minutes: Mapped[Optional[int]] = mapped_column(Integer)  # Retry hint for a failed processing: None = permanent (don't retry), >0 = retry after N minutes
	exif_data: Mapped[Optional[dict]] = mapped_column(JSON)
	detected_objects: Mapped[Optional[dict]] = mapped_column(JSON)
	sizes: Mapped[Optional[dict]] = mapped_column(JSON)
	analysis: Mapped[Optional[dict]] = mapped_column(JSONB)  # AI-generated photo analysis (indexed)

	# Client signature fields for secure uploads
	client_signature: Mapped[Optional[str]] = mapped_column(Text)  # Base64-encoded ECDSA signature from client
	client_public_key_id: Mapped[Optional[str]] = mapped_column(String)  # References the client's key used for signing
	upload_authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # When upload was authorized

	# Worker identity tracking for audit trail
	processed_by_worker: Mapped[Optional[str]] = mapped_column(String)  # Worker ID/signature that processed this photo
	processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))  # When worker completed processing

	# License / legal rights identifier (e.g. 'full1', 'ccbysa4')
	legal_rights: Mapped[Optional[str]] = mapped_column(String, nullable=True)

	# Featured photo flag
	featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')

	# Soft delete
	deleted: Mapped[bool] = mapped_column(Boolean, default=False)

	# Version for re-upload support (e.g., changing anonymization settings)
	version: Mapped[int] = mapped_column(Integer, default=1)

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
	photo_source: Mapped[str] = mapped_column(String(20))  # 'mapillary', 'hillview', or 'panoramax'
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
	target_user_source: Mapped[str] = mapped_column(String(20))  # 'mapillary', 'hillview', or 'panoramax'
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
	photo_source: Mapped[str] = mapped_column(String(20))  # 'mapillary', 'hillview', or 'panoramax'
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
	photo_source: Mapped[str] = mapped_column(String(20))  # 'mapillary', 'hillview', or 'panoramax'
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


class PhotoModerationAudit(Base):
	"""Audit trail of moderation actions taken by admins/moderators on photos
	they do not own (currently: deletions).

	Deliberately denormalized and free of FK cascade deletes: the actor's and
	the owner's usernames/ids are snapshotted so the record survives later
	deletion of either account, and ``extra_data`` snapshots a little about the
	photo (filename, title) since the photo row itself may later be hard-deleted.
	"""
	__tablename__ = "photo_moderation_audit"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	action: Mapped[str] = mapped_column(String(32), index=True)  # 'delete'

	# Actor: the admin/moderator who performed the action.
	actor_user_id: Mapped[str] = mapped_column(String, index=True)  # no FK — keep audit if actor is deleted
	actor_username: Mapped[Optional[str]] = mapped_column(String)  # denormalized snapshot
	actor_role: Mapped[Optional[str]] = mapped_column(String)  # role value at time of action

	# Target photo and its owner at the time of the action.
	photo_source: Mapped[str] = mapped_column(String(20), default='hillview')
	photo_id: Mapped[str] = mapped_column(String(255), index=True)
	photo_owner_id: Mapped[Optional[str]] = mapped_column(String, index=True)  # no FK — keep audit if owner is deleted
	photo_owner_username: Mapped[Optional[str]] = mapped_column(String)  # denormalized snapshot

	reason: Mapped[Optional[str]] = mapped_column(Text)
	ip_address: Mapped[Optional[str]] = mapped_column(String)
	user_agent: Mapped[Optional[str]] = mapped_column(String)
	extra_data: Mapped[Optional[dict]] = mapped_column(JSON)  # photo snapshot (filename, title, etc.)

	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class AnnotationModeration(Base):
	"""Record of a reactive moderation action (undo/revert) on an annotation chain.

	Mirrors ``PhotoModerationAudit``: denormalized snapshots and no FK cascades, so
	the record survives later removal of the moderator, the subject author, the
	annotation rows, or the photo. ``reason`` (optional) is what gets surfaced to
	the affected author via a ``Notification`` (linked by ``notification_id``).
	"""
	__tablename__ = "annotation_moderation"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	action: Mapped[str] = mapped_column(String(32), index=True)  # 'undo_create' | 'undo_update' | 'undo_delete'

	# The annotation event that was undone, and the new event the undo produced.
	target_event_id: Mapped[str] = mapped_column(String, index=True)  # no FK — keep record if the row is gone
	result_event_id: Mapped[Optional[str]] = mapped_column(String)
	photo_id: Mapped[Optional[str]] = mapped_column(String(255), index=True)

	# Moderator who performed the undo (denormalized snapshot).
	moderator_user_id: Mapped[str] = mapped_column(String, index=True)
	moderator_username: Mapped[Optional[str]] = mapped_column(String)
	moderator_role: Mapped[Optional[str]] = mapped_column(String)

	# Subject: the author whose work was reverted (denormalized snapshot).
	subject_user_id: Mapped[Optional[str]] = mapped_column(String, index=True)
	subject_username: Mapped[Optional[str]] = mapped_column(String)

	reason: Mapped[Optional[str]] = mapped_column(Text)
	notification_id: Mapped[Optional[int]] = mapped_column(Integer)  # the Notification row sent to the subject

	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class UserModeration(Base):
	"""Audit trail of admin user-management actions (role changes, suspensions,
	deletions), mirroring the other moderation-audit tables: denormalized and
	FK-cascade-free so the record survives deletion of the actor or the target.
	"""
	__tablename__ = "user_moderation"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	action: Mapped[str] = mapped_column(String(32), index=True)  # 'role_change' | 'suspend' | 'reactivate' | 'delete'

	# Actor (the admin performing the action) — denormalized snapshot.
	actor_user_id: Mapped[str] = mapped_column(String, index=True)
	actor_username: Mapped[Optional[str]] = mapped_column(String)
	actor_role: Mapped[Optional[str]] = mapped_column(String)

	# Subject (the user acted upon) — denormalized snapshot.
	target_user_id: Mapped[str] = mapped_column(String, index=True)
	target_username: Mapped[Optional[str]] = mapped_column(String)

	old_role: Mapped[Optional[str]] = mapped_column(String)
	new_role: Mapped[Optional[str]] = mapped_column(String)
	old_active: Mapped[Optional[bool]] = mapped_column(Boolean)
	new_active: Mapped[Optional[bool]] = mapped_column(Boolean)
	reason: Mapped[Optional[str]] = mapped_column(Text)

	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


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


class PhotoAnnotation(Base):
	"""A user-created annotation on a photo.

	The data model is intentionally simple (free-for-all) for the initial implementation.
	Future evolution should move toward a web-of-trust / RDF-based schema where:
	  - trust/karma scores determine annotation visibility
	  - conflict resolution is handled by the trust graph rather than central moderation
	  - annotations are linked to each other via superseded_by for transparent edit history
	  - the full RDF graph could be exported / federated across instances
	  - per-annotation endorsements / disputes form the basis of decentralised moderation
	"""
	__tablename__ = "photo_annotations"

	id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
	photo_id: Mapped[str] = mapped_column(String, ForeignKey("photos.id", ondelete="CASCADE"), index=True)
	user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))

	# Annotation content – W3C Web Annotation compatible fields
	body: Mapped[Optional[str]] = mapped_column(Text)  # Human-readable text
	# target stores the complete Annotorious selector JSON (shape, coordinates, etc.)
	target: Mapped[Optional[dict]] = mapped_column(JSON)

	# Version tracking: updating an annotation creates a new row and marks this one superseded
	is_current: Mapped[bool] = mapped_column(Boolean, default=True)
	superseded_by: Mapped[Optional[str]] = mapped_column(
		String, ForeignKey("photo_annotations.id", ondelete="SET NULL"), nullable=True
	)

	created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=func.now())
	event_type: Mapped[str] = mapped_column(String(16), default='created')

	# Relationships
	photo: Mapped["Photo"] = relationship()
	user: Mapped["User"] = relationship()


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

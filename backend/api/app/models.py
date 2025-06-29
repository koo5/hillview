from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base
import uuid

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
    filename = Column(String)
    filepath = Column(String)
    thumbnail_path = Column(String, nullable=True)
    
    # Location data
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    altitude = Column(Float, nullable=True)
    compass_angle = Column(Float, nullable=True)
    
    # Metadata
    captured_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=True)
    
    # Relationships
    owner_id = Column(String, ForeignKey("users.id"))
    owner = relationship("User", back_populates="photos")

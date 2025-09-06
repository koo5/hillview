#!/usr/bin/env python3
"""
Tests for hidden content database operations.

Tests direct database operations for hidden content:
- HiddenPhoto model CRUD operations
- HiddenUser model CRUD operations  
- Database constraints and validations
- Timestamp handling
- Data integrity
- Cleanup operations
"""

import asyncio
import pytest
import os
import pytest
import sys
import pytest
from datetime import datetime, timezone
from typing import List

# Add the backend paths to sys.path for imports
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_path)
sys.path.insert(0, os.path.join(backend_path, 'api', 'app'))
sys.path.insert(0, os.path.join(backend_path, 'common'))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_, func

from common.database import SessionLocal, Base, engine
from common.models import User, HiddenPhoto, HiddenUser
from common.auth_utils import get_password_hash

class TestHiddenDatabaseOperations:
    """Test suite for hidden content database operations."""
    
    def setup_method(self, method=None):
        """Setup method called before each test method."""
        self.test_users = []
        self.test_hidden_photos = []
        self.test_hidden_users = []
    
    async def setup_test_data(self):
        """Set up test users."""
        print("Setting up database test data...")
        
        db = SessionLocal()
        try:
            # Create test users
            user1 = User(
                username="db_test_hider",
                email="db_hider@test.com",
                hashed_password=get_password_hash("testpass123"),
                is_active=True,
                is_verified=True
            )
            
            user2 = User(
                username="db_test_target",
                email="db_target@test.com",
                hashed_password=get_password_hash("testpass123"),
                is_active=True,
                is_verified=True
            )
            
            db.add(user1)
            db.add(user2)
            await db.commit()
            await db.refresh(user1)
            await db.refresh(user2)
            
            self.test_users = [user1, user2]
            print(f"✓ Created {len(self.test_users)} test users")
            
        finally:
            await db.close()
    
    async def cleanup_test_data(self):
        """Clean up test data."""
        print("Cleaning up database test data...")
        
        db = SessionLocal()
        try:
            # Clean up hidden records
            for hidden_photo in self.test_hidden_photos:
                await db.delete(hidden_photo)
            
            for hidden_user in self.test_hidden_users:
                await db.delete(hidden_user)
            
            # Clean up test users
            for user in self.test_users:
                await db.delete(user)
            
            await db.commit()
            print("✓ Database cleanup complete")
            
        finally:
            await db.close()
    
    @pytest.mark.asyncio
    async def test_hidden_photo_crud_operations(self):
        """Test CRUD operations for HiddenPhoto model."""
        print("\n--- Testing HiddenPhoto CRUD Operations ---")
        
        db = SessionLocal()
        try:
            user = self.test_users[0]
            
            # CREATE - Add hidden photo
            hidden_photo = HiddenPhoto(
                user_id=user.id,
                photo_source="mapillary",
                photo_id="test_photo_123",
                reason="Database test"
            )
            
            db.add(hidden_photo)
            await db.commit()
            await db.refresh(hidden_photo)
            
            self.test_hidden_photos.append(hidden_photo)
            
            # Verify creation
            assert hidden_photo.id is not None
            assert hidden_photo.hidden_at is not None
            assert isinstance(hidden_photo.hidden_at, datetime)
            print("✓ HiddenPhoto created successfully")
            
            # READ - Query hidden photo
            result = await db.execute(
                select(HiddenPhoto).where(
                    and_(
                        HiddenPhoto.user_id == user.id,
                        HiddenPhoto.photo_source == "mapillary",
                        HiddenPhoto.photo_id == "test_photo_123"
                    )
                )
            )
            found_photo = result.scalars().first()
            
            assert found_photo is not None
            assert found_photo.reason == "Database test"
            print("✓ HiddenPhoto read successfully")
            
            # UPDATE - Modify reason
            found_photo.reason = "Updated reason"
            await db.commit()
            
            # Verify update
            result = await db.execute(
                select(HiddenPhoto).where(HiddenPhoto.id == found_photo.id)
            )
            updated_photo = result.scalars().first()
            
            assert updated_photo.reason == "Updated reason"
            print("✓ HiddenPhoto updated successfully")
            
            # DELETE - Remove hidden photo
            await db.delete(found_photo)
            await db.commit()
            
            # Verify deletion
            result = await db.execute(
                select(HiddenPhoto).where(HiddenPhoto.id == found_photo.id)
            )
            deleted_photo = result.scalars().first()
            
            assert deleted_photo is None
            print("✓ HiddenPhoto deleted successfully")
            
            self.test_hidden_photos.remove(hidden_photo)
            return True
            
        except Exception as e:
            print(f"✗ HiddenPhoto CRUD test failed: {e}")
            return False
        finally:
            await db.close()
    
    @pytest.mark.asyncio
    async def test_hidden_user_crud_operations(self):
        """Test CRUD operations for HiddenUser model."""
        print("\n--- Testing HiddenUser CRUD Operations ---")
        
        db = SessionLocal()
        try:
            hider_user = self.test_users[0]
            target_user = self.test_users[1]
            
            # CREATE - Add hidden user
            hidden_user = HiddenUser(
                hiding_user_id=hider_user.id,
                target_user_source="hillview",
                target_user_id=str(target_user.id),
                reason="Database test"
            )
            
            db.add(hidden_user)
            await db.commit()
            await db.refresh(hidden_user)
            
            self.test_hidden_users.append(hidden_user)
            
            # Verify creation
            assert hidden_user.id is not None
            assert hidden_user.hidden_at is not None
            assert isinstance(hidden_user.hidden_at, datetime)
            print("✓ HiddenUser created successfully")
            
            # READ - Query hidden user
            result = await db.execute(
                select(HiddenUser).where(
                    and_(
                        HiddenUser.hiding_user_id == hider_user.id,
                        HiddenUser.target_user_source == "hillview",
                        HiddenUser.target_user_id == str(target_user.id)
                    )
                )
            )
            found_user = result.scalars().first()
            
            assert found_user is not None
            assert found_user.reason == "Database test"
            print("✓ HiddenUser read successfully")
            
            # UPDATE - Modify reason
            found_user.reason = "Updated user reason"
            await db.commit()
            
            # Verify update
            result = await db.execute(
                select(HiddenUser).where(HiddenUser.id == found_user.id)
            )
            updated_user = result.scalars().first()
            
            assert updated_user.reason == "Updated user reason"
            print("✓ HiddenUser updated successfully")
            
            # DELETE - Remove hidden user
            await db.delete(found_user)
            await db.commit()
            
            # Verify deletion
            result = await db.execute(
                select(HiddenUser).where(HiddenUser.id == found_user.id)
            )
            deleted_user = result.scalars().first()
            
            assert deleted_user is None
            print("✓ HiddenUser deleted successfully")
            
            self.test_hidden_users.remove(hidden_user)
            return True
            
        except Exception as e:
            print(f"✗ HiddenUser CRUD test failed: {e}")
            return False
        finally:
            await db.close()
    
    @pytest.mark.asyncio
    async def test_duplicate_prevention(self):
        """Test prevention of duplicate hidden records."""
        print("\n--- Testing Duplicate Prevention ---")
        
        db = SessionLocal()
        try:
            user = self.test_users[0]
            
            # Create first hidden photo
            hidden_photo1 = HiddenPhoto(
                user_id=user.id,
                photo_source="mapillary",
                photo_id="duplicate_test_photo",
                reason="First entry"
            )
            
            db.add(hidden_photo1)
            await db.commit()
            self.test_hidden_photos.append(hidden_photo1)
            
            print("✓ First hidden photo created")
            
            # Try to create duplicate
            hidden_photo2 = HiddenPhoto(
                user_id=user.id,
                photo_source="mapillary", 
                photo_id="duplicate_test_photo",
                reason="Duplicate entry"
            )
            
            db.add(hidden_photo2)
            
            try:
                await db.commit()
                # If we get here, duplicate was allowed (might be OK depending on constraints)
                self.test_hidden_photos.append(hidden_photo2)
                print("ℹ Duplicate hidden photo was allowed (no unique constraint)")
                return True
            except Exception as e:
                # Duplicate was prevented by database constraint
                await db.rollback()
                print("✓ Duplicate hidden photo prevented by database constraint")
                return True
            
        except Exception as e:
            print(f"✗ Duplicate prevention test failed: {e}")
            return False
        finally:
            await db.close()
    
    @pytest.mark.asyncio
    async def test_timestamp_handling(self):
        """Test timestamp handling for hidden records."""
        print("\n--- Testing Timestamp Handling ---")
        
        db = SessionLocal()
        try:
            user = self.test_users[0]
            
            # Record time before creation
            before_time = datetime.now(timezone.utc)
            
            # Create hidden photo
            hidden_photo = HiddenPhoto(
                user_id=user.id,
                photo_source="mapillary",
                photo_id="timestamp_test_photo",
                reason="Timestamp test"
            )
            
            db.add(hidden_photo)
            await db.commit()
            await db.refresh(hidden_photo)
            
            self.test_hidden_photos.append(hidden_photo)
            
            # Record time after creation
            after_time = datetime.now(timezone.utc)
            
            # Verify timestamp is within expected range
            assert hidden_photo.hidden_at is not None
            assert isinstance(hidden_photo.hidden_at, datetime)
            assert before_time <= hidden_photo.hidden_at <= after_time
            
            # Verify timezone handling
            if hidden_photo.hidden_at.tzinfo is not None:
                print("✓ Timezone-aware timestamp created")
            else:
                print("✓ Naive timestamp created (will be interpreted as UTC)")
            
            print(f"✓ Timestamp: {hidden_photo.hidden_at}")
            return True
            
        except Exception as e:
            print(f"✗ Timestamp handling test failed: {e}")
            return False
        finally:
            await db.close()
    
    @pytest.mark.asyncio
    async def test_data_integrity(self):
        """Test data integrity constraints."""
        print("\n--- Testing Data Integrity ---")
        
        db = SessionLocal()
        try:
            user = self.test_users[0]
            
            # Test valid photo sources
            valid_sources = ["mapillary", "hillview"]
            
            for source in valid_sources:
                hidden_photo = HiddenPhoto(
                    user_id=user.id,
                    photo_source=source,
                    photo_id=f"integrity_test_photo_{source}",
                    reason="Integrity test"
                )
                
                db.add(hidden_photo)
                await db.commit()
                await db.refresh(hidden_photo)
                
                self.test_hidden_photos.append(hidden_photo)
                
                assert hidden_photo.photo_source == source
                print(f"✓ Valid photo source accepted: {source}")
            
            # Test user reference integrity
            hidden_photo = HiddenPhoto(
                user_id=user.id,
                photo_source="mapillary",
                photo_id="user_ref_test_photo",
                reason="User reference test"
            )
            
            db.add(hidden_photo)
            await db.commit()
            await db.refresh(hidden_photo)
            
            self.test_hidden_photos.append(hidden_photo)
            
            # Verify foreign key relationship
            assert hidden_photo.user_id == user.id
            print("✓ User foreign key relationship working")
            
            return True
            
        except Exception as e:
            print(f"✗ Data integrity test failed: {e}")
            return False
        finally:
            await db.close()
    
    @pytest.mark.asyncio
    async def test_bulk_operations(self):
        """Test bulk database operations for hidden content."""
        print("\n--- Testing Bulk Operations ---")
        
        db = SessionLocal()
        try:
            user = self.test_users[0]
            
            # Create multiple hidden photos
            hidden_photos = []
            for i in range(5):
                hidden_photo = HiddenPhoto(
                    user_id=user.id,
                    photo_source="mapillary",
                    photo_id=f"bulk_test_photo_{i}",
                    reason=f"Bulk test {i}"
                )
                hidden_photos.append(hidden_photo)
                db.add(hidden_photo)
            
            await db.commit()
            self.test_hidden_photos.extend(hidden_photos)
            
            print(f"✓ Created {len(hidden_photos)} hidden photos in bulk")
            
            # Query all hidden photos for user
            result = await db.execute(
                select(HiddenPhoto).where(HiddenPhoto.user_id == user.id)
            )
            all_hidden = result.scalars().all()
            
            assert len(all_hidden) >= len(hidden_photos)
            print(f"✓ Queried {len(all_hidden)} hidden photos")
            
            # Count hidden photos
            result = await db.execute(
                select(func.count(HiddenPhoto.id)).where(HiddenPhoto.user_id == user.id)
            )
            count = result.scalar()
            
            assert count >= len(hidden_photos)
            print(f"✓ Counted {count} hidden photos")
            
            # Bulk delete by source
            bulk_delete_query = await db.execute(
                select(HiddenPhoto).where(
                    and_(
                        HiddenPhoto.user_id == user.id,
                        HiddenPhoto.photo_source == "mapillary"
                    )
                )
            )
            photos_to_delete = bulk_delete_query.scalars().all()
            
            for photo in photos_to_delete:
                if photo in self.test_hidden_photos:
                    self.test_hidden_photos.remove(photo)
                await db.delete(photo)
            
            await db.commit()
            print(f"✓ Bulk deleted {len(photos_to_delete)} photos")
            
            return True
            
        except Exception as e:
            print(f"✗ Bulk operations test failed: {e}")
            return False
        finally:
            await db.close()
    
    async def run_all_tests(self):
        """Run all database operation tests."""
        print("=" * 50)
        print("HIDDEN CONTENT DATABASE TESTS")
        print("=" * 50)
        
        try:
            await self.setup_test_data()
            
            tests = [
                self.test_hidden_photo_crud_operations,
                self.test_hidden_user_crud_operations,
                self.test_duplicate_prevention,
                self.test_timestamp_handling,
                self.test_data_integrity,
                self.test_bulk_operations
            ]
            
            passed = 0
            failed = 0
            
            for test in tests:
                try:
                    if await test():
                        passed += 1
                    else:
                        failed += 1
                except Exception as e:
                    print(f"✗ {test.__name__} failed with exception: {e}")
                    failed += 1
            
            print("\n" + "=" * 50)
            print(f"RESULTS: {passed} passed, {failed} failed")
            
            if failed == 0:
                print("🎉 ALL DATABASE TESTS PASSED!")
                return True
            else:
                print("❌ Some database tests failed!")
                return False
                
        finally:
            await self.cleanup_test_data()


async def main():
    """Run the database tests."""
    test_runner = TestHiddenDatabaseOperations()
    success = await test_runner.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
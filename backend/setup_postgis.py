#!/usr/bin/env python3
"""
Setup script to enable PostGIS extension and create spatial indexes
"""
import asyncio
import os
import sys
from sqlalchemy import text
from dotenv import load_dotenv

# Add the api directory to the path to import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

from app.database import engine, Base
from app.models import User, Photo, CachedRegion, MapillaryPhotoCache

load_dotenv()

async def setup_postgis():
    """Setup PostGIS extension and create tables with spatial indexes"""
    
    async with engine.begin() as conn:
        print("Enabling PostGIS extension...")
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            print("✓ PostGIS extension enabled")
        except Exception as e:
            print(f"Warning: Could not enable PostGIS extension: {e}")
            print("Make sure PostGIS is installed and you have appropriate privileges")
        
        print("Creating database tables...")
        await conn.run_sync(Base.metadata.create_all)
        print("✓ Database tables created")
        
        print("Creating spatial indexes...")
        
        # Create spatial index on cached_regions.bbox
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cached_regions_bbox 
                ON cached_regions USING GIST (bbox);
            """))
            print("✓ Spatial index created on cached_regions.bbox")
        except Exception as e:
            print(f"Warning: Could not create spatial index on cached_regions.bbox: {e}")
        
        # Create spatial index on mapillary_photo_cache.geometry
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_mapillary_photo_cache_geometry 
                ON mapillary_photo_cache USING GIST (geometry);
            """))
            print("✓ Spatial index created on mapillary_photo_cache.geometry")
        except Exception as e:
            print(f"Warning: Could not create spatial index on mapillary_photo_cache.geometry: {e}")
        
        # Create regular indexes for performance
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cached_regions_is_complete 
                ON cached_regions (is_complete);
            """))
            print("✓ Index created on cached_regions.is_complete")
        except Exception as e:
            print(f"Warning: Could not create index on cached_regions.is_complete: {e}")
        
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_mapillary_photo_cache_region_id 
                ON mapillary_photo_cache (region_id);
            """))
            print("✓ Index created on mapillary_photo_cache.region_id")
        except Exception as e:
            print(f"Warning: Could not create index on mapillary_photo_cache.region_id: {e}")
        
        # Create index on cached_at for cache expiration queries
        try:
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_mapillary_photo_cache_cached_at 
                ON mapillary_photo_cache (cached_at);
            """))
            print("✓ Index created on mapillary_photo_cache.cached_at")
        except Exception as e:
            print(f"Warning: Could not create index on mapillary_photo_cache.cached_at: {e}")
        
        print("\n✅ PostGIS setup completed successfully!")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Start the server: uvicorn app.api:app --reload")
        print("3. Check cache stats: GET /api/mapillary/stats")

async def main():
    try:
        await setup_postgis()
    except Exception as e:
        print(f"❌ Error during setup: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
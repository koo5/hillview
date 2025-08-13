# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start FastAPI server with auto-reload
uvicorn app.api:app --reload

# Run with Docker Compose
docker-compose up

# Run tests
python test_api.py
```

### Database Operations
```bash
# Initialize database tables
python -c "from app.database import Base, engine; import asyncio; from app.models import User, Photo; asyncio.run(async def create_tables(): async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all); print('Tables created successfully'))(); create_tables()"

# Database setup script
./init_db.sh
```

### Dependencies
```bash
# Install Python dependencies (fix NumPy compatibility issues)
pip install -r requirements.txt

# App-specific dependencies
pip install -r api/app/requirements.txt

# Create database (run as postgres user)
sudo -u postgres psql -f create_database.sql

# OR manually create database
sudo -u postgres createdb hillview
sudo -u postgres psql -d hillview -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# Setup PostGIS extension and spatial indexes
python setup_postgis.py
```

## Architecture Overview

### Tech Stack
- **Backend**: FastAPI with async/await support
- **Database**: PostgreSQL with SQLAlchemy ORM (async)
- **Authentication**: JWT tokens with OAuth2 (Google, GitHub)
- **File Storage**: Local filesystem with upload/thumbnail management
- **External APIs**: Mapillary API for map data

### Project Structure
```
backend/
├── api/app/           # Core FastAPI application
│   ├── api.py         # Main API routes and endpoints
│   ├── auth.py        # Authentication logic, JWT, OAuth
│   ├── database.py    # Database configuration and session management
│   ├── models.py      # SQLAlchemy models (User, Photo)
│   └── requirements.txt
├── test_api.py        # API test suite
├── docker-compose.yml # Docker configuration
└── README.md         # Setup and configuration docs
```

### Key Components

#### Authentication System (auth.py)
- JWT-based authentication with configurable expiration
- OAuth2 integration for Google and GitHub
- Password hashing with bcrypt
- User registration and login endpoints

#### Database Models (models.py)
- **User**: Stores user accounts with OAuth support, auto-upload settings
- **Photo**: Stores photo metadata including GPS coordinates, compass angles, file paths

#### API Endpoints (api.py)
- `/api/auth/*` - Authentication endpoints (register, login, OAuth)
- `/api/photos/*` - Photo management (upload, delete, thumbnails)
- `/api/mapillary` - Mapillary API with intelligent caching and streaming support

### Configuration
Environment variables required:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - JWT signing key
- `MAPILLARY_CLIENT_TOKEN_FILE` - Path to Mapillary API token
- OAuth credentials for Google/GitHub (`*_CLIENT_ID`, `*_CLIENT_SECRET`)

Optional configuration:
- `ENABLE_MAPILLARY_CACHE` - Set to "true", "1", or "yes" to enable caching (disabled by default)

### Key Features
- **Intelligent Caching**: PostGIS-powered spatial caching of Mapillary photos
- **Rate Limiting**: Client-based rate limiting for Mapillary API calls
- **Photo Processing**: EXIF data extraction and thumbnail generation
- **Background Tasks**: Async photo processing after upload
- **CORS**: Configured for frontend integration
- **Error Handling**: Global exception handler with logging

### Database Schema
- Users have UUIDs as primary keys
- Photos linked to users via foreign key relationships
- Support for OAuth provider linking to existing accounts
- Automatic timestamp tracking for creation/updates

#### Mapillary Caching Schema
- **CachedRegion**: Stores bounding box polygons of cached areas with completion status
- **MapillaryPhotoCache**: Stores individual Mapillary photos with PostGIS Point geometry
- Spatial indexes (GIST) on geometry columns for efficient spatial queries
- Pagination cursor tracking for incremental cache population

### Mapillary Caching System
- **Immediate Response**: Returns cached photos instantly from PostGIS spatial queries
- **Smart Region Detection**: Uses PostGIS to calculate uncached areas within requested bbox
- **Background Population**: Asynchronously fetches and caches missing data using Mapillary pagination
- **Spatial Optimization**: Leverages PostGIS `ST_Within`, `ST_Intersects` for efficient geometry operations
- **Rate Limiting**: Maintains existing rate limiting while reducing API calls through caching

### Development Notes
- All database operations are async using SQLAlchemy AsyncSession
- Uses dependency injection pattern for database sessions
- PostGIS extension required for spatial functionality
- Comprehensive logging throughout the application
- File uploads stored in configurable upload directory with thumbnails
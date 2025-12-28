# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application
```bash
# Start FastAPI server with auto-reload (from api/app/ directory)
cd api/app && uvicorn api:app --reload

# Run with Docker Compose (preferred method)
docker compose up --build --remove-orphans -d api

# Run tests (use the test script for proper environment setup)
./tests/run_tests.sh

# Run specific integration tests
./tests/run_integration_tests.sh integration/test_content_filtering.py -v

# Run specific test methods
./tests/run_integration_tests.sh integration/test_user_profile.py::TestAccountDeletion::test_delete_account_cascades_photos -v -s

# Run unit tests
./api/app/run_unit_tests.sh tests/unit/test_photo_ratings.py -v
```

### Debug Utilities

```bash
# Use debug script for troubleshooting (from backend directory)
./debug.sh recreate    # Recreate test users and get passwords
./debug.sh photos      # Show user's photos with error details
./debug.sh photo <id>  # Show detailed info about specific photo
./debug.sh cleanup     # Delete all user's photos for cleanup
```

#### Getting Authentication for Manual Testing

The `./debug.sh recreate` command creates test users and displays their credentials:
- Username: `test`, Password: `StrongTestPassword123!`
- Username: `admin`, Password: `StrongAdminPassword123!`
- Username: `testuser`, Password: `StrongTestUserPassword123!`

Use these credentials with tools like curl or Postman for manual API testing.

#### Centralized Debug Infrastructure

The debug script uses centralized test utilities:
- **`debug.sh`** - Wrapper script that sets up environment and runs debug utilities
- **`tests/utils/api_client.py`** - Centralized API client eliminating code duplication
- **`tests/utils/debug_utils.py`** - Debug functions for troubleshooting photo processing
- **`api/app/debug_utils.py`** - Debug endpoint decorators and system cleanup utilities

### Database Operations
```bash
# Initialize database tables
python -c "from app.database import Base, engine; import asyncio; from app.models import User, Photo; asyncio.run(async def create_tables(): async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all); print('Tables created successfully'))(); create_tables()"

# Database setup script
./init_db.sh
```

### Database Migrations

**📖 See [Database Migrations Guide](../docs/database-migrations.md) for complete documentation.**

Quick reference using the migration script:
```bash
# Check migration status
./scripts/migrate.sh current

# Apply all pending migrations  
./scripts/migrate.sh upgrade head

# Create new migration after model changes
./scripts/migrate.sh revision --autogenerate -m "Description of changes"

# View migration history
./scripts/migrate.sh history
```

The migration script (`./scripts/migrate.sh`) automatically handles:
- Environment variable loading from `.env`
- Docker container networking and volume mounting
- Python path configuration
- Async/sync engine compatibility

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
│   ├── api.py         # Main FastAPI app and route registration
│   ├── auth.py        # Authentication logic, JWT, OAuth
│   ├── photo_routes.py # Photo upload/management endpoints
│   ├── user_routes.py  # User management endpoints
│   └── requirements.txt
├── common/            # Shared modules
│   ├── models.py      # SQLAlchemy models (User, Photo, etc.)
│   ├── database.py    # Database configuration and session management
│   └── config.py      # Configuration management
├── worker/            # Photo processing worker service
│   ├── photo_processor.py  # EXIF extraction, image processing
│   └── Dockerfile
├── tests/             # Test suite
│   ├── integration/   # Integration tests
│   └── utils/         # Test utilities and helpers
├── scripts/           # Utility scripts
│   └── migrate.sh     # Database migration runner
├── docker-compose.yml # Docker configuration
└── run_tests.sh       # Main test runner script
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

### Import Conventions
- Modules in `api/app/` use relative imports for sibling modules: `from dsl_utils import y`
- Shared modules use `common.` prefix: `from common.models import Photo`

## API Backend Control & Management

### Backend Development Server
```bash
# Start backend (required before Android app testing)
docker compose up --build --remove-orphans -d api

# Check backend health
curl http://localhost:8055/api/debug

# From Android emulator perspective 
curl http://10.0.2.2:8055/api/debug
```

### Authentication System Control

#### Test Users (for development)
- **Username**: `test`, **Password**: `StrongTestPassword123!`
- **Username**: `admin`, **Password**: `StrongAdminPassword123!`
- **Username**: `testuser`, **Password**: `StrongTestUserPassword123!`
- **Rate Limiting**: Active protection against brute force attempts
- **Token Expiration**: 30-minute JWT token validity

#### OAuth Configuration
- **Providers**: Google and GitHub OAuth2
- **Callback URLs**: Must include both web and mobile redirect URIs
- **Deep Links**: Mobile OAuth returns via `cz.hillview://auth`
- **Security**: Device registration required for private IP OAuth testing

#### API Endpoints for Testing
```bash
# Test username/password authentication
curl -X POST http://localhost:8055/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test&password=test123"

# Test protected endpoint with token
curl -H "Authorization: Bearer <jwt_token>" \
  http://localhost:8055/api/photos

# OAuth endpoints
GET /api/auth/oauth-redirect?provider=google
GET /api/auth/oauth-callback?code=...&state=...
```

### Database Management
```bash
# Database connection (from Docker)
docker exec -it hillview-db psql -U postgres -d hillview

# Check authentication tables
SELECT id, username, is_active FROM users;
SELECT provider, provider_user_id FROM users WHERE provider IS NOT NULL;
```

## Testing Strategy & Coverage

### Comprehensive Test Suite
1. **Backend Tests** (`backend/tests/`)
   - OAuth flow testing (`test_auth_oauth.py`)
   - Username/password authentication (`test_auth_login.py`)
   - Token validation and security
   - Rate limiting and SQL injection protection

2. **Frontend Tests** (`frontend/src/tests/`)
   - Authentication logic (`auth.test.ts`)
   - Token expiration handling
   - OAuth provider integration

3. **Android Integration Tests** (`frontend/test/specs/`)
   - App state validation (`android-auth-workflow.test.ts`)
   - Browser-based OAuth simulation
   - Deep link structure verification
   - Authentication persistence testing

### Running Full Test Suite
```bash
# Backend API tests
cd backend && python -m pytest tests/ -v

# Frontend unit tests  
cd frontend && bun test

# Android integration tests
cd frontend && bun run test:android

# Manual backend verification
cd backend/tests && python test_auth_login.py
```

### Security Testing Notes
- **Rate Limiting**: Automatically tested for login endpoints
- **SQL Injection**: Protection verified with malicious input testing
- **Token Security**: JWT validation and expiration testing
- **CORS**: Configured for development (localhost:8055, localhost:8212)

## Troubleshooting Common Issues

### Android App Issues
- **"error sending request"**: Check backend is running, verify `VITE_BACKEND_ANDROID` is set
- **App not launching**: Verify correct package ID (`cz.hillviedev` for dev)
- **Deep links not working**: Expected in test environment, check Android intent configuration

### Backend Issues
- **OAuth callback errors**: Missing `request: Request` parameter in FastAPI endpoints
- **CORS errors**: Add frontend URLs to allowed origins
- **Database connection**: Ensure PostgreSQL is running and accessible

### Testing Issues
- **Test timeouts**: Android tests need longer timeouts (60s+) for app startup
- **Package mismatch**: Ensure all test files use consistent package identifier
- **Environment variables**: `VITE_BACKEND_ANDROID` must be set for emulator networking

# Hillview Project - Overview

## Project Structure

This is a full-stack photo mapping application with Android support:

```
/hillview/
├── frontend/          # Svelte + Tauri Android app
│   ├── docs/         # Test documentation and guides
│   ├── test/         # Android test infrastructure
│   └── scripts/      # Build and development scripts
├── backend/          # FastAPI + PostgreSQL backend
│   ├── api/app/      # Core API application
│   ├── tests/        # Backend test suite
│   └── uploads/      # Photo storage directory
└── docs/             # Project-level documentation
```

## Quick Start Commands

### Frontend Development (from `/frontend/`)
```bash
# Start frontend dev server
bun run dev

# Android testing
bun run test:android --spec android-photo-simple.test0.ts

# Start Android development mode
./frontend/scripts/android/dev.sh

# Build Android APK (for actual builds)
./frontend/scripts/android/debug-build.sh
```

### Backend Development (from `/backend/`)
```bash
# Start backend services
docker compose up --build --remove-orphans -d api

# Run backend tests
python -m pytest tests/ -v

# Database migrations (see docs/database-migrations.md for complete guide)
./scripts/migrate.sh upgrade head
```

### Dependencies (from repo root)
```bash
# Audit every lockfile; refresh with the 14-day cooloff (see the script's docstring)
scripts/deps.py audit
scripts/deps.py backend pillow==12.3.0     # or --all; cargo / frontend subcommands likewise
```

## Architecture Overview

### Frontend (`/frontend/`)
- **Framework**: SvelteKit + Tauri v2 
- **Platform**: Web + Android hybrid app
- **Testing**: WebDriverIO + Appium for Android automation
- **Build**: Bun for package management and builds

### Backend (`/backend/`)  
- **API**: FastAPI with async/await
- **Database**: PostgreSQL + PostGIS for spatial data
- **Authentication**: JWT + OAuth2 (Google, GitHub)
- **External APIs**: Mapillary integration with caching

### Key Features
- **Photo Upload & Management**: EXIF processing, thumbnails, geotagging
- **Map Integration**: Interactive map with photo markers
- **Android App**: Native-like experience via Tauri WebView
- **Authentication**: Multiple OAuth providers + username/password
- **Spatial Caching**: PostGIS-powered Mapillary photo caching

## Development Workflow

### Setting Up Development Environment
1. **Backend First**: Start in repo root directory
   - Run `docker compose up --build --remove-orphans -d api`
   - Verify at `http://localhost:8055/api/debug`

2. **Frontend Second**: Start in `/frontend/` directory  
   - Run `bun run dev` for web development
   - Run `./scripts/android/dev.sh` for Android development

3. **Testing**: Both directories have their own test suites
   - Frontend: Android integration tests, Playwright web tests
   - Backend: pytest API tests, authentication tests

### Working with Android
- **Package ID**: `cz.hillviedev` (development)
- **Package ID**: `cz.hillview` (production)
- **Emulator**: Uses `10.0.2.2:8055` to reach localhost backend
- **Testing**: WebDriverIO + Appium for automated UI testing
- **Logs**: Use `./scripts/android/logs.sh` for debugging

## Directory-Specific Instructions

Each subdirectory has its own `CLAUDE.md` with detailed instructions:

- **`/frontend2/CLAUDE.md`**: the KMP/Compose rewrite — start with its "one state" rule
- **`/frontend/CLAUDE.md`**: Android testing, UI development, build processes
- **`/backend/CLAUDE.md`**: API development, database operations, deployment

## Documentation Guides

- **[One State](docs/one-state.md)**: the app's load-bearing architectural rule — one user-facing location/orientation state, written and read by everything, with no direct hardware side-channels. Read before touching position or heading.
- **[Database Migrations Guide](docs/database-migrations.md)**: Complete workflow for managing database schema changes with Alembic
- **[PostgreSQL Alpine Migration](docs/postgres-alpine-migration.md)**: why the postgres image moved to the alpine tag + ICU collation, the dump/restore procedure, and `backend/scripts/pg_rehearse_alpine.py` to prove it on a throwaway cluster first
- **[Terrain Data Licensing](docs/terrain-data-licensing.md)**: DEM/OSM licence obligations for terrain renders (required notices, pre-launch checklist)
- **[Native Android Auth](docs/native-auth.md)**: Credential Manager + Google ID-token login — concepts, security reasoning, and where everything lives
- **[Zoom view print view](docs/zoomview-print.md)**: ⋮ → Print view + Ctrl+P — share-link QR in the middle, why the viewer freezes instead of re-rendering at print time, the replaced-element canvas gotcha
- **[Panoramax Federation](docs/panoramax-federation.md)**: The `backend/panoramax/` read API + sequencer serving CC photos to the Panoramax federation (harvester contract, deployment, registration)

## Common Issues & Solutions

### Backend Not Reachable
- Ensure backend is running: `docker compose up -d api`
- Check Android emulator uses `10.0.2.2:8055` not `localhost:8055`

### Android Test Failures  
- "error sending request" = backend connectivity issue
- Multiple app restarts = check retry configurations in `wdio.conf.ts`

### Authentication Issues
- OAuth setup requires proper redirect URIs for both web and mobile
- Test credentials: `test/StrongTestPassword123!` for development (see backend/CLAUDE.md for full list)

## Coding Guidelines

- **Never delete commented-out code** - preserve it in edits, the user keeps it for reference
- Always use well-scoped data-testid attributes, following the project's style

## Project Goals

Hillview is a photo mapping application that allows users to:
1. Upload photos with automatic geolocation extraction
2. View photos on an interactive map
3. Integrate with external mapping services (Mapillary)
4. Use both web and Android native-like interfaces
5. Handle authentication across multiple platforms

The project emphasizes spatial data handling, real-time photo processing, and cross-platform compatibility.
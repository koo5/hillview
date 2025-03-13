# Hillview Backend

This is the backend service for the Hillview application, providing API endpoints for authentication, photo management, and map data.

## Features

- User authentication with username/password
- OAuth2 authentication with Google and GitHub
- Photo upload and management
- Photo metadata extraction (GPS coordinates, compass angle, etc.)
- Integration with Mapillary API

## Setup

### Prerequisites

- Python 3.8+
- PostgreSQL database
- Mapillary API token

### Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

### Configuration

The application uses environment variables for configuration. Create a `.env` file in the backend directory with the following variables:

```
# Database configuration
DATABASE_URL=postgresql+asyncpg://username:password@localhost/hillview

# JWT Authentication
SECRET_KEY=your-secret-key-change-this-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=30

# OAuth2 Configuration
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5000/oauth/callback

GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
GITHUB_REDIRECT_URI=http://localhost:5000/oauth/callback

# Upload directory
UPLOAD_DIR=./uploads

# Mapillary
MAPILLARY_CLIENT_TOKEN_FILE=~/.mapillary_token
```

### Database Setup

1. Create a PostgreSQL user and database:
   ```
   # Create a new PostgreSQL user
   sudo -u postgres createuser --interactive --pwprompt
   # Enter name of role to add: hillview
   # Enter password for new role: your_password
   # Enter it again: your_password
   # Shall the new role be a superuser? (y/n) n
   # Shall the new role be allowed to create databases? (y/n) y
   # Shall the new role be allowed to create more new roles? (y/n) n
   
   # Create a new database owned by the new user
   sudo -u postgres createdb --owner=hillview hillview
   ```

   Alternatively, you can use psql:
   ```
   sudo -u postgres psql
   postgres=# CREATE USER hillview WITH PASSWORD 'your_password';
   postgres=# CREATE DATABASE hillview OWNER hillview;
   postgres=# \q
   ```

2. Configure the database connection in the `.env` file:
   ```
   DATABASE_URL=postgresql+asyncpg://hillview:your_password@localhost/hillview
   ```
   
   Replace `your_password` with the password you set for the hillview user.

3. Create the database tables:
   ```
   python -c "from app.database import Base, engine; import asyncio; from app.models import User, Photo; asyncio.run(async def create_tables(): async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all); print('Tables created successfully'))(); create_tables()"
   ```

### Running the Application

Start the FastAPI server:

```
uvicorn app.api:app --reload
```

The API will be available at http://localhost:8000.

## API Documentation

Once the server is running, you can access the API documentation at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Development

### Database Migrations

For database migrations, you can use Alembic:

1. Install Alembic:
   ```
   pip install alembic
   ```

2. Initialize Alembic:
   ```
   alembic init migrations
   ```

3. Configure Alembic to use your database (edit `alembic.ini` and `migrations/env.py`)

4. Create a migration:
   ```
   alembic revision --autogenerate -m "Initial migration"
   ```

5. Apply migrations:
   ```
   alembic upgrade head
   ```

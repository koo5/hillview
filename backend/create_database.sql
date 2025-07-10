-- Database setup script for Hillview
-- Run this as PostgreSQL superuser (usually 'postgres')

-- Create database
CREATE DATABASE hillview;

-- Create user (optional - you can use existing postgres user)
-- CREATE USER hillview WITH PASSWORD 'your_password_here';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE hillview TO postgres;

-- Connect to the database to enable PostGIS
\c hillview

-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Show success
SELECT 'Database setup complete!' AS result;
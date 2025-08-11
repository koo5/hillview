-- Migration to add security-related tables

-- Create token blacklist table
CREATE TABLE IF NOT EXISTS token_blacklist (
    id VARCHAR PRIMARY KEY,
    token VARCHAR UNIQUE NOT NULL,
    user_id VARCHAR NOT NULL REFERENCES users(id),
    blacklisted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reason VARCHAR,
    
    -- Indexes for performance
    CONSTRAINT idx_token_blacklist_token UNIQUE (token)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_token_blacklist_user_id ON token_blacklist(user_id);
CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires_at ON token_blacklist(expires_at);

-- Add is_active column to users table if it doesn't exist
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;

-- Create index on is_active for faster queries
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active) WHERE is_active = FALSE;
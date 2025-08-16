from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2AuthorizationCodeBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import os
import secrets
import logging
from dotenv import load_dotenv

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'common'))
from common.database import get_db
from common.models import User, TokenBlacklist

load_dotenv()

logger = logging.getLogger(__name__)

# Security configuration
# Generate a secure random key if not provided
DEFAULT_SECRET_KEY = secrets.token_urlsafe(32)
SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)

# Warn if using default key (should only happen in development)
if SECRET_KEY == DEFAULT_SECRET_KEY:
    logger.warning("Using auto-generated JWT secret key. Set SECRET_KEY environment variable in production!")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Test users configuration
TEST_USERS = os.getenv("TEST_USERS", "false").lower() in ("true", "1", "yes")

# OAuth2 configuration
OAUTH_PROVIDERS = {
    "google": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", ""),
        "auth_url": "https://accounts.google.com/o/oauth2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
    },
    "github": {
        "client_id": os.getenv("GITHUB_CLIENT_ID", ""),
        "client_secret": os.getenv("GITHUB_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("GITHUB_REDIRECT_URI", ""),
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
    }
}

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

# Models
class Token(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserOAuth(BaseModel):
    provider: str
    code: str
    redirect_uri: Optional[str] = None

class UserOut(BaseModel):
    id: str
    email: str
    username: str
    is_active: bool
    is_test: bool
    created_at: datetime
    auto_upload_enabled: bool
    auto_upload_folder: Optional[str] = None

    class Config:
        from_attributes = True

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add issued at time for better token tracking
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire

async def get_user_by_username(db: AsyncSession, username: str):
    result = await db.execute(select(User).where(User.username == username))
    return result.scalars().first()

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalars().first()

async def get_user_by_oauth(db: AsyncSession, provider: str, oauth_id: str):
    result = await db.execute(
        select(User).where(User.oauth_provider == provider, User.oauth_id == oauth_id)
    )
    return result.scalars().first()

async def authenticate_user(db: AsyncSession, username: str, password: str):
    logger.debug(f"Authenticating user: {username}")
    user = await get_user_by_username(db, username)
    if not user:
        logger.debug(f"User not found by username, trying email: {username}")
        user = await get_user_by_email(db, username)  # Try with email
    
    if not user:
        logger.warning(f"Authentication failed: User not found: {username}")
        return False
    
    # Check if user is active BEFORE password verification
    if not user.is_active:
        logger.warning(f"Authentication failed: User is disabled: {username}")
        return False
    
    logger.debug(f"Verifying password for user {username}")
    logger.debug(f"Stored hash: {user.hashed_password[:50]}...")
    logger.debug(f"Password to verify: {password}")
    password_valid = verify_password(password, user.hashed_password)
    logger.debug(f"Password verification result: {password_valid}")
    if not password_valid:
        logger.warning(f"Authentication failed: Invalid password for user: {username}")
        return False
    
    logger.info(f"Authentication successful for user: {username}, id: {user.id}")
    return user

async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    inactive_user_exception = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User account is disabled",
    )
    
    try:
        # Decode and validate JWT token with strict algorithm checking
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": True})
        
        # Validate token type
        token_type = payload.get("type")
        if token_type != "access":
            logger.warning(f"Invalid token type: {token_type}")
            raise credentials_exception
        
        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        
        if username is None or user_id is None:
            logger.warning("Token missing username or user_id")
            raise credentials_exception
            
        # Check if token is blacklisted (implementation pending)
        if await is_token_blacklisted(token, db):
            logger.warning(f"Blacklisted token used by user: {user_id}")
            raise credentials_exception
            
        token_data = TokenData(username=username, user_id=user_id)
    except JWTError as e:
        logger.warning(f"JWT Error: {str(e)}")
        raise credentials_exception
    
    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if user is None:
        logger.warning(f"User not found with ID: {user_id}")
        raise credentials_exception
    
    # Check if user is active IMMEDIATELY after fetching
    if not user.is_active:
        logger.warning(f"Disabled user attempted access: {user_id}")
        raise inactive_user_exception
        
    logger.debug(f"User authenticated successfully: {user.username}, id: {user.id}")
    return user

# Check if token is blacklisted
async def is_token_blacklisted(token: str, db: AsyncSession) -> bool:
    """Check if a token has been blacklisted."""
    result = await db.execute(
        select(TokenBlacklist).where(
            TokenBlacklist.token == token,
            TokenBlacklist.expires_at > datetime.utcnow()
        )
    )
    return result.scalars().first() is not None

async def blacklist_token(token: str, user_id: str, reason: str, db: AsyncSession) -> None:
    """Add a token to the blacklist."""
    try:
        # Decode token to get expiration time
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        exp_timestamp = payload.get("exp")
        if exp_timestamp:
            expires_at = datetime.fromtimestamp(exp_timestamp)
        else:
            # Default to 30 days if no expiration
            expires_at = datetime.utcnow() + timedelta(days=30)
        
        blacklist_entry = TokenBlacklist(
            token=token,
            user_id=user_id,
            expires_at=expires_at,
            reason=reason
        )
        db.add(blacklist_entry)
        await db.commit()
        logger.info(f"Token blacklisted for user {user_id}, reason: {reason}")
    except Exception as e:
        logger.error(f"Error blacklisting token: {str(e)}")
        await db.rollback()
        raise

async def blacklist_all_user_tokens(user_id: str, reason: str, db: AsyncSession) -> None:
    """Blacklist all tokens for a specific user when they're disabled."""
    # This is a placeholder - in production, you'd need to track all active tokens
    # For now, we'll rely on the is_active check in get_current_user
    logger.info(f"All tokens invalidated for user {user_id}, reason: {reason}")

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_user_optional(
    token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)), 
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None"""
    if not token:
        return None
    
    try:
        # Decode and validate JWT token with strict algorithm checking
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        
        # Check if token is blacklisted
        blacklist_query = select(TokenBlacklist).where(TokenBlacklist.token == token)
        blacklist_result = await db.execute(blacklist_query)
        blacklisted_token = blacklist_result.scalars().first()
        
        if blacklisted_token:
            logger.warning(f"Blacklisted token used for user: {username}")
            return None
            
    except JWTError:
        return None
    
    # Get user from database
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    
    if user is None or not user.is_active:
        return None
        
    return user

async def get_current_user_optional_with_query(
    request: Request,
    token: Optional[str] = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)), 
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, checking both header and query params"""
    # First try header token
    if token:
        try:
            # Decode and validate JWT token with strict algorithm checking
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                return None
            
            # Check if token is blacklisted
            blacklist_query = select(TokenBlacklist).where(TokenBlacklist.token == token)
            blacklist_result = await db.execute(blacklist_query)
            blacklisted_token = blacklist_result.scalars().first()
            
            if blacklisted_token:
                logger.warning(f"Blacklisted token used for user: {username}")
                return None
                
            # Get user from database
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalars().first()
            
            if user is None or not user.is_active:
                return None
                
            return user
        except JWTError:
            pass
    
    # If no header token or it failed, try query parameter
    if request:
        query_token = request.query_params.get('token')
        if query_token:
            try:
                # Reuse the logic from get_current_user_optional
                payload = jwt.decode(query_token, SECRET_KEY, algorithms=[ALGORITHM])
                username: str = payload.get("sub")
                if username is None:
                    return None
                
                # Check if token is blacklisted
                blacklist_query = select(TokenBlacklist).where(TokenBlacklist.token == query_token)
                blacklist_result = await db.execute(blacklist_query)
                blacklisted_token = blacklist_result.scalars().first()
                
                if blacklisted_token:
                    logger.warning(f"Blacklisted token used for user: {username}")
                    return None
                    
                # Get user from database
                result = await db.execute(select(User).where(User.username == username))
                user = result.scalars().first()
                
                if user is None or not user.is_active:
                    return None
                    
                return user
            except JWTError:
                pass
    
    return None

def require_role(required_role: str):
    """Dependency factory for role-based access control."""
    async def role_checker(current_user: User = Depends(get_current_active_user)):
        from common.models import UserRole
        
        # Convert string to enum if needed
        if isinstance(required_role, str):
            try:
                required_role_enum = UserRole(required_role)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid role: {required_role}")
        else:
            required_role_enum = required_role
        
        # Check if user has the required role
        if current_user.role != required_role_enum:
            # Allow admin to access all endpoints
            if current_user.role != UserRole.ADMIN:
                raise HTTPException(
                    status_code=403, 
                    detail=f"Access denied. Required role: {required_role_enum.value}, your role: {current_user.role.value}"
                )
        
        return current_user
    
    return role_checker

# Convenience functions for common roles
def require_admin():
    """Require admin role."""
    from common.models import UserRole
    return require_role(UserRole.ADMIN)

def require_moderator():
    """Require moderator role (admins also have access)."""
    async def moderator_checker(current_user: User = Depends(get_current_active_user)):
        from common.models import UserRole
        
        if current_user.role not in [UserRole.ADMIN, UserRole.MODERATOR]:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: moderator or admin, your role: {current_user.role.value}"
            )
        
        return current_user
    
    return moderator_checker

async def delete_users_by_usernames(db: AsyncSession, usernames: list[str]) -> dict:
    """Delete users by usernames, including their owned photos. Returns summary of deletions."""
    from sqlalchemy import delete, select
    from common.models import Photo
    
    summary = {
        "photos_deleted": 0,
        "users_deleted": 0
    }
    
    try:
        # First, get user IDs for the specified usernames
        user_ids_query = select(User.id).where(User.username.in_(usernames))
        user_ids_result = await db.execute(user_ids_query)
        user_ids = [row[0] for row in user_ids_result.fetchall()]
        
        if user_ids:
            # Delete photos owned by these users
            photo_delete_stmt = delete(Photo).where(Photo.owner_id.in_(user_ids))
            photo_result = await db.execute(photo_delete_stmt)
            summary["photos_deleted"] = photo_result.rowcount
            if photo_result.rowcount > 0:
                logger.info(f"Deleted {photo_result.rowcount} photos owned by users: {usernames}")
        
        # Delete the users
        user_delete_stmt = delete(User).where(User.username.in_(usernames))
        user_result = await db.execute(user_delete_stmt)
        summary["users_deleted"] = user_result.rowcount
        if user_result.rowcount > 0:
            logger.info(f"Deleted {user_result.rowcount} users: {usernames}")
        
        await db.commit()
        return summary
        
    except Exception as e:
        logger.error(f"Error deleting users {usernames}: {str(e)}")
        await db.rollback()
        raise


async def recreate_test_users(db: AsyncSession) -> dict:
    """Recreate test users with fresh passwords. Returns summary of actions taken."""
    from common.models import UserRole
    
    # Hardcoded test users with roles
    test_user_data = [
        ("test", "test123", UserRole.USER),
        ("admin", "admin123", UserRole.ADMIN)
    ]
    
    summary = {
        "photos_deleted": 0,
        "users_deleted": 0,
        "users_created": 0,
        "created_users": []
    }
    
    try:
        test_usernames = [username for username, _, _ in test_user_data]
        
        # Delete existing test users and their photos
        delete_summary = await delete_users_by_usernames(db, test_usernames)
        summary["photos_deleted"] = delete_summary["photos_deleted"]
        summary["users_deleted"] = delete_summary["users_deleted"]
        
        # Create fresh test users
        for username, password, role in test_user_data:
            hashed_password = get_password_hash(password)
            logger.info(f"Creating test user {username} with role {role.value} and password hash: {hashed_password[:50]}...")
            new_user = User(
                username=username,
                email=f"{username}@test.local",
                hashed_password=hashed_password,
                role=role,
                is_active=True,
                is_test=True
            )
            
            db.add(new_user)
            summary["created_users"].append(username)
            summary["users_created"] += 1
            
        await db.commit()
        logger.info(f"Created {len(test_user_data)} fresh test users")
        
        return summary
            
    except Exception as e:
        logger.error(f"Error recreating test users: {str(e)}")
        await db.rollback()
        raise

async def ensure_test_users() -> None:
    """Create test users if TEST_USERS is enabled. Delete and recreate if they exist."""
    if not TEST_USERS:
        return
    
    from common.database import SessionLocal
    
    async with SessionLocal() as db:
        summary = await recreate_test_users(db)
        logger.info(f"Test users recreation complete: {summary}")

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2AuthorizationCodeBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import os
from dotenv import load_dotenv

from .database import get_db
from .models import User

load_dotenv()

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-for-jwt")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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
    to_encode.update({"exp": expire})
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
    print(f"Authenticating user: {username}")
    user = await get_user_by_username(db, username)
    if not user:
        print(f"User not found by username, trying email: {username}")
        user = await get_user_by_email(db, username)  # Try with email
    
    if not user:
        print(f"Authentication failed: User not found: {username}")
        return False
    
    password_valid = verify_password(password, user.hashed_password)
    if not password_valid:
        print(f"Authentication failed: Invalid password for user: {username}")
        return False
    
    print(f"Authentication successful for user: {username}, id: {user.id}")
    return user

async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        print(f"Decoding JWT token: {token[:10]}...")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        print(f"Token payload - username: {username}, user_id: {user_id}")
        
        if username is None or user_id is None:
            print("Token missing username or user_id")
            raise credentials_exception
            
        token_data = TokenData(username=username, user_id=user_id)
    except JWTError as e:
        print(f"JWT Error: {str(e)}")
        raise credentials_exception
    
    print(f"Looking up user by ID: {user_id}")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    
    if user is None:
        print(f"User not found with ID: {user_id}")
        raise credentials_exception
        
    if not user.is_active:
        print(f"User is inactive: {user_id}")
        raise HTTPException(status_code=400, detail="Inactive user")
        
    print(f"User authenticated successfully: {user.username}, id: {user.id}")
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

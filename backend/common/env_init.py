"""
Early environment initialization - must be imported first by all modules.

This module loads environment variables once at startup before any other
module tries to access them. Import this at the top of your main modules.
"""

import os
import logging
from pathlib import Path

# Set up basic logging first
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def init_environment():
    """Initialize environment variables from .env file if not already done."""
    # Only initialize once
    if hasattr(init_environment, '_initialized'):
        return
    
    try:
        from dotenv import load_dotenv
        
        # Look for .env file in current working directory (should be /app/app inside container)
        env_file = Path.cwd() / ".env"
        
        if env_file.exists():
            logger.info(f"Loading environment variables from {env_file}")
            success = load_dotenv(env_file)
            
            if success:
                # Count loaded variables
                with open(env_file, 'r') as f:
                    lines = f.readlines()
                    var_count = sum(1 for line in lines if line.strip() and not line.strip().startswith('#') and '=' in line)
                
                logger.info(f"Successfully loaded {var_count} environment variables")
                
                # Log a few key variables (without values for security)
                key_vars = ['JWT_PRIVATE_KEY', 'RATE_LIMIT_PHOTO_UPLOAD', 'AUTH_MAX_ATTEMPTS']
                loaded_keys = [var for var in key_vars if os.getenv(var)]
                if loaded_keys:
                    logger.info(f"Key configuration variables loaded: {', '.join(loaded_keys)}")
                    
            else:
                logger.warning(f"Failed to load environment variables from {env_file}")
        else:
            logger.info(f"No .env file found at {env_file}, using system environment only")
            
    except Exception as e:
        logger.error(f"Error loading environment variables: {e}")
    
    # Mark as initialized
    init_environment._initialized = True

# Initialize environment immediately when this module is imported
init_environment()
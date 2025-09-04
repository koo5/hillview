"""
Centralized dotenv loader with proper error handling and logging.
"""

import os
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

def load_dotenv_with_logging(
    dotenv_path: Optional[str] = None,
    service_name: str = "Service"
) -> bool:
    """
    Load environment variables from .env file with proper error handling and logging.
    
    Args:
        dotenv_path: Path to .env file. If None, searches for .env in current directory
        service_name: Name of the service loading the env vars (for logging)
        
    Returns:
        bool: True if successfully loaded, False if failed
    """
    try:
        # Determine the .env file path
        if dotenv_path is None:
            env_file = Path.cwd() / ".env"
        else:
            env_file = Path(dotenv_path)
            
        # Check if file exists
        if not env_file.exists():
            logger.warning(f"{service_name}: No .env file found at {env_file}")
            return False
            
        # Check if file is readable
        if not env_file.is_file():
            logger.error(f"{service_name}: .env path exists but is not a file: {env_file}")
            return False
            
        # Count expected variables before loading
        expected_vars = []
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        var_name = line.split('=')[0].strip()
                        expected_vars.append(var_name)
        except Exception as e:
            logger.debug(f"{service_name}: Could not analyze .env file: {e}")
            
        # Attempt to load the .env file
        logger.info(f"{service_name}: Loading environment variables from {env_file}")
        success = load_dotenv(env_file)
        
        if success:
            logger.info(f"{service_name}: Python-dotenv reported success for {env_file}")
            
            # Check if all expected variables were actually loaded
            if expected_vars:
                loaded_vars = []
                missing_vars = []
                for var_name in expected_vars:
                    if os.getenv(var_name) is not None:
                        loaded_vars.append(var_name)
                    else:
                        missing_vars.append(var_name)
                
                logger.info(f"{service_name}: Loaded {len(loaded_vars)} of {len(expected_vars)} variables from .env")
                
                if missing_vars:
                    logger.warning(f"{service_name}: Missing {len(missing_vars)} expected variables: {', '.join(missing_vars[:5])}{'...' if len(missing_vars) > 5 else ''}")
                    logger.warning(f"{service_name}: This may indicate partial .env file parsing due to syntax errors")
                    # Check for common parsing issues
                    try:
                        with open(env_file, 'r') as f:
                            content = f.read()
                            if '@' in content or '`' in content or '!' in content:
                                logger.warning(f"{service_name}: .env file contains potentially problematic characters that may cause parsing to stop")
                    except:
                        pass
                else:
                    logger.info(f"{service_name}: All expected variables loaded successfully")
                
            return len(missing_vars) == 0 if expected_vars else True
        else:
            logger.error(f"{service_name}: Failed to load environment variables from {env_file}")
            return False
            
    except Exception as e:
        logger.error(f"{service_name}: Exception while loading .env file: {e}")
        
        # Try to provide more specific error information
        if "unexpected character" in str(e).lower():
            logger.error(f"{service_name}: .env file contains malformed content - check for invalid characters or syntax")
        elif "permission" in str(e).lower():
            logger.error(f"{service_name}: Permission denied reading .env file")
        elif "encoding" in str(e).lower():
            logger.error(f"{service_name}: .env file encoding issue - ensure it's UTF-8")
            
        return False

def load_dotenv_or_warn(service_name: str = "Service") -> bool:
    """
    Convenience function that loads .env from current directory and warns on failure.
    This is the drop-in replacement for simple load_dotenv() calls.
    
    Args:
        service_name: Name of the service for logging
        
    Returns:
        bool: True if successfully loaded, False if failed
    """
    return load_dotenv_with_logging(service_name=service_name)

def get_env_var_with_logging(
    var_name: str, 
    default: Optional[str] = None,
    required: bool = False,
    service_name: str = "Service"
) -> Optional[str]:
    """
    Get environment variable with logging about whether it was found.
    
    Args:
        var_name: Name of environment variable
        default: Default value if not found
        required: If True, logs error when variable is missing
        service_name: Service name for logging
        
    Returns:
        str or None: Environment variable value or default
    """
    value = os.getenv(var_name, default)
    
    if value is None and required:
        logger.error(f"{service_name}: Required environment variable {var_name} is not set")
    elif value is None and default is not None:
        logger.debug(f"{service_name}: Using default value for {var_name}")
    elif value is not None:
        # Don't log the actual value for security, just that it exists
        logger.debug(f"{service_name}: Found environment variable {var_name}")
        
    return value
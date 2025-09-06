#!/usr/bin/env python3
"""
Debug script to understand hillview filtering test failures.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'api', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from integration.test_hillview_filtering import TestHillviewFiltering
from utils.test_utils import clear_test_database

def main():
    print("=== DEBUG HILLVIEW FILTERING TEST ===")
    
    # Clear database first
    try:
        clear_test_database()
        print("✓ Database cleared")
    except Exception as e:
        print(f"✗ Database clear failed: {e}")
        return 1
    
    # Create test instance
    test_runner = TestHillviewFiltering()
    
    # Try setup
    try:
        print("\nTrying test setup...")
        test_runner.setup_method()  # Initialize instance variables
        success = test_runner.setup()
        print(f"Setup result: {success}")
        print(f"Test users: {len(test_runner.test_users)}")
        print(f"Test photos: {len(test_runner.test_photos)}")
        
        if test_runner.test_photos:
            print("Sample photo:", test_runner.test_photos[0])
        
    except Exception as e:
        print(f"✗ Setup failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Cleanup
        test_runner.cleanup()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
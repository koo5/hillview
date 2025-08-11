#!/usr/bin/env python3
"""
Run the photo processing worker.
"""
import sys
import os

# Add the api directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

from app.worker import main

if __name__ == "__main__":
    print("Starting Hillview photo processing worker...")
    print("Press Ctrl+C to stop")
    main()
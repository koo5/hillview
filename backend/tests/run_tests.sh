#!/bin/bash

# Create test virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating test virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install test dependencies
echo "Installing test dependencies..."
pip install -r requirements.txt

# Run the tests
echo "Running secure upload workflow test..."
python -m pytest test_secure_upload_workflow.py::TestSecureUploadWorkflow::test_complete_secure_upload_workflow -v -s

# Deactivate virtual environment
deactivate
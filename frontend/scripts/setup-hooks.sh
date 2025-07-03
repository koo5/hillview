#!/bin/bash

# Script to set up Git hooks using Husky
echo "Setting up Git hooks..."

# Install husky if not already installed
if ! command -v husky &> /dev/null; then
    echo "Installing husky..."
    bun add -d husky
fi

# Initialize husky
npx husky install

# Make pre-commit hook executable
chmod +x .husky/pre-commit

echo "✅ Git hooks set up successfully!"
echo "Pre-commit validation will now run automatically before each commit."
#!/usr/bin/env fish

# Shared Node.js version management for Android scripts
# Usage: source (dirname (status --current-filename))/ensure-node-version.sh

# Switch to required Node.js version
echo "🔄 Switching to Node.js v22.18.0..."
nvm use v22.18.0

# Verify Node.js version after nvm
if not node --version | string match -q -- 'v2*'
    echo "❌ Node.js 20+ required. Current: "(node --version)
    echo "NVM switch failed - check Node.js installation"
    exit 1
end
echo "✅ Using Node.js "(node --version)
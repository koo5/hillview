#!/bin/bash

# Script to generate Android keystore for APK signing

KEYSTORE_FILE="hillview-release.keystore"
ALIAS="hillview"
STOREPASS="hillview123"
KEYPASS="hillview123"

# Check if keystore already exists
if [ -f "$KEYSTORE_FILE" ]; then
    echo "Keystore $KEYSTORE_FILE already exists!"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 1
    fi
fi

echo "Generating Android keystore..."
echo "This keystore will be used to sign your APK releases."
echo ""

# Generate keystore with default values
keytool -genkeypair -v \
    -keystore "$KEYSTORE_FILE" \
    -alias "$ALIAS" \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass "$STOREPASS" \
    -keypass "$KEYPASS" \
    -dname "CN=Hillview Dev, OU=Development, O=Hillview, L=City, ST=State, C=US"

if [ $? -eq 0 ]; then
    echo ""
    echo "Keystore generated successfully!"
    echo "Location: $(pwd)/$KEYSTORE_FILE"
    echo "Alias: $ALIAS"
    echo "Store Password: $STOREPASS"
    echo "Key Password: $KEYPASS"
    echo ""
    echo "⚠️  IMPORTANT: Keep this keystore file safe! You'll need it to sign all future releases."
    echo "Consider backing it up in a secure location."
else
    echo "Failed to generate keystore."
    exit 1
fi
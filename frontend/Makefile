# Hillview Frontend Makefile
# Convenient commands for development and validation

# Configuration
SHELL := /bin/bash
.DEFAULT_GOAL := help

# Common variables
SCRIPTS_DIR := scripts
NODE_MODULES := node_modules

# Phony targets
.PHONY: help install dev build test test-android validate validate-quick validate-android clean clean-android setup all

# Default target - show help
help:
	@echo "Hillview Frontend - Available commands:"
	@echo ""
	@echo "  Development:"
	@echo "    make install         - Install dependencies"
	@echo "    make dev             - Start development server"
	@echo "    make build           - Build for production"
	@echo ""
	@echo "  Testing:"
	@echo "    make test            - Run all tests"
	@echo "    make test-android    - Run Android tests only"
	@echo ""
	@echo "  Validation:"
	@echo "    make validate        - Run full validation (build + all tests)"
	@echo "    make validate-quick  - Quick validation (skip Android tests)"
	@echo "    make validate-android - Android-specific validation"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make clean           - Clean build artifacts"
	@echo "    make clean-android   - Clean Android device/emulator storage"
	@echo "    make setup           - Initial project setup with git hooks"
	@echo ""
	@echo "  Shortcuts:"
	@echo "    make all             - Build and run all tests"
	@echo "    make check           - Alias for validate-quick"

# Dependency management
$(NODE_MODULES): package.json bun.lock
	@echo "📦 Installing dependencies..."
	@bun install
	@touch $(NODE_MODULES)

install: $(NODE_MODULES)

# Development tasks
dev: $(NODE_MODULES)
	@bun run dev

build: $(NODE_MODULES)
	@$(SCRIPTS_DIR)/build-check.sh

# Testing tasks
test: test-android

test-android: $(NODE_MODULES)
	@bun run test:android

# Validation tasks
validate: $(NODE_MODULES)
	@$(SCRIPTS_DIR)/validate.sh

validate-quick: $(NODE_MODULES)
	@$(SCRIPTS_DIR)/validate.sh --skip-android

validate-android: $(NODE_MODULES)
	@$(SCRIPTS_DIR)/validate-android.sh

# Aliases
check: validate-quick

all: build test
	@echo "✅ Build and tests completed!"

# Maintenance tasks
clean:
	@echo "🧹 Cleaning build artifacts..."
	@rm -rf build/ .svelte-kit/ node_modules/.vite/ src-tauri/gen/android/app/build/
	@echo "✅ Clean complete!"

clean-android:
	@$(SCRIPTS_DIR)/clean-android.sh

setup: install
	@echo "🔧 Setting up project..."
	@$(SCRIPTS_DIR)/setup-hooks.sh
	@echo "✅ Project setup complete!"

# Show current project status
status:
	@echo "📊 Project Status:"
	@echo -n "  Dependencies: "; \
		if [ -d $(NODE_MODULES) ]; then echo "✓ Installed"; else echo "✗ Not installed"; fi
	@echo -n "  Build artifacts: "; \
		if [ -d build ] || [ -d .svelte-kit ]; then echo "✓ Present"; else echo "✗ Clean"; fi
	@echo -n "  Git hooks: "; \
		if [ -f .husky/pre-commit ]; then echo "✓ Configured"; else echo "✗ Not configured"; fi
	@echo ""
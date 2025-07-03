# Validation and Testing Guide

This document explains the validation and testing setup for the Hillview frontend project.

## Quick Start

```bash
# Run full validation (build + all tests)
bun run validate

# Run quick validation (build + type checking, skip Android tests)
bun run validate:quick

# Or use Make
make validate
```

## Validation Script

The validation script (`scripts/validate.sh`) runs the following checks:

1. **Dependency Check** - Ensures node_modules are installed
2. **Type Checking** - Runs TypeScript/Svelte type checking
3. **Linting** - Runs ESLint if configured
4. **Build** - Builds the project for production
5. **Unit Tests** - Runs unit tests if available
6. **Android Tests** - Runs Android E2E tests (if device connected)
7. **Code Quality** - Checks for console.log and TODO comments

### Usage

```bash
# Full validation
./scripts/validate.sh

# Skip Android tests
./scripts/validate.sh --skip-android
```

## Git Hooks

Pre-commit hooks ensure code quality before commits:

```bash
# Set up git hooks (one-time setup)
bun run setup:hooks
```

This will:
- Install Husky for Git hooks
- Set up pre-commit validation
- Run quick validation before each commit

## CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on:
- Push to main/master/develop branches
- Pull requests

### Pipeline stages:
1. **Validate** - Type checking, linting, and build
2. **Android Test** - Runs E2E tests on Android emulator
3. **Deploy** - Deploys to GitHub Pages (main/master only)

## Available Scripts

```bash
# Development
bun run dev              # Start dev server
bun run build            # Build for production
bun run preview          # Preview production build

# Testing
bun run check            # Type checking
bun run test:android     # Android E2E tests

# Validation
bun run validate         # Full validation
bun run validate:quick   # Quick validation (no Android)
bun run ci               # CI validation

# Setup
bun run setup:hooks      # Set up git hooks
```

## Make Commands

For convenience, you can also use Make:

```bash
make help        # Show available commands
make install     # Install dependencies
make dev         # Start development
make build       # Build production
make test        # Run tests
make validate    # Full validation
make clean       # Clean artifacts
make setup       # Initial setup
```

## Testing Requirements

### Android Tests
- Android device or emulator must be running
- ADB must be installed and in PATH
- Appium dependencies must be installed

Check Android setup:
```bash
bun run appium:doctor
```

## Best Practices

1. **Before Committing**
   - Run `bun run validate:quick` to ensure build passes
   - Fix any TypeScript errors or build issues

2. **Before Merging**
   - Ensure all CI checks pass
   - Run full validation locally: `bun run validate`

3. **Regular Maintenance**
   - Keep dependencies updated
   - Address TODO comments regularly
   - Remove unnecessary console.log statements

## Troubleshooting

### Build Fails
- Check TypeScript errors: `bun run check`
- Clear cache: `make clean`
- Reinstall dependencies: `rm -rf node_modules && bun install`

### Android Tests Fail
- Ensure device/emulator is running: `adb devices`
- Check Appium setup: `bun run appium:doctor`
- Review logs in `logs/` directory

### Git Hook Issues
- Reinstall hooks: `rm -rf .husky && bun run setup:hooks`
- Check hook permissions: `chmod +x .husky/pre-commit`
# Hillview Frontend - Build & Test Validation

This project includes several scripts to ensure code quality before commits and deployments.

## Quick Commands

```bash
# Ensure build passes
bun run build:check

# Run full validation (with type checking and tests)
bun run validate

# Run quick validation (skip Android tests)
bun run validate:quick

# Run Android tests
bun run test:android
```

## Available Scripts

### Build Check (`build:check`)
- Ensures the project builds successfully
- Quick check before commits
- Usage: `bun run build:check`

### Full Validation (`validate`)
- Type checking with `svelte-check`
- Build verification
- Android tests (if device connected)
- Code quality checks
- Usage: `bun run validate`

### Quick Validation (`validate:quick`)
- Same as full validation but skips Android tests
- Ideal for pre-commit hooks
- Usage: `bun run validate:quick`

### Setup Git Hooks (`setup:hooks`)
- Installs pre-commit validation
- One-time setup
- Usage: `bun run setup:hooks`

## Git Hooks

After running `bun run setup:hooks`, the pre-commit hook will automatically:
- Run type checking
- Verify the build passes
- Check for console.log statements
- Prevent commits if validation fails

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs:
1. **Build validation** on multiple Node versions
2. **Android tests** on macOS with emulator
3. **Deployment** to GitHub Pages (main branch only)

## Makefile Commands

For convenience, you can also use Make:

```bash
make help        # Show commands
make build       # Build production
make validate    # Full validation
make check       # Quick validation
make clean       # Clean artifacts
```

## Files

- `scripts/validate.sh` - Full validation script
- `scripts/build-check.sh` - Simple build verification
- `scripts/setup-hooks.sh` - Git hooks setup
- `.github/workflows/ci.yml` - CI/CD pipeline
- `.husky/pre-commit` - Pre-commit hook
- `docs/VALIDATION.md` - Detailed documentation

## Troubleshooting

If validation fails:
1. Check TypeScript errors: `bun run check`
2. Review build output: `bun run build`
3. Clean and rebuild: `make clean && make build`

For Android test issues:
1. Ensure device/emulator is running: `adb devices`
2. Check Appium setup: `bun run appium:doctor`
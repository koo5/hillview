These patches cover advisories with no published fixed package version:

- `extract-zip@2.0.1`: GHSA-7pqw-9j4j-h8q3 and GHSA-jmr9-qjv8-65gv.
  Validate lexical and canonical containment, including dangling symlink
  ancestors; refuse writes through an existing final-component symlink and
  use `O_NOFOLLOW` where available. Internal archive symlinks remain supported.
  Upstream tracking: https://github.com/max-mapper/extract-zip/pull/160
- `braces@3.0.3`: GHSA-vfj7-8cjw-p6xm. Bound parser nesting and recursive
  compile/expand/stringify walkers to 256 levels, including direct AST input.

Bun applies these through `patchedDependencies`; a frozen install verifies
that the lockfile and patch hashes match. Run `bun run test:security` here.
The tests use real ZIP files and verify normal extraction and brace behavior
alongside the attack cases. The original packages fail the regression checks.

OSV still reports the original version numbers because it does not evaluate
Bun patch contents. No advisory has been suppressed. Remove a patch only after
a published upstream release incorporates the fix and passes these tests.

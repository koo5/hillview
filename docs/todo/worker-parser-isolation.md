# Future thread: isolate untrusted image and metadata parsing

Deferred explicitly on 2026-10-22; resume as a separate design/implementation
thread. Continue the ExifTool security review independently.

The current worker pool provides crash recovery, not a privilege boundary.
Processing children inherit worker environment/access and initialize CDN clients.
A JPEG gate does not protect against vulnerabilities in JPEG, EXIF, ICC or
embedded-metadata parsers. See ../security/public-jpeg-review-2026-10-22.md.

Desired boundary: parsing and transformation run without signing/CDN credentials,
network access, unrelated source files, other jobs' outputs or writable code.
A trusted coordinator authenticates jobs, stages inputs, validates bounded
results, and publishes artifacts. Include ExifTool metadata extraction AND tag
copying, native decoding/color conversion, and external-tool descendants.

Questions for the future thread:
- Per-job disposable process/container versus reusable isolated worker; startup
  and ML-model memory costs, concurrency, Linux/Docker and Fly/Firecracker support.
- Read-only input, private bounded scratch space, explicit output handoff;
  defend against symlink/path tricks and oversized output from a compromised child.
- Remove credentials from environment and mounts; deny outbound networking;
  restrict filesystem, capabilities and syscalls where compatible with libraries.
- Bound CPU, wall time, memory, disk, file descriptors, processes and output bytes.
  Kill/reap the whole job process tree and clean up after timeout/OOM/crash.
- Keep auxiliary panorama policy explicit; do not silently lose disk spilling,
  color management or legitimate resource provisioning.

Acceptance evidence: a deliberately misbehaving harmless helper cannot read a
sentinel outside its input/scratch, obtain coordinator secrets, access network,
modify another job, evade timeouts with descendants, or exceed configured
budgets. Verify ordinary JPEG color/orientation/metadata and auxiliary fixtures
remain correct. Test coordinator rejection of malformed results and recovery
without losing unrelated jobs. Document residual shared-kernel risks.

This note does not authorize deployment or claim these protections exist today.

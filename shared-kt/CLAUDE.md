# shared-kt

@README.md

## Docs

- **[One state](../docs/one-state.md)**: one user-facing location/orientation state, written and read by everything, with no direct hardware side-channels — the sensor and geo-tracking code here feeds it in both apps
- **[Upload: one funnel](../docs/upload-one-funnel.md)**: the same shape of rule for the upload family that lives here — one scheduler, one drain
- **[Photo sources: independent loading](../docs/sources-loading.md)**: the contract `StreamPhotoLoader` and `CullingGrid` implement for both apps
- **[Native Android Auth](../docs/native-auth.md)**: Credential Manager + Google ID-token login — concepts, security reasoning, and where everything lives
- **[Geo election test debt](../docs/geo-election-test-todo.md)**: what the geo-tracking election rework across `shared-kt`, both apps and `pics` still leaves unasserted, and what is already covered

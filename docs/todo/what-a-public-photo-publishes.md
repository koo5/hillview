# What a public photo actually publishes

Research direction, opened 2026-09-27. Nothing here is a decision yet.

The prompt for it: withholding the wholesale EXIF dump from public endpoints by
default is probably the right call, and **users should be able to make an informed
choice** about what else goes out. The interesting part is what "informed" means
once you look at what is currently published, because the careful part of the
system is no longer the risky part.

## What the public endpoint does today

Measured on a real prod photo (`ce9ffa98`, 2026-09-27), owner response versus
public response:

| | raw (owner) | public |
|---|---:|---:|
| `exif_data['data']` tags | **73** | — |
| curated `exif` fields | — | **8** |
| `exif_data['gps']` (lat/lon/altitude/bearing/**pitch**) | 5 | — |
| `exif_data['debug']` | 7 | — |

`_curate_exif` is deliberate and its docstring says why: camera settings only,
"nothing that LOCATES", because the raw dump can carry more precise or sensitive
location than we want to publish. The public response instead carries
latitude/longitude/bearing/altitude at the top level, which is the app's whole
point — so the withholding is not hiding the position, it is refusing to publish a
*second, uncurated* copy of it.

What the 65 withheld tags actually contain on this photo:

- **Filesystem timestamps** — `FileAccessDate`, `FileInodeChangeDate`,
  `FileModifyDate`. When the file was HANDLED, which is not when the photo was
  taken and is nobody's business.
- **A thicket of time tags** — `SubSecCreateDate`, `SubSecModifyDate`,
  `SubSecTimeDigitized`, `ModifyDate`, `CreateDate`, and
  `SubSecDateTimeOriginal`, which is the camera's own exposure time (see
  `captured-at-is-the-exposure.md` — it is 515 ms after the app's `captured_at` on
  this photo).
- **`Software`**, and the `UserComment` provenance blob.
- **No serial numbers on this phone** — but that is a property of this device, not
  of the format. DSLR bodies write `SerialNumber` and `LensSerialNumber`, and the
  `pics` pipeline ingests exactly those photos. A body serial in a public dump is a
  strong cross-photo identifier: it links every photo a person ever published, and
  it cannot be unlinked afterwards.

So: default-withhold looks right, and is already the behaviour. The open question
is not whether to keep it.

## The part that is not careful: the inertial payload

Today's deploy published, publicly and **unauthenticated**:

- `attitude` — 10 fields: true and magnetic heading, pitch, roll, sensor accuracies
- `fix` — 5 fields, including **`speed_mps`** and `provider`
- `inertial` — gravity and linear acceleration
- **`imu_samples_url`** — a gzipped artifact holding **4 776 samples: six seconds
  of accelerometer and gyroscope at 398 Hz**, fetchable by anyone with the URL

A six-second 400 Hz motion trace is plausibly *more* identifying than any EXIF tag
in the withheld set. It is a movement signature: whether the photographer was
walking, standing, in a vehicle, on a bike; their gait; a tremor. Gait
recognition from phone IMU is an established literature, and six seconds at
400 Hz is not a marginal sample. `fix.speed_mps` publishes their speed outright.

**That is the finding worth acting on.** The EXIF gate was reasoned about
carefully years ago; the inertial payload went out this morning because it is
research data and nobody asked the question. The two sit in the same response with
opposite postures. A user who chose "make this photo public" consented to a
photo with a position and a heading, and has now also published a motion trace
they were never told about.

Not an argument for removing it — it is the point of the recon work. An argument
that it belongs on the *consented* side of a line that does not exist yet.

## Design options, cheapest first

1. **Publish the summary, withhold the raw window.** `inertial.imu_window` already
   carries sample count, bounds and the three peaks — enough for a reader to know
   a window exists and whether the frame was moving. The raw artifact becomes
   owner-only or request-gated. This costs reconstruction nothing until someone
   actually wants the samples, at which point it is a request rather than a
   default. It is also the smallest change: one field's visibility.
2. **Per-account default plus per-photo override**, mirroring `is_public` and the
   licence model, which are the precedents already in the schema. The hard part is
   not the switch, it is the explanation: "publish a 400 Hz motion trace" means
   nothing to a user, and an honest UI has to say what can be inferred from it.
3. **Licence-coupled.** CC photos already federate to Panoramax. Whatever is public
   flows outward and stops being controllable — which is the strongest argument for
   default-withhold on anything new, since a default that leaks is not revisitable.
4. **Authenticate the artifact URL.** Currently a plain pool URL served as a static
   file. Gating it is a real change to how pools work, and `_delete_one_url` /
   `delete_photo_files_for_artifacts` already exist for removal — but anything
   already fetched is gone, so revocation is not retroactive.

## Research questions

- **Can a 6 s window at 398 Hz re-identify a photographer across photos?** This is
  answerable with the data we now have: several photos from one device, and the
  `pics` corpus for negatives. If the answer is yes, option 1 stops being a
  preference and becomes the default.
- **What does reconstruction actually need?** If pose priors want peaks, gravity
  and a motion-blur estimate, the summary may be sufficient and the raw window is a
  research convenience — which would make option 1 nearly free. Nobody has checked.
- **What does Panoramax republish of what we serve?** Determines whether a
  publication decision is reversible at all.
- **What does the `pics` corpus already carry?** External DSLR photos with body
  serials, ingested before anyone asked this question. Worth an audit of what is
  public today rather than what new photos will do.

## Reading prod as a user — where that credential may live

Recorded because it came up alongside: the `frontend2` account password can be used
to fetch prod as its owner (this is how the owner/public difference above was
measured), and the rule for it follows the posture the project already has.

- **The workbench does not need it.** `enrich/api` takes `HILLVIEW_DB_URL`, and on
  the VPS it runs a mirror of the hillview database (75 766 photos as of
  2026-09-10). Everything the owner endpoint returns is already there, with more
  fidelity than the API exposes. A credential would add a second, weaker path and a
  new secret to manage, for nothing.
- **The GPU box must never have it**, and the GPU runbook already forbids the
  class: forwarding the API to a rented instance was rejected because it would hand
  an hourly machine "queue purges, run imports, every artifact and the photo
  mirror". The box gets a scoped broker user (`recon-worker`, no management tags,
  read-only on `^recon(\.(DQ|XQ))?$`, publish denied), from a mode-600 file on the
  VPS, through a tunnel opened from the trusted side. A hillview account password
  would be strictly worse than what that design deliberately withholds.
- **Where it may live:** a verification tool on the trusted side, reading the
  password through the project's existing convention — a `*_FILE` env var pointing
  at a runtime-mounted path (`MAPILLARY_CLIENT_TOKEN_FILE`,
  `OPENROUTER_API_KEY_FILE`, the CDN pool's `secrets_file`). Never a Docker `ARG` or
  `ENV`: build arguments persist in image history and `docker history` prints them,
  which is exactly the leak to avoid. Never in argv, where `ps` shows it. Exchange
  it for a token once and pass only the token onward — it expires on its own.

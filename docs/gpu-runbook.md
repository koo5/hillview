# Renting the GPU box: what is already done, and what to do on the day

Written 2026-09-12, before the first rental. Companion to `~/.claude/plans/we-re-in-a-forked-peppy-dragon.md`
(why a 4090, what it costs) and `recon/tasks.txt` (what we want to learn from it).

## Already done, so the rental clock does not pay for it

- **The payload image is built and published.** `hillview-recon-gpu:3e2bd058`, 16.8 GB,
  exported to 7.6 GB compressed with a SHA-256 beside it, served from the VPS over HTTPS
  with range requests so a partial pull resumes. Verified inside the image: both virtual
  environments import, torch is the **cu126** build that matches the base image, the CUDA
  RoPE kernel compiled, and the tiling and binary-PLY code is present.
- **The checkpoint is published beside it**, 2.6 GB, pulled by the VPS straight from Naver
  and verified as `e28f91b488554653e2b46ddae9c78c1143e0bcb2e27d3e26cdb0b717f1568eb2`.
  Nothing large ever leaves the house.
- **The workbench runs on the VPS** with its mirror loaded to 2026-09-10 17:33 — 75,766
  photos, including all four new areas — behind a secret path prefix and basic auth.
- **Fourteen runs are queued and waiting for a consumer.** See below.
- **The worker token is a real one**, in `~/hillview/enrich/.env` on the VPS at mode 600,
  and an unauthenticated callback is refused with 403.
- **The one-route proxy is already running** on the VPS as a restart-policy container
  (`callback-proxy`, 127.0.0.1:8075). Verified there: every route but
  `POST /api/recon/result` answers 404, and a real 2 MB callback with the token returns
  200 in 188 ms. Tunnel 8075; never 8070.
- **The box's broker user is scoped and tested** — see the tunnel section.
- **The published image is checksum-verified on disk**, `b3b33b55…d9529`, and the
  superseded one has been removed so there is nothing stale to pull by mistake.

## The queue, in the order it will run

| run | frames | what it answers |
|---|---|---|
| `gpu-calib-spotA` | 46 | Does the GPU produce a sane solve, and what is seconds-per-pair? Everything else is costed from this. Reference is 1.33 px, 0.9 cm. |
| `gpu-calib-spotA-masked` | 46 | What semantic masking costs on a GPU. It is 18 s/frame on CPU and should be under 1 s. |
| `obelisk-w8` | 182 | Baseline on a tight rotation. |
| `kriz-w8` | 126 | Baseline on the double walk-around. |
| `podolanka-first180-w8` | 180 | A contiguous half, to derisk the frame count before the whole thing. Never a stride: stride 4 takes the gold walk from 1.33 px to 11 px. |
| `brandys-w8` | 334 | Baseline on the criss-cross area. |
| `podolanka-w8` | 363 | Six times the largest solve we have ever run. |
| `obelisk-complete` | 182 | Exhaustive pairing where it should win outright — 7,505 revisit pairs in a 25 m rotation. If complete does not beat window-8 here, it will not anywhere. |
| `brandys-bearing` | 334 | Distance-gated pairing against 11,938 revisit pairs a window cannot see. |
| `brandys-adaptive` | 334 | Reaching past weak links, on the case it was designed for. |
| `obelisk-tiles2x2-pinned` | 182 | Tiling with each tile's principal point pinned from its crop box. A 2×2 grid buys only 1.5× the whole-frame detail, so this is a test of the *pinning*, not of resolution — and a coarse grid puts the crop centre furthest from the frame centre, which is where pinning should matter most. |
| `obelisk-tiles2x2-freepp` | 182 | The same with it estimated. A two-frame toy test could only separate them by 0.330 m against 0.294 m, too thin to conclude from. |
| `res23-spotA-tiles3x3` | 22 | **The control.** Tiling on the one cluster with a trustworthy baseline: these 22 frames solve at 1.33 px with 1.0 cm ground agreement. 3×3 buys 2.6× detail. |
| `res23-spotA-tiles7x5` | 22 | The same at **native** detail — 7×5 is where a tile's long side finally fits inside 512. If this does not beat 1.33 px on identical input, the ceiling is MASt3R's centred-crop assumption and Pow3R is the route (see `recon/tasks.txt`). |

Every tiled run now logs and records what its grid actually bought, as
`stats.tiles.detail_vs_whole_frame`, because a coarse grid otherwise gets misread as
"tiling did not help". Watch `tile_centre_spread_m` too: tiles of one frame share a camera
and must land in one place.

Re-order with `POST /api/recon/purge_queue` then requeue in the order wanted; a finished run
refuses requeue unless forced.

## On the day

### 1. Rent

Filter: `gpu_name=RTX_4090 num_gpus=1 gpu_ram>=24 disk_space>100 inet_down>500 inet_up>300
cpu_cores_effective>=8 reliability>0.98 cuda_vers>=12.6`. The offer we sized (Norway, 18.3
effective cores, 37 GB RAM, 160 GB disk, 899/907 Mbps, 99.7%, $0.237/hr) clears everything
except the plan's 48 GB RAM line, and that is a comfort margin: our 60-frame solves peak
near 5–6 GB resident.

**Destroy instances, never stop them.** Storage is billed while an instance exists.

### 2. Pull the payload, on the instance

The published segment is in `~/.recon-pub-segment` on the VPS (mode 600, deliberately not
written into anything the web server serves). With `BASE=https://robust1.ueueeu.eu/<segment>`:

```sh
curl -fL -O "$BASE/hillview-recon-gpu-3e2bd058.tar.zst"
curl -fL -O "$BASE/hillview-recon-gpu-3e2bd058.tar.zst.sha256"
sha256sum -c hillview-recon-gpu-3e2bd058.tar.zst.sha256   # refuse to continue if this fails
zstd -d -c hillview-recon-gpu-3e2bd058.tar.zst | docker load
```

The checkpoint is **not** in the image, deliberately: `torch.load` executes what it contains,
so its provenance has to be ours, and its licence is non-commercial. The entrypoint fetches
it from `RECON_CKPT_URL` and verifies the checksum, so it needs no separate step.

### 3. Open the tunnel, from the trusted side

The workbench accepts nothing inbound. Open it **from the VPS**, so the broker and the
callback appear on the instance's own loopback, where the worker's defaults already point.

First start the one-route proxy on the VPS, and forward **that**, not 8070:

```sh
nohup python3 ~/hillview/enrich/recon/callback_proxy.py > ~/proxy.log 2>&1 &
ssh -N -R 5672:127.0.0.1:5672 -R 8070:127.0.0.1:8075 root@<instance> -p <port>
```

The instance still believes it is talking to 8070 on its own loopback, which is what the
worker's defaults expect, and it is. Forwarding the API itself would hand an hourly-rented
machine queue purges, run imports, every artifact and the photo mirror, on an API that is
unauthenticated by design; the proxy accepts one method on one path, streams the body
through unbuffered, and answers everything else 404. Verified before the first rental:
every other route 404s, a valid callback returns 200, and a 2 MB multipart streams in 66 ms.

**The box gets its own broker user**, `recon-worker`, no tags and therefore no management
access, with configure/write/read all restricted to `^recon(\.(DQ|XQ))?$`. Its URL is in
`~/.recon-amqp` on the VPS at mode 600. Use that, never `enrich:enrich`, which is an
administrator that can also read `terrain` and `matching`.

Verified before the rental, and two of the checks were wrong the first time, which is worth
knowing if you ever re-derive these:

- Consuming from `recon` works; consuming from `terrain` or `matching` is refused.
- **Publishing anywhere is refused.** The first attempt granted write on the default
  exchange, whose name is the empty string, and that lets a client publish to *any* queue by
  routing key — the permission is checked on the exchange, not the destination. Write is now
  denied outright, which a consumer does not need.
- A passive `queue.declare` is **not** a permission test: RabbitMQ answers it without
  checking. Neither is a bare `basic.publish`, which is asynchronous, so the server's refusal
  never reaches the client. Use `basic.get` for read and publisher confirms for write.
- The real worker was then run against these credentials on CPU: it reached the broker and
  the callback proxy, consumed a job, and started the solve with the right flags. Nothing in
  remoulade needed to publish, because the actor is `max_retries=0`.

### 4. Start the worker

```sh
docker run -d --name recon --gpus all \
  -e RECON_DEVICE=auto \
  -e RECON_CKPT_URL="$BASE/mast3r.pth" \
  -e RECON_CKPT_SHA256=e28f91b488554653e2b46ddae9c78c1143e0bcb2e27d3e26cdb0b717f1568eb2 \
  -e RABBITMQ_URL="$(cat ~/.recon-amqp | cut -d= -f2-)"  # the scoped recon-worker user \
  -e RECON_CALLBACK_URL='http://127.0.0.1:8070/api/recon/result' \
  -e ENRICH_WORKER_TOKEN='<from ~/hillview/enrich/.env on the VPS>' \
  -v /workspace/runs:/runs \
  hillview-recon-gpu:3e2bd058
```

The entrypoint refuses to start in any state that would quietly waste rent: no GPU visible
to torch, no compiled RoPE kernel (which would run the slow path for hours while looking
healthy), no checkpoint, or a checkpoint whose checksum does not match. It also tests that
the broker and the callback are reachable and says "is the tunnel up?" if not.

### 5. Watch

- The bench's runs table, most recent first, with pace and ETA per running run.
- `meta.progress.s_per_it` should drop 30–100× against the archived CPU pace on the same
  cluster. If it does not, the RoPE kernel warning is the first thing to check.
- The machine card for disk: a 60-frame run dir is 3.6 GB, of which 3.0 GB is the forward
  cache. That cache is *meant* to stay on the instance and be reused across the batch.

### 6. Before destroying

Confirm every run has its artifacts. This is the irreversible step. The forward cache is
deliberately left to die: it is content-addressed and regenerable, and pulling 50 GB to save
recomputation we may never need is the wrong trade. What comes home is about 285 MB per 60
frames, roughly 2 GB for the whole batch now that PLY is binary and depth is float16.

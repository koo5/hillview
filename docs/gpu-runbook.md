# Renting the GPU box: what is already done, and what to do on the day

Written 2026-09-12, before the first rental. Companion to `~/.claude/plans/we-re-in-a-forked-peppy-dragon.md`
(why a 4090, what it costs) and `recon/tasks.txt` (what we want to learn from it).

## Already done, so the rental clock does not pay for it

- **The payload image is built and published.** `hillview-recon-gpu:4c8799f5`, 16.8 GB,
  exported to 7.6 GB compressed with a SHA-256 beside it, served from the VPS over HTTPS
  with range requests so a partial pull resumes. Verified inside the image: both virtual
  environments import, torch is the **cu126** build that matches the base image, the CUDA
  RoPE kernel compiled, and the tiling and binary-PLY code is present.
- **The checkpoint is published beside it**, 2.6 GB, pulled by the VPS straight from Naver
  and verified as `e28f91b488554653e2b46ddae9c78c1143e0bcb2e27d3e26cdb0b717f1568eb2`.
  Nothing large ever leaves the house.
- **The workbench runs on the VPS** with its mirror loaded to 2026-09-10 17:33 — 75,766
  photos, including all four new areas — behind a secret path prefix and basic auth.
- **Twelve runs are queued and waiting for a consumer.** See below.
- **The worker token is a real one**, in `~/hillview/enrich/.env` on the VPS at mode 600,
  and an unauthenticated callback is refused with 403.

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
| `obelisk-tiles2x2-pinned` | 182 | First tiled solve, with each tile's principal point pinned from its crop box. |
| `obelisk-tiles2x2-freepp` | 182 | The same with the principal point estimated, because a two-frame toy test could only separate them by 0.330 m against 0.294 m and that is too thin to conclude from. Watch `stats.tiles.tile_centre_spread_m` on both: tiles of one frame share a camera and must land in one place. |

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
curl -fL -O "$BASE/hillview-recon-gpu-4c8799f5.tar.zst"
curl -fL -O "$BASE/hillview-recon-gpu-4c8799f5.tar.zst.sha256"
sha256sum -c hillview-recon-gpu-4c8799f5.tar.zst.sha256   # refuse to continue if this fails
zstd -d -c hillview-recon-gpu-4c8799f5.tar.zst | docker load
```

The checkpoint is **not** in the image, deliberately: `torch.load` executes what it contains,
so its provenance has to be ours, and its licence is non-commercial. The entrypoint fetches
it from `RECON_CKPT_URL` and verifies the checksum, so it needs no separate step.

### 3. Open the tunnel, from the trusted side

The workbench accepts nothing inbound. Open it **from the VPS**, so the broker and the
callback appear on the instance's own loopback, where the worker's defaults already point:

```sh
ssh -N -R 5672:127.0.0.1:5672 -R 8070:127.0.0.1:8070 root@<instance> -p <port>
```

**The residual risk, stated plainly.** Forwarding 8070 gives the rented box the whole
workbench API, which is unauthenticated by design and exposes queue purges, run imports,
artifacts and the photo mirror. The photos are public and the queue is reconstructible, so
for a first session that is contained — but the hardening is cheap and worth doing before
this becomes routine: a Caddy listener on 127.0.0.1:8075 that proxies only
`POST /api/recon/result` to 8070 and 404s everything else, and forward 8075 instead.

Give the box its own RabbitMQ user scoped to the `recon` queue rather than `enrich:enrich`,
which can also read `terrain` and `matcher`.

### 4. Start the worker

```sh
docker run -d --name recon --gpus all \
  -e RECON_DEVICE=auto \
  -e RECON_CKPT_URL="$BASE/mast3r.pth" \
  -e RECON_CKPT_SHA256=e28f91b488554653e2b46ddae9c78c1143e0bcb2e27d3e26cdb0b717f1568eb2 \
  -e RABBITMQ_URL='enrich:enrich@127.0.0.1:5672' \
  -e RECON_CALLBACK_URL='http://127.0.0.1:8070/api/recon/result' \
  -e ENRICH_WORKER_TOKEN='<from ~/hillview/enrich/.env on the VPS>' \
  -v /workspace/runs:/runs \
  hillview-recon-gpu:4c8799f5
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

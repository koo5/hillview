# Analyzer evaluation and metadata design

Design recorded 2026-10-11 after reading the queue-based analyzer at d4229dac.
The detailed configuration approvals below describe a future extension.

## Minimal implementation now

`ANALYZER_TRUSTED_MODELS` (comma-separated, loaded as `distill.TRUSTED_MODELS`)
controls which models' answers can participate in
distillation. It currently contains the evaluated Nemotron and Qwen models.
`--model` independently selects what to query. An untrusted query model records
answers but does not distill or publish them, or change the production queue.
Adding it to the trusted list makes its saved answers eligible without changing
the history. Fine-grained configuration approvals remain future work.

`--prefer missing` retains the usual priority for missing assessments;
`--prefer update` visits photos with existing assessments first, then the rest.
Both use the database. Updating uses a stable traversal and the existing JSON
locks; successful cached passes do not consume more requests after a restart.
Failed photos back off in memory using the existing retry policy. Restarting
the process resets that backoff; persistent experimental scheduling is deferred.

Settings in `.env` for the current comparison on dev44:

```bash
ANALYZER_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
ANALYZER_PREFER=update
ANALYZER_INTERVAL=10
ANALYZER_ALTERNATIVE_MODEL=dots-studio/dots-3-note-preview:free
ANALYZER_TRUSTED_MODELS=nvidia/nemotron-nano-12b-v2-vl:free,qwen/qwen3-vl-30b-a3b-thinking
```

```bash
./compose.sh --profile analyzer --profile analyzer-alternative up -d --no-deps analyzer analyzer-alternative
./compose.sh logs --tail 50 analyzer analyzer-alternative
```

The compose secret is `secrets/OPENROUTER_API_KEY`. Sessions retain reported
usage/cost, provider/model, generation ID, finish reason and raw answer text.
Transport failures are recorded with unknown cost. Each pass is saved before
the next, using atomic file replacement. HTTP 502 retries are bounded to three
attempts. Individual retry billing records and the runtime meta layout below
are still future work. `--interval` defaults to 60 seconds between photos that
need calls; provider daily limits can still pause useful collection.

On 2026-10-12, both free Gemma 4 variants returned upstream shared-pool 429s.
Switched the query model to Nemotron Omni after both passes on an assessed
photo returned schema-valid answers with reported cost zero. Those calls needed
502 retries, so reliability still needs observation; the new model remains
outside the trusted list. The smoke-test answers are in the regular history.

A second persistent collector now runs Dots in the `analyzer-alternative`
service. Both collectors use a 10-second interval, the same per-photo locks,
and the shared daily account quota. Dots echoed the schema on one smoke-test
features pass: keep that answer as evaluation evidence, not trusted output.
Failure backoffs remain unchanged.

## Record, evaluate, distill, publish

Recording an answer must not grant it permission to influence production.
Acquisition records every trial in the existing per-photo sessions history.
Evaluation reads explicitly selected sessions. Production distillation reads
only successful sessions allowed by an explicit approval policy. Publication
writes the resulting overall assessment to photos.analysis.

For example, a trial of google/gemma-4-26b-a4b-it:free records both passes but
does not change the production document, dequeue production work, or influence
later production distillation. Once evaluated and approved, its saved answers
can be used without paying for inference again. Revoking approval excludes the
answers from future distillation without deleting their history. Existing DB
documents require an explicit rebuild to reflect policy changes.

The user extensively evaluated the existing Nemotron and Qwen configurations
and was happy with their quality. Preserve those as approved legacy baselines;
do not require a new ground-truth campaign before using them for comparison.
Their approvals should identify the existing configurations, rather than
approve every future prompt bearing the same model name.

## Configuration identity and approval

Approve a configuration, optionally for just features or distances, rather than
the model name alone. Its identity includes requested model, prompt/schema
revision, inference parameters and provider constraints. Keep the full rendered
prompt in each session: focal-length-specific variants belong to the same
prompt revision but have different concrete request fingerprints. Record the
returned model and provider separately so routing changes remain observable.

Use pending, approved and rejected decisions with reviewer, timestamp, rationale
and supporting evaluation run IDs. Missing decisions mean pending. An approval
is external to the recorded answer: changing it must not rewrite raw evidence.
Legacy configurations need explicit entries; absence of new fields must not
make every legacy session trusted implicitly. Per-session exclusions can remove
known bad answers from an otherwise approved configuration.

Duplicate detection answers "have we already acquired this response?" and must
remain independent of approval. A pending cached response is reusable for
evaluation but remains ineligible for production distillation. Evaluation must
never borrow fields from a baseline to fill a candidate's missing answer.

## Storage

This source directory holds the design and, eventually, metadata code/schema.
Runtime metadata belongs in $ANALYZER_DATA_DIR/meta/ alongside the history, so
the existing /data bind mount preserves it. Proposed layout:

```text
<datadir>/
  <file_md5>.json                 existing session histories
  meta/
    approvals.json               explicit policy, with policy revision
    catalog/<snapshot_id>.json   dated model/provider prices and capabilities
    runs/<run_id>.json           configuration, subset, purpose, code revision
    requests/<request_id>.json   attempt outcome, usage and billing evidence
    evaluations/<eval_id>.json   scores, human review and referenced sessions
```

Give new sessions stable session IDs and run IDs. Request IDs identify each
HTTP attempt, including retries; provider generation IDs are separate. A run
has an explicit purpose (evaluation or production). Refer to legacy sessions
using photo hash plus a canonical session-content hash, without bulk rewriting
the existing files. Do not use list positions as durable identifiers.

Write each attempt separately using atomic replacement; shared policy updates
need locking too. Persist a started record before sending and finalize it after
the response. A crash can leave outcome and billing unknown; do not retry an
unknown attempt and pretend the first one never happened. Save each completed
pass before starting the next, so a second-pass failure cannot discard the
first answer. The current code saves both passes together and does not persist
transport exceptions or individual 502 retries.

## Request facts

Capture these from the actual response, retaining sanitized response evidence:

- Requested model, returned model/provider, provider generation ID, run ID,
  session ID, concrete request fingerprint and configuration identity.
- Start/end timestamps, elapsed time, HTTP status, retry number, error type,
  finish reason, parse/schema validation outcomes and raw answer text.
- Full reported usage, including reasoning and cached token details when
  available, and reported account cost with currency and billing source.
- Pricing snapshot reference and estimated cost separately from reported cost.
  Unknown cost is null, never zero. A free catalog price does not establish
  whether an unsuccessful request was billed. Optional later billing lookup
  can reconcile the record by generation ID.
- Image derivative, URL and content hash when available; never retain API keys
  or Authorization headers. Image hash is currently optional, so comparisons
  must distinguish identical URLs from verified identical image bytes.

Aggregate cost per completed photo across both passes and all attempts. Report
evaluation spending separately from production spending, and show unknown-cost
requests alongside known totals. Cached reuse incurs no new inference call;
retain the original call's cost without counting it again as new spending.

## Integration with the current queue

The queue tracks production work using ANALYZER_VERSION. Trial collection must
use a selected photo manifest and bypass production queue mutation; the current
--dry-run path is not that separation because main_loop still syncs the queue.
Approving a configuration and publishing its existing answers are separate
operations. A deliberate production policy/distiller change can then bump
ANALYZER_VERSION and rebuild from eligible cached sessions where possible.

Keep the approval policy separate from schema_version (reader document shape)
and analyzer_version (production reprocessing). Record policy revision and
source session IDs in metadata for each published assessment so it can be
explained without putting request history into the reader-facing DB document.

The next implementation should prove that a newer pending Gemma answer cannot
change a baseline assessment, approval allows its cached answer to participate,
revocation excludes it, and evaluation never fills gaps from another model.

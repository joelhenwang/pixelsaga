# Live provider runbook (S3-PROV-001)

Executes the bounded live sample against OpenRouter and captures
`evidence/stage3-live-v1/`. CI never runs this: the test skips
without `WORLDSIM_LIVE_SCENARIO=1` and real credentials.

## Prerequisites

- A `.env` file (never committed) with:
  `OPENROUTER_API_KEY`, `OPENROUTER_OPENAI_BASE_URL`, and
  `OPENROUTER_MODEL_NAME`.
- `WORLDSIM_LIVE_SCENARIO=1` to opt in.

Map the file into settings before running (unprefixed names stay
local to your shell):

```
set -a; source .env; set +a
export WORLDSIM_PROVIDER__ACTIVE_PROFILE=openrouter
export WORLDSIM_PROVIDER__OPENROUTER_API_KEY="$OPENROUTER_API_KEY"
export WORLDSIM_PROVIDER__OPENROUTER_BASE_URL="$OPENROUTER_OPENAI_BASE_URL"
export WORLDSIM_PROVIDER__OPENROUTER_MODEL="$OPENROUTER_MODEL_NAME"
export WORLDSIM_LIVE_SCENARIO=1
```
- A spend cap you enforce at the provider dashboard (suggested:
  $2 for the sample below; the sample is 3 phases on the stage0
  seed, roughly 20 model calls on small prompts).

## Procedure

1. Confirm the key is load-bearing, not echoed anywhere:
   `printenv | grep -c OPENROUTER` must print 1 (name only).
2. Run the sample (from the repo root):
   `uv run --project backend --group dev pytest backend/tests/test_s3_live.py -q`
3. On any provider outage, rate limit, or spend-cap warning:
   abort. The sample is resumable only by re-running; phases are
   idempotent per `derive_run_id`, so a re-run replays rather
   than duplicating.
4. Inspect `evidence/stage3-live-v1/`: every call needs a usage
   row with tokens and a cost row. Refusals or malformed outputs
   must appear as fallback beats, never as committed canon.
5. Commit the bundle (it carries a `.gitignore` exception).
   Review it for secret leakage first: no key material, no
   bearer tokens — prompts pass through `redact`, but verify.

## What the sample proves

- The OpenRouter adapter serves narrator and decision roles end
  to end (all roles go live; the bounded world keeps spend low).
- Retry semantics hold against the real endpoint (rate-limit
  responses honor `retry-after`; exhaustion degrades to
  fallback, recorded in the bundle).
- Every live call has a usage/cost row backed by the pricing
  table version in the bundle.

## What it does not prove

Text quality. S3-QUAL-001 judges the committed sample against
the rubric (continuity, perspective discipline, trope
avoidance) with a human-signed record.

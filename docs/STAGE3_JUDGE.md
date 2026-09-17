# Live-sample judge protocol (S3-QUAL-001)

Human judgment over `evidence/stage3-live-v1/` (3 phases, all
roles live). The judge may be LLM-assisted, but the record is
human-signed below; signing is a process step, not a pytest
assertion.

## Sampled phases

All three: phases 1, 2, and 3 (`calls.json` → `phases`). The
sample is small enough to judge whole.

## Rubric (pass / flag per phase, then overall)

1. **Continuity.** No contradictions with earlier beats in the
   sample (names, places, states, ongoing actions). A quiet
   "the day passes" beat passes by default; invented
   developments must cohere.
2. **Perspective discipline.** Beats reveal only what the scene
   could know. No omniscient asides, no other-owner private
   facts (beliefs, hidden states) leaking into narration.
3. **Trope avoidance.** No canned filler: ozone clichés, purple
   travelogue, moralizing codas, or repeated sentence skeletons
   across the three phases.

## Recording

Judgments live in `docs/stage3-live-judgments-v1.json`:
per-phase pass/flag with quoted evidence, plus an overall line
and the signer's name and date. A flag does not fail any gate;
it files an observation for the next quality pass.

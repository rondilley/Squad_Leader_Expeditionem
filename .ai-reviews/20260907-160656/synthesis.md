# Synthesis of the first multi-AI validation pass

Date: 2026-09-07
Bundle reviewed: `docs/VISION.md`, `docs/REQUIREMENTS.md`, `docs/SUCCESS_CRITERIA.md`. The research report, the discovery notes, the license, and the ignore file were sent as context.

Reviewers that ran: gemini (gemini-3.1-pro-preview), xai (grok-4.3), openai (gpt-5.6-terra). Mistral did not run on this account tier (HTTP 403 on the large model, HTTP 429 on the medium and small models across three tries).

Full referee report: `2026-09-07_1606_consolidated_review.md` in this folder.

## Critical contradictions

| Claim | Divergence | Resolution |
|---|---|---|
| Throughput gate (NFR-01) against the single-game bound (NFR-03, TC-10) | gemini and openai: 218 to 437 steps/s for each worker against 500 to 2,000 steps/s on one core | Give the definition of the environment step. NFR-03 becomes 15 s. Add a benchmark specification. |
| Python core (AR-05) against "no server" hot seat (FR-36) | openai: a browser cannot run a Python core | Hot seat runs against a local Python host. "No remote server". |
| Integer-only rules (NFR-05) against vector LOS (FR-28) | gemini: polygon tests want floats | Integer lattice with integer cross products. LOS cached for each board. |
| "Scenarios 1 to 3 play" against private boards | openai and xai: two products with one name | Reference mode (private layouts) and generated mode (zone-based set up areas). |

## Common items

- The MVP is more than one project (all three). Re-tiered into v0.1 to v0.4 plus a release candidate.
- Legal-command generation is the critical path (all three). v0.1 builds and measures it first.
- The model agent fallback target has no support (gemini, openai). Retries default to 2. The rate is measured, with a target only for the SaaS model.
- The 100 million step run must not be the first sign of learning (openai, with gemini on sequence). Learning ladder at 1 million and 10 million steps.
- A per-player state projection is missing (openai, gemini on client-calculated hashes). New AR-09, DR-04 rewritten, secrecy test added.

## Single-reviewer items with merit

- DR-06 inverted its meaning in the STE rewrite (openai). Corrected.
- The survey's "rules 1 to 41" for scenarios 1 to 3 (openai). Corrected to rules 1 to 27 for 1, 2, and 3A.
- The FR-34 LOS restriction decreases play quality on a 2D board (gemini). Casual mode is the default.
- TC-14 mixes geometry with taste (gemini). Divided into two criteria.
- TC-01 with one case for each rule is not conformance (openai). Conformance matrix.
- TC-18 is satisfied by a weak bot (openai). Frozen bot versions, confidence intervals.
- Five SaaS providers in the MVP (openai). One local plus one SaaS in v0.4.
- Room code, provider allowlist, prompt and log leak paths (openai). SR-03, SR-05, SR-09.
- Terms drift on "model agent" (gemini). Terms section added.
- The Rust port is not "mechanical" (openai). Vision wording softened.

## Disagreements with the reviewers

- openai on GPL-3: to send a browser bundle to a browser is conveyance in section 6, and the section 7 added permission is FSF guidance, not an invention. The survey wording is tightened. The claim stays.
- openai on missing architecture and orientation files: those are subsequent phases of the init pipeline. Not a defect.
- xai on requirements-against-vision drift: not correct for the reviewed material, but it becomes the instruction after the re-tiering.
- gemini on floats in LOS: rejected, because the project cannot prove float agreement across a Rust port and a WebAssembly build. The integer lattice has no rounding.

## Applied edits

Applied on 2026-09-07 with the annotation `AI review 20260907-160656` in each edited document:

- `docs/REQUIREMENTS.md`: full rewrite. It has tiers v0.1 to v0.4 and RC, a terms section, the two scenario modes, and the integer lattice. It has the casual mode default, the local host topology, the retry count, the step definition, and the 15 s bound. It has SR-03, SR-05, SR-09, DR-04, DR-06, AR-09, the TR-01 matrix, the scoped TR-11, and appendix B.
- `docs/SUCCESS_CRITERIA.md`: TC-01, TC-09, TC-10, TC-14 divided, TC-16, TC-18 with the ladder, TC-20, TC-29, the secrecy criterion TC-34, the counter rubric, and the scoped binding clause.
- `docs/VISION.md`: section 5.1 lists the sequence, bet 2 wording on the port, bet 3 on retries.
- `docs/2026-09-07_Squad_Leader_Digital_Edition_Research.md`: the rule boundary sentence in section 4.3 and the GPL sentence in section 6.3.

The owner's directive of 2026-09-07 on a tuned local model went into the same edit pass: FR-60 to FR-64, NFR-09, SR-10, IR-08, DR-08, AR-10, TR-12, BC-09, and TC-35 to TC-37.

## Missing research vector

None. The reviewers want design work (the architecture document), not more research. The open question on zone-based set up areas is a prototype question for v0.2.

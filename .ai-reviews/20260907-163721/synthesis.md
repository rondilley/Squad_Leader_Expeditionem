# Synthesis of the second multi-AI review (architecture), 2026-09-07 16:37

Reviewers: gemini (gemini-3.1-pro-preview), xai (grok-4.3), openai (gpt-5.6-terra). Mistral did not run, see `tasks/lessons.md`. The full referee report is `2026-09-07_1637_consolidated_review.md` in this folder. This file lists the decisions.

## Critical contradictions

| Claim | Divergence | Resolution |
|---|---|---|
| The lattice is exact enough. | gemini: replace with cube coordinates. openai: prove it or replace it with a rational system. xai: the design is sound. | Neither gemini nor xai. The lattice becomes exact: x integer, y integer in units of the square root of three. Cross products stay integers. The polygon test stays. |
| The tuned model is a year-one deliverable. | xai: move it to v0.5. openai: constrain it to a 7B or 8B profile with a smoke path. | The owner directive keeps it in v0.4. TC-36 is a measurement with no threshold. TC-37 is a gate for the 7B or 8B profile only. |
| The basic Defensive Fire Phase is correct. | gemini: it "misrepresents the rules". openai: the target identity is under-specified. | The basic method is rule 4.4 and 16.1, a phase after movement. Optional rule 16 is a sub-state. The `track_return` command fixes the target identity. |
| One harness for the four families. | xai: collapse the four families into one harness. gemini and openai: silent. | The prompted and the tuned families share one harness. The scripted and the learned families have no text view, so they stay separate. |

## Common findings

- Command ID as a list index (gemini, openai). Fixed by the decision frame and canonical payloads.
- Portage absent from v0.1 (gemini, openai). Fixed by `pickup` and `drop` in the Movement Phase.
- The legal command list is the load-bearing component (the three reviewers). Confirmed, in slices 2 and 3.
- A sub-step table for page 41 (xai, openai). Added as section 3.2.
- A traceability matrix (xai, openai). Added as Appendix B.
- The v0.1 throughput gate after scenario 1 is complete (openai, and gemini on the benchmark method). Fixed in section 14, TC-09, and `tasks/todo.md`.

## Singleton findings with merit

- The client hash in the sequence diagram against DR-04 (openai). Fixed.
- SR-10 has no enforcement (openai). Fixed by `board_source` and the fine-tune guard.
- Rally Phase for the two players, set up commands, predesignation, close combat allocation (openai). Fixed in section 3.1.
- The LOS cache is one byte and unordered against FR-28 (openai). Fixed by the split into a static table and a rule evaluator, and FR-28 now says unordered.
- `los_request` for FR-34 strict mode (gemini). Added to the protocol.
- The hierarchical command tree (gemini). Adopted as the internal shape.
- The view cost model (xai). Added to section 4.
- The zone resolution fallback (xai). Added to section 7.
- The GPU profile and the staged smoke path (openai). Added to section 9.4.
- TC-36 measures the grammar when the constraint is on for the two models (openai). TC-36 now records four metrics.
- The "two AI families" text in the vision (openai). Fixed.
- Board composition for FR-29, the victory evaluator for FR-14, the release controls for SR-06 to SR-08, the data retention for DR-07 (openai). Added.

## Disagreements with the reviewers

- gemini, cube coordinates: cube coordinates give hex-to-hex lines, not a thread against sub-hex terrain shapes. Not adopted.
- gemini, the 33 times 866 arithmetic: the lattice does not measure distance. The real defect is the vertex side test, and the exact lattice removes it.
- gemini, morale checks with a leader choice: the Q and A for rule 15.1 says the opposite for morale checks and rally. The choice exists for fire groups only.
- gemini, the grammar compile cost: no data. FR-62 keeps the three constraint options, and the harness measures.
- xai, defer the tuned model: the owner directive of 2026-09-07 (EA-9) decides this.
- xai, the LOS design is sound with no reservation: openai found two real defects in it.

## Proposed edits, applied

- `docs/ARCHITECTURE.md`: rewritten to v0.2 with annotations `<!-- AI review 20260907-163721: ... -->` at each change. Sections 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, Appendix A, and the new Appendix B.
- `docs/REQUIREMENTS.md`: FR-28 (unordered static pairs, rule evaluator with context), DR-04 (the log stores the canonical payload), SR-10 (the `board_source` tag and the fine-tune guard), NFR-09 (the 7B or 8B profile).
- `docs/SUCCESS_CRITERIA.md`: TC-09 cadence (the v0.1 gate after scenario 1), TC-36 (four metrics), TC-38, TC-39, TC-40 added, the test plan rows added.
- `docs/VISION.md`: "two AI families" to "four agent families".
- `tasks/todo.md`: slice 2 gets the decision frame, portage, set up, and TC-38. Slice 3 owns the v0.1 TC-09 gate. Slice 8 gets `board_source`. Slice 11 gets the profile, the smoke path, and TC-39. Slice 5 gets `los_request` and TC-40.

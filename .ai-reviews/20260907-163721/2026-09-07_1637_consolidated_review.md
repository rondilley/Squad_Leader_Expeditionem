# Squad_Leader_AI: Consolidated Multi-AI Architecture Review, pass two

- Synthesized by: Claude Fable 5.1, as the referee across the three reviews below
- Reviewers: gemini (gemini-3.1-pro-preview), xai (grok-4.3), openai (gpt-5.6-terra)
- Date: 2026-09-07 16:37
- Material reviewed: 13 files, 232,925 characters, 0 secrets redacted, documents only, no code
- Scope: `docs/ARCHITECTURE.md` v0.1 against `docs/REQUIREMENTS.md` v0.2, `docs/VISION.md` v0.2, and `docs/SUCCESS_CRITERIA.md` v0.2

## Bottom line

The three reviewers agree that the concept is worth building and that v0.1 is the correct first milestone. They agree that the legal-command list is the load-bearing component. They also agree that the architecture is not tight enough to code from. Two reviewers found the same defect in the command identity: a command ID as a list index cannot serve replay, traces, and training. Two reviewers found that the command model does not include portage, which rule 5.7 puts in the movement rules of v0.1. The referee confirms the two findings against the rules text and the requirements.

The verdict: apply the P0 edits below, then start slice 1.

## Validated contradictions and feasibility problems

The items are in sequence of severity. Each item names the problem, the location, the reviewers, and the resolution.

### 1. A command ID as a list index is not a replayable identity

Problem: section 8 says a command ID is an index into the legal list the host sent. DR-04, FR-60, and DR-08 store that ID in the command log and in the traces. An index changes when the list sequence changes, so a replay after a code change can apply the wrong command. Location: `ARCHITECTURE.md` sections 3, 8, 9.2, 9.3, 9.4, and 12. Reviewers: gemini (protocol brittleness) and openai (replay, traces, masks). The referee confirms it.

Resolution: a decision frame is the one artifact that the host, the trainer, the harness, the trace writer, and the replay tool share. Each legal command has a canonical payload and a command ID derived from that payload. The command log stores the payload. The client sends the frame ID and the command ID. Section 3.4 of the architecture now defines the frame.

### 2. The client sends a hash, which DR-04 forbids

Problem: DR-04 says a client sends intent only and MUST NOT send a hash. The sequence diagram in section 12 shows the client with a view hash. Location: `ARCHITECTURE.md` section 12 against `REQUIREMENTS.md` DR-04. Reviewer: openai. The referee confirms it.

Resolution: the client sends the frame ID that the host issued. The host maps the frame ID to the state it built the frame from. The client does not compute or send a state hash.

### 3. The command model does not include portage

Problem: rule 5.7 lets an infantry unit pick up or drop a support weapon at each point of its move, with the movement cost. Scenario 1 has LMG, MMG, and HMG counters. Section 3.1 moves `pickup` and `drop` to a subsequent tier, so scenario 1 is not playable as written. Location: `ARCHITECTURE.md` section 3.1 against FR-01 and rules 5.7 to 5.74. Reviewers: gemini and openai. The referee confirms it against the rules text.

Resolution: `pickup` and `drop` are Movement Phase commands in v0.1. Rule 5.73 governs the portage limit in the Advance Phase.

### 4. Section 3.1 is not complete for rules 1 to 21

Problem: the openai review lists five more gaps. Rule 4.1 gives the two players a Rally Phase, but section 3 has one active player. Rule 21 has a set up step with no commands. Rule 8.7 predesignation has no declaration window. A Defensive Fire target under rule 16.1 is a set of moved units returned to a track hex, not a hex alone. Close Combat has no allocation constraint. Reviewers: openai (the five items) and xai (the sub-step transitions for Prep Fire and Defensive Fire). The referee confirms each item against the rules text.

Resolution: section 3 now has a command window for each player in the Rally, Rout, and Close Combat Phases, in a fixed sequence. It has a Set Up Phase with `place(unit, hex)`. It has the predesignation switch as a declaration window. It has `track_return(units, hex)` for rule 16.1. It has the one-attack-for-each-unit constraint for rule 20. Section 3.2 has the sub-step table from page 41.

### 5. The LOS text overclaims

Problem: section 5 says the 1,000 by 866 lattice "changes no LOS". That is an assertion. Section 5 also says one byte for each unordered pair, but FR-28 says ordered pairs, and rule 17.7 gives the firer a choice that one byte cannot hold. Reviewers: gemini (the approximation) and openai (the assertion, the cache semantics, ordered against unordered). The referee confirms the three points.

Resolution: the lattice changes to an exact one. The x coordinate is an integer, and the y coordinate is an integer with an implicit factor of the square root of three. A cross product of two such vectors is an integer times that square root, so its sign is exact. The 866 approximation goes away. The cache splits into a static geometry table and a rule evaluator with context. FR-28 changes to "each unordered pair" for the static table. The gemini proposal of cube coordinates is not adopted, see the referee section.

### 6. SR-10 is not enforced by the design

Problem: SR-10 says the tuned model weights MUST NOT contain reference-mode board data. Section 9.4 keeps reference-mode traces on the owner's machine, but it does not stop a fine-tune from reading them. An adapter can encode a private layout. Reviewer: openai. The referee confirms it.

Resolution: each trace record has a `board_source` field with the value `generated` or `reference_private`. The fine-tune command rejects `reference_private` traces unless the owner gives an explicit local-only flag. Weights from such a run stay on the owner's machine.

### 7. The v0.1 throughput gate is measured too early

Problem: `tasks/todo.md` slice 2 measures TC-09 on a movement-only game. NFR-01 says the benchmark includes fire, morale, observation construction, and hashing. Reviewers: openai, and gemini (the benchmark must not use a legal list again across states). The referee confirms it.

Resolution: the slice 2 number is a signal. The v0.1 gate is the slice 3 number on the complete scenario 1. The benchmark plays random legal games from fresh seeds, and a legal list cache lives only inside one state.

## Concept and scope: synthesized view

All three reviewers say the concept is worth building. All three say v0.1 as a headless rules proof is the correct size. The openai review divides v0.1 into three proofs: geometry and LOS, canonical command and replay, then scenario 1. That sequence matches slices 1 to 3 in `tasks/todo.md`, so the referee keeps the slices and adds the command identity gate to slice 2.

The xai review moves the tuned model to v0.5. The owner's directive of 2026-09-07 puts the tuned model in year one, so the referee keeps it in v0.4 and makes TC-36 a measurement, not a release gate. TC-37 stays a gate for the 7B or 8B profile only.

## Critical path and leverage

The three reviewers name the same load-bearing component: the legal-command list from a deterministic state. The plan puts it in slices 2 and 3, which is correct. The openai review adds that the list is not derisked until its identity is canonical, and the referee agrees. The gemini review adds that the list is a tree (unit, action, target) and not a flat list, which matches the composed action head of the trainer. The referee adopts the tree as the internal shape and the flat enumeration as a view of the tree.

## Contested or single-reviewer findings

- Cube coordinates for LOS (gemini). Not adopted. Cube coordinates give the hexes that a line crosses. Rule 7.1 tests a thread against terrain shapes inside hexes, and cube coordinates have no sub-hex shapes. The root-three lattice above is exact and keeps the polygon test.
- The 5-second latency budget fails for a local model (gemini). Partly adopted. The gemini numbers for prompt speed are in the range of RV-6 section 4.2, and the architecture already says a local model is at the edge of the budget. No data supports the grammar compile cost claim. The referee adds prefix caching on llama-server and a size budget for the view. FR-62 keeps the three constraint options.
- Hierarchical legal commands (gemini). Adopted as the internal shape. The client and the model agent get the flat enumeration from the frame.
- `los_request` in the protocol (gemini). Adopted. FR-34 strict mode makes the host answer LOS questions, because the client has no rule logic.
- An interrupt sub-state for optional rule 16 (gemini). Adopted as a sub-state of the Movement Phase. The gemini text says the basic method "misrepresents the rules". It does not. Rule 4.4 and rule 16.1 give the basic method as a phase after movement, and optional rule 16 is the interleaved method.
- Morale checks get player input for a leader modifier (gemini). Not correct. The Q and A for rule 15.1 says a player cannot refuse the modifier of a poor leader in morale checks and rally. The choice exists for fire groups, so `group_fire` gets a leader option.
- A single harness across the four families (xai). Partly adopted. The prompted and the tuned families share one harness and differ in the model loader and the constraint. The scripted and the learned families have no text view, so one harness for the four is a name and not a simplification.
- A view cost model (xai). Adopted. Section 4 gets the cost of a view with zero, some, or all units concealed.
- A fallback when zone resolution fails (xai). Adopted. The client says that generated mode is not available for that scenario and seed and offers a new seed.
- A requirements-to-architecture matrix (xai, openai). Adopted as Appendix B.
- Board composition for FR-29 (openai). Adopted as one paragraph in section 7. A 180-degree turn is a negation of the two lattice coordinates.
- The GPU memory target and the staged smoke path for the fine-tune (openai). Adopted. The year-one profile is a 7B or 8B base, generated traces only, a fixed context length, a named LoRA or QLoRA profile, a 50-step smoke run, and an export before the full run.

## Where the reviewers were wrong or shallow

- The gemini arithmetic on the lattice (33 times 866 against 28,578.83) is not the defect. The lattice does not measure distance. The defect is that a scaled integer y can put a thread on the wrong side of a vertex, and the exact lattice removes that.
- The gemini claim that the basic Defensive Fire Phase "misrepresents the rules" reads the optional rule as the rule.
- The gemini claim about morale checks is wrong, see above.
- The xai review says that the LOS design "is sound" with no reservation. The openai review found the ordered-pair contradiction and the one-byte cache problem that xai did not see.
- The xai proposal to move the tuned model to v0.5 does not agree with the owner directive that the requirements record in Appendix B, EA-9.
- The openai byline says gpt-5.5, and the run used gpt-5.6-terra. That is a script default, not a review defect.
- No reviewer found that the rules give no Rally Phase sequence between the two players. The referee sets the phasing player first as a project ruling, recorded in the rulings data with the rule reference.

## Security posture: merged view

The threat model stays as SR-01 to SR-10 describe it: trusted-party LAN convenience, per-player views, a provider allowlist, and key redaction. The merged findings:

1. The client-side hash weakens the trust boundary (openai). Fixed by the frame ID.
2. Reference-mode data can leak through model training (openai). Fixed by the `board_source` tag and the fine-tune guard.
3. The release controls (GPL section 7 notice, source link, non-affiliation notice, release audit) are not in section 10 (openai). Added to section 10.
4. Origin checks and room codes reduce accidental joins and browser misuse. They do not stop an active attacker on the LAN. The architecture already says so, and the wording stays.

## Efficacy, performance, and acceptance gates

- TC-36 with constrained decoding on for the two models measures the grammar, not the model (openai). TC-36 now records the invalid-command rate with and without the constraint, the fallback rate, the win rate against the same scripted set, and the decision time.
- TC-09 moves to the end of slice 3 (openai). The slice 2 number stays as an early signal.
- The benchmark plays random legal games from fresh seeds (gemini).
- The PPO ladder stop points at 1 million and 10 million steps stay (openai).
- Three new criteria: TC-38 command identity replay after a deliberate shuffle of the legal list, TC-39 the fine-tune rejects reference-mode traces by default, TC-40 the LOS overlay in the client uses host geometry only.

## What everyone says is missing

- A sub-step table for page 41 (xai, openai).
- A traceability matrix from requirement to section (xai, openai).
- ADRs for the decision frame, the LOS split, and the reference trace policy (openai). Added to Appendix A.
- A victory evaluator contract for FR-14 (openai). Added to section 6.
- A statement of what NFR-02 measures (openai). Added to section 8.

## Unified remediation plan by priority

P0, before slice 1:

1. The decision frame with canonical command payloads and IDs. Touches `ARCHITECTURE.md` sections 3.4, 8, 9, and 12, and `REQUIREMENTS.md` DR-04. Retires the replay and trace identity risk.
2. Remove the client hash. Touches section 12. Retires the DR-04 contradiction.
3. The exact root-three lattice and the LOS split. Touches section 5 and FR-28. Retires the approximation claim and the cache semantics defect.
4. Complete section 3.1 for rules 1 to 21, with portage, set up, the two-player windows, predesignation, track return, and close combat allocation. Retires the "scenario 1 not playable" finding.
5. SR-10 enforcement in the trace format and the fine-tune command. Touches section 9.4 and `tasks/todo.md` slices 8 and 11.

P1, before the v0.1 sign-off:

6. The v0.1 TC-09 gate after slice 3. Touches section 14, `SUCCESS_CRITERIA.md` TC-09, and `tasks/todo.md`.
7. The victory evaluator contract. Touches section 6.
8. The generator parameter record and the zone fallback. Touches section 7.
9. The release controls in section 10.

P2, before v0.4:

10. The tuned model profile, the smoke path, and the TC-36 metrics.
11. The `los_request` message and the NFR-02 definition.
12. The view cost model.

P3, documents:

13. The vision drift "two AI families". Touches `VISION.md` section 2.
14. Appendix B, the traceability matrix.

## Proposed revised scope

v0.1 stays a headless rules proof in three slices: geometry and LOS, canonical command and replay, then scenario 1 with the throughput gate. v0.2 to RC stay as `REQUIREMENTS.md` section 0.3 lists them. The tuned model stays in v0.4 as a measured experiment.

## Open questions for the team

- O-02: the GPU model and memory decide the LoRA profile and the largest base model.
- O-06: the base model for the first fine-tune.
- The step count for each game (section 15), which sets the throughput gate again.
- The Rally Phase sequence between players, which the rules do not state. The project ruling is the phasing player first.

## Final judgment

The architecture is worth building after the P0 edits. The system stands or falls on canonical legal commands, deterministic replay, and LOS correctness. A start from the unchanged document would show the same gaps at the first integration test between the core, the host, the trainer, and the replay tool.

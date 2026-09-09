# Squad_Leader_AI: Success Criteria

Status: Draft v0.3, after the second multi-AI review
<!-- AI review 20260907-160656 and 20260907-163721: gemini, xai, openai -->
Author: Ron Dilley
Last updated: 2026-09-07
Companion documents: `VISION.md` (direction), `REQUIREMENTS.md` (the requirements with IDs), `ARCHITECTURE.md` (design)

This document says what "done" means. Each criterion is measurable. Section 3 names the test, the data source, the threshold, and the cadence for each criterion. Section 4 says what does not count as success, because earlier projects declared work complete on stub-based data.

Criterion IDs: BC business, TC technical. Each criterion names the requirement IDs it proves.

## 1. Business success criteria

The principal is the owner. The business outcomes are the owner's outcomes.

| ID | Criterion | Threshold | By when | Proves |
|---|---|---|---|---|
| BC-01 | The owner plays scenario 1 from start to finish in a browser against a scripted agent, and the game gives a victory result with its cause. | 1 complete game, no rule error, victory result given | 2027-03 | FR-01, FR-14, FR-19, FR-39 |
| BC-02 | The owner plays scenario 1 against a second person on the LAN with a room code. | 1 complete game from two browsers | 2027-06 | FR-38 |
| BC-03 | The owner plays a full game against a model agent on a local model and on one SaaS model. | 2 complete games, fallback rate recorded | 2027-06 | FR-45 to FR-48, IR-01, IR-02 |
| BC-04 | The owner reads the action log for one game and finds the rule ID, the dice, and the modifiers for each result. | 100 percent of log entries have all four fields | 2027-03 | FR-06, FR-35 |
| BC-05 | The generated boards satisfy the owner's written look rubric (TC-14). | Rubric score at or above the threshold in TC-14 | 2027-09 | FR-25, FR-30 |
| BC-06 | A learned agent has an Elo number against the scripted bots after a run of a minimum of 100 million steps. | Elo recorded in a run artifact | 2027-09 | FR-51, FR-52, NFR-01 |
| BC-09 | The owner reads one table that compares the four agent families (scripted, learned, prompted model, tuned model) on the same scenarios: win rate, invalid-command rate, decision time, and cost. | One table from one tournament run, all four families | 2027-09 | FR-63 |
| BC-07 | A future session continues the build from `VIBE_HISTORY.md`, `tasks/todo.md`, and `tasks/lessons.md` with no re-derivation of a decision. | Observed at the start of each session | Each session | MR-03, MR-04 |
| BC-08 | The project ships no Avalon Hill art, scan, layout, or rulebook text, and uses no protected brand. | Audit of the repository and the served page finds zero items | Each release | SR-07, SR-08 |

## 2. Technical success criteria

### 2.1 Rules fidelity

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-01 | The conformance corpus covers each rule family in scope with valid, invalid, boundary, and interaction cases. Each case cites its source. The corpus gives zero failures. | 0 failures. Each rule ID in scope has a minimum of the four case types. | FR-01, FR-02, TR-01 |
| TC-02 | Each official Q and A ruling for rules 1 to 27 has a conformance case that cites the ruling. | 100 percent of rulings | FR-07 |
| TC-03 | The legal-action list rejects each illegal action in a fuzz test of 10,000 random attempts with a rule ID in the message. | 0 illegal actions accepted | FR-04, FR-05 |
| TC-04 | Scenario 1 (v0.1), then scenarios 2 and 3A (v0.3), play to game end from their data files with two scripted agents in a headless run. | 100 games for each scenario, 0 unhandled errors, replay hashes agree | FR-19, FR-40 |
| TC-41 | The random construction of Game Set IV builds a scenario from a seed. It sets up on a generated board. Two scripted agents play it to a result. | 24 seeds build, 0 set up errors. 2 seeds play to a result | FR-17 |
| TC-46 | Two computer opponents play a full game in the browser, to a result or to a stated limit. The client and the host agree on the turn and the phase, each log entry names a rule, and the console gets no error. | 1 game to a result, 0 console errors, 0 log entries with no rule | FR-39, TR-07 |
| TC-45 | Rule 44 gives its effect to each of the three rural terrain types, and the generator makes a board with each of them. | Fire through a wheatfield is half strength. A shellhole gives minus one. A cliff is impassable and no cliff cuts a board in two | FR-16, FR-25 |
| TC-43 | Two to four generated boards make one playing surface, on the long edges or the short edges, with a turn of 180 degrees. A game on that surface replays. | 0 seam problems for each pair of the four board types. The hash sequence agrees | FR-24, FR-29 |
| TC-44 | A hidden unit of rule 42 is in no view of the other player, and it comes on the board on each cause of rule 42.2. | 0 hidden units in the view of the other player. Each hidden unit is on the board at the end of the game | FR-10, AR-09 |
| TC-42 | A campaign of six scenarios gives the same record from one seed. The record sets the strength and the seed of the next scenario. | 2 runs of one seed agree. A record of wins and a record of losses give different seeds | FR-17 |

### 2.2 Determinism and data integrity

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-05 | A replay of the command log gives the same state hash sequence as the live game. | 1,000 random games, 0 mismatches | FR-12, FR-13 |
| TC-06 | The same seed and command log give the same hash sequence on Windows 11 and on Linux. | 100 games, 0 mismatches | NFR-04 |
| TC-07 | The core has no float in a rules path. | Static scan of the core finds 0 float operations in rule modules | NFR-05 |
| TC-08 | Each run artifact has a manifest, a command log, an action log, and stats, and the SQLite index lists it. | 100 percent of runs in a test sweep | FR-56, FR-57, DR-05 |
| TC-38 | The test shuffles the legal list sequence, then a replay applies each command from its canonical payload. The hash sequence agrees with the live game. <!-- AI review 20260907-163721: gemini, openai --> | 100 random games, 0 mismatches after the shuffle | DR-04, FR-12, FR-13 |

### 2.3 Performance

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-09 | The throughput test gives the end-to-end environment step rate on the training workstation. It uses the frozen benchmark specification in NFR-01 on the complete scenario 1 (rules 1 to 21, fire, morale, observation build, and hashing). The benchmark plays random legal games from new seeds, and a legal list cache lives only inside one state. The slice 2 movement-only number is a signal, not the gate. <!-- AI review 20260907-163721: gemini, openai --> | A minimum of 3,500 steps/s at 8 or 16 workers, sustained 10 minutes. If below, AR-05 starts the Rust port | NFR-01, TR-04 |
| TC-10 | A headless scripted game completes in less than 15 seconds on one core. This is a sanity bound, not a derivation of TC-09. | Median of 100 games below 15 s | NFR-03 |
| TC-11 | The legal-action list for one phase returns in less than 50 ms in the browser. | p95 below 50 ms in the Playwright test | NFR-02 |
| TC-12 | A LAN move reaches the second browser in less than 500 ms. | p95 below 500 ms in the LAN test | NFR-07 |
| TC-13 | The training loop runs unattended for 24 hours. | 1 run, 0 crashes, steps/s recorded each minute | NFR-08 |

### 2.4 The look rubrics

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-14a | An automated test proves that each board from the generator satisfies the geomorphic edge rules and connects to a second board. | 100 percent of 1,000 seeds | FR-24, FR-25 |
| TC-14b | The owner scores a set of 12 boards from the generator (3 of each type) against the board rubric below. | Mean score 4 or more of 5, no board below 3 | FR-25, FR-26, FR-30 |
| TC-14c | The owner scores the counter set against the counter rubric below. | Mean score 4 or more of 5 | FR-31 |

The rubric (each item scored 1 to 5 by the owner):

1. Hex grid, center dots, and grid labels are readable at the default zoom.
2. Terrain types are identifiable at a glance without a legend: woods, stone buildings, wooden buildings, hills by level, roads, walls, hedges, grain, shell holes.
3. The color palette is in the 1977 family: flat greens, browns, grays, and yellows, with no gradients.
4. Woods and hill edges look hand-drawn, not procedural.
5. Buildings have the shapes and dimensions of the 1977 boards: long, L, T, and plus shapes for stone, small rectangles for wooden.
6. The board satisfies the geomorphic edge rules (FR-24) and connects to a second board without a seam that a person can see.
7. Counters are readable at the default zoom: values, silhouette, nationality color.
8. The board type is identifiable: a city board looks like a city, a hills board like hills.

The counter rubric (each item scored 1 to 5 by the owner):

1. The values are readable at the default zoom and at half zoom.
2. The value positions agree with the 1977 counters (firepower-range-morale for squads, morale-leadership for leaders).
3. The nationality is identifiable by color at a glance.
4. The silhouette, the colors, and the typeface are new or open-license, and a provenance record names each asset.
5. The counter reads as cardboard on the board, not as a UI widget.

### 2.5 AI behavior limits

<!-- AI review 20260907-160656: gemini, openai -->

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-15 | Each scripted agent completes 100 headless games in each of scenarios 1, 2, and 3A with 0 unhandled errors. | 0 unhandled errors | FR-44 |
| TC-16 | The model agent harness records the invalid-command rate, the retry count, the fallback rate, and the timeout rate for each model. | Recorded for each game. The SaaS model in v0.4 has a fallback rate below 20 percent. The local model rate is a measurement with no gate. | FR-47, FR-59, OR-02 |
| TC-17 | The model agent does not send an image and does not run model output as code. | Static scan and a runtime assertion | FR-48, SR-04 |
| TC-18 | The learning ladder runs. At 1 million steps the win rate against the random agent increases. At 10 million steps the win rate against the weakest versioned scripted agent increases. After 100 million steps the learned agent beats that agent. | 200 games with sides balanced, win rate above 50 percent, 95 percent confidence interval above 50 percent, scripted agent version in the artifact | FR-51, FR-52 |
| TC-19 | The Elo table has an entry for each snapshot and each scripted agent after a training run. | 100 percent of agents in the run | FR-52, OR-04 |
| TC-35 | The tournament compares the four agent families on scenarios 1, 2, and 3A with sides balanced. | 200 games for each pairing, confidence intervals reported | FR-63, AR-10 |
| TC-36 | The tuned model agent is compared against the same base model prompted on four metrics. The metrics are the invalid-command rate (constraint off and on), the fallback rate, the win rate against one scripted set, and the median decision time. <!-- AI review 20260907-163721: openai. With the constraint on for the two models, the invalid rate measures the grammar, not the model. --> | Measured on 100 games each. The four metrics are recorded. The direction of each difference is the result. No threshold. | FR-61, FR-62 |
| TC-37 | The fine-tune runs on the owner's workstation from a trace set of a minimum of 200 games, and the exported model loads on the local server. | Less than 24 hours for the year-one profile of NFR-09 (7B or 8B base). The model answers TR-06. | FR-60, FR-61, NFR-09, IR-08, TR-12 |
| TC-39 | The fine-tune command rejects a trace set that holds a `reference_private` record, unless the owner gives the local-only flag. <!-- AI review 20260907-163721: openai --> | 1 rejected run in the test, 0 reference-mode records in a default run | SR-10, FR-60 |

### 2.6 Integration completeness

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-20 | The SaaS adapter of the tier gives a JSON move that the schema accepts, from a real call. | v0.4: 1 provider. RC: 5 providers. 1 real call each, schema accepts the move | IR-02, IR-03, TR-05 |
| TC-21 | The local model client satisfies the health check and gives a JSON move that the schema accepts, from a real llama-server. | 1 real call, schema accepts the move | IR-01, TR-06 |
| TC-22 | The failover sequence moves to the next provider when one provider times out, and logs it. | 1 timeout caused by the test, 1 failover record | IR-05 |
| TC-23 | The hot seat browser test plays the first turn of scenario 1. | Playwright test gives zero failures | FR-37, TR-07 |
| TC-40 | The LOS overlay in the client comes from a host `los_request` answer, and the client bundle has no LOS geometry code. <!-- AI review 20260907-163721: gemini --> | Static scan of the client finds 0 LOS functions. The Playwright test sees 1 `los_request` for each overlay | FR-34, AR-06 |
| TC-24 | The LAN test connects two clients with a room code and plays one turn. | Test gives zero failures | FR-38, TR-08 |
| TC-34 | The secrecy test proves that each outbound message, each prompt, and each public replay holds no opponent-hidden unit, identifier, or position. | 0 disclosures across 100 games with concealment | FR-42, AR-09, TR-09 |

### 2.7 Security posture

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-25 | No key file is in git history. | `git log --all` finds 0 `*.key.txt` files | SR-01 |
| TC-26 | The key loader marks a provider unavailable when the key file and the environment variable are missing, with no exception. | 5 of 5 providers | SR-02 |
| TC-27 | The LAN host binds only to the LAN interface, rejects a client without the room code, rejects a bad origin, and limits connection tries. | 1 rejected connection, 1 rejected origin, 1 rate limit in the LAN test | SR-03 |
| TC-28 | The served page has the GPL-3 section 7 notice and the source link. | Static check of the built page | SR-06 |
| TC-29 | The repository, the built archives, the fixtures, the screenshots, and the public run artifacts hold none of these: a scan, a board layout from the 1977 boards, card text, or rulebook text. | Audit script finds 0 items that are not in `background/reference/` | SR-07, FR-27 |

### 2.8 Maintainability and observability

| ID | Criterion | Threshold | Proves |
|---|---|---|---|
| TC-30 | Each rule module and each conformance case names its rule ID. | Static scan finds 100 percent | MR-01, MR-02 |
| TC-31 | The code has no stub function, no empty return, and no substitute object in tests. | The project hook scripts give zero items on each write | MR-05 |
| TC-32 | Each model call, each training cadence, and each tournament writes its record. | Log audit of one game, one training run, one tournament | OR-01 to OR-04 |
| TC-33 | `CLAUDE.md`, `README.md`, and `VIBE_HISTORY.md` are current at the end of each session. | Session review | MR-03 |

## 3. Test plan: criterion to data

| Criterion | Test | Data source | Threshold | Cadence |
|---|---|---|---|---|
| TC-01, TC-02 | `pytest tests/conformance` | `tests/conformance/*.json` | 0 failures | Each commit |
| TC-03 | `pytest tests/fuzz/test_legal_actions.py` | Random seeds | 0 accepted illegal actions | Each commit |
| TC-04, TC-10 | `sl-cli play --headless --games 100` | Run artifacts | 0 unhandled errors, median below 15 s | Each commit |
| TC-15 | `sl-cli agents --games 100` for the gate, and `pytest tests/agents` on each commit | A run artifact with one row for each agent and scenario | 0 unhandled errors in 900 games | Each change to an agent |
| TC-05, TC-06 | `pytest tests/determinism` on Windows and Linux | Run artifacts | 0 hash mismatches | Each commit, each OS |
| TC-38 | `pytest tests/determinism/test_command_identity.py` | Run artifacts with a shuffled legal list | 0 hash mismatches | Each commit |
| TC-07, TC-30, TC-31 | Static scans in `tools/lints/` | Source tree | 0 items | Each commit |
| TC-08 | `pytest tests/artifact` | `runs/` | 100 percent | Each commit |
| TC-09 | `sl-cli bench --workers 1,8,16 --minutes 10` | Run artifact `stats.json` with the hardware manifest | 3,500 steps/s sustained | At the end of slice 3 on the complete scenario 1 (the v0.1 gate), before the first long run, and after each core change |
| TC-11, TC-23, TC-40 | Playwright `tests/browser/` and a static scan of `client/` | Browser timings, captured messages | p95 below 50 ms, test gives zero failures, 0 LOS functions in the client | Each commit |
| TC-12, TC-24, TC-27 | `pytest tests/lan` | Two clients on the loopback address, with their messages | p95 below 500 ms, and a test for each refusal | Each commit that touches the host |
| TC-34 | `pytest tests/secrecy` on each commit, and `pytest tests/secrecy -m gate` for the hundred games | Views of the two players in games of scenario 2 | 0 disclosures | Each commit that touches the host or the view |
| TC-13 | `sl-cli train --hours 24` | TensorBoard, run artifact | 0 crashes | Before each release |
| TR-10 | `pytest tests/agents/test_ppo_smoke.py -m gate` | The stats of a training run | 10,000 steps, a finite loss, a recorded rate | Each change to the trainer |
| TC-14a | `pytest tests/boards/test_geomorphic.py` | 1,000 seeds | 100 percent | Each commit |
| TC-14b, TC-14c | Owner scoring session with `sl-cli boards --write <directory> --count 12` and the counter sheet | Owner's scores in `docs/look_rubric_scores.md` | Mean 4 or more, min 3 | Each generator or art change |
| TC-16, TC-17 | `pytest tests/agents/test_model_agent.py -m integration` | Real provider calls | Rates recorded. Fallback below 20 percent for the SaaS model | Each harness change |
| TC-18, TC-19 | `sl-cli train --steps N --eval-games 200` | Run artifact, Elo table, agent versions | Win rate above 50 percent with the confidence interval above 50 percent | After each ladder rung |
| TC-35, TC-36 | `sl-cli tournament --families all --games 200 --balance-sides` | Run artifact, family table | Table complete, invalid-command rates recorded | After each fine-tune and each training run |
| TC-37 | `sl-cli traces build` then `sl-cli finetune --model <base> --lora` | Run artifact, exported model, TR-06 result | Less than 24 hours, model loads and answers | Each fine-tune |
| TC-39 | `pytest tests/agents/test_trace_guard.py` | A trace set with one `reference_private` record | 1 rejected run | Each commit that touches the trace writer or the fine-tune |
| TC-20, TC-21, TC-22 | `pytest tests/providers -m integration` | Real provider calls, key files available | 1 SaaS and 1 local real call in v0.4, 5 SaaS in RC | Each provider change, and before each release |
| TC-25, TC-28, TC-29 | `tools/audit_release.py` | git history, built page, source tree | 0 items | Before each release |
| TC-26 | `pytest tests/providers/test_keys.py` | Temporary directory with no keys | 5 unavailable, 0 unhandled errors | Each commit |
| TC-32, TC-33 | Manual log audit and session review | Logs, docs | Complete | Each session |

## 4. What does not count as success

These anti-patterns come from earlier projects in this family. Each one produced a "complete" claim that was not correct.

- A test that passes against a stub, a substitute object, or recorded data is a wiring check. It does not prove the integration. TC-20 and TC-21 must make real calls.
- "The tests pass" does not mean the game plays. TC-04 must play full games to game end.
- A conformance case that asserts the code's current output is not a conformance case. Each case must come from the rule text or an official ruling, and the case file must cite it.
- A throughput number from a synthetic environment is not TC-09. The measurement must use the real core with the real observation build.
- A generated board that the developer likes is not TC-14. The owner scores it against the written rubric.
- A learned agent that beats a random agent is not TC-18 at 100 million steps. The opponent is a versioned scripted agent, and the version is in the artifact.
- A "done" claim without a run artifact is not done. Each criterion in section 3 names its data source.
- A tuned model that wins against a scripted agent but was not compared against the same base model prompted is not TC-36. The comparison is the result.

The binding clause:

No tier or version is "shipped", "closed", or "complete" until a minimum of one real call against each external service in the tier gave data. Stub-based tests are checks of the wiring, not validation. <!-- AI review 20260907-160656: openai, scope of the clause -->

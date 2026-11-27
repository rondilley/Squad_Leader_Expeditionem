# Squad_Leader_AI: Success Criteria

Status: Draft v0.4, after the second multi-AI review, with the status of each criterion on 2026-10-28
<!-- AI review 20260907-160656 and 20260907-163721: gemini, xai, openai -->
Author: Ron Dilley
Last updated: 2026-10-28
Companion documents: `VISION.md` (direction), `REQUIREMENTS.md` (the requirements with IDs), `ARCHITECTURE.md` (design)

This document says what "done" means. Each criterion is measurable. Section 3 names the test, the data source, the threshold, and the cadence for each criterion. Section 4 says what does not count as success, because earlier projects declared work complete on stub-based data.

Criterion IDs: BC business, TC technical. Each criterion names the requirement IDs it proves.

## 0. The status of a criterion

Each criterion has one of these four status words, with the date and the evidence:

- `passed`: a run artifact or a gate record satisfies the full threshold.
- `partly`: the evidence satisfies a part of the threshold. Or a test in the suite holds the criterion, but no run artifact records the result.
- `failed`: the newest artifact shows a failure.
- `not measured`: no artifact and no test gives the result.

The evidence is a file in `gates/`, a directory in `runs/`, or an entry of `VIBE_HISTORY.md`. A date in the evidence is the date of the run.

### 0.1 The gate records

`runs/` holds the run artifacts. Git does not record that directory, because it is large and it stays on the owner's machine. `gates/` holds one small JSON summary for each gate type, and git can record it.

`python tools/summarize_gates.py` makes the summaries. It reads the newest artifact of each gate type in `runs/` and writes one file in `gates/`. It only reads `runs/`. Each summary has these items:

- the run ID, the date, and the type of the run
- the measured numbers
- the status of each criterion against the threshold of this document
- the result that the run itself recorded
- a SHA-256 hash of the artifact files

The tool calculates each status again from the numbers, because a run can record a pass on a sample that is smaller than the threshold. A summary status is `pass`, `fail`, `short` (no failure, but the sample is too small), or `measurement` (no threshold). Run the tool again after each gate run.

The seven summaries at this time:

| File | Run | Criteria | Status in the file |
|---|---|---|---|
| `gates/gate.json` | `20260924T223545Z-v01-s01-guards-counterattack` | TC-04, TC-05, TC-10, TC-38 | `pass` |
| `gates/bench.json` | `bench_nfr01_20260924_w8.json` | TC-09 | `pass` |
| `gates/boards.json` | `20260924T210252Z-tc14a-s01-guards-counterattack` | TC-14a | `pass` |
| `gates/agents.json` | `20260924T210310Z-tc15-scripted-agents` | TC-15 | `pass` |
| `gates/gauntlet.json` | `20260924T224236Z-gauntlet-v7` | none, an Elo table | `measurement` |
| `gates/tournament.json` | `20260919T060202Z-s01-guards-counterattack-v7-vs-model-local` | TC-16 | `fail` |
| `gates/train.json` | `20260917T224037Z-ppo-s01-guards-counterattack` | TC-18 | `short` |

The newest gate records are from 2026-09-24. The runs of the library, the gauntlets, and the training chains after that date are in `runs/` and in `VIBE_HISTORY.md`. The tool has no summary type for them at this time.

### 0.2 The count

On 2026-10-28 the 65 criteria have these status words: 8 `passed`, 1 `failed`, 38 `partly`, and 18 `not measured`.

## 1. Business success criteria

The principal is the owner. The business outcomes are the outcomes of the owner.

| ID | Criterion | Threshold | By when | Proves | Status |
|---|---|---|---|---|---|
| BC-01 | The owner plays a library scenario from start to finish in the 3D window against a scripted agent. The game gives a victory result with its cause. | 1 complete game, no rule error, victory result given | 2027-03 | FR-01, FR-14, FR-39, FR-66, FR-67, FR-69 | `passed`, 2026-10-27. Four games of `lib01_grain_office` against the computer go to the end, and a replay through the core agrees with each hash. Evidence: `runs/games/lib01_grain_office-1-20261027T022653-526b75.jsonl` and three more files of that day. |
| BC-02 | The owner plays a scenario against a second person on the LAN with a room code. | 1 complete game from two clients | 2027-06 | FR-38 | `not measured`. |
| BC-03 | The owner plays a full game against a model agent on a local model and on one SaaS model. | 2 complete games, fallback rate recorded | 2027-06 | FR-45 to FR-48, IR-01, IR-02 | `not measured`. The two games of `gates/tournament.json` are v7 against `model:local`, with no person. |
| BC-04 | The owner reads the action log for one game and finds the rule ID, the dice, and the modifiers for each result. | 100 percent of log entries have all four fields | 2027-03 | FR-06, FR-35 | `partly`, 2026-09-08. The browser test of slice 5 holds it (`VIBE_HISTORY.md`). No artifact records an audit of the log of the 3D window. |
| BC-05 | The generated boards satisfy the written look rubric of the owner (TC-14). | Rubric score at or above the threshold in TC-14 | 2027-09 | FR-25, FR-30 | `not measured`. |
| BC-06 | A learned agent has an Elo number against the scripted bots after a run of a minimum of 100 million steps. | Elo recorded in a run artifact | 2027-09 | FR-51, FR-52, NFR-01 | `partly`, 2026-10-26. Runs of 10 million steps record the Elo (`runs/20261026T085258Z-ppo-lib12-the-long-front/stats.json`). No run has 100 million steps. |
| BC-09 | The owner reads one table that compares the four agent families (scripted, learned, prompted model, tuned model) on the same scenarios: win rate, invalid-command rate, decision time, and cost. | One table from one tournament run, all four families | 2027-09 | FR-63 | `not measured`. |
| BC-07 | A future session continues the build from `VIBE_HISTORY.md`, `tasks/todo.md`, and `tasks/lessons.md` with no re-derivation of a decision. | Observed at the start of each session | Each session | MR-03, MR-04 | `not measured`. No record keeps this observation. |
| BC-08 | The project ships no Avalon Hill art, scan, layout, or rulebook text, and uses no protected brand. | Audit of the repository and the served page finds zero items | Each release | SR-07, SR-08 | `partly`, 2026-09-08. `tools/audit_release.py` reported zero results (`VIBE_HISTORY.md`, slice 12). No artifact records it, and no audit ran on the 3D window or the package. |
| BC-10 | A person plays a library scenario from the package, and the collector keeps the game after a replay that agrees with each hash. | 1 game in `games/` of the collector on tars, from the package | 2026-12 | FR-73 to FR-75, SR-12, DR-09 | `partly`, 2026-10-27. The local collector kept one verified game of `lib01_grain_office` with 132 commands of a person (`collected/index.jsonl`). The deploy to tars and the Linux package wait. |

## 2. Technical success criteria

### 2.1 Rules fidelity

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-01 | The conformance corpus covers each rule family in scope with valid, invalid, boundary, and interaction cases. Each case cites its source. The corpus gives zero failures. | 0 failures. Each rule ID in scope has a minimum of the four case types. | FR-01, FR-02, TR-01 | `partly`. `tests/conformance` holds it. The last count in `VIBE_HISTORY.md` is 167 cases on 2026-09-08. No run artifact. |
| TC-02 | Each official Q and A ruling for rules 1 to 27 has a conformance case that cites the ruling. | 100 percent of rulings | FR-07 | `partly`, 2026-09-07. The 22 rulings for rules 1 to 21 are in the data (`VIBE_HISTORY.md`). No record for rules 22 to 27. |
| TC-03 | The legal-action list rejects each illegal action in a fuzz test of 10,000 random attempts with a rule ID in the message. | 0 illegal actions accepted | FR-04, FR-05 | `not measured`. `tests/` has no fuzz test of 10,000 tries. |
| TC-04 | Scenario 1 (v0.1), then scenarios 2 and 3A (v0.3), play to game end from their data files with two scripted agents in a headless run. | 100 games for each scenario, 0 unhandled errors, replay hashes agree | FR-19, FR-40 | `partly`, 2026-09-24. Scenario 1 satisfied the threshold in 1,000 games (`gates/gate.json`). Scenarios 2 and 3A have 0 errors in 100 games of each agent (`gates/agents.json`), with no replay check. |
| TC-41 | The random construction of Game Set IV builds a scenario from a seed. It sets up on a generated board. Two scripted agents play it to a result. | 24 seeds build, 0 set up errors. 2 seeds play to a result | FR-17 | `partly`. `tests/campaign` holds it. No run artifact. |
| TC-46 | Two computer opponents play a full game in the 3D window, to a result or to a stated limit. The window and the host agree on the turn and the phase, each log entry names a rule, and the window gives no error. | 1 game to a result, 0 errors, 0 log entries with no rule | FR-39, FR-66, TR-07 | `partly`, 2026-09-08. The browser version held (`VIBE_HISTORY.md`, slice 17). No gate run of the 3D window is in this tree. |
| TC-45 | Rule 44 gives its effect to each of the three rural terrain types, and the generator makes a board with each of them. | Fire through a wheatfield is half strength. A shellhole gives minus one. A cliff is impassable and no cliff cuts a board in two | FR-16, FR-25 | `partly`, 2026-09-08. `tests/engine/test_rural_terrain.py` holds it (`VIBE_HISTORY.md`, slice 16). No run artifact. |
| TC-43 | Two to four generated boards make one playing surface, on the long edges or the short edges, with a turn of 180 degrees. A game on that surface replays. | 0 seam problems for each pair of the four board types. The hash sequence agrees | FR-24, FR-29 | `partly`, 2026-09-08. `tests/boards/test_composition.py` holds it. No run artifact. |
| TC-44 | A hidden unit of rule 42 is in no view of the other player, and it comes on the board on each cause of rule 42.2. | 0 hidden units in the view of the other player. Each hidden unit is on the board at the end of the game | FR-10, AR-09 | `partly`, 2026-09-08. `tests/engine/test_hidden_placement.py` and `tests/secrecy` hold it. No run artifact. |
| TC-42 | A campaign of six scenarios gives the same record from one seed. The record sets the strength and the seed of the next scenario. | 2 runs of one seed agree. A record of wins and a record of losses give different seeds | FR-17 | `partly`. `tests/campaign/test_campaign_run.py` holds it. The artifact `runs/20260908T153309Z-campaign-42` is one run. |

### 2.2 Determinism and data integrity

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-05 | A replay of the command log gives the same state hash sequence as the live game. | 1,000 random games, 0 mismatches | FR-12, FR-13 | `passed`, 2026-09-24, `gates/gate.json`: 1,000 games, 0 mismatches. |
| TC-06 | The same seed and command log give the same hash sequence on Windows 11 and on Linux. | 100 games, 0 mismatches | NFR-04 | `not measured`. |
| TC-07 | The core has no float in a rules path. | Static scan of the core finds 0 float operations in rule modules | NFR-05 | `not measured`. The tree has no `tools/lints/`. |
| TC-08 | Each run artifact has a manifest, a command log, an action log, and stats, and the SQLite index lists it. | 100 percent of runs in a test sweep | FR-56, FR-57, DR-05 | `partly`. `tests/artifact` holds it. No sweep artifact. |
| TC-38 | The test shuffles the legal list sequence, then a replay applies each command from its canonical payload. The hash sequence agrees with the live game. <!-- AI review 20260907-163721: gemini, openai --> | 100 random games, 0 mismatches after the shuffle | DR-04, FR-12, FR-13 | `passed`, 2026-09-24, `gates/gate.json`: 100 games, 0 mismatches. |

### 2.3 Performance

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-09 | The throughput test gives the end-to-end environment step rate on the training workstation. It uses the frozen benchmark specification in NFR-01 on the complete scenario 1 (rules 1 to 21, fire, morale, observation build, and hashing). The benchmark plays random legal games from new seeds, and a legal list cache lives only inside one state. The slice 2 movement-only number is a signal, not the gate. <!-- AI review 20260907-163721: gemini, openai --> | A minimum of 3,500 steps/s at 8 or 16 workers, sustained 10 minutes. If below, AR-05 starts the Rust port | NFR-01, TR-04 | `partly`, 2026-09-24, `gates/bench.json`: 9,279.2 steps/s at 8 workers for 600 s. The run was on a Linux host with 12 processors and not on the Windows workstation. |
| TC-10 | A headless scripted game completes in less than 15 seconds on one core. This is a sanity bound, not a derivation of TC-09. | Median of 100 games below 15 s | NFR-03 | `passed`, 2026-09-24, `gates/gate.json`: median 0.221 s. |
| TC-11 | The legal-action list for one phase returns in less than 50 ms in the browser. | p95 below 50 ms in the Playwright test | NFR-02 | `partly`, 2026-09-08. The browser test held it (`VIBE_HISTORY.md`, slice 5). The browser client of this tree is older, and no artifact records the time. |
| TC-12 | A LAN move reaches the second client in less than 500 ms. | p95 below 500 ms in the LAN test | NFR-07 | `partly`. `tests/lan` holds it on the loopback address. No run artifact. |
| TC-13 | The training loop runs unattended for 24 hours. | 1 run, 0 crashes, steps/s recorded each minute | NFR-08 | `not measured`. No training run of 24 hours is in `runs/`. |

### 2.4 The look rubrics

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-14a | An automated test proves that each board from the generator satisfies the geomorphic edge rules and connects to a second board. | 100 percent of 1,000 seeds | FR-24, FR-25 | `passed`, 2026-09-24, `gates/boards.json`: 1,000 boards of the four types, 0 failures. |
| TC-14b | The owner scores a set of 12 boards from the generator (3 of each type) against the board rubric below. | Mean score 4 or more of 5, no board below 3 | FR-25, FR-26, FR-30 | `not measured`. The tree has no `docs/look_rubric_scores.md`. |
| TC-14c | The owner scores the counter set against the counter rubric below. | Mean score 4 or more of 5 | FR-31 | `not measured`. |

The rubric (the owner gives each item a score of 1 to 5):

1. Hex grid, center dots, and grid labels are readable at the default zoom.
2. Terrain types are identifiable at a glance without a legend: woods, stone buildings, wooden buildings, hills by level, roads, walls, hedges, grain, shell holes.
3. The color palette is in the 1977 family: flat greens, browns, grays, and yellows, with no gradients.
4. Woods and hill edges look hand-drawn, not procedural.
5. Buildings have the shapes and dimensions of the 1977 boards: long, L, T, and plus shapes for stone, small rectangles for wooden.
6. The board satisfies the geomorphic edge rules (FR-24) and connects to a second board without a seam that a person can see.
7. Counters are readable at the default zoom: values, silhouette, nationality color.
8. The board type is identifiable: a city board looks like a city, a hills board like hills.

The counter rubric (the owner gives each item a score of 1 to 5):

1. The values are readable at the default zoom and at half zoom.
2. The value positions agree with the 1977 counters (firepower-range-morale for squads, morale-leadership for leaders).
3. The nationality is identifiable by color at a glance.
4. The silhouette, the colors, and the typeface are new or open-license, and a provenance record names each asset.
5. The counter reads as cardboard on the board, not as a UI widget.

### 2.5 AI behavior limits

<!-- AI review 20260907-160656: gemini, openai -->

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-15 | Each scripted agent completes 100 headless games in each of scenarios 1, 2, and 3A with 0 unhandled errors. | 0 unhandled errors | FR-44 | `passed`, 2026-09-24, `gates/agents.json`: agents v0 to v7 on scenarios 1, 2, 3A, and 4, 3,200 games, 0 errors. |
| TC-16 | The model agent harness records four rates for each model: invalid commands, retries, fallbacks, and timeouts. It also records the count of decisions where the cycle guard held a command back. | Recorded for each game, in the tournament and in the gauntlet. The SaaS model in v0.4 has a fallback rate below 20 percent. The local model rate is a measurement with no gate. | FR-47, FR-59, FR-65, OR-02 | `failed`, 2026-09-19, `gates/tournament.json`: the run has no harness counters. |
| TC-17 | The model agent does not send an image and does not run model output as code. | Static scan and a runtime assertion | FR-48, SR-04 | `partly`, 2026-09-08. `tests/agents/test_model_agent.py` holds it. No run artifact. |
| TC-18 | The learning ladder runs. At 1 million steps the win rate against the random agent increases. At 10 million steps the win rate against the weakest versioned scripted agent increases. After 100 million steps the learned agent beats that agent. | 200 games with sides balanced, win rate above 50 percent, 95 percent confidence interval above 50 percent, scripted agent version in the artifact | FR-51, FR-52 | `partly`. The 1 million step rung is short: 20 games for each opponent (`gates/train.json`, 2026-09-17). The 10 million step chunks of the library have v7 gates of 200 games (`VIBE_HISTORY.md`, 2026-10-21). No run has 100 million steps. |
| TC-19 | The Elo table has an entry for each snapshot and each scripted agent after a training run. | 100 percent of agents in the run | FR-52, OR-04 | `passed`, 2026-10-26, `runs/20261026T085258Z-ppo-lib12-the-long-front/stats.json`: the learner and each scripted opponent have an Elo. |
| TC-35 | The tournament compares the four agent families on scenarios 1, 2, and 3A with sides balanced. | 200 games for each pairing, confidence intervals reported | FR-63, AR-10 | `not measured`. |
| TC-36 | The tuned model agent is compared against the same base model prompted on four metrics. The metrics are the invalid-command rate (constraint off and on), the fallback rate, the win rate against one scripted set, and the median decision time. <!-- AI review 20260907-163721: openai. With the constraint on for the two models, the invalid rate measures the grammar, not the model. --> | Measured on 100 games each. The four metrics are recorded. The direction of each difference is the result. No threshold. | FR-61, FR-62 | `not measured`. |
| TC-37 | The fine-tune runs on the owner's workstation from a trace set of a minimum of 200 games, and the exported model loads on the local server. | Less than 24 hours for the year-one profile of NFR-09 (7B or 8B base). The model answers TR-06. | FR-60, FR-61, NFR-09, IR-08, TR-12 | `not measured`. |
| TC-39 | The fine-tune command rejects a trace set that holds a `reference_private` record, unless the owner gives the local-only flag. <!-- AI review 20260907-163721: openai --> | 1 rejected run in the test, 0 reference-mode records in a default run | SR-10, FR-60 | `partly`, 2026-09-08. `tests/agents/test_trace_guard.py` holds it. No run artifact. |

### 2.6 Integration completeness

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-20 | The SaaS adapter of the tier gives a JSON move that the schema accepts, from a real call. | v0.4: 1 provider. RC: 5 providers. 1 real call each, schema accepts the move | IR-02, IR-03, TR-05 | `partly`, 2026-09-08. The v0.4 threshold held with OpenAI. For RC, 3 of 5 providers gave a move (`VIBE_HISTORY.md`, slices 10 and 12). |
| TC-21 | The local model client satisfies the health check and gives a JSON move that the schema accepts, from a real llama-server. | 1 real call, schema accepts the move | IR-01, TR-06 | `partly`, 2026-09-19. `model:local` played 2 games against v7 (`gates/tournament.json`). No record of the TR-06 test. |
| TC-22 | The failover sequence moves to the next provider when one provider times out, and logs it. | 1 timeout caused by the test, 1 failover record | IR-05 | `partly`, 2026-09-08. `tests/providers` holds it. No run artifact. |
| TC-23 | The hot seat browser test plays the first turn of scenario 1. | Playwright test gives zero failures | FR-37, TR-07 | `partly`, 2026-09-08. The test held at slice 5. The browser client of this tree is older, and 28 tests of its tables fail. |
| TC-40 | The LOS overlay in the client comes from a host `los_request` answer, and the client bundle has no LOS geometry code. <!-- AI review 20260907-163721: gemini --> | Static scan of the client finds 0 LOS functions. The Playwright test sees 1 `los_request` for each overlay | FR-34, AR-06 | `partly`, 2026-09-08. The browser test and the static scan held it at slice 5. No run artifact. |
| TC-24 | The LAN test connects two clients with a room code and plays one turn. | Test gives zero failures | FR-38, TR-08 | `partly`. `tests/lan` holds it. No run artifact. |
| TC-34 | The secrecy test proves that each outbound message, each prompt, and each public replay holds no opponent-hidden unit, identifier, or position. | 0 disclosures across 100 games with concealment | FR-42, AR-09, TR-09 | `partly`, 2026-09-08. `pytest tests/secrecy -m gate` played 100 games of scenario 2 with 0 disclosures (`VIBE_HISTORY.md`, slice 7). No run artifact. |

### 2.7 Security posture

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-25 | No key file is in git history. | `git log --all` finds 0 `*.key.txt` files | SR-01 | `partly`, 2026-09-08. The release audit reported zero results. No artifact records it. |
| TC-26 | The key loader marks a provider unavailable when the key file and the environment variable are missing, with no exception. | 5 of 5 providers | SR-02 | `partly`. `tests/providers/test_keys.py` holds it. No run artifact. |
| TC-27 | The LAN host binds only to the LAN interface, rejects a client without the room code, rejects a bad origin, and limits connection tries. | 1 rejected connection, 1 rejected origin, 1 rate limit in the LAN test | SR-03 | `partly`. `tests/lan` holds it. No run artifact. |
| TC-28 | The served page has the GPL-3 section 7 notice and the source link. | Static check of the built page | SR-06 | `partly`, 2026-09-08. The release audit reported zero results. No artifact records it. |
| TC-29 | The repository, the built archives, the fixtures, the screenshots, and the public run artifacts hold none of these: a scan, a board layout from the 1977 boards, card text, or rulebook text. | Audit script finds 0 items that are not in `background/reference/` | SR-07, FR-27 | `partly`, 2026-09-08. The release audit reported zero results. No audit ran on the package archive. |

### 2.8 Maintainability and observability

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-30 | Each rule module and each conformance case names its rule ID. | Static scan finds 100 percent | MR-01, MR-02 | `not measured`. The tree has no `tools/lints/`. |
| TC-31 | The code has no stub function, no empty return, and no substitute object in tests. | The project hook scripts give zero items on each write | MR-05 | `not measured`. The hooks run on each write, and no record keeps their results. |
| TC-32 | Each model call, each training cadence, and each tournament writes its record. | Log audit of one game, one training run, one tournament | OR-01 to OR-04 | `not measured`. |
| TC-33 | `CLAUDE.md`, `README.md`, and `VIBE_HISTORY.md` are current at the end of each session. | Session review | MR-03 | `not measured`. No record keeps the review. |

### 2.9 The 3D window, the library, the farm, the package, and the collection

| ID | Criterion | Threshold | Proves | Status |
|---|---|---|---|---|
| TC-47 | Each library scenario is balanced: v7 against v7 gives the first side 45 to 55 percent in 1,600 games, and the notes of the scenario give the seeds and the result. | 12 of 12 slots in the band | FR-69, FR-70 | `passed`, 2026-10-17 and 2026-10-18. The 12 results are 46.6 to 53.0 percent. Evidence: the `library` artifacts in `runs/` from `20261017T011201Z-library-l01-s9` to `20261018T143547Z-library-l12-s1-10`. |
| TC-48 | v3, v6, and v7 each play 4 games of each library scenario against themselves to the end, and each card sentence agrees with the scenario. | 12 of 12 games for each slot with no stall and no repeat. `tests/library` gives zero failures | FR-69, FR-71 | `partly`, 2026-10-18. Each slot gave 12 of 12 games (`VIBE_HISTORY.md`, 2026-10-17 and 2026-10-18). `tests/library` holds the card checks. No run artifact records the 12 games. |
| TC-49 | A run on the farm gives the same result list as the same run on one machine. A host refuses a client with an incorrect key, and a client refuses a host with different code. The host refuses a learned agent and a model agent. | 0 differences. 1 refusal of each type in the test | FR-72, SR-11, AR-11 | `partly`. `tests/farm` holds it. No run artifact compares a farm run with a run on one machine. |
| TC-50 | `tools/package.py` builds the package on Windows and on Linux. The package has no torch, no numpy, and no key file. The packaged game renders a board offscreen. | 2 of 2 systems | FR-73 | `partly`, 2026-10-27. The Windows package was built, and it rendered a `lib05` board offscreen (`VIBE_HISTORY.md`). The Linux package is not built. |
| TC-51 | The collector refuses an upload with a bad MAC, an expired time, a nonce that it saw, or an unknown key. It keeps a game in `games/` when the replay agrees with each hash, and in `unverified/` when not. | 1 refusal of each type, 1 game in each folder, in the test | FR-75, SR-12, SR-13, DR-09 | `partly`, 2026-10-27. `tests/collect/test_collect.py` holds the refusal of a false key, a revoked key, and a second send, and the replay check. One real game is in `collected/games/` with its line in `collected/index.jsonl`. |
| TC-52 | A person plays a full game of a library scenario with the mouse in the 3D window, to a result. The window opens offscreen in the gate. | 1 game to a result, 0 errors | FR-66, FR-67, FR-68, TR-13 | `partly`, 2026-10-27. The games of the owner in `runs/games/` go to a result (BC-01). The mouse gate of the 3D window is not in this tree. |
| TC-53 | The launcher shows the consent question one time, sends nothing without consent, and lists the 12 library scenarios. | `tests/window/test_launcher.py` gives zero failures | FR-74, FR-75 | `partly`, 2026-10-27. `tests/window/test_launcher.py` holds it (5 tests). No run artifact. |

## 3. Test plan: criterion to data

| Criterion | Test | Data source | Threshold | Cadence |
|---|---|---|---|---|
| TC-01, TC-02 | `pytest tests/conformance` | `tests/conformance/*.json` | 0 failures | Each commit |
| TC-03 | `pytest tests/fuzz/test_legal_actions.py` | Random seeds | 0 accepted illegal actions | Each commit |
| TC-04, TC-05, TC-10, TC-38 | `sl-cli gate` for the gate, then `python tools/summarize_gates.py` | The run artifact, `gates/gate.json` | 0 unhandled errors, 0 mismatches, median below 15 s | Each change to the core |
| TC-15 | `sl-cli agents --games 100` for the gate, and `pytest tests/agents` on each commit | A run artifact with one row for each agent and scenario, `gates/agents.json` | 0 unhandled errors | Each change to an agent |
| TC-05, TC-06 | `pytest tests/determinism` on Windows and Linux | Run artifacts | 0 hash mismatches | Each commit, each OS |
| TC-38 | `pytest tests/determinism/test_command_identity.py` | Run artifacts with a shuffled legal list | 0 hash mismatches | Each commit |
| TC-07, TC-30, TC-31 | Static scans in `tools/lints/` | Source tree | 0 items | Each commit |
| TC-08 | `pytest tests/artifact` | `runs/` | 100 percent | Each commit |
| TC-09 | `sl-cli bench --workers 1,8,16 --minutes 10` | Run artifact `stats.json` with the hardware manifest, `gates/bench.json` | 3,500 steps/s sustained | Before the first long run, and after each core change |
| TC-11, TC-23, TC-40 | Playwright `tests/browser/` and a static scan of `client/` | Browser timings, captured messages | p95 below 50 ms, test gives zero failures, 0 LOS functions in the client | Each commit |
| TC-12, TC-24, TC-27 | `pytest tests/lan` | Two clients on the loopback address, with their messages | p95 below 500 ms, and a test for each refusal | Each commit that touches the host |
| TC-34 | `pytest tests/secrecy` on each commit, and `pytest tests/secrecy -m gate` for the hundred games | Views of the two players in games of scenario 2 | 0 disclosures | Each commit that touches the host or the view |
| TC-13 | `sl-cli train --hours 24` | TensorBoard, run artifact | 0 crashes | Before each release |
| TR-10 | `pytest tests/agents/test_ppo_smoke.py -m gate` | The stats of a training run | 10,000 steps, a finite loss, a recorded rate | Each change to the trainer |
| TC-14a | `sl-cli boards --count 1000`, and `pytest tests/boards/test_geomorphic.py` | 1,000 seeds, `gates/boards.json` | 100 percent | Each commit |
| TC-14b, TC-14c | Owner scoring session with `sl-cli boards --write <directory> --count 12` and the counter sheet | The scores of the owner in `docs/look_rubric_scores.md` | Mean 4 or more, min 3 | Each generator or art change |
| TC-16, TC-17 | `pytest tests/agents/test_model_agent.py -m integration` | Real provider calls | Rates recorded. Fallback below 20 percent for the SaaS model | Each harness change |
| TC-18, TC-19 | `sl-cli train --steps N --eval-games 200` | Run artifact, Elo table, agent versions, `gates/train.json` | Win rate above 50 percent with the confidence interval above 50 percent | After each ladder rung |
| TC-35, TC-36 | `sl-cli tournament --families all --games 200 --balance-sides` | Run artifact, family table | Table complete, invalid-command rates recorded | After each fine-tune and each training run |
| TC-37 | `sl-cli traces build` then `sl-cli finetune --model <base> --lora` | Run artifact, exported model, TR-06 result | Less than 24 hours, model loads and answers | Each fine-tune |
| TC-39 | `pytest tests/agents/test_trace_guard.py` | A trace set with one `reference_private` record | 1 rejected run | Each commit that touches the trace writer or the fine-tune |
| TC-20, TC-21, TC-22 | `pytest tests/providers -m integration` | Real provider calls, key files available | 1 SaaS and 1 local real call in v0.4, 5 SaaS in RC | Each provider change, and before each release |
| TC-25, TC-28, TC-29 | `tools/audit_release.py` | git history, built page, source tree, package archive | 0 items | Before each release |
| TC-26 | `pytest tests/providers/test_keys.py` | Temporary directory with no keys | 5 unavailable, 0 unhandled errors | Each commit |
| TC-32, TC-33 | Manual log audit and session review | Logs, docs | Complete | Each session |
| TC-41 | `pytest tests/campaign/test_points_and_draws.py`, and `sl-cli campaign --draw 24` | 24 seeds, two games of scripted agents | 24 builds, 0 set up errors, 2 results | Each change to `slcampaign` |
| TC-42 | `pytest tests/campaign/test_campaign_run.py`, and `sl-cli campaign --seed N` two times | Two campaign records of one seed | The records agree. Wins and losses give different seeds | Each change to `slcampaign` |
| TC-43 | `pytest tests/boards/test_composition.py` | Compositions of the four board types, a replay of a game on one | 0 seam problems, hash sequence agrees | Each change to `slboards/compose.py` |
| TC-44 | `pytest tests/engine/test_hidden_placement.py tests/secrecy` | Views of the two players in a game with hidden placement | 0 hidden units in the other view | Each change to rule 42 or the view |
| TC-45 | `pytest tests/engine/test_rural_terrain.py tests/boards` | Fire results, generated hills and rural boards | The three effects, 0 boards cut in two | Each change to rule 44 or the generator |
| TC-46 | A gate in `tests/window3d` that plays two computer opponents to the end offscreen. This gate is not written at this time | The log of the host, the frames of the window | 1 result, 0 errors, 0 log entries with no rule | Each change to the window or the host protocol |
| TC-47 | `sl-cli library search` on the farm for each slot | The `library-search` artifact in `runs/`, the notes of the scenario file | 45 to 55 percent in 1,600 games | Each change to a slot, the rules, or v7 |
| TC-48 | `sl-cli library check`, and `pytest tests/library` | 12 games for each slot, the card text | 12 of 12 games, 0 failures | Each change to a slot or the card writer |
| TC-49 | `pytest tests/farm`, and one gauntlet with and without `--remote` | Two artifacts of one gauntlet | 0 differences, each refusal | Each change to `slfarm` |
| TC-50 | `python tools/package.py` on Windows and on Linux, then the packaged `window3d --screenshot` | `dist/`, the picture | 2 packages, no excluded module, no key file | Before each release |
| TC-51 | `pytest tests/collect`, and `sl-cli collect send` from the package to the collector | `games/`, `unverified/`, `index.jsonl` of the collector | Each refusal, 1 game in `games/` | Each change to `slcollect` or the save file |
| TC-52 | A mouse gate of the 3D window offscreen, and the games of the owner | The save file of each game, replayed through the core | 1 game to a result, 0 errors | Each change to the play input |
| TC-53 | `pytest tests/window/test_launcher.py` | The launcher model with a temporary data directory | 0 failures | Each change to the launcher |

## 4. What does not count as success

These anti-patterns come from earlier projects in this family. Each one produced a "complete" claim that was not correct.

- A test that passes against a stub, a substitute object, or recorded data is a wiring check. It does not prove the integration. TC-20 and TC-21 must make real calls.
- "The tests pass" does not mean the game plays. TC-04 must play full games to game end.
- A conformance case that asserts the current output of the code is not a conformance case. Each case must come from the rule text or an official ruling, and the case file must cite it.
- A throughput number from a synthetic environment is not TC-09. The measurement must use the real core with the real observation build.
- A generated board that the developer likes is not TC-14. The owner scores it against the written rubric.
- A learned agent that beats a random agent is not TC-18 at 100 million steps. The opponent is a versioned scripted agent, and the version is in the artifact.
- A "done" claim without a run artifact is not done. Each criterion in section 3 names its data source.
- A tuned model that wins against a scripted agent but was not compared against the same base model prompted is not TC-36. The comparison is the result.
- A balance result of a screen of 100 games is not TC-47. The random variation of 100 games is approximately 10 points, so the result comes from 1,600 games.
- A game that the collector keeps in `unverified/` is not TC-51 or BC-10. The replay must give each recorded hash.

The binding clause:

No tier or version is "shipped", "closed", or "complete" until a minimum of one real call against each external service in the tier gave data. Stub-based tests are checks of the wiring, not validation. <!-- AI review 20260907-160656: openai, scope of the clause -->

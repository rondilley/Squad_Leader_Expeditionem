# tasks/todo.md - Squad_Leader_AI

Per `.claude/claude-base.md` ("Task Management"): plans for non-trivial work live here. Each plan is a checkable list. Mark items complete as work progresses. Add a review section when a slice is done.

---

## 2026-09-07 - Year-one build plan in vertical slices

Goal: the tiers in `docs/REQUIREMENTS.md` section 0.3, in sequence, with the gates in `docs/SUCCESS_CRITERIA.md`. The design is `docs/ARCHITECTURE.md`.

Principle: each slice gives real, working, tested code. No scaffolding-only commits, no empty modules, no stubs, no substitute objects in tests. The repository at the end of slice N runs and its tests give zero failures. Slice N+1 extends it. A slice is complete only when its gate has a run artifact.

<!-- AI review 20260907-163721: slices 2, 3, 5, 8, and 11 changed. See docs/ARCHITECTURE.md v0.2 and .ai-reviews/20260907-163721/synthesis.md. -->

### v0.1: headless rules proof

#### Slice 1: geometry, boards, and line of sight

- [x] `pyproject.toml` with the real dependencies of this slice only (pytest, hypothesis).
- [x] `src/slcore/geometry.py`: the exact lattice (x integer, y an integer with an implicit factor of the square root of three, hex side 2 units), hex coordinates A1 to GG10 with half hexes, neighbors, distance, and the segment-against-polygon test with integer cross products.
- [x] `src/slcore/state.py`: `Board` and `Hex` with the fields of DR-03 and the terrain polygons.
- [x] `src/sldata/tables/terrain.json` with the terrain modifiers and movement costs from RV-1 section 7 and the rules text, with provenance notes.
- [x] `src/slcore/rules/r07_los.py`: rules 7.1 to 7.9 on the lattice, with the two tie breaks (7.1 and 17.7).
- [x] `src/slcore/los_cache.py`: the static per-board thread table for each unordered pair, with the two threads for a segment along a hexside.
- [x] `src/slcore/los_eval.py`: the rule evaluator with the firer as the context (hexside choice, dynamic hindrances, penetration direction).
- [x] `tests/los/`: property tests for symmetry, adjacency, and blind hexes (TR-03). Conformance cases for the LOS examples in rules 7.4, 7.7, and 17.5, each with the rule citation.
- [x] A hand-written 10 by 10 test board fixture (not a 1977 layout) for the tests.

Gate: TR-03 gives zero failures. The LOS conformance cases give zero failures. `tasks/lessons.md` records each lattice edge case that the rules did not answer.

Done 2026-09-07: 43 tests, 0 failures (`tests/los/`). The lattice edge cases are in `tasks/lessons.md`.

#### Slice 2: state, phases, the decision frame, movement, and the first throughput number

- [x] `src/slcore/state.py`: `State`, `Unit`, `Stack`, the counters of scenario 1 (German 4-6-7, Russian 4-4-7, 6-2-8, leaders, LMG, MMG, HMG) from `src/sldata/counters/`.
- [x] `src/slcore/phases.py`: the Set Up Phase and the eight-phase state machine with the sub-step table of ARCHITECTURE section 3.2. The Rally and Rout Phases have the two-player windows.
- [x] `src/slcore/commands.py`: the command payloads, the command tree, and the legal list for the Set Up, Movement, Rout, and Advance Phases, with `pickup` and `drop` (rules 5.7 to 5.74).
- [x] `src/slcore/frame.py`: the decision frame, the canonical payload bytes (sorted-key JSON, no white space), the SHA-256 command ID, the frame ID, and a golden test of ten payloads.
- [x] `src/sldata/rulings/project.json`: the project rulings with their causes, first the Rally Phase player sequence.
- [x] `src/slcore/rules/r05_movement.py` and `r06_stacking.py`: rules 5.1 to 5.76 and 6.1 to 6.3, including portage and the leader bonus.
- [x] `src/slcore/rng.py`: xoshiro128** with the golden vector test.
- [x] `src/slcore/hashing.py`: the state hash of the full state, the phase, the sub-step, and the switches.
- [x] `src/slagents/scripted/v0.py`: an agent that moves to the objective and ends phases.
- [x] `src/slcli/play.py`: a headless movement-only game from the command line, with the command log of canonical payloads (DR-04).
- [x] `tests/determinism/`: random legal games from many seeds, replay, compare the last hash (TR-02). `test_command_identity.py` shuffles the legal list and replays (TC-38).
- [x] `src/slcli/bench.py` and `tests/bench/`: the throughput test with the benchmark specification of NFR-01, one worker and then 8 and 16. Random legal games from new seeds, and a legal list cache only inside one state.

Gate: TC-05 (replay hashes agree), TC-38 (the shuffled replay agrees), and the first TC-09 number in a run artifact, with the hardware manifest. The slice 2 number is a signal on a movement-only game, not the v0.1 gate. If it is far below 3,500 steps/s at 8 or 16 workers, record the number and the cause in `VIBE_HISTORY.md` before slice 3.

Done 2026-09-07: 94 tests, 0 failures. TC-05 on 24 seeds, TC-38 on 7 seeds. The RNG golden vector and the command ID table come from JavaScript ports run with Node. The slice 2 throughput number is in `VIBE_HISTORY.md`.

#### Slice 3: fire, morale, close combat, scenario 1, and the v0.1 throughput gate

- [x] `src/sldata/tables/ift.json`, `close_combat.json`, `support_weapons.json` from RV-1 section 7 with provenance notes.
- [x] `src/slcore/rules/r08_fire.py` to `r11_terrain.py`: rules 8 to 11, fire groups with `group_leader` (Q and A 15.1), the two predesignation methods of rule 8.7 as a switch, the four firepower modifiers, the terrain modifiers.
- [x] `src/slcore/rules/r12_morale.py`, `r13_rout.py`, `r14_rally.py`, `r15_leadership.py`: rules 12 to 15.
- [x] `src/slcore/rules/r16_defensive_fire.py`: rule 16 with the track of moved units, `track_return`, and the return to the end position after each group (rules 16.1 to 16.5).
- [x] `src/slcore/rules/r17_mg.py`: rule 17, machine gun penetration along the LOS.
- [x] `src/slcore/rules/r18_fate.py`, `r19_procedures.py`, `r20_close_combat.py`: rules 18 to 20, with the two declaration windows and the one-attack-for-each-unit constraint (rule 20.4), and the second project ruling (the declaration sequence).
- [x] `src/sldata/rulings/qa.json`: the Q and A rulings for rules 1 to 21 from the rulebook pages 27 to 29.
- [x] `src/sldata/scenarios/s01_guards_counterattack.json`: the force lists, the set up areas in the two forms, the turn count, and the victory conditions of scenario 1 in the project's own words.
- [x] `src/slcore/rules/victory.py`: the victory evaluator with the typed condition records of ARCHITECTURE section 6, for scenario 1.
- [x] `src/slagents/scripted/v1.py`: fire at the best-odds target, move to cover and the objective, rout to cover.
- [x] `tests/conformance/`: the conformance matrix of TR-01 for rules 1 to 21, each case with its citation.
- [x] A first generated city fixture from a minimal `src/slboards/generator.py` (edge pass and a building placement pass only), for the headless games.

Gate: TC-01 for rules 1 to 21, TC-04 (100 headless games of scenario 1, zero unhandled errors, replay hashes agree), TC-10, and TC-09 on the complete scenario 1. This TC-09 number is the v0.1 gate. If it is below 3,500 steps/s at 8 or 16 workers, open the Rust port decision (AR-05) before slice 4.

Done 2026-09-07.

- TC-01: 78 conformance cases for rules 4 to 21. Each case has its citation, and each rule family has the four case types.
- TC-02: the 22 official rulings for rules 1 to 21 are in `src/sldata/rulings/qa.json`. Each one is modeled, or it names the tier it waits for.
- TC-04 and TC-10: `runs/2026-09-07T-tc04-scenario1/stats.json` records 100 games with 0 unhandled errors and 0 replay mismatches. The median game took 5.1 s.
- TC-09: `runs/2026-09-07T-tc09-scenario1/stats.json`.

#### Slice 4: run artifacts, index, and tournament

- [x] `src/slruns/`: the run artifact writer (DR-05), the SQLite index (FR-57), Elo (OR-04).
- [x] `src/slcli/tournament.py`: N games between two agents with sides balanced and confidence intervals (FR-58).
- [x] `tests/artifact/`: file creation, index round trip, upsert idempotency.
- [x] `src/slcli/gates.py`: one command that plays N games, tests the replay with and without a shuffle of the legal list, and writes the v0.1 gate artifact.
- [x] `src/slcli/runs_cmd.py`: list the index, build it again, and show the Elo history of an agent.

Gate: TC-08. v0.1 is complete when TC-04, TC-05, TC-08, TC-09, and TC-38 each has a run artifact, and TR-11 holds (no external service is in v0.1).

Done 2026-09-07. v0.1 is complete. The artifacts are in `runs/`, which git does not record.

- TC-04, TC-05, TC-10, TC-38: `20260908T060448Z-v01-s01-guards-counterattack`. 100 games of scenario 1 with two scripted v1 agents. Zero unhandled errors and zero replay mismatches. Zero mismatches after a shuffle of the legal list. The median game took 1.4 s.
- TC-08: the same run and `20260908T060938Z-s01-guards-counterattack-v1-vs-v0` each have the four files, and `runs/runs.sqlite` lists the two.
- TC-09: `2026-09-07T-tc09-scenario1`. On the complete scenario 1: 581 steps/s with one worker, 3,118 with 8, and 5,662 with 16, each sustained 10 minutes. The gate is 3,500, so the Rust port decision (AR-05) stays closed.
- TC-01 and TC-02: the conformance corpus and the rulings, in the test suite.
- TR-11: v0.1 calls no external service.
- The first tournament: the scripted agent v1 beat v0 in 20 of 20 games with the sides balanced, with a 95 percent interval of 83.9 to 100 percent.

### v0.2: browser hot seat

#### Slice 5: host, protocol, and client

- [x] `src/slhost/`: the WebSocket host with the protocol of ARCHITECTURE section 8 (`intent` with the frame ID and the command ID, `los_request` with the strict-mode check of rule 19.3), the per-player view (a single view in hot seat), the selector loop policy on Windows.
- [x] `client/`: Vite, TypeScript, the board renderer from polygons in the 1977 look, and counters from data as an SVG atlas. Also pan, zoom, hex hit testing, the action log panel, the tabletop switch, and the casual and strict LOS modes.
- [x] `src/slcli/host.py`: one command starts the host and opens the client.
- [x] `tests/browser/`: Playwright plays the first turn of scenario 1 in hot seat (TR-07).

Gate: BC-01 (the owner completes scenario 1 in the browser against the scripted agent), BC-04, TC-11, TC-23, TC-40 (the client has no LOS code).

Done 2026-09-08. BC-01 is the one item that waits, because the owner must play the game.

- TC-23 and TR-07: `tests/browser/test_hot_seat.py` drives the built client through the set up and the first turn of scenario 1 with Playwright, and the page reports no error.
- TC-11 and NFR-02: the same suite measures the time from the intent to the next frame in the browser. The 95th percentile is below 50 ms on localhost.
- TC-40: the client sends `los_request` to the host and shows the answer. A static scan of the built bundle finds no rule function.
- BC-04: the action log panel shows the rule ID, the dice, and each modifier with its cause. The tabletop switch hides the dice and the modifiers.
- FR-39: `sl-cli host --agent v1` gives one side to a scripted agent, and `tests/host/test_agent_opponent.py` plays a game against it to its end.
- BC-01 waits for the owner. The command is `sl-cli host --scenario s01_guards_counterattack --agent v1 --open-browser`.

#### Slice 6: generator v1 and the reference loader

- [x] `src/slboards/`: the five-pass generator for the city type with zone constraints from the scenario.
- [x] `src/slboards/reference.py`: the reference-mode loader from `background/reference/`, with the guard that default tests do not load it.
- [x] Zone resolution for scenario 1 on a generated city board (FR-21), with the bounded seed retry and the fallback message. The generator parameter record goes in the run artifact.
- [x] `tests/boards/test_geomorphic.py`: 1,000 seeds satisfy the edge rules (TC-14a).
- [x] `src/slcli/boards_cmd.py`: `sl-cli boards` for the gate run and for the board documents the owner scores.

Gate: TC-14a, and the answer to O-04 recorded in `VIBE_HISTORY.md`.

Done 2026-09-08.

- TC-14a: 1,000 seeds, 100 percent, in `runs/20260908T085233Z-tc14a-s01-guards-counterattack` and in `tests/boards/test_geomorphic.py`.
- O-04 is answered in `VIBE_HISTORY.md` and in `docs/ARCHITECTURE.md` section 7.1. Zone set up moves scenario 1 to a generated board when the zone says how much room is necessary.
- 21 of the 1,000 seeds used the bounded retry. Each one found a subsequent seed.

### v0.3: scenarios and LAN

#### Slice 7: rules 22 to 27, scenarios 2 and 3A, concealment, views

- [x] Rules 22 to 27 with their conformance cases and Q and A rulings.
- [x] Scenarios 2 and 3A as data files.
- [x] `src/slcore/view.py`: the per-player view with opaque concealment tokens and dummy stacks (AR-09).
- [x] `tests/secrecy/`: no opponent-hidden unit in each outbound message, prompt, or public replay (TR-09).

Gate: TC-01 for rules 22 to 27, TC-04 for scenarios 2 and 3A, TC-34.

Done 2026-09-08.

- TC-01: 40 new cases in `tests/conformance/cases/rules_22_27.json`, and each of the six rule families has the four case types.
- TC-04: scenarios 2 and 3A play to their last turn and replay to the same hash sequence.
- TC-34: `pytest tests/secrecy -m gate` gave zero disclosures in 100 games of scenario 2.
- The client draws the concealment tokens, the smoke, and its own charges. It has no rule logic, and TC-40 holds.

#### Slice 8: LAN rooms, three scripted agents, traces

- [x] `src/slhost/rooms.py`: room codes with 128 bits of entropy, origin check, connection limits, slot assignment (SR-03).
- [x] Two clients on one LAN play one turn (TR-08).
- [x] Three scripted agents with named parameters and versions (FR-44).
- [x] `src/slagents/tuned/traces.py`: the trace writer from the acting agent's view, with the canonical payload and the `board_source` field (FR-60, DR-08, SR-09, SR-10).
- [x] `src/slcli/agents_cmd.py`: `sl-cli agents` for the agent list and the TC-15 gate.

Gate: TC-12, TC-24, TC-27, TC-15.

TC-15 holds on 2026-09-08. The gate played 900 games with zero unhandled errors, in
`runs/20260908T151517Z-tc15-scripted-agents`. The run before it gave six games that did not
end, and project ruling PR-19 was the cause.

Done 2026-09-08.

- TC-12, TC-24, TC-27: `pytest tests/lan` with two clients on the loopback address.
- TC-15: `sl-cli agents --games 100`, with a run artifact for each agent and scenario.

### v0.4: agents that learn

#### Slice 9: the reinforcement learning environment, PPO, the ladder, the league

- [x] `src/slagents/learned/env.py`: PettingZoo AEC with the legal-command mask (FR-50).
- [x] `src/slagents/learned/ppo.py`, `nets.py`, `league.py`: PPO in raw torch with the composed head, snapshots, opponent sampling by loss rate, Elo (FR-51, FR-52).
- [x] `src/slcli/train.py`: one command starts a run with TensorBoard scalars (IR-07).
- [x] `tests/agents/test_ppo_smoke.py`: 10,000 steps, finite loss, steps/s recorded (TR-10).
- [ ] The ladder: 1 million, 10 million, then 100 million steps, each with a run artifact and a tournament against the versioned scripted agents. The 1 million rung ran on 2026-09-12 (`runs/20260912T192005Z-ppo-s01-guards-counterattack`, 188 steps/s on the RTX 5070, 89 minutes). TC-18 gave 42.5 to 50 percent against each scripted agent, and that number is 153 truncated games of 160 counted as half a win each, with 0 wins. The greedy policy cycles pickup and drop in the Advance Phase of turn 1. The report is `docs/reports/2026-09-12_training_run_1m.md`. The shaped reward of `src/slagents/learned/reward.py` (a truncation costs a loss, the doctrine terms of RV-9 table A, the national weights of table B, the evaluation counts a truncation on its own) landed the same day, and the rung runs again as `runs/train_1m_shaped/`. The third run (`runs/20260913T014918Z-ppo-s01-guards-counterattack`, no discount, the repetition defeat) plays to the end as the Russian and loses to v1 to v6, and it cycles as the German, which it never played. The evaluation built the scripted opponent for one side and then changed the sides; the member now plays the side of the frame, the row has `by_side`, and `--player both` trains the two sides. The fourth run (`runs/20260913T033700Z-ppo-s01-guards-counterattack`, `--player both`) learned the German defence (8 to 10 of 10 against v1 to v5) and not the Russian attack (0 of 10). The cause was on the board: the scenario file put the front along the columns, six to twelve hexes apart, and the card puts it along the rows, two to five hexes apart. Scenario 1 uses the row bands and the `near` zone now, and the generator places the zone buildings before the free pass. The v6 Russian wins 8 of 20 against v1 on the new board, from 1 to 5, and v5 wins 20 of 20. The fifth run (`runs/20260914T010152Z-ppo-s01-guards-counterattack`, the fourth run's settings on the new board) wins 0 of 10 as the Russian against each opponent and, as the German, 0 of 10 against v1, v2, v3, and v6. The 1 million step policy is below v1 on the two sides. The owner chose the start from the scripted agents: `sl-cli imitate` (2026-09-14, `runs/20260914T161617Z-imitate-s01-guards-counterattack`) copies v5 and v6 from 400 games, holdout accuracy 61.5 percent, and the snapshot wins 4 of 10 as the Russian against v2 to v5 before any PPO step. The sixth run, PPO from that snapshot, stopped at 24,576 steps for a shutdown (`runs/20260914T165424Z-ppo-s01-guards-counterattack`: v1 11 of 20, v5 14, v6 5). To run it again: `sl-cli train --scenario s01_guards_counterattack --steps 1000000 --seed 20260917 --player both --entropy 0.01 --learning-rate 0.0001 --device cuda --start-from runs/imitate_v5v6/snapshot-0.pt --out runs/train_1m_imitate/snap --tensorboard runs/train_1m_imitate/tb --eval-games 20`.

Gate: TC-13, TC-18 at each rung, TC-19.

Done 2026-09-08. The ladder is the one item that waits.

- TR-10: `pytest tests/agents/test_ppo_smoke.py -m gate` gives 10,000 steps with a finite loss.
- TC-19: each training run writes an Elo table with the learner and each member of the league.
- TC-18: `sl-cli train --eval-games N` measures the win rate against each constant opponent, with the sides balanced and the interval reported.
- The ladder and TC-13 wait for the owner. The processor build of torch gives about 60 steps a second, so the rungs are hours to weeks. The owner installs the CUDA build of torch for them.

#### Slice 10: the prompted model agent

- [x] `src/slagents/prompted/providers/`: the base class from the `llm_compare` pattern, the local OpenAI-compatible adapter with the health check, the Anthropic adapter, the key loader, the allowlist (IR-01, IR-02, SR-02, SR-05).
- [x] `src/slagents/prompted/harness.py`: the text view, the two-stage answer, the flat schema, retries, the scripted default, the latency budget (FR-45 to FR-49, FR-59).
- [x] `tests/providers/` with the `integration` marker: one real call to the local endpoint and one to a SaaS provider (TR-05, TR-06).
- [x] `src/slagents/prompted/router.py`: the failover sequence with a breaker for each provider (IR-05).

Gate: TC-16, TC-17, TC-20 (one provider), TC-21, TC-22.

Done 2026-09-08. TC-21 is the one gate that waits.

- TC-16, TC-17, TC-20, and TC-22 hold. The real call went to OpenAI, because the Anthropic account has no credit.
- TC-21 waits for the local llama-server. It answered its health check and then stopped answering. The test skips when the endpoint is quiet.

#### Slice 11: the tuned model agent

- [x] `src/slcli/traces_cmd.py`: build the trace data set from `runs/` (FR-60). The default build rejects `reference_private` records, and `tests/agents/test_trace_guard.py` proves it (TC-39).
- [x] `src/slagents/tuned/finetune.py`: the year-one profile (a 7B or 8B base, LoRA or QLoRA with a named configuration, a fixed context length, generated traces only) with importance weights (FR-61, NFR-09). The path has three steps: the 50-step smoke run, the export and load, then the full run.
- [x] `src/slagents/tuned/export.py`: merge and export to GGUF, load on llama-server (IR-08).
- [x] Constrained decoding with the legal list as the grammar or schema (FR-62).
- [x] `src/slcli/tournament.py --families`: the family table (FR-63).
- [x] `tests/agents/test_finetune_smoke.py`: 50 LoRA steps on 10 traces (TR-12).

Gate: TC-35, TC-37, TC-39, BC-09. TC-36 is recorded as a measurement with its four metrics.

Done 2026-09-08 for the parts that this machine can run.

- TC-39 holds, with the guard in the data set build and in the fine-tune.
- TR-12 holds in its first half. The second half needs llama.cpp and a running llama-server.
- TC-37, TC-35, and BC-09 wait for the owner's workstation and the local endpoint. The commands and the artifacts are complete for them.

### RC: release candidate

#### Slice 12: art, boards, rubrics, audit, title

- [x] The last art pass on counters and boards, with a provenance record for each asset. `docs/ASSET_PROVENANCE.md` names each drawn asset and where its look comes from. The client draws the three hill shades and the crest lines of rule 43.
- [x] The four board types in the generator. City, hills, village, and rural, each with a style record (FR-25, FR-26). Rule 43 in the core is the part that makes a hills board playable.
- [ ] The owner scores the board rubric and the counter rubric (TC-14b, TC-14c). `sl-cli boards --write <directory> --count 12` writes the twelve boards and the empty sheet. The scores are the owner's to give.
- [x] `tools/audit_release.py`: the release audit of the tree, archives, fixtures, screenshots, and artifacts (SR-07, TC-25, TC-28, TC-29). Zero findings, with 20 tests.
- [x] The non-affiliation notice and the licence notice on the served page (SR-08, SR-06). The public title is the owner's to select. The page carries a working title until that time.
- [x] The remaining SaaS adapters (IR-02 RC) with their real-call tests. The Gemini adapter is the third API shape. Each provider of the configuration has its own real-call test.

- [x] The three armies of the counter set. The American counters come from RV-1 sections 2 to 4. A group of a scenario can name its own army. One project scenario starts with German, Russian, and American forces in one game.
- [x] The `columns` zone and the `edge` zone for a set up area (FR-21), each with a terrain test.

Gate: BC-05, BC-08, TC-14b, TC-14c, TC-25, TC-28, TC-29, TC-20 for five providers.

State of the gate on 2026-09-08:

- TC-25, TC-28, TC-29: hold. `python tools/audit_release.py` reports zero findings.
- BC-08: holds on the same run. The tree and the page carry no brand and no Avalon Hill material.
- TC-20: the configuration names five SaaS providers. Real calls answered from openai, xai, and gemini. Claude answered that the account balance is too low, and mistral answered that the rate limit is exceeded. The two answers are conditions of the owner's accounts, and each test stops with that reason. TC-20 stays open until the two accounts answer.
- BC-05, TC-14b, TC-14c: they wait for the owner's scoring session.

---

#### Slice 13: the design-your-own tools and the campaign game (FR-17)

The owner told us to add a set of scenarios to start with, and a campaign generator. The
sequence of the campaign must follow the performance in each scenario. Game Set IV of the
1977 rules is that feature, and FR-17 names it.

- [x] `src/slcampaign/points.py`: a force point value for each counter. The printed Point Value Chart is a picture on the rules sheet. So the scale is the project's own until the owner reads the chart (open item O-08).
- [x] `src/slcampaign/generator.py`: random scenario construction. Six steps give the board type, the two armies, and the turn count. Three more give the victory condition, the share of the points, and the two forces. Each step reads the seeded generator of the core. So one seed builds the same scenario again.
- [x] `src/slcampaign/build.py`: the layout. The defender sets up first and the attacker moves first (rule 11). The two sides start in bands at the two ends of the board (rule 12).
- [x] Two more victory conditions in the core, `force_eliminated` and `casualty_exchange`, which the victory table of the printed method uses.
- [x] `src/slcampaign/campaign.py`: the campaign game. Seven ranks, the Elan and Cowardice points of rule 4, the promotion of rules 2.4 to 2.7, and the victory points of rule 5.
- [x] `src/slcampaign/ladder.py`: how the record chooses the next scenario. A win makes the next defence stronger and a loss makes it weaker. The seed of the next scenario mixes the wins, the losses, and the points on the personnel file.
- [x] `sl-cli campaign --draw 12` writes twelve scenarios and plays none. `sl-cli campaign --seed 11` plays a campaign and writes a run artifact.
- [x] `tests/campaign/`: 75 tests. Each item of rule 4 has its own test. The scorer reads a list of events, so a test of a rule gives it the events that rule names.
- [ ] The printed Point Value Chart and the printed Random Selection Chart (open item O-08). The owner reads them off the sheet.
- [ ] The victory conditions of the printed table that use a rule of a subsequent tier. Those are the night scenario, the exit off the far edge, and the conditions that name an armoured fighting vehicle.

Gate: FR-17. A random scenario builds and plays. A campaign is repeatable from its seed.

---

#### Slice 14: board composition (FR-29)

Scenarios 4 to 12 each play on two to four boards, so the composition is the first thing
that year two needs. It is also the one piece of that work with no external blocker.

- [x] `src/slboards/compose.py`: two to four boards make one playing surface. The boards touch along their long edges or along their short edges, and a board can turn 180 degrees.
- [x] The edge constants of FR-24 set each hex that a seam can touch. Before this slice they set the woods half hexes and the road entries only. Generator version 5 is the first one that holds them.
- [x] `column_label` and `column_index` continue after ZZ, because a composition of four boards is 129 columns.
- [x] `board_composition` in a scenario, and `s00c_two_board_advance` as the game that uses it.
- [x] `tests/boards/test_composition.py`: 32 tests.

Gate: FR-29. Two to four boards compose. A game on a composition replays.

Done 2026-09-08.

- The seam was a real defect. The edge pass set the woods half hexes and the road entries only. So two boards disagreed on each other seam hex, and no composition held. The pass sets each seam hex, and the join check reads each one.
- The scenario zone bands have new values, because the seam columns hold no building. Scenario 1 and scenario 3A moved to a building density of 2.

#### Slice 15: hidden initial placement (rule 42, FR-10)

- [x] `src/slcore/rules/r42_hidden.py`: rule 42.1 to 42.5, without the blind fire of the first half of rule 42.4.
- [x] `Unit.hidden`, and the view of the other player does not name a hidden unit.
- [x] The reveal of rule 42.2, after a move, a fire, or a smoke. Also next to an enemy at the end of a Defensive Fire Phase or an Advance Phase.
- [x] The halving and the reveal of rule 42.4, and the stop of rule 42.5.
- [x] `tests/engine/test_hidden_placement.py`: 19 tests.
- [ ] The blind fire of rule 42.4. It changes the legal list of each fire window into each hex in the line of sight. The environment of FR-50 reads that list as its action space. `blind_fire_hexes` gives the error that says so.

Gate: FR-10. A hidden unit is in no view of the other player. It comes on the board on each of the causes of rule 42.2.

Done 2026-09-08.

---

#### Slice 16: the rural terrain of rule 44

Game Set II gives an effect to three terrain types that the city board does not use. Two of
them were in the terrain data with no effect, and the third had half of one.

- [x] `src/slcore/rules/r44_rural.py`: rules 44.1, 44.21, 44.22, 44.23, 44.24, 44.31, and 44.32.
- [x] A wheatfield stops sight through it and not into it. Fire that goes through one is half strength, and a unit above the crop fires at full strength.
- [x] Rule 44.24: the crop is seasonal. A scenario says `wheat_season`, and out of season the hex plays as open ground.
- [x] Rule 44.32: a unit fired on while it moved through a shellhole gets minus one and not the minus two of rule 16.5.
- [x] Rule 44.1: Point Blank Fire across a cliff hexside is tripled for the higher unit.
- [x] The `cliffs` style of the generator. A cliff goes on a hexside where the level changes, and a cliff that would cut the board in two is dropped.
- [x] The client draws a cliff hexside in black, which is the colour rule 44.1 names.
- [x] `tests/engine/test_rural_terrain.py`: 20 tests, and 5 more in the board tests.

Gate: TC-45. Each of the three terrain types has its effect, and the generator makes a board with each of them.

Done 2026-09-08.

- A lower building density does not change the retry rate of scenario 1. The limit is how many buildings the eight columns of the band hold, and not how many the generator tries to put there. The measured rate is 25 of 200 seeds, and the test reads that measurement.

---

#### Slice 17: the armor tables, and computer against computer

- [x] `src/sldata/tables/armor.json` with `load_armor`: the to-hit table of rule 33.3, the eleven cases of rule 33.31, the kill table of rule 33.4, and the vehicle modifiers of rule 33.41. The numbers come from page 13 of the rulebook, where the tables are graphics.
- [x] `tests/conformance/test_armor_tables.py`: 40 tests. Each row is in the file, and four tests read a property so that one incorrect digit stops a test.
- [x] `sl-cli host --agents v1,v2`: a game between two computer opponents that a browser shows. `--agent-delay` sets the pace, and a game with two agents gets a pace a person can follow.
- [x] `Game.spectator_view` with its guard: a game with a person in a seat gives an error, and it does not give a full view (AR-09).
- [x] `tests/browser/test_computer_vs_computer.py`: a full game in the browser, with 10 tests. The harness reads the pixels of the canvas. A client that gets each frame and makes no picture stops the test.
- [x] A page that cannot connect says why. SR-03 refuses a connection with no room code, and the person got an empty board and one line of small text. A notice in the middle of the board tells the person to open the address that the host prints.
- [x] The armor rules 28 to 41. Slice 18 holds them.

Gate: TC-46. Two computer opponents play a full game in the browser, to a result, with no console error.

Done 2026-09-08. The first run: the Germans took The Guards Counterattack in six turns and 924 commands.

---

#### Slice 18: the armor rules 28 to 41, and a window that is not a browser

The owner told us to do three things. Write the armor rules 28 to 41. Give the map its
buildings, its trees, its walls, and its roads. Open a window of its own on Windows and on
Unix, and not a browser.

**The armor game**

- [x] `src/slcore/rules/r28_vehicles.py`: rule 28 and rule 29. The covered arc of rule 29.4
  as exact integer geometry, the target facing of rule 33.5, and the stacking of rule 29.2.
- [x] `src/slcore/rules/r30_vehicle_movement.py`: rule 30 with the Vehicle Movement Cost
  Chart of page 11, in half movement points, and the breakdown die of rule 39.1.
- [x] `src/slcore/rules/r31_transport.py`: rule 31. A passenger rides on the counter. The
  infantry on foot stand below it, and rule 32 makes the two different conditions.
- [x] `src/slcore/rules/r32_afv_cover.py`: rule 32. The hull is a stone wall on the line of
  sight. It is a plus one for the infantry below it, and a plus two for the passengers.
- [x] `src/slcore/rules/r33_afv_combat.py`: rule 33. Two steps, the to-hit table and the
  kill table, with the eleven cases, the possible hit of rule 33.32, and the crew of 33.9.
- [x] `src/slcore/rules/r34_afv_vs_infantry.py`: rule 34, with the canister of rule 34.9 and
  the crew exposed counter of rule 34.8.
- [x] `src/slcore/rules/r35_overrun.py`: rule 35 and the grenade bundle of rule 38.3.
- [x] `src/slcore/rules/r36_infantry_vs_afv.py`: rule 36, the two methods, with the chart of
  rule 36.12.
- [x] `src/slcore/rules/r37_at_weapons.py`: rule 37. The flamethrower, the panzerfaust, and
  the bazooka, each with its own column of the kill table.
- [x] `src/slcore/rules/r38_fate.py`: rule 38, rule 40.4, rule 41.3, and rule 41.4.
- [x] The vehicle counters of the three armies in `src/sldata/counters/`, with the
  panzerfaust and the bazooka in the support weapons.
- [x] `src/sldata/tables/vehicle_movement.json` and four more charts in `armor.json`.
- [x] `src/sldata/scenarios/s04_armor_probe.json`: the first game that plays them.
- [x] `tests/conformance/cases/rules_28_41.json`: 82 cases. Each of the fourteen rule
  families has all four case types.
- [x] `tests/armor/`: 28 tests. The covered arc reads properties and not one example, and
  the scenario plays and replays.
- [x] Project rulings PR-20 to PR-29 for what the rules text leaves open.
- [ ] Rules 47 and 51, the halftrack, the truck, and the jeep. Their counter values are in
  the counter data, and PR-20 keeps them out of a scenario until their rules are here.
- [x] Rule 35.6 and rule 35.7 (PR-31, 2026-10-10: the sequence of play resolves overruns in
  the Defensive Fire Phase, so the window exists). The overrunning vehicle must live through the defensive
  fire of the hex before it enters. The phase sequence of rule 4 puts the Defensive Fire
  Phase after the Movement Phase. So a fire that stops an overrun in the middle of a move
  has no window. That window is a change to `phases.py`, and it is its own work.
- [x] Rule 34.5, area fire against a concealed target for the primary armament. Rule 25.8
  in `apply_to_hex` gives half the fire to a concealed target, and rule 34.5 gives the same
  cut to a hit. One conformance case shows that the shot gets the cut one time.

**The computer opponent**

- [x] `src/slagents/scripted/v3.py`: the tanker. Agent v1 and agent v2 have no policy for
  a vehicle, so their tanks do not move. Agent v3 drives, fires the gun at a vehicle first,
  fires the machine guns at infantry, and fires a panzerfaust or a bazooka. It sends
  infantry at a tank and it repairs a broken gun. Four named parameters (FR-44).
- [x] `tests/armor/test_tanker_agent.py`: 7 tests. One of them measures that agent v2 plays
  no armor command, which is the measurement agent v3 is here to change.
- [x] `v3` is in `sl-cli play`, `tournament`, `host`, `window`, `campaign`, `agents`, and
  the trainer league.

**The window**

- [x] `src/slwindow/`: a window of its own with a 2D game library, on Windows and on Unix.
  The `desktop` extra installs it: `pip install -e ".[desktop]"`.
- [x] The window speaks to the same host the browser speaks to, on the same protocol. So it
  holds no rule and no rule table (AR-06). `src/slwindow/embedded.py` starts a host in the
  same process, so one command opens one window.
- [x] The board shows the buildings, the trees, the walls, the hedges, the cliffs, and the
  roads. It also shows the hills with their crest lines, the wheat, the shellholes, and the
  sewer covers.
- [x] The counters show the vehicle with its movement points, its gun, and its gun barrel.
  A click on a vehicle shades the wedge of its covered arc.
- [x] `sl-cli window --agents v1,v2` shows two computer opponents that fight in that window.
- [x] `tests/window/`: 30 tests. Each of the 25 that draw reads the pixels of the surface.
  Four of them show that the pixel check says no. It says no to a blank window, to a board
  with no counters, and to a board with no buildings.
- [x] One test plays a command the way a person does: a click on a row of the panel, an
  intent to the host, and the next frame. Five more check `sl-cli window` with a stand-in
  that opens nothing.

Gate: FR-16, FR-30, and NFR-01. The armor rules play in a game and replay from the seed.
The window opens with no browser and shows the board and the counters of a live game. The
throughput stays above 3,500 environment steps each second.

State of the gate on 2026-09-08:

- FR-16 holds for rules 28 to 41. 975 tests pass and 2 are skipped, with 0 failures.
- FR-30 holds in a second consumer. The window shows the board and the counters, and each
  of its 25 tests reads the pixels.
- NFR-01 holds. 5,678 environment steps each second at sixteen workers for ten minutes,
  against the gate of 3,500. The artifact is `runs/20260908T-slice18-nfr01/stats.json`, and
  the number before this slice was 5,662.

Done 2026-09-08.

- The portage of rule 5.7 is in half points, because rule 37.35 gives the panzerfaust half
  the cost of a machine gun. Rule 6.1 reads full points, and half a point of load rounds
  up, because half a point of load is load.
- A crew counter is made when the game starts, and not when a vehicle dies. The unit list
  of a game does not change length, so an agent that learns keeps one observation shape.
- The move of a vehicle holds no facing. It stops on the spine to the right of the
  direction it moved, and a free pivot command gets to the other five. Rule 33.32 tells us
  that the penalty for a pivot and the penalty for a move to a new hex are not cumulative.
  So the free pivot costs the player nothing that the rules do not charge.

---



#### Slice 19: the shape of a hex, the road planner, and the drawing

The owner looked at a game in the window and gave five corrections.

- [x] The camera multiplies the y value of the lattice by the square root of three. It used
  half of that constant, so each hexagon was half as tall as it must be.
- [x] `tests/window/test_geometry_and_navigation.py`: 15 tests. The six sides and the six
  vertices of a hexagon, the two limits of the zoom, the four arrow keys, and the drag.
- [x] `road_grid` puts the east to west road on one row index for each column. It put the
  columns of an odd index one row lower, and those hexes are two apart, so the road was 21
  pieces.
- [x] `connect_roads` attaches each part that remains to the largest part. It goes by the
  shortest line of open ground, so each road entry of FR-24 goes somewhere.
- [x] `tests/boards/test_roads.py`: 20 tests. One connected group, all four edges, and a
  junction with four roads around it.
- [x] The window makes a building as a plan. The outline goes around the full building and
  not around each hex, and there is no ink border that makes it read as a counter.
- [x] A wall, a hedge, and a cliff each have height: a lit top, the body, and the shadow.
- [x] The wheel changes the size about the pointer. A drag with one of the three mouse
  buttons moves the board, and the four arrow keys move the board. The two page keys move
  the command cursor.
- [x] Generator version 7. Scenario 2 moved to seed 19421122, which satisfies its zones on
  the first try.

Gate: FR-30. The board reads as a board: hexagons of one shape, roads that go across it,
and terrain that no person reads as a unit.

Done 2026-09-08.

---

#### Slice 20: the terrain that the owner's boards show

The owner has photographs of the boards of the 1977 game. The instruction was to make a new
picture of each terrain, in a flat shaded style.

- [x] A study of the photographs, terrain by terrain, and a record of it in
  `docs/ASSET_PROVENANCE.md`. The study gives the visual language. Each colour and each
  shape is the project's own (SR-07, DR-01).
- [x] `src/slwindow/theme.py`: a new set of colours. The ground is a light yellow-green.
  Each feature has four tones for the flat shading.
- [x] `src/slwindow/render.py`: a wood is a mass of eleven crowns. A building is a plan of
  one shape for each hex, and a road is a ribbon that turns.
- [x] `src/slwindow/render.py`: a hill is a flat brown area, a grain hex is five rows of a
  crop, and a shell hole hex is six pits.
- [x] The position of each crown and each pit comes from the reference of its hex. So a
  board makes the same picture in each session, and the core generator stays with the
  rules.
- [x] `client/src/board/render.ts` and `client/src/counters/draw.ts` hold the same base
  tones. `tests/browser/test_render_constants.py` compares them with `slwindow.theme`.
- [x] The hex centre dot goes on top of the terrain. The colour change removed it from the
  browser, and FR-30 makes it necessary. Rule 7.1 threads a line of sight to it.
- [x] `tests/window/`: 48 tests. Each of them reads the pixels of the surface.
- [x] `tools/make_docs_images.py` makes the pictures of the documentation: three boards
  from the generator and the desktop window in a game. `docs/images/MANIFEST.json` gives
  the seed of each one.
- [x] The release audit lets an image through only in `docs/images/`, and only when the
  manifest names it. Each other image in the tree is a finding (SR-07, TC-29).
- [x] `tests/docs/test_documentation_images.py`: 8 tests. Each picture is made again and
  compared with the file in the tree.
- [x] `README.md` and `docs/ASSET_PROVENANCE.md` show the pictures. SR-07 says which
  directory can hold an image and what holds that rule.

Gate: FR-30. A person looks at the board and reads the terrain without a legend.

Done 2026-09-08.

---

#### The tempo pass: agent v6 and the settled gauntlet (2026-09-12)

The first gauntlet run showed the cause of the weak play: each 15 to 15 pair on scenario 1
was one side that wins each game. The German defender wins against each agent, and a random
German wins too, because v4 and v5 as the Russian attacker move on turn 1 and then stand.

- [x] `src/slagents/scripted/v6.py`: the tempo agent. The schedule, the maneuver element out
  of prep fire, the threat in squads with the open ground and stack factors, the route
  field, the stand as a choice, the stacking guard, the machine guns in the threat, the
  defender's own buildings, and the plan with a garrison and a hold.
- [x] `v6` and `v6:<nation>` in `make_agent`, and in the choices of `host`, `window`, `gate`,
  `campaign`, the trainer league, and the TC-15 gate.
- [x] `slruns.elo.settled_ratings`: the gauntlet's Elo from the whole result list, a
  Bradley-Terry fit, because one pass ranked by the order of play. The first run put the
  best win rate fourth.
- [x] `tests/agents/test_v6_tempo.py`: 12 tests, each on a real state of a real game. The
  attacker moves after turn 1, which is the defect the agent corrects.
- [ ] The Russian attack of scenario 1 against a v1 or v5 German. It wins 1 to 5 of 20 with
  each parameter set tried. The German outranges the Russian, a stack in a street dies to
  one KIA, and 5 turns leave no time for a covered detour. The next lever is a plan of a
  whole turn (a search) or the learned tier, and a check of the set up distances of the
  scenario against the card (the printed board puts the two sides closer).

Gate: the gauntlet leaderboard. v6 first on scenario 1 with the settled Elo (1739 against
v1 at 1701), 70.0 percent overall, and 28 of 30 as the Russian against a random German.

---

## 2026-10-10 - The plan to the MVP: a person plays a whole game in the 3D window

Owner directive 2026-10-10: the one UI that matters is the 3D window (`sl-cli window3d`, with
its 2D and 3D cameras). The browser client and the pygame window get no new features; their
tests stay green.

The MVP: a person installs with one command, starts a game against the computer on scenario
1, 2, 3A, or 4 in the 3D window, plays it to the result with the mouse, saves it, and
resumes it. The opponent is strong enough to be interesting, and the release audit is clean.
Out of the MVP: the 10M and 100M ladder, the tuned model, BC-06, BC-09, the printed campaign
charts. Run 6 of the learned agent continues as an overnight parallel track.

Finding of the review: before slice 21 the 3D window only watched. The mouse buttons only
panned, it never sent an intent, and the docstring of `window3d_cmd.py` said that it did. No
person had played a whole game in any front end (BC-01 open since slice 5).

#### Slice 21: the 3D window plays (M1)

- [x] `src/slwindow3d/picking.py`: the hex under the mouse, a ray against the hex prisms (top
  faces and the side faces of a hill), in the 2D and the 3D camera. No Panda3D import.
- [x] `src/slwindow3d/selection.py`: a click on a unit selects it, a click on a target hex gives
  its legal command, a menu when a hex has more than one command or also holds other units,
  the list of commands with no hex, the units to place in set up. No Panda3D import.
- [x] `src/slwindow3d/play.py`: the rings of the selected unit and its targets, the list of
  buttons on the left, the menu, the phase banner, one intent for each frame, and a new try
  after the host refuses an intent.
- [x] `Board3DApp(send=...)`: a click is a press with no drag; Escape cancels in a window that
  plays; a click on the status panel is not a board click.
- [x] `sl-cli window3d --agent v6 [--agent-side german]`: a person against the computer; with
  no agent, hot seat.
- [x] The options overlay (`o`) read the action from the top of a legal entry and drew nothing
  in a live game; it reads the payload now, and a test uses the host's shape.
- [x] `tests/window3d/test_picking.py` (6), `test_selection.py` (7: each legal command of a
  whole game of scenario 1 and of scenario 4 is reachable by clicks), `test_play_input.py`
  (the set up and 120 commands by mouse through a real host).
- [x] The gate: `pytest -m gate tests/window3d/test_play_input.py` plays a whole game by mouse
  to a result. 2026-10-10: scenario 1, 402 commands, 610 board clicks, 215 button presses,
  the Russians won on the last turn. Both lenses picked.
- [x] The 3D board was a mirror of the 2D board (each hex label read backwards);
  `picking.world_xy` puts north at the top.
- [x] The font caches of the counter drawing survive a `pygame.quit()`.

Gate: TC-46 for the 3D window with a person's seat, and the path to BC-01.

#### M2: the owner plays (BC-01)

- [ ] `sl-cli window3d --scenario s01_guards_counterattack --agent v6`, to the end. Each place
  the owner stopped, guessed, or got annoyed is the backlog of slice 22.

#### Slice 22: the finish work (M3)

Started before M2 on 2026-10-10, with the items that did not wait for the owner's game.

- [x] Save and resume (`src/slhost/saves.py`): the scenario, board, seed, opponents, and the
  command log with the hash after each command. Resume plays the log again through the core
  and stops at the first hash that does not agree. `sl-cli window3d` saves after each frame
  and at exit to `runs/saves/<scenario>-seed<seed>.json`; `--resume FILE` resumes.
- [x] The end-of-game screen with the winner, the cause, and the turn.
- [x] Difficulty names: `--agent easy`, `normal`, `hard` give v5, v3, v6 (by the gauntlet of the four MVP scenarios).
- [x] The action log with the dice and the modifiers (BC-04): `src/slwindow/logtext.py`; the
  3D window gives the panel space of the command list to the log.
- [x] The fire odds before the fire: `Engine.fire_preview` (rule 10.3, the known modifiers,
  the results over the 36 rolls), sent only to the player who builds the group.
- [x] A set up by the computer for the person's side: `sl-cli window3d --auto-setup [agent]`
  (`Host(setup_agents=...)`).
- [x] Defect: the window client added the whole log tail with each frame, so each event
  showed many times, and a long computer turn lost its start from the log. Each frame now
  holds every event since the last frame, and `log_from` lets the client add only new ones.
- [x] Defect (AR-09): the host sent the same log to each seat, and the log named hidden and
  concealed units. `src/slhost/logview.py` makes each player's log at the time of each
  command; `tests/secrecy/test_log_secrecy.py` checks it command by command.
- [x] Defect: in scenario 2 the units to place pushed the selected unit's commands out of the
  list; in scenario 3A a command with a hex and no unit (a concealment counter) had no click.
  The mouse gate now plays scenarios 1, 2, 3A, and 4 to a result.
- [x] The line of sight in the 3D window: `l` asks the host (FR-34) from the selected unit to
  the hex under the mouse; the window draws the answer and gives its rule.
- [x] The options overlay (`o`) starts off in a window that plays, so it does not hide the
  rings of the selected unit.
- [x] The `play` extra: `pip install -e ".[play]"` installs the 3D window; the README has a
  "Play the game" section.
- [x] The tanks drive to firing positions and fire (`armor.py`, v3.1, v6.2), 2026-10-10.
- [ ] Scenario 4 balance: the Allied side won 78 of 80 games of the scripted agents.
- [ ] What M2 finds.

#### Slice 23: content (M4)

- [ ] The gauntlet on scenarios 1, 2, 3A, and 4 for games that do not end and agent defects.
- [x] v6.1: the parameter sweep for the Russian attack of scenario 1 (134 of 200 against v1
  and v5 Germans, the old v6 107), and the empty objective crash of scenario 2.
- [x] Rules 35.6 and 35.7: PR-31, the overrun resolves at the end of the Defensive Fire Phase
  (2026-10-10).
- [x] Rule 42.4 blind fire, and rules 47 and 51: out of the MVP scope (2026-10-10). Of the
  MVP scenarios (1, 2, 3A, 4) none has hidden placement and none has a halftrack, a truck, or
  a jeep; only `s00c_two_board_advance` has hidden placement. `blind_fire_hexes` names its
  tier, and PR-20 refuses the three vehicles in a scenario. They wait for year two.
- [x] TC-15 with v6.1, and the mixed gate `sl-cli agents --mixed` (0 errors in 168 pairs).

#### The merge with the GitHub line (2026-10-10)

The GitHub line (2026-09-16 to 2026-09-25) had its own playable 3D window, save and resume,
log streams, odds, and engine split. The merge takes that line as the base (VIBE_HISTORY,
2026-10-10). So these items of slices 21 and 22 are now the GitHub ones, and the modules of
this line are not in the merged tree: the play input (`picking.py`, `selection.py`,
`play.py`, and the mouse gate of `test_play_input.py`), `saves.py`, `logview.py`, this
line's `logtext.py`, `Engine.fire_preview`, `--auto-setup` (Ctrl and a), and the end screen
(the panel shows the end). The briefing, the fire animations, the sound, the armor policy,
PR-54 (was PR-31), the difficulty names (now v5, v6, v7), `--resume`, `--mixed`, and the
`play` extra are in the merged tree.

- [ ] The owner copies the scratch tree in and makes the commits (no git write by Claude).
- [ ] The newer browser client of the Windows machine goes into the tree, so the 28 client
  table tests pass.
- [ ] A gauntlet for the difficulty names on the merged engine (v5, v6, v7 were chosen from
  the reports of the GitHub line, not measured here).
- [ ] A mouse gate for the GitHub play input in the 3D window (a whole game by clicks).

#### Slice 24: release (M5)

- [ ] The board rubric (the public title is Squad Leader Expeditionem in the GitHub line) (TC-14b, TC-14c), a clean audit.
- [ ] One-command install on Windows and Linux with `view3d` in the default install.
- [ ] A README quickstart for a new person.
- [x] The `LICENSE` file holds the GPL-3 text (2026-10-10; the GitHub line had it too).

---

## Open items for the owner before slice 2

- O-02: the training workstation (CPU cores, GPU model and memory) for the benchmark manifest and the fine-tune bound.
- O-01: the llama-server endpoint for the local model tests.
- O-06: the base model for the first fine-tune.
- The public title, before RC.

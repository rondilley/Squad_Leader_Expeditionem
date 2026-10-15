# CLAUDE.md - Squad_Leader_AI

Operating manual for Claude Code sessions in this repository. Read it at session start.

## What this project is

An edition of the 1977 Avalon Hill board game Squad Leader, with the 4th edition rules. It plays in a browser or in a window of its own on Windows and on Unix.

The counter set has the three armies of that game: German, Russian, and American, with their vehicles. One rules core with no input or output is the engine for six consumers: the browser client, the desktop window, a local host, a reinforcement learning trainer, a model agent harness, and a replay tool. The core keeps the rule ID of each rule it applies. The action log shows the rule, the dice, and the modifiers for each result.

Four play modes: hot seat, LAN with a room code, human against computer, and computer against computer.

Computer opponents come in four families. Scripted agents have parameters with names. Learned agents are neural networks from self-play. Prompted model agents use local or SaaS language models through one provider interface. Tuned model agents are local language models fine-tuned on the game's own traces. The four families share one interface, one trace format, and one tournament.

The project is GPL-3 and non-commercial. The repository name is `Squad_Leader_AI`. The public title of the game is Squad Leader Expeditionem, and the window captions show it. This project is not affiliated with, sponsored by, or endorsed by Hasbro or Multi-Man Publishing.

## Read these first

1. `VIBE_HISTORY.md`, the newest entry first: what was done, what was decided, and why.
2. `tasks/todo.md`: the slice plan and the current slice.
3. `tasks/lessons.md`: corrections and surprises from earlier sessions.
4. `docs/VISION.md`, `docs/REQUIREMENTS.md`, `docs/SUCCESS_CRITERIA.md`, `docs/ARCHITECTURE.md`: direction, the requirements with IDs, the gates, and the design with its causes.
5. `docs/2026-09-07_Squad_Leader_Digital_Edition_Research.md` and the eight appendices in `docs/research/`: the evidence, with URLs. Read the appendix when a design question is about a number or a citation.

## The non-negotiable invariants

- One core, no side effects. `slcore` has no file access, no network, no clock, and no print. It has three public functions: `legal_commands`, `apply`, `hash_state`. A consumer applies a rule only through the core.
- Every rule application has its 4th edition rule ID in code, in the event it emits, and in the action log.
- All dice come from the seeded generator in the core. A game is its seed, its switches, and its command log. A replay that does not reproduce the hash sequence is a defect.
- The core gives its legal commands as a decision frame. Each command has a canonical payload and a command ID derived from the payload. The command log, the traces, and the trainer mask store the payload or its ID. Nothing stores a position in the legal list.
- Integer arithmetic only in rules. The geometry lives on the exact lattice (x integer, y an integer with an implicit factor of the square root of three). No float in a rules path.
- A client has no rule logic (AR-06). It shows the view and the legal list that the host sends, and it sends `los_request` for a line of sight answer. A rule function in the client bundle is a defect, and TC-40 finds it. The desktop window is the same kind of consumer: it speaks the host protocol and holds no rule table.
- The host keeps the authoritative state and calculates the hash. The client sends intents only. Each outbound message, prompt, trace, log line, and public replay is a per-player view. No opponent-hidden unit goes out of the host in the other player's view.
- No Avalon Hill art, scan, board layout, rulebook text, or card text in the tree, in fixtures, in screenshots, or in artifacts. Reference material lives in `background/reference/`, which git does not record, and it stays on the owner's machine.
- "Squad Leader" and "Avalon Hill" are not the brand. Descriptive text has the non-affiliation notice.
- The throughput gate (3,500 environment steps/s, NFR-01) is measured before the first long training run. If it is not satisfied, the core moves to Rust as its own milestone. Do not propose Rust before the measurement.
- Model output is data. The harness validates it against the schema and does not run it.
- A rule that the text leaves open gets a project ruling in `src/sldata/rulings/project.json` with its cause, before the code that reads it.

## Defensive engineering rules

The project rules are in `.claude/claude-code-rules.md` and the hooks in `.claude/hooks/` enforce them on each write. In short:

- No emoji or Unicode symbols in code, output, or documentation.
- Never declare code "complete" or "working" without a test that ran.
- No stubs, no placeholder results, no substitute objects in tests. A deferred feature gives an error that names the tier it waits for.
- `*.key.txt` files hold the API keys at the project root. They are on the first line of `.gitignore`. Do not commit them, do not print them, and do not put them in a log or a trace.
- Error handling at each boundary (WebSocket, provider HTTP, file, subprocess) with typed exceptions, timeouts, and fallbacks. No defensive code inside the core.
- Surgical changes. Touch only what the task makes necessary.
- Update `CLAUDE.md`, `README.md`, and `VIBE_HISTORY.md` when a module, an interface, or a data format changes.
- The owner does all writes to git. Never commit, stage, push, branch, or make any other git write, and do not mention git, commits, or commit status in a report or a question.

## What to do at session start

1. Read `VIBE_HISTORY.md` newest entry first.
2. Read `tasks/todo.md` and find the current slice.
3. Read `tasks/lessons.md`.
4. Run `hybrid_search` on the memory server for "Squad_Leader_AI" and the current slice topic.
5. State the slice, the gate, and the first file you will write. Then write real code with its test.

## Style

- All chat responses and all project documents are in ASD-STE100 Simplified Technical English. Run `python ~/.claude/skills/ste100/scripts/ste_check.py <file>` on each document before you give it to the owner. The project allow-list is `.ste-allow`. Exit code 0 is the bar.
- Prose-first architecture documents. Say the cause of each decision, the alternative, where it breaks, and the mitigation.
- Direct, plain, no business-speak, no hedges without a cause, sentence-case headings, real citations only.
- Mermaid in the portable subset: no HTML line breaks, no quoted subgraph titles, no edge labels, no punctuation in node labels.

## The success-claim guardrail

Do not declare an iteration, a tier, or a version "shipped", "closed", or "complete" before two things occur. One: a minimum of one real call against each external service in the tier gave data. Two: the gate in `docs/SUCCESS_CRITERIA.md` has a run artifact. Stub-based tests are checks of the wiring, not validation.

## Where the code lives

The target layout is `docs/ARCHITECTURE.md` section 11. Slice 1 (2026-09-07) added `src/slcore/geometry.py`, `state.py`, `rules/r07_los.py`, `los_cache.py`, `los_eval.py`, `src/sldata/tables/terrain.json`, `src/sldata/loaders.py`, and `tests/los/`. The loaders live in `sldata`, not in the core, because the core reads no files. Slice 2 (2026-09-07) added `game.py`, `units.py`, `scenario.py`, `commands.py`, `frame.py`, `phases.py`, `rng.py`, `hashing.py`, `engine.py`, `rules/r05_movement.py`, `r06_stacking.py`, `r21_setup.py`, the counter and scenario data, `slagents`, and `slcli`. Slice 3 (2026-09-07) added `tabledata.py`, `paths.py`, `rules/r08_fire.py` to `r20_close_combat.py` and `victory.py`, the IFT and close combat tables, the official and project rulings, scenario 1, `slboards` (the first generator pass), the scripted agent v1, and `tests/conformance/`. Slice 4 (2026-09-07) added `src/slruns/` (the artifact writer, the SQLite index, Elo), `slcli/tournament.py`, `slcli/gates.py`, `slcli/runs_cmd.py`, and `tests/artifact/`. 

Slice 5 (2026-09-08) added `src/slcore/view.py`, `src/slhost/` (protocol, rooms, server), `src/slcli/host_cmd.py`, the TypeScript client in `client/`, `tests/host/`, and `tests/browser/`.

Slice 6 (2026-09-08) added `src/slboards/tiles.py`, `wfc.py`, `polygons.py`, `reference.py`, the five-pass `generator.py`, `src/slcli/boards_cmd.py`, `tests/boards/test_geomorphic.py`, `test_zone_setup.py`, `test_reference.py`, and `test_boards_command.py`. Zone set up areas name a band of columns or of rows, a distance to the other band, and a rank by building size, and the generator makes a board that holds them. Scenario 1 (2026-09-13) has its front along the rows, as the card does: the Germans in rows 5 to 7 and the Russians in rows 1 to 4 within three hexes of them.

Slice 7 (2026-09-08) added `src/slcore/rules/r22_flamethrower.py` to `r27_sewer.py`, the counters of rules 23 to 27 in `game.py`, the concealment tokens in `view.py`, `src/sldata/scenarios/s02_tractor_works.json` and `s03a_streets_of_stalingrad.json`, `tests/conformance/cases/rules_22_27.json`, `tests/secrecy/`, and `tests/engine/test_scenarios_2_and_3a.py`. The long measurement of a success criterion has the `gate` marker, and `pytest -m gate` runs it. Slice 8 added `sl-cli agents --list` and `sl-cli agents --games 100` (the TC-15 gate), and the `--traces` option on `sl-cli play`, `sl-cli tournament`, and `sl-cli host`.

Slice 8 (2026-09-08) added `src/slagents/scripted/v2.py` (the engineer agent), `src/slagents/tuned/traces.py` (the trace writer of FR-60), `src/slcli/agents_cmd.py`, `tests/lan/`, and `tests/agents/`. Slice 18 added `src/slagents/scripted/v3.py`, the tanker, which is the agent that plays rules 28 to 41.

Slice 9 (2026-09-08) added `src/slagents/learned/` (encoding, env, nets, ppo, league) and `src/slcli/train.py`. The shaped reward (2026-09-12) is `src/slagents/learned/reward.py`. A win pays 100. A loss, a draw, and a truncation each cost 100. Each step pays the terms of RV-9 table A (find, fire, hurt, kill, cover, sneak, exposed, hide, survive, the objective), with the national weights of table B for the army of each side. The counts are zero-sum and the weights are not. `sl-cli train` has `--discount`, and the update divides the reward by `reward_scale`. `--player 0`, `1`, or `both`: with `both` the learner takes the other side at each new game. `--opponents v7` makes the named agents the only league members, and no snapshot of the learner goes into the league (2026-10-13). `--jump-start v7` is Jump-Start RL (`src/slagents/learned/jumpstart.py`, 2026-10-13). The guide plays the learner's side in the first `--jump-start-turns` turns of each game. It does not play the last turn. When the learner wins `--jump-start-threshold` of the last `--jump-start-window` games at one horizon, the guide plays one turn less. It works only with `--workers 2` or more. The run artifact records each change of the horizon. `--value-warmup 100000` trains the value head alone in the first 100,000 decisions, with the trunk and the policy heads fixed (PIRLNav, 2026-10-13). The value head of a clone has the returns of the teachers' games and not of its own games. A scripted opponent in the league holds one agent for each side and plays the side of the frame. Each TC-18 row has the five counts (won, lost, drawn, truncated, repeated) and the same counts for each side in `by_side`. The `train` extra is necessary for them: `pip install -e ".[train]"` gives torch, numpy, PettingZoo, gymnasium, and TensorBoard. The `sl-cli train` command is in the command list only when they are installed. `src/slagents/learned/agent.py` gives a trained snapshot the Agent interface, so it plays in a tournament, a gate, and a real game. The name `learned:<snapshot>` in `make_agent` builds it, and it needs the `train` extra for torch. It scores the legal commands of the frame with the policy's three heads and returns the ID of the best one, so the ID is always a legal command. The default choice is the action first (2026-10-13): the agent adds the probability of the legal commands of each action and plays the best command of the action with the highest sum. The argmax of the joint score ended each phase with no infantry move. The cause: the policy divides the probability of a move between many units and hexes. A seed turns on sampling. A pickup and a drop are free (rule 5.7), so a second pickup or drop of a weapon in one phase goes after each other command in the agent, and the environment's masks leave it out (`SquadLeaderEnv.choices`; `groups` stays the whole legal list for `step` and the scripted agents). The agent and the masks treat a second board or debark of one unit in a phase the same way (2026-10-13).

Slice 10 (2026-09-08) added `src/slagents/prompted/` (keys, providers, schema, router, harness), `src/sldata/providers.json`, `tests/providers/`, and `tests/agents/test_model_agent.py`. A model agent is `model:openai` or `model:local+openai` in the agent name.

Slice 11 (2026-09-08) added `src/slcli/traces_cmd.py`, `src/slcli/finetune_cmd.py`, `src/slagents/tuned/finetune.py`, and `src/slagents/tuned/export.py`. The `finetune` extra is necessary for the fine-tune: `pip install -e ".[finetune]"` gives transformers, peft, datasets, and accelerate.

The 3D board view added `src/slwindow3d/` (`mesh.py` for the hex prisms, `counters.py` for the counter cards, `app.py` for the Panda3D window), `src/slcli/window3d_cmd.py`, and `tests/window3d/test_board3d.py`. It is a new consumer of the same board document and view document the pygame window reads, and it holds no rule (AR-06). The elevation of a hex lifts its prism, so a hill stands up in three dimensions. The `view3d` extra is necessary: `pip install -e ".[view3d]"` gives panda3d. `sl-cli window3d --screenshot PATH` renders one board offscreen and needs no display; `sl-cli window3d --agents v4,v1` watches a game of two computer opponents.

The GitHub line (2026-09-16 to 2026-09-25) and the 3D line of this machine (2026-10-10) came together on 2026-10-10. The GitHub line split the engine into `src/slcore/api.py` (the public names), `actions.py` (one handler for each command action), `handlers.py`, `turn.py` (the phases and the automatic steps, `AUTO_STEPS`), and `windows.py` (the windows of `phases.PHASE_STEPS`). `src/slcore/player_state.py` gives each agent the state that its player may know, and `slagents.base.decide` is the one way an agent decides. It also added `src/slhost/annotate.py` (the unit names, the labels, the hexes, and the odds of each legal entry), `src/slhost/savegame.py` (a save file of each host game, `--resume`), the per-viewer log streams of `slhost/server.py` (AR-09), the rule 18 berserk rules, `src/slagents/scripted/v7.py` (the odds agent), `src/slagents/registry.py`, `sl-cli evolve`, `src/slshape/`, and PR-31 to PR-53. The browser client sources that its tests compare with (`client/src/`) were not in that line; this tree keeps the older client, so 28 tests of the client tables fail until the newer client comes in.

The 3D window is the MVP front end: the owner uses only this UI. Its play input is the GitHub one: a click on a hex puts a unit in focus, the overlay shades its options, and the list on the right (`slwindow.choice.Chooser`) plays a command. The 3D line added the scenario card before the game (`src/slwindow3d/briefing.py`; the host starts on Begin, `--no-briefing` skips it; each playable scenario has a `situation` field for the players, and `notes` stays the provenance record), the fire animations (`firekinds.py` sorts the log lines into kinds and `effects.py` animates them, with the historical tracer colours of each army), and the sound (`sounds.py` makes each sound in code, except the vehicle, which is a part of the owner's tank recording `src/slwindow3d/assets/tank_drive.wav` (2026-10-11; `python tools/make_tank_sound.py` makes it from `background/Tank_Noise.m4a`), and `audio.py` plays them from a Panda3D ramdisk; Ctrl and m mutes, `--mute` loads no audio library). The two windows take `--agent easy|normal|hard` (v5, v6, v7: `slcli.window_cmd.DIFFICULTY`), save each game to `--save-dir`, and go on with one by `--resume`. The vehicles of v3, v6, and v7 drive and fire with `src/slagents/scripted/armor.py`: a route to a firing position out of panzerfaust range, hold and fire, overrun only a weak target. The combined-arms pass (2026-10-11, v3.2, v6.3, v7.1) puts RV-9 P4, P6, P7, and P13 in that policy: a firing position pays for its distance from the own infantry, a screened tank may stand nearer the enemy, the section bounds by halves in contact with one tank on watch, the tanks fire as a section, and a tank prefers a side or rear shot and turns its front to the largest threat. The squads of the attacker escort a tank in contact (`escort_bonus`). The `tank_*` parameters of v7 map to `armor.ArmorParameters`, and `sl-cli evolve --only` searches them; a search of them needs scenario 4. `tests/window3d/conftest.py` stops the Panda3D tests while a live `sl-cli window3d` runs.

`docs/images/` holds the pictures of the documentation. `python tools/make_docs_images.py` writes them and `docs/images/MANIFEST.json`. It is the one directory of the tree with an image: the release audit gives a finding for an image that the manifest does not name, and `tests/docs/test_documentation_images.py` makes each picture again and compares it (SR-07, TC-29). Run the tool after a change to the board drawing.

Slice 20 (2026-09-08) is the terrain drawing. `src/slwindow/theme.py` holds one set of colours for the window, and `client/src/board/render.ts` holds the base tone of each terrain. `tests/browser/test_render_constants.py` compares the two. The shapes come from a study of the owner's photographs in `background/`, which git does not record. `docs/ASSET_PROVENANCE.md` records what the study gave and what is the project's own.

Slice 19 (2026-09-08) is generator version 7: the east to west road holds one row index for each column, and `connect_roads` attaches each road entry of FR-24 to the network. The window camera multiplies the y value of the lattice by the square root of three, which is the constant `client/src/board/geometry.ts` uses.

Slice 18 (2026-09-08) added the armor game and the desktop window. The armor rules are `src/slcore/rules/r28_vehicles.py` to `r38_fate.py`, with `src/sldata/tables/vehicle_movement.json`, the vehicle counters of the three armies, and `src/sldata/scenarios/s04_armor_probe.json`. The window is `src/slwindow/` with `src/slcli/window_cmd.py`. The tests are `tests/armor/`, `tests/window/`, and `tests/conformance/cases/rules_28_41.json`.

An overrun (rule 35) is declared when the vehicle enters the hex and resolves at the end of the Defensive Fire Phase that follows (PR-54), in the automatic step `resolve_overruns` before the push out of PR-51. The vehicle field `overrun_hex` holds the declaration; it is in the state document only when it is set.

An infantry unit boards or debarks one time in each Movement Phase (PR-55, 2026-10-13). A passenger debarks only when its vehicle has the two movement points of rule 31.3 left. The unit field `rode` holds the board or the debark until the end of the player turn. It is in the state document only when it is set, so the hash of a game with no board or debark stays the same.

Portage is in half points since slice 18, because rule 37.35 gives the panzerfaust half the cost of a machine gun. `UnitType.portage_squad_halves` and `free_portage_halves` are the fields to read. `r06_stacking.hex_load` gives full points, because rule 6.1 gives its limit in full points, and it rounds up.

The game farm (2026-10-14) is `src/slfarm/` (`protocol.py`, `server.py`, `client.py`) and `src/slcli/farm_cmd.py`, with `tests/farm/`. Each Ubuntu host runs `sl-cli farm serve`, and `sl-cli gauntlet` and `sl-cli evolve` send it games with `--remote tars,case,kipp,plex` and the key file `--remote-key farm.key.txt`. A job is a scenario, a seed, and two scripted agent names, and the host checks each one. The farm refuses a learned agent and a model agent. The connection proves the key with an HMAC of a nonce, and the host and the client compare a hash of `src/`, so run `python tools/farm_deploy.py [host]` after a change: one ssh connection for each host copies the code, the key, and `tools/farm_worker.sh`, and runs that script, which installs and starts the worker. `_play_all` of `slcli/gauntlet.py` takes the farm, and the results come back in the order of the jobs, so the artifact is the one a single machine writes. `slfarm` does not import `slcli`; the command gives the server the function that plays one game. PPO workers on the farm (2026-10-14): `sl-cli train --remote ... --opponents v7` opens `--remote-envs` environments on each host (default: its slots). A host runs the loop of `slagents.learned.workers.worker_main` in a process for each environment, and a bridge process for each host on the workstation (`slfarm.client.host_bridge_main`) gives the trainer a pipe end to each, so `ppo.collect_parallel` does not change. The bridges are processes because 44 bridge threads in the trainer took its interpreter lock. `ppo.wait_any` waits on more than 63 pipes, the limit of one wait on Windows. The commands and the decisions go as checked JSON (`slfarm/envwire.py`), the arrays as base64 with a dtype and a shape, never as pickle. The farm refuses a snapshot opponent.

## Common dev commands

```
python -m venv .venv
# Linux or macOS:     source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest tests/
```

The venv path is `.venv/bin/` on Linux and macOS and `.venv\Scripts\` on Windows. Activate the venv one time, and then the commands below are the same on each system.

Slice 2 added `sl-cli play --headless --verify` and `sl-cli bench --workers 1,8,16` (run them with `sl-cli` when the venv is active). Slice 3 added `--scenario s01_guards_counterattack` and the `v1` agent. 

Slice 4 added `sl-cli tournament`, `sl-cli gate`, and `sl-cli runs --rebuild`. Slice 5 added `sl-cli host`, and the client build is `cd client && npm install && npm run build`. Slice 6 added `sl-cli boards --count 1000` (the TC-14a gate) and `sl-cli boards --write <directory>` (the board documents for the owner's scoring session). Slice 9 adds `sl-cli train`. The imitation start (2026-09-14) adds `sl-cli imitate`: `src/slagents/learned/imitate.py` plays games of the scripted teachers in the environment, fits the policy to their decisions by cross entropy on the three heads, and writes a training snapshot. The fit keeps the weights of the epoch with the lowest holdout cross entropy. `--labels 0=v3,1=v3` names the teacher whose command is the label of each side; it has no default (2026-10-12), so without it each teacher labels its own decisions. `--side-weights 0=1,1=0` fits the decisions of player 0 only (2026-10-13). `sl-cli train --start-from <snapshot>` continues from it, and the snapshot's shape replaces `--channels` and `--hidden`. Slice 11 adds `sl-cli traces` and `sl-cli finetune`. Slice 12 adds `--type` to `sl-cli boards` for the four board types, and `python tools/audit_release.py`, the release audit of the tree and the served page.

Slice 13 adds `sl-cli campaign`, the design-your-own tools of Game Set IV.

The strong-AI pass (2026-09-12) adds `sl-cli gauntlet`, the evaluation gauntlet. It plays a round-robin of a candidate agent and a panel across one scenario or more, feeds every game into one shared Elo pool, and prints a leaderboard with a Wilson interval on each agent. `--anchor-only` plays the candidate against each panel agent only. The report has the side baseline (2026-10-14): for each opponent and each side, the wins of the candidate, of the other panel agents, and with `--mirror` of the opponent against itself, because a one-sided scenario hides the skill of an attacker. It is the honest measure that every agent change is judged against, in place of a single win rate against one opponent. The same pass adds the `v5` scripted agent (`src/slagents/scripted/v5.py`, `v5` or `v5:<nation>`): it adds enemy vehicle fire to v4's threat map and fires to suppress the defender that covers its advance lane. Measured agent against agent on the vehicle-free scenario 1 it is even with v4 (50/50 in 120 games); the vehicle-threat change matters against an opponent that drives armor, which the current agent panel does not exercise. The same pass gives the learned trainer a device: `sl-cli train --device cuda` (or `auto`, the default) runs the policy and the update on the GPU, and `--channels` and `--hidden` size the net. Before this the pipeline built every tensor on the processor and the card did no work.

The tempo pass (2026-09-12) adds the `v6` scripted agent (`src/slagents/scripted/v6.py`, `v6` or `v6:<nation>`). The attacker keeps a schedule, and a pressed unit stays out of prep fire. The path is a field that the threat weights, and the agent compares a stand with a step. A move keeps the stacking limit. The plan divides the force between the nearest target buildings, with a garrison in each taken one. The defender holds the buildings that the condition of the attacker names.

Agent v6 is the first agent that wins scenario 1 as the Russian attacker against a random German (28 of 30). The Elo of the gauntlet comes from the full result list (`slruns.elo.settled_ratings`, a Bradley-Terry fit). One pass of the update rule gave a rank by the order of play.

Slice 18 adds `sl-cli window`, the desktop window. The `desktop` extra is necessary for it: `pip install -e ".[desktop]"` gives pygame-ce. With no `--connect` the command starts a host in the same process.

Slice 14 adds `src/slboards/compose.py`, the board composition of FR-29, and the `board_composition` field of a scenario. Slice 15 adds `src/slcore/rules/r42_hidden.py`, the hidden initial placement of rule 42, and the `hidden_placement` field of a scenario. Slice 16 adds `src/slcore/rules/r44_rural.py`, the rural terrain of rule 44, and the `cliffs` style of the generator. It also adds `src/sldata/tables/armor.json` with `load_armor`, the four tables of rule 33. Slice 17 adds `sl-cli host --agents v1,v2`, a game between two computer opponents that a browser watches, and `tests/browser/test_computer_vs_computer.py`, the harness that plays one to the end.

## User context

- Owner: Ron Dilley. Senior security engineer. Windows 11 workstation with one NVIDIA GPU, PowerShell primary shell, Git Bash available. Runs a llama-server (OpenAI-compatible) on the LAN for local model tests.
- Preferences: GPL-3 or BSD for the owner's code, not Apache-2.0. Python for the family of projects in `G:\git\`. Terse, no preamble, no AI-tell writing.
- Related projects: `LocalLLMPerf_AI` (run artifact pattern, OpenAI-compatible endpoint), `SpaceWar_AI` (league self-play in raw torch), `llm_compare` (provider abstraction), `HoneyAI` (provider router and key discovery), `DungeonsOfDreagoth` (key loader).

# Squad_Leader_AI: Requirements

Status: Draft v0.4, after the second multi-AI review (architecture) and the requirements of 2026-10 (the 3D window, the library, the farm, the package, and the collection)
Author: Ron Dilley
Last updated: 2026-10-28
Companion documents: `VISION.md` (direction), `SUCCESS_CRITERIA.md` (measurable outcomes), `ARCHITECTURE.md` (design), `2026-09-07_Squad_Leader_Digital_Edition_Research.md` (evidence), `../tasks/discovery_notes.md` (the input brief, historical)

<!-- AI review 20260907-160656 (gemini, xai, openai): re-tiered into v0.1 to v0.4 plus RC, with topology, throughput, geometry, secrecy, and scenario-mode edits. Owner directive 2026-09-07: the tuned local model is a fourth agent family. -->

Requirement keywords follow RFC 2119: MUST, SHOULD, MAY. Each requirement has an ID for traceability. Each requirement has one sentence of justification or a pointer to its source.

## 0. Context, terms, and tiers

### 0.1 Context

The game is an edition of the 1977 Avalon Hill board game Squad Leader, with the 4th edition rules. It plays in a window of its own on Windows and on Linux, and in a browser. It has one rules core with no input or output.

The core is the engine for the two windows, the browser client, the local host, the reinforcement learning trainer, the model agent harness, and replay. The farm hosts and the collector also use it. The owner selected a Python core first, with a throughput gate that decides a Rust port (see AR-05).

The project is GPL-3 and non-commercial. The repository is `Squad_Leader_AI`. The public title of the game is "Squad Leader Expeditionem" (owner, 2026-09-18, SR-08).

### 0.2 Terms

- Core: the rules engine. No input, no output, no network, no file access.
- Host: the local process that owns the authoritative game state, applies commands through the core, and gives each player a view. The host runs on the owner's machine for hot seat and on one player's machine for LAN.
- Client: a front end. The 3D window (`sl-cli window3d`), the 2D window (`sl-cli window`), and the browser page are clients. A client shows a view and sends intents. It has no rule logic.
- Command: one player intent (unit, action, target, or end phase) that the host applies.
- Environment step: one agent decision, which is one command. This is one PettingZoo step. Steps/s means commands applied each second, with the legal-command list and the observation built for each.
- Scripted agent: an opponent that follows constant code with named parameters.
- Learned agent: an opponent with a policy that is a neural network from reinforcement learning.
- Prompted model agent: an opponent that selects from the legal list through a language model with no training on this game, local or SaaS.
- Tuned model agent: an opponent that selects from the legal list through a local language model, small or large, that is fine-tuned on this game's traces. Owner directive of 2026-09-07.
- Agent family: one of the four kinds above. The tournament compares all four on the same scenarios.
- Reference mode: play on one of the four 1977 layouts, from private data on the owner's machine. Never shipped.
- Generated mode: play on a board from the generator, with scenario set up areas resolved by zone. The public build ships this mode only.
- Library scenario: one of the 12 project scenarios `lib01_grain_office` to `lib12_the_long_front`. A project tool makes each one from a slot of `src/sldata/library/slots.json`.
- Farm: the Ubuntu hosts that play games for the workstation (`sl-cli farm serve`). At this time they are tars, case, kipp, and plex.
- Package: the PyInstaller folder and archive that `tools/package.py` builds for players.
- Collector: the HTTP server that keeps the games that persons played (`sl-cli collect serve`).

### 0.3 Tiers

Each requirement has one tier tag. The tiers are sequential, and each has an exit gate in `SUCCESS_CRITERIA.md`.

- v0.1, headless rules proof: the core for scenario 1, one generated city fixture, one scripted agent, command log, hashes, replay, conformance corpus, throughput benchmark.
- v0.2, browser hot seat: the client against a local host, scenario 1 in hot seat, the tabletop switch, the action log panel.
- v0.3, scenarios and LAN: rules to 27, scenarios 2 and 3A, three scripted agents, the LAN host with per-player views, the tournament runner.
- v0.4, agents that learn: the PettingZoo environment, the learning ladder, the snapshot league, one local prompted model agent, one SaaS prompted model agent, and the tuned model agent test.
- RC, release candidate: the last art pass, four board types, the look and counter rubrics, the content audit, the public title.
- MVP (2026-10-10 on): a person plays a full game in the 3D window. This tier also has the scenario library, the farm, the package, and the collection.
- Scale: year two (rules 45 to 63, unattended league, play by email, an Internet collector, tuned model at scale).
- vNext: year three or a decision that is not made at this time (gamette overlays, community scenarios, public play).

ID prefixes: FR functional, NFR non-functional, SR security, IR integration, DR data, OR observability, OP operational, AR architectural, MR maintainability, TR testing.

## 1. Functional requirements

### 1.1 Rules core

FR-01: The core MUST apply rules 1 to 27 of the 4th edition text. Scenario 1 uses rules 1 to 21. Scenario 2 adds 22 to 26. Scenario 3A adds 27.

*v0.1 for rules 1 to 21. v0.3 for rules 22 to 27.* Source: the "Rules Introduced" line of each card, RV-2 section 3.

FR-02: Each rule application in the core MUST have the rule ID from the 4th edition text as a code-level reference. The action log MUST have the same ID.

*v0.1.* Source: Vision bet 1.

FR-03: The core MUST run the eight phases of each player turn as a state machine that follows the "Advanced Sequence of Play" on page 41 of the rules.

*v0.1.* Source: discovery notes section 6.2.

FR-04: The core MUST give the full list of legal commands for the active player in the current phase, with a short ID for each command.

*v0.1.* Source: research implication 9 and RV-5 section 2. The mask for the trainer and the list for the model agents are the same list.

FR-05: The core MUST reject a command that is not in the legal list, with a message that names the rule ID that makes it illegal.

*v0.1.*

FR-06: The core MUST write an action log entry for each rule application. The entry MUST have the rule ID, the dice values, each modifier with its cause, and the result for each affected unit.

*v0.1.* Source: RV-8 signal 1.

FR-07: The core MUST encode each official Q and A ruling that affects the rules in scope, with the rule number it refers to.

*v0.1 for rules 1 to 21. v0.3 for 22 to 27.* Source: rules pages 27 to 29 and Vision bet 1.

FR-08: The rules give the players a choice in four places: rule 8.7 predesignation, the optional rule 16 semi-simultaneous method, optional rule 17.5, and optional rule 25.4. The core MUST give each choice as a scenario-level switch. The switch value MUST be part of the state hash.

*v0.1.*

FR-09: The core MUST support concealment counters, dummy stacks, and the concealment rules of section 25, including the area fire halving.

*v0.3.*

FR-10: The core MUST support Hidden Initial Placement (rule 42) so that the owner of hidden units sees them and the opponent does not.

*Scale.* The rule is in Game Set II, but the solo community names hidden placement as its unsolved problem.

FR-11: The core MUST roll all dice from one seeded generator that lives in the core. No other component MAY roll dice.

*v0.1.* Source: RV-7 section 5.

FR-12: The core MUST replay a game from the seed and the ordered command list and get the same state at each step.

*v0.1.* Source: RV-7 section 5.3.

FR-13: The core MUST calculate a hash of the game state after each command, and a replay MUST stop at the first hash mismatch.

*v0.1.*

FR-14: The core MUST apply the victory conditions of a scenario at game end and give the result with the cause.

*v0.1.*

FR-15: The core MUST support sewer movement (rule 27) for scenario 3A.

*v0.3.*

FR-16: The core MUST support rules 28 to 63 (armor, Game Sets II and III). Rules 28 to 41 are done: `src/slcore/rules/r28_vehicles.py` to `r38_fate.py`, with the tables in `src/sldata/tables/armor.json` and `vehicle_movement.json`, from pages 11, 13, and 15 of the rulebook. Rules 45 to 63 stay open, and rules 47 and 51 are the next of them.

*Scale.* Source: research open question OQ-R1.

FR-17: The core MUST support the Game Set IV design-your-own rules: random scenario construction, the point value chart, and the campaign game.

*Scale.*

### 1.2 Scenarios and data

FR-18: A scenario MUST be a data file that follows the scenario card schema in RV-2 section 4: number, title, place, date, boards and orientation, set up sequence, turn count, force lists, set up areas, victory conditions, special rules, variations.

*v0.1.*

FR-19: Scenario 1 MUST play from its data file in v0.1. Scenarios 2 and 3A MUST play from their data files in v0.3. Variation 3B (armor) waits for FR-16. Each scenario file MUST list the rule IDs it uses.

*v0.1 and v0.3.*

FR-20: The printed scenarios 4 to 12 are out of the project. FR-69 replaces this requirement.

*Replaced on 2026-10-16.* Source: owner directive 2026-10-16.

FR-21: A scenario file MUST give its set up areas in two forms: hex lists for reference mode, and zone definitions for generated mode (for example "stone buildings in the western third"). A generated board of the scenario's type MUST satisfy the zone definitions.

*v0.1 for the format. v0.2 for the first zone resolution on scenario 1.* Source: consolidated review, contradiction 6.

FR-22: The scenario text (narrative, victory conditions, special rules) in the project MUST be a paraphrase, not the card text.

*v0.1.* Source: RV-4 section 3(f).

### 1.3 Boards and line of sight

FR-23: A board MUST be a data structure of 33 columns by 10 rows with half hexes on all four edges, as in RV-2 section 1.2.

*v0.1.*

FR-24: A board MUST have the geomorphic connections that all four 1977 boards share. The woods half hexes are at columns F, H, J, L, V, X, Z, and BB on the long edges. The road entries are at I1, Q1, Y1, I10, Q10, Y10, A5/A6, and GG5/GG6.

*v0.1.*

FR-25: The generator MUST make a board of one of the four types (city, hills, village, rural) from a seed, with the edge constraints of FR-24.

*v0.1 for one city fixture. RC for all four types.*

FR-26: The generator MUST accept style parameters that control the density and placement of buildings, woods, hills, roads, walls, hedges, grain, and shell holes.

*RC.*

FR-27: The core MUST load a reference-mode layout from a local path that git does not record. Then a printed layout plays on the owner's machine. Default tests MUST NOT load reference-mode data. Committed fixtures, screenshots, and public run artifacts MUST NOT hold reference-mode data.

*v0.2.* Source: owner decision on 2026-09-07 and the consolidated review.

FR-28: The core MUST calculate line of sight as a center-to-center segment tested against terrain polygons for each hex, as in rules 7 and 43. The geometry MUST live on an exact integer lattice, and the tests MUST use integer cross products. The core MUST cache the static LOS geometry for each unordered hex pair for each board at load time.

A rule evaluator MUST apply the context that depends on the firer at play time: the hexside choice of rule 17.7, the smoke and vehicle hindrances, and the machine gun penetration sequence.

<!-- AI review 20260907-163721: openai -->

*v0.1 for rules 7. Scale for rules 43.* Source: RV-3 section 5.3 and the consolidated review, contradiction 4.

FR-29: The core MUST connect two to four boards along long edges or short edges with 180 degree turns. The board configuration diagrams in RV-2 section 6 give the layouts.

*Scale.* Scenario 4 is the first that uses more than one board.

### 1.4 Clients

FR-30: A client MUST render a board in the 1977 look. The look has flat colors with no gradients, a woods mass with a ragged edge, and brown hill contours with crest lines. It also has gray stone buildings, red-brown wooden buildings, and a hex grid with center dots and grid labels. Each terrain is a shape on the ground, and not a hexagon of color. A building is the plan of a structure that can cover more than one hex.

Three clients do it: the 3D window in `src/slwindow3d/`, the browser client in `client/`, and the 2D window in `src/slwindow/`. The two windows open on Windows and on Unix with no browser. `src/slwindow/theme.py` holds the colors. The browser client holds the base tone of each terrain, and `tests/browser/test_render_constants.py` compares the two files.

*v0.2 for a first pass. RC for the rubric.* Source: discovery notes section 6.6.

FR-31: The client MUST render counters from data with new art. The numbers and their positions MUST agree with the 1977 counters. The silhouettes, colors, and typeface MUST be new or open-license.

*v0.2 for a first pass. RC for the rubric.* Source: RV-4 section 3(d).

FR-32: The client MUST support pan, zoom, and hex hit testing in hex math.

*v0.2.*

FR-33: The client MUST have a tabletop switch that shows or hides the dice, the tables, and the LOS thread.

*v0.2.* Source: RV-8 signal 2.

FR-34: The client MUST have a casual mode and a strict mode. In casual mode the LOS tool is available at all times. In strict mode the tool is available only at the times rule 19.3 lets a player use it. Casual mode MUST be the default for human play.

*v0.2.* Source: consolidated review, gemini on playability.

FR-35: The client MUST show the action log with the rule ID, the dice, and the modifiers for each result, for the two sides.

*v0.2.*

FR-36: Hot seat play MUST run with no remote server. The client connects to a local host process on the same machine.

*v0.2.* Source: consolidated review, contradiction 3.

### 1.5 Play modes

FR-37: The game MUST let two humans play at one screen with the phases in sequence (hot seat), through the local host.

*v0.2.*

FR-38: The game MUST let two humans play from two browsers on one LAN through one host, with a room code as the join credential.

*v0.3.*

FR-39: The game MUST let a human play against a scripted agent in a client. The 3D window is the client of the MVP.

*v0.2.* Against a learned agent, a prompted model agent, or a tuned model agent:

*v0.4.*

FR-40: The game MUST let two agents play a full game with no browser and no human (headless), from the command line.

*v0.1.*

FR-41: The game MUST let two humans play by email through the command log.

*Scale.*

FR-42: The host MUST give each player only that player's view (see AR-09). Concealed stacks, dummy counters, and hidden placement MUST NOT be in the other player's view, in each play mode, prompt, log, or public replay.

*v0.3 for concealment. Scale for hidden placement.*

### 1.6 Agents

FR-43: All agent families MUST use one agent interface: observe the view, get the legal commands, select one command.

*v0.1.*

FR-44: The project MUST ship one scripted agent in v0.1 and three scripted agents with named parameters (aggression, cover preference, fire priority) in v0.3. Each scripted agent MUST have a version, and the run artifact MUST record it.

*v0.1 and v0.3.*

FR-45: The model agent harness MUST give the model a compact text state built from the agent's own view. The state has unit-level annotations (hex, terrain, LOS to the nearest enemies, morale, status) and the legal command list with IDs. The state MUST hold the victory conditions of the scenario card. Each legal command MUST show its odds from the tables of the core (a shot its result and break chances, a move its break chance, a close combat the kill chances, a rally its chance). The odds MUST read the units the agent sees and no other, so a target below a concealment counter has no odds in the text.

*v0.4. The odds and the card since 2026-09-19.* Source: RV-6 recommendation, SR-09, and the gauntlet of 2026-09-19 (a model with the list and no number won 0 of 56).

FR-46: The model agent harness MUST let the model give its analysis in free text first. Then the model MUST emit JSON that a flat schema constrains, with the command ID as an enum of the legal IDs.

*v0.4.* Source: arXiv 2408.02442.

FR-47: When the host rejects a model answer, the harness MUST retry with the rejection message, up to a configurable count with a default of 2. After the last failure the harness MUST apply a scripted default and log the fallback.

*v0.4.* Source: arXiv 2508.07485 and the consolidated review, contradiction 5.

FR-48: The model agent harness MUST send text only. It MUST NOT send board images.

*v0.4.* Source: BALROG.

FR-49: The model agent harness MUST keep the last N of the agent's own plans in the prompt and write a scenario-level lesson at game end.

*v0.4 for the plans. Scale for the lesson memory.*

FR-50: The reinforcement learning environment MUST follow the PettingZoo AEC API with a legal-command mask in each observation.

*v0.4.* Source: RV-5 section 6.

FR-51: The trainer MUST run PPO in raw torch with a unit-by-unit composed command (unit, action, target) and an end-phase command.

*v0.4.* Source: RV-5 section 8.

FR-52: The trainer MUST run a learning ladder before a long run: 1 million steps for a sanity signal, 10 million steps for a pilot, then 100 million to 300 million steps. The trainer MUST run a snapshot league: policy snapshots, versioned scripted agents as constant opponents, opponent sampling by loss rate, and an Elo table against constant opponents.

*v0.4.* Source: SpaceWar_AI sibling, RV-5, and the consolidated review.

FR-53: The trainer MUST support behavior cloning from replays as a warm start.

*Scale.*

FR-54: The project MUST tune the scripted agents with CMA-ES or population-based training on win rate.

*Scale.*

FR-55: The project MUST support prompt evolution for the prompted model agent with win rate, invalid-command rate, and cost as fitness.

*Scale.*

FR-59: A model agent with a median decision time of more than 5 seconds MUST be an asynchronous opponent (the human is told to wait, or takes the turn later), not a real-time opponent. Each run MUST record timeouts and fallbacks with their causes.

*v0.4.* Source: consolidated review, latency budget.

FR-60: The project MUST build a game trace data set for model training. Each trace holds the agent's view as text, the legal command list, the selected command, and the outcome, for each decision. Traces come from headless, hot seat, LAN, and tournament games. The trace MUST come from the acting agent's view only.

*v0.3.* Source: owner directive 2026-09-07 and RV-6 section 6.

FR-61: The project MUST test a tuned model agent. The tuned model is a local language model of 7B to 14B parameters, fine-tuned with LoRA on the trace data set of FR-60. The training target is the selected command, given the view and the legal list. The test MUST report the same metrics as the prompted model agent (OR-02). It MUST also report the tournament result against the other three families on the same scenarios.

*v0.4.* Source: owner directive 2026-09-07, RV-6 section 6 (SPIN, SPIRAL), RV-8 section 4 (the Diplomacy RL report).

FR-62: The tuned model agent MUST use constrained decoding on the legal command IDs on the local server. The constraint is a grammar or JSON schema on llama-server, or a logits mask on the legal IDs where the server supports it. The harness MUST record the invalid-command rate with and without the constraint.

*v0.4.* Source: RV-8 section 4 (valid moves rose from about 50 to about 75 percent with a trie-based logits processor).

FR-63: The tournament MUST compare the four agent families (scripted, learned, prompted model, tuned model) on the same scenarios, with sides balanced. It MUST give the win rates, the confidence intervals, the median decision time, and the cost for each family.

*v0.4.* Source: owner directive 2026-09-07.

FR-64: The project MUST support a subsequent step for the tuned model agent: self-play reinforcement learning on the language model (SPIRAL-style or GRPO with LoRA), only if FR-61 shows that the tuned model beats the prompted model.

*Scale.* Source: RV-6 section 6.

FR-65: The model agent harness MUST offer the model no command that gives the game a position seen in the same turn and phase. A position is the state without its command count. When each legal command gives a seen position, the harness MUST offer the full list, so the agent always has a command. The harness MUST record the count of decisions where it held a command back.

*v0.4, 2026-09-20.* Source: the gauntlet of 2026-09-19, where one game of 40 had 15,837 decisions from a drop and a pickup of one weapon.

### 1.7 Runs, replay, and tournaments

FR-56: Each game and each training run MUST write a self-contained run artifact in `runs/`, as in the sibling pattern: config, seed, versions of the core, the data, and each agent, the command log, the action log, and derived statistics.

*v0.1.*

FR-57: A SQLite index MUST list the runs for cross-run queries.

*v0.3.*

FR-58: A tournament command MUST play N games between two agents, balance sides, and give the win rates with confidence intervals and the Elo update.

*v0.3.*

### 1.8 The 3D window

FR-66: The 3D window (`src/slwindow3d/`, `sl-cli window3d`) MUST be the front end of the MVP. It MUST render the board document and the view document that the host sends. Each hex is a prism, and the elevation of a hex lifts its prism. The window MUST have a 2D camera and a 3D camera.

The window MUST hold no rule (AR-06). It speaks the host protocol and sends intents only. `sl-cli window3d --screenshot PATH` MUST render one board offscreen with no display.

*MVP.* Source: owner directive 2026-10-10 (`tasks/todo.md`, the plan to the MVP).

FR-67: A person MUST play a full game with the mouse in the 3D window and in the 2D window. The play input has these parts:

- the set up tray: a click or a drag puts a counter on a shaded hex, and a click on a placed counter lifts it (`setup_lift`)
- the cause of a refused placement, from the host (`options_request`, `src/slhost/options.py`)
- the reach of a unit in a Movement Phase and its field of fire in a fire phase, from the host
- a click on a reach hex that moves the unit there (`move_to`), one legal step at a time
- the menu of a unit (a right click, or Ctrl and Space), the about box, and the Undo button
- the objective hexes on the map, and the "Victory conditions" box with the count of the side of the person
- the end box, with "You won." or "You lost." for the one human side

*MVP.* Source: the notes of the owner of 2026-10-26 (`VIBE_HISTORY.md`).

FR-68: The 3D window MUST show the scenario card before the game (`src/slwindow3d/briefing.py`). The two windows MUST accept an opponent by its difficulty name: `easy`, `normal`, and `hard` give v5, v6, and v7. The two windows MUST save each game to `--save-dir` and continue a saved game with `--resume`.

*MVP.* Source: `src/slcli/window_cmd.py` (`DIFFICULTY`).

### 1.9 The scenario library

FR-69: The project MUST have a library of 12 project scenarios, `lib01_grain_office` to `lib12_the_long_front`. No part of a library scenario MAY be a copy of a 1977 card. A library scenario MUST use only the rules that are in the core.

`src/sldata/library/slots.json` MUST hold the 12 slots (L01 to L12). Each slot has the board types, the armies, the rule level, and the bands of points and turns.

*MVP. All 12 are in `src/sldata/scenarios/` since 2026-10-18.* Source: owner directive 2026-10-16.

FR-70: Each library scenario MUST be balanced before it goes into the library. The measure is v7 against v7 in 1,600 games on the farm, and the first side MUST win 45 to 55 percent. The search MUST try the board seeds and the draw seeds first. A change of the forces, the turns, or the victory condition comes only when no seed gives the balance.

The notes of the scenario file MUST give the seeds and the balance result. `sl-cli library search` MUST write a run artifact of each search.

*MVP.* Source: owner directive 2026-10-16.

FR-71: Each sentence of a library card MUST agree with the rules and the data of its scenario. A card MUST name a building by its rank and its band of columns, because nothing on the board marks a building. A balanced candidate with a card that has no fault MUST go into the library with no review step.

*MVP.* Source: the owner decisions of 2026-10-17.

### 1.10 The game farm

FR-72: The farm MUST play games for the workstation. Each host runs `sl-cli farm serve` on port 5160. `sl-cli gauntlet`, `sl-cli evolve`, and `sl-cli library search` MUST send games to it with `--remote`. `sl-cli train --remote` MUST open PPO environments on it.

The results MUST come back in the sequence of the jobs, so the artifact is the one that a single machine writes. `--remote-slots N` MUST limit the games at one time on each host.

*MVP.* Source: `src/slfarm/`, 2026-10-14.

### 1.11 The package, the launcher, and the collection

FR-73: `tools/package.py` MUST build a PyInstaller folder and an archive on the system where it runs, for Windows and for Linux. The package MUST NOT hold torch or numpy. The build MUST stop when a `*.key.txt` file is in the folder.

The entry of the package is `src/slcli/frozen_main.py`. With no arguments it starts the launcher, and with arguments it is `sl-cli`.

*MVP.* Source: owner decisions 2026-10-27.

FR-74: The launcher (`sl-cli launch`, `src/slwindow/launcher.py`) MUST show the consent question one time, at the first start. Then it MUST give these choices:

- the 12 library scenarios
- the side
- the opponent: `easy`, `normal`, `hard`, hot seat, LAN host, and LAN join
- the window: the 3D window or the 2D window

The launcher MUST start each game window as a second process of the same program. A LAN host window MUST bind all addresses on `--lan-port` (8731).

*MVP.* Source: owner decisions 2026-10-27.

FR-75: The packaged game MUST save each game to the data directory of the player in all cases. The uploader MUST send a game only when the player gave consent and has a player key. It MUST send only a game with a minimum of one command of a person. A network error MUST NOT stop the game. The uploader tries again at the next start and after the next game.

*MVP.* Source: `src/slcollect/client.py`, `src/slcollect/settings.py`.

## 2. Non-functional requirements

NFR-01: The core MUST give a minimum of 3,500 environment steps/s end to end on the owner's training workstation, with the benchmark specification below. This is the gate for AR-05, measured in v0.1 on the vertical slice and again before the first long run.

*v0.1.* Source: RV-5 section 5 (derived) and the consolidated review, contradiction 2.

The benchmark specification (frozen before optimization starts):

- the hardware manifest: CPU model and core count, RAM, GPU model and driver, Python version, OS build
- worker counts measured one at a time: 1, 8, and 16
- a fixed scenario and board seed set
- the policy that selects commands: the v0.1 scripted agent
- the measurement includes legal-command generation, observation construction, and the state hash, and does not include artifact writes
- median and p95 steps/s, and the sustained rate for 10 minutes
- games/s and steps/s, the two reported
- memory use and worker failures

NFR-02: A legal-command list for one phase MUST be available in less than 50 milliseconds in the browser on the owner's workstation.

*v0.2.*

NFR-03: A full headless game between two scripted agents MUST complete in less than 15 seconds on one core. This is a sanity bound for the CLI and the tests, not a derivation of NFR-01.

*v0.1.* Source: consolidated review, contradiction 2.

NFR-04: A replay MUST give a bit-identical state hash sequence on Windows and on Linux.

*v0.1.*

NFR-05: The core MUST use integer arithmetic only for rules, with the geometry on an integer lattice. No float MAY be in a rules path.

*v0.1.* Source: RV-7 section 5.3 and the consolidated review, contradiction 4.

NFR-06: The browser client MUST render a four-board configuration with 300 counters at 60 frames each second on the owner's workstation during pan and zoom.

*Scale.*

NFR-07: A LAN move MUST get to the second browser in less than 500 milliseconds.

*v0.3.*

NFR-08: The training loop MUST run unattended for 24 hours without a crash.

*v0.4.*

NFR-09: The tuned model fine-tune MUST complete on the owner's workstation (one GPU) in less than 24 hours. The bound applies to the year-one profile: a 7B or 8B base model, LoRA or QLoRA, a fixed context length, generated traces only, and a trace set of a minimum of 200 games. A 14B base is a measurement, not a bound.

<!-- AI review 20260907-163721: openai -->

*v0.4.* Source: RV-6 section 6.

## 3. Security requirements

The threat model: one owner's workstation, a trusted LAN with a second player, and outbound calls to model providers. LAN play is trusted-party convenience. It gives no confidentiality against a hostile machine on the same LAN.

The farm hosts are on the owner's LAN. The collector gets uploads from players of the package. At this time it runs on the workstation on 127.0.0.1, and its deploy to tars waits.

SR-01: API keys MUST live in `*.key.txt` files at the project root or in environment variables. They MUST NOT be in source control. `.gitignore` MUST list `*.key.txt` on its first line. This is a private-workstation practice, not a deployment practice.

*v0.1.*

SR-02: The key loader MUST resolve paths against the project root and skip lines that start with `#`. It MUST fall back to the environment variable, and it MUST mark a provider unavailable if the key is missing.

*v0.4.* Source: DungeonsOfDreagoth sibling.

SR-03: The LAN host MUST bind to the LAN interface only. The room code MUST have a minimum of 128 bits of entropy. The host MUST check the WebSocket origin. It MUST limit connection tries for each address. It MUST give the player slots itself.

*v0.3.* Source: consolidated review, security 3.

SR-04: Model output MUST be treated as data. The harness MUST validate it against the schema and MUST NOT run it as code.

*v0.4.*

SR-05: The provider client MUST send requests only to hosts on an allowlist that comes from the config file: scheme plus host, with the local endpoint as the only private-network entry. No UI and no scenario file MAY set a provider URL.

*v0.4.* Source: HoneyAI sibling and the consolidated review, SSRF.

SR-06: The served page MUST have the FSF LibreJS-style license notice (the GPL-3 section 7 additional permission for minified code) and a link to the Corresponding Source. Serving the bundle conveys object code in the terms of GPL-3 section 6, so the source must be available.

*RC.* Source: RV-4 section 6.

SR-07: The project MUST NOT commit or ship scans, board layouts transcribed from the four 1977 boards, rulebook text, or card text. A release audit MUST scan the source tree, the built archives, the fixtures, the screenshots, and the public run artifacts.

A picture that the project makes from its own code is not a scan. Those go in `docs/images/`, and `docs/images/MANIFEST.json` MUST name each one with the seed that made it. The audit MUST give a finding for an image in that directory that the manifest does not name. A test MUST make each picture again and compare it with the file in the tree.

*v0.1 for the rule. RC for the audit.* Source: RV-4 and the owner decision.

SR-08: The project name and the served page MUST NOT use "Squad Leader" or "Avalon Hill" as the brand. Descriptive text MUST have a non-affiliation notice.

The one exception is the public title "Squad Leader Expeditionem", which the owner named on 2026-09-18. The window captions and the served page MAY show that title. Each place that shows it MUST also have the non-affiliation notice. The release audit accepts the full title and no other use of the two names.

*RC.* Source: the owner decision of 2026-09-18.

SR-09: Prompts to a model and traces for training MUST be built from the acting agent's view only. Logs and run artifacts MUST NOT contain API keys, authorization headers, or opponent-hidden state.

*v0.4.* Source: consolidated review, leak paths.

SR-10: The trace data set and the tuned model weights MUST NOT contain reference-mode board data. Each trace record MUST have a `board_source` field with the value `generated` or `reference_private`. The fine-tune command MUST reject `reference_private` traces unless the owner gives an explicit local-only flag. The weights from such a run MUST stay on the owner's machine. Traces from reference-mode games MUST stay on the owner's machine.

<!-- AI review 20260907-163721: openai -->

*v0.3.* Source: FR-27 and the owner decision.

SR-11: A farm connection MUST prove the farm key with an HMAC-SHA256 of a nonce that the host selects. The key MUST NOT go on the wire. The client MUST refuse a host when the hash of `src/` on the host is not the same as its own. The host MUST refuse a learned agent and a model agent, and it MUST run no code that the network sends. The arrays of a PPO environment MUST go as JSON that the receiver validates, and MUST NOT go as pickle.

*MVP.* Source: `src/slfarm/protocol.py`, `src/slfarm/envwire.py`.

SR-12: Each upload to the collector MUST have the key name, a time, a nonce, and an HMAC-SHA256 with the key of the player. The HMAC MUST cover the method, the path, the time, the nonce, and the SHA-256 of the body. The key MUST NOT go on the wire.

The collector MUST refuse these uploads:

- a time more than 600 s from its clock
- a nonce that it saw
- an unknown key or a revoked key
- more than 30 uploads of one key in 60 s
- a body larger than 8 MB

Each player MUST have a key of their own (`sl-cli collect key add NAME`), so the owner can revoke one key. The key store is `collect_keys.key.txt`.

*MVP.* Source: `src/slcollect/wire.py`, `src/slcollect/keys.py`, `src/slcollect/server.py`.

SR-13: An upload MUST hold only the lines of the save file and the package version. The collector MUST give no game to a client. Its one answer with no key is `GET /v1/ping`. An Internet collector MUST have TLS in front of it. On plain HTTP, the key name and the address of the player go in clear text.

*MVP for the first two sentences. Scale for TLS.* Source: `docs/ARCHITECTURE.md` section 8.1.

## 4. Integration requirements

IR-01: The local model client MUST use the OpenAI-compatible HTTP API at a configured `http://host:port/v1` endpoint and MUST do a `/v1/models` health check at start.

*v0.4.* Source: LocalLLMPerf_AI sibling.

IR-02: The project MUST have one provider interface with a thin adapter for each provider. v0.4 ships the local endpoint and one SaaS adapter (Anthropic). The OpenAI, Gemini, xAI, and Mistral adapters are

*RC*. Source: llm_compare sibling and the consolidated review.

IR-03: Each adapter MUST use the provider's schema-constrained output mode with one flat JSON schema: string enums, no recursion, no numeric ranges, `additionalProperties: false`.

*v0.4.* Source: RV-6 section 3.

IR-04: Each provider call MUST have a timeout and MUST record tokens, latency, cost estimate, and outcome.

*v0.4.*

IR-05: The provider router MUST have an explicit failover sequence with a circuit breaker for each provider.

*RC.* Source: HoneyAI section 7.3.

IR-06: The provider client MUST structure the prompt with a stable prefix so that prompt caching applies where a provider supports it.

*v0.4.* Source: RV-6 section 7.

IR-07: The trainer MUST write TensorBoard scalars for loss, entropy, win rate, and Elo.

*v0.4.* Source: SpaceWar_AI sibling.

IR-08: The tuned model MUST load on the same local server as the prompted local model (llama-server with a GGUF export of the merged LoRA, or an adapter the server supports).

*v0.4.*

## 5. Data requirements

DR-01: The rules tables (Infantry Fire Table, Close Combat Table, Support Weapons Chart, movement costs, terrain modifiers) MUST be project data files in the project's own layout, each with a provenance note that names its source.

*v0.1.* Source: RV-4 section 3(a).

DR-02: The counter data (values, quantities, names, colors) MUST be project data files, with the values from RV-1 sections 2 to 6 and a provenance note.

*v0.1.*

DR-03: The board format MUST hold, for each hex: terrain type, elevation level, building type and dimension, hexside features (wall, hedge, cliff, road), a sewer entrance flag, and a stair flag.

*v0.1.*

DR-04: The command log MUST be an ordered list of commands. Each entry has a sequence number, the player, the phase, the frame ID, the command ID, the canonical payload, and the state hash. The command ID MUST derive from the canonical payload, not from a position in the legal list. The host computes the hash after each command. A client sends intent only and MUST NOT send a hash.

<!-- AI review 20260907-163721: gemini, openai -->

*v0.1.* Source: consolidated review, security 2.

DR-05: A run artifact MUST be a directory `runs/<ISO8601-Z>-<slug>/` with `manifest.json`, `commands.json`, `log.json`, and `stats.json`.

*v0.1.*

DR-06: The reference-mode layouts MUST live in `background/reference/`, which `.gitignore` lists, so that git does not record them.

*v0.2.* <!-- AI review 20260907-160656: openai. The earlier text inverted the meaning. -->

DR-07: The project MUST hold no personal data. Player names in a LAN game are display strings that live for the session only. The one exception is the index of the collector (DR-09), which records the key name and the network address of each upload.

*v0.3.*

DR-08: A trace record MUST hold these fields: the game ID, the decision index, the agent family and version, the view text, the legal command IDs, the selected command ID, and the outcome. Traces MUST live in `runs/` with the game.

*v0.3.*

DR-09: The collector MUST play each upload again through the core (`slcollect.verify`). It MUST keep the game in `games/` when each command is legal and each hash agrees, and in `unverified/` when not. It MUST refuse a game with no command of a person. A game that a player continued comes again with more lines. The collector MUST keep the longer file when the older file is the start of it.

`index.jsonl` MUST have one line for each kept upload: the time, the key, the address, the package, the folder, and the result of the check.

*MVP.* Source: `src/slcollect/server.py`, `src/slcollect/verify.py`.

DR-10: The record of a collected game MUST be the save file of the host (`slhost.savegame`). Each command line MUST have its source (`human`, `computer`, `route`, or `forced`). The collector MUST NOT keep a second format.

The data directory of the player is `%LOCALAPPDATA%\SquadLeaderExpeditionem` on Windows and `~/.local/share/squad-leader-expeditionem` on Linux. `SL_DATA_DIR` changes it.

*MVP.* Source: `src/slcollect/settings.py`.

## 6. Observability requirements

OR-01: Each component MUST write structured JSON logs with a game ID and, where applicable, a turn, phase, and player.

*v0.1.*

OR-02: Each model agent call MUST emit a record with these fields:

- provider and model
- tokens, latency, and cost estimate
- invalid-command flag and retry count
- fallback flag and timeout flag
- constrained-decoding flag

*v0.4.*

OR-03: The trainer MUST emit steps/s, episode length, win rate against each constant opponent, and Elo at a fixed cadence.

*v0.4.*

OR-04: The tournament command MUST keep an Elo history for each agent version, with the agent family.

*v0.3.*

## 7. Operational requirements

OP-01: One command MUST start the local host and the browser client. One command MUST run a headless game. One command MUST run the benchmark. One command MUST start a training run. One command MUST build the trace data set and start a fine-tune.

*v0.1 for headless and benchmark. v0.2 for the host. v0.4 for training and the fine-tune.*

OP-02: The project MUST run on Windows 11 (the owner's workstation) and on Linux.

*v0.1.*

OP-03: The Python target is 3.12 or a subsequent version. The Node target is 20 or a subsequent version.

*v0.1.*

OP-04: A README MUST give the install procedure, the start procedure, and the current status.

*v0.1.*

OP-05: One command MUST deploy the code and the key to the farm hosts (`python tools/farm_deploy.py [host]`). One command MUST deploy the collector (`python tools/collect_deploy.py`). A farm host MUST report success only when its new server holds port 5160.

*MVP.* Source: `tools/farm_deploy.py`, `tools/farm_worker.sh`, `tools/collect_deploy.py`.

## 8. Architectural requirements

AR-01: There MUST be one rules core, with no input or output, no network, and no file access.

*v0.1.* Source: Vision bet 2.

AR-02: Each consumer (client, host, trainer, harness, replay) MUST use the core through a binding or through the host. No consumer MAY re-implement a rule.

*v0.1.*

AR-03: The core MUST be deterministic from a seed, a command log, and the scenario switches.

*v0.1.*

AR-04: The phase state machine, the hex math, the LOS, and the random generator MUST live in the core.

*v0.1.*

AR-05: The core language is Python for v0.1 to v0.3. If NFR-01 is not satisfied on the training workstation, the core MUST move to Rust as its own milestone before the first long training run. The port uses PyO3 and wasm-bindgen bindings. The conformance battery (TR-01) MUST give zero failures on the port before training starts.

*v0.1 gate.* Source: owner decision 2026-09-07 and RV-7 section 1.

AR-06: The client MUST get rule results from the host on a local WebSocket (Python core) or from a WebAssembly binding (Rust core). The client MUST NOT have rule logic.

*v0.2.*

AR-07: The rules data (tables, counters, scenarios, boards) MUST be data files, so that a subsequent gamette overlay is a data change plus a small code change.

*v0.1 for the format. vNext for an overlay.*

AR-08: The provider abstraction MUST follow the sibling pattern: a base class with a response record, provider status, and model preferences, plus presence-based provider discovery.

*v0.4.* Source: llm_compare and HoneyAI siblings.

AR-09: The host MUST keep one authoritative state. It MUST calculate a per-player view for each outbound message, prompt, trace, log line, and public replay. A view MUST NOT contain the other player's concealed or hidden units, their identifiers, or their positions.

*v0.3.* Source: consolidated review, security 1.

AR-10: The four agent families MUST share the agent interface (FR-43), the trace format (DR-08), and the tournament (FR-63). Then a family can be added or removed without a change to the host or the core.

*v0.4.*

AR-11: The farm hosts and the collector MUST apply rules only through the core. `slfarm` MUST NOT import `slcli`: the command gives the server the function that plays one game.

*MVP.* Source: `CLAUDE.md`, the game farm.

## 9. Maintainability requirements

MR-01: Each rule in the core MUST be traceable to its 4th edition rule ID in code and in tests.

*v0.1.*

MR-02: A new rule MUST land as data plus conformance cases plus the code that applies it. No rule MAY land without a test.

*v0.1.*

MR-03: `CLAUDE.md`, `README.md`, and `VIBE_HISTORY.md` MUST be updated when a module, an interface, or a data format changes.

*v0.1.* Source: project rules 6 and 7.

MR-04: `tasks/lessons.md` MUST get an entry after each correction from the owner.

*v0.1.*

MR-05: The code MUST have no stub functions, no empty returns, and no substitute objects in tests. A deferred feature MUST give an error that names the version it waits for.

*v0.1.* Source: project rule 3.

## 10. Testing requirements

TR-01: A JSON conformance corpus MUST cover each rule in scope with a conformance matrix, not one case for each rule. Each rule family MUST have four case types: valid command, invalid command, boundary, and interaction with a second rule family. Each case MUST cite the rule text or the Q and A ruling that gives its expected outcome. Each binding of the core MUST run the same corpus.

*v0.1.* Source: consolidated review, conformance.

TR-02: A determinism test MUST play random legal games from many seeds, replay each log, and compare the last hash. It MUST run on Windows and Linux in automation.

*v0.1.*

TR-03: Property tests MUST cover LOS: symmetry (A sees B if and only if B sees A, rule 43.8), adjacency (rule 7.8), and blind hexes (rule 7.4).

*v0.1.*

TR-04: A throughput test MUST measure NFR-01 with the benchmark specification and write the numbers and the hardware manifest to a run artifact.

*v0.1.*

TR-05: Provider integration tests MUST make real calls to each provider that the tier claims to support and MUST run when the key file is available. They MUST have the `integration` mark, and the test runner MUST skip them when the key is missing. No substitute object MAY replace a provider in these tests.

*v0.4.*

TR-06: A local model integration test MUST play one full phase decision against a real llama-server endpoint, with the prompted model and with the tuned model.

*v0.4.*

TR-07: A browser test with Playwright MUST play the first turn of scenario 1 in hot seat mode.

*v0.2.*

TR-08: A LAN test MUST connect two clients to one host with a room code and play one turn.

*v0.3.*

TR-09: A secrecy test MUST assert that each outbound message, prompt, trace, and public replay contains no opponent-hidden unit, identifier, or position.

*v0.3.*

TR-10: A training smoke test MUST run 10,000 steps of PPO and assert that loss is finite and steps/s is recorded.

*v0.4.*

TR-11: No tier is "shipped", "closed", or "complete" until a minimum of one real call against each external service in the tier gave data. Stub-based tests are checks of the wiring, not validation.

*v0.1.* Source: `SUCCESS_CRITERIA.md` section 4.

TR-12: A fine-tune smoke test MUST run 50 LoRA steps on 10 traces. It MUST assert that loss is finite and that the exported model loads on the local server.

*v0.4.*

TR-13: The tests of the 3D window MUST open it offscreen. No test MAY open a window on the desktop of the owner. The tests of the collection MUST use a real collector on the loopback address and real signed uploads.

*MVP.* Source: `tests/window3d/`, `tests/collect/`, and `tasks/lessons.md`.

## 11. Out of scope for year one

Listed so that they are not argued again. None is rejected. Each has a re-entry point.

- Rules 45 to 63 and variation 3B. Rules 28 to 44 are done (`src/slcore/rules/r28_vehicles.py` to `r44_rural.py`). Rules 47 and 51 come first. Re-entry: FR-16.
- The printed scenarios 4 to 12. The 12 library scenarios replace them (FR-69). No re-entry point.
- The blind fire of rule 42.4. It changes the action space of FR-50. Hidden placement is done in `slcore/rules/r42_hidden.py`.
- Play by email. Re-entry: FR-41.
- Prompt evolution. Re-entry: FR-55. Imitation of the scripted teachers (`sl-cli imitate`) and the evolution of the scripted agents (`sl-cli evolve`) are done.
- Self-play reinforcement learning on the language model itself. Re-entry: FR-64, after FR-61 shows a result.
- Gamette overlays (Cross of Iron, Crescendo of Doom, GI: Anvil of Victory). Re-entry: owner decision in year three.
- Internet play, accounts, matchmaking, and a hosted game server. No re-entry point. A collector on the Internet, with its own name and TLS, is planned before the public release (SR-13).
- AlphaZero, MuZero, and search-based training. Re-entry: after PPO results are in.
- Advanced Squad Leader. No re-entry point.
- Board images to model agents. Re-entry: when a benchmark shows vision input helps.
- A public release. Re-entry: RC. The public title is Squad Leader Expeditionem.

## 12. Open questions

- O-01: Answered on 2026-09-08. The reference endpoint is `http://tars.uberadmin.com:5150/v1`, which the LocalLLMPerf_AI sibling also uses. It is in `src/sldata/providers.json` as the one private-network entry of the allowlist (SR-05). It served `unsloth/Llama-3.3-70B-Instruct-GGUF` on that day.
- O-02: What is the owner's training workstation for NFR-01 and NFR-09 (CPU cores, GPU model and memory)? The benchmark manifest must name it, and the GPU memory decides the largest model that a LoRA fine-tune can use.
- O-03: Which of the optional rule switches in FR-08 is the default for scenarios 1 to 3? Recommendation: the basic method (rules as printed), with optional rule 16 off.
- O-04: Answered on 2026-09-08. Zone-based set up areas (FR-21) move scenario 1 onto a generated city board when the zone says how much room is necessary for a group. All of 1,000 generated boards set the scenario up with ten groups in ten different stone buildings. See `docs/ARCHITECTURE.md` section 7.1.
- O-08: The Point Value Chart of Game Set IV is a graphic on page 34 of the rulebook. The armor tables were the same, and a read of the page as an image gave those numbers. Read the chart the same way, so `slcampaign/points.py` can use the printed scale in place of the project's own.
- O-05: Does the generator produce all four types before RC? Recommendation: one city fixture in v0.1, one village or hills type in v0.3 for variety, all four in RC.
- O-06: Which base model is the first tuned model (FR-61)? Recommendation: a 7B or 8B instruction model with a permissive license that llama-server runs in Q8, so that the constraint of NFR-09 holds. Measure the prompted baseline of the same model first.

## Appendix A: traceability summary

| Cluster | IDs | Primary source |
|---|---|---|
| Rules core | FR-01 to FR-17 | discovery notes section 6, Vision bet 1 |
| Scenarios and data | FR-18 to FR-22 | RV-2 sections 3 and 4, RV-4 section 3, consolidated review |
| Boards and LOS | FR-23 to FR-29 | RV-2 section 1, RV-3 section 5, owner decision, consolidated review |
| Clients | FR-30 to FR-36 | discovery notes 6.6, RV-8 signal 2, consolidated review |
| Play modes | FR-37 to FR-42 | owner decision, RV-8 signal 3 |
| Agents | FR-43 to FR-55, FR-59 to FR-65 | RV-5, RV-6, RV-8, siblings, consolidated review, owner directive |
| Runs and tournaments | FR-56 to FR-58 | LocalLLMPerf_AI and SpaceWar_AI siblings |
| The 3D window | FR-66 to FR-68 | owner directive 2026-10-10, owner notes 2026-10-26 |
| The scenario library | FR-69 to FR-71 | owner directive 2026-10-16, owner decisions 2026-10-17 |
| The farm | FR-72 | `src/slfarm/` |
| Package, launcher, collection | FR-73 to FR-75 | owner decisions 2026-10-27 |
| Non-functional | NFR-01 to NFR-09 | RV-5 section 5, RV-6 section 6, RV-7, consolidated review |
| Security | SR-01 to SR-13 | project rules, RV-4, consolidated review |
| Integration | IR-01 to IR-08 | RV-6 section 3, siblings |
| Data | DR-01 to DR-10 | RV-1, RV-2, RV-4 |
| Observability | OR-01 to OR-04 | siblings |
| Operational | OP-01 to OP-05 | owner environment |
| Architectural | AR-01 to AR-11 | Vision bet 2, RV-7, consolidated review |
| Maintainability | MR-01 to MR-05 | project rules |
| Testing | TR-01 to TR-13 | project rules, success-claim guardrail, consolidated review |

## Appendix B: the initial goal items to the requirements

| Original ask (discovery notes section 4, and the directive of 2026-09-07) | Requirements | Criteria |
|---|---|---|
| EA-1 Find all pieces, maps, rules, scenarios | the research report and appendices, DR-01, DR-02 | TC-01, TC-02, BC-08 |
| EA-2 Maps that look like the board game maps | FR-23 to FR-26, FR-30 | TC-14a, TC-14b |
| EA-3 Tiles that look like the board game tiles | FR-31 | TC-14c |
| EA-4 Human versus human | FR-36, FR-37, FR-38, AR-09 | BC-01, BC-02, TC-23, TC-24, TC-34 |
| EA-5 Human versus computer | FR-39, FR-44, FR-59 | BC-01, BC-03, TC-15 |
| EA-6 Computer versus computer | FR-40, FR-58, FR-63 | TC-04, TC-15, TC-19, TC-35 |
| EA-7 Learning and evolution | FR-50 to FR-55, FR-61, FR-64 | TC-18, TC-19, BC-06, TC-35 |
| EA-8 Local and SaaS models | FR-45 to FR-49, FR-65, IR-01 to IR-06 | BC-03, TC-16, TC-20, TC-21 |
| EA-9 A local model with training on the game as a play family (2026-09-07) | FR-60 to FR-63, IR-08, DR-08, NFR-09, SR-10 | TC-35, TC-36, TC-37 |
| EA-10 A front end that the owner uses (2026-10-10) | FR-66 to FR-68 | BC-01, TC-46, TC-52 |
| EA-11 A library of 12 project scenarios (2026-10-16) | FR-69 to FR-71 | TC-47, TC-48 |
| EA-12 A package for players and a collection of their games (2026-10-27) | FR-73 to FR-75, SR-12, SR-13, DR-09, DR-10 | BC-10, TC-50, TC-51, TC-53 |

# Discovery notes: Squad Leader electronic edition

Date: 2026-09-07
Source folder: `background/`
Status: Phase 1 output of the VIBE init pipeline. This file is the single source of truth for the subsequent phases.

## 1. Goal as given

The user gave the goal in chat on 2026-09-07. This is the verbatim text:

```text
we are going to create a new electronic version of the very old and out of print
squad leader by Avalon Hill. Here are some artifacts in the background folder and
you need to do deep research to find all the possible pieces, maps, rules,
scenarios, etc. The goal is to have a browser based version of the squad leader
game that generates maps that look like the boardgame maps, has tiles that look
like the board games tiles, and has human-vs-human, human-vs-computer, and
computer-vs-computer play with learning and evolution and the use of local models
and SaaS AI models.
```

The rulebook gives the design intent of the 1977 game (rules section 1, page 2):

```text
SQUAD LEADER is more of a game system, than a game. Having mastered this system
the player will be able to simulate (or "game") any comparable scale action of
WWII in Europe.
```

## 2. Principals

| Who | Role | What is important to them |
|---|---|---|
| Ron Dilley | Owner, sole developer, player | A playable browser game that looks like the 1977 board game. AI opponents that learn. Local and SaaS models work. |
| Human opponents of Ron | Players | Correct rules, fair play, a readable map, and a simple procedure to connect to a game. |
| Hasbro (rights holder since 1998) and Multi-Man Publishing (licensee) | IP owners | Their copyright in rules text, board art, and counter art. See open question OQ-1. |
| Squad Leader Academy (SQLA) and the VASSAL community | Prior digital keepers | The VSQL module and the softcopy rules are their work. A new project must credit them and must not copy their graphics without permission. |
| Future Claude sessions | Builders | Clear invariants, a rules engine with rule IDs, and tests that prove each rule. |

## 3. Technical environment

- Project root: `G:\git\Squad_Leader_AI\`. Not a git repository at init time.
- Windows 11, PowerShell primary shell, Git Bash available, Python 3 with `pypdf` and `Pillow` installed.
- Five API key files are at the project root: `claude.key.txt`, `openai.key.txt`, `gemini.key.txt`, `mistral.key.txt`, `xai.key.txt`. They are the same as the copies in `G:\git\AI_Scaffolding\`.
- Sibling projects with related patterns: `SpaceWar_AI` and `Scorched_Earth_MOAG` (Python games with RL agents), `airobots` (multi-LLM battle), `llm_compare` (multi-provider comparison), `DungeonsOfDreagoth` (game port with an AI DM). See section 7.
- Target platform from the goal: a browser. The user gave no server or host constraint.

## 4. Explicit goal items

- EA-1: Find all the possible pieces, maps, rules, and scenarios of the 1977 game. This is a research task, not a build task.
- EA-2: Make maps that look like the board game maps.
- EA-3: Show tiles (counters) that look like the board game tiles.
- EA-4: Support human versus human play.
- EA-5: Support human versus computer play.
- EA-6: Support computer versus computer play.
- EA-7: Computer players must learn and evolve.
- EA-8: Computer players must use local models or SaaS AI models, as the user selects.
- EA-9 (added 2026-09-07 from a directive in chat): The project must test a local language model, small or large, with training to play the game. It is one computer-play family with the neural network agents and the other strategies.

## 5. Scope signals

- In scope by the user's words: the 1977 Avalon Hill Squad Leader. The rulebook in `background/` is the 4th edition (1979 rules text, 2012 softcopy).
- Not named by the user: the three expansion gamettes. The rulebook refers to them as Cross of Iron (COI), Crescendo of Doom (COD), and GI: Anvil of Victory (GIA). The 4th edition text has bracketed pointers to rules that those gamettes change.
- Not named by the user: Advanced Squad Leader (ASL). ASL is a different game with a different rulebook. Treat it as out of scope until the user says it is in scope.
- The counter photos include some counters that are not in the base game. See OQ-3.
- "Learning and evolution" is a named tier of the AI work. The words point at self-play reinforcement learning and at evolutionary search of agent parameters. See OQ-5.

## 6. Embedded rules and logic

The rulebook is `background/Squad_Leader_4th_Edition_Rules.pdf` (43 pages, author metadata: Bill Thomson, SQLA, produced 2012-02-08 for MMP). The text uses the Programmed Instruction method. Each rule has a numeric ID. The engine must keep these IDs.

### 6.1 Rule sections in the PDF

| Section | Topic | Rule IDs | Game set |
|---|---|---|---|
| 1 | Introduction | 1 | I |
| 2 | Unit counters (firepower, range, morale, leadership, weapon type, penetration, breakdown) | 2.1 to 2.9 | I |
| 3 | The mapboard (hex grid, center dot, grid coordinates, half hexes, cumulative terrain) | 3.1 to 3.8 | I |
| 4 | Sequence of play (8 phases for each player turn, 2 player turns for each game turn) | 4.1 to 4.9 | I |
| 5 | Movement (MF, squads 4 MF, leaders 6 MF, leader bonus 2 MF, portage) | 5.1 to 5.76 | I |
| 6 | Stacking (4 infantry units, 3 squads, 10 portage points) | 6.1 to 6.3 | I |
| 7 | Basic line of sight | 7.1 to 7.9 | I |
| 8 | Fire combat principles (fire groups) | 8.1 to 8.9 | I |
| 9 | Firepower modifiers (point blank x2, long range x1/2, moving x1/2, area x1/2) | 9.1 to 9.5 | I |
| 10 | Fire combat resolution on the Infantry Fire Table (IFT) | 10.1 to 10.6 | I |
| 11 | Terrain effects modifiers, walls and hedges | 11.1 to 11.6 | I |
| 12 | Morale and morale checks | 12.1 to 12.4 | I |
| 13 | Broken units and rout | 13.1 to 13.7 | I |
| 14 | Rally, desperation morale (morale minus 4) | 14.1 to 14.7 | I |
| 15 | Leadership | 15.1 to 15.8 | I |
| 16 | Defensive fire principles (move back, track counters, minus 2 in open) | 16.1 to 16.7 | I |
| 17 | Machine guns (penetration) | 17.1 to 17.9 | I |
| 18 | Fate (breakdown, repair on 1, loss on 6, rally 12 kills, Russian berserk on 2) | 18.1 to 18.5 | I |
| 19 | Procedures of movement and fire | 19.1 to 19.4 | I |
| 20 | Close combat (odds, kill number, melee) | 20.1 to 20.9 | I |
| 21 | Prepare for play | 21.1 to 21.3 | I |
| 22 | Flamethrowers (20 FP, range 2, no modifiers, out of fuel on 9 or more) | 22.1 to 22.9 | I |
| 23 | Demolition charges (30 FP) | 23.1 to 23.8 | I |
| 24 | Smoke (one die modifier) | 24.1 to 24.8 | I |
| 25 | Concealment counters | 25.1 to 25.9 | I |
| 26 | Fanaticism (minus 1 morale modifier, scenarios 2 and 3 only) | 26.1 to 26.2 | I |
| 27 | Sewer movement (3 hexes, die roll 4 or less) | 27.1 to 27.7 | I |
| 28 | Armored fighting vehicles (MP, main gun, MG armament) | 28.1 to 28.4 | I |
| 29 | Vehicle stacking, placement, covered arc | 29.1 to 29.4 | I |
| 30 | AFV movement | 30.1 to 30.8 | I |
| 31 | Transport of infantry on tanks and SP guns | 31.1 to 31.9 | I |
| 32 | AFVs as cover | 32.1 to 32.7 | I |
| 33 | AFV combat (To Hit, AFV Kill, target facing, crew survival) | 33.1 to 33.9 | I |
| 34 | AFVs versus infantry (crew exposed, canister) | 34.1 to 34.92 | I |
| 35 | Overruns (16 FP tanks, 8 FP halftracks) | 35.1 to 35.9 | I |
| 36 | Infantry versus AFVs (pre-AFV attack morale check, immobilize, close combat kill) | 36.1 to 36.4 | I |
| 37 | Special infantry weapons versus AFVs (flamethrower, panzerfaust, bazooka) | 37.1 to 37.48 | I |
| 38 | Fate versus armor (malfunction on 12, repair) | 38.1 to 38.3 | I |
| 39 | Immobilization (woods and wood building breakdown) | 39.1 to 39.4 | I |
| 40 | Wrecks | 40.1 to 40.6 | I |
| 41 | Miscellaneous armor (hull down, crews, AFV smoke, German smoke dischargers) | 41.1 to 41.4 | I |
| 42 | Hidden initial placement | 42.1 to 42.7 | II |
| 43 | Advanced line of sight (three hill levels, crest lines, blind hexes) | 43.1 to 43.9 | II |
| 44 | Rural terrain (cliffs, wheatfields, shellholes) | 44.1 to 44.32 | II |
| 45 | Offboard artillery (modules, fire missions, counter battery) | 45.1 to 45.42 | II |
| 46 | Artillery fire mechanics (radio contact, spotting round, FFE, 7 hex blast area) | 46.1 to 46.9 | II |
| 47 | Halftracks | 47.1 to 47.9 | II |
| 48 | Anti-tank guns | 48.1 to 48.9 | II |
| 49 | Night rules (visibility range, starshells) | 49.1 to 49.8 | II |
| 50 | The Americans (no desperation morale, repair on 1 or 2) | 50.1 to 50.5 | III |
| 51 | Trucks | 51.1 to 51.7 | III |
| 52 | Jeeps | 52.1 to 52.5 | III |
| 53 | Wire | 53.1 to 53.9 | III |
| 54 | Entrenchments | 54.1 to 54.9 | III |
| 55 | Minefields (secret record, no counters) | 55.1 to 55.7 | III |
| 56 | Bunkers | 56.1 to 56.9 | III |
| 57 | Upper building levels (staircase hexes, 2 MF for each level) | 57.1 to 57.93 | III |
| 58 | Rubble | 58.1 to 58.4 | III |
| 59 | Fire (spread table) | 59.1 to 59.8 | III |
| 60 | "River Crossings" (scenario 11) | 60.1 to 60.5 | III |
| 61 | Snow | 61.1 to 61.4 | III |
| 62 | Roadblocks | 62.1 to 62.4 | III |
| 63 | On board artillery (mortars, howitzers, HEAT, indirect fire) | 63.1 to 63.7 | III |
| Appendix | Clarifications of 4.7 and 11.5 | | |
| Optional | 7.1, 8.7, 16 (semi-simultaneous movement and defensive fire), 17.5, 25.4, 32.4, TI counters, 59.1 | | |
| Q and A | About 60 official questions and answers that refer to rule IDs | | |
| Game Set IV | Design your own: random scenario construction with a 52 card deck, random selection chart, point value chart, victory condition chart | | IV |
| Campaign game | Personal leader counter, ranks, elan and cowardice points | | IV |
| Designer's notes | John Hill on abstraction, effect based design, MG penetration, leadership | | |
| Basic tactics | Platoon line, company line, city combat, wire and mines, the attack | | |
| "Advanced Sequence of Play" | Full phase checklist with rule pointers (page 41) | | |
| Index | Rule pointer index (page 42) | | |
| Terrain effects chart | Rule pointers for each terrain type, no numbers (page 43) | | |

### 6.2 The core turn structure (rule 4)

Each game turn has two player turns. Each player turn has eight phases. The player who moves is the attacker.

1. Rally Phase (4.1). The two players repair weapons and rally broken units.
2. Prep Fire Phase (4.2). The attacker fires. Units that fire get a Prep Fire marker.
3. Movement Phase (4.3). The attacker moves units that did not prep fire.
4. Defensive Fire Phase (4.4). The defender fires at units in LOS or units that moved through LOS.
5. Advancing Fire Phase (4.5). The attacker fires moved units at half firepower.
6. Rout Phase (4.6). Broken units of the two sides go to cover.
7. Advance Phase (4.7). The attacker moves non-broken infantry one hex. This is the only time infantry can enter an enemy hex.
8. Close Combat Phase (4.8). Units in the same hex attack on the Close Combat Table.

The "Advanced Sequence of Play" on page 41 expands each phase into numbered sub-steps with rule pointers. That list is the state machine for the engine.

### 6.3 Numeric constants in the text

| Constant | Value | Rule |
|---|---|---|
| Hex scale | 40 meters | 5 |
| Game turn time | 2 minutes (two player turns) | 4 |
| Squad MF | 4 | 5.41 |
| Leader MF | 6 | 5.42 |
| Leader movement bonus to squads | 2 MF | 5.44 |
| Squad free portage | 3 points | 5.7 |
| Leader free portage | 1 point, 3 maximum | 5.7, 5.71 |
| Stacking limit | 4 infantry units, 3 squads, 10 portage points | 6.1 |
| Point blank fire | firepower x2 | 9.1 |
| Long range fire | firepower x1/2, no fire at more than 2x range | 9.2 |
| Moving fire | firepower x1/2 | 9.3 |
| Area fire (concealed target) | firepower x1/2 | 9.4 |
| Defensive fire at movers in open | minus 2 | 16.5 |
| Desperation morale | morale minus 4 | 14.6 |
| Rally roll of 12 | unit removed | 18.3 |
| Repair die roll | 1 repairs, 6 removes | 18.2 |
| Russian berserk | unmodified morale check roll of 2 | 18.4 |
| Berserk MF | squad 6, leader 8 | 18.43 |
| Flamethrower | 20 FP, range 2, penetration 2, out of fuel on 9 or more | 22.1, 22.6 |
| Demolition charge | 30 FP | 23.1 |
| Sewer move | 3 hexes, success on die roll 4 or less | 27.2, 27.22 |
| Vehicle stacking | 1 vehicle for each hex | 29.1 |
| Under vehicle stacking | 3 infantry units, 2 squads, 5 portage points | 29.2 |
| AFV passengers | 2 infantry units, 1 squad, 5 portage points | 31.1 |
| Overrun | 16 FP tank, 8 FP armed halftrack | 35.3 |
| Main gun malfunction | To Hit roll of 12 | 38.1 |
| Woods and wood building breakdown | 6 for US and Russian AFV, 5 or 6 for German AFV | 39.1 |
| Panzerfaust range | 3 hexes | 37.31 |
| Bazooka range | 4 hexes, out on 11 or 12 | 37.41, 37.45 |
| Artillery blast area | FFE hex plus 6 adjacent hexes | 46.5 |
| Artillery correction | up to 3 hexes for each Rally Phase | 46.31 |
| Spotting round on target | 1 or 2 German and US, 1 Russian | 46.21 |
| Radio breakdown | roll of 12 | 46.81 |
| Night visibility range | 2 dice each game turn, plus 3 for vehicles | 49.11, 49.12 |
| Starshell radius | 3 hexes, put up to 5 hexes from leader | 49.6, 49.7 |
| Entrenchment try | 2 dice, 5 or less | 54.2 |
| Mortar range | minimum 10, maximum 60 | 63.21 |
| Indirect howitzer minimum range | 20 hexes | 63.41 |
| Truck capacity | 1 squad, 1 leader, 7 portage points | 51.1 |
| Snow | infantry and soft vehicle movement cost x2 | 61.1 |
| Company game budget | 1,000 points a side | Point value chart |

### 6.4 Unit values read from the rules text

| Nationality | Squad types named | Rule |
|---|---|---|
| German | 4-6-7 line, 8-3-8 assault engineer | 10.6 example, 22.4 |
| Russian | 4-4-7 line, 6-2-8 guards | 12.4 example, 20.3 example |
| American | 6-6-6 line, 8-4-7 elite | Random selection chart note, 50.2 |
| All | Crew counters with firepower 2 | 41.2 |

Leader counters have a morale value and a leadership modifier from +1 to -3 (rule 15.1). The campaign game table gives the rank ladder: Cpl 7/0, Sgt 8/0, 1st Sgt 8/-1, 2nd Lt 9/-1, 1st Lt 9/-2, CPT 10/-2, MAJ 10/-3.

### 6.5 What the PDF does not contain

The rules name these items. The engine needs them. The PDF has no readable copy of them:

- The Quick Reference Data Card. This card holds the tables that follow.
  - Infantry Fire Table
  - Close Combat Table
  - To Hit Table
  - AFV Kill Table
  - Hit Determination modifiers (cases A to I)
  - Terrain Effects Modifiers numbers
  - Movement Cost charts for infantry and vehicles
  - Support Weapons Chart with portage costs
  - Defensive Fire AFV Immobilize Numbers
  - Radio Contact Values
  - Artillery Module Selection Table
  - Spreading Fire Table
  - Minefield versus Vehicle modifiers
  - Entrenchment protection modifiers
  - Bunker values
- The 12 scenario cards (names, boards, order of battle, set up areas, turn counts, victory conditions, special rules). The text names scenario 1 "The Guards Counterattack", scenario 2 "The Dzerhezinsky Tractor Works", scenarios 3A and 3B, and scenario 11 as an assault across the Rhine.
- The Random Selection Chart rows (pages 32 and 33 came out as unlabeled digits).
- The Point Value Chart row and column headings (page 34 came out as unlabeled digits).
- The four mapboards as images.
- The counter manifest (how many of each counter).
- Most diagrams (LOS examples, target facing, covered arc, direction of error).

### 6.6 What the photos show

`background/Map_Photo.png` (1500 x 1500) shows all four boards put edge to edge along their long edges. From bottom to top the boards are:

- board 1, the city, with stone buildings and paved streets
- two hill boards with level 1 to 3 hills, shellholes, a village, and wheatfields
- a top board with wheatfields, small buildings, and a coordinate strip

You can see the hex grid, the center dots, and the grid labels. The art style has these properties:

- flat color fills
- hand drawn woods clumps
- brown hill contours with darker cores
- gray stone buildings with white roof highlights
- red-brown wooden buildings

`background/Allied_Pieces.png` (900 x 932) shows two counter sets. The yellow-green counters are American:

- squads 6-6-6, elite squads 8-4-7, crews 2-4-6
- leaders 9-2, 9-1, 8-1, 8-0, 7-0
- MMG 4-12 B12, HMG .30 cal 8-20 B12, 9 triangle B12 (mortar)
- flamethrower 20 triangle -1 [2], demolition charge 30 triangle A, bazooka 6 [4] X11
- 57 and 76 anti-tank guns with B12
- vehicle counters with MP 16, 18, 24 and gun data (75 4/6, H6 105 4/2, P5, P7)
- Artillery Request, SR (spotting round) with flames, "?" concealment, MC and Immobilize markers
- "Broke 7, 8, 9, 10" back sides

The darker green counters are a different nationality:

- squads 3-4-7
- leaders 8-0, 8-1, 7-0, 6+1
- a 1-8-8 unit with a -1 or -2 modifier
- MMG 4-10 B11+, LMG 2-7 B11+

This nationality is not in the base game. See OQ-3.

`background/Axis_Pieces.png` (900 x 932) shows tan counters with red and pink berserk versions. Readable values:

- squads 4-4-7, 6-2-8, 4-3-6, 3-3-6, 5-3-7, crews 2-3-7
- leaders
- LMG 2-6 B10, MMG, HMG 6-20 B12
- ATR (anti-tank rifle), 50 and 82 mortars
- CE -2 markers, CREST marker, "?" concealment, "Broke" back sides

Rule 18.41 says only Russian units get red berserk counters, and 6-2-8 is the Russian guards squad. Thus this file shows Russian counters, not Axis counters. See OQ-2.

## 7. Dependencies and sibling conventions

- `G:\git\AI_Scaffolding\` for the key files (already copied).
- Sibling inspection result (2026-09-07, Explore agent, eight projects examined). All eight siblings are Python. None has a browser UI. This project is the first browser project in the family. Conventions to inherit:
  - Provider abstraction: copy `G:\git\llm_compare\llm_compare\providersase.py` (ABC, `Response` dataclass, `ProviderStatus`, `MODEL_PREFERENCES`). Add the HoneyAI refinements from `G:\git\HoneyAI\docs\ARCHITECTURE.md` section 7: JSON schema response format with validate-and-repair fallback, per-provider timeout, circuit breaker, explicit failover sequence.
  - Key files: resolve `*.key.txt` against the project root, not the current directory. Skip lines that start with `#`, then fall back to the environment variable. If the key file and the environment variable are missing, mark the provider unavailable and do not stop the program. Pattern source: `G:\git\DungeonsOfDreagoth\dreagothi\client.py` line 33.
  - Local models: use the OpenAI-compatible HTTP endpoint (`http://host:port/v1`) with a `/v1/models` health check at start. This one code path serves llama.cpp server, Ollama, vLLM, and LM Studio. Pattern source: `G:\git\LocalLLMPerf_AI\CLAUDE.md`.
  - Run storage: `runs/<ISO8601-Z>-<slug>/` with a `runs/runs.sqlite` index. Each run is self-contained (config, seeds, versions, raw samples, derived stats). Pattern source: `G:\git\LocalLLMPerf_AI\src\localllmperfrtifact\`.
  - RL: custom PPO and DQN in torch on a `gymnasium.Env`, with league self-play (policy snapshots, opponent sampling ratio, win-rate snapshot trigger). Pattern source: `G:\git\SpaceWar_AI\spacewar_ai\main.py` (`SelfPlayManager`) and `tournament.py`. No sibling uses stable-baselines3.
  - Tests: pytest with `testpaths=["tests"]`, `asyncio_mode="auto"`, and marker-gated integration tests (`addopts = "-m 'not integration'"`). Pattern source: `G:\git\LocalLLMPerf_AI\pyproject.toml`.
  - License: six of eight siblings are GPL-3, `airobots` is BSD-3, `QC_Qore_AI` has no license file.
  - Anti-pattern, do not copy: `airobots` reads keys relative to the current directory and has debug artifacts in the root.
- VASSAL and the VSQL module: the standard digital play surface for Squad Leader. It is a source for counter data and map layout, not a source for graphics to copy.
- The MMP consolidated Q and A booklet, shown by the arrow marks in the rules.

## 8. Open questions

- OQ-1 (legal): Hasbro owns the Squad Leader trademark and the copyright in the art and rules text. Copyright law in the United States does not apply to game mechanics. The project must select what it reproduces: the 1977 art, redrawn art in the same style, or new art. Needs research and a user decision, because the answer shapes EA-2 and EA-3.
- OQ-2 (data): `Axis_Pieces.png` shows Russian counters. No German counters are in `background/`. The German counter set must come from research.
- OQ-3 (data): The dark green 3-4-7 counters and the "B11+" weapons do not agree with one of the base game nationalities in the rules text. They look like a subsequent gamette. Confirm the source and make a decision on scope.
- OQ-4 (scope): Base game only, or also COI, COD, and GIA? The 4th edition text has the modification pointers. Thus the engine can accept gamette overlays after v0.1 ships with the base game only. Recommendation: base game only for v0.1.
- OQ-5 (AI): What does "learning and evolution" mean in practice? There are four alternatives:
  - self-play RL on a compact state encoding
  - evolutionary search of scripted policy parameters
  - LLM agents with a tool interface to the engine
  - a mix, with the LLM as a planner and a learned policy as the executor
  This needs research and a user decision.
- OQ-6 (play modes): Human versus human on one machine (hot seat), or across a network? The goal says "browser based", which lets us do the two. Recommendation: hot seat and local network first. Do not build matchmaking.
- OQ-7 (maps): "Generates maps that look like the boardgame maps" has three possible meanings:
  - reproduce the four boards
  - make new isomorphic boards in the same style
  - the two
  Recommendation: the two, with the four 1977 boards as the fidelity test.
- OQ-8 (license): Ron uses GPL-3 or BSD for Ron's code and does not use Apache-2.0 (durable preference, 2026-06-18). The init skill defaults to MIT. Ask which of GPL-3 or BSD applies.
- OQ-9 (rules source): The Quick Reference Data Card tables are missing from the PDF. Research must find a readable source. If there is no readable source, the tables must be rebuilt from secondary sources and identified as rebuilt.

## 9. References

- `background/Squad_Leader_4th_Edition_Rules.pdf`. Page map:
  - rules 1 to 63: pages 2 to 26
  - appendix and optional rules: page 27
  - Q and A: pages 27 to 29
  - LOS course: page 30
  - Game Set IV: pages 31 to 35
  - credits and designer's notes: pages 36 to 38
  - basic tactics: pages 38 to 40
  - "Advanced Sequence of Play": page 41
  - index: page 42
  - terrain effects chart: page 43
- `background/Map_Photo.png`: four boards, see 6.6.
- `background/Allied_Pieces.png`: American and one unidentified green set, see 6.6.
- `background/Axis_Pieces.png`: Russian set, see 6.6 and OQ-2.
- Normalized rules text extract: scratchpad `rules.txt` and `rules_1.txt` to `rules_6.txt` (session temporary files, not project files).
- Sibling docs to read before the draft phases: `G:\git\QC_Qore_AI\docs\VISION.md`, `G:\git\QC_Qore_AI\docs\REQUIREMENTS.md`, `G:\git\LocalLLMPerf_AI\docs\ARCHITECTURE.md`, `G:\git\HoneyAI\docs\ARCHITECTURE.md`, `G:\git\HoneyAI\docs\PLAN.md`, `G:\git\LocalLLMPerf_AI\VIBE_HISTORY.md`.

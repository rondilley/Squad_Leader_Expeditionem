# Squad Leader digital edition: state of the art report

Author: Ron Dilley, with research by Claude Fable 5.1
Date: 2026-09-07
Status: v0.1, first pass after eight parallel research vectors
Companion documents: `tasks/discovery_notes.md` (the input brief), `docs/research/2026-09-07_RV-1_counters_charts.md` to `docs/research/2026-09-07_RV-8_community.md` (the eight full research reports with their reference lists)

This document is the synthesis. Each of the eight appendix reports holds the full data, the URLs, and the items that the research could not find. Read the appendix when you must have a number or a quotation. Read this document when you must have the decision that the data supports.

## 1. Scope and methodology

### 1.1 The question

The question has four parts. Can a solo developer build a browser edition of the 1977 board game Squad Leader? Can it play the 4th edition rules correctly? Can it look like the board game? Can it support human and computer players in all three pairings? Can it train computer players by self-play and by local or SaaS language models?

The research had to find the component data, the prior art, the legal boundary, the AI methods, the browser technology, and the community expectations.

### 1.2 Method

Eight research vectors ran in parallel on 2026-09-07. Each vector had one agent, one written brief, and one rule of evidence. The rule: each fact must have a URL that the agent opened. Each agent wrote a report with a reference list. The ASD-STE100 checker gave zero errors for each report.

The vectors were:

- RV-1: counter inventory and the Quick Reference Data Card
- RV-2: the four mapboards and the 12 scenarios
- RV-3: prior digital implementations and usable building blocks
- RV-4: legal and intellectual property status
- RV-5: reinforcement learning, self-play, and evolution for hex wargames
- RV-6: language model agents as board game players
- RV-7: browser technology, engine sharing, rendering, and map generation
- RV-8: community and social signal

### 1.3 Limits

Each agent had a web search budget of 200 calls, and most agents used all of it. BoardGameGeek pages returned HTTP 403 to automated fetches. The agents got BoardGameGeek data from the public JSON endpoints at api.geekdo.com as the alternative. Reddit was not reachable at all, so no report contains Reddit data. The Squad Leader Academy site (wargameacademy.org) closed connections for some agents and gave PDF scans to others. Each appendix lists the pages that did not open.

Two source classes have a caution. First, facts identified as "(scan)" in RV-1 and RV-2 come from the agent's inspection of 600 DPI scans on archive.org, not from a text source. Make sure of each hex number and counter value on the full resolution scan before you put it in code. Second, the 2012 SQLA softcopy of the rules and the 4th edition scans are from the 1980s printings. No source says that counter values or board layouts changed between 1977 and the 4th edition.

## 2. Definitions and prior art

Squad Leader is a tactical board wargame. John Hill made the design and Avalon Hill published it in 1977. One counter is a squad of 4 to 10 men, a leader, a support weapon, or a vehicle. One hex is 40 meters.

One game turn is two player turns of eight phases each. The rules use Programmed Instruction: 12 scenarios add rule sections 1 to 63 in sequence.

Three gamettes followed: Cross of Iron (1978), Crescendo of Doom (1979), and GI: Anvil of Victory (1982). Advanced Squad Leader (1985) replaced the series with a new rulebook. This project targets the 1977 base game with the 4th edition rules text. ASL is out of scope.

The prior digital art has two branches. VASSAL is a general board game engine, and the VSQL module (version 4.3.8) is the standard play surface for Squad Leader and Cross of Iron online. VSQL gives boards, counters, dice, hidden units, and a line of sight check. It does not automate combat, morale, or rout.

The other branch is commercial computer games. The 2000 Hasbro Interactive game dropped the board rules and the hex map, and reviewers rejected it (Metacritic 46). Second Front (2023) is an ASL-like game with rule automation and a rules-bound AI, and players audit its AI phase by phase. No open-source project has the Squad Leader rules as an engine. Section 5 has the details.

## 3. Components: counters and the data card (RV-1)

### 3.1 What the research found

The base game has 520 half-inch counters and 192 five-eighths-inch counters on three sheets. The Squad Leader Academy inventory gives the counts for each nationality. The agent made sure of them counter by counter against the 600 DPI scan of the 4th edition sheets. The table below gives the squad and crew values as printed.

| Nationality | Line squad | Elite squad | Crew | Leaders | Color |
|---|---|---|---|---|---|
| German | 4-6-7 (35) | 8-3-8 (7) | 2-4-7 (13) | 21 | light blue |
| Russian | 4-4-7 (53) | 6-2-8 (13) | 2-3-7 (10) | 15 | tan |
| American | 6-6-6 (32) | 8-4-7 (16) | 2-4-6 (11) | 21 | yellow-green |

The American elite squad is 8-4-7, not 7-4-7. The 7-4-7 comes with GI: Anvil of Victory. Ten Russian counters are red berserk versions (4 x 4-4-7, 3 x 6-2-8, 3 x 2-3-7).

Leaders have names. The agent read all of them from the scan. There are 13 named German leaders, from Sgt Kelso 9-1 to Col Rosenberger 6+1 and Obr Greup 10-3. There are 7 named Russian leaders and 13 named American leaders. Each nationality also has 7 rank-only leaders on the back sides of "Broke" counters.

Support weapons, vehicles, and markers have full value tables in RV-1 sections 4 to 6. Two examples: the German LMG is 2-8 B12 and the Russian LMG is 2-6 B10+. The T-34 has 16 MP, a 76 gun, and MG values 4/-.

### 3.2 The data card: found and not found

RV-1 section 7 has these tables in full:

- the Infantry Fire Table (11 columns from 1 to 36+, with a 24 column that the brief did not list)
- the Close Combat Table (kill numbers 2 to 11)
- the Support Weapons Chart with portage costs and its notes A to H
- the stacking limits, the overrun values, and the sewer roll
- the infantry movement cost chart
- the Terrain Effects Modifiers down to the wooden building line

The rules text itself supplies the stone building modifier (+3, rule 11.53 example) and the wooden building modifier (+2, rule 37.36).

These tables were not found in a readable form:

- the To Hit Table
- the AFV Kill Table
- the Hit Determination modifiers A to I
- the vehicle movement cost chart
- the Defensive Fire AFV Immobilize Numbers
- the Artillery Module Selection Table
- the Spreading Fire Table

These are on page 2 of the data card. The only online copy (Scribd) did not open after page 1. Some values are on counter back sides. The fire counter back side gives the spread-of-fire numbers (wooden 8+, stone 9+, other 10+). The entrenchment back side gives the entrenchment modifiers. The panzerfaust and bazooka back sides give their To Hit tables.

### 3.3 The two photo questions

The photo named `Axis_Pieces.png` shows Russian counters. The 1977 German counters are light blue. The dark green counters with 3-4-7 squads, 6+1 and 8-0 leaders, a 1-8-8 sniper, and MMG 4-10 B11+ are the Cross of Iron Rumanian contingent. Five printed values agree with the SQLA Cross of Iron inventory. They are out of scope for v0.1.

## 4. Boards and scenarios (RV-2)

### 4.1 Board geometry

Each board is 8 inches by 22 inches. The hex grid is 33 columns (A to Z, then AA to GG) by 10 rows, with half hexes on all four edges. Wikipedia says 32 columns wide. The VASL board specification says 33 columns in a 1800 by 645 pixel image. The 33 count agrees with the letter range.

All four boards share the same geomorphic connections. Woods half hexes are at columns F, H, J, L, V, X, Z, and BB on the top and bottom edges. Roads enter at I1, Q1, Y1, I10, Q10, Y10, A5/A6, and GG5/GG6. Rule 3.5 gives the tie break for the half hexes at a joint.

Board 1 is the city. Board 2 is the hills, with Hill 621 and Hill 538 at three levels. Board 3 is the village with four small hills. Board 4 is open rural ground with large grain fields.

RV-2 section 1.4 gives a hex list for each terrain feature on each board, read from the scans. One disagreement stands: the rules put the 538 hill symbol at 2BB5 and the scan shows it at BB6.

### 4.2 Board images and their status

Two image sources are available. The archive.org item "Squad Leader by Avalon Hill Scans" has 600 DPI scans of all four 4th edition boards, the counter sheets, and two scenario cards. It has no license field, and the boards show the 1977 Avalon Hill copyright. VASL boards 1 to 4 share the geometry and the terrain layout of the Squad Leader boards, because ASL used the boards without change.

The current VASL and MMP art is a computer redraw from the 2000s reprints, because the 1977 artwork is lost. Neither source gives permission to use the art again. Section 6 covers what that means.

### 4.3 The 12 scenarios

RV-2 section 3 transcribes all 12 scenario cards from the SQLA scans. Each transcription has the title, date, place, board configuration with orientation, turn count, and set up sequence. It has the victory conditions verbatim, the full force lists with leader names and counts, the special rules verbatim, the variations, and the aftermath text. The summary table:

| No. | Title | Boards | Attacker | Turns |
|---|---|---|---|---|
| 1 | The Guards Counterattack | 1 (rows A to P) | Russian | 5 |
| 2 | The Tractor Works | 1 (rows O to GG) | German | 8 |
| 3 | The Streets of Stalingrad | 1 | the two sides | 7 |
| 4 | The Hedgehog of Piepsk | 4, 3, 2 | Russian | 10 |
| 5 | Hill 621 | 2, 4, 3 | Russian | 10 |
| 6 | Escape From Velikiye Luki | 4, 2, 3, 1 | German (night) | 10 |
| 7 | Buchholz Station | 4, 3 | German | 10 |
| 8 | The Bitche Salient | 4, 2 | American | 10 |
| 9 | The Cannes Strongpoint | 4, 2, 3 | American | 5 |
| 10 | Hitdorf on the Rhine | 4, 3 | American | 9 |
| 11 | The St. Goar Assault | 2, 1, 4, 3 end to end | American | 7 |
| 12 | The Road to Wiltz | 1, 3, 2, 4 end to end | German | 12 |

Scenarios 1 to 3 use board 1 only. Scenario 1 uses rules 1 to 21, scenario 2 adds 22 to 26, and variation 3A adds 27. Variation 3B (armor) adds rules 28 to 41. Scenario 3 has variations 3A (sewers), 3B (armor), and 3C (the two). <!-- AI review 20260907-160656: openai -->

The card does not divide it into two scenarios. Scenarios 4 to 12 use two to four boards. The General magazine published 25 more scenarios with letter and number designations. Scenarios 1 to 3 do not use the vehicle tables, because the armor in scenario 3 is a variation.

### 4.4 Card format

Each card is 8.5 by 11 inches, printed on the two sides. The elements are:

- number and title, a picture, and a historical narrative with place and date
- "Rules Introduced" and victory conditions
- a board configuration diagram with a north arrow
- a turn record chart with set up sequence and reinforcement marks
- one force list box for each side, with the historical unit name and the set up instruction
- special rules, variations, and aftermath

This is the schema for the scenario data format.

## 5. Prior digital implementations and building blocks (RV-3)

### 5.1 Lessons from the products that shipped

| Product | Lesson |
|---|---|
| VSQL and VASL | A play surface with dice, hidden units, and an LOS check is what the community used for 25 years. VASL automates only LOS and dice. Its LOS engine walks a pixel terrain grid, not hex cells. |
| Squad Leader (Hasbro, 2000) | It dropped the board rules and the hex map for an earlier isometric engine. Metacritic 46. Fans and reviewers rejected it for that cause. |
| Second Front (2023) | Two developers shipped an ASL-like game with rule automation, hit percentages, and a rules-bound AI. Players find each rule deviation. Complaints: coarse range bands, random reloads, no LOS tool, weak fog of war, no multiplayer at release. |
| Conflict of Heroes PC (2012) | Good rules port with a 2D chit mode. Main defect: no LOS display before a move. |
| Lock 'n Load Tactical Digital (2020) | Correct rules and a praised LOS preview. Complaint: small content. |

### 5.2 Engine sharing between browser and Python

No open-source project has the Squad Leader or ASL rules as an engine. The closest architecture pattern is OpenStratCore. It is an embryonic Rust hex core with PyO3 bindings for reinforcement learning and WebAssembly bindings for a browser.

Mature projects that ship one Rust core to the two targets are available: boytacean, oxigraph, y-crdt, regorus, datalogic-rs, rapier, Automerge, and Ruff. The boytacean Cargo file shows the feature-flag layout. The datalogic-rs project shows the test strategy: one conformance battery that each binding runs against the same core.

Do not use boardgame.io as the rules engine. Its game state and random generator live in JavaScript, so Python cannot share them. Its phase and lobby model is a good reference for the browser shell.

### 5.3 Line of sight

Three algorithm families are available. Hex-cell algorithms (Verbrugge 1996, zvold 2010, Red Blob Games) find the hexes that a line touches. VASL rasterizes the board art to a terrain grid and an elevation grid, one cell for each pixel. Then it walks the pixels between the two hex centers. The board rule is a thread from center dot to center dot that touches printed terrain. Thus the VASL approach agrees with the rule better than a hex-cell method.

A vector approach gives the same result with less data and works for generated boards. It keeps terrain polygons for each hex and tests them against the center-to-center segment.

### 5.4 Counter look

The 1977 counters mix sans-serif faces (Helvetica, Univers Bold Condensed, and possibly others). No source names one typeface. VASL renders 6,270 SVG counters with the free Nimbus Sans L font. Archivo Narrow and Inter are free alternatives. The five-eighths-inch vehicle counters use a top-down silhouette, a name, and values in bold condensed numerals. Roger MacGowan prepared them.

## 6. Legal and intellectual property status (RV-4)

This section is not legal advice. It is a summary of public sources.

### 6.1 Who owns what

Hasbro bought Avalon Hill on 1998-08-04 and holds the copyrights. Multi-Man Publishing holds an exclusive license from late 1998 for Squad Leader and ASL products. The USPTO registration for SQUAD LEADER expired in 2009. The ADVANCED SQUAD LEADER registration was cancelled in 2018. No live federal registration is on record for the two names, but common-law rights continue through MMP sales. The AVALON HILL mark is live.

### 6.2 What copyright covers

17 U.S.C. 102(b) and the Copyright Office do not include the idea of a game, its name, or its method of play. Four court cases agree:

- Allen v. Academic Games League (9th Cir. 1996)
- Spry Fox v. LOLApps (W.D. Wash. 2012)
- Tetris v. Xio (D.N.J. 2012)
- DaVinci v. ZiKo (S.D. Tex. 2016)

Rules and mechanics get no protection.

Rulebook prose gets thin protection against near-identical copies. Board art, counter art, and a fanciful look and feel get full protection. No US decision from 2020 to 2026 changed this.

### 6.3 What this means for the project

| Element | Risk | Practice |
|---|---|---|
| Rules engine, tables, unit values | Safe | Write the tables as your own data in your own layout |
| Rule numbers and technical terms | Safe | Keep them |
| Rulebook text | Thin protection | Paraphrase. Do not ship the PDF |
| The four board layouts | Real risk | The terrain layout is a creative selection. Generated boards in the same style have less risk |
| Counter art | Full protection | Draw new counters. Keep the numbers and their positions |
| Scenario titles and orders of battle | Safe | Facts and short phrases |
| Project name | Trademark risk | Do not use "Squad Leader" as the brand. Nominative use in text is permitted with a non-affiliation notice |

Community precedent agrees. VASL ran from the 1990s with no takedown, but tolerance is not a license. Hasbro sent takedown notices for Scrabulous in 2008 when a fan product competed with an official digital product. Renegade Game Studios has a streamlined Squad Leader in digital playtest (2025 to 2026), so an official digital product is possible. Freeciv, OpenTTD, FreeCol, and TripleA survived because they re-implemented mechanics with their own art and no brand name.

GPL-3 adds one duty for the served browser bundle. To send it to a browser is to convey object code (section 6), so the Corresponding Source must be available. The FSF LibreJS guidance gives a section 7 added permission for minified code. That notice plus a link to the repository satisfy the duty. <!-- AI review 20260907-160656: openai, wording tightened -->

## 7. Reinforcement learning, self-play, and evolution (RV-5)

### 7.1 Closest prior work

Palma, Santos, and Dias (arXiv 2502.13918, February 2025) did the training of AlphaZero with hexagonal convolutions on a Standard Combat Series ruleset. Training used 5 by 5 maps, 3 to 8 units, and CPU only. The policy alone won about 80 percent against a random agent, and with search about 100 percent. This shows the approach works at toy scale and gives no wall-clock numbers. No paper trains an agent on Squad Leader, ASL, Advance Wars, or Wesnoth.

### 7.2 Action space

The Gym-uRTS work (arXiv 2105.13807) gives the template. The action is a composed tuple (unit, action type, target) with invalid action masking. The policy selects one unit at a time until an end-phase action. Masking is a correct policy-gradient method, and its effect grows with the number of invalid actions (arXiv 2006.14171). A single discrete head with a mask keeps throughput high. The tribes-rl project gets 1.8 million steps/s on an RTX 5090 with a C engine.

### 7.3 What one workstation can do

Full AlphaStar-style leagues are out of reach. TStarBot-X, the cheap version, used 144 V100 GPUs for 57 days. Ataraxos got to superhuman Stratego with 16 H100 GPUs for a week. What is practical: a snapshot league with prioritized fictitious self-play, 10 to 20 snapshots plus 3 to 5 scripted bots, and an Elo tournament, as the SpaceWar_AI sibling does.

Pgx reports single-GPU Gumbel AlphaZero runs of 6 to 18 hours on an A4000 for about 105 million frames on small board games. Gym-uRTS got to state-of-the-art bot play at 300 million steps in about 60 hours on one GPU.

Derived planning figures: 1,000 to 4,000 decision steps for each game, and a budget of 100 million to 300 million steps for v0.1. The end-to-end rate must be 3,500 steps/s to complete 300 million steps in 24 hours. A pure Python engine gives 1,000 to 5,000 steps/s for each core. With 8 to 16 workers it can give this rate only if observation construction is cheap.

### 7.4 Evolution

Data that pure neuroevolution beats PPO on a multi-unit strategy game is thin. Evolution works for three jobs. It tunes scripted policies and behavior trees (CMA-ES, arXiv 1604.00772). It makes diverse opponents for a league (MAP-Elites on Tribes, arXiv 2104.08641, and Generational Adversarial MAP-Elites, arXiv 2505.06617). It tunes hyperparameter schedules (Population Based Training, arXiv 1711.09846).

### 7.5 Tooling

Gymnasium, PettingZoo, CleanRL, PufferLib, and Sample Factory are MIT. OpenSpiel and RLlib are Apache-2.0. MicroRTS is GPL-3.0, which is compatible with this GPL-3 project.

Use PettingZoo AEC as the environment contract for alternating turns. Keep PPO in raw torch in CleanRL style, as the siblings do. Custom action heads with masks are custom code in each framework. Move to PufferLib if throughput becomes the limit.

## 8. Language model agents (RV-6)

### 8.1 How the models play

Not at a high level, as of 2026.

BALROG (arXiv 2411.13543) gives average progress of 32.6 percent for Claude 3.5 Sonnet, 32.3 percent for GPT-4o, 27.9 percent for Llama 3.1 70B, and 15.1 percent for Llama 3.1 8B.

WGSR-Bench (arXiv 2506.10264) scores humans at 80 to 92 and the best models at 49 to 60 on wargame tasks.

WARBENCH (arXiv 2603.21280) reports three results. Tactical reasoning breaks down with complex terrain. Small edge models break rules up to about 70 percent of the time. 4-bit quantization causes catastrophic degradation. Vision input makes most models worse.

### 8.2 The failure modes and the harness that absorbs them

Invalid moves continue with each prompt style. A strong Diplomacy harness (arXiv 2508.07485) saw 6 to 14 percent invalid orders across 16 models from 9B to o3. It completed games only with retry-then-default. In chess, a legal-move list in the prompt made gpt-4o play worse. Move regurgitation plus three examples raised it to about 1540 Elo.

lmgame-Bench (arXiv 2505.15146) shows that a perception and memory harness lifts runs that beat random from 60 percent to 86.7 percent, for all models. Geo-Commander (Scientific Reports, 2026) beat the prior AlphaWar agent on a hex tank wargame. It used ReAct plus explicit hex coordinate, elevation, and terrain encoding, at 3,000 to 3,500 tokens and 40 to 50 seconds for each decision. Strict JSON constraints degrade reasoning (arXiv 2408.02442). Thus the model must reason in free text first and emit JSON second.

### 8.3 Structured output in 2026

Each provider supports schema-constrained output: Anthropic `output_config.format`, OpenAI `text.format`, Gemini `response_format`, xAI and Mistral `response_format`, llama-server `response_format` changed to GBNF, Ollama `format`, vLLM `structured_outputs`, and LM Studio `response_format` (weak below 7B). A flat schema with string enums, no recursion, no numeric ranges, and `additionalProperties: false` works on all of them.

### 8.4 Cost and local throughput

RV-6 section 7 gives the arithmetic. Assume 64 calls for each 8-turn game at 5,500 input and 300 output tokens each. The uncached estimate is 3 cents for gpt-5-nano, 45 cents for Claude Haiku 4.5, 90 cents for Claude Sonnet 5, and 4.48 dollars for Claude Fable 5.1. Batch APIs cut this by half on all five vendors.

A local RTX 5090 with llama.cpp runs an 8B Q4 model at 186 tokens/s and a 32B Q4 model at 61 tokens/s. Thus one game costs 3 to 8 minutes of GPU time and no money. All prices are from vendor pages fetched on 2026-09-07 and will change.

### 8.5 Learning with language model agents

Reflexion, ExpeL, and Agent Workflow Memory are cheap and do not use training. The agent writes a lesson after each game and reads it before the next. EvoPrompt is practical with a local model and win rate as fitness. A LoRA fine-tune of a 7B to 14B model on the game's own traces is the next step. The owner made it year-one work on 2026-09-07. SPIRAL (arXiv 2506.24119) shows that 3B to 7B self-play RL on text games is possible.

A hobby-scale Diplomacy report (RV-8 section 4) shows two results that apply to a local model. A trie-based logits constraint increased valid moves from about 50 to about 75 percent. Per-token loss weights by move importance were the largest quality increase. <!-- Owner directive 2026-09-07: tuned local model as a fourth agent family -->

## 9. Browser technology (RV-7)

### 9.1 The engine-sharing decision

Four options were compared with sources. Option (b) has the strongest support: one Rust crate for the rules engine, with a wasm-bindgen crate for the browser and a PyO3 crate for Python. In-process Rust environment steps through PyO3 get to millions of steps/s on one laptop (rlox, 2.7 million steps/s at 512 environments on an Apple M3 Pro, CPU only). Automerge and Ruff show that one Rust crate can ship the two bindings at the same version. WebAssembly runs at a 45 to 55 percent mean slowdown against native code (Jangda and others, 2019), which is sufficient for a turn-based game.

Python stays the trainer language.

Option (c) is Python as the single source of truth with the browser as a thin client. It is sufficient for LAN play but cannot give the RL throughput. CPython is 10 to 200 times slower than Node.js on compute-bound benchmarks. Option (d), a C engine with Emscripten and cffi, is the fallback if the developer will not use Rust. Option (a), a TypeScript engine with a Node-to-Python bridge, has no measured bridge throughput in a fetched page.

RV-5 and RV-7 give different positions on the first step. RV-5 says a pure Python engine with 8 to 16 workers can give the 3,500 steps/s gate if observation construction is cheap. RV-5 defers a compiled core to v0.2. RV-7 says a compiled core from the start. Section 11 resolves this.

### 9.2 Rendering, hex math, and multiplayer

The board is small: 1,320 hexes for four boards, plus some hundreds of counters. Use Canvas 2D or PixiJS 8 with WebGL. Pre-render each board as one texture. Show counters as sprites from a generated atlas. Hit test in hex math, not in the DOM.

Honeycomb (MIT) has hex math but last published in 2023. Put hex math and LOS in the engine crate from the Red Blob pseudocode. The Squad Leader LOS rule belongs to this game.

For turn management, write the phase sequencer in the engine, because the trainer also uses it. For LAN, run a small authoritative host and transport signed, ordered command records on a WebSocket. A room code is the only credential. boardgame.io had no feature release after 2022. Colyseus (0.18.5, August 2026) is active if a room framework is wanted. CRDTs do not fit, because a wargame rejects moves.

### 9.3 Determinism and replay

JavaScript `Math.random()` cannot be seeded, and Python uses Mersenne Twister. Thus a game that must have the same dice in the browser and in Python must ship its own generator. Put it in the engine crate. Store the seed and the ordered command list, not the dice results. Hash the state after each command, so a replay stops at the first mismatch. Keep all rules arithmetic in integers.

### 9.4 Map generation with a hand-drawn look

Wave Function Collapse (MIT, with a JavaScript port) gives constraint-based tile placement. Red Blob noise terraces give contour steps for hill levels. Geomorphic edge constraints set the boundary hex row of each edge and let the generator fill the interior. rough.js (MIT) gives hachure fills and sketchy lines for woods and hill shade. mapgen4 (Apache-2.0) shows contour and edge-line rendering. No fetched page gives a recipe for the 1977 Avalon Hill look, so that is new work.

### 9.5 Tooling versions seen on 2026-09-07

Vite 8.2.2, TypeScript 7.0.2, Vitest 5.0.0, Playwright 1.63.0, PixiJS 8.20.1, pyo3 0.29.2, wasm-bindgen 0.2.128, maturin 1.15.0.

## 10. Community and social signal (RV-8)

The 1977 Squad Leader community is small and constant. BoardGameGeek lists 3,565 ratings and 7,028 owners. The General and Rules forums get one to two new threads a month, with the last posts in August 2026. The SQLA ladder runs tournaments on VSQL with six to eight games in progress. Solo play dominates the session reports. Hidden initial placement is the one problem that solo players cannot remove by hand.

Three signals are strong and shape the requirements:

1. The AI must obey the printed rules and show its work. Second Front players count the AI's fire phases against rule numbers and open "does the AI cheat" threads for years. The developer's answer is "exactly the same rules" and decisions "visible enough to argue with". A digital Squad Leader must have a log for each action with rule IDs, dice, and modifiers for the two sides.
2. Automate lookups and LOS, but keep the tabletop feel and make it a switch. VSQL LOS, the LnLT LOS function, and the SL spreadsheet calculators get praise. Second Front and Tigers on the Hunt get criticism for LOS feedback that is missing or comes too late. Valor and Victory shows that shown dice and tables annoy PC-native players. The board rules punish fire after a player examines the LOS, so the time at which the tool is available is a design decision.
3. Solo players are the core. An AI that controls hidden setup and concealment is for the solo base. Hotseat and network play with the same engine is for the "no multiplayer, no sale" group.

Two more signals. A fan Godot implementation of scenario 1 started in 2026 (GPL-3, 15 commits). Renegade Game Studios has a streamlined Squad Leader in digital playtest, which is a license risk and a proof of demand.

## 11. Implications for this project

These are the decisions the data supports. The Vision, Requirements, and Architecture documents build on them.

1. Ship Game Set I first. Scenarios 1 to 3 use rules 1 to 27 (infantry, flamethrowers, demolition charges, smoke, concealment, fanaticism, sewers). Each table for those rules is sourced: the IFT, the Close Combat Table, the Support Weapons Chart, the movement costs, and the terrain modifiers. The armor tables (To Hit, AFV Kill, hit modifiers, vehicle movement) are not sourced. Armor waits until a readable copy of data card page 2 is available.
2. Keep the rule IDs in the engine and in the action log. This satisfies the community signal and the legal analysis at the same time. Numbers and technical terms are safe, and a rule-cited log is what players want.
3. Draw new art and make new boards. The counter values and their positions are safe. The silhouettes and colors are new work.

   The four 1977 board layouts are a copyright risk if shipped as data. Recommendation: the generator ships, the style ships, and the four 1977 layouts are a user-supplied reference that the project does not ship. This is a decision for the owner. It changes what "looks like the board game maps" means.
4. Give the project a different name. Refer to Squad Leader in descriptive text with a non-affiliation notice.
5. One rules core, two bindings. The data favors a Rust core with PyO3 and wasm-bindgen bindings and one JSON conformance battery. The owner's siblings are all Python, so this is the largest departure from the family conventions and it is the owner's decision. The fallback that keeps the family conventions is a Python core with a thin browser client for v0.1 and a measured throughput gate. If the Python core cannot give 3,500 steps/s on the training workstation, the core moves to Rust before RL training starts.
6. LOS as vector geometry in the core: terrain polygons for each hex tested against the center-to-center segment. This works for the generated boards and agrees with the thread rule.
7. Determinism by construction: seeded generator in the core, event-sourced command log, state hash after each command, integer arithmetic only.
8. RL as PPO in raw torch with a unit-by-unit composed action and a legal-action mask from the engine. Add a snapshot league with scripted bots. Add behavior cloning from replays when 200 games are available. Use PBT or CMA-ES for the scripted bots. Budget 100 million to 300 million steps for a run.

9a. A tuned local model as a fourth agent family. It is a LoRA fine-tune of a 7B to 14B model on the game's traces, with constrained decoding on the legal command IDs. One tournament compares it against the scripted, learned, and prompted families (owner directive 2026-09-07).
9. LLM agents as engine-verified choosers. The engine emits a text state with unit-level annotations and a legal-move list with IDs. The model gives its analysis in free text and then emits JSON with a `move_id` enum. The engine verifies, retries one time with the rejection message, and then applies a scripted default. Text only. Record invalid-move rate, fallback rate, win rate, tokens, latency, and cost for each call from day one.
10. One OpenAI-compatible client for local servers and thin adapters for Anthropic, Gemini, xAI, and Mistral, with the sibling key-file pattern and presence-based provider discovery.
11. Hotseat and LAN through the same authoritative host process with a room code. No accounts. The engine controls hidden placement and concealment, so the human does not see the AI's hidden units.
12. Give the tabletop surface as a switch: dice, tables, and the LOS thread shown or hidden. Make the LOS tool available only at the times the rules let a player use it. Add a "casual" mode that removes the restriction.

## 12. Open questions the literature does not resolve

- OQ-R1: Where is a readable copy of data card page 2 (To Hit, AFV Kill, hit modifiers, vehicle movement)? The owner's physical copy is the most likely source.
- OQ-R2: Is the 538 hill symbol at 2BB5 (rules) or 2BB6 (scan)? A full resolution check settles it.
- OQ-R3: Does a unit-by-unit PPO policy learn Squad Leader tactics at 100 million to 300 million steps? No paper tried a game with dice, morale, rout, and concealment at this scale on one GPU.
- OQ-R4: What is the measured invalid-move rate of a 14B to 32B local model on Squad Leader phase decisions with the engine-verified harness? WARBENCH suggests high rates for small models with complex terrain. Measure in project.
- OQ-R5: Can a generated board in the 1977 style satisfy the owner's "looks like the board game" test without the four 1977 layouts? This is a taste question that a prototype answers.
- OQ-R6: Does the MMP license from Hasbro cover computer versions? One unverified forum claim says it does not. This affects the risk of an official digital competitor and the value of a permission request.
- OQ-R7: What is the throughput of a pure Python Squad Leader engine on the training workstation? This number gives the answer to implication 5.

## References

Each appendix has its own full reference list with URLs. The list below names the sources that have the most weight in this synthesis.

1. archive.org, "Squad Leader by Avalon Hill Scans", 600 DPI 4th edition boards and counter sheets. https://archive.org/details/allied-infantry-back
2. Squad Leader Academy, scenario card scans and component inventory. http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/index.html and http://www.wargameacademy.org/sqla/Resources/Inventories/inventory_sql.txt
3. Scribd, "Squad Leader Quick Reference Data Card (English) - V4", page 1. https://www.scribd.com/document/167277427/Squad-Leader-Quick-Reference-Data-Card-English-V4
4. vasl-developers/vasl, LOS engine and board archives. https://github.com/vasl-developers/vasl
5. Tetris Holding v. Xio Interactive, 863 F. Supp. 2d 394 (D.N.J. 2012). https://static.case.law/f-supp-2d/863/cases/0394-01.json
6. U.S. Copyright Office, "Games". https://www.copyright.gov/register/tx-games.html
7. Palma, Santos, Dias, "Playing Hex and Counter Wargames using Reinforcement Learning and Recurrent Neural Networks", arXiv 2502.13918. https://arxiv.org/abs/2502.13918
8. Huang and others, "Gym-uRTS", arXiv 2105.13807. https://arxiv.org/abs/2105.13807
9. Paglieri and others, "BALROG", arXiv 2411.13543. https://arxiv.org/abs/2411.13543
10. Duffy and others, "Democratizing Diplomacy", arXiv 2508.07485. https://arxiv.org/abs/2508.07485
11. PyO3 discussion #1935 on dual Wasm and Python bindings from one crate. https://github.com/PyO3/pyo3/discussions/1935
12. Second Front, "AI Defensive Fire" thread, players audit the AI against rule numbers. https://steamcommunity.com/app/1148490/discussions/0/688616674580127428/

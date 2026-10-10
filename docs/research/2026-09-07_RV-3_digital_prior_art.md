# RV-3: Digital prior art for Squad Leader and available building blocks

Date: 2026-09-07. Project: Squad_Leader_AI.

Evidence rule: each fact has a URL in the References list. The reference number is in square brackets. Star counts and push dates come from the GitHub API on 2026-09-07. Quoted text is verbatim from the source.

## 1. VASSAL, VSQL, and VASL

### 1.1 VSQL (Squad Leader module for VASSAL)

- Current version: "VSQL 4.3.8" on VASSAL 3.7+, with "COD/GIA Extension 9.5". The page says "VSQL 4.3.8 is not compatible with prior versions, although one can install both." [1]
- Contents: boards 00 to 10 for Squad Leader and Cross of Iron, boards 11 to 24 for Crescendo of Doom and GI: Anvil of Victory. The page shows an LOS function with colors for hindrance and blocked, concealment counters, hidden-in-place units with password protection, and dice. It supports live play in online rooms and play by email with log files. [1]
- Version 4.3.3.2 (announced January 2022) supports VASSAL 3.5+ and 3.6+. The maintainers named in the announcement are Brent E, Bill Thomson, Joel U, and Scott B. The release added a "Look Here" function that "flashes a red circle around a hex on Ctrl-Right click". [2]
- The maintainers released version 4.3.4 for VASSAL 3.6.17 (thread title, May 2023). BoardGameGeek refuses automated fetches (HTTP 403), so I could not read the thread body. [3]
- Older history: VSQL 4.1.97c ran on VASSAL 3.1.20. The page says "Boards in use were previously Version 4 from Toumoland. Version 5 Boards are now the VSQL standard." The change log has the entry "NPE in CASL.Map.GameMap.LOS()", which shows that VSQL used the CASL LOS engine from VASL 4. [4] The CASL repository is "Legacy LOS code for VASL 4.0", LGPL-2.1, last push 2019-06-22. [5]
- License or permission statement: I found no statement on the pages I could read. The VASSAL module library page loads with JavaScript, and WebFetch got only the page title. [6]
- Automation: the VASSAL engine itself does no LOS check. The VASSAL reference manual says "There is no automatic checking if a Line of Sight exists by Vassal, this is up to the players to determine." [7] VSQL adds an LOS check on top of the engine through the CASL code [1][4]. VSQL does not automate combat resolution or morale. It is a play surface with dice, LOS, and hidden units.
- VASSAL engine: GitHub, LGPL-2.1, 626 stars, Java, last push 2026-09-07. [8]

### 1.2 VASL (Advanced Squad Leader module)

- Repository: vasl-developers/vasl, LGPL-2.1, 72 stars, Java, last push 2026-09-07. The latest tag is v6.7.4-beta4 (2026-09-03). The README says the code is "a library, not a complete standalone application" that VASSAL uses. [9]
- Release page: VASL 6.7.3 (May 7, 2026) is for "at least VASSAL3.7.20". The page says a font for the SVG counter graphics "is now included in the VASL VMOD". It shows LOS corrections and "SASL dr/DR buttons". [10]
- What is automated: LOS checks and dice. The LOS help document says: "VASL provides an integrated tool you can use to check line of sight (LOS)." "Version 6 and later boards support LOS checking." The thread "snaps to either the center dot of the target hex, or to the nearest hex vertex." [11]
- Thread colors show clear, hindered, and blocked. Verbose mode reports hex coordinates, levels, range, the number of hindrances, and the cause of a block. [11]
- The user guide page gives the colors: "Black: LOS is clear", "Red: LOS is hindered", "Blue: LOS is blocked". [12]
- Rule interpretation: "The LOS engine does not enforce the rule that terrain must be visible on both sides of the thread to affect LOS. If the thread touches an obstacle or hindrance, LOS will be affected." [11]
- LOS source: src/VASL/LOS/Map/Map.java (7,481 lines), Hex.java, Terrain.java, LOSResult.java, Location.java. The Map class comment says each cell "in the grid corresponds to one pixel in the map image". The class holds `char[][] terrainGrid; // terrain for each pixel` and `byte[][] elevationGrid; // height for each pixel`. The constructor has the parameters hexWidth, hexHeight, A1CenterX, A1CenterY, imageWidth, and imageHeight. [13]
- LOS method: `public void LOS(Location source, boolean useAuxSourceLOSPoint, Location target, boolean useAuxTargetLOSPoint, LOSResult result, ...)`. The method steps column by column across the pixel grid. For each column it steps through the rows between an enter value and an exit value, and reads the terrain and elevation at each pixel. [13]
- Hexside conditions: when the LOS runs along a hexside (`LOSisHorizontal || LOSis60Degree`), the method gets the two adjacent hexes and checks the two. The comment says: "Standard LOS is drawn to the counterclockwise-most hexspine on the bypassed hexside. The auxillary LOS point is the clockwise-most hexspine on the bypassed hexside." [13]
- Board storage: each board is a zip archive without an extension. I downloaded boards/bdFiles/bd01 (362,076 bytes) and examined its contents. It contains bd01.gif (173,556 bytes), BoardMetadata.xml, BoardMetadata, LOSData (41,070 bytes), data, SSRControls, and overlay images (01_DenseJungle.gif, 01_LightWoods.gif, 01_NoRoads.gif, SSO_O.png). [14]
- BoardMetadata.xml holds `name="01" version="6.9" versionDate="Jan 2025" author="TR" boardImageFileName="bd01.gif" hasHills="FALSE" width="33" height="10"`. The comment says "Standard geomorphic boards are 10 by 33 hexes". A buildingTypes element overrides building types for each hex, for example `hexName="E4" buildingTypeName="Stone Building, 2 Level"`. [14]
- Hex coordinate mapping: BoardArchive.java has the constants `LOSDataFileName = "LOSData"` and `GEO_A1_Center = new Point2D.Double(0, GEO_HEX_HEIGHT/2.0)`. The archive reader gives getA1CenterX and getA1CenterY, "x location of the A1 center hex dot". The Map object maps pixels to hexes with gridToHex and getHexCenterPoint. [15]
- LOS data tools: vasl-developers/los-gui, "Code for the VASL LOS GUI", LGPL-2.1, 1 star, Java, last push 2026-07-14. [16] The dev documentation folder has UpdatingVASLboards.pdf. [13]
- Counter art: the repository holds 6,270 SVG files. The counter dist/images/ge/ge000H.svg uses `font-family: Nimbus Sans L`. The folder dist/images/fonts holds NimbusSanL-Reg.ttf, NimbusSanL-Bol.ttf, italic variants, and KaushanScript-Regular.ttf. [17]

## 2. Commercial computer versions and comparable digitizations

### 2.1 Avalon Hill's Squad Leader (2000)

- Developer Random Games, publisher Hasbro Interactive with the MicroProse label, release October 24, 2000. The engine came from Warhammer 40,000: Chaos Gate. Soldiers at War used the same engine. [18]
- Design intent: producer Bill Levay said the goal was the "spirit" of the board game and an "accessible" game, "rather than a hardcore simulation or literal adaptation of the board version". [18]
- Reception: Metacritic 46/100. Computer Gaming World 1/5, PC Gamer (US) 12%, GameSpot 3.8/10, IGN 5/10, GameSpy 68%. [18]
- William R. Trotter (PC Gamer) wrote "Hasbro has confirmed everyone's worst fears." Trotter wrote that the game would antagonize each fan of Squad Leader and confuse most newcomers. Peter Suciu (2004) said it was "one of the worst board-to-computer adaptations to date". [18]
- Metacritic critic table: GameZone 75, Game Over Online 52, Electric Playground 50, IGN 50, GameSpot 38 ("Clunky and unpolished."), TotalGames.net 34, GamerWeb PC 20. [19]
- Lesson: the game dropped the board game rules and hex map for the engine of an earlier isometric game. Fans and reviewers rejected it for that cause [18][19].

### 2.2 Computer Squad Leader and Combat Mission

- In January 1997 Avalon Hill contracted Big Time Software for a computer version of Advanced Squad Leader, named Computer Squad Leader. The contract ended in July 1998, the month Hasbro bought Avalon Hill. Charles Moylan did not add the ASL-specific features until late. Thus the game continued as Combat Mission with a WeGo turn system and a 3D engine. [20]
- Combat Mission is thus not a hex-and-counter digitization. It is a 3D game that resolves the moves of the two sides at the same time, and it grew from an ASL contract.

### 2.3 Second Front (2023)

- Developer Hexdraw (Jo Bader), publisher MicroProse, released in 2023. [21]
- ASL fidelity: asl-players.net shows "direct 1-to-1 correlation with some of the unit stats of ASL" and says "Second Front vehicles duplicate the numbers of their ASL analog." The author writes that it is ASL with some changes for the AI. The author also writes that the AI is "very timid to counterattacks, especially with vehicles." A commenter shows missing features: "OBA, entrenching, tons of nationalities", and routing "is totally out of your hands". [22]
- Strengths (Breeden, 2023-03-13): "Second Front mostly looks like a board game". The game "takes care of a lot of the backend calculations and rule applications that tend to bog down board games." [23]
- More strengths (Breeden): players "see a percentage of how likely a shot is to hit". Readied units "have the ability to interrupt actions". Criticism: "the lack of artillery or air power". [23]
- Weaknesses (Tim Stone, 2023-01-27): infantry fire uses four range bands, so "the extra hex of range means there is zero chance C will lose men if fired upon". Gun ranges use nine bands. [24]
- More weaknesses (Stone): reload chance is random. "One AT gun, tank, or mortar might get to fire once in a turn while an identical but luckier compatriot gets to fire two" or more times. Standard ammunition "is always inexhaustible". [24]
- Sir Nuno (2023-01-31) praises the AI ("will try to puncture your lines, exploit those weaknesses, flood the objectives") and multi-hex buildings. Sir Nuno criticizes binary victory conditions ("trial and error, brute forcing my way through the game"), the "absolutely arbitrary" reload mechanic, and the tutorial. [25]
- Metacritic shows one critic review, PC Invasion 85: "Second Front is not literally a PC adaptation of ASL, but it is as much we could hope for". [26]

### 2.4 Conflict of Heroes: Awakening the Bear (PC, 2012)

- Developer Western Civilization Software, publisher Slitherine, release May 8, 2012. Steam shows "Mixed", 65% positive of 32 reviews. Features: AI opponent, PBEM multiplayer, scenario editor, "3D line-of-sight calculations using ray casting". [27]
- Review (play-board-games, 5/6): "The battle system has been ported very well to the PC game." "The graphics are very nice and you have the option to play in a 2-D mode or with chits on the board." Main defect: "Line of sight is hard to determine until after you move a unit. It would be nice to easily determine the line of site from a space you are moving to." [28]

### 2.5 Lock 'n Load Tactical Digital (2020)

- Developer and publisher Lock 'n Load Publishing, release April 2, 2020, Windows and macOS, Early Access, "82% of the 566 user reviews for this game are positive". Features: AI, online and LAN multiplayer, Steam Workshop, editor DLC. [29]
- Review (theboardgameschronicle, 2023-04-18): "I noticed no software issues nor rules implementation ones." The LOS preview is a "very cool option in the app". The AI "is a decent opponent". Criticism: "the Starter Kit is too small". [30]

### 2.6 Panzer Command (2006 to 2013)

- Developer Koiosworks, publisher Matrix Games. Titles: Operation Winter Storm (2006-06-29), Kharkov (2008-04-10), Ostfront (Wikipedia gives 2013-05-12). Each turn "consists of two 40 second phases, the first for orders, the second for reactions and targeting." Unit data is editable XML. [31]
- Review (Digitally Downloaded, dated 2011-05-27, 3.5 stars): "this game plays out at a glacial pace", "The bigger scenarios take literally weekends to complete". The reviewer also writes that the AI is not bright. [32] Note: the review date is earlier than the Wikipedia release date for Ostfront. I could not resolve this difference.

### 2.7 Summary of lessons

| Title | Strengths | Weaknesses | Sources |
|---|---|---|---|
| Squad Leader 2000 | None that reviewers reported | Dropped the board rules and hex map, used the Chaos Gate engine | [18][19] |
| Second Front | Board game look, rule automation, hit percentages, reaction fire, AI | Coarse range bands, random reloads, no OBA or air, binary victory | [22][23][24][25] |
| Conflict of Heroes PC | Faithful rules port, 2D chit mode, AI, solo play | No LOS display before a move | [27][28] |
| LnLT Digital | Correct rules, LOS preview, AI, editor | Small content | [29][30] |
| Panzer Command | Depth, editable data | Slow, weak AI | [31][32] |

## 3. Open-source engines and libraries

### 3.1 Browser (TypeScript or JavaScript)

| Project | License | Stars | Language | Last push | Gives | Source |
|---|---|---|---|---|---|---|
| boardgame.io | MIT | 12,428 | TypeScript | 2026-08-18 | Turn-based game engine, phases, multiplayer, bots | [33] |
| Honeycomb (honeycomb-grid) | MIT | 704 | TypeScript | 2026-02-19 | Hex grid math, version 4.1.5 | [34] |
| PixiJS | MIT | 48,132 | TypeScript | 2026-09-07 | 2D WebGL renderer | [35] |
| Phaser | MIT | 40,268 | JavaScript | 2026-08-21 | 2D game framework | [36] |
| milsymbol | MIT | 794 | JavaScript | 2026-06-27 | NATO APP-6 and MIL-STD-2525 symbols as SVG or Canvas | [37] |
| coyotte508/hexagrid | MIT | 9 | TypeScript | 2023-09-27 | Hex grid for npm | [38] |
| yiyuezhuo/Hex-Wargame-JavaScript | MIT | 38 | JavaScript | 2022-05-16 | Hex wargame with CRT, CSV scenarios, DOM counters with NATO symbols | [39] |
| dahifi/hexops | MIT | 0 | HTML | 2026-02-14 | Single-file hex play surface, no LOS | [40] |
| 2551147/husky-operation-sicily | none | 2 | HTML | 2026-06-27 | Browser hex-and-counter game (Sicily 1943) | [41] |

boardgame.io data:

- Phases: a phase without its own moves uses the global moves. A phase with its own moves overrides the global moves. [42]
- Phase options: start, next, endIf, onBegin, onEnd. End checks run in this sequence: game endIf, then phase endIf, then turn endIf. [42]
- Randomness: "You can set the initial `seed` used for the random number generator on your game object". "The RNG and its state must stay on the server." Dice: `random.Die(spotvalue, diceCount)` and wrappers D4 to D20. [43]
- Bots: the game gives `ai.enumerate`, which gives the list of legal moves. The tutorial says the framework uses "MCTS under the hood to explore the game tree and find good moves" with 1000 iterations by default. The debug panel has Play and Simulate. [44]
- Last release v4.1.5 on 2023-11-20. Last commit 2026-08-10. [33]
- The notable projects page shows one hex game and no hex-and-counter wargame. [45]

Honeycomb: "heavily inspired by Red Blob Games' blog posts". It works in browsers and Node 16+. The core has no rendering dependency. A* is an example, not a core feature. [34]

Red Blob Games hex guide:

- Topics: coordinate systems (offset, cube, axial, doubled), distances, rounding, line drawing, field of view. [46]
- Line drawing: "To draw a line, I linearly interpolate between two hexes, and then round it to the nearest hex." An epsilon nudge (1e-6, 1e-6, -2e-6) moves points off hex edges. [47]
- The implementation page generates code in C++, Python, C#, Haxe, Java, JavaScript, TypeScript, Lua, and Rust. I found no license statement on the two pages. [46][47]

### 3.2 Python

| Project | License | Stars | Last push | Gives | Source |
|---|---|---|---|---|---|
| maximinus/wargame | GPL-3.0 | 29 | 2024-07-23 | Pygame engine, no hex or LOS documented | [48] |
| hongkongwargamer/ASLGameLog | GPL-3.0 | 3 | 2021-12-02 | Game log, not an engine | [49] |
| lifelike/countersheetsextension | NOASSERTION | 265 | 2025-07-29 | Inkscape counter sheet generator | [50] |

### 3.3 GitHub search results for Squad Leader and ASL engines

The GitHub API search for "squad leader hex" found no related repository. The search for "advanced squad leader" found these repositories [49]:

- vasl-developers/vasl (see section 1.2).
- craigonic/jasl: "ASL (Advanced Squad Leader) helper program, implemented in Java", no license, 4 stars, last push 2026-09-06. The README request got HTTP 404. [51]
- shawnshifflett/openASL: TeX learning aids, no license, 3 stars, last push 2016-08-19. [52]
- Small projects with 1 star: btbroot/asl-helper (AGPL-3.0, Jupyter), viniromao/advancedSquadLeader (MIT, C), nathanbaney/asl_tcod (Python), mulcare/aslogic (Ruby). [49]

Conclusion: no open-source project has the Squad Leader or ASL rules as an engine. VASL has LOS only.

### 3.4 Rust hex and wargame projects

| Project | License | Stars | Last push | Gives | Source |
|---|---|---|---|---|---|
| ManevilleF/hexx | Apache-2.0 | 371 | 2026-08-06 | Hex math, version 0.25.0, axial coordinates, line drawing, FOV, A*, Bevy features | [53] |
| ozkriff/zemeroth | Apache-2.0 | 1,456 | 2024-03-26 | Turn-based tactical game | [54] |
| ozkriff/zoc | MIT or Apache-2.0 | 394 | 2019-11-11 | Hex strategy game, fog of war, reaction fire, discontinued 2017 | [55] |
| Shengda21/OpenStratCore | Apache-2.0 | 0 | 2026-06-11 | Deterministic Rust hex core, PyO3 for RL, WASM for browser, PettingZoo, PixiJS front end, 11 commits | [56] |
| Goblinlordx/ironline-wars | none | 0 | 2026-07-30 | Event-sourced hex tactics scaffold, Bevy, browser through WASM | [57] |

OpenStratCore has the same architecture as the plan for this project. It is real-time, not turn-based, and it is embryonic (0 stars, 11 commits). It is a pattern to study, not a dependency. [56]

## 4. One rules engine for browser (WASM) and Python

### 4.1 Real projects that ship one Rust core to the two targets

| Project | License | Stars | Last push | Python binding | Browser binding | Source |
|---|---|---|---|---|---|---|
| joamag/boytacean (Game Boy emulator) | Apache-2.0 | 679 | 2026-09-07 | PyO3, `pip install .` | wasm-pack | [58][59] |
| oxigraph/oxigraph (SPARQL database) | Apache-2.0 or MIT | 1,867 | 2026-09-07 | python/ (pyoxigraph, PyO3) | js/ (wasm-bindgen) | [60] |
| y-crdt/y-crdt (Yjs port) | MIT | 2,155 | 2026-08-28 | pycrdt (PyO3) | ywasm (wasm-bindgen) | [61] |
| microsoft/regorus (Rego interpreter) | NOASSERTION on GitHub API | 343 | 2026-09-03 | bindings/python | bindings/wasm | [62] |
| GoPlasmatic/datalogic-rs (JSONLogic) | Apache-2.0 | 87 | 2026-09-07 | bindings/python | bindings/wasm | [63] |
| dimforge/rapier (physics) | Apache-2.0 | 5,720 | 2026-08-28 | python/rapier-py-3d | wasm-bindgen in root Cargo.toml | [64][65] |

boytacean is the closest analog to a game engine. Its root Cargo.toml has `crate-type = ["cdylib", "rlib"]` and feature flags `wasm = ["wasm-bindgen", "js-sys", "boytacean-common/wasm"]` and `python = ["pyo3", "boytacean-common/python"]`. The two dependencies are optional. [59]

datalogic-rs shows the test strategy: "every binding wraps the same core and passes the same 59-suite conformance battery", "1,698 cases across 59 suites, run against the same core every binding ships". [63]

A GitHub code search for Cargo.toml files that name wasm-bindgen and pyo3 together also found RustPython, microsoft/qdk, rerun-io/rerun, nickel-lang/nickel, and BoundaryML/baml. [66]

### 4.2 Design guidance

Mathieu Leplatre (2020-09-08) built one `canonical_json` crate with two thin binding crates: one with PyO3 (built with maturin) and one with wasm-bindgen (built with wasm-pack). The post tells about duplicated boilerplate in the binding layers and points to uniffi-rs as a possible solution. [67]

### 4.3 Recommendation

Use a Rust core crate with no I/O and no binding code. Add two thin binding crates:

- `sl-py` with PyO3 and maturin for the reinforcement learning harness.
- `sl-wasm` with wasm-bindgen and wasm-pack for the browser.

Make the core deterministic from a seed and a command stream, as OpenStratCore does ("The same seed + command stream always replays into the same game") [56]. Keep one conformance test battery in JSON that the two bindings run, as datalogic-rs does [63]. Use hexx for hex math if it fits, or write the small hex module in the core [53].

Do not use boardgame.io as the rules engine. Its game data and RNG live in JavaScript, and Python could not share them [43]. Its phase and lobby model is a good reference for the browser shell [42].

## 5. Hex line-of-sight algorithms

### 5.1 Published algorithms

- Clark Verbrugge, "Hex Grids", version 3, copyright 1996 and 1997, hosted by Amit Patel. Section 3 calculates LOS with a modified Bresenham line. [68]
- Verbrugge section 6, "LOS by Intersection of Hexagons with a Straight Line", finds all hexagons that a straight line touches. It has different code paths for a vertex that is on the line, with the comment "current vertex (i)" on the line. [68]
- Verbrugge FOV: an obstacle makes a shadow that hides all hexagons behind it. The diagram marks fully hidden hexes S and hexes in part hidden P. [68]
- zvold (2010-02-07) extends Bresenham to visit each hexagon that the line cuts, not only the hexes nearest the line. An error term (epsilon) against thresholds of plus or minus 0.5 and 1.0 selects the next hex. The test "epsilon >= 1.0", and not "epsilon > 1.0", makes a line that passes directly between two hexes count the two hexes. An integer-only variant and an all-quadrant variant follow. [69]
- Red Blob Games: linear interpolation in cube coordinates plus cube rounding, with an epsilon nudge for points on edges. The guide says field of view "turns out to be trickier" than it seems, with more than one correct interpretation. [46][47]
- hexx (Rust) ships line drawing and a field-of-view algorithm. [53]
- A GameDev.net thread (2011) and a BoardGameGeek thread, "Hex-grid LOS math general solution", discuss the same problem. The two sites refused my fetches (HTTP 403), so I give only the URLs. [70][71]

### 5.2 VASL's approach (the closest to the Squad Leader rule)

VASL does not use a hex-level algorithm. It rasterizes the board to a terrain grid and an elevation grid with one cell for each pixel. Then it walks the pixels between the source and target points column by column. Each pixel maps back to a hex, and the rules run for each pixel (buildings, hexsides, depressions, rooftops, bridges). [13]

Bypass and hexside conditions use auxiliary aiming points at hexspines. A LOS along a hexside checks the two adjacent hexes. [13] This is the digital form of the board rule, where a thread from center dot to center dot touches printed terrain. The help document shows that the engine tests contact with the thread, not visibility on the two sides. [11]

### 5.3 Implication for this project

Squad Leader boards are hand-drawn art with partial-hex terrain. A pixel or vector raster of the terrain, as in VASL, matches the board rule better than a pure hex-cell algorithm. A vector approach (terrain polygons for each hex, segment intersection against the center-to-center line) gives the same result with less data and works for generated boards. The hex-cell algorithms in section 5.1 are useful for range, fire lanes, and AI approximations.

## 6. Counter and map rendering that looks like cardboard

### 6.1 Counter fonts

- The 1977 counters do not use one typeface. On FontTalk, a contributor examined the Squad Leader counters and concluded "they used a mixture of sans serif faces for these tiles, some even on one piece". The faces named were Helvetica, Univers Bold Condensed, and possibly Venus, Nimbus, or URW Linear. Identification tools suggested Archivo Narrow and Pragati Narrow. The poster used Acumin Pro as a compromise. [72]
- The jzsquadleader counter project says "Squad Leader fonts do not appear consistent. They vary from game to game, and seem to use some variations within games (eg the number 4 on Cross of Iron). For the original, I have used Acumin Variable Concept which is an Adobe font." [73]
- VASL's SVG counters use Nimbus Sans L, and the repository ships the Nimbus Sans L TTF files. [17]
- Practical selection: a Helvetica-class sans with condensed weights. Nimbus Sans L is free and is what VASL uses [17]. Archivo Narrow is free on Google Fonts, and a font identification tool suggested it for the counters [72].

### 6.2 Counter geometry and colors

- Squad Leader ships "520 1/2-inch counters and 192 5/8-inch" (fraction glyphs in the source replaced with ASCII). [74]
- jzsquadleader: "The original counters have 2 sizes, 1/2" (squads, leaders, markers, small equipment) and 5/8" (vehicles, large equipment and markers)." Files are 800 by 800 px for 1/2 inch and 1000 by 1000 px for 5/8 inch, so 1600 px for each inch. Colors: goldenrod for Soviet, skyblue for German, and #d5d22f for the US, because "There is no good match for the (horrid!) US colour for original Squad Leader." License CC BY-NC-SA 4.0. [73]
- The Wikipedia counter article says counters "often include a simplified APP-6a representation". [74]

### 6.3 Counter generation tools

- lifelike/countersheetsextension (Inkscape): templates are "5/8 x 5/8 inches in size", with "7 included basic unit templates" and NATO unit dimension symbols. Sheets come from CSV files, for example nato_counters.csv. Text and image slots use ids with `-t/n/` and `-i/n/` suffixes. [75]
- milsymbol: NATO APP-6 (B, D, E) and MIL-STD-2525 (C, D, E) symbols as SVG or Canvas instructions, "1,000 symbols in under 20 milliseconds". [37]
- VASL: 6,270 SVG counter files with embedded font-family, which shows that SVG plus a bundled font is a proven method for ASL-style counters. [17]

### 6.4 Board look

- Second Front reviewers describe the look as "mostly looks like a board game". [23]
- Conflict of Heroes PC offers "a 2-D mode or with chits on the board". [28]
- VASL boards are GIF raster scans (bd01.gif) with overlay GIFs. [14]
- Texture and drop shadow methods: I found no source with verified technical data. The Squad Leader 2000 game is the counter-example, because it dropped the board look and reviewers rejected it [18].

## 7. Five best URLs

1. VASL source, LOS engine and board archives: https://github.com/vasl-developers/vasl [9]
2. VASL LOS help (rule interpretation and limits): https://github.com/vasl-developers/vasl/blob/develop/dist/LOS.pdf [11]
3. boytacean, one Rust crate with `wasm` and `python` feature flags: https://github.com/joamag/boytacean [58]
4. Clark Verbrugge, Hex Grids (LOS by intersection, FOV shadows): http://www-cs-students.stanford.edu/~amitp/Articles/HexLOS.html [68]
5. VSQL module page (contents and features): https://sites.google.com/site/2012squadleadertourny/vsql-module [1]

## References

1. VSQL Module, Squad Leader Ladder and Tournament site. https://sites.google.com/site/2012squadleadertourny/vsql-module
2. SQLA Announcements, VSQL 4.3.3.2, January 2022. https://squadleaderladder.blogspot.com/2022/01/vassals-squad-leader-module-updated-to.html
3. BoardGameGeek thread, VSQL 4.3.4 for VASSAL 3.6.17 (title only, HTTP 403 on fetch). https://boardgamegeek.com/thread/3083604/squad-leader-vsql-module-434-for-vassal-3617-relea
4. Virtual Squad Leader (VSQL), Wargame Academy. http://www.wargameacademy.org/sqla/Vsql/index.html
5. vasl-developers/casl, Legacy LOS code for VASL 4.0. https://github.com/vasl-developers/casl
6. VASSAL module library, Squad Leader. https://vassalengine.org/library/projects/Squad_Leader
7. VASSAL Reference Manual, Line of Sight Thread. https://vassalengine.org/doc/latest/ReferenceManual/LineOfSight.html
8. vassalengine/vassal. https://github.com/vassalengine/vassal
9. vasl-developers/vasl. https://github.com/vasl-developers/vasl
10. VASL downloads, 6.7.3. https://vasl.info/download.htm
11. VASL LOS Help (dist/LOS.pdf in the VASL repository). https://github.com/vasl-developers/vasl/blob/develop/dist/LOS.pdf
12. VASL user guide, Checking Line of sight. https://vasl.info/los/out/src/t_checking_los.html
13. VASL Map.java LOS engine. https://github.com/vasl-developers/vasl/blob/develop/src/VASL/LOS/Map/Map.java
14. VASL board archive bd01 (zip, contents examined with unzip). https://github.com/vasl-developers/vasl/blob/develop/boards/bdFiles/bd01
15. VASL BoardArchive.java. https://github.com/vasl-developers/vasl/blob/develop/src/VASL/build/module/map/boardArchive/BoardArchive.java
16. vasl-developers/los-gui. https://github.com/vasl-developers/los-gui
17. VASL counter SVG with Nimbus Sans L, and fonts folder. https://github.com/vasl-developers/vasl/blob/develop/dist/images/ge/ge000H.svg and https://github.com/vasl-developers/vasl/tree/develop/dist/images/fonts
18. Wikipedia, Avalon Hill's Squad Leader. https://en.wikipedia.org/wiki/Avalon_Hill%27s_Squad_Leader
19. Metacritic, Squad Leader. https://www.metacritic.com/game/squad-leader/
20. Wikipedia, Combat Mission: Beyond Overlord. https://en.wikipedia.org/wiki/Combat_Mission:_Beyond_Overlord
21. GeekDad, MicroProse Second Front, February 2023. https://geekdad.com/2023/02/microprose-takes-us-back-to-classic-wwii-wargames-with-second-front/
22. asl-players.net, Second Front: A Comparison to ASL, Neal U., 2023-01-31. https://asl-players.net/second-front-a-comparison-to-asl/
23. Gameindustry.com, Second Front review, John Breeden II, 2023-03-13. https://www.gameindustry.com/reviews/game-review/second-front-is-a-dream-come-true-for-armchair-tacticians/
24. Tally-Ho Corner, Second Front: Roman's Reservations, Tim Stone, 2023-01-27. https://tallyhocorner.com/2023/01/second-front-romans-reservations/
25. Strategy and Wargaming, Second Front review, 2023-01-31. https://strategyandwargaming.com/2023/01/31/second-front-review-a-magnum-opus-despite-its-flaws/
26. Metacritic, Second Front. https://www.metacritic.com/game/second-front/
27. Steam, Conflict of Heroes: Awakening the Bear. https://store.steampowered.com/app/510320/Conflict_of_Heroes_Awakening_the_Bear/
28. play-board-games, Conflict of Heroes PC review. https://www.play-board-games.com/conflict-of-heroes-awakening-the-bear-pc-game-review/
29. Steam, Lock 'n Load Tactical Digital: Core Game. https://store.steampowered.com/app/1149940/Lock_n_Load_Tactical_Digital_Core_Game/
30. The Boardgames Chronicle, LnLT Digital Starter Kit first impressions, 2023-04-18. https://theboardgameschronicle.com/2023/04/18/lock-n-load-tactical-digital-starter-kit-first-impressions/
31. Wikipedia, Panzer Command. https://en.wikipedia.org/wiki/Panzer_Command
32. Digitally Downloaded, Panzer Command Ostfront review, 2011-05-27. https://www.digitallydownloaded.net/2011/05/review-panzer-command-ostfront-pc.html
33. boardgameio/boardgame.io. https://github.com/boardgameio/boardgame.io
34. flauwekeul/honeycomb. https://github.com/flauwekeul/honeycomb
35. pixijs/pixijs. https://github.com/pixijs/pixijs
36. phaserjs/phaser. https://github.com/phaserjs/phaser
37. spatialillusions/milsymbol. https://github.com/spatialillusions/milsymbol
38. coyotte508/hexagrid. https://github.com/coyotte508/hexagrid
39. yiyuezhuo/Hex-Wargame-JavaScript. https://github.com/yiyuezhuo/Hex-Wargame-JavaScript
40. dahifi/hexops. https://github.com/dahifi/hexops
41. 2551147/husky-operation-sicily. https://github.com/2551147/husky-operation-sicily
42. boardgame.io phases documentation. https://github.com/boardgameio/boardgame.io/blob/main/docs/documentation/phases.md
43. boardgame.io randomness documentation. https://github.com/boardgameio/boardgame.io/blob/main/docs/documentation/random.md
44. boardgame.io tutorial (bots section). https://github.com/boardgameio/boardgame.io/blob/main/docs/documentation/tutorial.md
45. boardgame.io notable projects. https://github.com/boardgameio/boardgame.io/blob/main/docs/documentation/notable_projects.md
46. Red Blob Games, Hexagonal Grids. https://www.redblobgames.com/grids/hexagons/
47. Red Blob Games, Hexagonal Grids implementation. https://www.redblobgames.com/grids/hexagons/implementation.html
48. maximinus/wargame. https://github.com/maximinus/wargame
49. GitHub API repository search, "advanced squad leader" (results recorded 2026-09-07). https://api.github.com/search/repositories?q=advanced+squad+leader&sort=stars
50. lifelike/countersheetsextension. https://github.com/lifelike/countersheetsextension
51. craigonic/jasl. https://github.com/craigonic/jasl
52. shawnshifflett/openASL. https://github.com/shawnshifflett/openASL
53. ManevilleF/hexx. https://github.com/ManevilleF/hexx
54. ozkriff/zemeroth. https://github.com/ozkriff/zemeroth
55. ozkriff/zoc. https://github.com/ozkriff/zoc
56. Shengda21/OpenStratCore. https://github.com/Shengda21/OpenStratCore
57. Goblinlordx/ironline-wars. https://github.com/Goblinlordx/ironline-wars
58. joamag/boytacean. https://github.com/joamag/boytacean
59. boytacean Cargo.toml (feature flags). https://github.com/joamag/boytacean/blob/master/Cargo.toml
60. oxigraph/oxigraph. https://github.com/oxigraph/oxigraph
61. y-crdt/y-crdt. https://github.com/y-crdt/y-crdt
62. microsoft/regorus. https://github.com/microsoft/regorus
63. GoPlasmatic/datalogic-rs. https://github.com/GoPlasmatic/datalogic-rs
64. dimforge/rapier. https://github.com/dimforge/rapier
65. rapier root Cargo.toml. https://github.com/dimforge/rapier/blob/master/Cargo.toml
66. GitHub code search, Cargo.toml with wasm-bindgen and pyo3 (results recorded 2026-09-07). https://github.com/search?q=%22wasm-bindgen%22+%22pyo3%22+filename%3ACargo.toml&type=code
67. Mathieu Leplatre, Leveraging Rust in Python and JavaScript, 2020-09-08. https://blog.mathieu-leplatre.info/leveraging-rust-in-python-and-javascript.html
68. Clark Verbrugge, Hex Grids, version 3 (hosted by Amit Patel). http://www-cs-students.stanford.edu/~amitp/Articles/HexLOS.html
69. zvold, Line of sight on a hexagonal grid, 2010-02-07. http://zvold.blogspot.com/2010/02/line-of-sight-on-hexagonal-grid.html
70. GameDev.net, Hex grid line-of-sight (HTTP 403 on fetch). https://gamedev.net/forums/topic/596721-hex-grid-line-of-sight/
71. BoardGameGeek, Hex-grid LOS math general solution (HTTP 403 on fetch). https://boardgamegeek.com/thread/403761/hex-grid-los-math-general-solution
72. FontTalk, Font Identification: game counter. https://www.fonttalk.com/t/font-identification-game-counter/4786
73. jzedwards/jzsquadleader README. https://github.com/jzedwards/jzsquadleader
74. Wikipedia, Counter (board wargames). https://en.wikipedia.org/wiki/Counter_(board_wargames)
75. countersheetsextension wiki, Counters and Markers Templates. https://github.com/lifelike/countersheetsextension/wiki/Counters-and-Markers-Templates

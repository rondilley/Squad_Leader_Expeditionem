# RV-2: Mapboards and scenarios of Squad Leader (Avalon Hill, 1977)

Date of research: 2026-09-07.
Scope: the base game only (boards 1 to 4, scenarios 1 to 12).

## How to read this document

Each fact has a source tag in square brackets. The References section at the end gives the URL for each tag.

Verbatim text from a card or from the rulebook is in a fenced text area. I did not change that text. Hex lists from the board scans are in inline code.

Two sources are primary:

- [SQLA-n] is scenario card n as scanned by the Squad Leader Academy (wargameacademy.org). Each card shows the Avalon Hill part number (8220003 on card 1). The Academy says that some of its PDF scans "contain errors in wording and with counters" and that the HTML version is current. For scenarios 1 to 12, only PDF scans are on the site. I read each card and transcribed it.
- [IA-MAP] is the archive.org item "Squad Leader by Avalon Hill Scans". These are 600 DPI scans of a 4th edition copy. I downloaded the eight map scans (two halves for each board) and examined them. Facts that come from what I saw on the scans have the tag (scan). A (scan) fact is not a quotation. Make sure of each hex number on a full resolution scan before you use it in code.

The rulebook quotations with the tag [RULES-4E] come from the local file G:\git\Squad_Leader_AI\background\Squad_Leader_4th_Edition_Rules.pdf. This file has no URL. I include it because it is the only source I found for the sewer entrance rule and for the rule for hex names (rule 3.5).

Limits of this research:

- BoardGameGeek pages give HTTP 403 to automated fetches. The BGG XML API gives HTTP 401 without a token. I could not read one BGG thread or file page. I record the BGG URLs that the search results showed, but I did not see their content.
- The `WebSearch` tool budget of this session ran out after I found the scenario cards. The last two queries (sewer hex list, board terrain lists) did not run.
- No source gives the hex dimension in inches. See item 1.

## 1. The four geomorphic mapboards

### 1.1 Physical dimensions

- "4 isomorphic mounted 22" x 8" maps" [TWG-SL].
- The ASL reprints of boards 1 to 4 are "8" x 22" cardstock mapboards" [DM-BV].
- The 4th edition scans are 6876 x 5070 pixels at 600 DPI for each half board. That is 11.46 in x 8.45 in for each half, with the board border included. Two halves make one board of approximately 22 in x 8.45 in [IA-MAP] (scan). The two halves overlap. The overlap dimension is unknown.
- A BGG result snippet says the playing area is "22" x 28"" for four boards [BGG-SL]. I did not see the page.
- Rule 3.4 [RULES-4E]:

The source text is entry Q-00 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

### 1.2 Hex grid

Sources disagree on the number of hex columns:

- "Each mapboard measured 10 columns of hexes high by 32 hexes wide, numbered from hex A1 in the top left corner to hex GG10 in the lower right" [TWG-SL]. Wikipedia has the same sentence [WIKI-SL].
- "Standard-sized VASL geo maps are 1800 x 645 pixels in size, 33 x 10 hexes" [TEXAS-VASL]. The letters A to Z plus AA to GG give 33 columns. So 33 agrees with the letter range. The "32" count possibly counts the two half-hex columns A and GG as one column. I did not find a source that says this.

Geometry from [TEXAS-VASL]. This document describes the VASL board, which is a copy of the paper board:

- Column letters A to GG go along the long edge. Row numbers 1 to 10 go down the short edge. Hex A1 is at the top left. Hex GG10 is at the bottom right. The board number is in hex B8 (VASL). On the paper board the yellow numeral is near B9 (scan).
- Half hexes are on all four edges. Half hexes along the top edge are `F0, H0, J0, L0, V0, X0, Z0, BB0` (the even columns). Half hexes along the bottom edge are `F10, H10, J10, L10, V10, X10, Z10, BB10`. Half hexes on the left side are the A column (the document names A4, A7). Half hexes on the right side are the GG column (GG4, GG7).
- Geomorphic connections that all boards have. Woods half hexes at the positions above. Roads that enter the board at `I1, Q1, Y1, I10, Q10, Y10, A5/A6, GG5/GG6`. The document says the last two "are along the hexside".
- Rule 3.5 [RULES-4E]:

The source text is entry Q-01 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Rule 3.7 [RULES-4E]:

The source text is entry Q-02 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Rule 3.3 [RULES-4E]:

The source text is entry Q-03 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Scale: each hex is 40 m [TWG-SL] [WIKI-SL].

Hex dimension in inches: not found. A derived value, not from a source: 22 in / 33 columns = 0.67 in between column centers. VASL has 1800 px / 33 = 54.5 px between column centers.

### 1.3 Coordinate examples from the sources

- 1AA5 is the sewer entrance hex example in rule 27.1 [RULES-4E].
- 2BB5 has the hill symbol ∆538 in rule 3.5 [RULES-4E]. The scan shows ∆538 in hex BB6 of board 2, one row lower (scan). Thus the 4th edition scan and the 4th edition rules disagree by one row, or my row count is off by one.
- Rule text on 3I10 [RULES-4E]:

The source text is entry Q-04 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Rule 3.6 [RULES-4E]:

The source text is entry Q-05 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Rule 3.8 [RULES-4E]: hex 2I9 costs infantry 4 MF and gives +3 to fire.
- Board 1 road hexes Y10, GG5-GG6, and I1 are the entry hexes for armor in scenario 3 [SQLA-3].
- Board 4 hexes Y1, Y10, Q1, Q10 are road entry hexes in scenario 12 [SQLA-12].

### 1.4 Terrain of each board

Summary from the sources: board 1 is urban, board 2 is hills, board 3 is a village, board 4 is rural [WIKI-SL]. Rule 3.1 names board 1 "the city board 1" [RULES-4E].

Part numbers on the 4th edition boards (scan): board 1 = 8220041, board 2 = 8220043, board 3 = 8220045, board 4 = 8220047. Board 4 also shows `Copyright 1977 The Avalon Hill Game Co., Baltimore, Md. 21214, Printed in U.S.A.` and the SQUAD LEADER title [IA-MAP].

The descriptions below are (scan) facts from [IA-MAP]. Building types: "stone" is a grey or brown-grey building. "Wooden" is a building with an orange-red roof. Hill levels: the scan shows a maximum of three shades of brown.

#### Board 1 (city)

- Roads: a paved road grid. A north-south road goes the full height of the board at column I (enters at I1, exits at I10). A second north-south road goes at column Y (Y1 to Y10). Dirt roads enter from the west at A5/A6 and exit east at GG5/GG6. Paved roads connect the blocks between columns C and DD.
- Woods: `A1-C4 (west edge), A6-C8, H2-H3, C6, G9-H10, I8-J9, X9-X10, BB2, CC5, DD2-EE3, EE4-GG4, FF7-GG8, DD8-DD9`.
- Large stone buildings:
  - `F3-G4` (L shaped). `F5-G6-H5` (long).
  - `J4-K4-J5-K5` (the largest block west of the I road, white squares at K4 and J6).
  - `M5-N4-N5` (white square at M5). `L6-L7-M7-L8` (T shaped, white square near L6).
  - `P3-Q3-Q4`. `P7-P8` (long). `R1-S1-S2` (long).
  - `T2-U2-U3-V2` (cross shaped, white square at U3).
  - `X3-X4-Y3-Y4-W4-W5-X5-Y5-X6` (the Tractor Works, the largest building on the board, white squares near X3, W5, and X6).
  - `AA4-AA5-BB4-BB5` (white square near BB4). `Y7-Z7-AA7-Y8-Z8` (white squares near AA7 and Y8).
  - `CC8-DD7-DD8`. `S5-T5` (long). `U8-T8` (long). `DD3`. `R7`.
- Small stone buildings: `J2, M2, O2, N3, M9, I7, FF6, O8, T4`.
- Wooden buildings: `F1-G1, D2, D4, C7, D8, F8, H4, H7, K2, K7-K8, M4, O5, P5, W1, V4, V5, S4, T6, S7, V7, X7, R9, W9, AA2, AA9-BB9, T7`.
- Sewer entrances. The PDF text of rule 27.1 says a sewer entrance hex is marked with a circle. Rule 3.3 says the hex center mark is a white dot or a white square. On the scan, some building hexes show a white square in the position of the dot.
  - I saw white squares at or near `G4, F6/G7, K4, J6, M5, L6/L7, U3, X3, W5, X6, BB4, AA7, Y8`. The rulebook example 1AA5 is in the AA4-BB5 building, where I saw the square at BB4. Make sure of each hex on a full resolution scan.
- Scenario 2 names building 1X3 as the Tractor Works [SQLA-2]. Scenario 1 names stone buildings `F5, K5, I7, M7, M9` (German) and `N4, J2, M2, N2, F3` (Russian) [SQLA-1]. Scenario 2 names buildings `U3, T4, R7, T7, Y8, CC7, AA4, CC3, P8, P5, Q4, R1` [SQLA-2].

#### Board 2 (hills)

- Hill 621: one large hill mass in the center-east of the west half.
  - Level 1 covers approximately `G3 to P9`. Level 2 covers approximately `I4 to O7`.
  - Level 3 (the darkest shade) is a crest line of hexes around `J4, K5, L5, M5, N5, O5, O6`. The ∆621 label is at O5. Scenario 5 says the crest line has 7 level 3 hexes [SQLA-5].
- Hill 538: a second hill mass on the east half. Level 1 covers approximately `W2 to DD8`. Level 2 covers approximately `Y4 to CC7`. The ∆538 label is at BB6 (scan) or 2BB5 (rule 3.5).
- Smaller hills: a level 2 knob at `R3` with level 1 around `R3-R5-S6-T7`. Level 1 areas at `F7-G8, T4-U4, R6-S7-T7, W5-W6, DD2-EE2`.
- Woods: `B1-C3, A3-B4-D4, F2, I3, K3-L3-M3-N3-N4, J6-J7, H7-I8, K8-L8, L9-L10, P6-P7, D7-E8-C9, S1, S3, U5-V5, W2-W4, X3-X4, Z5-AA5, DD2-EE3, EE4-GG4, GG7-GG8, EE8-FF8, T8-T10, Z9-AA10`.
- Buildings: wooden at `C2, G1, L1-M1, F3, D4-D5, I9, M9, T1, AA2, W7-X7, T8, V8, W9`. A stone wall is on the hexsides around `E5-E6`. Stone walls are at `H1-I1` (on the I1 road) and around `U8-V8`.
- Roads: dirt roads. One goes east-west across the north (row 2) from A2 to the east edge. One enters at A5/A6 and goes east through `B5-D5-F5-G6` and on to the center. Roads are at I1 and Y1 at the top, Y10 and I10 at the bottom, and GG5/GG6 at the east edge.
- Orchard: `U7-V7-V8` (trees in rows, with the shade of a level 1 hill).
- Grain (light yellow): `D1-E1` at the north edge. `EE1-FF1` on the east half.

#### Board 3 (village)

- Hills:
  - Hill 547 in the northwest: level 1 approximately `C1 to H5`, level 2 at `D3-E3-E4-F3-G3-H3`, label ∆547 at E3.
  - Hill 534 in the south center: level 1 approximately `G6 to K10`, level 2 at `H7-I7-I8-J7`, label ∆534 at I7.
  - Hill 522 in the east half: level 1 approximately `V4 to X8`, level 2 at `W5-W6-W7`, label ∆522 at W6.
  - Hill 498 in the northeast: level 1 approximately `BB1 to EE4`, level 2 at `DD2-DD3`, label ∆498 at DD2.
- The village. Stone buildings at `M2-N2` (large), `L4-M5` (long), `O5`, `S3-R3` (large, church shape), `T4`, `R6` (long). Wooden buildings at `I1, K1, M1, P2, P4, M7, P6, O10, I10, S1, T1, U1, V1, T3, V3, X3, S5, T6-U6, Z1, Y6, Y8, CC5, T8`. Stone walls around `K3-L3, M4-N4, O3-O4, P2-P3, O6-O8, N7-P8, T3-T4-U4-U5, X2-Y3`. Hedges (green lines) at `M6-M8` and `N8`.
- Orchard: a row of trees along a dirt road at `G6-G7-H5-I5-J4`. Shell holes at `X2-Y3`.
- Grain fields: `K2-L2, K9-K10, U2, R4-S4, Z4-Z5-AA5-BB4, T9-U9, FF8-FF9-GG9`.
- Woods: `B1-C2, A4-B4-C4, A7-B7-C7-D8-C9, F5, J4, I2-J2-J3, L1-M1, O1-P1, L9-M9-M10, N9, O9, P5-P6, R1, S2, W1-X1, R8-S9, T7-T8, U7-U8, W9-X10, AA3-BB3, BB5, AA7-BB8, DD7-EE9, FF3-GG3, GG5, GG7-GG8`.
- Roads: dirt roads from A5/A6 east through the center to the village and on to GG5/GG6. Roads at I1, Y1, I10, Y10.

#### Board 4 (rural, open)

- Open ground for the most part, with a small number of features.
- Grain fields (light yellow): `C1-C2`. A large field at `J5-K5-J6-K6-I7-J7-K7-I8-J8-K8`. `G8-G9, D10-E10, O2-O3-P2, N8-O9-M9, S1, X2`. A large field at `V4-W4-V5-W5-X5-V6-W6-X6-V7-W7-X7-W8`. `CC1-CC2-CC3, R5-R6, FF9-GG9`.
- Woods: `G1-H1-H2-G3-H3, D1-D2, E5-F4, H5-I5-H6-I6-J4, B7-A8, D9, M1-N1-M2-N2, K10-L9-L10, O3, N5-O5, M8, T1-U1, W1-X1, R1, V2-V3, T9-T10, U8, Z1-AA1-BB1, Z4-AA4-BB4, R7-R8, GG2, GG4, FF7-GG7, X10-Z10`.
- Buildings: a large wooden farm complex at `O6-P6` with small sheds at `O7-P7`. Wooden buildings at `P1, P8, I10, S2, R2, T3, CC6, Y9` (with a small shed at Y8). One stone building at `X1`.
- Walls and hedges:
  - Stone wall at `I1-J2`. Hedges around `N7-O8-P8`. A hedge at `Y1-Z2-AA2`.
  - A long hedge line from `Y8` through `Z8-AA8-BB7-CC7-DD6` to `EE7-FF8`. Hedge at `DD5-EE6`. Hedge at `Y10-Z10`.
- Shell holes at `S3`.
- Roads:
  - A dirt road from A6 east through `B5-D4-E4-F4-G4-H3-I2` to I1.
  - A road from Y1 south through `Y2-Y3`, then west through `X3-W2-V2-U2-T2` to the west edge near R2.
  - A road from GG5/GG6 west through `DD4-CC4-AA3-Z3` to Y3. A road from Y10 north through `Z9-Z8-AA8` to the east.
  - A road near `O7-P7-P8` to the farm. A road at I10.

### 1.5 Sources with no board data

The Wikipedia article on geomorphic mapboards has no dimensions [WIKI-GEO]. The ASL Wikipedia article gives dimensions only for Deluxe ASL boards (11 in x 26 in, 2.2 in hexes) [WIKI-ASL]. The asl-players geomorphic board gallery gives thumbnails and says boards 1 to 4 come from Beyond Valor [ASLP-GEO].

## 2. Board images online and license

### 2.1 archive.org

- Item: "Squad Leader by Avalon Hill Scans". Uploader RameyNoodles (Sean Ramey). Published 2024-08-11. Collection "opensource_image" [IA-MAP].
- Description: "600DPI Scans of components from the game "Squad Leader" by Avalon Hill. 4th Edition." [IA-MAP].
- Files: `Map1-A.png, Map1-B.png, Map2-A.png, Map2-B.png, Map3-A.png, Map3-B.png, Map4-A.png, Map4-B.png` (42 MB to 59 MB each), `Scenario1.png, Scenario7.png`, and counter sheets (Allied and German infantry, vehicles and fortifications, front and back) [IA-MAP-META].
- License: the item metadata has no "licenseurl" field and no "rights" field [IA-MAP-META]. The boards show `Copyright 1977 The Avalon Hill Game Co.` (scan). Treat the scans as Avalon Hill (now Hasbro) art with copyright and with no stated permission.
- The second archive.org item from the search, "Avalon Hill's Squad Leader USA", gave HTTP 404 [IA-USA].

### 2.2 VASL boards bd1 to bd4

- VASL board files are zip archives with the .zip extension removed (bd1 is bd1.zip). Each has a .gif (or .png since VASL 6.5) map image and data files [VASL-WIKI-BOARDS]. This comes from the search snippet. The wiki page itself did not load.
- VASL 6.4.3 and subsequent versions download boards on demand through the board picker. The vasl.info boards page says it "is no longer being updated and will be removed entirely in early 2024" and that "there is no longer a need for players themselves to download boards" [VASL-BOARDS].
- Standard VASL geo board image: 1800 x 645 pixels, 33 x 10 hexes, 1 pixel black frame [TEXAS-VASL].
- Repositories. github.com/vasl-developers/vasl has the source code (LGPL) [GH-VASL]. github.com/aslplayer/vasl-boards-extensions has "map boards and extensions" from the VASL Map Bazaar. Its boards folder gave an empty result through the GitHub API, and the page has no license text [GH-ASLP]. github.com/davidsullivan317/VASL-boards is there (304 entries) but has no files with the names bd1 to bd4 at the root [GH-DS]. github.com/vasl-developers/vasl-boards gave HTTP 404 [GH-VB].
- License of the board art: not found. vasl.info has no copyright or license statement [VASL-HOME] [VASL-DL]. asl-players.net says: "ASL-Players.net is not affiliated with Hasbro, Avalon Hill Games, Inc., or Multi-Man Publishing in any way. Advanced Squad Leader is a trademark of Avalon Hill Games, Inc." [ASLP-BOARDS].

### 2.3 Do ASL boards 1 to 4 have the same geometry as the Squad Leader boards?

- ASL used the Squad Leader boards without change: "only the map boards of the earlier series were compatible with the new game" [WIKI-ASL]. Some ASL modules required "boards 1 to 4" from the first Squad Leader game [WIKI-ASL]. Beyond Valor 1st edition included boards 20 to 23 only. Some of its scenarios "assume the ownership of boards from the original Squad Leader and its gamettes (specifically, Boards 1 and 8)" [DM-BV].
- MMP subsequently reprinted boards 1 to 4 because it did not reprint Squad Leader: "MMP's decision not to reprint the original Squad Leader games resulted in reorganization and 2nd editions of many ASL core modules in order to include boards from the earlier games" [WIKI-ASL]. Beyond Valor 3rd edition contains "10 8" x 22" cardstock mapboards (1-5, 8, 20-23)" [DM-BV].
- The 3rd edition art is new: "The art on the new Beyond Valor maps is not the original ASL art, but has been redrawn with computer graphics" because "the original artwork no longer exists, so some sort of recreation was necessary" [DM-BV].
- Thus the hex geometry and the terrain layout of ASL boards 1 to 4 agree with the Squad Leader boards. The current MMP and VASL art is a new copy. I found no source that shows terrain differences between the 1977 print and the new boards. The Squad Leader Academy VSQL notes say that the Starter Kit style boards "report differently in regards to LOS" than the standard style boards [SQLA-INDEX].
- The BGG file "The Guards Counterattack Scenario and Map" (filepage 162477) possibly has a board 1 image. I did not see it (HTTP 403) [BGG-FILE-GCA].

## 3. The 12 scenarios of the base game

All twelve are Programmed Instruction scenarios. Each card shows "Rules Introduced: Sections x-y". The titles, dates, and locations agree in [WIKI-SLS], [AUSW], and [SQLA-INDEX]. Wikipedia spells the location of scenario 4 "Piersk". The card says "PIEPSK" [SQLA-4].

Counter notation below. A squad is firepower-range-morale (4-6-7). A leader is morale-modifier (9-1). Support weapons are LMG, MMG, HMG, and:

- `[3]` tube counter: a German infantry anti-tank rocket weapon with range 3. This is my interpretation of the counter picture. The card gives no name.
- `6 [4] X11+`: American bazooka.
- `20∆ -1 [2]`: flamethrower. `30 ∆ A`: demolition charge. `7 ∆ B12` and `9 ∆ B12`: radios (German and American).
- `?`: concealment counters.
- Vehicles are as printed: name, gun, movement number in the top right corner, and the gun rate (for example `STGIII 75 6/- 12`).
- Red numbers below a counter on the card give the count. A counter with no red number is one counter.

The squad totals below are sums of the printed counts. I use "force list" for the card's "Order of Battle" box.

### Scenario 1: The Guards Counterattack [SQLA-1]

- Card part number 8220003. Date and location: Stalingrad, October 6, 1942 [WIKI-SLS] [SQLA-1].
- Rules Introduced: Sections 1-21.
- Board: board 1 only, north at the top. Caption: the west half, columns A to P (the west half).
- Turn Record Chart: German sets up first. Russian moves first. 5 turns.
- Attacker: Russian.
- Victory Conditions:

The source text is entry Q-06 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- German force list, Co H, 389th Infantry:
  - In building F5: 9-1 (Sgt Kelso), 3 x 4-6-7, 2 x LMG.
  - In building K5: 8-0 (Cpl Pollack), 3 x 4-6-7, 2 x LMG.
  - In building I7: 9-2 (Cpt Wetzelberge), 3 x 4-6-7, 3 x LMG.
  - In building M7: 8-1 (Sgt Hamblen), 3 x 4-6-7, 1 x LMG, 1 x MMG.
  - In building M9: 8-1 (Sgt Hieken), 1 x 4-6-7, 1 x HMG.
  - Total 13 squads.
- Russian force list, Elements of the 308th Rifle Division:
  - In building N4: 8-0 (Com Cohenov), 4 x 4-4-7.
  - In building J2: 9-1 (Lt Dubovich), 1 x 4-4-7, 1 x MMG.
  - In building M2: 3 x 4-4-7.
  - In building N2: 1 x 4-4-7.
  - Elements of the 2nd Bn, 37th Guards, in building F3: 10-2 (Col Berki), 12 x 6-2-8.
  - Total 21 squads.
- Special Rules:

The source text is entry Q-07 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Variations: variation 1A, which the two players agree to use or not
- The ASL Scenario Archive agrees: 21 Russian squads against 13 German squads, 5 turns. It gives a balance record of 49.8 percent German wins from 219 games [ASA-GCA].

### Scenario 2: The Tractor Works [SQLA-2]

- The rulebook names it "The Dzerhezinsky Tractor Works" [RULES-4E]. Stalingrad, October 6, 1942.
- Rules Introduced: Sections 22-26.
- Board: board 1 only, north at the top. Caption: the east half, columns O to GG (the east half).
- Turn Record Chart: Sequential set up. a die roll decides the first mover. 8 turns.
- Attacker: German. The two sides attack. The Russian relief force enters from the outer buildings.
- Victory Conditions:

The source text is entry Q-08 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Russian force list:
  - Garrison of the 308th Rifle Division, sets up first in the Tractor Works, building X3: 9-2 (Maj Kirkov), 12 x 4-4-7, 3 x LMG, 2 x MMG, 1 x HMG, 18 x `?`.
  - Elements of two battalions of the 295th Infantry Division, deploys last in buildings P8, P5, Q4, and R1: 9-1 (Com Doltski), 8-0 (Lt Eastonov), 8-0 (Lt Burnski), 27 x 4-4-7, 4 x LMG.
  - Total 39 squads. A search snippet says 38 [MATRIX].
- German force list, Elements of the 389th Infantry Division, sets up after the Russian garrison:
  - Kampfgruppe Stahler, deploys in buildings U3, T4, R7, and T7: 9-2 (Lt Stahler), 8-1 (Sgt Pitz), 7 x 4-6-7, 2 x MMG, 4 x LMG, 12 x `?`.
  - Kampfgruppe Tienham, deploys in buildings Y8, CC7, and AA4: 10-2 (Cpt Tienham), 9-1 (Sgt Stites), 8-0 (Cpl Uhl), 6 x 4-6-7, 3 x LMG, 1 x HMG.
  - Co A, Assault Engineer Battalion 50, deploys in buildings AA4, CC3, and Y8: 10-3 (Obr Greup), 6 x 8-3-8, 2 x flamethrower, 4 x demolition charge, 2 x LMG, 6 x SMOKE. Card note: the smoke counters leave the game after one use
  - Total 19 squads.
- Special Rules:

The source text is entry Q-09 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Variations: variation 2A, which the two players agree to use or not

### Scenario 3: The Streets of Stalingrad [SQLA-3]

- Stalingrad, October 6, 1942. Card text:

The source text is entry Q-10 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Rules Introduced: Sections 27-41.
- Board: all of board 1, north at the top.
- Turn Record Chart: Sequential set up. a die roll decides the first mover. 7 turns. A red star is above turn 2 and a German symbol is above turn 3 (the armor entry turns).
- Victory Conditions:

The source text is entry Q-11 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Force list, from rule 3.1:

The source text is entry Q-12 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Armor Support, "Variant 3B only":
  - German, enters on turn 3 in the German Movement Phase, on road hex Y10 or on GG5 and GG6: 3 x STGIII (75, 6/-, 12), 2 x STGIII (105, 6/-, 12).
  - Russian, enters on turn 2 in the Russian Movement Phase, on road hex I1: 4 x T-34 (76, 4/-, 16).
- Special Rules:

The source text is entry Q-13 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Variations:

The source text is entry Q-14 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- The card does not divide scenario 3 into two scenarios 3A and 3B. The labels 3A and 3B are variations on one card. The fan report title "Squad Leader report: 3a" [MERRIC-3A] uses the variation label.

### Scenarios 4 to 12

The project builds scenarios 1, 2, and 3A in year one, and each of those has its own
data file in the project's own words. The detail of the other nine cards is card text,
so it is in `background/reference/rv2_scenarios_4_to_12.md`, which git does not record
(SR-07, DR-06). The table below holds the facts that the plan needs.

| Number | Name | Boards | Turns | Rules introduced |
|---|---|---|---|---|
| 4 | The Hedgehog of Piepsk | three boards | 10 | 42-46 |
| 5 | Hill 621 | three boards, north at the top | 10 | 47-48 |
| 6 | Escape From Velikiye Luki | four boards, north at the top | 10 | 49 |
| 7 | Buchholz Station | two boards, north at the top | 10 | 50-52 |
| 8 | The Bitche Salient | two boards | 10 | 53-54 |
| 9 | The Cannes Strongpoint | three boards, north at the top | 5 | 55-56 |
| 10 | Hitdorf on the Rhine | two boards | 9 | 57-59 |
| 11 | The St. Goar Assault | four boards end to end, north at the top | 7 | 60 |
| 12 | The Road to Wiltz | four boards end to end, north at the top | 12 |  |

### 3.1 Summary table

| No. | Title | Date | Place | Boards (west to east or north to south) | Attacker | Turns |
|---|---|---|---|---|---|---|
| 1 | The Guards Counterattack | 1942-10-06 | Stalingrad | 1 (west half, rows A-P) | Russian | 5 |
| 2 | The Tractor Works | 1942-10-06 | Stalingrad | 1 (east half, rows O-GG) | German (mutual) | 8 |
| 3 | The Streets of Stalingrad | 1942-10-06 | Stalingrad | 1 (all) | the two sides | 7 |
| 4 | The Hedgehog of Piepsk | 1941-11-14 | Piepsk | 4, 3, 2 (north to south, 3 upside down) | Russian | 10 |
| 5 | Hill 621 | 1944-07-01 | near Minsk | 2, 4, 3 (all upside down) | Russian | 10 |
| 6 | Escape From Velikiye Luki | 1943-01-12 | Velikiye Luki | 4, 2, 3, 1 (4 and 3 upside down) | German (night) | 10 |
| 7 | Buchholz Station | 1944-12-16 | Buchholz | 4 north, 3 south (upside down) | German | 10 |
| 8 | The Bitche Salient | 1945-01-14 | Bitche | 4 west, 2 east | American | 10 |
| 9 | The Cannes Strongpoint | 1944-08-23 | Cannes | 4, 2, 3 (4 and 2 upside down) | American | 5 |
| 10 | Hitdorf on the Rhine | 1945-04-06 | Hitdorf | 4 west, 3 east | American, then German | 9 |
| 11 | The St. Goar Assault | 1945-03-24 | St. Goar | 2, 1, 4, 3 end to end (4 upside down) | American | 7 |
| 12 | The Road to Wiltz | 1944-12-17 | Wiltz | 1, 3, 2, 4 end to end (4 upside down) | German | 12 |

Dates and locations: [WIKI-SLS] [AUSW]. Boards, attacker, and turns: [SQLA-1] to [SQLA-12]. For the unclear conditions, the attacker column agrees with the Classic ASL list in the ASL Scenario Archive [ASA-CLASSIC].

## 4. Scenario card format

- A previous Wikipedia revision says [ENAC-SLS]:

```text
Each scenario of the original four game releases was printed on an 8-1/2" x 11" cardstock with the following elements in place: Scenario number, Illustrative graphic, Historical overview, Board configuration and orientation, Listing of rules sections introduced, Victory Conditions, Turn Record Chart, Countermix and historical identity of scenario forces, Scenario Special Rules, Variations, Historical Aftermath
```

- The current Wikipedia text is shorter [WIKI-SLS]:

```text
Each scenario in the original four-game releases was printed on an 8-1/2" × 11" cardstock with the scenario number, an illustrative graphic, and a historical overview of the aftermath
```

- A blog review gives the same fields: "Title, Scenario Number, Rules Introduced Section, Historical Vignette, Victory Conditions, Board Configuration, Turn Record Chart, Order of Battle for each force, Special Rules, Variations". It says the card is "a double-sided stock card that is 8-1/2" x 11" inches" [MF6S].
- The scanned cards agree with this layout [SQLA-1] to [SQLA-12]. Scenario number and title are at the top. A black and white picture is at the top left. The historical narrative is at the top right, with the location and date in bold (for example "STALINGRAD, October 6, 1942:"). Then come "Rules Introduced", "Victory Conditions", "Board Configuration" with a north arrow, and "Turn Record Chart".
- Then come the two force list boxes. The German box has a black cross symbol. The Russian box has a red star. The American box has an outlined star. Then come "Special Rules", "Variations", and "Aftermath". Each card has an Avalon Hill part number (8220003 on card 1) [SQLA-1].
- Each force list box shows the historical unit in bold, the set up instruction, then counter pictures with red count numbers below them. Leaders have names (Sgt Kelso, Cpt Wetzelberge, Com Cohenov, Cpt Shaw, and so on). The same names occur again in other scenarios [SQLA-1] [SQLA-4] [SQLA-8].
- "Each scenario card includes historical information, victory conditions and play balancers for each side" [WIKI-SL].
- The 4th edition scans on archive.org include `Scenario1.png` and `Scenario7.png` [IA-MAP-META].

## 5. Additional official scenarios in The General

The General published Squad Leader scenarios with letter and number designations. The table is from Wikipedia [WIKI-SLS]. The Squad Leader Academy index gives the same issues 15.6, 17.2, 19.5, 19.6, 20.2, 20.4, 20.6, 21.2, 21.3, 21.4 for its TAHGC scenario files [SQLA-INDEX].

| Issue | ID | Title | Date | Place |
|---|---|---|---|---|
| 15-6 | A | Burzevo | 1941-12-02 | Burzevo, USSR |
| 15-6 | B | Hill 253.5 | 1943-07-09 | North of Kursk |
| 15-6 | C | The Burkin Bridgehead | 1943-09-24 | SE of Kiev |
| 15-6 | D | Delaying Action | 1944-10-30 | Western Lithuania |
| 17-2 | E | The Niscemi-Biscari Highway | 1943-07-10 | Biscari, Sicily |
| 17-2 | F | The Pouppeville Exit | 1944-06-06 | Normandy |
| 17-2 | G | Devil's Hill | 1944-09-19 | Kleve-Nijmegen |
| 17-2 | H | The Attempt to Relieve Peiper | 1944-12-21 | the Ardennes |
| 17-2 | I | Hunters from the Sky | 1945-03-24 | Rhine river |
| 18-2 | J | Semper Paratus | 1944-09-27 | Oorderen, Holland |
| 18-3 | K | Fast Heinz | 1944-08-07 | Roslavl, USSR |
| 18-4 | L | The Long Road | 1942-09-16 | Madagascar |
| 18-5 | M | The Dead of Winter | 1941-12-29 | NW of Staritsa |
| 19-5 | TS1 | First Crisis at Army Group North | 1941-06-25 | Daugava river |
| 19-5 | TS2 | Pavlov's House | 1942-10-20 | Stalingrad |
| 19-5 | TS3 | Land Leviathans | 1941-07-03 | Lipki, USSR |
| 19-5 | TS4 | Soldiers of Destruction | 1944-10-10 | Radzymin, Poland |
| 19-6 | N | Faugh A'Ballagh! | 1944-05-16 | Sinagoga, Italy |
| 20-2 | 1000 | Operation Marston | 1943-07-14 | Catania, Sicily |
| 20-4 | O | Strayer's Strays | 1944-06-06 | Normandy |
| 20-6 | SSTK 1a, 1b | Death's Head at Lusho | 1941-09-24 | Lusho, USSR |
| 21-2 | P | Aachen's Pall | 1944-10-25 | Aachen |
| 21-3 | Q | Gambit | 1941-05-21 | Maleme, Crete |
| 21-4 | 2000 | Operation Hubertus | 1942-11-11 | Stalingrad |
| 22-5 | 3000 | Assault on Round Top | 1944-09-30 | north of Riga |

Notes:

- The SQLA index marks scenarios A to D with "GENERAL 15.6" and one custom board 4. It marks E to I with "GENERAL 17.2" and one custom board 2 [SQLA-INDEX]. I did not find which of these are for the base game only and which are for Cross of Iron.
- The Wikipedia table also shows subsequent ASL conversions of these scenarios in issues 22-6 to 32-3 [TWG-SLS]. The vftt.co.uk magazine index shows the ASL versions and the Robert Medrow "first impressions" articles (Vol 14 No 5, 15-6, 17-2, 20-1). It shows no Squad Leader scenario entries [VFTT].
- The Squad Leader Academy has SQL versions of scenarios H and P [SQLA-INDEX]. A BGG result snippet says scenarios G1 to G46 in The General were ASL scenarios [BGG-ADD]. I did not see the page.
- The series 100 to 300 scenarios (Cross of Iron, Crescendo of Doom, GI: Anvil of Victory) and the rogue scenarios R211 to R220 do not belong to the base game [WIKI-SL].

## 6. Turn Record Chart and Board Configuration conventions

From the cards [SQLA-1] to [SQLA-12] and the rulebook [RULES-4E]:

- Rules 21.1 to 21.3 [RULES-4E]:

The source text is entry Q-49 of `background/reference/rv2_source_quotes.md`, which git does not record (SR-07).

- Board Configuration diagram: a rectangle for each board, in proportion. The number of each board is in the corner that agrees with the numeral on the paper board (the yellow numeral near B9). An upside down numeral shows that the board has a 180 degree turn.
- A north arrow adjacent to the diagram gives the compass direction. The arrow points up, left, or right as necessary for the scenario. When part of one board is in play, the diagram shades the playable part in red, and a caption names the column range of that part.
- The cards give the diagram only. They do not name the edges that touch. The boards touch along their long edges (scenarios 4 to 10) or along their short edges (scenarios 11 and 12).
- The numbered edge is the edge that has the board number. Variations 7A, 9B, and 10B turn each board by a die roll: an even roll puts its numbered edge to the north. Variation 4D puts the numbered edge to the west.
- Rule 3.5 gives the tie break for the half hexes at a joint. The hex takes its board number and its row letter from the board that is furthest to the north and the east in the configuration [RULES-4E].
- The set up areas on the cards take four shapes, and the scenario data of this project has to say the same four things. Edge names are compass names for the whole playing area.
  - A whole board, or a whole hex of one named board.
  - A distance from one edge, or a distance from one named hex.
  - An entry along one edge, sometimes on a road hex, sometimes with each unit on the same road.
  - A choice between two edges of one board, where the side takes one of them and not both.
- Turn Record Chart: a two row header on the left gives who sets up first and who moves first. The numbered boxes 1 to n come first and an END box comes last. Header examples:
  - the German side sets up first, and the Russian side moves first.
  - sequential set up, and a die roll for the first mover.
  - simultaneous set up, and the German side moves first.
  - the Russian side sets up first, and the German side moves first.
- Small symbols above a turn number (red star for Russian, black cross symbol for German, outlined star for American) show the turn on which a reinforcement group enters. Turn counts in the base game: 5, 8, 7, 10, 10, 10, 10, 10, 5, 9, 7, 12.
- Rule 4 [RULES-4E] says the attacker is the player who moves first in the turn. Each game turn is two player turns of 8 phases. One game turn is equal to 2 minutes.

## References

- [SQLA-INDEX] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/index.html (The Avalon Hill Game Company scenarios index, revised 160919)
- [SQLA-1] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-001-The%20Gaurds%20Counterattack.pdf
- [SQLA-2] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-002-The%20Tractor%20Works.pdf
- [SQLA-3] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-003-The%20Streets-Of-Stalingrad.pdf
- [SQLA-4] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-004-The%20Hedgehog%20Of%20Piepsk.pdf
- [SQLA-5] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-005-Hill%20621.pdf
- [SQLA-6] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-006-Escape%20From%20VelikiyeLuki.pdf
- [SQLA-7] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-007-Buchholz%20Station.pdf
- [SQLA-8] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-008-The%20Bitche%20Salient.pdf
- [SQLA-9] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-009-The%20Cannes%20Strongpoint.pdf
- [SQLA-10] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-010-Hitdorf%20On%20The%20Rhine.pdf
- [SQLA-11] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-011-The%20St%20Goar%20Assault.pdf
- [SQLA-12] http://www.wargameacademy.org/sqla/scenarios/ScenariosTAHGC/TAHGC-012-The%20Road%20To%20Wilttz.pdf
- [SQLA-TOP] http://www.wargameacademy.org/SQLA/Scenarios/ (Squad Leader Scenario Resources, "over 430 Scenarios")
- [IA-MAP] https://archive.org/details/allied-infantry-back
- [IA-MAP-META] https://archive.org/metadata/allied-infantry-back
- [IA-USA] https://archive.org/details/Avalon_Hills_Squad_Leader_USA (HTTP 404)
- [RULES-4E] G:\git\Squad_Leader_AI\background\Squad_Leader_4th_Edition_Rules.pdf (local file, no URL)
- [TWG-SL] https://www.tacticalwargamer.com/boardgames/squadleader/squadleader.htm
- [TWG-SLS] https://tacticalwargamer.com/boardgames/squadleader/squadleaderscenarios.htm
- [WIKI-SL] https://en.wikipedia.org/wiki/Squad_Leader
- [WIKI-SLS] https://en.wikipedia.org/wiki/Squad_Leader_Scenarios and the raw text at https://en.wikipedia.org/w/index.php?title=Squad_Leader_Scenarios&action=raw
- [WIKI-ASL] https://en.wikipedia.org/wiki/Advanced_Squad_Leader
- [WIKI-GEO] https://en.wikipedia.org/wiki/Geomorphic_mapboard
- [ENAC-SLS] https://en-academic.com/dic.nsf/enwiki/1454649 (mirror of an old Wikipedia revision)
- [AUSW] https://australianwargamer.wordpress.com/paperback-wargames/world-war-2/advanced-squad-leader/original-squad-leader-scenari/
- [TEXAS-VASL] https://texas-asl.com/download/Ye%20Old%20VASL%20Boards%20v6.pdf ("Ye Old Booke of VASL Mapmaking Secrets", section 2.2.1 Geo Board Details)
- [VASL-BOARDS] https://vasl.info/boards.htm
- [VASL-DL] https://vasl.info/download.htm
- [VASL-HOME] https://vasl.info/
- [VASL-WIKI-BOARDS] https://github.com/vasl-developers/vasl/wiki/Creating,-adding-LOS-data-to,-and-Updating-Boards-in-the-Age-of-Automatic-Board-Synchronization (content from the search snippet only)
- [GH-VASL] https://github.com/vasl-developers/vasl
- [GH-VB] https://github.com/vasl-developers/vasl-boards (HTTP 404)
- [GH-ASLP] https://github.com/aslplayer/vasl-boards-extensions
- [GH-DS] https://github.com/davidsullivan317/VASL-boards
- [ASLP-GEO] https://asl-players.net/mmp-geo-boards/
- [ASLP-BOARDS] https://asl-players.net/advanced-squad-leader-files-boards/
- [DM-BV] https://www.desperationmorale.com/products/beyond-valor/
- [DM-CLASSIC] https://www.desperationmorale.com/products/asl-classic/
- [ASA-GCA] https://www.aslscenarioarchive.com/scenario.php?id=56508
- [ASA-CLASSIC] https://www.aslscenarioarchive.com/viewPub.php?id=749
- [ASLNET-H621] https://advancedsquadleader.net/index.php?title=Hill_621
- [GG-H621] https://groups.google.com/g/squad-leader-aars/c/QM1lNaTaBxo
- [SCRIBD-11] https://www.scribd.com/document/498513259/Avalon-Hill-Squad-Leader-Scenario-11
- [MF6S] https://www.mf6s.com/2022/06/13/bga-squad-leader/
- [VFTT] https://www.vftt.co.uk/ah_mags.asp?ProdID=index
- [MATRIX] https://forums.matrixgames.com/viewtopic.php?t=254614 (search snippet only)
- [MERRIC-3A] https://merricb.com/2014/01/30/squad-leader-report-3a-the-streets-of-stalingrad/ (now goes to an unrelated site, not read)
- [BGG-SL] https://boardgamegeek.com/boardgame/1035/squad-leader (HTTP 403, search snippet only)
- [BGG-S4] https://boardgamegeek.com/thread/1118061/scenario-4-hedgehog-piepsk (HTTP 403, search snippet only)
- [BGG-ADD] https://boardgamegeek.com/thread/861156/additional-scenarios (HTTP 403, search snippet only)
- [BGG-FILE-GCA] https://boardgamegeek.com/filepage/162477/the-guards-counterattack-scenario-and-map (HTTP 403, not read)
- [BGG-MAPS] https://boardgamegeek.com/thread/225408/squad-leader-series-map-boards and https://boardgamegeek.com/thread/1209316/map-pdf (HTTP 403, not read)

# RV-8: Community and social signal for Squad Leader (1977) and digital hex wargames

Date of research: 2026-09-07

Scope: the 1977 Avalon Hill Squad Leader (SL) and its gamettes (COI, COD, GIA), not ASL, plus digital and AI-driven hex wargames. In this document, "SL" means the 1977 game.

Format note: text in backticks is a verbatim quotation from the source. It is not in Simplified Technical English.

## Method and limits

- Each claim below has a URL that I fetched. If I could not fetch a page, I say so.
- The WebSearch budget for this session ran out after 20 queries. All subsequent work used page fetches.
- Blocked sources, part 1: reddit.com, old.reddit.com and Reddit mirrors (blocked by the tool). Also web.archive.org (blocked by the tool). Also boardgamegeek.com HTML pages (HTTP 403).
- Blocked sources, part 2: wargameacademy.org (connection closed on 5 fetches). Also Steam Workshop (HTTP 429 on 5 fetches). Also DuckDuckGo and Bing (CAPTCHA or no applicable result).
- Workaround for BGG: the public JSON endpoints at api.geekdo.com gave game statistics, forum lists, thread lists, thread bodies, files and videos.
- Workaround for the VASSAL wiki: a text proxy (r.jina.ai) rendered the module page.
- Reddit is a gap. I could not read one Reddit thread. Do not make the conclusion that there are no SL posts on Reddit.

## 1. Where the SL community lives today

### BoardGameGeek (the primary hub)

Game statistics for BGG item 1035 (fetched 2026-09-07):
- 3,565 ratings, average 7.56, weight 4.03 of 5, 7,028 copies marked as owned, 1,395 comments, 4,743 logged plays, 387 fans, overall rank 1,037, wargame rank 74.
- Source: https://api.geekdo.com/api/dynamicinfo?objectid=1035&objecttype=thing

Forum totals (all time):
- General: 291 threads, 1,939 posts. Rules: 402 threads, 2,499 posts. Sessions: 53 threads, 294 posts.
- Reviews: 12 threads, 109 posts. Strategy: 10 threads, 56 posts. Variants: 18 threads, 140 posts.
- News: 42 threads, 129 posts. Find Players: 31 threads, 55 posts. Play By Forum: 4 threads, 32 posts.
- Source: https://api.geekdo.com/api/forums?objectid=1035&objecttype=thing

Recent posts:
- General forum: the ten most recent threads run from 2025-12-14 to 2026-07-17. The last post is 2026-08-15. That is one to two new threads for each month.
- Source: https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=1&sort=recent
- Rules forum: the ten most recent threads run from 2026-02-01 to 2026-08-16. The last post is 2026-08-20. Topics are MG penetration and rule 8.5, captured MGs, smoke and to-hit, gun shields, and concealment.
- Source: https://api.geekdo.com/api/forums/threads?forumid=66&objectid=1035&objecttype=thing&pageid=1&sort=recent
- Sessions forum: five session reports from 2024-10 to 2025-10. Most are solo reports.
- Source: https://api.geekdo.com/api/forums/threads?forumid=64&objectid=1035&objecttype=thing&pageid=1&sort=recent
- Find Players forum: ladder reports and tournament announcements by user scott_67 from 2021 to 2026. The post "The Ladder is working again" has the date 2026-02-27.
- Source: https://api.geekdo.com/api/forums/threads?forumid=274&objectid=1035&objecttype=thing&pageid=1&sort=recent
- News forum: "2025 Squad Leader Academy Tournament - Register now!" (2025-11-11), VSQL 4.3.6 release (2023-08-03), tournament results 2023 and 2024.
- Source: https://api.geekdo.com/api/forums/threads?forumid=68&objectid=1035&objecttype=thing&pageid=1&sort=recent

Key threads:
- "Anyone still playing the original Squad Leader?" Posted 2020-12-07, 35 posts. Posters say they play solo through the gamettes. One says SL is `the best` of a large WW2 tactical collection. One poster reports more than 40 years of play.
- The same thread on ASL: `No thanks, one giant tackle box full of boards and counters is quite enough` and `I find ASL now to be a bit too much`. No poster refers to VASSAL, computer versions or AI.
- Metadata: https://api.geekdo.com/api/threads/2555617
- Posts: https://api.geekdo.com/api/articles?threadid=2555617
- "Still 'The Daddy'." Posted 2025-12-01. The poster says SL `still stands up` because of sturdy components, flexibility, `staggered learning`, solo play, and good scenarios. A reply says SL `still sees play each year in spite of all the new games.`
- Source: https://api.geekdo.com/api/articles?threadid=3620935
- "Just bought 4th Edition for first time, what should I expect?" Posted 2026-07-15, 13 posts. Veterans point to programmed instruction, the Tactical Training Series by Alan Yngve, the "Retro" solitaire rule set, and the Quick Reference Data Chart.
- Source: https://api.geekdo.com/api/articles?threadid=3738095
- "Classic Squad Leader and COI PBEM/Server Tournament Opportunities" (2026-01-27). The SQLA 2025 tournament, part 1, has `six games in progress with 2 more with pending start`. The BPA 2026 Cross of Iron tournament starts 2026-03-15 with five parts.
- Source: https://api.geekdo.com/api/articles?threadid=3652135

### Squad Leader Academy (SQLA) and the ladder

- The SQLA site (wargameacademy.org) closed the connection on each fetch. I could not read it.
- The SQLA ladder site on Google Sites is readable. It hosts SL, COI, COD and GIA ladder and tournament games. The ladder table shown is from July 2024 (top records 22-9-0, 15-4-0, 10-1-0). The Guards Tournament, a "Campagne de France, 1940" tournament and the SQLA Tournament are open. The site points to a Discord server for voice during VASSAL games.
- Source: https://sites.google.com/site/2012squadleadertourny/home
- The VSQL module page on that site shows VSQL 4.3.8 on VASSAL 3.7+ and COD/GIA extension 9.5. It says `VSQL 4.3.8 is not compatible with prior versions, although one can install both.` It describes a Line of Sight tab with a "Check all" function and configurable hindrance and blocked colours.
- Source: https://sites.google.com/site/2012squadleadertourny/vsql-module

### VASSAL VSQL player base

- Module page: VSQL 4.3.8, updated about two years before the fetch, made 16 years before, maintainers "Scott and wga". It `provides the complete game-set for SQUAD LEADER and CROSS OF IRON`. Extensions: COD/GIA, COI-SS, Italians and Japanese sets, DYO.
- Board set v5SK is current. `Board v5SK LOS may not function properly on Apple OS`.
- Source: https://r.jina.ai/https://vassalengine.org/wiki/Module:Squad_Leader
- Release notes for 4.3.8 (2024-04-07): a crash correction in the graveyard, scenario start counters moved to the Control tab, COD/GIA 9.5, COI-SS 2.2.
- Source: https://api.geekdo.com/api/articles?threadid=3279700
- Release notes for 4.3.6 (2023-08-04): counter corrections, a Gun Flashes counter for night rules, squad deployment and ELR corrections for COD/GIA. The post tells users to report errors `except line-of-sight issues`.
- Source: https://api.geekdo.com/api/articles?threadid=3129657
- A 2023 PBEM thread: `The VASSAL module actually calculates LOS for me (for the most part) which is really cool.` A maintainer notes that terrain pixels sometimes do not continue into the adjacent hex. Manual judgement is then necessary.
- Source: https://api.geekdo.com/api/articles?threadid=3056316
- Estimate: the active competitive base is small. Six to eight games are in progress in the 2025 SQLA tournament. The ladder shows three named leaders with 10 to 31 games each.

### ConsimWorld

- You must log in to read the forum. The public page claims `20,000+ individually registered` members. It shows a folder for "Advanced Squad Leader series (MMP)" plus WWII folders by front. No folder for SL is shown without login.
- Source: https://talk.consimworld.com/

### Discord

- "Advanced Squad Leader | Central": 3,065 members, 402 online at fetch time. It is for ASL. The page does not refer to SL areas.
- Source: https://discord.com/servers/advanced-squad-leader-central-415876852419395586
- The SQLA ladder site refers to a Discord server for VASSAL voice play (see above).

### Facebook

- "Counterus Hex" is a public group with 718 members. A member post says the member will refresh SL knowledge before "Huzzah Con".
- Sources: https://www.facebook.com/groups/103649983443889/ and https://www.facebook.com/groups/103649983443889/posts/249078145567738/
- "The Tabletop Strategist" page posted "Old school: Squad Leader, Avalon Hill, 1977" on April 2 (year not shown): 15 reactions, 2 comments, 1 share.
- Source: https://www.facebook.com/tabletopstrategist/posts/old-school-squad-leader-avalon-hill-1977-the-game-that-introduced-a-generation-t/122186807288769211/

### Reddit (r/hexandcounter, r/wargames, r/ASL)

- Not readable with the available tools. Gap.

### Matrix Games forum (historical interest signal)

- A 2006 thread requested a faithful computer ASL from Matrix. Posters said Paradox held the electronic rights. They said Combat Mission and Close Combat started as ASL ports and `came to the same conclusions. Can't be done`. Peter Fisla was then at work on an unofficial XASL with rules automation and AI. One poster said `no interest` in a port that copies the board game.
- Source: https://forums.matrixgames.com/viewtopic.php?t=103257

## 2. What players say they want from a digital Squad Leader

### The 2000 Hasbro PC game and the unsuccessful lineage

- Wikipedia: two earlier projects did not succeed. "Beyond Squad Leader" with Atomic Games became Close Combat (1996). "Computer Squad Leader" by Big Time Software was cancelled in July 1998 and became Combat Mission. Random Games used the Chaos Gate engine again. The team wanted an `accessible` tactical game, not a literal board game conversion.
- Scores for the 2000 game: Metacritic 46/100. PC Gamer: `Hasbro has confirmed everyone's worst fears...will antagonize every living fan`. GameSpy (2004): `one of the worst board-to-computer adaptations to date`.
- Source: https://en.wikipedia.org/wiki/Avalon_Hill%27s_Squad_Leader
- Combat Mission: Beyond Overlord started as "Computer Squad Leader" with a contract from Avalon Hill in January 1997. Charles Moylan kept Avalon Hill IP out of the code from the start, so the game survived the Hasbro purchase.
- Combat Mission has a WeGo turn structure. The first-year inventory sold out 12 days after release. Computer Gaming World said it `altered the basic idea of what a wargame can be`.
- Source: https://en.wikipedia.org/wiki/Combat_Mission:_Beyond_Overlord
- Lesson: a licensed SL computer game that was not the board game did not succeed. An unlicensed game that kept the tactical feel and removed the board mechanics succeeded.

### AI opponents: fidelity and transparency (Second Front threads)

- "AI Defensive Fire" (2025-11-30, 30 replies). A player says the AI gets a second full defensive fire after it used its fire in the movement phase. The player names this compensation for weak AI. A second player counts AI infantry fire three times where ASL rules 8.3 to 8.4 let a unit fire two times.
- The developer replies that intensive fire was in the code but is off, because human players could not manage it. The developer also says full fire-group logic would decrease performance. Players request strict rule compliance.
- Source: https://steamcommunity.com/app/1148490/discussions/0/688616674580127428/
- AI "cheating" threads (Feb 2023 to Nov 2025): "AI kinda.... cheats?", "Does the AI cheat?", "How is the AI?" (24 replies), "how is the AI in this game?" (2025-04). In "Advices to play Second Front" the developer wrote that the `AI is playing by exactly the same rules the player is`. In "Enjoying the game" a player says the cheating suspicion was not correct after three weeks of play.
- Source: https://steamcommunity.com/app/1148490/discussions/search/?q=AI+cheat&gidforum=0
- Developer diary (entries 2026-08-10 to 2026-09-05). The AI has permanent commanders for each side, neutral sectors, a line-of-departure attack planner, and Broken, Desperate and Doomed conditions.
- The AI `examines the legal escape routes of Broken enemy units` and sends units to close them. When a broken unit is trapped, the AI `removes that unit from its fire-target choices`. The reason: `shooting at an already trapped Broken unit can trigger a Heat of Battle result that rallies it`. The developer wants decisions `visible enough to argue with`.
- The developer then says: `I feel much more confident about the current state of the AI and intend to move on to multiplayer development soon.`
- Source: https://steamcommunity.com/app/1148490/discussions/0/1746773321970002062/?ctp=18
- Signal: players audit the AI against the rulebook, phase by phase. They accept a hard AI only if it obeys the printed rules and the log shows it.

### Multiplayer interest

- "Is multiplayer (pvp) supported?" (2022-11-27, 78 replies, locked). Quotes: `No MP, no sale here.` and `I don't know one war-gamer who says 'I can't wait to play that war-game solo.'` One player wants hotseat `for play with my wife`. The developer says multiplayer `could be added after the release. But it depends on the wishes of the players.`
- Source: https://steamcommunity.com/app/1148490/discussions/0/3592213151642191130/
- In August 2026 the developer wrote: `No, multiplayer has not been abandoned. It is still planned and being worked on.`
- Source: https://steamcommunity.com/app/1148490/discussions/search/?q=multiplayer&gidforum=0

### LOS tools

- Second Front has no LOS tool. Players count hexes by hand. Tim Stone names the fog of war `halfhearted`: `enemies are never mis-identified and, even when technically out-of-LoS, are rarely hidden from view`. The game has no difficulty levels.
- Source: https://tallyhocorner.com/2023/02/second-front-review/
- Tigers on the Hunt: `Too frequently, the user interface lets me go onto clicking and selecting options for fire just to let me know that I'm trying to fire without a valid line of sight.` A commenter notes that ASL rules do not let you examine LOS before you declare fire.
- Source: https://kriegsimulation.blogspot.com/2016/04/tigers-on-hunt-review.html
- Valor & Victory: `clicking off your unit during movement also ends movement for that stack, meaning you can't check line of sight mid-move.`
- Source: https://www.gamewatcher.com/reviews/valor-victory-review/13283
- Lock 'n Load Tactical Digital: `I checked Line of Sight of enemy (very cool option in the app). I know where they can see me and where it is safe to move.` You can set Fog of War and Opportunity Fire modes at setup.
- Source: https://theboardgameschronicle.com/2023/04/18/lock-n-load-tactical-digital-starter-kit-first-impressions/
- VSQL users praise the module LOS but note edge errors (see section 1).
- Signal: players think an LOS tool is standard. The open question is when you let a player use it, because the board rules punish fire after you examine the LOS.

### Automation compared with a free play surface

- Tabletop-Club on Hacker News (2022-11-28, 286 points). One group wants a physics sandbox with no coded rules so that `humans play the game`. The other group wants `rules-enforcing` automation. One user found the physics `so bad it was deemed unusable`. A second user: `using a mouse to interact...feels clunky and you end up hitting other game pieces.`
- Source: https://hn.algolia.com/api/v1/items/33775085
- Valor & Victory: `the reliance on tabletop hit tables and animated dice rolls can break the immersion` for PC-native players. Also `unit stacks hide needed information behind clicks`.
- Source: https://www.gamewatcher.com/reviews/valor-victory-review/13283
- Conflict of Heroes PC: the game `gets even smoother with the computer calculating movement rates, DRMs and other penalties and bonuses.` Differences from the board game are kept APs, fog of war and unit quality.
- Source: https://www.play-board-games.com/conflict-of-heroes-awakening-the-bear-pc-game-review/
- SL players make their own calculators. A March 2026 Google Sheets aid has calculators for the IFT, to-hit, movement, morale, LOS and terrain effects. A reply names it `a good addition to any players SQL tool kit`.
- Source: https://api.geekdo.com/api/articles?threadid=3671672
- BGG files from 2020 to 2026 are mostly flowcharts and sequence-of-play documents (see section 3). This shows that rule navigation is the pain point.

### Solo play and hidden placement

- "Solo" (2025-11-07). Two-handed solo `works great` for a player who started in 1978. The primary problem is hidden initial placement. One player prepares `2+ possibilities, and then I dice for them`. A second player makes identical-looking stacks with dummy concealment stacks. Two solitaire scenarios are in "On All Fronts" ("Chance Encounter" and "The Bowling Alley").
- Source: https://api.geekdo.com/api/articles?threadid=3607007
- The 2020 BGG thread and "Still 'The Daddy'" also show solo play as important (section 1).
- Signal: an AI opponent that controls hidden setup and concealment removes the one problem that solo players cannot remove by hand.

### Learning and mentorship

- Nate Warren owned SL for 40 years before Warren learned it. Quote: `it doesn't matter how cool these games are unless somebody is there with you`. Warren learned through remote VASSAL sessions with a friend.
- Source: https://www.breakupgamingsociety.com/blog/learning-avalon-hill-squad-leader-after-owning-it-for-40-years
- The Warren scenario 1 session report is a tactics narrative, with no request for digital aids.
- Source: https://www.breakupgamingsociety.com/blog/avalon-hill-squad-leader-session-report-learning-scenario-1
- "First EVER play! What a blast!" (2023-10-11, 27 posts). The new player posted a question: does a KIA remove the full stack? The player said close combat rules `look a bit daunting`.
- Veterans gave tactics advice. No poster wanted digital aids.
- Source: https://api.geekdo.com/api/articles?threadid=3169116

## 3. Fan projects for SL, 2020 to 2026

### Official signal: Renegade Game Studios

- October 2022 thread "Renegade Games?" (21 posts). Renegade announced license work with Hasbro. SL was in the promotion one time. By late October 2022, posters said SL was out of the agreement. Only Axis & Allies, RoboRally and Diplomacy stayed.
- Source: https://api.geekdo.com/api/articles?threadid=2947046
- February 2025 thread "New Squad Leader Playtesting". Matt Hyra, Senior Game Designer at Renegade Game Studios, made a request for playtesters for a `streamlined Squad Leader for a new generation` on the Screentop digital platform. In April 2026 Hyra wrote `it is still in development`. The playtest request is closed.
- Source: https://api.geekdo.com/api/articles?threadid=3465479
- The Renegade Wikipedia page shows a Hasbro partnership since 2018, extended in October 2022. It does not refer to Squad Leader.
- Source: https://en.wikipedia.org/wiki/Renegade_Game_Studios
- Result: the license holder has an active digital playtest of a modernised SL. That is a competitor and a rights risk for a public project.

### BGG file uploads (2020 to 2026)

- 2026-07-07: Italian translations of the SL and COI manuals (Simone09).
- 2025-11-18: AFV Combat Flowchart (tanik).
- 2025-09-09: "Deluxe" redraw of map board 3 in an illustrative style, from scans of the originals (MGibo).
- 2025-06-15: AFV Counter Player Aid (tanik).
- 2024-11-10: OBA Flowchart (scott_67).
- 2023-07-18: SL Infantry Combat Summary and New Scenarios (CPagano).
- 2022-05-28: Sequence of Play Guide for Scenarios 1 to 12 (Michael Power).
- 2021-01-30: Ritterkrieg IIFT.
- 2020-01-24: Reconstructed Squad Leader 4th Edition Rules (pmikec).
- Source: https://api.geekdo.com/api/files?objectid=1035&objecttype=thing&pageid=1&sort=recent
- Older items: counter inventory spreadsheet (2018), SQLA Rule Conventions (2016), VSQL replay file (2015), "Blind Squad Leader" double-blind article from The General Vol 19 No 2 (2015).
- Source: https://api.geekdo.com/api/files?objectid=1035&objecttype=thing&pageid=2&sort=recent

### Rules consolidation

- February 2025 thread "Combined reformatted rules" (13 posts). A poster put the SL, COI, COD and GIA rules into ASL-style chapters. The poster completed most of chapter A. A second poster pointed to a Scribd document "Squad Leader Core Rules".
- Source: https://api.geekdo.com/api/articles?threadid=3465607
- The SQLA Q&A Compilation version 2.4 was released 2026-01-03 (thread title only).
- Source: https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=1&sort=recent

### Scenario databases

- The Australian Wargamer page (compiled about October 2011) shows all published SL scenarios with PDF sheets and an Excel index: 12 (SL), 18 (COI), 23 (COD), 15 (GIA), 17 (The General), 20 (The Wargamer).
- Source: https://australianwargamer.wordpress.com/paperback-wargames/world-war-2/advanced-squad-leader/original-squad-leader-scenari/
- tacticalwargamer.com holds history, rules explanation, scenario lists with ASL cross-references, and a bibliography. It notes that `many aficionados continued to prefer the simplicity of the earlier design to its more complicated offspring.`
- Source: https://www.tacticalwargamer.com/boardgames/squadleader/squadleader.htm

### Software

- ivcafe413/squad-leader-godot: `Open-source Godot implementation of the 1977 Avalon Hill board game`. GPL-3.0, GDScript, hotseat and online modes in the plan, v1 is for scenario 1 only, 15 commits, last push 2026-08-25, 0 stars. It has documents for movement, fire, morale, LOS and close combat.
- Sources: https://api.github.com/search/repositories?q=%22squad+leader%22+avalon&sort=updated&per_page=30 and https://github.com/ivcafe413/squad-leader-godot
- cryptopatrick/squadleader: a Rust `type system and rule engine to model small unit infantry combat simulation`. Generic, 9 commits, last push 2024-12-12, MIT or Unlicense. It does not name the Avalon Hill game.
- Source: https://github.com/cryptopatrick/squadleader
- jsquadleader (SourceForge): a Java "Computer Squad Leader" for remote multiplayer, GPLv2, beta, recorded 2002-05-03, last update 2013-05-13.
- Source: https://sourceforge.net/projects/jsquadleader/
- I found no browser or mobile version of SL.

### Tabletop Simulator

- Steam Workshop gave HTTP 429 on each fetch. A search result (not fetched) said a "Squad Leader" mod by Mr. Foxx was removed for a guideline violation. The same result said an "Avalon Hill" restored-games collection is available. Apply caution: I did not read the source.
- A BGG thread with the title "After Action Report, TTS AL-2" (2025-02-14) is a tactical narrative. It does not describe a TTS module.
- Source: https://api.geekdo.com/api/articles?threadid=3461282

### Miniatures

- "SL/COI in 15mm with hex map" (2025-03-24, 5 posts) shows players who moved SL to miniatures on a hex mat.
- Source: https://api.geekdo.com/api/forums/threads?forumid=64&objectid=1035&objecttype=thing&pageid=1&sort=recent

### YouTube channels and videos

BGG video list (dates are BGG post dates):
- 2026-03-23: Scenario 1 and Scenario 2 by Satoshi Mori (Japanese channel).
- 2026-01-01: "How Avalon Hill Changed Board Gaming Forever -- The Movie" by Legendary Tactics.
- 2025-11-25: "Squad Leader Scenario 1 AAR" by Breakup Gaming Society.
- 2024-07 to 2024-08: Guards Counterattack, Tractor Works and Streets of Stalingrad playthroughs by Knights and Warriors.
- 2024-08-10: "Memory Lane Chat: Squad Leader".
- Source: https://api.geekdo.com/api/videos?objectid=1035&objecttype=thing&pageid=1&sort=recent
- Channel names from YouTube oEmbed:
  - Legendary Tactics: https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=vVnmAKrqMzs&format=json and https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=vSgTYkMI7ZM&format=json
  - Rich (@Rich-gr5im), `Let's Play THE GUARDS COUNTERATTACK`: https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=l0oCgTG9ZLE&format=json
  - Knights and Warriors: https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=jIpII9mqCOY&format=json
  - Breakup Gaming Society: https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=sdTPetvDk4I&format=json
  - Japanese channel (Satoshi Mori): https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=M60ucVf_v_k&format=json
- View counts and upload dates were not readable (YouTube pages are client-rendered).

## 4. Hacker News and Reddit on board game AI, LLM play, RL self-play, wasm and boardgame.io

Reddit was not reachable. All items below are Hacker News or the linked articles.

### boardgame.io

- HN thread 2024-12-18, 345 points. Pitfalls: `many parts didn't really work right, lots of conflict between dependencies` (server side). Many npm vulnerabilities and deprecated packages on install. Redux-style state is `inconvenient` for card effects that branch.
- To keep state updates apart from UI animation, you must have an event or instruction stack. A built-in MCTS bot is available. The author works on boardgamelab.app at this time. Posters named Boardzilla as an alternative.
- Source: https://hn.algolia.com/api/v1/items/42449497
- Repository status 2026-09-07: 12,428 stars, 66 open issues, last push 2026-08-18, MIT, not archived.
- Source: https://api.github.com/repos/boardgameio/boardgame.io
- Older HN posts: FreeBoardGames.org (2021), the initial 2017 launch (657 points).
- Source: https://hn.algolia.com/api/v1/search?query=boardgame.io&tags=story&hitsPerPage=15

### Boardzilla

- HN thread 2024-01-29, 574 points. One TypeScript codebase runs on the server and on the client. The client runs `like the server, just without the hidden information`. Pluggable AI functions were in the plan.
- Users hit Object.hasOwn errors on older iOS. A user requested step-by-step tutorials. The Commons Clause license drew criticism.
- Source: https://hn.algolia.com/api/v1/items/39180953

### Open-source tabletop simulators

- Tabletop-Club (2022-11-28, 286 points): physics sandbox compared with rules enforcement, see section 2.
- Source: https://hn.algolia.com/api/v1/items/33775085

### LLMs that play games

- "Letting AI play my game" (2026, 136 points, 36 comments). The author made a text-only harness so that Claude could play-test a dungeon game. The longest session used about 300K tokens. Advice: keep a text interface, not screenshots.
- More advice: `run millions of simulated games headless` with deterministic bots for coverage. Let the LLM make bots in place of play on each turn. Real-time games break the loop.
- Source: https://news.ycombinator.com/item?id=47947525
- "Something weird is happening with LLMs and chess" (2024-11-14, 696 points). Chess performance is `extremely sensitive to prompting`. gpt-3.5-turbo-instruct completes PGN text and plays legal moves for 20+ moves. Chat models do worse.
- Source: https://hn.algolia.com/api/v1/items/42138289
- Follow-up article: a repeat of the full move list before each move helps. Three in-context examples help a lot. An explicit list of legal moves made the model worse. Fine-tuning on Elo 1800+ games helps.
- Source: https://dynomight.net/more-chess/
- Board Game Bench (2025-04): `LLMs struggle to even understand the rules well enough to consistently make valid moves`. No Scrabble game completed.
- Source: https://hn.algolia.com/api/v1/items/43556853
- Other 2025 to 2026 posts with low points: "Why are LLMs so bad at board games?" (2026-06), DiploBench (2026-08), settl (Catan with local LLMs, 2026-04).
- Sources: https://hn.algolia.com/api/v1/search?query=LLM%20board%20game&tags=story&hitsPerPage=25 and https://hn.algolia.com/api/v1/search?query=Diplomacy%20LLM&tags=story&hitsPerPage=20
- Cicero (2023-11-24, 285 points). The lesson: connect a language model to a planning engine that is not the LLM, because a pure LLM does not deliberate. Meta did not release usable weights.
- Source: https://hn.algolia.com/api/v1/items/38407521

### LLM plus RL, hobby scale

- "Training an LLM to play Diplomacy with RL" (2026-01-11). Qwen3-14B with LoRA and GRPO. Without constrained generation `valid move accuracy is ~50%`. A trie-based logits processor increased it to about 75% and gave a 10x inference speed-up. Per-token loss weights by order importance were `the single biggest improvement to model quality`. In league training `Your Elo can drop while you're improving`, so measure against opponents that do not change.
- A vLLM and HuggingFace logprob mismatch caused NaN losses.
- Source: https://www.benglickenhaus.com/blog/diplomacy_rl_part_1

### RL self-play

- tinyzero (2023-12-20, 87 points). Standard AlphaZero is for perfect-information games only. Use ReBeL, MuZero or methods of the same type for hidden information. Results are a function of `how long you can afford to train`. Keep action indexing the same between the policy head and the legal-move list. OpenAI Gym is unmaintained.
- Source: https://hn.algolia.com/api/v1/items/38707475
- mctx release (2023-02-15, 328 points). A Google Brain engineer said a three-person AlphaZero re-implementation used about one year: three months of code and the remainder to debug details that the paper did not give. Naive Python MCTS is very slow. A careful implementation gave a 30x speed-up. Gradient-boosted trees can replace the network at the start.
- Source: https://hn.algolia.com/api/v1/items/34801636
- Mastering Stratego (2022-12-01, 290 points). You cannot enumerate hidden information in Stratego as you can a poker deck. R-NaD trains one agent from zero to low exploitability. A game that favours defence can give passive optimal play that humans do not like.
- Source: https://hn.algolia.com/api/v1/items/33822145
- AlphaZero-related HN stories since 2022 with 20+ points: PNAS chess knowledge paper (103), "Reimagining Chess with AlphaZero" (155), mctx (328), tinyzero (87), AlphaZero in MLX (71, 2025-05).
- Source: https://hn.algolia.com/api/v1/search?query=AlphaZero&tags=story&hitsPerPage=30

### WebAssembly engines shared with Python

- The HN query found no story about one game engine shared between browser wasm and Python. "WebAssembly game engine Python Rust" gave zero hits. The nearest items were WasmBots (2025-01, 5 points) and small Pyodide games.
- Sources: https://hn.algolia.com/api/v1/search?query=WebAssembly%20game%20engine%20Python%20Rust&tags=story&hitsPerPage=25 and https://hn.algolia.com/api/v1/search?query=wasm-bindgen%20game&tags=story&hitsPerPage=20 and https://hn.algolia.com/api/v1/search?query=Pyodide%20game&tags=story&hitsPerPage=20
- Gap: there is no community data for or against that architecture. Make the decision on engineering grounds.

## 5. Designers and voices to read

### John Hill (1945 to 2015)

- Obituary by Gerald D. Swick, 2015-01-12. Hill entered the GAMA Hall of Fame in 1978. Squad Leader entered in 2004. SL started as miniatures rules and became a counter game at the request of Avalon Hill. Other designs: Jerusalem, Battle for Hue, Battle for Stalingrad, Tank Leader, Johnny Reb, Across a Deadly Field.
- Source: http://armchairgeneral.com/in-memoriam-john-hill-1945-2015-designer-of-squad-leader.htm
- The 2 Half-Squads interview, recorded February 2010, rebroadcast 2015-01-14. Transcript quotes: SL has `elegant simplicity` that gave it `legs`.
- More quotes: `the system is very, very robust, as is SQUAD LEADER, you can just pile a lot of stuff on it as ADVANCED SQUAD LEADER proved and the system holds up quite well`. `I think ASL has gone too far with too much detail, and too much that slows down the game too much`. `once you learned the game, the basic game, you could play it in real time, two minutes per turn`.
- When rule-checking uses `a half-hour to resolve...you've gotten a lot of detail, but I think you lost the realism`. The 4-4-7 base squad came from leftover Verdun counters `already labelled as four-fours`.
- Sources: https://www.the2halfsquads.com/2015/01/special-john-hill-interview.html and http://thetacticalwargamer.blogspot.com/2018/04/the-2-half-squads-interview-with-john_20.html
- The Fire & Movement interview on acrossadeadlyfield.com is client-rendered and gave no text.
- Source (empty): https://acrossadeadlyfield.com/fire-movement-interview-with-john-hill
- "History of Tactical Games: Evolution of Squad Leader" by Stephanie Hill (2015), from the Fire & Movement special report by Rodger B. MacGowan. Lineage from Tactical Game 3 (1969). A 1976 Dunnigan interview says Avalon Hill went to Hill for a squad-level game.
- Source: https://acrossadeadlyfield.com/history-of-tactical-games-evolution-of-squad-leader

### Don Greenwood

- Greenwood went to Avalon Hill in 1972 as Research and Design Director and editor of The General. Greenwood revised Cross of Iron. Greenwood was the primary designer of GI: Anvil of Victory (1982) and Advanced Squad Leader (1985). Greenwood helped to start Origins (1975) and the WBC.
- Source: https://en.wikipedia.org/wiki/Don_Greenwood_(game_designer)

### The General articles on SL

- Vol 14 No 5, item 1: "Squad Leader First Impressions" (Robert Medrow).
- Vol 14 No 5, item 2: "Historical Commentary: The Evolution of Small Unit Tactics" (John Hill).
- Vol 14 No 5, item 3: "Design Analysis: Game Design: Art or Science" (Don Greenwood, John Hill, Hal Hock).
- Vol 15 No 6, Vol 17 No 2, Vol 20 No 1: "An Introduction to Squad Leader Plus One / Two / Three" (Robert Medrow).
- Source: https://www.vftt.co.uk/ah_mags.asp?ProdID=index
- Vol 19 No 2: "Blind Squad Leader", a double-blind moderated system (via BGG files).
- Source: https://api.geekdo.com/api/files?objectid=1035&objecttype=thing&pageid=2&sort=recent

### Retrospectives

- No Dice No Glory, Patrick S. Baker, 2023-06-15. SL was `a watershed moment in war gaming`. Hill decreased infantry fire results to three outcomes. The eight-phase turn is `a module of time, such that events can occur and interact with one another`. Larry Harris (Axis & Allies) named SL `a significant influence on my design approach`.
- Sales: more than 100,000 copies sold in the first years. Charles S. Roberts award 1977.
- Source: https://nodicenoglory.com/a-retrospective-of-squad-leader/
- Grognardia, James Maliszewski, 2011-03-02. Attractive, readable counters. Geomorphic maps used again for RPG campaigns. SL `was designed to allow players to create their own scenarios easily`. A note that a complex WW2 simulation was one time on Toys R Us shelves.
- Source: http://grognardia.blogspot.com/2011/03/retrospective-squad-leader.html
- tacticalwargamer.com: by 1983 `there were four separate rulebooks with sometimes contradictory or poorly integrated rules`. ASL replaced them. `many aficionados continued to prefer the simplicity of the earlier design`.
- Source: https://www.tacticalwargamer.com/boardgames/squadleader/squadleader.htm
- Wikipedia: initial purple-box run of 2,500. More than 100,000 sold. SL and ASL went above 1 million by 1997.
- Sources: https://en.wikipedia.org/wiki/Squad_Leader and https://en.wikipedia.org/wiki/Avalon_Hill%27s_Squad_Leader

## 6. Related modern digital games and their lessons

### Second Front (Hexdraw / MicroProse, 2023)

- Steam: released 2023-01-31, "Mostly Positive", 78% of 613 reviews, $34.99. Features: `Competitive emergent AI`, 48 scenarios, editor, 40+ infantry types, 216+ vehicles and weapons.
- Source: https://store.steampowered.com/app/1148490/Second_Front/
- Team: `We are two people developing Second Front full time` (Jo Bader, 2022-03-18), with volunteer testers and MicroProse art help.
- Source: https://steamcommunity.com/app/1148490/discussions/0/3187991824505847732/
- Interview 2021-04-30: Bader reports `wargaming and coding for 30 years`. The four-phase turn is `all about being able to move into the enemy space`. Players `play too cautiously`. `Right now I'm working on weapons and after that I'm going to work more on the AI.`
- Source: https://strategyandwargaming.com/2021/04/30/interview-second-front/
- Strategy and Wargaming review 2023-01-31: the AI `will try to puncture your lines, exploit those weaknesses, flood the objectives, and avoid getting mowed down`. AI turns use `several minutes` in large battles. Flaws: binary victory conditions, weak tutorials, missions locked behind progression.
- Source: https://strategyandwargaming.com/2023/01/31/second-front-review-a-magnum-opus-despite-its-flaws/
- Tally-Ho Corner, Tim Stone, 2023-02-03: the AI `handles her units with aplomb` and `ensures player victories never come easy`. But `she flounders` on some maps and has bad AFV habits. Twelve IGOUGO phases from ASL are `somewhat fussy`.
- Also from Tim Stone: no LOS tool. Fog of war `halfhearted`. No difficulty levels.
- Source: https://tallyhocorner.com/2023/02/second-front-review/
- asl-players.net, Neal U., 2023-01-31: the game `unabashedly borrows heavily from the Advanced Squad Leader system`. Unit statistics are the same or almost the same as ASL. `I do believe the AI needs some work. It's very timid to counterattacks, especially with vehicles.` Missing: OBA, entrenching, most nationalities.
- Source: https://asl-players.net/second-front-a-comparison-to-asl/
- Rules automation and AI transparency: see section 2 (AI Defensive Fire thread, developer diary).
- Lesson: a two-person team shipped a commercially viable ASL-like game with a rules-bound AI. The community continues to find each rule deviation. No LOS tool, weak fog of war and no multiplayer are the permanent complaints.

### Lock 'n Load Tactical Digital (2020)

- Steam: released 2020-04-02, "Very Positive", 82% of 566 reviews, $4.99 core. Limited multiplayer. Battle Generator DLC. The developers plan to `gradually...improve the AI tactics`.
- Source: https://store.steampowered.com/app/1149940/Lock_n_Load_Tactical_Digital_Core_Game/
- Boardgames Chronicle 2023-04-18: `I like how AI plays - especially on higher difficulty levels ... in general is a decent opponent.` The reviewer saw no rules errors in the software. The reviewer praised the LOS function.
- Source: https://theboardgameschronicle.com/2023/04/18/lock-n-load-tactical-digital-starter-kit-first-impressions/
- Steam thread `Measured against it's peers` (2023-11-27). One poster says Tigers on the Hunt `plays more like Squad Leader` and Second Front is `awesome` but too 3D. A second poster says LnL is `far, far superior as a game than valor and victory` and finds Tigers unplayable.
- Source: https://steamcommunity.com/app/1149940/discussions/0/4038102480392512600/

### Nations at War Digital (2020)

- Steam: released 2020-04-25, Early Access at this time, "Mostly Positive", 71% of 105 reviews, $4.99. Steam notes `The last update made by the developers was over 5 years ago`.
- Source: https://store.steampowered.com/app/1226000/Nations_At_War_Digital/
- Lesson: an unfinished Early Access wargame stops, and the community sees it.

### Tigers on the Hunt (2016)

- Real and Simulated Wars, 2016-04-23: the AI is `Occasionally good at defending but reckless and incompetent at attacking.` `Almost all the other core rules of Advanced Squad Leader are there`, but not full multi-story buildings. The reviewer says the game `dilapidates a lot of talent on an incomplete, half-hearted computer port`.
- Source: https://kriegsimulation.blogspot.com/2016/04/tigers-on-hunt-review.html
- Big Boss Battle, 2016-03-11: four difficulty levels set which sides must roll for command of units each turn. `Line of sight is also clearly visible due to the art design`. The UI is `an old, early 90's style UI`.
- Source: https://bigbossbattle.com/review-tigers-on-the-hunt/
- Matrix forum thread 2016 to 2018: counter values `match up with the exception of the smoke exponent`. Players made French, Finnish, Italian and Japanese forces from the available units.
- Source: https://forums.matrixgames.com/tm.asp?key=&m=4041280&mpage=1
- Lesson: rules fidelity alone does not support a game. UI and AI attack behaviour make the reviews.

### Valor & Victory (2021)

- GameWatcher, Matthew Ralphson, 2021-06-16, score 7.0. `meticulously designed for fans of that format`. Hit tables and animated dice `can break the immersion`. Stacks hide information. You cannot examine LOS in the middle of a move.
- Source: https://www.gamewatcher.com/reviews/valor-victory-review/13283
- Steam review share from a search result (not fetched): 69% positive of 163. Apply caution: I did not read the source.
- Lesson: PC-native players reject board-game friction that tabletop players accept.

### Conflict of Heroes: Awakening the Bear (2012)

- play-board-games.com, score 5 of 6. `The AI in the game can be challenging and being able to play the game solo is great.` The computer calculates `movement rates, DRMs and other penalties and bonuses`. Digital-only functions: kept APs, fog of war, unit quality.
- Source: https://www.play-board-games.com/conflict-of-heroes-awakening-the-bear-pc-game-review/
- The BGG "Solo" thread recommends this game with its solitaire expansion to new solo players.
- Source: https://api.geekdo.com/api/articles?threadid=3607007

### Combat Mission (2000)

- See section 2. It started as Computer Squad Leader and became its own game.
- Source: https://en.wikipedia.org/wiki/Combat_Mission:_Beyond_Overlord

### Avalon Hill's Squad Leader (Hasbro, 2000)

- See section 2. Metacritic 46. Not the board game.
- Source: https://en.wikipedia.org/wiki/Avalon_Hill%27s_Squad_Leader

### Summary of AI reception across the set

| Game | AI verdict in reviews | Source |
|---|---|---|
| Second Front | Strong on attack and defence, rules-bound, timid with vehicles, no difficulty levels | tallyhocorner.com, asl-players.net |
| LnL Tactical Digital | Decent, better on defence, better with each update | theboardgameschronicle.com |
| Tigers on the Hunt | Defends sometimes, weak in attack | kriegsimulation.blogspot.com |
| Valor & Victory | Not discussed in the fetched review | gamewatcher.com |
| Conflict of Heroes PC | Challenging, good for solo | play-board-games.com |
| Nations at War | Development stopped | store.steampowered.com |

## The three strongest signals for a digital Squad Leader

1. The AI must obey the printed rules and show its work. Players count AI fire phases against rule numbers. They open "does the AI cheat" threads for years. The Second Front developer answers with `exactly the same rules` and decisions `visible enough to argue with`. A digital SL must have a log for each action with rule IDs, dice and modifiers for the two sides.
2. Automate lookups and LOS, but keep the tabletop feel and make it optional. VSQL LOS, the LnLT LOS function and the SL Google Sheets calculators get praise. Second Front and Tigers get criticism for LOS feedback that is missing or comes too late. Valor & Victory shows that shown dice and tables annoy PC-native players. Supply a rules-enforced surface with dice, tables and LOS views that you can turn on or off.
3. Solo players are the core of the SL community, and hidden placement is their unsolved problem. Solo play dominates the BGG threads from 2020 to 2025. Players roll dice for hidden setups and use dummy stacks by hand. An AI that controls hidden setup and concealment, plus hotseat and PBEM parity, satisfies the solo base and the "No MP, no sale" group.

A fourth signal to monitor: Renegade Game Studios has a streamlined Squad Leader in digital playtest (2025 to 2026). It is a license risk and proof that the publisher sees interest.

## References (all fetched on 2026-09-07 unless marked)

BGG data
- https://api.geekdo.com/api/dynamicinfo?objectid=1035&objecttype=thing
- https://api.geekdo.com/api/forums?objectid=1035&objecttype=thing
- https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=1&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=2&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=3&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=4&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=5&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=65&objectid=1035&objecttype=thing&pageid=6&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=66&objectid=1035&objecttype=thing&pageid=1&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=64&objectid=1035&objecttype=thing&pageid=1&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=68&objectid=1035&objecttype=thing&pageid=1&sort=recent
- https://api.geekdo.com/api/forums/threads?forumid=274&objectid=1035&objecttype=thing&pageid=1&sort=recent
- https://api.geekdo.com/api/threads/2555617
- https://api.geekdo.com/api/articles?threadid=2555617
- https://api.geekdo.com/api/articles?threadid=3620935
- https://api.geekdo.com/api/articles?threadid=3607007
- https://api.geekdo.com/api/articles?threadid=3738095
- https://api.geekdo.com/api/articles?threadid=3671672
- https://api.geekdo.com/api/articles?threadid=3652135
- https://api.geekdo.com/api/articles?threadid=3465479
- https://api.geekdo.com/api/articles?threadid=3465607
- https://api.geekdo.com/api/articles?threadid=3463841
- https://api.geekdo.com/api/articles?threadid=3461282
- https://api.geekdo.com/api/articles?threadid=3056316
- https://api.geekdo.com/api/articles?threadid=3169116
- https://api.geekdo.com/api/articles?threadid=3279700
- https://api.geekdo.com/api/articles?threadid=3129657
- https://api.geekdo.com/api/articles?threadid=2947046
- https://api.geekdo.com/api/files?objectid=1035&objecttype=thing&pageid=1&sort=recent
- https://api.geekdo.com/api/files?objectid=1035&objecttype=thing&pageid=2&sort=recent
- https://api.geekdo.com/api/videos?objectid=1035&objecttype=thing&pageid=1&sort=recent

SQLA, VASSAL, community sites
- https://sites.google.com/site/2012squadleadertourny/home
- https://sites.google.com/site/2012squadleadertourny/vsql-module
- https://r.jina.ai/https://vassalengine.org/wiki/Module:Squad_Leader
- https://talk.consimworld.com/
- https://discord.com/servers/advanced-squad-leader-central-415876852419395586
- https://www.facebook.com/groups/103649983443889/
- https://www.facebook.com/groups/103649983443889/posts/249078145567738/
- https://www.facebook.com/tabletopstrategist/posts/old-school-squad-leader-avalon-hill-1977-the-game-that-introduced-a-generation-t/122186807288769211/
- https://forums.matrixgames.com/viewtopic.php?t=103257
- https://forums.matrixgames.com/viewtopic.php?p=515260
- https://www.breakupgamingsociety.com/blog/learning-avalon-hill-squad-leader-after-owning-it-for-40-years
- https://www.breakupgamingsociety.com/blog/avalon-hill-squad-leader-session-report-learning-scenario-1
- https://www.tacticalwargamer.com/boardgames/squadleader/squadleader.htm
- https://australianwargamer.wordpress.com/paperback-wargames/world-war-2/advanced-squad-leader/original-squad-leader-scenari/

Fan software
- https://api.github.com/search/repositories?q=%22squad+leader%22+avalon&sort=updated&per_page=30
- https://api.github.com/search/repositories?q=squadleader&sort=updated&per_page=30
- https://github.com/ivcafe413/squad-leader-godot
- https://github.com/cryptopatrick/squadleader
- https://sourceforge.net/projects/jsquadleader/
- YouTube oEmbed URLs in section 3

Digital games
- https://store.steampowered.com/app/1148490/Second_Front/
- https://steamcommunity.com/app/1148490/discussions/0/3187991824505847732/
- https://steamcommunity.com/app/1148490/discussions/0/688616674580127428/
- https://steamcommunity.com/app/1148490/discussions/0/3592213151642191130/
- https://steamcommunity.com/app/1148490/discussions/0/1746773321970002062/?ctp=18
- https://steamcommunity.com/app/1148490/discussions/0/1746773321970002062/?ctp=17
- https://steamcommunity.com/app/1148490/discussions/search/?q=AI+cheat&gidforum=0
- https://steamcommunity.com/app/1148490/discussions/search/?q=multiplayer&gidforum=0
- https://strategyandwargaming.com/2021/04/30/interview-second-front/
- https://strategyandwargaming.com/2023/01/31/second-front-review-a-magnum-opus-despite-its-flaws/
- https://tallyhocorner.com/2023/02/second-front-review/
- https://asl-players.net/second-front-a-comparison-to-asl/
- https://store.steampowered.com/app/1149940/Lock_n_Load_Tactical_Digital_Core_Game/
- https://theboardgameschronicle.com/2023/04/18/lock-n-load-tactical-digital-starter-kit-first-impressions/
- https://steamcommunity.com/app/1149940/discussions/0/4038102480392512600/
- https://store.steampowered.com/app/1226000/Nations_At_War_Digital/
- https://kriegsimulation.blogspot.com/2016/04/tigers-on-hunt-review.html
- https://bigbossbattle.com/review-tigers-on-the-hunt/
- https://forums.matrixgames.com/tm.asp?key=&m=4041280&mpage=1
- https://www.gamewatcher.com/reviews/valor-victory-review/13283
- https://www.play-board-games.com/conflict-of-heroes-awakening-the-bear-pc-game-review/
- https://en.wikipedia.org/wiki/Combat_Mission:_Beyond_Overlord
- https://en.wikipedia.org/wiki/Avalon_Hill%27s_Squad_Leader

Designers and history
- http://armchairgeneral.com/in-memoriam-john-hill-1945-2015-designer-of-squad-leader.htm
- https://www.the2halfsquads.com/2015/01/special-john-hill-interview.html
- http://thetacticalwargamer.blogspot.com/2018/04/the-2-half-squads-interview-with-john_20.html
- https://acrossadeadlyfield.com/history-of-tactical-games-evolution-of-squad-leader
- https://en.wikipedia.org/wiki/Don_Greenwood_(game_designer)
- https://www.vftt.co.uk/ah_mags.asp?ProdID=index
- https://nodicenoglory.com/a-retrospective-of-squad-leader/
- http://grognardia.blogspot.com/2011/03/retrospective-squad-leader.html
- https://en.wikipedia.org/wiki/Squad_Leader
- https://en.wikipedia.org/wiki/Renegade_Game_Studios

Hacker News and technical
- https://hn.algolia.com/api/v1/items/42449497
- https://api.github.com/repos/boardgameio/boardgame.io
- https://hn.algolia.com/api/v1/search?query=boardgame.io&tags=story&hitsPerPage=15
- https://hn.algolia.com/api/v1/items/39180953
- https://hn.algolia.com/api/v1/items/33775085
- https://news.ycombinator.com/item?id=47947525
- https://hn.algolia.com/api/v1/items/42138289
- https://dynomight.net/more-chess/
- https://hn.algolia.com/api/v1/items/43556853
- https://hn.algolia.com/api/v1/search?query=LLM%20board%20game&tags=story&hitsPerPage=25
- https://hn.algolia.com/api/v1/search?query=Diplomacy%20LLM&tags=story&hitsPerPage=20
- https://hn.algolia.com/api/v1/items/38407521
- https://www.benglickenhaus.com/blog/diplomacy_rl_part_1
- https://hn.algolia.com/api/v1/items/38707475
- https://hn.algolia.com/api/v1/items/34801636
- https://hn.algolia.com/api/v1/items/33822145
- https://hn.algolia.com/api/v1/search?query=AlphaZero&tags=story&hitsPerPage=30
- https://hn.algolia.com/api/v1/search?query=WebAssembly%20game%20engine%20Python%20Rust&tags=story&hitsPerPage=25
- https://hn.algolia.com/api/v1/search?query=wasm-bindgen%20game&tags=story&hitsPerPage=20
- https://hn.algolia.com/api/v1/search?query=Pyodide%20game&tags=story&hitsPerPage=20

Fetches that did not succeed (for the record)
- https://boardgamegeek.com/boardgame/1035/squad-leader/forums/0 (403)
- https://boardgamegeek.com/thread/2555617/anyone-still-playing-the-original-squad-leader (403)
- http://www.wargameacademy.org/SQLA/ and subpages (connection closed)
- https://www.reddit.com/r/hexandcounter/ and old.reddit.com (blocked by tool)
- https://steamcommunity.com/sharedfiles/filedetails/?id=702134282 and ?id=2595656353 (429)
- https://acrossadeadlyfield.com/fire-movement-interview-with-john-hill (client-rendered, empty)
- https://www.gamespot.com/reviews/squad-leader-review/1900-2649062/ (403)
- https://en.citizendium.org/wiki/Squad_Leader (403)
- https://saveorquit.com/2021/07/05/review-valor-victory/ (403)

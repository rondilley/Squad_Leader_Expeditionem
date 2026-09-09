# Squad_Leader_AI: Vision

Status: Draft v0.3, strategic north star, after the second multi-AI review
Author: Ron Dilley
Last updated: 2026-09-07
Companion documents: `REQUIREMENTS.md` (year-one engineering scope), `SUCCESS_CRITERIA.md` (measurable outcomes), `ARCHITECTURE.md` (year-one design), `2026-09-07_Squad_Leader_Digital_Edition_Research.md` (the evidence)

This document is the strategic north star. It gives the cause for the project, the persons with an interest in it, the three-year arc, the bets, and the anti-goals. Use this document to argue about direction. Use the other documents to argue about the build.

Naming note: the repository is `Squad_Leader_AI`. The game gets a different public title before a release, because the research shows that "Squad Leader" as a brand is a trademark risk (see section 4, bet 5). In this document "the game" means the software this project builds. "Squad Leader" means the 1977 Avalon Hill board game with the rules that the software plays. This project is not affiliated with, sponsored by, or endorsed by Hasbro or Multi-Man Publishing.

## 1. The vision in one paragraph

By 2027-09 Ron plays the 1977 Squad Leader rules in a browser against a computer opponent. That opponent learned its tactics by self-play. The game shows a log for each action with the rule number, the dice, and the modifiers. The same engine runs three more ways: two humans at one screen, two browsers on the LAN, and computer against computer for training and tournaments.

Computer opponents come in four families. Scripted agents follow constant tactics with tunable parameters. Learned agents are neural networks that train by self-play on the owner's workstation. They get better from one generation to the next. Prompted model agents use local models or SaaS models through one provider interface, and the engine keeps them legal.

Tuned model agents are local language models, small or large, fine-tuned on this game's own traces. They play through the same harness with constrained decoding. <!-- Owner directive 2026-09-07: tuned local model as a fourth agent family -->

The boards look like the 1977 boards but come from a generator. Thus the project ships no Avalon Hill art. The first year ships Game Set I, the infantry game with scenarios 1 to 3. The subsequent years add the armor game, the design-your-own tools, and the campaign game.

## 2. Why a rules engine, not a play surface

The community has a play surface at this time. VASSAL with the VSQL module gives boards, counters, dice, hidden units, and a line of sight check. The Squad Leader Academy ladder runs on it. A second play surface adds nothing.

The value of this project is in the three things a play surface cannot give:

- A computer opponent. Solo play dominates the community's session reports. Hidden initial placement is the one problem that solo players cannot remove by hand. An opponent that controls hidden setup and concealment is only possible when software owns the rules.
- Rule fidelity that a player can audit. Players of Second Front count the AI's fire phases against the rule numbers and open "does the AI cheat" threads for years. The answer is a log with rule IDs, dice, and modifiers for the two sides. That log is only possible when the engine applies each rule.
- Learning. Self-play, replay, behavior cloning, and prompt evolution all use the same thing: an engine that can play a full game in milliseconds with no human in the loop.

The arithmetic is the same as for a platform. Each play mode and each agent family would cost the same set of things if built alone: legality, phase sequence, dice, LOS, tables, replay, and a log. Built one time in the engine, they are inherited. The engine is the constant. The play modes and the agents are the variables.

<!-- AI review 20260907-163721: openai. The text said two AI families. There are four. -->

## 3. The principal map

| Principal | Role | What is important to them |
|---|---|---|
| Ron Dilley | Owner, sole developer, first player | A faithful, playable game. AI opponents that get better. Local and SaaS models work. A build that a future session can continue without re-derivation. |
| Ron's human opponents | Players at the same screen or on the LAN | Correct rules, a readable board, a simple procedure to connect, and no accounts. |
| The Squad Leader solo community | The BoardGameGeek and SQLA players | An opponent that obeys the printed rules and shows its work. LOS and table lookups automated, with the tabletop feel available as a switch. |
| Hasbro and Multi-Man Publishing | Rights holders and licensee | Their copyright in the art and the rules text and their trademark in the name. They tolerated VASL and the SQLA rules project for decades, but tolerance is not a license. |
| Squad Leader Academy and the VASL developers | Prior digital keepers | Credit for the softcopy rules, the scenario scans, and the LOS engine. No copies of their graphics. |
| Future Claude sessions | Builders | Invariants, rule IDs in the engine, a conformance battery, and a history file that says what was decided and why. |

The asymmetry that matters: only Ron holds the taste test for "looks like the board game". Each rendering and generation decision ends at that test, and the test has no written rubric at this time. Section 7 names the rubric as year-one work.

## 4. The five strategic bets

These are the convictions the project is built on. Each one names where it breaks and what the project does about it.

### Bet 1: A rule-cited engine beats a play surface

The claim: the engine applies each rule of the 4th edition text and keeps the rule ID with each application. It writes a log that a player can audit. The log shows the rule, the dice, the modifiers, and the result for the two sides.

Why it is right: the community signal is unambiguous. Rule fidelity and transparency are what players want from a digital opponent. They are also what the legal analysis lets the project do. Numbers, rule IDs, and technical terms get no copyright protection. A rulebook paraphrase gets thin protection at most.

Where it breaks: the 1977 rules have ambiguities, and the Q and A booklet resolves some but not all of them. A player can contest an automated ruling.

Mitigation: the engine encodes the official Q and A rulings with their references. Each contested rule is a switch where the rules give a choice. A tabletop mode shows the dice and the tables, so a player can see what the engine did.

### Bet 2: One engine, many consumers, with a measured gate

The claim: one rules core with no input or output is the engine for all consumers. The consumers are the browser, the LAN host, the trainer, the model agent harness, and replay. The core is deterministic from a seed and a command log.

Why it is right: each consumer that a second engine would supply is a source of drift. The research found mature projects that ship one core to a browser and to Python. A conformance battery that each binding runs is the proven test strategy.

Where it breaks: the owner selected a Python core first. CPython is 10 to 200 times slower than Node.js on compute-bound benchmarks. Reinforcement learning at 100 million to 300 million steps must have about 3,500 environment steps/s end to end to complete in 24 hours.

Mitigation: the throughput gate is a year-one milestone. Ron measures it on the training workstation before a long run.

If the Python core cannot give the gate, the core moves to Rust with PyO3 and wasm-bindgen bindings before training starts. The core has no input or output and a JSON conformance battery, so the port is bounded and testable. It is its own milestone with its own budget, not a mechanical step. <!-- AI review 20260907-160656: openai -->

### Bet 3: Engine-verified model agents are playable opponents at low cost, and a tuned local model can beat a prompted one

The claim: a language model can play a phase when the engine gives it three things. The three things are a compact text state, a legal-move list with IDs, and a flat JSON schema for the answer. The engine verifies the answer, retries a small number of times (default 2), and then applies a scripted default. <!-- AI review 20260907-160656: gemini, openai -->

Why it is right: the research shows that invalid moves continue with each prompt style. A strong Diplomacy harness saw 6 to 14 percent invalid orders. A perception and memory harness lifts results for each model. A legal-move list in the prompt can make play worse if the model must select from it blind. The harness design absorbs the failure modes the papers report.

A local 8B to 32B model on one RTX 5090 plays a game in 3 to 8 minutes at no cost. A SaaS model plays a game for 3 cents to 4.48 dollars.

The second half of the claim: a local 7B to 14B model fine-tuned with LoRA on the game's own traces makes fewer invalid commands than the same model prompted. With a legal-command constraint at decode time, it also wins more games.

The research gives the methods (SPIN, SPIRAL, LoRA on winning traces) and one hobby-scale data point (a trie-based logits constraint raised valid moves from about 50 to about 75 percent in Diplomacy). No paper tried it on this game. <!-- Owner directive 2026-09-07: tuned local model as a fourth agent family -->

Where it breaks: WARBENCH reports rule violations up to about 70 percent for small edge models with complex terrain. It also reports that 4-bit quantization causes catastrophic degradation. A model agent can be a weak opponent.

Mitigation: the model agent is one family, not the only one. The learned agents and the scripted agents are the primary opponents. The model agent's invalid-move rate, fallback rate, and win rate are recorded from day one, and prompt evolution uses them as fitness.

### Bet 4: Self-play on one workstation learns useful tactics

The claim: PPO in raw torch learns tactics that beat the scripted bots at 100 million to 300 million steps. The action is a unit-by-unit composed action with a legal-action mask from the engine. The training runs in a snapshot league with scripted bots.

Why it is right: the closest paper (arXiv 2502.13918) shows AlphaZero learns a hex-and-counter ruleset at toy scale on CPU only. Gym-uRTS got to state-of-the-art bot play at 300 million steps on one GPU. The action-space template and the masking method are published and proven. The sibling project SpaceWar_AI has the league code.

Where it breaks: no paper tried a game with dice, morale, rout, and concealment at this scale on one GPU. The policy can learn nothing useful, or learn a passive style that humans do not enjoy.

Mitigation: behavior cloning from human, scripted, and model-agent replays when 200 games are available. Scripted bots tuned by CMA-ES stay as constant opponents and as the fallback opponent. Elo against constant opponents measures the league, not the score against the current self.

### Bet 5: New art in the 1977 style, boards from a generator, and a different name keep the project safe

The claim: the game can look like the board game without one Avalon Hill pixel. Counter values and their positions are functional. The silhouettes, colors, and board art are new. Boards come from a generator that keeps the geomorphic edge rules, the hex geometry, and the 1977 look. The four 1977 layouts stay as private reference data that the project does not ship.

Why it is right: four court cases that agree with each other and the Copyright Office give no protection to rules, mechanics, or tables. They give full protection to art and to a fanciful look and feel. Freeciv, OpenTTD, FreeCol, and TripleA survived on that line. Scrabulous did not.

Where it breaks: a board from the generator can miss the owner's taste test, and the 12 printed scenarios use the four 1977 layouts.

Mitigation: the taste test gets a written rubric in year one. The scenarios run on the private reference layouts on the owner's machine. A permission request to MMP or Hasbro is a path if the project ever wants to ship the layouts. Renegade Game Studios has a streamlined Squad Leader in digital playtest, so an official digital product is possible, and the project stays non-commercial.

## 5. The three-year arc

### 5.1 Year 1 (2026-09 to 2027-09): Foundation

Theme: the infantry game plays correctly in the browser, with all four play modes, and the training loop runs.

The work runs in sequence: <!-- AI review 20260907-160656: gemini, xai, openai -->

- v0.1: the headless rules proof and the throughput gate
- v0.2: browser hot seat against a local host
- v0.3: scenarios 2 and 3A with LAN
- v0.4: the learning ladder and the model agents
- then the release candidate

End-of-year state:

- The rules core plays rules 1 to 27 (Game Set I plus sewers) with rule IDs and an action log. A JSON conformance battery covers each rule with a minimum of one case.
- Scenarios 1, 2, and 3 (with variation 3A) play from data files that follow the scenario card schema.
- The browser client renders boards from the generator in the 1977 style and new counters. It has pan, zoom, a switchable tabletop mode, and the LOS tool at the times the rules let a player use it.
- Hot seat play works against a local host process. LAN play works through the same host with a room code and a per-player view.
- Three scripted opponents play all three scenarios. One prompted model agent plays through the engine-verified harness on a local model and on one SaaS model, with the metrics recorded. One tuned model agent, a local model fine-tuned on the game's traces, plays the same tournament, and the four families are compared on one table.
- Ron measured the throughput gate. The Python core gives 3,500 steps/s, or the Rust port is complete.
- The learning ladder ran: 1 million steps for a sanity signal, 10 million for a pilot, then a minimum of 100 million. The learned agent's Elo against versioned scripted bots is recorded with confidence intervals.
- The written rubric for "looks like the board game" is available, and the generator satisfies it.

### 5.2 Year 2 (2027-09 to 2028-09): Earn

Theme: the armor game, the design-your-own tools, and a league that gets better.

End-of-year state:

- Rules 28 to 63 play, when a readable copy of the second data card page is in hand. Scenarios 4 to 12 play on the private reference layouts.
- The design-your-own tools from Game Set IV work: random scenario construction, point values, and the campaign game with a personal leader.
- The league runs unattended, with snapshots, scripted bots, and model agents as test opponents. Population-based training tunes the scripted bots and the reward weights.
- Play by email through the command log works, because the log is the game.
- The project has its public title and a first public GPL-3 release.

### 5.3 Year 3 (2028-09 to 2029-09): Scale

Theme: the system is a platform for tactical WW2 rules, not one game.

End-of-year state:

- The rule set is data-driven to the point where a gamette overlay (Cross of Iron first) is a data change plus a small code change. This is the owner's decision, not a commitment.
- A community scenario format lets a player write a scenario card as data and share it.
- Learned agents have a public Elo history, and a stranger can play the best one in a browser.

## 6. What the project does not build

Year-one anti-goals:

- No Advanced Squad Leader. Different game, different rulebook.
- No gamettes. The engine design makes an overlay possible, but Cross of Iron, Crescendo of Doom, and GI: Anvil of Victory are not year-one or year-two work.
- No accounts, no internet matchmaking, no hosted server. A room code on the LAN is the full identity story, and LAN play is trusted-party convenience with no confidentiality guarantee.
- No shipped Avalon Hill art, scans, board layouts, or rulebook text. Reference copies stay on the owner's machine.
- No use of "Squad Leader" or "Avalon Hill" as the brand.
- No commercial use. The project stays free and GPL-3.
- No board images to the model agents. Text state only.
- No AlphaZero, MuZero, or search-based training in year one. Model-free PPO first.
- No self-play reinforcement learning on a language model in year one. A LoRA fine-tune on game traces is year-one work, and the self-play step waits for its result.
- No armor until the armor tables are sourced.

Architecture anti-goals:

- No second rules engine. One core, and each consumer uses it through a binding.
- No JavaScript rules. The browser gets the core through a binding or through a thin client, not through a port.
- No CRDT for game state. A wargame rejects moves. An authoritative host makes the decision.
- No dice out of the core. One seeded generator, one command log, one state hash.

Strategic anti-goals:

- Not a VASSAL replacement for other games.
- Not a general wargame engine in year one. The core is data-driven where that is cheap, but the year-one target is one rule set.
- Not a research project. Each feature lands because a play mode or an agent family must have it.

## 7. What success looks like at the horizon

Three checkpoints. None is guaranteed.

### 7.1 At the end of year one

Ron plays scenario 1 in a browser against a scripted opponent, against a prompted model agent, and against a tuned model agent. The action log shows the rule number for each result. A second person plays Ron on the LAN with a room code. The conformance battery gives zero failures for rules 1 to 27.

The throughput gate has a measured number. A 100 million step training run has an Elo number against the scripted bots. The boards from the generator satisfy the written look rubric.

### 7.2 At the end of year two

All 12 scenarios play. The learned agent beats each scripted bot in more than half of its games. The league runs unattended for a week without a crash. The project has its public title and a first public release.

### 7.3 At the end of year three

A stranger plays the best learned agent in a browser. A community scenario written as data runs without a code change. The owner made a decision on the gamette overlay.

If these checkpoints land, this document survives. If one of them moves late by a large margin, this document is revised, not the work.

## 8. Where this vision can break

- The official digital product scenario. Renegade Game Studios has a streamlined Squad Leader in digital playtest. If it ships, the rights holders can make the decision that a free fan project competes with it. The project's protection is the posture in bet 5 and the non-commercial stance. If a takedown request arrives, the project obeys it and renames.
- The Python throughput scenario. If the Python core cannot give the gate, year one absorbs a Rust port. The conformance battery limits the port, but the port delays training by weeks.
- The learned-agent-learns-nothing scenario. If PPO learns nothing useful at 300 million steps, year two uses the scripted bots, tuned by evolution, and the model agents as the opponents. That is a playable game, but the "learning and evolution" goal is only half met.
- The model-agent-is-too-slow scenario. A local model at 40 to 50 seconds for each decision makes a 64-decision game last an hour. If that is too slow to enjoy, model agents become test opponents only.
- The armor-tables-never-surface scenario is closed. The four tables of rule 33 are graphics on page 13 of the rulebook, and `src/sldata/tables/armor.json` holds them. The armor game waits for its rules and not for its numbers.
- The taste-test scenario. If boards from the generator do not satisfy the owner, the owner plays on the private reference layouts. The game ships with boards from the generator that are "good enough". The written rubric is what makes this scenario measurable.

## 9. How this document stays current

- Owner: Ron Dilley.
- Refresh cadence: at each year boundary in section 5, after each multi-AI review, and when a bet in section 4 is challenged.
- Causes of an update: a change to the three-year arc, a change to the principal map, or an anti-goal that moves into scope. Also a takedown request, or the selection of the public title.
- Companion documents that must stay in sync: `REQUIREMENTS.md`, `SUCCESS_CRITERIA.md`, `ARCHITECTURE.md`, `../VIBE_HISTORY.md`.

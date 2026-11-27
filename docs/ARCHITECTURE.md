# Squad_Leader_AI: Architecture

Author: Ron Dilley, with design work by Claude Fable 5.1
Date: 2026-09-07, last updated 2026-10-28
Status: v0.4, the design of the tree as built on 2026-10-28
Companion documents: `VISION.md` (direction), `REQUIREMENTS.md` (the requirements with IDs), `SUCCESS_CRITERIA.md` (the gates), `2026-09-07_Squad_Leader_Digital_Edition_Research.md` (the evidence), `../tasks/todo.md` (the build slices)

<!-- AI review 20260907-163721 (gemini, xai, openai). The changes: the decision frame, the exact lattice, the two-part LOS, and the command list for rules 1 to 21. Also the sub-step table, the SR-10 control, the throughput gate after slice 3, and Appendix B. Each changed section has its own note. -->

This document explains the cause of each design decision. The research did the work of finding what the field settled and where it did not. This document selects answers in those open spaces and constrains the build. If you are about to write code, read this first.

Each section states one decision, the alternative, the cause, where the decision breaks, and the mitigation. Mermaid diagrams support the prose. They do not replace it.

## 1. The shape of the system

Six consumers use the rules engine, and no human is in most of them. That is what makes this system different from a generic digital board game.

- The browser client shows a human a view.
- The desktop windows show a human a view. The 2D window (`slwindow`) and the 3D window (`slwindow3d`) are two front ends of one consumer. The 3D window is the front end that the owner uses.
- The local host owns the game and applies commands.
- The trainer plays millions of headless games.
- The model agent harness turns a game view into text and a text answer into a command.
- The replay tool runs a command log again and compares hashes.

Three more parts carry games and do not add a consumer. The game farm (`slfarm`, section 8.3) plays scripted games and PPO environments on four Linux hosts. The collector (`slcollect`, section 8.1) gets the save files of played games and plays each one again through the core. The launcher of the package starts a window and a host.

Each consumer would drift from the others if it had its own copy of a rule. So there is one core, and each consumer applies a rule only through it.

The second thing that shapes the system is that the core must be fast for reinforcement learning on one workstation. That sets the language decision, the geometry decision, and the throughput gate. The third thing is that the game has hidden information. So the host must give each player a different view, and the client must not hold the full state.

```mermaid
flowchart TB
    Client[Browser client]
    Window2D[2D window]
    Window3D[3D window]
    Launcher[Launcher]
    Host[Local host]
    Core[Rules core]
    Data[Rules data and scenarios]
    Trainer[RL trainer]
    Farm[Game farm]
    Harness[Model agent harness]
    Replay[Replay tool]
    Collector[Collector]
    Provider[Model providers local and SaaS]
    Runs[Run artifacts]
    Launcher --> Window3D
    Launcher --> Window2D
    Client --> Host
    Window2D --> Host
    Window3D --> Host
    Host --> Core
    Core --> Data
    Trainer --> Core
    Trainer --> Farm
    Farm --> Core
    Harness --> Core
    Harness --> Provider
    Replay --> Core
    Launcher --> Collector
    Collector --> Core
    Host --> Runs
    Trainer --> Runs
    Harness --> Runs
```

The core is a Python package with no input, no output, no network, and no file access. It gets a state and a command. It gives a new state and a list of events, and a second call gives the hash. It also gives the legal command list for a state, as a decision frame (section 3.4).

The host, the trainer, the harness, the replay tool, the farm, and the collector are Python packages that import the core. The browser client is TypeScript, and it communicates with the host on a WebSocket. The two windows are Python, and they use the same WebSocket protocol. The providers are HTTP endpoints.

## 2. One core with no input or output

The decision: the rules live in one Python package, `slcore`, that has no side effects. It does not read files, roll dice from the system clock, open sockets, or print. It has three public functions: `legal_commands(state)`, `apply(state, command, frame)`, and `hash_state(state)`.

The three functions are methods of the class `Engine` in `slcore/engine.py`. An engine holds one scenario, its board, its tables, and its line of sight table, so the three calls do not load these again. `Engine.new_game(seed, switches)` gives the first state, and `Engine.replay` applies a payload list and gives the hash after each command.

`slcore/api.py` is the public surface of the core. Its table `SURFACE` names each submodule and each name that a consumer may read: the engine, the data types, the per-player view, the seeded generator, the lattice, and the rule helpers that the odds read. `tests/arch/test_core_api.py` holds each import of `slcore` outside the core to that table. A Rust port must give each name of the table with the same behaviour (AR-05).

The alternative: a rules engine in the browser (boardgame.io or a TypeScript port) and a second engine in Python for training. The research rejected this (RV-3 section 4.3). Two engines drift. Also, boardgame.io keeps its state and random generator in JavaScript, so Python cannot share them.

Why this is right, first cause: each consumer gets the same rule, the same dice, and the same hash. The conformance corpus (TR-01) runs one time against one package, and each consumer inherits the result. Second cause: a package with no side effects is the only thing that ports to Rust with a bounded test. The port is a new package with the same three functions and the same corpus (AR-05).

Where it breaks: CPython is 10 to 200 times slower than compiled code on compute-bound work (RV-7 section 1.3). The trainer must have 3,500 environment steps/s (NFR-01).

Mitigation: the throughput gate is measured at the end of slice 3, on the complete scenario 1, before the rules for the subsequent scenarios are written. The design below keeps the per-step work small: a cached LOS table, integer arithmetic, and a legal-command list built from a small set of candidate units. If the gate is not satisfied, the core moves to Rust with PyO3 and wasm-bindgen bindings as its own milestone (section 14).

## 3. The command model and the phase state machine

The decision: the unit of play is a command. A command is one player intent: an action, the units it applies to, and a target, or an end-phase marker. The core gives the full legal command list for the active player in the current phase and sub-step.

The active player selects one. The core applies it and gives events. Dice results are events, not commands.

This is the load-bearing design of the project. The three reviewers of the first pass and the three reviewers of the second pass converged on it: legal-command generation is the critical path. The mask for the trainer, the list for the model agents, and the click targets for the client are the same list.

The internal shape of the list is a tree: action, then unit or units, then target. The trainer's composed action head walks that tree (section 9.2). The client and the model agents get the flat enumeration of the tree from the decision frame (section 3.4). The flat sequence is a view of the tree, and nothing stores a position in it.

<!-- AI review 20260907-163721: gemini, the hierarchical command tree -->

### 3.1 What one command is, phase by phase

<!-- AI review 20260907-163721: gemini and openai, portage. openai, set up, the two-player windows, predesignation, the track return, and the close combat allocation. -->

The list below covers rules 1 to 27, which is scenario 1 (v0.1) and scenarios 2 and 3A (v0.3). The last item gives the commands of the armor rules 28 to 41. `slcore/commands.py` holds the full list of actions (`ACTIONS`), and `slcore/actions.py` holds one handler for each action.

- Set Up Phase (rule 21.2): `place(unit, hex)` for each unit in the side's set up area, in the sequence the scenario gives. `place_weapon(weapon, unit)` gives a support weapon to a unit in the same hex. `end_setup`. The scenario file says which side sets up first.
- Rally Phase (rule 4.1): the two players have a command window. The phasing player goes first, then the defender. This sequence is a project ruling, because rule 4.1 gives no sequence. It is recorded in the project rulings data (section 6).
- Rally Phase commands: `repair(weapon)` (rule 18.2), `rally(unit)` (rule 14.1), `end_phase`. The dice results are events. The core removes DM counters (rule 14.6) as an automatic step.
- Prep Fire Phase (rule 4.2): fire is a short sequence of commands. `group_add(unit, target_hex)` adds a unit to the fire group that aims at a target hex. `group_add_weapon(unit, weapon, target_hex)` adds a support weapon. `group_leader(leader)` adds or removes the leader modifier for the group, because the Q and A for rule 15.1 gives the player that choice for fire groups.
- Prep Fire Phase, resolution: `group_fire()` resolves the group on the Infantry Fire Table and emits the events. `end_phase` closes the phase. A fire group is open only while its members are in the same or adjacent hexes (rule 8.6). Smoke placement (rule 24.3) is a v0.3 command.
- Predesignation (rule 8.7): the core has the basic method only. `group_fire()` resolves one group, and the player then forms the next group. The optional method of rule 8.7, where the player forms all groups before the first one fires, has no command at this time.
- Movement Phase (rule 4.3): `move(unit, hex)` moves one hex and spends movement factors. `stack_move(leader, units, hex)` moves a leader with squads for the leader bonus (rule 5.44). `end_phase` closes the phase.
- Movement Phase, portage: `pickup(unit, weapon)` and `drop(unit, weapon)` are legal at each point of a move, with the portage cost of the Support Weapons Chart (rules 5.7 to 5.72). The core records the track of each moved unit: the sequence of hexes where it spent movement factors (rule 16.4).
- Movement Phase, rules 23 and 27: `place_demo(unit, weapon, hex)` puts a demolition charge on a hex next to the unit (rule 23.3). `sewer_move(units, entrance)` moves a stack down one sewer entrance and up at a second one in three hexes (rule 27.2). `sewer_return(hex)` is the window of the opposing player for a stack that was lost (rule 27.22).
- Prep Fire Phase, rule 24: `place_smoke(unit, hex)` puts one smoke counter in or next to the hex of an assault engineer squad, as the first action of the phase (rule 24.3).
- Fire phases, rule 22: `ft_fire(unit, weapon, target_hex)` is one flamethrower attack. It is its own command and not a fire group, because rule 22.3 says a flamethrower does not fire with other units.
- Advancing Fire Phase, rule 23: `explode_demo(charge)` explodes one operable charge when the owner selects it (rule 23.4).
- Set Up Phase, rule 25.6: `place_concealment(hex)` puts one of the counters the scenario gives on a woods hex or a building hex of the side's set up area.
- Defensive Fire Phase (rule 4.4): the defender is active. `track_return(units, hex)` moves a set of units that moved through the target hex back to that hex on their track (rules 16.1 and 16.3). Then the fire commands apply, and the target hex is the return hex.
- Defensive Fire Phase, after each group: the core moves the units that did not break to their end position, or to the next track hex the defender names. Units that did not move are targets where they stand (rule 16.2). `end_phase`. The core removes the track records as an automatic step.
- Advancing Fire Phase (rule 4.5): the same fire commands. The core applies the moved-fire halving (rule 9.3) and the portage limit on support weapon fire (rule 5.74). The core removes the Prep Fire counters as an automatic step.
- Rout Phase (rule 4.6): the two players have a command window, the phasing player first, as rule 4.6 says. `rout(unit, hex)` for each hex of the rout path, with the legal destinations from rules 13.4 to 13.47. `stay(unit)` for a broken unit in cover and not adjacent to an enemy. `end_phase`. The core removes a broken unit with no legal path (rule 13.47), and the event names the rule.
- Advance Phase (rule 4.7): `advance(unit, hex)` one hex, with the portage limit of rule 5.73. `end_phase`.
- Close Combat Phase (rule 4.8): the two players have a declaration window, the phasing player first, then the defender. `cc_attack(attacking_units, defending_units, leader)` declares one attack. Each unit attacks one time in the phase (rule 20.4). The leader modifier applies to one declared attack for each leader (rule 20.6). `end_phase` closes the window.
- Close Combat Phase, resolution: when the two windows close, the core resolves each attack in the declared sequence, and the effects apply at the same time (rule 20.2). The declaration sequence between the players is a project ruling.
- Rules 28 to 41, the armor game (`r28_vehicles.py` to `r38_fate.py`): `vehicle_move`, `vehicle_pivot`, `afv_fire`, `afv_mg`, `at_fire`, `afv_attack`, `cc_afv`, `afv_repair`, `push_wreck`, `afv_smoke`, and `afv_dischargers`. `board` puts a unit on a vehicle, and `debark` removes it (rule 31). A unit boards or debarks one time in each Movement Phase (PR-55). `push_out` moves the infantry below an enemy vehicle to one side (rule 35.8, PR-51).

Three state fields of the armor game are in the state document only when they are set. Thus the hash of a game that does not use them stays the same:

- An overrun (rule 35) is declared when the vehicle enters the hex, and it resolves at the end of the Defensive Fire Phase that follows (PR-54). The vehicle field `overrun_hex` holds the declaration. The automatic step `resolve_overruns` resolves it before the push out of PR-51.
- A passenger debarks only when its vehicle has the two movement points of rule 31.3 left. The unit field `rode` holds the board or the debark until the end of the player turn (PR-55).
- Portage is in half points, because rule 37.35 gives the panzerfaust half the cost of a machine gun. `UnitType.portage_squad_halves` and `free_portage_halves` are the fields to read. `r06_stacking.hex_load` gives full points, because rule 6.1 gives its limit in full points, and it rounds up.

The alternative: a free-form action description that the engine parses. That is what makes language model agents give invalid moves (RV-6 section 1.5). With a closed list, a model agent selects an ID, and an invalid answer is not possible by construction.

Where it breaks: the list can be long. In a Movement Phase with 20 units and 6 neighbors each, the list has 120 move commands plus the pickup, drop, and end-phase commands. That is not a problem for a model agent, because each command is about 12 tokens (RV-6 section 7). It is not a problem for a trainer with a composed action head (RV-5 section 2). It is a problem if the core builds LOS or paths again for each candidate.

Mitigation: the LOS table is cached (section 5). Movement candidates come from the six neighbors and the movement factors that remain. The list for a sub-step is built one time and used again until a command changes the state.

### 3.2 The state machine

The phases follow the "Advanced Sequence of Play" on page 41 of the rules. Each phase has a numbered list of sub-steps with rule pointers, and the core runs them in that sequence. Some sub-steps are automatic. Some open a command window. The core records the phase, the sub-step, and the active player in the state, and the three are part of the hash.

```mermaid
flowchart LR
    Setup[Set up] --> Rally[Rally]
    Rally --> Prep[Prep Fire]
    Prep --> Move[Movement]
    Move --> Def[Defensive Fire]
    Def --> Adv[Advancing Fire]
    Adv --> Rout[Rout]
    Rout --> Advance[Advance]
    Advance --> CC[Close Combat]
    CC --> Swap[Change attacker]
    Swap --> Rally
```

The sub-step table below is the state machine for year one, in the project's own words. Each row names the rule that the sub-step applies. Rows for the armor rules, artillery, night, wire, and fire (Game Sets II and III) are not in the table, and the core adds them with those rules. <!-- AI review 20260907-163721: xai and openai, the sub-step table -->

| Phase | Sub-step | Kind | Rule | Tier |
|---|---|---|---|---|
| Rally | Repair malfunctioning support weapons | Window, phasing player then defender | 18.2 | v0.1 |
| Rally | Rally broken units | Window, same | 14.1 | v0.1 |
| Rally | Remove DM counters | Automatic | 14.6 | v0.1 |
| Prep Fire | Remove the smoke of the phasing player | Automatic | 24.8 | v0.3 |
| Prep Fire | Put new smoke | Window with a condition, phasing player | 24.3 | v0.3 |
| Prep Fire | Fire at enemy units | Window, phasing player | 4.2, 8 to 11 | v0.1 |
| Prep Fire | Place Prep Fire counters | Automatic | 4.2 | v0.1 |
| Movement | Bring a sewer stack up from the sewer | Window with a condition, defender | 27.22 | v0.3 |
| Movement | Move units that did not prep fire, place charges, go down a sewer | Window, phasing player | 4.3, 5, 6, 23.3, 27.2 | v0.1, v0.3 |
| Movement | Concealment for sewer movers with no enemy near | Automatic | 27.5 | v0.3 |
| Defensive Fire | Fire at enemy units, with track returns | Window, defender | 16.1 to 16.5 | v0.1 |
| Defensive Fire | Say which demolition charges are operable | Automatic | 23.3 | v0.3 |
| Defensive Fire | Remove track records | Automatic | 16.3 | v0.1 |
| Defensive Fire | Remove concealment next to unbroken enemies | Automatic | 25.4 | v0.3 |
| Advancing Fire | Explode the demolition charges that are operable | Window with a condition, phasing player | 23.4 | v0.3 |
| Advancing Fire | Fire moved units at half firepower | Window, phasing player | 4.5, 9.3 | v0.1 |
| Advancing Fire | Remove Prep Fire counters | Automatic | 4.5 | v0.1 |
| Rout | Broken units rout to cover | Window, phasing player then defender | 4.6, 13.4 | v0.1 |
| Advance | Move unbroken infantry one hex | Window, phasing player | 4.7, 5.73 | v0.1 |
| Advance | Remove concealment next to unbroken enemies | Automatic | 25.4 | v0.3 |
| Close Combat | Declare attacks | Window, phasing player then defender | 20.4, 20.6 | v0.1 |
| Close Combat | Resolve attacks | Automatic | 20.2, 20.3 | v0.1 |
| Close Combat | Concealment on units that did not fire and did not move | Automatic | 25.3 | v0.3 |
| End of turn | Change the attacker, move the turn record forward | Automatic | 4.9 | v0.1 |

Two properties of the table need a word.

A window with a condition opens only when its rule has a decision for that player. Smoke, a demolition charge, and a stack in the sewer are rare. A window that is always open puts an empty decision in each player turn. The condition is part of the state machine, so the core and a replay agree on which windows a game had.

The removal of a concealment counter by rule 25.4 is not a sub-step when a unit moves or fires. Rule 25.4 says immediately, so the counter comes off in that command. The sub-steps above are the second half of that rule. A counter comes off at the end of the Defensive Fire Phase and the Advance Phase when an unbroken enemy is next to it. Rule 25.5 is the cause of the delay: the counter stays when Defensive Fire eliminated or broke that enemy.

The optional rules are switches in the scenario (FR-08). The switch values are in the hash, so a replay with incorrect switches stops at the first command.

Optional rule 16 is a sub-state of the Movement Phase. After each moved stack ends its move, the defender gets a fire window against that stack. The Defensive Fire Phase then has no track returns. The basic method of rule 4.4 and rule 16.1 is a phase after movement with track returns, and the core has the basic method as its default.

<!-- AI review 20260907-163721: gemini said the basic method misrepresents the rules. It does not. Rule 4.4 and rule 16.1 give the basic method as a phase after movement, and optional rule 16 is the interleaved method. -->

### 3.3 Rule IDs in code

The decision: the rule ID is in the module name, in a constant, in the docstring, and in each event. The code uses these conventions:

- One module for each rule section, with the section number in its name: `rules/r08_fire.py` holds rules 8 and 9, and `rules/r35_overrun.py` holds rule 35.
- Each rule ID is a module constant, for example `RULE_9_1 = "9.1"` in `r08_fire.py`. A function has a plain name, such as `group_firepower`, and its docstring names the rules it applies.
- The first field of each `Event` is the rule ID that produced it. A data row and a project ruling also hold the rule ID they extend.

Each event that the core emits has the rule IDs that produced it. The action log (FR-06) is the event list with the dice and the modifiers. A player reads "KIA, rule 10.6, IFT column 16, roll 4, modifiers +3 stone building (11.1), -2 leader (15.2)" and finds each number in the rulebook. This is the community signal from RV-8 as a data structure.

Why: a player who is not sure of a result must find the rule. A test that does not pass must name the rule it tests. The conformance corpus (TR-01) and the action log read the same rule IDs.

The alternative: the rule ID in the function name, as `rule_9_1_point_blank`. The first design proposed it. One function frequently applies more than one rule, and a rule frequently has more than one function. A name with one rule ID is then incorrect or too long.

Where it breaks: nothing stops a function that applies a rule with no constant and no event. A rule with no event is not in the log.

Mitigation: the conformance corpus has cases for each rule family, and each case names the rule. A case can name an event of a rule ID that must occur, or one that must not occur (`tests/conformance/test_conformance.py`). `tests/core/test_action_table.py` holds the table of handlers to the list of actions.

### 3.4 The decision frame and the command identity

<!-- AI review 20260907-163721: gemini and openai. A command ID as a list index cannot serve replay, traces, and training. -->

The decision: the core gives the legal commands as a decision frame. A frame has the frame ID, the active player, the phase and sub-step, and the list of legal commands. Each legal command has a canonical payload and a command ID. The payload is a small record: the action name, the unit IDs in sorted sequence, the target hex, the weapon ID, and the other fields of that action.

The command ID is the first 64 bits of the SHA-256 hash of the payload in its canonical byte form (JSON with sorted keys and no white space).

The frame ID has two layers. In the core, the frame ID is the state hash of the state that the frame came from (`Engine._build_frame`). `Engine.apply` compares the frame ID with the hash of the state, and it refuses a stale frame. The trainer, the agents, and the replay use this layer.

In the host, the frame ID is an opaque token of 32 hex digits (`secrets.token_hex` in `slhost/server.py`). The host makes a new token for each connection when the state hash changes, and it keeps the state hash next to the token. A client does not see the state hash (DR-04, section 8).

Unit IDs are stable for the game. Each counter gets its ID from its position in the scenario force list, not from a list position at run time. Hex IDs are the grid labels (for example `K5`) with a board prefix in a composition (section 7).

The command log stores the payload (DR-04). A replay reads each payload, builds the frame for the current state, and finds the command by ID. The trace record stores the payload, the ID, and the legal IDs (DR-08). The trainer's mask maps each head choice to a payload and then to an ID. The client sends the token of its frame and the command ID (section 8). No consumer stores a position in the flat list.

The alternative: the command ID is an index into the legal list the host sent, as the v0.1 design said. That is one integer, and it is cheap. It breaks when the list sequence changes.

A code change can sort the list in a different sequence. A Rust port can iterate in a different sequence, and a new candidate rule can add an entry. Each of these puts the stored index on a different command, so the replay, the traces, and the mask do not agree with the log.

Why this is right, first cause: the payload names what the player did in game terms, so it is stable across list sequences, code versions, and languages. Second cause: the ID is short, so a model agent selects a short token, and the harness maps it back to the payload. Third cause: the host, the trainer, the harness, the trace writer, and the replay tool use the same frame, so there is one artifact to test (TC-38).

Where it breaks: a canonical form must be the same in Python, in Rust, and in the browser. SHA-256 is available in the three, and a sorted-key JSON encoder with no white space is a small function. The client does not calculate IDs. It receives them from the host, so the client needs no encoder.

Mitigation: a golden test holds ten payloads with their IDs. The Rust port runs the same test. TC-38 shuffles the legal list and replays a game, and the hash sequence must agree.

## 4. State, views, and secrecy

The decision: the host keeps one authoritative state. For each outbound message the host calculates a view for one player. A view holds the player's own units in full, the opponent's units that the rules let the player see, and opaque tokens for concealed stacks.

The client, the model agent harness, and the trace writer see views only. The host calculates the state hash. The client sends intents only.

The alternative: send the full state to each client and hide units in the client. The first multi-AI review named the problem: a player reads the network messages or the browser memory (consolidated review, security 1).

Why this is right, first cause: concealment is a rule, not a display setting. Rule 25.2 says a concealed stack "must be treated as if it were an opposing squad until proven otherwise". Only a view can enforce that.

Second cause: the prompt to a model agent and the trace for the tuned model must not leak the opponent's hidden units. If they do, the model gets training data it must not have (SR-09, SR-10).

How a view works, as slice 7 built it: each concealment counter has its own identity, and no second counter of a game has it. The owner's view carries the counter, the units below it, and the units themselves. The opponent's view carries the counter, its hex, and how many counters are in that hex, and no unit of that hex at all.

The identity is the same number for the two players, and that is not a disclosure. A counter is a piece on the board that the two players see and follow from turn to turn, which is what the number does. The number does not hold what is below the counter.

Dummy stacks (rule 25.7) are counters with no units below them, and the opponent's view cannot tell them apart. The test for that is simple: the token of a dummy and the token of a full stack have the same fields and the same values. Hidden Initial Placement (rule 42, Scale) is the same mechanism with no counter shown at all.

The cost of a view has three cases. When no unit is concealed, the view is a copy of the unit list with the viewer's side identified. Its cost is linear in the unit count. Scenario 1 has no concealment, so the trainer in v0.1 pays this case only. When some stacks are concealed, the view replaces each concealed stack with its token. The cost is linear in the unit count plus the token map.

When the scenario has hidden placement, the view drops the hidden units and the cost is the same as the second case. The benchmark of NFR-01 includes the view build, so TC-09 measures the cost. The core does not keep a view between calls, because the core has no state of its own. The host keeps the last legal list of each seat and the last spectator view. It uses them again until a command changes the state.

The host message is that view for one seat. An unjoined socket gets no frame. In a LAN room the legal list goes to the seat that acts. The idle seat gets an empty list. Hot seat keeps the list.

The log tail omits a line that names a unit the viewer cannot see. A hidden unit is not in the other player's view. Each viewer has its own log stream, and `seq` counts the lines of that stream with no gap. Hot seat reads the stream of the side on the screen. So a side does not keep the lines of the other side in its history.

<!-- AI review 20260907-163721: xai, the view cost model -->

Where it breaks: a view for each outbound message costs time in the trainer, which plays millions of games with no hidden information problem in self-play.

Mitigation: the trainer uses the view function too, because the policy must learn from what a player can see. Hot seat play on one screen cannot stop the local user from a look at the other player's turn. The host gives one view at a time, so the client does not hold the two.

## 5. Determinism, geometry, and line of sight

<!-- AI review 20260907-163721: gemini and openai. The 1,000 by 866 lattice was an approximation with an assertion. The cache stored one byte for an unordered pair, and FR-28 said ordered pairs. -->

The decision has four parts. One seeded random generator lives in the core. The command log with a hash after each command is the game. All rules arithmetic is integer. The hex geometry lives on an exact integer lattice, and line of sight is a segment-against-polygon test with integer cross products. The static part of the test is cached for each board, and a rule evaluator applies the context at play time.

The alternative for dice: the host or the client rolls. Then a replay cannot reproduce the game, and a trainer cannot reproduce a defect.

The alternative for geometry: float coordinates with a hex-cell algorithm (Red Blob, RV-3 section 5.1). The first multi-AI review found that float geometry and an integer-only rule (NFR-05) do not agree, and proposed floats in the LOS function. The project rejected that. It cannot prove that a Python float path and a future Rust or WebAssembly path agree bit for bit.

The second alternative, from the second review: cube coordinates, which give the hexes that a line between two centers goes through. Not used. Rule 7.1 tests a thread against the terrain shapes printed in the hexes, and cube coordinates have no sub-hex shapes. A building that fills half of a hex stops some threads through that hex and not others.

Why the lattice is right: the board rule is a thread from center dot to center dot that touches printed terrain (rule 7.1). VASL reproduces this with a per-pixel raster walk (RV-3 section 5.2). A vector version gives the same answer with less data. Each hex holds terrain polygons, and the LOS test asks if the segment goes through a polygon that blocks.

The lattice is exact. A hex with a side of 2 units has its center and its six vertices at lattice points. At a lattice point, x is an integer, and y is an integer multiple of the square root of three. The core stores y as that integer and does not multiply it out. A cross product of two such vectors is an integer times the square root of three, so its sign is exact. A dot product and a squared distance are integers.

The segment tests use cross products only, so the LOS test has no rounding and no platform dependence. A finer polygon scale multiplies the two coordinates by the same integer.

The v0.1 design scaled the hex height to 866 units as an approximation. The defect was not distance, which the lattice does not measure. The defect was that a scaled integer y can put a thread on the incorrect side of a polygon vertex. The exact lattice removes that. The conformance corpus stays the arbiter. Each LOS example in the rulebook (rules 7.4, 7.7, 17.5, the LOS course on page 30) becomes a case.

Why the cache is right, and what it holds: a board has 346 hexes with its half hexes, so 59,685 unordered pairs. At board load the core calculates the thread for each pair: the sequence of hexes the segment goes through, the static result (clear or blocked by terrain), and the hexes with a hindrance-capable terrain (wheat). A segment along a hexside gets two threads, one for each side, because rule 17.7 gives the firer the choice. The static table is symmetric, so it is unordered (FR-28).

The rule evaluator runs at play time with the firer as the context. It gets the static thread and applies the firer's hexside choice. It adds the dynamic hindrances (smoke, vehicles, fire), and it walks the thread in the firer's direction for machine gun penetration (rule 17). So a LOS question is one table lookup plus a walk along a short list. This is the largest single lever on the throughput gate.

What the first measurement showed: the static thread table is necessary and not sufficient. The rule evaluator on top of it ran for each pair on each frame, and it costs more than the table lookup. The core memoizes the evaluator result for a pair while no smoke and no vehicle is on the board, which is each state of v0.1. The lesson file records the profile and the three other costs it found.

The random generator: the core uses xoshiro128** with a 32-bit state. It has a CC0 reference in C, a direct port in Python with a 32-bit mask, and a direct port in JavaScript with `Math.imul` (RV-7 section 5.2). If the core moves to Rust, the same generator moves with it. A golden-vector test (one seed, the first 1,000 outputs) proves agreement across languages.

Where it breaks: an exact lattice can put a segment through a polygon vertex or along a polygon edge. The result is then a policy, not an accident, and the rules have an answer for the two cases.

Rule 43 gives each hex a height, and the core applies the rule as one integer test. The height of the thread above a hex is a linear interpolation between the two ends. The test compares that height with the top of the hex.

A hex with a symbol that stops the sight stops the thread when its top reaches the thread. That is the height advantage of rule 43.4. A bare hill hex stops the thread only when its level is above the thread, which is rule 43.7. The blind hexes of rules 43.6 and 43.62 come from the end with the height advantage. That keeps rule 43.8: when A sees B, B sees A.

`r43_elevation.py` holds this reading. It says nothing when each hex of the thread is on ground level, so the city boards keep one reading of rule 7.

Rule 7.1 says the LOS is blocked when the obstacle shows on the two sides of the string. So a thread that only touches a polygon vertex, or runs along a polygon edge, is not blocked. Rule 17.7 says a LOS along a hexside goes through one of the two hexes at the firer's choice. The core encodes the two as the tie break (slice 1, `tests/los/`). Rule 43 (hills and blind hexes, Scale) adds elevation to the polygon test on the same lattice.

## 6. Rules as data

The decision: the tables, the counters, the scenarios, and the boards are data files in the project's own layout. The Q and A rulings are data with the rule number they refer to. The conformance corpus is JSON. The rule functions are the only code, and each one reads its numbers from the data.

The project's own rulings are a second data file, apart from the official rulings. A project ruling fills a gap that the rules text leaves open, names the rule it extends, and says the cause. The first two are the Rally Phase sequence and the Close Combat declaration sequence between the players (section 3.1). <!-- AI review 20260907-163721: the referee found the Rally Phase gap -->

The alternative: numbers in code. That makes a gamette overlay (Cross of Iron, vNext) a code rewrite, and it hides the provenance of each number.

Why this is right, first cause: the legal analysis (RV-4 section 3) says tables are a method of operation and are safe to reproduce. It says to reproduce them as your own data in your own layout. A data file with a provenance note is that layout. An example note: "IFT, from the data card image, RV-1 section 7.1, compared against the rulebook example in 10.6".

Second cause: the conformance corpus cites the rule text for each case. A case that names a data row and a rule function is a case a future session can audit.

The victory evaluator (FR-14) is a rule function with a data contract. A scenario file lists its victory conditions as typed records: control of named buildings or zones, units exited from an edge, casualties as a fraction, and a turn limit. The core tests the conditions at the end of the last player turn, and it tests a sudden-death condition at the end of each phase. The result is an event with the winner or a draw, and one line for each condition with its count and its threshold. The action log shows that event as the cause of the result.

Why the evaluator is a typed record: a scenario names a building by its group, not by a hex. The evaluator maps a group to the building of its set up area (slice 3). Thus one scenario file works on each board that the generator makes. The host reads the same records for the objectives of each frame (`slhost/objectives.py`).

The alternative: a victory function in code for each scenario. Each new scenario is then code, and the library of 12 generated scenarios (section 7.3) is not possible.

Where it breaks: a card can say a sentence that the record does not say. The L03 card said "each wants the other end", but only the German side won by a building (2026-10-17).

Mitigation: the card text comes from the same record (`slcards`, section 7.4). The owner's rule is that each sentence of a card agrees with the rules of the scenario. Each sentence gets a check against the code before a scenario goes into the library.

<!-- AI review 20260907-163721: openai, the victory evaluator contract -->

The rule-by-scenario matrix, from the "Rules Introduced" line of each card (RV-2 section 3):

| Scenario | Rules | Tables | Counter types | Tier |
|---|---|---|---|---|
| 1, The Guards Counterattack | 1 to 21 | IFT, Close Combat, Support Weapons, movement costs, terrain modifiers | squads, leaders, LMG, MMG, HMG, markers | v0.1 |
| 2, The Tractor Works | 22 to 26 added | the same, plus flamethrower and demolition charge rows, smoke | plus flamethrower, demolition charge, smoke, concealment | v0.3 |
| 3A, The Streets of Stalingrad with sewers | 27 added | the same, plus the sewer roll | plus the sewer entrance flags | v0.3 |
| 3B, with armor | 28 to 41 added | To Hit, AFV Kill, hit modifiers, vehicle movement, immobilize numbers | vehicles, crews, wrecks, malfunction markers | Built for rules 28 to 41. The project scenario `s04_armor_probe` plays them, and no 3B file is in the tree |

The armor rules are built (slice 18). `sldata/tables/armor.json` holds the four tables of rule 33, and `vehicle_movement.json` holds the vehicle movement chart. An earlier note said that the armor tables were not available. That was incorrect: the tables are graphics on page 13 of the rulebook, and a search of the text layer did not find them (slice 17).

Where it breaks: a table that is a graphic in the source has no text to compare with. A transcription with an incorrect digit is a defect that no text search finds.

Mitigation: `tests/conformance/test_armor_tables.py` gives each row of each table a second time, so an incorrect cell stops one test. The 82 cases of `rules_28_41.json` test the rules that read the tables. A scenario file lists its rule IDs (FR-19). The core refuses a scenario that uses a rule that is not in the build, with a message that names the rule.

## 7. Boards, the generator, and the two modes

The decision: a board is a data structure of 33 by 10 hexes with half hexes on all four edges (FR-23). Each hex holds terrain type, elevation, building type and dimension, hexside features, and the flags for sewers and stairs (DR-03). Each hex also holds its terrain polygons on the lattice, for LOS. The generator makes a board of one type from a seed, with the geomorphic edge constraints (FR-24). A reference-mode loader reads one of the four 1977 layouts from `background/reference/`, which git does not record.

The generator pipeline has five passes:

1. Edge pass: set the boundary hexes to the geomorphic constants. The woods half hexes are at F, H, J, L, V, X, Z, and BB on the long edges. The roads are at I, Q, and Y on the long edges and at row 5/6 on the short edges.
2. Structure pass: place the type's large features. A city gets a road grid and building blocks. A hills board gets one or two hill masses in three terraced levels. A village gets a cluster of stone buildings around a road junction and one low hill. A rural board gets grain fields and hedgerows.
3. Fill pass: Wave Function Collapse with adjacency rules from a small set of hand-written tiles (RV-7 section 6.1), constrained by passes 1 and 2.
4. Polygon pass: give each hex its terrain polygons, with the vertices on the lattice. Buildings get their footprint shapes (long, L, T, plus). Woods get an irregular blob. Hills get a contour polygon for each level.
5. Style pass: the renderers make the polygons with flat fills, ink lines, and the shapes of each terrain. This pass is not in the generator. `slwindow/render.py` makes the board picture for the two windows. `client/src/board/render.ts` makes it in the browser with the canvas API and no other library.

The style record of FR-26 gives the density of each feature, and `STYLE_DEFAULTS` holds the default style of each type.

A set up area is a zone: a predicate on the hexes of the board (FR-21). Three zones cover the forms that RV-2 section 6 reads off the cards.

`stone_building` gives one building of a band, by rank. The band is a range of columns, a range of rows, or the two. A `near` parameter adds a distance: the building must be at that count of hexes or less from a stone building of a different band.

`columns` gives each hex of a column band, and `edge` gives each hex in a depth from one named edge. The last two also apply a terrain test: a terrain type, a road flag, or one hill level.

Two rules hold for each board type. First, the outer ring of the board stays on ground level. A seam between two levels is a step that no rule describes, and two boards must connect along an edge. Second, no slope is steeper than one level. A step of two levels is a cliff hexside (rule 44.1), and an impassable hexside can cut a board in two.

Each generated board has a parameter record: the seed, the generator version, the board type, the style parameters, and the zone constraints it was built with.

Orchards and landmarks (2026-10-17) come after the polygon pass, and only when the record names them. The style `orchards` gives the count of orchards on the board. Each orchard is a row of three to five open hexes adjacent to a road. The orchard pass has a random state of its own, so the other hexes of the board do not change.

A record can also have `landmarks`. A mill goes on a stone building, and a windmill goes on a wooden building. Each goes on the building of its rank in its band, in the order that a `stone_building` set up area uses. The default of `orchards` is 0, and a record with no `landmarks` writes no key. Thus each record from before builds the same board, and the generator version stays 8.

The two passes are `slboards.generator.orchard_pass` and `landmark_pass`.

The rules come from two project rulings. PR-56: an orchard has the effects of a wheatfield of rule 44.2 in each season. PR-57: a mill is a stone building and a windmill is a wooden building. Thus a landmark changes only the picture and the name on the card.

Why: on 2026-10-17 the owner told the project to put orchards, mills, and windmills on the boards. The causes were the library slot L05 (an orchard village), and a card that can name a landmark. The printed boards have orchards, and rules 1 to 44 give them no rule.

The core has the wheatfield effects at this time, so PR-56 uses them. A mill with rules of its own would change the play that the balance of each scenario measured. Thus PR-57 gives a mill the rules of its building.

The alternative: an orchard as woods. Its trees stand in rows with space between them, so they hide a unit and give no cover that a woods hex gives (PR-56).

Where it breaks: an orchard is a new terrain type, so each consumer that lists the terrain types must have it. The learned agent puts an orchard in the plane of the wheatfield, because the two have the same rules. Thus each net from before keeps the shape of its input.

Generator version 4 adds the four board types, the style record, the hill levels, and the wall and hedge hexsides. An older record with a `building_density` field continues to build its board, because that field is the `buildings` style. Version 5 sets each seam hex of FR-24, and version 6 adds the cliff hexsides of rule 44.1.

Version 7 (slice 19) gives the east to west road one row index for each column, and `connect_roads` attaches each road entry of FR-24 to the road network. Version 8 adds the road hexsides of PR-50. A board document lists the directions of the road out of each road hex (`road_sides`). A vehicle pays the road rate only across such a hexside.

Version 8 changes no terrain. It seeds the random state as version 7 does (`SEED_VERSION`), so each seed that a scenario names builds the same hexes. A record of version 7 builds its board again with no road hexsides.

A run artifact stores the record. A future session regenerates the board from the record and gets the same board. A change to the generator changes its version, and an earlier record names the earlier version.

<!-- AI review 20260907-163721: openai, the generator parameter record -->

### The design-your-own tools and the campaign game

`slcampaign` holds Game Set IV (FR-17). It is a consumer of the core and not a part of it.
It builds a `Scenario`, gives it to the engine, and reads the events the engine writes.

`points.py` gives each counter a force point value. The printed Point Value Chart is a
picture on the rules sheet, and the text of the rulebook does not hold its numbers. So the
project cannot transcribe it the way it transcribed the Infantry Fire Table. Open item O-08
gives that task to the owner. Until then the scale is the project's own, built from the
counter values, and it says so.

The scenario library (`library.py`) is in section 7.3.

`generator.py` is the random scenario construction. The printed method uses playing cards.
This project uses the seeded generator of the core. A game is its seed, and a scenario that
a seed cannot build again is not reproducible (NFR-04). Six steps give the board type, the
two armies, and the turn count. Three more give the victory condition, the share of the
points that goes to the attacker, and the two forces.

`build.py` puts a scenario on a board. The defender sets up first and the attacker moves
first (rule 11). The two sides start in bands of columns at the two ends of the board, with
a space between them. So no attacker starts next to a defender (rule 12). One group of the
defender holds a stone building, because the building victory conditions name a building of
the defender.

`campaign.py` is the campaign game. One leader counter holds a rank and a performance total
from one scenario to the next. The scorer reads the event log and applies rule 4.

Elan points come from a rally and from a win. They also come from directed fire that killed
a squad, and from a close combat that emptied a hex of its enemy units.

Cowardice points come from a break. They also come from a break that broke a squad in the
same hex, and from a weapon of the leader that malfunctioned. A rally roll of twelve costs
the most. Two Elan items are for an armoured fighting vehicle. The campaign table marks them
with an `awaits` field, and the scorer does not award them. The armor rules are in the core
at this time, so this mark is older than the core.

`ladder.py` is how the record chooses the next scenario. It is the project's own rule and
not a printed one. A win makes the next defence stronger and a loss makes it weaker. A floor
and a ceiling hold the result. The seed of the next scenario mixes the wins, the losses, and the
points on the personnel file. So two campaigns from one seed that go differently do not
play the same scenarios.

`run.py` plays a campaign: a sequence of scenarios from one seed, with the leader of the
personnel file in the force of the player.

Why the scenario construction uses the seeded generator: a scenario that a seed cannot build
again is not reproducible (NFR-04). A game is its seed, its switches, and its command log,
and a random scenario adds only its seed to that record.

The alternative: the printed method with a deck of playing cards. A deck is a random source
that is not in the core, so a replay cannot build the same scenario.

Where it breaks: the point scale is the project's own (O-08), so a random draw can give two
forces that are not equal in play. A random scenario also has no scenario file, so it has no
card and no briefing in the 3D window.

Mitigation: the library (section 7.3) uses the same draw with a balance search, and only a
balanced draw goes into the library.

Board composition (FR-29): a scenario puts two to four boards along long edges or short edges, and a board can turn 180 degrees. `slboards/compose.py` holds it.

The boards touch along their long edges, which stacks them from north to south. They can also touch along their short edges, which puts them end to end from west to east. Rule 3.5 makes the half hexes of the two edges into one hex. So a join costs one row or one column. Two boards of 33 by 10 give 65 by 10 side by side, or 33 by 20 stacked.

A column offset must divide by two. The lattice moves an odd column down by one unit. An offset that does not divide by two gives the second board an incorrect position, and it is not a hex grid. A board is 33 columns and a join removes one, so the offset is 32.

A turn of 180 degrees negates the two lattice coordinates about the centre of the board. On the lattice it is one form: `y` becomes `2 * (rows + 1) - y`. In hex coordinates it reads as two forms, one for each column parity.

The column count must be an odd number, or a turn does not keep the position of each column, and 33 is odd. A hexside feature moves from direction d to direction d plus three. A polygon moves point by point, so a woods hex keeps its shape and the line of sight through it does not change.

The composition is one `Board`, so the static LOS table of section 5 covers each pair, including a pair across a seam. A composition keeps its own hex names, because the core reads a hex by its position on the lattice. `compose.board_coordinate` gives the name of rule 3.5, which tells you the board a hex came from.

A seam works only when the two boards agree on it. So the edge constants of FR-24 set each hex that a seam can touch. Those hexes are the odd columns at row 0 and at the last row, and the first and the last column. A woods half hex and a road entry keep their own type, and each other seam hex is open ground. Generator version 5 is the first one that holds them.

Why: FR-29 gives the scenarios of more than one board, and the library slots L08 to L12 have two to four boards. One `Board` keeps one core, one LOS table, and one hex address for each consumer.

The alternative: a set of boards with a seam rule in the core. Each rule that reads a neighbour, a path, or a thread then must have a case for the seam.

Where it breaks: a composition of four boards has a large LOS table. The farm workers ran out of memory on two boards (2026-10-17), and a game of four boards holds about 2 GB.

Mitigation: the LOS table has a limit, and a game worker clears it above `LOS_ENTRY_LIMIT` (section 8.3). `--remote-slots` limits the games of one host at a time.

Computer against computer, the fourth play mode. `sl-cli host --agents v1,v2` gives each seat to a computer opponent. The host then plays the game itself, one command at a time. It sends the new frame to each browser after each command. `--agent-delay` is the wait between two commands: zero for a test, and a fraction of a second for a person at a screen.

A person at a screen in that game sees each unit of each side. `Game.spectator_view` builds that document, and its argument is the guard. It gives an error unless a computer opponent holds each of the two seats. A game with a person in a seat does not build it, because a full view in that game breaks AR-09. Three tests hold that guard, one for each shape of game.

`tests/browser/test_computer_vs_computer.py` is the harness. A browser joins the game, and the test reads what the browser shows after each step.

It checks five things. The client and the host agree on the turn and the phase. Each entry of the action log names a rule. The game moves through its turns and through the phases of rule 4. The console gets no error. The game ends with a result.

The harness writes a picture of each turn and a video of the game. They go to a directory that is not in the repository, because SR-07 keeps images out of the tree.

Why: the owner told the project to show the game when the computers fight (slice 17). The owner also told the project to add a harness that plays a full game in a browser. The alternative was a headless game and a log. A log does not show a defect of the client.

Where it breaks: a spectator view discloses each unit, so a guard error is a leak of hidden units (AR-09). Mitigation: the guard has its own three tests, and the host builds the view only when no person holds a seat. The two windows also accept `--agents`, with the same host path.

Rural terrain (rule 44): `slcore/rules/r44_rural.py`. Game Set II gives an effect to three terrain types that the city board does not use.

A wheatfield stops sight through it and not into it (rule 44.21). A thread that goes through a wheatfield hex goes across two of its hexsides. A thread that stops in the hex goes across one. So the halving of rule 44.21 reads the hexes between the two ends. A unit above the crop fires at full strength.

Rule 44.24 makes the crop seasonal. A scenario says `wheat_season` as `in` or `out`, and out of season the hex plays as open ground.

A shellhole gives plus one to the dice roll of the attacker (rule 44.31), and the terrain table held that number before this slice. Rule 44.32 makes the minus two of rule 16.5 into minus one, because the hole gives cover to a unit that moves through it.

A cliff hexside is impassable. The hexside table gave that to the movement rule before this slice. Rule 44.1 adds the second half. Point Blank Fire across a cliff is tripled for the higher unit. The lower unit keeps the doubling of rule 9.1.

The generator puts a cliff on a hexside where the level changes. It drops a cliff that would cut the board in two. A board in two pieces is a board that no scenario can use.

Why: the hills, village, and rural board types of FR-23 have these terrain types, and rule 44 gives them their effects. The rules go in the core with the rule ID, as each other rule does. No alternative design is recorded.

Where it breaks: a scenario with no `wheat_season` switch must have a season. With no switch the crop stands (`r44_rural.py`). Mitigation: the switch value is in the hash (section 3.2), so a replay with a different value stops at the first command.

Hidden Initial Placement (rule 42, FR-10): `slcore/rules/r42_hidden.py`. A scenario names one side. A unit of that side can set up in a woods hex or a building hex. Such a unit goes on the record of its owner and not on the board.

The view of the other player does not name that unit at all. A concealment counter tells you where a unit is not. A hidden unit tells you nothing.

The unit comes on the board on five occasions. It moves, it fires, or it makes smoke. It stands next to an enemy at the end of a Defensive Fire Phase or an Advance Phase. An attack on its hex has an effect. A unit that walks into its hex stops and ends its movement in the hex it came from. It learns of the hidden unit at that moment and not before.

The first half of rule 42.4 lets a player fire into a hex where no enemy is known to be. It waits for its own tier. It would change the legal list of each fire window into each hex in the line of sight. The environment of FR-50 reads that list as its action space.

Why: FR-10 gives rule 42, and the per-player view of section 4 removes each unit that a player cannot see. A hidden unit is a unit that the other view does not hold, so no new path of disclosure is necessary.

The alternative: a concealment counter on the hex. A counter tells the other player that a unit can be in the hex, and a hidden unit must tell the other player nothing.

Where it breaks: the log, the trace, and the prompt are three more paths that can name a hidden unit. Mitigation: each one reads the per-player view, and `tests/secrecy/` and `tests/core/test_hidden_contact.py` hold the paths.

<!-- AI review 20260907-163721: openai, board composition -->

The two modes: reference mode loads a 1977 layout and plays a printed scenario with its hex-list set up areas. Generated mode plays the same scenario data on a generated board of the same type, with set up areas resolved by zone (FR-21).

A zone is a predicate on hexes. The first version, in `slcore/scenario.py`, selects a stone building with four parameters. They are the band of columns for the side, the rank in the band, and the minimum and maximum hexes for the group. The band sorts by hex count first, from the largest, and then from the west. Thus rank 0 is the largest building of the band, and the scenario gives rank 0 to its largest group.

The band, and not an index from one end of the board, keeps the two sides apart on each board. The rank by hex count, and not by position, gives each group sufficient room. The `min_hexes` parameter is the check. A board that cannot hold the group is an error at load, and not a set up that breaks rule 6.1. The scenario file has the hex-list form and the zone form.

The alternative: ship the four 1977 layouts as data. The legal research (RV-4 section 3(c)) says the terrain layout is a creative selection with real risk. The owner made the decision on 2026-09-07 to keep the layouts private.

Where it breaks: the zone predicates can put scenario 1's five German buildings on a generated city board that has no five stone buildings in its western half. Then generated mode is a demo, not the game. This was open question O-04. The slice 6 prototype answered it on 2026-09-08, and the answer is in section 7.1.

Mitigation in the generator: the city type gets the scenario's zone requirements as constraints for pass 2. Then the board has the building count and the rough positions that the scenario specifies. When zone resolution does not succeed for a seed, the generator tries a bounded count of new seeds.

If none succeeds, the client says that generated mode is not available for that scenario and seed, and it offers a new seed. A headless run stops with an error that names the zone. The look rubric (TC-14b) then tells if the result looks like a board.

<!-- AI review 20260907-163721: xai, the zone fallback -->

### 7.1 The answer to O-04

The question: can zone-based set up areas move scenario 1 onto a generated city board with no change to the game?

The answer, measured on 2026-09-08 with the slice 6 generator: yes for the structure, on the condition that the zone says how much room is necessary for a group. The evidence is `sl-cli boards --count 1000`, and its run artifact is `runs/20260908T085233Z-tc14a-s01-guards-counterattack`.

- All 1,000 boards satisfy the geomorphic edge rules and connect to the next board on the east and on the south.
- All 1,000 set up scenario 1 with ten groups in ten different stone buildings, five for each side.
- 21 of the 1,000 seeds did not satisfy the zone constraints at the first try. The bounded retry found a subsequent seed for each one, and the fallback message was not necessary.

The condition came from a defect that the prototype found. Zone resolution by position alone gave the Russian guards a three-hex building on some seeds, and twelve squads do not stack in three hexes (rule 6.1). Two changes correct it. The zone parameters have `min_hexes`, and the generator constraints have the same number. Thus pass 2 makes a board that holds the group.

What the answer does not cover: the balance. Ten games of the v1 scripted agent against itself on each of eight boards gave the Russians between 0 and 7 wins of 10. The board changes the result. A weak agent is a weak measure of balance. Thus the balance question stays open, and it belongs with the agent work and the look rubric (TC-14b).

### 7.2 The front of scenario 1 runs along the rows

The first zone form of scenario 1 gave the Russians the west band of columns and the Germans the east band. On the card the front runs along the rows. The German buildings are in rows 5 to 9 and the Russian buildings in rows 2 to 4. Each Russian building is two to five hexes from a German one.

The column bands put the two sides six to twelve hexes apart. On that board no agent won the Russian attack against a German who fired at range six. The v6 agent won 1 to 5 games of 20, and three learned policies of 1 million steps won none.

The balance record of the printed scenario is 50 percent (RV-2 section 3).

The correction, on 2026-09-13, is in the scenario data and in the generator. The German zone is the rows 5 to 7 of the west half, which is the front of the card. The Russian zones are the rows 1 to 4, three hexes or less from a stone building of the German band. They are four small buildings and the guards building of four hexes or more.

The generator puts the zone buildings on the board before the free pass. The cause is room: a board that the free pass filled has no room for a building of four hexes in a band of three rows. The buildings of the other band are also necessary before a `near` zone can put its own on the board.

The starts of a zone that a `near` zone anchors on stay in the distance of that zone's band. Then no German building is deeper than the Russians can get to. A record with no `near` zone takes the earlier path and builds the same board as before.

The measure after the correction: on 200 seeds, 172 satisfy the zones at the first try. On each of 60 seeds, each Russian group is five hexes or less from a German group. The v6 Russian wins 8 of 20 against the v1 German, from 1 to 5 before, and 19 of 20 against a random German.

### 7.3 The scenario library

The decision: the library is 12 project scenarios, `lib01_grain_office.json` to `lib12_the_long_front.json` in `sldata/scenarios/`. The project does not copy the 1977 scenarios (owner, 2026-10-16). `sldata/library/slots.json` holds the 12 slots, L01 to L12. Each slot gives its board types, its armies, its rule level, its weapons, and the bands of its points and turns. Its field `required` gives the counters that a side always gets, so that the card can name them.

`slcampaign/library.py` makes a candidate of a slot from two seeds:

- The draw seed sets the point total, the turns, the victory condition, the attack share, and the two forces. It reads the seeded generator of the core, as the random construction of Game Set IV does.
- The board seed sets the board. A new board seed does not change the forces.

A slot names its rule level, and the draw takes only the counters and the features of that level. A slot of rule 21 has no smoke, no concealment, no engineers, and no vehicles. A slot of rule 41 or more has the armor. Halftracks, trucks, and jeeps wait for rules 47, 51, and 52 (PR-20), so the vehicle list of the slot file holds tanks and guns only.

A slot of two or more boards stacks them from north to south (`slboards.compose`). Thus the front gets wider with the force, and the depth of the fight stays one board. Each side has a group on each board, and the defender holds one stone building on each board. A `columns` set up area can have `min_row` and `max_row` (`slcore.scenario.resolve_columns`), so each group sets up on the rows of its own board.

A slot field `orchards` gives each board orchards, and `landmark` (for example `{"defender": "mill"}`) puts a mill on the building that the defender holds (section 7).

`sl-cli library` (`slcli/library_cmd.py`) has four actions. `slots` lists the slots. `draw` writes one candidate to `runs/library/<slot>/`. `check` plays the gate games on the two sides. `search` runs the seed search on the farm.

The balance method of the owner is the board seed first. The forces change only when no board seed gives 45 to 55 percent for the first side, with v7 against v7 in 1,600 games. A balanced candidate with a card that has no fault goes into the library with no review step (owner, 2026-10-17). Its seeds and its balance result go in the notes of the file.

Why two seeds: the owner's balance method searches the board seeds first, with the forces fixed (2026-10-16). With one seed for the two, each new board also gives new forces.

The alternative: copies of the 1977 cards, as `s01` to `s03a` are. The owner selected no copies for the library. A hand-made scenario for each slot was the second alternative, and it has no seed to search.

Where it breaks: the point scale is the project's own (O-08), so two forces of equal points are possibly not equal in play. The seed search finds a board that corrects a small difference only. When the forces of a slot are far apart, a change of the slot bands is necessary.

Mitigation: the search plays thousands of games on the farm, so a slot that does not balance shows in hours. Three corrections came from the searches:

- A two-sided slot (L03) gives each side a building at its own end, and a die roll decides which side moves first. The first L03 search gave the two sides equal points and the condition `building_swing`. The best of 1,600 games was 19.1 percent for the German side, because the Russians win when nothing occurs. With the attack share and `hex_control` of the Russian building, draw seed 8 and board seed 10 gave 50.1 percent (2026-10-17).
- A support weapon goes to a group only with a squad or a leader. A weapon with no group stays with the units in the building. The second L03 search found a group of one MMG, which no player sets up.
- Nothing on the board marks a building. Thus the card names a victory building by its rank and its band of columns, as the set up area does. Without the band, the two sides of L03 each read "the largest stone building" for two buildings.

### 7.4 The scenario cards

The decision: `slcards/card.py` makes a printable card of a scenario, and `sl-cli cards` (`slcli/cards_cmd.py`) writes it as a PNG file. The layout follows the 1977 card. It has a title, a red scenario number, a situation text, a board diagram, and a turn record chart. Then it has an order of battle for each side, the victory conditions, and the special rules. The 3D window shows the same card before the game (`slwindow3d/briefing.py`, `slcards.render_card`).

Each word comes from the scenario file, which is the project's own text (FR-22). Each shape is the project's own drawing (SR-07, DR-01). The mini-counters come from `slwindow.counters`, the code of the windows. Thus a counter on the card and a counter on the board are one drawing. The renderer sets the dummy SDL video driver before it imports pygame, so a display is not necessary.

Why: the owner told the project to make a card in the style of the 1977 card (2026-09-10). A person must read the forces, the set up areas, and the victory conditions before the first command.

The alternative: the text of the 1977 cards. The legal research forbids card text in the tree (SR-07). The set up areas are in words, because the printed board layout is not in the repository.

Where it breaks: a card sentence can disagree with the rules of the scenario. The L03 card said "the marked building", and nothing on the board marks a building (2026-10-17). The `notes` field of a scenario is the record of its provenance, and the first briefing showed it to the player.

Mitigation: the owner's rule is that each sentence of a card agrees with the rules of the scenario. The project does a check of each sentence against the code before a scenario goes into the library. Each playable scenario has a `situation` field for the players, and `notes` stays the provenance record. `tests/cards/` holds the card layout, and a test in `tests/library/test_library.py` makes sure that no card says "marked".

## 8. Topology: the host, the clients, the package, and the farm

The decision: a local Python host owns the game. The browser client connects to it on a WebSocket. Hot seat is one client on the owner's machine with the host on localhost. LAN is two clients on two machines with the host on one of them, and a room code as the join credential. The client has no rule logic (AR-06).

The alternative: run the core in the browser through WebAssembly, so that hot seat has no process. The first multi-AI review found that this does not agree with the Python core (consolidated review, contradiction 3). The WebAssembly path stays as the option if the core moves to Rust.

Why this is right: the host is the same code in hot seat and in LAN, so the per-player view (section 4) is built and tested one time. The trainer and the harness import the core and do not use the host, because they have no browser.

The protocol is small, and it is version 2 since 2026-09-23. `src/slhost/protocol.py` holds the fields of each message, and `tools/make_protocol_schema.py` writes the shared schema from it. <!-- AI review 20260907-163721: gemini and openai, the frame ID replaces the list index. gemini, the los_request message. --> The client sends nine messages:

- `join(room_code, display_name, seat_token)`. The seat token is optional. The host gives a token to each client that holds a player seat. A join with that token gets the seat back after a drop. A watcher gets no token.
- `intent(frame_id, command_id)`. The frame ID is an opaque token of 32 hex digits. The host makes a new token for each connection and each frame, and the token has no relation to the state hash. The host refuses a token that is not the newest one it gave to that connection. The command ID is one of the IDs in that frame.
- `undo()`. The host takes back the last command of the person at the screen when that command rolled no die and showed no hidden information. Hot seat and a game against the computer only.
- `auto_setup()`. The host sets up the side of the person with the v7 agent.
- `view_request()`.
- `los_request(from_hex, to_hex)`. The host answers with the rule evaluator's result, because the client has no rule logic. In strict mode (FR-34) the host answers only at the times rule 19.3 lets a player use the tool. At other times it rejects the request with the rule ID. The welcome message has `strict_los`. The client shows that flag as text and sends no mode.
- `setup_lift(unit)`. While the side of the person sets up, the host takes that placed unit off the board again (`Game.lift`).
- `options_request(unit)` (2026-10-26). The host answers `options_result(unit, frame_id, result)` from `src/slhost/options.py`, for a unit of a side that the connection holds. The frame ID lets the client discard an answer for an expired frame. The contents of the result:
  - In the set up: the text of the set up area, and the cause for each hex of the area that refuses the counter. The causes are rule 6.1, rule 29.2, the portage of a leader, and a weapon with no carrier.
  - In the Movement Phase: each hex that the unit gets to with its remaining factors, by the costs of the core. For a vehicle, the search is on the hex and on the use of its free pivot (`options.vehicle_paths`). Rule 30.5 lets it select its facing in the hex it enters, so only its first step can pay the cost of rule 29.4.
  - In a fire phase: the hexes in range (rule 9.1) and in long range (rule 9.2) with a clear line of sight. In strict mode the lists are empty.

- `move_to(frame_id, unit, hex)` (2026-10-26). In the Movement Phase the host moves the unit, or its stack, to the hex by the path of lowest cost of `options_request`. Each step is a command of the legal list at that time (`options.route_step`), and the host applies it as an intent. Thus the log, the save file, and a replay hold the single steps. The first step has the source `human` and each subsequent step has the source `route`, so one undo takes back the full move. The move stops at the first step that is not legal, and the host sends an error that gives the hex where the unit stopped.

- Each frame has the field `objectives` (2026-10-26, `src/slhost/objectives.py`): one record for each victory condition, with its side, the sentence of the card, and its hexes. The record of a condition of the viewer's side also has the count at this time and the hexes that the side controls. The host gets them from the core on the state that the viewer may know (`player_state.for_player`). The record of a condition of the other side has no count, so it gives no fact of a hidden unit (AR-09).

  The cause of the options message: the window has no rule logic (AR-06). The legal list names only the next step of a move and the targets with a known enemy. The legal list stays the one source of a command.

The host sends `welcome` with the seat, the board, the scenario, `strict_los`, and the controller of each side. It sends `frame(player, view, legal_commands, frame_id, log_tail, status)` after each command, `error(rule_id, message, code)` for a rejected intent, `los_result(from_hex, to_hex, result)`, `options_result(unit, frame_id, result)`, and `game_over` with the result and the casualties. A client does not connect again after a terminal error code.

A computer turn runs in a thread. Thus the event loop keeps each socket open while an agent makes its decision.

The frame is the view of one seat. In a LAN room the idle seat gets an empty legal list. A stale client cannot apply a command against a state it has not seen. The host compares the frame ID in the intent with the newest token of that connection. A mismatch is an error with a new frame. The client does not calculate, get, or send a state hash (DR-04).

NFR-02 measures the time from the host's receipt of an intent to the client's receipt of the next frame. The measurement is on localhost, in the Playwright test (TC-11). That time includes the core's apply, the view build, the frame build, and the transport. It does not include the browser render.

<!-- AI review 20260907-163721: openai, what NFR-02 measures -->

Security posture: the LAN is trusted-party convenience (SR-03). The room code has 128 bits of entropy. The host examines the WebSocket origin, limits connection tries for each address, and gives the player slots itself.

A refused join or connection has the code `rate_limited`, and the session stops. Each connection can also send 30 questions (a line of sight, the options of a unit, a view) in 5 seconds. A question above that gets the code `request_limited`, and the session continues. The window client sends at most 24 questions in 5 seconds, and it sends a held question again in a subsequent frame (`slwindow.client.QUESTION_LIMIT`). None of this is a confidentiality guarantee against a hostile machine on the same LAN, and the documents say so.

Where it breaks: WebSocket libraries on Windows and the asyncio event loop policy. The LocalLLMPerf_AI sibling hit a pyzmq starvation defect on the Windows proactor loop.

Mitigation: the host uses `websockets` with the selector loop policy on Windows, set in one place, as the sibling does.

### 8.1 The package for players, and the collection of played games (2026-10-27)

The decision: the package is a PyInstaller folder for each system (`tools/package.py`), with the launcher as its entry (`slcli.frozen_main`, `slwindow.launcher`). The packaged game sends each game that a person played to a collector (`slcollect`, `sl-cli collect serve`). It sends only when the player agreed at the first start and has a player key. The first collector is `tars.uberadmin.com:5170` (owner, 2026-10-27). An Internet collector with its own name comes when the game is published.

The launcher (`slwindow/launcher.py`) is `sl-cli launch`, and it is the entry of the package when the program gets no arguments (`slcli/frozen_main.py`). With arguments, the same program is `sl-cli`. The launcher shows the consent question one time, and then it shows a menu:

- The scenario: the 12 library scenarios (section 7.3), each with its two sides in the order of play.
- The side of the person.
- The opponent: `easy`, `normal`, or `hard` (v5, v6, and v7, `slcli.window_cmd.DIFFICULTY`), a person at the same computer (hot seat), a LAN host, or a LAN join with an address and a room code.
- The window: the 3D window (the default) or the 2D window.

Play starts the game window as a second process of the same program (`launcher.game_argv`), so each game has a new window and a new Panda3D. A LAN host window binds all addresses on port 8731 (`--lan-port`, `launcher.LAN_PORT`). After the game, the launcher sends the saved games on a thread of its own (`slcollect.client.send_pending`). The package has no torch and no numpy, so the `learned:` agents are not in it.

The record is the save file of the host (`slhost.savegame`). A game is its seed, its switches, and its command log, and each command line has its source. Thus the save file is sufficient for the training: the trainer makes each position, each legal list, and each decision of a person again through the core. The collector does not keep a second format.

The wire is HTTP. Each `POST /v1/games` has the key name, a time, a nonce, and an HMAC-SHA256 (`slcollect.wire`). The HMAC covers the method, the path, the time, the nonce, and the hash of the body. The collector refuses a time more than 600 s from its clock and a nonce that it saw. Each player has a key of their own (`slcollect.keys`), so the owner can revoke one key.

The collector plays each game again (`slcollect.verify`) and keeps it in `games/` when each hash agrees, or in `unverified/` when not. A game with no command of a person is refused. A resumed game comes again with more lines, and the collector keeps the longer file when the older one is the start of it.

Why: a player must have the game with no Python install, and the decisions of persons are necessary for the computer players. The save file and the replay check exist, so the collection adds only a signed upload and a store.

The alternatives:

- A Python wheel and a launcher script. It is small, but each player must install Python 3.12.
- One key in the package. Each person can read it from the files, and one bad key stops all the players.
- The trace records of FR-60 in place of the save file. A trace is larger, and the replay makes it again.

Where it breaks:

- PyInstaller builds only for the system it runs on. The Linux package must have a Linux build.
- A game from a package with other rules gives other hashes, so the collector cannot make sure of it.
- The server is plain HTTP. On the Internet the key name and the address of the player go in clear text.
- A player can send false games with a valid key. The replay check stops a game that the rules do not let occur, but not a game that a script played.

The mitigation:

- The build of each system has the same script.
- The upload names the package version, and `unverified/` keeps those games for a replay with the code of that version.
- An Internet collector has TLS in front of it.
- The index records the key of each game, so the owner can remove the games of one key and revoke it.

Privacy: the launcher shows the question one time before it sends (`slcollect.settings`, `consent`). A sent game has the scenario, the seed, the commands, the key name, and the package version. The collector also records the network address. The game saves each game on the disk of the player in all cases.

The files of the collection:

- The key store of the collector is `collect_keys.key.txt`. `sl-cli collect key add NAME` writes a key to it and the player file `collect_players/NAME/collect.key.txt`.
- `slcollect.settings` gives the data directory of the player: `%LOCALAPPDATA%\SquadLeaderExpeditionem` on Windows and `~/.local/share/squad-leader-expeditionem` on Linux. The tests set it with `SL_DATA_DIR`.
- `slhost.savegame.check_lines` reads the parsed lines of a save file. The host uses it for `--resume`, and the collector uses it before the replay.

### 8.2 The desktop windows

The decision: the two desktop windows are consumers of the host protocol, with no rule logic (AR-06). `sl-cli window` opens the 2D window (`slwindow`, pygame-ce, the `desktop` extra). `sl-cli window3d` opens the 3D window (`slwindow3d`, Panda3D, the `view3d` extra). With no `--connect` address, the command starts a host in the same process (`slwindow/embedded.py`) and connects the window to it on the loopback address. That is the path that the browser client takes.

The 3D window is the MVP front end, and the owner uses only this window. It puts each hex on a prism that its elevation lifts, so a hill stands up. It has a top-down camera mode and a tilted camera mode. The 2D window stays, and the two windows share most of their code.

What the windows share in `slwindow`:

- `client.py`, the protocol client, and `choice.py`, the command list (`Chooser`).
- `overlay.py`, the shades of the board, and `logtext.py`, the text of a log line.
- `setup.py`, `traydraw.py`, and `traycontrol.py`, the set up tray. `SetupTrayControl` is a mixin of the 2D `Window` and the 3D `Board3DApp`.
- `unitinfo.py`, `unitmenu.py`, and `boxes.py`, the "about this unit" box and the menu of a unit.
- `victorytext.py`, `endgame.py`, and `panel.py`, the victory box, the end box, the turn line, and the panel.

The set up tray shows each counter of the side that sets up. A click on a counter shades its hexes of the legal list, and a click on one of them puts the counter there. A drag from the tray or the board to a shaded hex also puts it there. A support weapon goes onto a unit that can carry it (`setup.weapon_step`). A click on a placed counter sends `setup_lift`, and the host plays the game again through the core without the place command of that unit (`Game.lift`). The host does not apply `end_setup` for the person, and the Finish set up button sends it.

The options of a unit come from the host (section 8). The window sends `options_request` for the selected counter. In the set up, the answer gives the set up area and the cause of each refused hex. In the Movement Phase it gives the reach of the unit, and in a fire phase the field of fire. The tray shows the cause after a refused click or drop (`App.refusal_text`, `overlay.setup_refusal`).

A click on a reach hex sends `move_to`, and the host plays the path one legal step at a time (section 8). A right click on a unit, or Ctrl and Space, opens the menu of the unit: its commands in groups, the commands of the side, About this unit, and Undo. The panel has an Undo button that is bright when the frame has `can_undo`. The victory conditions come with each frame (`objectives`). The overlay shades their hexes, and the "Victory conditions" button or Ctrl and v opens their box.

The end of a game is a box in the middle of the board. `endgame.summary` gives "You won." or "You lost." to the one side that a person holds, and the winning side to a watcher. `annotate.side_names` gives a side with a generic key (`allied`, `axis`) the name of its army.

Three more details of the windows:

- The windows show a carried weapon in the stack after its carrier (`overlay.with_carried`). The view gives each weapon its portage, and it gives the owner the movement factors of a unit with a load (`view._add_portage`).
- `endgame.turn_text` gives the turn line of the panel, for example "turn 2 of 5: 3 more turns after this one".
- The Undo button is the row `panel.UNDO_ROW` of the panel (`panel.draw_panel(undo_button=True)`).

The 3D window has three more parts:

- The briefing (`briefing.py`): the scenario card covers the board until the person selects Begin. The window connects to the host only then, so no game starts behind the card. `--no-briefing` skips it.
- The fire effects: `firekinds.py` sorts the log lines into kinds of fire, and `effects.py` animates each kind with the tracer colour of each army. `firekinds.py` reads facts of the event and of the view only, and it calculates no result.
- The sound: `sounds.py` makes each sound in code. The one exception is the vehicle, which is a part of the owner's tank recording (`assets/tank_drive.wav`). `audio.py` plays the sounds of the new events from a Panda3D ramdisk. Ctrl and m mutes, and `--mute` loads no audio library.

Why: the owner told the project to open a window of its own on Windows and on Unix, and not a browser (slice 18). Then the owner told the project to make a board that turns, tilts, and zooms, with the height of the ground (2026-09-10). A window that speaks the host protocol keeps one host, one per-player view, and one secrecy test for each front end.

The alternative: a window that imports the core and applies the rules itself. That window would be a second rules path, and AR-06 forbids it. The second alternative: the browser client only. The owner told the project to make a window that is not a browser.

Where it breaks: three front ends (the browser client, the 2D window, and the 3D window) must show the same game. The tree has an older browser client, and 28 tests of the client tables fail until the newer client comes in. A window also must show facts that the legal list does not give, for example the reach of a unit across more than one hex.

Mitigation: the two windows share the modules above, and `tests/window/` and `tests/window3d/` test the two with real pixels. The 3D tests run offscreen, and `tests/window3d/conftest.py` stops them while a live `sl-cli window3d` runs. The host calculates the reach, the field of fire, and the refusals (`slhost/options.py`), so the window shows a fact of the core and calculates none.

### 8.3 The game farm

The decision: the game farm (`slfarm`) plays games on four Ubuntu hosts: `tars`, `case`, `kipp`, and `plex`, each an AMD Ryzen AI Max+ 395. Each host runs `sl-cli farm serve`, a server with a pool of worker processes (`slfarm/server.py`). `sl-cli gauntlet`, `sl-cli evolve`, the library search, and `sl-cli train` send it work with `--remote tars,case,kipp,plex` and the key file `--remote-key farm.key.txt`.

The protocol (`slfarm/protocol.py`) is one JSON object on each line of a TCP stream, on port 5160 by default:

- The server sends a challenge with a nonce, the protocol version, the hash of its source tree, and its slots.
- The client answers with an HMAC-SHA256 of the nonce with the key. The key does not go on the wire.
- The client compares the hash of the source tree with its own, and it refuses a host with other code. A game is its seed only on the same code.
- A job is a scenario (a name or a document), a seed, and two scripted agent names. The server checks each field. It refuses a learned agent, because it reads a file, and a model agent, because it uses the network.

`python tools/farm_deploy.py [host]` copies the code, the key, and `tools/farm_worker.sh` to each host with one ssh connection, and that script installs and starts the worker. Run it after each change to `src/`, or the hash compare refuses the host.

`_play_all` of `slcli/gauntlet.py` gives the jobs to the farm, and the results come back in the order of the jobs. Thus the artifact is the one that a single machine writes. A game worker keeps the engine of its last scenario only (`ENGINE_LIMIT` is 1). After each game it clears the line of sight table when the table holds more than `LOS_ENTRY_LIMIT` (250,000) results. The table of three boards grew by hundreds of MB with each game. `--remote-slots N` sends at most N games at a time to each host (`Farm.slots_per_host`), because a game of four boards holds about 2 GB.

PPO workers on the farm (2026-10-14): `sl-cli train --remote ... --opponents v7` opens `--remote-envs` environments on each host. The default is the slots of the host. A host runs the loop of `slagents.learned.workers.worker_main` in a process for each environment. A bridge process for each host on the workstation (`slfarm.client.host_bridge_main`) gives the trainer a pipe end to each environment, so `ppo.collect_parallel` does not change.

- The bridges are processes. 44 bridge threads in the trainer took its interpreter lock, and the run gave 244 steps/s, less than with 16 local workers.
- `ppo.wait_any` waits on more than 63 pipes, which is the limit of one wait on Windows. It looks at groups of pipes in turn.
- The commands and the decisions go as JSON that each side examines (`slfarm/envwire.py`). The arrays go as base64 with a dtype and a shape, and not as pickle, because pickle runs code.
- The farm refuses a snapshot opponent, because a snapshot is a file of the workstation.
- A remote worker that stops goes out of the pool (`WorkerPool.drop`). The run continues while `MIN_LIVE_SHARE` (0.5) of the workers at the start are live. A local worker that stops also stops the run, because the cause is in the code of the workstation. The run artifact lists the dropped workers in `dropped_workers`.

Why: the cost of a gauntlet, an evolution, or a training run is the game simulation on the processor. The four hosts run the local language models, and each host has 16 cores that llama-server does not use (2026-10-14). The owner told the project to make a Linux server that plays games on each host, with control from the workstation through a TCP socket.

The alternative: the OpenAI API of the language model servers on those hosts. That API gives text and cannot play a game step. A general job system for clusters was not examined, and no record gives a cause against one.

Where it breaks: the farm runs code that the workstation copied, so a host with expired code gives different games. A host that stops removes the games in flight. A PPO run on the farm has 136 workers, and the one trainer process becomes the limit. In L11 the speed fell from about 355 to 245 steps/s when v7 became a member of the league.

Mitigation: the hash compare refuses a host with other code. The client puts the games of a stopped host back on the queue, and a game is its seed, so the result is the same. A worker that dies gives a `refused` answer, and the server makes a new pool. The trainer timers (`ppo.CollectTiming`, section 9.5) show where the time of a run goes. With `--rollout 4096 --minibatch 1024`, a run of 40,000,000 decisions gave 1,789 steps/s on s04.

## 9. The four agent families

The decision: all four families use one interface: observe a view, get the decision frame, select one command ID. They share the trace format and the tournament (AR-10). Each family is a Python package that imports the core.

The prompted family and the tuned family share one harness (section 9.3). The two are different in the model loader and in the constraint mode. The scripted and the learned families have no text view, so they do not use that harness. One harness for the four families would be a name, not a simplification.

<!-- AI review 20260907-163721: xai proposed one harness for the four. Used for the two model families only. -->

### 9.1 Scripted agents

A scripted agent is a function from view and frame to a command, with named parameters (aggression, cover preference, fire priority). It is the constant opponent: versioned, cheap, and deterministic for a given seed. FR-54 names CMA-ES or population-based training for the tuning. The built search is a (mu + lambda) evolution strategy (`slagents/scripted/evolve.py`, section 9.5).

`slagents/registry.py` names nine computer players with no net and no model: `random` and the eight scripted agents v0 to v7 (FR-44). `random` (`slagents/base.py`, `RandomAgent`) selects a legal command at random with the seed of the game. It is the floor of the league and of the first measures. The first three scripted agents are below.

- Agent v0 is the baseline with no parameter. It sets up, it moves in the direction of the objective, and it ends each phase it has no rule for. It is the low mark of the ladder, and it does not change.
- Agent v1 plays rules 1 to 21. It fires at the best-odds target in range, it moves to cover and to the objective, and it routs to the nearest cover.
- Agent v2 is the engineer. It plays rules 22 to 27 also. It makes smoke in the direction of the enemy, and it puts a demolition charge on an occupied hex. It fires a flamethrower before it forms a fire group. It moves a stack down a sewer when the other entrance is nearer the objective. It divides its concealment counters between its own stacks and the dummies of rule 25.7.

Why a third agent and not a third parameter set: the difference between v1 and v2 is which commands they answer, not how they weigh a move. A parameter cannot make an agent use a rule its code does not know.

The subsequent agents are v3 to v7. v3 is the tanker. v4 extends the threat map of v1. v5 adds vehicle fire. v6 keeps an attack schedule.

v7 trades on the odds and reads only the enemy units the player can see. v7 does not place concealment, use a demolition charge, use a flamethrower, or use a sewer. Smoke of rule 24 is in v7. A name such as `v7:german` selects the nation record for the role of that side.

### 9.2 Learned agents

The environment is a PettingZoo AEC environment on the core, with the legal-command mask in each observation (FR-50). The observation is a stack of planes on the board plus a vector for the active unit. The planes are terrain, own units by type and state, enemy units in view, concealment counters, phase, turn, and side. The action is one composed command with a unit head, an action head, a target head, and an option head. Masks from the command tree of the frame apply to each head, and there is an end-phase action. The composed choice maps to a payload and its ID (section 3.4).

This is the Gym-uRTS template (RV-5 section 2). The trainer is PPO in raw torch in CleanRL style, as the siblings do.

The league keeps snapshots, the versioned scripted agents, and an Elo table against the constant opponents. The learning ladder is 1 million steps for a sanity signal, 10 million for a pilot, then 100 million to 300 million (FR-52). The 24-hour budget for 300 million steps is the source of the 3,500 steps/s gate.

Where it breaks: no paper tried PPO on a game with dice, morale, rout, and concealment at this scale on one GPU (Vision bet 4).

Mitigation: the ladder stops a bad run at 1 million steps. Behavior cloning from replays is the year-two fallback. The scripted agents stay as the opponents in the game.

Slice 9 built the parts. The environment is `slagents/learned/env.py`, an Agent
Environment Cycle environment with two agents. Each observation holds four things: the
board as planes, one row for each unit slot, a scalar vector, and the mask of the legal
commands. The planes and the rows come from the view of the acting player. So a concealed
stack is a counter and not the units below it (rule 25.2).

The command has four parts, so the policy has four heads: which unit, which action,
which hex, and which option. Two weapons at one hex, and many close-combat attacks that
start with one unit, share the first three parts. The option names the command.

The option list holds 64 commands. The unit mask and the action mask are in the observation.
The target mask and the option mask come from methods on the environment.

The planes and the unit rows use the player view. A hidden enemy and a concealed enemy
are not in them. A dummy concealment counter and a full concealed stack pay the same sneak
term.

The reward is the shaped reward of `slagents/learned/reward`. A win pays. A loss, a draw,
and a truncation each cost the same large number. The step terms pay for a find, a shot,
a break, a kill, cover, and a sneak. They also pay for a move nearer to the objective of a positional victory
condition. A factory
hex that each side counts pays one time.

A snapshot written before 2026-09-23 does not
load. The load uses `weights_only=True`.

The league of `league.py` keeps three kinds of opponent: the random agent, the versioned
scripted agents, and the snapshots of the policy. It samples by loss rate, with a floor so
that each opponent stays in the set. Its Elo table has the same shape as the tournament
table, so one number means the same thing in the two places (TC-19).

Section 9.5 gives the details of the trainer and of the agent at play time, in the order
of the runs that made them necessary. In short:

- `agent.py` gives a snapshot the Agent interface as `learned:<snapshot>`. Its choice rule
  is the action first, with two exceptions (`JOINT_SCORE_PHASES`, `ACTION_FAMILY`).
- `routes.py` adds the actions `route` and `stack_route` at the end of `encoding.ACTIONS`.
  They are not commands of the core. The agent or the environment plays their single steps.
- `reward.py` holds the shaped reward, with the approach term `reward.Approach`.
- `jumpstart.py` is Jump-Start RL, and `--value-warmup` trains the value head alone first.
- `workers.py` holds the worker processes, local and on the farm (section 8.3), and
  `ppo.CollectTiming` measures where the time of a run goes.

Some details of the trainer:

- The update divides the reward by `reward_scale`.
- Each row of the TC-18 table has five counts: `won`, `lost`, `drawn`, `truncated`, and `repeated`. `by_side` has the same counts for each side.
- The option of a stack route is the bit mask of its squads by unit ID (`routes.stack_option`). A snapshot with fewer actions than `stack_route` needs has no routes (`routes.uses_routes`), and `make_env(..., use_routes=False)` gives its environment.
- In the imitation, a run of moves of the teacher in a phase is one route row, to the last hex of the run (`imitate._label_of`).

### 9.3 Prompted model agents

The harness builds a text view. The view has a header (scenario, turn, phase, side) and a unit table. The table has hex, terrain, morale, status, and the LOS to the nearest three enemies. The view also has a short history of the agent's own plans and the legal command list with IDs.

The model answers in two stages: free text analysis, then a JSON object with the command ID as an enum of the legal IDs (FR-46). The provider adapter uses the provider's schema mode with one flat schema (IR-03).

The harness compares the ID against the frame. On a mismatch it retries with the rejection message, up to the configured count, and then applies the scripted default (FR-47). Each call records tokens, latency, cost, and the flags (OR-02).

The provider abstraction comes from the siblings. The `llm_compare` base class gives a response record, provider status, and model preferences. The HoneyAI refinements add JSON schema output with validate-and-repair, per-provider timeout, a circuit breaker, and an explicit failover sequence. The key loader resolves against the project root and skips comment lines. It falls back to the environment variable, and it marks a provider unavailable when the key is missing. The local endpoint is OpenAI-compatible HTTP with a `/v1/models` health check (IR-01).

The latency budget: a decision with a median time of more than 5 seconds makes the agent asynchronous (FR-59). On a local 8B to 32B model at Q4 on an RTX 5090, a 5,500-token prompt and a 300-token answer use 2 to 6 seconds (RV-6 section 4.2). So a local model is at the edge of real-time play. A SaaS model is below the budget.

Two things keep the local model in the budget. The prompt has a stable prefix (the rules summary and the scenario header) so that llama-server's prefix cache applies (IR-06). The view has a size budget in tokens, set in the harness config. When the view is larger than the budget, the unit table drops the LOS columns first.

<!-- AI review 20260907-163721: gemini, the local latency -->

Slice 10 built the family. `providers/base.py` has the interface and the allowlist.

`sldata/providers.json` holds the allowlist and ten provider rows: five local rows (`local`
to `local5`) and five SaaS rows (`claude`, `openai`, `mistral`, `xai`, and `gemini`). Three
adapters serve them. `providers/openai_compatible.py` covers the local rows, `openai`,
`mistral`, and `xai`. `providers/anthropic.py` covers `claude`. `providers/gemini.py` covers
`gemini`, because its API has a shape of its own and accepts a subset of JSON
Schema.

`keys.py` reads a key from
`<provider>.key.txt` at the project root or from an environment variable, and it does not
put a key in a message. `router.py` is the failover sequence with a breaker for each
provider. `harness.py` builds the text, sends it, reads the answer, and counts the four
rates of TC-16.

The harness does not obey the model output. The answer names a command identity, and the
harness looks that identity up in the frame the core gave. A name that is not in the frame
is an invalid answer and a retry (SR-04).

The odds in the text (2026-09-19). The first gauntlet of a local model gave 0 of 56
against the scripted agents. The cause was plain: the scripted agents read the odds of
the core, and the model read a list with no number on it. `oddsview.py` builds one
`OddsView` for each decision from the acting player's view, and each legal command shows
its odds from `slagents.scripted.odds`.

- A shot shows its firepower and its modifier. It shows the chance of a result, the
  chance of a kill, and the break chance of each unit in the target.
- A move shows the terrain of its destination and the break chance at the worst hex of
  its path. Rule 16.1 lets the defender fire at each hex of it.
- A close combat shows the kill chance of each side, and a rally its chance.
- Each own unit line has its break chance where it stands.
- The text holds the victory conditions of the card with their buildings.

Why this is right: a model has no fire table in its head, and the number is what the
doctrine agent reads. The alternative is a rules summary in the prompt. It costs tokens
on each call, and it gives the model a table to read by itself, which it does incorrectly
(RV-6). Where it breaks: the odds of a shot name the units of the target hex, and a
per-player view must not name a concealed unit (SR-09).

Mitigation: a target below a concealment counter gets no odds. The loss of a hex counts
the enemy units the player sees and no other. The system prompt says a missing number is
unknown and not zero.

The measure: the same model on the same seeds went from 0 of 40 to 1 of 40. So the odds alone did not make a 3 billion active parameter model a player. The
tuned family is the next lever.

The cycle guard (FR-65, 2026-09-20). One game of that gauntlet had 15,837 decisions, and
the other 39 had 120 to 274: the model dropped and picked up one weapon for four and a
half hours.

The harness keeps the positions it saw in the turn and phase. A position is the state
document without its command count, because the state hash counts each command. For
each legal command the harness finds the position the command gives with
the core's own `apply`, at about 20 milliseconds a decision. It offers the model no
command that gives a seen position.

The prompt says how many commands the guard held back. The schema constraint holds the
model to the offered list, and the scripted default of the fallback obeys the guard too.
When each command gives a seen position, the guard stands down and the full list goes
out, so the agent always has a command (FR-47). The counters record the decisions where
the guard held a command back (TC-16).

The local pool (2026-09-19). The owner's network has five llama.cpp servers: four
desktops with an AMD Ryzen AI Max+ 395 each and the workstation's RTX 5090. The provider
table names each as a row, and the name `model:local*` in an agent name is the pool. The
seed of the game picks the first host, and the other rows follow it as the failover
sequence of the router. So the games of a gauntlet go across the hosts with no state and
no coordination.

A gauntlet worker binds to one host by its index, and `--workers 4`
puts one game on each box.

A provider row can hold a `request` field that the adapter adds to each request. The
local rows turn the reasoning of Qwen3 off. The harness wants a short analysis and a
JSON object, and a reasoning pass spends thousands of hidden tokens first. The gauntlet
and the tournament record the harness counters of each model agent of each game. A
gauntlet of a model agent is hours long, so `sl-cli gauntlet --progress` prints one line
for each game that ends.

### 9.4 Tuned model agents

The owner's directive of 2026-09-07 makes a fine-tuned local model a fourth family, tested in year one. The design has four parts.

First, the trace data set (FR-60, DR-08). Each decision in each game writes one record: the view text, the legal IDs, the selected payload and ID, the outcome, and the `board_source` field. Traces come from the acting agent's view only (SR-09). Traces from reference-mode games get `board_source` equal to `reference_private` and stay on the owner's machine (SR-10).

The fine-tune command rejects such traces unless the owner gives the local-only flag. The run manifest of such a run identifies the weights as local-only, and the release audit (SR-07) finds that mark.

Slice 8 built the writer as `slagents/tuned/traces.py`. One option gives the traces of each kind of game: `sl-cli play --traces`, `sl-cli tournament --traces`, and `sl-cli host --traces` for hot seat and for LAN. The writer calls the same `slcore.view.build` that the host sends to a player. So a record cannot hold a unit that the view of the acting player does not have. The actor of a decision on the host is the computer opponent by name, or `human` for the person at the seat.

<!-- AI review 20260907-163721: openai, SR-10 had no enforcement -->

Second, the fine-tune (FR-61) with the year-one profile. The profile is a 7B or 8B instruction model, LoRA or QLoRA with a named configuration, a fixed context length, and generated traces only. The training target is the selected command, given the view and the legal list. The trainer weights the loss by decision importance (fire and rout decisions above end-phase decisions). The Diplomacy report names that weight as its largest quality increase (RV-8 section 4).

The path has three steps: a 50-step smoke run on 10 traces (TR-12), then an export and a load on llama-server, then the full run. The full run on 200 games completes in less than 24 hours on the owner's GPU (NFR-09). A 14B base is a measurement after the profile works, not a bound.

<!-- AI review 20260907-163721: openai, the GPU profile and the staged smoke path -->

Third, constrained decoding (FR-62). The merged model exports to GGUF and loads on the same llama-server as the prompted local model (IR-08). The harness sends a GBNF grammar or a JSON schema with the legal list as the command enum. Then the model cannot emit an ID that is not legal.

The harness records the invalid-command rate with and without the constraint, because that difference is the measure of what the fine-tune learned. FR-62 keeps the three constraint modes (grammar, schema, logits mask). The harness measures the compile and decode time of each on the local server, because no source gives that number.

Fourth, the comparison (FR-63). The tournament runs the four families on scenarios 1, 2, and 3A with sides balanced. It reports win rate, confidence interval, decision time, and cost. The one comparison that matters for the directive is the tuned model against the same base model prompted (TC-36). The four metrics are the invalid-command rate with the constraint off and on, the fallback rate, the win rate, and the decision time.

TC-36 is a measurement, not a release gate. TC-37 is the gate, for the year-one profile only.

Where it breaks: 200 games of traces is a small data set, and a model can learn the scripted agent's habits and not the game.

Mitigation: traces come from all four families and from human games. The trace writer records the source family, and the fine-tune can weight or remove sources. The self-play step for the language model itself (SPIRAL-style, FR-64) waits for the first result.

Slice 11 built the four parts. `slcli/traces_cmd.py` reads the trace files of a directory
and writes one line for each decision, with the importance weight of that decision. The
guard of SR-10 is in that command and in the fine-tune: a record from a reference-mode
board stops the build, and the message names the file and the flag that accepts it.

`slagents/tuned/finetune.py` holds the year-one profile and the smoke run. The smoke run
builds a small model in memory, applies LoRA to it, and runs fifty steps on ten traces.
The weights of the decisions are in its loss. No download and no GPU are necessary, so it
runs on each commit. The full run of the year-one profile gives an error that names its
workstation. A build that cannot complete a run must not start one.

`slagents/tuned/export.py` merges the adapter, converts the result to GGUF, and sends the
local server one question. Each of the three steps says what is missing when it cannot run.

Constrained decoding (FR-62) is one argument on the provider interface. The harness sends the schema of
the decision, and the command field of that schema is the enum of the legal identities.
The provider then holds the model to it. The agent name `tuned:local` is the harness with the
constraint on, and `model:local` is the same harness with it off. The difference between
the two invalid rates is what the constraint is worth.

### 9.5 The methods of the computer players

Sections 9.1 to 9.4 give the four families. This section gives the methods that make and measure a player in each family. It also gives how the methods supply each other, and the result of each method to 2026-10-27. The record of each run is in `VIBE_HISTORY.md`.

| Method | Family | What it learns from | Code | Command |
|---|---|---|---|---|
| A random legal command | Scripted (the floor) | Nothing | `slagents/base.py` (`RandomAgent`) | `--agent random` |
| Doctrine by hand | Scripted | The rules, RV-9 doctrine, and the probe of the games that it did not win | `slagents/scripted/v0.py` to `v7.py`, `armor.py` | `--agent v7` |
| The odds function | Scripted, prompted | The tables of the core, with no die | `slagents/scripted/odds.py` | (a library) |
| Parameter evolution | Scripted | The results of games against a fixed panel | `slagents/scripted/evolve.py` | `sl-cli evolve` |
| The shape study | Scripted (an input) | The positions of many games, with the winner | `slshape/` | `sl-cli shape` |
| Imitation and DAgger | Learned | The decisions of the scripted teachers | `slagents/learned/imitate.py` | `sl-cli imitate` |
| PPO with a league | Learned | Its own games, with the shaped reward | `slagents/learned/ppo.py`, `league.py`, `reward.py`, `routes.py`, `jumpstart.py`, `workers.py`, `agent.py` | `sl-cli train` |
| Prompted model | Prompted | Nothing: a text view with the odds | `slagents/prompted/` | `model:local*` |
| LoRA fine-tune | Tuned | The traces of the game | `slagents/tuned/` | `sl-cli finetune` |
| The gauntlet | All | (the measure, not a method of play) | `slcli/gauntlet.py`, `slruns/elo.py` | `sl-cli gauntlet` |

```mermaid
flowchart LR
    Core[Rules core] --> Odds[Odds function]
    Odds --> Scripted[Scripted agents v0 to v7]
    Odds --> Prompted[Prompted model agents]
    Shape[Shape study] --> Scripted
    Evolve[Parameter evolution] --> Scripted
    Scripted --> Imitate[Imitation and DAgger]
    Imitate --> PPO[PPO with a league]
    Scripted --> PPO
    PPO --> Learned[Learned agent]
    Traces[Game traces] --> Tuned[Tuned model agent]
    Scripted --> Gauntlet[Gauntlet and Elo]
    Learned --> Gauntlet
    Prompted --> Gauntlet
    Tuned --> Gauntlet
    Farm[Game farm] --> Gauntlet
    Farm --> Evolve
    Farm --> PPO
```

#### Doctrine by hand: the scripted agents

The decision: each scripted agent is a policy in code with named parameters (FR-44). Each version adds one thing that the probe of the games of the version before found.

- v0 moves to the objective. v1 fires at the best odds and moves to cover. v2 adds the tools of rules 22 to 27. v3 adds the vehicles of rules 28 to 41.
- v4 puts a threat map on each move: the firepower that each enemy can put on the hex. Cover makes the threat less. It assaults only a broken enemy, or with more units than the enemy.
- v5 adds the fire of the enemy vehicles to the threat map. It gives fire to the enemy that covers its own lane of advance.
- v6 is the tempo agent. The attacker keeps a schedule. The threat is in squads, and it multiplies by the number of units in the stack that moves. The defender holds the buildings that the victory conditions name.
- v7 trades on the odds (`odds.py`). It forms a fire group at the target with the highest possible loss and stops before overkill. It fires on a leader first, moves by the possible loss of each hex, and puts smoke by the same odds. A nation record selects the parameters of the role of each side.
- `armor.py` gives v3, v6, and v7 one vehicle policy. A tank drives on a route to a firing position out of panzerfaust range, it holds and fires, and it overruns only a weak target. The tanks stay near their infantry, and the squads escort a tank in contact.

The combined-arms pass (2026-10-11, v3.2, v6.3, v7.1) puts RV-9 P4, P6, P7, and P13 in that policy. A firing position pays for its distance from the own infantry, and a screened tank can stand nearer the enemy. The section bounds by halves, with one tank on watch, and the tanks fire as a section. A tank prefers a side or rear shot, and it turns its front to the largest threat.

The squads of the attacker escort a tank in contact (`escort_bonus`). The `tank_*` parameters of v7 map to `armor.ArmorParameters`, and `sl-cli evolve --only` can search them. A search of them must play scenario 4, because the other scenarios have no vehicle.

Why: an agent in code is constant, fast, and deterministic for a seed. Thus it is the opponent of each other method and the teacher of the learned family. The alternative was a learned opponent from the start. A learned opponent changes with each run, and the scripted ladder shows a defect in one game.

Where it breaks: a person writes each rule, and each rule repairs a defect that a person saw. Four attack plans of v7 (a leader with the stack, a tank base of fire, a covered approach, smoke on the route) gave no change on s04 at 200 games each. They are parameters that are off by default.

Mitigation: v7 is the strongest agent of the panel. The other methods start from it, and the gauntlet measures each change against it.

#### The odds function

`odds.py` gives the possible result of a fire group at a hex as integer counts out of 1,296: the 36 results of the fire dice by the 36 results of the morale dice. It calls the fire, modifier, and morale functions of the core, so a change to a rule changes the odds with it. It reads only the enemy units that the player can see, and a concealed target has no odds (SR-09).

Why: a person reads the odds on the table, and a number is necessary for a fire decision. The prompted family reads the same numbers in its text view (section 9.3). The host labels each legal command with them for a person (`slhost/annotate.py`).

No record names an alternative. One alternative is a sample of dice rolls through the core. A sample has noise, and it costs a full apply for each roll. The exact count costs one pass through the 1,296 results, and it gives the same number for each run.

Where it breaks: the odds read only the units that the player can see, so they are too high or too low near a concealed or hidden enemy. They read the rule helpers through `slcore.api`, so a rule that has no helper in the surface has no odds.

Mitigation: a concealed target gets no odds, and the text tells a model agent that a missing number is unknown and not zero. A new rule helper goes into `SURFACE` with its cause, and `tests/arch/test_core_api.py` holds the surface.

#### Parameter evolution

`sl-cli evolve` is a (mu + lambda) evolution strategy on the integer and boolean parameters of v7. Each candidate plays the same seeds against a fixed panel, on each side. The elites play again in each generation, because one game is noise. The best candidate is a name such as `v7[loss_scale=12,fire_floor=4]`, so a person can play it. `--only` searches some of the parameters, and `--side` searches the record of one side.

Why: v7 has approximately thirty parameters, and a change of one by hand makes a gauntlet necessary. The search does the same loop with no person in it. The alternative was CMA-ES (FR-54). The parameters are integers and booleans, and a discrete mutation moves in the units that the doctrine work used.

Where it breaks: the evolution of the s04 Axis attack found no record better than v7 (14 of 200 against 16 of 200). When the policy does not have the correct behaviour, no parameter value gives it.

Mitigation: the game farm makes a search four times faster. A search is cheap to try before a change of the code.

#### The shape study

`sl-cli shape` records the position at the end of each Movement Phase and Advance Phase of many games. A position is a picture of the board and a set of shape statistics, with the winner. The analysis gives the AUC of each statistic between the winners and the losers. It gives the increase that the shape statistics add to the material counts, in a model with cross validation. It also gives a small convolutional net on the pictures, with its occlusion map.

Why: the owner's hypothesis is that a winning position has a shape, as in Go. A shape with information becomes a parameter of the scripted agents or a term of the reward. The study reads the core and the agents, and it has no rule in it.

No record names an alternative. One alternative is a reward term or a parameter for each shape idea, with a training run or a gauntlet to measure each one. That is hours for each idea. The study measures many statistics on one recorded set of games.

Where it breaks: a statistic that separates the winners from the losers is possibly a result of the win and not a cause of it. `slshape` must have numpy, and it has no extra of its own (`docs/reports/2026-09-23_opus_review.md`, B7). No result of the study is recorded in this tree, and no parameter or reward term came from it.

Mitigation: the analysis gives the increase above the material counts with cross validation, so a statistic that only repeats the material count shows no increase. A shape that the study finds goes to a gauntlet before it goes into an agent.

#### Imitation and DAgger

`sl-cli imitate` plays games of the scripted teachers in the training environment. It fits the policy to the teachers' decisions by cross entropy on the four heads, and the value head to the returns of the games. The fit keeps the weights of the epoch with the lowest holdout cross entropy.

- `--labels 0=v7,1=v7` names the teacher that gives the label of each side. With no labels, each teacher labels its own decisions.
- `--side-weights 0=1,1=0` fits the decisions of one side only.
- DAgger rounds (Ross, Gordon, and Bagnell, 2011): the policy plays, the label teacher names its command at each state, and those decisions go into the data. Thus the net learns the states that its own errors make, and not only the states of the teacher's games.

Why: PPO from random weights did not learn scenario 1 in 1 million steps (`docs/reports/2026-09-12_training_run_1m.md`). A copy of a scripted agent is a policy that plays a full game, and it is the start of each PPO run since 2026-09-14.

Where it breaks: a copy is not better than its teacher. The best clone of each scenario is near the panel and below v7. The s04 clone of 2026-10-15 wins 46.9 percent of the gauntlet and 0 of 20 attacks against v7.

#### PPO with a league

`sl-cli train` is PPO in raw torch (FR-50, FR-51). The environment is a PettingZoo AEC environment on the core. The observation is the player view: the board as planes, a row for each unit, a scalar vector, and the masks. The policy has four heads with masks: the unit, the action, the hex, and the option.

- The reward (`reward.py`): a win pays 100, and a loss, a draw, or a truncation costs 100. Each step pays the doctrine terms of RV-9 table A with the national weights of table B.
- The league (`league.py`): the random agent, the scripted agents, and the snapshots of the learner. It gives each member a share by the loss rate of the learner against it, with a floor. `--opponents v3,v6,v7` makes the named agents the only members, and no snapshot of the learner goes into the league. A scripted member holds one agent for each side and plays the side of the frame.
- The sides (`--player 0`, `1`, or `both`): with `both`, the learner changes to the other side at each new game.
- The anchor (`--anchor-kl`): a KL term holds the policy near the frozen start policy, so the update does not cancel the clone.
- The value warm-up (`--value-warmup 100000`): the value head trains alone in the first 100,000 decisions, with the trunk and the policy heads fixed (PIRLNav). The cause: the value head of a clone has the returns of the teachers' games and not of its own games.
- Jump-Start RL (`--jump-start v7`, Uchendu and others, 2023): a guide plays the learner's side in the first `--jump-start-turns` turns of each game, and not in the last turn. When the learner wins `--jump-start-threshold` of the last `--jump-start-window` games at one horizon, the guide plays one turn less. The guide plays in the worker processes, so `--workers 2` or more is necessary. The run artifact records each change of the horizon.
- The workers (`workers.py`): each environment is a process, and the trainer selects the decisions of all workers in one batch on the GPU. The game farm adds 120 workers on four Linux hosts (`slfarm`). With `--rollout 4096 --minibatch 1024`, a run of 40,000,000 decisions gave 1,789 steps/s.
- The loss of a worker: a remote worker that stops goes out of the pool (`WorkerPool.drop`, 2026-10-16), and the run continues while 50 percent or more of its workers are live. Its last step bootstraps on its own value, and its game does not count in the league. Before this, one bad line from one host stopped all 120 workers. A local worker that stops also stops the run, because the cause is in the code of the workstation.
- The snapshots (`--snapshot-every`): the trainer writes one at each multiple of the interval and one at the last decision of the run. A run shorter than the interval kept no net before 2026-10-16.
- The timers (`ppo.CollectTiming`, 2026-10-24): the wall time of the parts of the trainer (`choose`, `idle`, `gather`, `receive`, `send`, `tail`, `update`) and the mean batch. For local and remote workers, it divides each round trip into the work in the worker, the transit, and the queue in the trainer. Each `Decision` has `work_seconds`, which the worker measures, and the farm wire carries it. The data is in `timing` in `stats.json`, in each rate report, and in the TensorBoard scalars `timing/*`.

  The cause of the timers: the speed of the two-board slots fell at each chunk, and no measure showed where the time went (2026-10-24). The first data showed that the cost of the v7 opponent in the worker was the cause.
- The stop: a run that stops at `--hours` has `stopped_because` "the hours limit" in its artifact.

The choice rule at play time (`agent.py`): the learned agent adds the probability of the legal commands of each action and plays the best command of the action with the highest sum. The joint argmax divided a move between many units and hexes, and it stopped each phase with no move (2026-10-13). The training samples the policy. Thus the training win rate and the win rate of the agent are different numbers.

In two cases the agent does not use the action first (2026-10-27):

- In the Prep Fire Phase the agent plays the command with the highest joint score (`JOINT_SCORE_PHASES`). There each unit that can fire adds to the sum of a fire action, and the end of the phase stays on one command. The L05 clone fired where the teacher stopped the phase, and a unit that fires does not move. With the joint score the v7 attack of the L03 and L07 nets increased by 3 to 4 of 100.
- A route and a stack route share one sum (`ACTION_FAMILY`). Each unit has single routes, and only a stack has stack routes. Thus with two sums a leader went forward alone and left the squads of its stack. With one sum the v7 defence increased from 52 to 93 of 100 on L04 and from 7 to 74 on L05. The attack did not change.

A third rule did not go in: an end of the Movement Phase only when its probability is more than that of all other commands together. It decreased the L03 attack from 44 to 22 of 100. On L05 the squads came near the objective with it, but v7 removed them. A better tactic is necessary for the L05 attack, and a rule of choice does not give it (`runs/exam_20261027_l05_losses/`).

Why: PPO with action masks is the method that worked on games with large legal lists (RV-5). The trainer is CleanRL style, as in the sibling projects. Each extension above comes from a run that did not learn. Self-play on one workstation is Vision bet 4.

Where it breaks: the learner wins almost no training game against a strong opponent, so the win term of the reward gives almost no signal. The s04 Axis run of 40,000,000 decisions against v7 won 0.4 percent of its training games. In the gauntlet it won 5 of 20 attacks against v7, and the clone won 0 of 20. Its Allied side became worse, because the run updated only the Axis side. Jump-Start RL against v7 did not change the horizon in 8 hours.

A league of v3, v6, and v7 (2026-10-15, 40,000,000 decisions more) gave the learner training wins: 20 percent against v6, 8.5 percent against v3, and 2.4 percent against v7. In the gauntlet the Axis won 11 of 20 against v6, equal to the panel, but 3 of 20 against v3 and 1 of 20 against v7. The learner learned to beat the member it could beat, and not the others.

A curriculum with gates (2026-10-16) adds a stronger member only after the learner beats the members before it: v6, then v3, then v7. Two chunks of 10,000,000 decisions against v6 and v3 gave a gauntlet of 58.1 percent, the best s04 net.

The Axis won 11 of 20 against v3 and 18 of 20 against v6, equal to or better than the panel. The Allied side became better too. Against v7 the Axis won 4 of 20, and the panel 20 of 60. The gate against v7 was satisfied at 18 of 50, so no chunk had v7 as a member.

Two chunks more against v6, v3, and v7 from the curriculum net (2026-10-16) gave a gauntlet of 63.7 percent. Their gate had 100 Axis games against v7. Only v7 has a higher Elo. The Axis won 10 of 20 against v7, and the panel agents won 20 of 60. The net kept its level against v3 and v6.

Chunk 5 (2026-10-16, 10,000,000 decisions more) gave a gauntlet of 66.9 percent, Elo 1743, 9 points below v7. In the gate against v7, the Axis won 46 of 100 (37 before), and the Allied side won 42 of 100 (62 before). The training updates only the Axis side, so the Allied side can become worse while the Axis becomes better.

Chunk 6 (10,000,000 decisions more) showed the limit of this method. The Axis won 49 of 100 in the gate against v7, approximately the same as chunk 5. The Allied side won 20 of 100 (42 before), and 1 of 20 in the gauntlet. The gauntlet fell to 60.6 percent, so chunk 5 stays the best net.

Chunk 7 trains the two sides from chunk 5 (`--player both`, 10,000,000 decisions). The gauntlet gave 67.5 percent, equal to chunk 5 in this sample. In the gate against v7, the Axis won 56 of 100, the best result, and the Allied side won 31 of 100 (chunk 6: 20, chunk 5: 42).

Thus the training of the two sides keeps the defence and does not decrease the attack. A chunk that trains one side must also have a gate for the other side.

Chunk 8 was 10,000,000 decisions more of the two sides. The gauntlet gave 70.6 percent and rank 1, with Elo 1787 against 1738 for v7. Against v7 in the gate and the gauntlet, the Axis won 67 of 120 and the Allied side 47 of 120. It is the first learned s04 net that ranks above each scripted agent. The method that worked: imitation, then a curriculum with gates on the attacking side, then chunks of the two sides.

Mitigation: the curriculum with gates is the method that worked. A gate needs 100 games on the side that it measures, because a gate of 50 games was satisfied by chance. Two levers are not tried: more DAgger rounds and an anchor weight that decreases.

#### The routes and the approach term (2026-10-20)

Gate item 5 of the library gave defenders and no attackers. On L01 the attack against v7 was 0 to 2 of 100 after each chunk. On L02 the imitation net won 0 of 50 attacks, and two attacker chunks gave 0 and 1 of 100. The examination of 2026-10-20 (`docs/reports/2026-10-20_attack_movement_design.md`) found the causes in the Movement Phase:

- The net moved a unit back and forth between two hexes until it had no movement points. The repeat guards did not find it. The cause: `mf_used` is a part of the position key.
- A move of the core is one hex. Thus a route of four hexes is four decisions of the net, and the net has no memory of the route. The squads stopped 12 hexes from the objective, and the teacher's squads came to 3.
- The option of a stack move is its place in the order of the hashed command IDs. Thus the net could not learn which stack an option names.
- No reward term paid a side for getting nearer to its objective. Cover and sneak paid a squad that stayed far back, at about 0.4 each turn.

The changes:

- The no-return filter (`routes.PhaseMemory`): a move into a hex that its unit held in the phase goes last in the agent and out of the masks.
- The route actions `route` and `stack_route` (`routes.py`): the net selects a destination, and the agent or the environment plays the single steps through the core. For PPO a route is one decision. The option of a stack route is the bit mask of its squads by unit ID. A snapshot with fewer actions than `stack_route` needs plays with the core commands as before.
- The labels: a run of moves of the teacher in a phase is one route row, to the last hex of the run.
- The approach term (`reward.Approach`, weight `approach` 0.2): the potential is minus the sum of the distances of the squads of a side to its objective. The side gets its change at each player turn end. A potential term does not change which policy is best (Ng, Harada, and Russell, 1999). A side with a positional condition gets cover and sneak only near its objective: `cover_radius`, 4 hexes or less.

The first measurement: the L02 imitation net with routes won 0 of 100 attacks against v7 and 69 of 100 defences. The routes play correctly, but the net does not copy the plan of the teacher: first the leader goes to the squads, and then the stack moves. The approach term is for PPO.

The PPO measurement: three chunks on L02 from that net, on the schedule of the first method. The attack against v7 after chunk 3 was 8 of 100 (the first method: 11), and the defence was 88 of 100 (the first method: 73).

The gauntlet gave 58.1 percent, rank 3 of 5 above v3 and v5 (the first method: 34.4 percent, rank 5). As the attacker the net won 35 of 60 against v3, v5, and v6 (the first method: 11 of 60), and 0 of 20 against v7. Thus the attack is better against the weaker agents, but not against v7.

Where it breaks: the path of a route is the cheapest path, not the teacher's path, so it can cross open ground where the teacher goes through cover. The s04 attacker of chunk 8 learned with the reward from before this change. The forces of s04 start nearer to each other than the forces of the library scenarios. Thus that reward is not the cause in each scenario.

#### Prompted and tuned model agents

The prompted agent reads a text view with the odds of each legal command and answers with a command identity from the legal list (section 9.3). The cycle guard offers no command that gives a position that the phase had. The `model:local*` pool sends the games to the five llama.cpp hosts. The best measure is 1 of 40 games against the scripted agents with the odds in the text. The tuned agent is the same harness with a LoRA fine-tune on the game traces and a constrained decode (section 9.4).

Why: a language model can explain its choice, and the project tests if that makes a player (Vision bet 3).

The alternative: a free text answer that the harness parses. That gives invalid moves (RV-6). The closed list of IDs and the schema make an invalid answer a retry and not a move.

Where it breaks: a model with 3 billion active parameters does not play the game at the level of v1. A local decision uses seconds, so a gauntlet of a model agent is hours long.

Mitigation: the odds in the text, the cycle guard, and the scripted fallback keep each game to a result. The local pool puts one game on each of the five hosts. The tuned family is the next lever, and it waits for its first full fine-tune on the year-one profile.

#### The measure: the gauntlet

`sl-cli gauntlet` plays a candidate against a panel on each side of each scenario. All the games go into one Elo pool, fitted with a Bradley-Terry model (`slruns.elo.settled_ratings`), with a Wilson interval on each rate. For each opponent and each side, the side baseline gives the wins of three players. They are the candidate, the other panel agents, and with `--mirror`, the opponent against itself.

Why: a scenario with one strong side hides the skill of an attacker. `--anchor-only` plays the candidate against each panel agent only, and not the panel agents against each other. A win rate against one opponent did not show that a net won only as the defender. The gauntlet is the measure of each method above. A result has 200 games or more before it is a baseline.

The mirror also balances a scenario. s04 changed on 2026-10-14 until v7 against v7 gave the Axis 832 of 1,600 games. A net or a result of s04 from before that date is of the scenario before the change.

The alternative: a single win rate against one opponent, as TC-18 gave at first. It ranked a net that won only as the defender above the panel.

Where it breaks: the Elo pool changes with the panel. A new panel gives other numbers, so two gauntlets with other panels do not compare. A gauntlet of 20 games for each side of a pair has a wide interval.

Mitigation: the report gives the Wilson interval of each rate. A baseline has 200 games or more, and a gate has 100 games on the side that it measures. The seeds of each command family are in their own range (`slruns/seeds.py`), so a gauntlet does not play the seeds of the training it measures.

## 10. Cross-cutting topics

Observability: each component writes JSON logs with a game ID, turn, phase, and player (OR-01). Each game and each training run writes a run artifact in `runs/<ISO8601-Z>-<slug>/` with `manifest.json`, `commands.json`, `log.json`, and `stats.json`. A SQLite index lists the runs (FR-56, FR-57). The trainer writes TensorBoard scalars (IR-07). The pattern comes from the LocalLLMPerf_AI sibling.

Why: a result that has no artifact is not a result (the success-claim guardrail of the project). The four files hold the seed and the command log, so a person can play each game again. The alternative is a database as the record. The SQLite index is a cache only, and `sl-cli runs --rebuild` builds it again from the artifacts.

Where it breaks: `runs/` becomes larger with each run, and git does not record it.

Mitigation: the owner deletes runs at will, and the gate reports name the artifact of each gate.

Error handling: each boundary crossing (WebSocket, provider HTTP, farm TCP, collector HTTP, file read, subprocess) has a typed exception handler with a timeout and a fallback, as in project rule 5. In the core there is no defensive code, because the core has no boundary. A rejected command is a usual result with a rule ID, not an exception.

No cause other than the absence of a boundary is recorded. The alternative is a check in each rule function, and that check costs time on each step of the throughput gate. Where it breaks: a defect in the core stops a long training run.

Mitigation: a remote worker that stops goes out of the pool (section 8.3). The invariant test finds a state with no legal command before a run (`tests/determinism/test_invariants.py`).

Security: the threat model and the controls are in `REQUIREMENTS.md` section 3. The architecture has these controls:

- The per-player view (section 4) and the host token in place of a client hash (section 8).
- The provider allowlist in `sldata/providers.json` (SR-05), and the redaction of keys from logs and traces (`slagents.prompted.keys.redact`, SR-09).
- The HMAC of a nonce on the farm, and the source hash compare (section 8.3). The farm runs no code from the network, and its wire carries no pickle.
- The signed upload with a key for each player, the time window, and the nonce check of the collector (section 8.1).

Why: each control stops one path from the threat model, and each one is in the code at the boundary where the path crosses. Where it breaks: the LAN, the farm, and the collector use plain TCP or HTTP. A machine on the same network reads the traffic.

Mitigation: the documents say that the LAN is trusted-party convenience (SR-03). The farm key does not go on the wire, and an Internet collector has TLS in front of it.

Release controls: the served page has the GPL-3 section 7 notice and the link to the source (SR-06). It has the non-affiliation notice with the public title (SR-08). The release audit (`python tools/audit_release.py`) scans the tree, the archives, the fixtures, the screenshots, and the public run artifacts. It finds key files that git does not ignore, reference-mode data, rulebook text, card text, and images that `docs/images/MANIFEST.json` does not name (SR-07, TC-29).

It also finds a local-only mark on model weights (section 9.4). The audit runs before each release.

Why: the legal research (RV-4) puts the risk in the board layouts, the rulebook text, and the card text. A person cannot read each file before each release. Where it breaks: the audit finds only the patterns it knows. A picture of a printed board with a new name is not one of them.

Mitigation: `docs/images/` is the one directory with an image. `tools/make_docs_images.py` makes each picture from code with its seed. `docs/ASSET_PROVENANCE.md` records the one file that the tool does not make.

<!-- AI review 20260907-163721: openai, the release controls -->

Data retention (DR-07): a display name in a LAN game lives in the host's memory for the session and is not written to a run artifact. Run artifacts hold agent names, versions, seeds, and game data. The owner deletes `runs/` at will, and nothing else uses it after the SQLite index is rebuilt.

The collection of played games (section 8.1) adds a record of persons. A sent game has the scenario, the seed, the commands, the key name, and the package version, and the collector also records the network address. Why: the decisions of persons are necessary for the computer players.

Mitigation: the launcher shows the consent question one time before it sends. Each player has a key of their own, and the index lets the owner remove the games of one key.

Cost: model agent cost is recorded for each call (OR-02). The estimate in RV-6 section 7 is 3 cents to 4.48 dollars for each game on SaaS models, and no money on a local model. The tournament reports cost as a column, so the owner can see it.

No cause other than OR-02 is recorded. Where it breaks: the price of a provider changes, and the record holds the price of the day. Mitigation: the pool of the five local hosts (`model:local*`) costs no money.

## 11. Module layout

```
Squad_Leader_AI/
  pyproject.toml
  src/
    slcore/                      the rules core, no side effects
      state.py                   Board, Hex, Building, Polygon, TerrainType
      game.py                    State, the frozen game record
      units.py                   UnitType and Unit
      scenario.py                Scenario, groups, set up areas, victory records
      engine.py                  Engine: new_game, legal_commands, apply, hash_state, replay
      api.py                     the public surface of the core; tests/arch checks that each
                                 consumer reads the core only through it (AR-05)
      actions.py                 the table of command handlers, one for each command action
      handlers.py                the modules that register a handler in actions.py
      turn.py                    the turn sequence and its automatic steps (AUTO_STEPS)
      windows.py                 the legal commands of each command window of PHASE_STEPS
      fire_window.py             the legal commands of the fire window of the three fire phases
      player_state.py            the state as one player may know it, for the agents (AR-09)
      commands.py                Command payloads and their canonical bytes and IDs
      frame.py                   the decision frame
      phases.py                  the phases and their sub-steps (PHASE_STEPS)
      rules/                     one module for each rule section, rule IDs in names
        r05_movement.py            movement, portage, and the Advance Phase
        r06_stacking.py            the stacking limits
        r07_los.py                 basic line of sight
        r08_fire.py                fire groups and firepower modifiers
        r10_resolution.py          the fire table, the modifiers, penetration, breakdown
        r11_terrain.py             the terrain effects modifiers
        r12_morale.py              morale checks, and the check that makes a unit berserk
        r13_rout.py                rout routes and elimination
        r14_rally.py               rally and repair
        r15_leadership.py          the leader modifiers
        r16_defensive_fire.py      the track and the return
        r18_berserk.py             the berserk charge of rule 18.42 and its movement (PR-37)
        r20_close_combat.py        close combat and melee
        r21_setup.py               set up
        r22_flamethrower.py        flamethrowers, which fire alone and with no modifier
        r23_demolition.py          demolition charges, placed in one phase and exploded in the next
        r24_smoke.py               smoke counters and the die they add to a fire group
        r25_concealment.py         concealment counters, the halved firepower, and the removals
        r26_fanaticism.py          the modifier that a place gives to a side
        r27_sewer.py               sewer movement, the lost stack, and the closed entrance
        r28_vehicles.py            the vehicle counter, the covered arc, and the target facing
        r30_vehicle_movement.py    the vehicle movement chart and the breakdown die
        r31_transport.py           passengers on a vehicle counter: one board or debark for
                                   each unit in a Movement Phase (PR-55)
        r32_afv_cover.py           the hull as a wall on the line of sight and as cover in a hex
        r33_afv_combat.py          the to-hit table, the kill table, the crew, and immobilization
        r34_afv_vs_infantry.py     the gun and the machine guns against infantry
        r35_overrun.py             the overrun: declared when the vehicle enters the hex, and
                                   resolved at the end of the Defensive Fire Phase (PR-54)
        r36_infantry_vs_afv.py     the morale check, the immobilize roll, and close combat
        r37_at_weapons.py          the flamethrower, the panzerfaust, and the bazooka
        r38_fate.py                malfunction and repair, the wreck push, and smoke
        r42_hidden.py              hidden initial placement
        r43_elevation.py           the three hill levels and the height advantage
        r44_rural.py               the wheatfield, the shellhole, and the cliff hexside
        victory.py                 the victory evaluator
      geometry.py                the exact lattice, hex math, the Cyrus-Beck clip
      los_cache.py               the static per-board thread table, lazy and memoized
      los_eval.py                the rule evaluator with the firer context and the rule 17.7 choices
      paths.py                   shortest routes in movement factors, for the rout
      tabledata.py               the fire table and the close combat table as data
      rng.py                     xoshiro128** with the golden vector test
      hashing.py                 the state hash
      events.py                  Event types with rule IDs
      view.py                    the per-player view and the board document
    sldata/                      data files with provenance notes, and loaders.py (the file boundary)
      tables/                    terrain.json, ift.json, close_combat.json, armor.json (rule 33),
                                 vehicle_movement.json (rule 30), campaign.json (Game Set IV)
      counters/                  german.json, russian.json, american.json
      scenarios/                 s00_movement_drill, s00b_combined_forces, s00c_two_board_advance,
                                 s01_guards_counterattack, s02_tractor_works,
                                 s03a_streets_of_stalingrad, s04_armor_probe, and the library
                                 lib01_grain_office to lib12_the_long_front (section 7.3)
      boards/                    fixture_10x10.json, a small board for the tests
      library/                   slots.json, the 12 slots of the library
      rulings/                   qa.json (official), project.json (project rulings with causes)
      providers.json             the provider allowlist and the ten provider rows (section 9.3)
    slboards/                    the generator and the reference loader
      generator.py               the five passes, the parameter record, and the seed retry
      edges.py                   the geomorphic constants, the edge check, and the join check
      wfc.py                     the fill pass
      tiles.py                   the tile set and the adjacency rules of a board type
      polygons.py                the terrain shapes on the exact lattice
      compose.py                 board offsets and turns on the shared lattice (FR-29)
      reference.py               loads from background/reference, not from the tree
    slhost/                      the local host
      server.py                  WebSocket host, the static file server, the computer opponent
      protocol.py                message types and the parser at the trust boundary
      rooms.py                   room codes, seats, join limits, the origin check
      annotate.py                the unit names, the labels, the hexes, and the odds of each
                                 legal entry, for a person to read
      savegame.py                the save file of each host game (runs/games), and the resume
      objectives.py              the victory conditions of each frame: the hexes, the sentence of
                                 the card, and the count of the viewer's own conditions
      options.py                 the options of one unit (options_request): why a hex refuses
                                 a counter in the set up, the hexes a unit or a vehicle gets to
                                 in the Movement Phase, the field of fire, and the steps of a
                                 move_to route
    slagents/                    the four families behind one interface
      base.py                    the Agent interface, and decide(), the one way an agent decides
      registry.py                the agents by name and the engine of a scenario by name
      scripted/                  v0.py (the baseline), v1.py (rules 1 to 21), v2.py (the engineer),
                                 v3.py (the tanker), v4.py (the doctrine agent), v5.py (the
                                 doctrine of fire), v6.py (the tempo agent), v7.py (the odds
                                 agent), armor.py (how the vehicles of v3, v6, and v7 drive
                                 and fire), engineer.py (rules 22, 23, and 27 for v4 to v7),
                                 odds.py, evolve.py (the parameter search)
      learned/                   encoding.py (the tensors and the composed command), env.py
                                 (PettingZoo AEC), nets.py (the four heads), ppo.py, league.py,
                                 reward.py (the shaped reward), imitate.py (imitation and
                                 DAgger), jumpstart.py (Jump-Start RL), workers.py (the PPO
                                 worker processes), agent.py (a snapshot as an Agent),
                                 routes.py (the route actions and the no-return filter)
      prompted/                  harness.py (the text, the guard), oddsview.py (the odds), keys.py,
                                 schema.py, router.py, providers/ (base.py, openai_compatible.py,
                                 anthropic.py, gemini.py)
      tuned/                     traces.py (the trace writer), finetune.py (LoRA), export.py (GGUF)
    slruns/                      artifact.py (the four files), index.py (the SQLite index), elo.py
                                 (ratings and intervals), seeds.py (the seed range of each command family)
    slshape/                     picture.py, features.py, record.py, analyze.py (the shape study of positions)
    slfarm/                      protocol.py (the HMAC challenge, the job check), server.py (the
                                 farm host), client.py (the job sender and the PPO bridges),
                                 envwire.py (the PPO commands and decisions as checked JSON)
    slcollect/                   the collection of played games (section 8.1): wire.py (the signed
                                 upload), keys.py (a key for each player), verify.py (the replay
                                 check), server.py (the collector), client.py (the uploader),
                                 settings.py (the data directory, the consent, the collector address)
    slwindow/                    the desktop window, a consumer of the host protocol
      app.py                     the window, the loop, the keys, and the pointer
      client.py                  the protocol client on a task of its own
      embedded.py                a host inside the same process, for one command and one window
      layout.py                  the camera: the exact lattice to pixels
      render.py                  the board: the ground, the woods mass, the building plans, the
                                 roads, the hills and their crest lines, the grain, the shell
                                 holes, and the wall, hedge, and cliff hexsides
      counters.py                the counters, the vehicle facing, and the covered arc
      silhouettes.py             the figures, the weapon icons, and the vehicle plans of a counter
      panel.py                   the scenario, the turn, the legal list, and the action log
      choice.py                  the command choice (Chooser) of the two windows, with no game library
      overlay.py                 the tactical overlay of the two windows; marks.py draws it in 2D
      logtext.py                 the text of one action log entry in the two windows
      setup.py                   the set up tray: the counters, the offered counter, the hexes
      traydraw.py                the set up tray drawn with pygame, for the two windows
      traycontrol.py             SetupTrayControl: the clicks, the drags, the pick up, and the
                                 refusal of the tray, a mixin of the two windows
      unitinfo.py                the facts of the "about this unit" box
      unitmenu.py                the rows of the menu of one unit, with no game library
      boxes.py                   the menu, the about box, and the end box, drawn with pygame for
                                 the two windows
      endgame.py                 the text of the end of a game ("You lost.") and the turn line
      victorytext.py             the text of the "Victory conditions" box
      launcher.py                the launcher of the package: the consent, the menu, the game process
      theme.py                   the colours. The browser client holds the base tone of each
                                 terrain, and a test compares the two files
    slwindow3d/                  the 3D window (Panda3D), the MVP front end; it uses the
                                 client, the overlay, the choice, and the theme of slwindow
      app.py                     the window, the camera, the keys, the pointer, and the panel
      mesh.py                    the hex prisms, lifted by the elevation of each hex
      counters.py                the 3D counters, from the same chit art as the 2D window
      indicators.py              the overlay in 3D, and the new log lines for the effects
      briefing.py                the scenario card before the game; the host starts on Begin
      tray.py                    Overlay2D: a pygame picture (the tray, a box) as a texture
                                 over the 3D board
      firekinds.py               the kind of weapon that a log line shows
      effects.py                 a short animation for each kind of fire
      sounds.py                  each sound, made by code; the vehicle is the owner's tank recording
      assets/tank_drive.wav      that recording; tools/make_tank_sound.py makes it from background/
      audio.py                   the sound board: plays the sounds of the new events
    slcards/                     card.py, the printable scenario card (section 7.4)
    slcampaign/                  the design-your-own tools and the campaign game of Game Set IV
      points.py                  the force point value of each counter
      generator.py               the random scenario construction from a seed
      build.py                   a random scenario on a board
      campaign.py                the personnel file and the scorer of rule 4
      ladder.py                  the choice of the next scenario of a campaign
      run.py                     a campaign: a sequence of scenarios from one seed
      library.py                 the candidates of the 12 library slots (section 7.3)
    slcli/                       main.py, play.py, bench.py, tournament.py, gauntlet.py, gates.py, host_cmd.py, runs_cmd.py, boards_cmd.py, agents_cmd.py, cards_cmd.py, train.py, imitate_cmd.py, evolve.py, farm_cmd.py, shape_cmd.py, traces_cmd.py, finetune_cmd.py, campaign_cmd.py, library_cmd.py, window_cmd.py, window3d_cmd.py, worker_limit.py, collect_cmd.py, launch_cmd.py, frozen_main.py (the entry of the package)
  client/                        TypeScript and Vite, with the canvas API and no other library
    src/
      board/                     geometry.ts and render.ts: the polygons, with the base tones of
                                 slwindow/theme.py
      counters/                  draw.ts and silhouettes.ts: the counters from data
      views/                     commands.ts: the legal list
      net/                       protocol.ts, protocol_schema.ts, socket.ts: the WebSocket client
      log/                       panel.ts and rules.ts: the action log panel
  tests/
    conformance/                 JSON corpus by rule family, and the armor tables
    core/                        the action table, berserk, concealment, hidden contact, and rule fixes
    engine/                      the engine contract, the frame, the golden vectors, and the scenarios
    determinism/                 replay, the command identity test, and the invariants
    los/                         property tests
    bench/                       the throughput test
    perf/                        board documents of each scenario, for the measures of time
    browser/                     Playwright
    lan/                         LAN rooms
    host/                        the annotations, the options, the save file, and the log streams
    secrecy/                     the per-player view
    providers/                   marked integration
    agents/                      the scripted, learned, and model agents
    armor/                       the covered arc, and games that play rules 28 to 41
    boards/                      the generator, the zones, the composition, and the reference loader
    window/                      the desktop window and the launcher, with a pixel check
    window3d/                    the 3D window offscreen: the board, the briefing, the effects, the sounds
    arch/                        the consumers read the core only through slcore.api, and the layers
    artifact/                    the run artifact and the SQLite index
    campaign/                    Game Set IV
    library/                     the library slots, the candidates, and the card text
    cards/                       the scenario card
    cli/                         the agent registry, the gate seeds, and the worker limit
    farm/                        the farm server, the jobs, and the PPO environments on the farm
    collect/                     the signed upload, the keys, and the collector
    shape/                       the shape study
    docs/                        the pictures of the documentation are made again and compared
  tools/                         audit_release.py (the release audit), package.py (the package),
                                 farm_deploy.py and farm_worker.sh (the farm hosts),
                                 collect_deploy.py and collect_server.sh (the collector),
                                 make_docs_images.py, make_protocol_schema.py,
                                 make_tank_sound.py, summarize_gates.py
  docs/images/                   the pictures of the documentation, and a manifest with the
                                 seed of each one. tools/make_docs_images.py writes them
  background/reference/          private, git does not record it
  runs/                          git does not record it
```

Module decomposition occurs when a file gets too large to read in one sitting, not before. The tree above is the tree as built on 2026-10-28. Slice 1 of `../tasks/todo.md` started it with `slcore/geometry.py`, `slcore/state.py`, `slcore/rules/r07_los.py`, `slcore/los_cache.py`, the terrain data file, and `tests/los/`.

## 12. Data flow: one command in hot seat

<!-- AI review 20260907-163721: openai. The client sent a view hash, which DR-04 forbids. The frame ID replaces it. -->

```mermaid
sequenceDiagram
    participant C as Client
    participant H as Host
    participant K as Core
    participant R as Runs
    C->>H: intent with frame token and command id
    H->>H: compare the token with the newest token of the connection
    H->>K: apply state and command payload and core frame
    K-->>H: new state and events
    H->>K: hash of the new state
    K-->>H: state hash
    H->>R: append payload and events to the log
    H->>K: view and frame for the active player
    K-->>H: view and decision frame
    H->>H: new token for the new state hash
    H-->>C: frame with view and legal commands and log tail and token
```

The trainer path is the same without the host. The environment calls `legal_commands`, and the policy selects a head combination that maps to a payload. The environment calls `apply`, and the events become the reward signal and the trace record. The model agent path puts the harness between the view and the command: view to text, text to the provider, answer to a command ID, ID compared against the frame.

## 13. Failure modes and what shows them

- The throughput gate is not satisfied. The benchmark (TC-09) shows it at the end of slice 3. The first response is a profile: the measurement of 2026-09-07 found that most of the cost was in the plumbing, not in the rules. The response after that is the Rust port as its own milestone, bounded by the conformance corpus.
- A rule is incorrect. The conformance corpus shows it if a case is available, and the action log shows it to a player if no case is available. The response is a new case with the rule citation, then the correction.
- A replay hash mismatch. The determinism test shows it. The cause is a side effect in the core (a dictionary iteration sequence, a float, a time call), and the correction removes it.
- A replay finds no command with the logged ID in the frame. The command identity test (TC-38) shows it. The cause is a payload field that is not canonical, or a unit ID that is not stable. The correction is in the frame builder.
- A concealed unit leaks. The secrecy test shows it. The cause is a view built for the incorrect player or a log line with the full state.
- A model agent stalls. The harness timeout shows it, and the scripted default keeps the game in motion. The record shows the cause.
- A training run diverges. The ladder shows it at 1 million steps. The response is a reward or observation change, not a longer run.
- The generator makes a board that a scenario cannot use. The zone check at scenario load shows it, with the zone that did not pass, and the client offers a new seed.
- A provider is down. The circuit breaker opens, the failover sequence moves to the next provider, and the record shows the failover.
- A fine-tune reads a reference-mode trace. The trace control test (TC-39) shows it, and the command stops before training.

## 14. Version boundary

The tiers below are the plan of 2026-09-07 with the state of each on 2026-10-28. `tasks/todo.md` holds the slices, and `VIBE_HISTORY.md` holds the gate results.

- v0.1, headless rules proof: `slcore` for rules 1 to 21, scenario 1, the first generator, the scripted agents v0 and v1, `slruns`, and the CLI `play` and `bench`. Also the conformance corpus, the determinism test, the command identity test, and the LOS property tests. Gate: TC-04, TC-05, TC-08, TC-09, TC-38. Built in slices 1 to 4.
- <!-- AI review 20260907-163721: openai, the gate after scenario 1 -->
- v0.2, browser hot seat: `slhost`, the browser client, the action log panel, the `los_request` path, the reference loader, and the zone resolution for scenario 1. Gate: BC-01, TC-23, TC-40. Built in slices 5 and 6.
- v0.3, scenarios and LAN: rules 22 to 27, scenarios 2 and 3A, concealment and the per-player view, LAN rooms, the secrecy test, the tournament, and the trace writer with `board_source`. Gate: TC-24, TC-34. Built in slices 7 and 8.
- v0.4, agents that learn: the PettingZoo environment, PPO and the league, the prompted harness, and the tuned model pipeline with the trace control. Gate: TC-18, TC-20, TC-21, TC-35, TC-37, TC-39. TC-36 is a measurement.

  The parts are built (slices 9 to 11). The prompted family has the local pool and five SaaS providers (section 9.3), and not one SaaS provider as the plan said.
- Built after the plan of these tiers: the armor rules 28 to 41 and `s04_armor_probe`, the rules 42 to 44, and board composition. Also the desktop windows, the scripted agents v2 to v7, and the game farm. Also the scenario library of 12 scenarios, the package for players, and the collector.
- RC: the last art pass, four board types, the rubrics, the release audit, and the public title. The four board types and the release audit are built.
- If the throughput gate is not satisfied: `slcore-rs`, a Rust crate with the same three functions, PyO3 and wasm-bindgen bindings, and the same corpus. The gate is satisfied (section 15), so this tier does not start.

## 15. Open questions and answers

- The throughput gate (NFR-01). Answered at the end of slice 3. On the complete scenario 1 the core gave 581 environment steps/s with one worker, 3,118 with 8, and 5,662 with 16, on a 20-core workstation. The gate of 3,500 is satisfied, so the Rust port stays closed (AR-05).
- The count of environment steps for each game. The estimate was 1,000 to 4,000 (RV-5 section 5). Two computer opponents took 924 commands for one game of scenario 1 (slice 17). A learner of the two-board library slots makes 190 to 200 steps in each game. The gate was not derived again from these numbers.
- The outline scale of the terrain polygons on the lattice. A hex side of 2 units is the scale in `slcore/geometry.py`, and the LOS conformance cases use it.
- The base model for the first fine-tune (O-06). Open. The prompted local pool uses Qwen3-30B-A3B in Q8_0 (`sldata/providers.json`), and the full fine-tune of the year-one profile did not run.
- The training workstation (O-02). The workstation has one RTX 5090. The first learned runs used an RTX 5070 (2026-09-10).
- The two project rulings on player sequence in the Rally Phase and the Close Combat declaration (section 3.1). The owner can change them, and the rulings file records the change.
- The printed Point Value Chart (O-08). Open. The point scale of `slcampaign/points.py` is the project's own.

## Appendix A: the record of the decisions

The plan of 2026-09-07 named ten architecture decision records in `docs/adr/`. That directory was not made. The decisions are in this document, each with its cause, its alternative, where it breaks, and the mitigation. `VIBE_HISTORY.md` records each decision on the day it was made, with the results that caused it.

| Planned record | Where the decision is |
|---|---|
| ADR-001: Python core first, the local host, the throughput gate, the Rust port boundary | Sections 2, 8, 14, 15 |
| ADR-002: the command model, the phase state machine, the replay hash | Sections 3, 3.2, 5 |
| ADR-003: the per-player view and concealment | Section 4 |
| ADR-004: reference mode, generated mode, zone-based set up areas | Sections 7, 7.1, 7.2 |
| ADR-005: the exact lattice, the LOS polygon test, the thread table, the rule evaluator | Section 5 |
| ADR-006: the RL observation, the composed action head, the benchmark | Sections 9.2, 9.5 |
| ADR-007: the provider policy and the local endpoint | Section 9.3 |
| ADR-008: the trace data set, the fine-tune, constrained decoding | Section 9.4 |
| ADR-009: the decision frame, the canonical payload, the command ID | Section 3.4 |
| ADR-010: the reference trace policy, `board_source`, the fine-tune control | Section 9.4 |

## Appendix B: requirement to section

<!-- AI review 20260907-163721: xai and openai, the traceability matrix -->

Each requirement ID from `REQUIREMENTS.md` and the section of this document that satisfies it. "Data" means the requirement is a data file with no design decision. "Plan" means `../tasks/todo.md` owns it.

| Requirement | Section | Requirement | Section |
|---|---|---|---|
| FR-01 | 3, 6 | FR-02 | 3.3 |
| FR-03 | 3.2 | FR-04 | 3, 3.4 |
| FR-05 | 3, 3.4 | FR-06 | 3.3 |
| FR-07 | 6 | FR-08 | 3.2 |
| FR-09 | 4 | FR-10 | 4 |
| FR-11 | 5 | FR-12 | 3.4, 5 |
| FR-13 | 5 | FR-14 | 6 |
| FR-15 | 3.1 | FR-16 | 6 |
| FR-17 | 6, vNext | FR-18 | 6, data |
| FR-19 | 6 | FR-20 | 6, data |
| FR-21 | 7 | FR-22 | 6, data |
| FR-23 | 7 | FR-24 | 7 |
| FR-25 | 7 | FR-26 | 7 |
| FR-27 | 7 | FR-28 | 5 |
| FR-29 | 7 | FR-30 | 7, client |
| FR-31 | 11, client | FR-32 | 11, client |
| FR-33 | 11, client | FR-34 | 8 |
| FR-35 | 3.3, 11 | FR-36 | 8 |
| FR-37 | 8 | FR-38 | 8 |
| FR-39 | 8, 9.1 | FR-40 | 9, 12 |
| FR-41 | 3.4, 5 | FR-42 | 4 |
| FR-43 | 9 | FR-44 | 9.1 |
| FR-45 | 9.3 | FR-46 | 9.3 |
| FR-47 | 9.3 | FR-48 | 9.3 |
| FR-49 | 9.3 | FR-50 | 9.2 |
| FR-51 | 9.2 | FR-52 | 9.2 |
| FR-53 | 9.2 | FR-54 | 9.1 |
| FR-55 | 9.3, year two | FR-56 | 10 |
| FR-57 | 10 | FR-58 | 9.4, 10 |
| FR-59 | 9.3 | FR-60 | 9.4 |
| FR-61 | 9.4 | FR-62 | 9.4 |
| FR-63 | 9.4 | FR-64 | 9.4 |
| FR-65 | 9.3 | | |
| NFR-01 | 2, 5, 14 | NFR-02 | 8 |
| NFR-03 | 14, plan | NFR-04 | 5 |
| NFR-05 | 5 | NFR-06 | 11, client |
| NFR-07 | 8 | NFR-08 | 9.2 |
| NFR-09 | 9.4 | SR-01 | 9.3, 10 |
| SR-02 | 9.3 | SR-03 | 8 |
| SR-04 | 9.3 | SR-05 | 10 |
| SR-06 | 10 | SR-07 | 10 |
| SR-08 | 10 | SR-09 | 4, 10 |
| SR-10 | 9.4 | IR-01 | 9.3 |
| IR-02 | 9.3 | IR-03 | 9.3 |
| IR-04 | 9.3, 10 | IR-05 | 9.3 |
| IR-06 | 9.3 | IR-07 | 10 |
| IR-08 | 9.4 | DR-01 | 6 |
| DR-02 | 6 | DR-03 | 7 |
| DR-04 | 3.4, 8 | DR-05 | 10 |
| DR-06 | 7 | DR-07 | 10 |
| DR-08 | 3.4, 9.4 | OR-01 | 10 |
| OR-02 | 9.3 | OR-03 | 9.2, 10 |
| OR-04 | 9.2, 10 | AR-01 | 2 |
| AR-02 | 1, 2 | AR-03 | 5 |
| AR-04 | 2, 3.2, 5 | AR-05 | 2, 14 |
| AR-06 | 8 | AR-07 | 6 |
| AR-08 | 9.3 | AR-09 | 4 |
| AR-10 | 9 | MR-01 | 3.3 |
| MR-02 | 6 | MR-03 | plan |
| MR-04 | plan | MR-05 | 10, plan |
| TR-01 | 2, 6 | TR-02 | 5, 13 |
| TR-03 | 5 | TR-04 | 2, 14 |
| TR-05 | 9.3 | TR-06 | 9.3, 9.4 |
| TR-07 | 8 | TR-08 | 8 |
| TR-09 | 4 | TR-10 | 9.2 |
| TR-11 | 14 | TR-12 | 9.4 |
| OP-01 | 11, plan | OP-02 | 8, plan |
| OP-03 | plan | OP-04 | plan |

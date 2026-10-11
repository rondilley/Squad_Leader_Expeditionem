# tasks/lessons.md - Squad_Leader_AI

Per `.claude/claude-base.md` ("Self-Improvement Loop"): durable lessons from corrections, surprises, and tries that did not succeed during this project's life. Read this file at session start.

Format for each lesson:

```
## YYYY-MM-DD - short title

What happened. What we expected. What occurred.

**Rule for next time:** the concrete change in behavior.
```

---

## 2026-10-10 - Two machines, two lines, one feature set built twice

The session built a playable 3D window, save and resume, log secrecy, log text, and odds on
this machine. The GitHub line already had each of them from 2026-09-17 to 2026-09-25, from
the Windows machine, and this machine had never had those commits. The owner found the
split only at the push. Much of the day's work was a second copy of finished work, and the
merge had to choose one of each pair.

**Rule for next time:** at session start, read `git status -sb` and
`git log --oneline HEAD..origin/main` (read-only; Claude makes no git write, so ask the
owner to fetch when the last fetch is old), and say so when the branch is behind or split,
before building. A feature the owner asks for that "was there
before" is a sign that the newer work is on another machine.

---

## 2026-09-09 - A node_modules tree from Windows has no execute bit on Linux

The client checkout had `node_modules/` from the Windows workstation. On Linux, `npm run build` gave "tsc: Permission denied". The `.bin` shims were plain files with no execute bit, not symlinks. A second `npm install` did not repair them, because the packages were in the tree before.

**Rule for next time:** After a move from Windows to Linux, delete `node_modules` and `package-lock.json`, then run `npm install` again. Do not trust an in-place `npm install` to repair the `.bin` shims. The same holds for a `.venv`: make a new one on the target system. A Windows venv has a `Scripts/` directory and `.exe` files that Linux does not run.

## 2026-09-07 - An STE word substitution inverted a requirement

The first draft of DR-06 said the reference layouts live in a folder "which `.gitignore` excludes". The STE checker flagged "excludes". The rewrite became "which `.gitignore` does not include", which says the opposite. The OpenAI reviewer in the first multi-AI pass caught it. No human read the sentence between the substitution and the review.

**Rule for next time:** After each STE substitution of a verb, read the sentence for meaning, not only for the checker. Prefer a rewrite that names the mechanism ("which `.gitignore` lists, so that git does not record it") to a one-word change. Put the checker run and a meaning check in the same step.

## 2026-09-07 - Reasoning models use the review token budget on hidden reasoning

The multi-AI review script sent `max_completion_tokens=8000` to OpenAI. gpt-5.5 and gpt-5.6-terra used all 8,000 tokens as reasoning tokens and gave an empty message with `finish_reason=length`. The script reported "Empty response", which reads like a key or model problem. A retry with `--max-tokens 40000` gave a full review.

**Rule for next time:** For a reasoning model, give the review script a completion budget of 30,000 tokens or more. When a provider gives an empty message with `finish_reason=length` and `reasoning_tokens` equal to the budget, the cause is the budget, not the key.

## 2026-09-07 - The Mistral account tier stops the large model and rate-limits the small ones

`mistral-large-latest` gave HTTP 403 "not available in your subscription tier". `mistral-medium-latest` and `mistral-small-latest` gave HTTP 429 on each of three tries with a 38,000 token prompt. The review ran with three external reviewers, not four.

**Rule for next time:** Do not count Mistral as a reviewer for large documents on this account until the tier changes. Three reviewers (Gemini, xAI, OpenAI) satisfy the minimum of the multi-AI skill.

## 2026-09-07 - The research agents use all of their web search budget

Each research agent had 200 web searches, and most used all of them, then continued with page fetches. Two agents reported that their last planned searches did not run. BoardGameGeek, Reddit, and the Squad Leader Academy site refused automated fetches for some agents.

**Rule for next time:** Give a research agent a shorter list of questions when the vector has more than six items. Or divide the vector across two agents. Tell the agent at the start which sites refuse fetches and which alternative endpoints work (for BoardGameGeek, the `api.geekdo.com` JSON endpoints).

## 2026-09-07 - A synthesis said "applied" before the edits were on disk

The second multi-AI review gave a synthesis with a section "Proposed edits, applied". The session ended before the edits were made. The next session found `docs/ARCHITECTURE.md` at v0.1 with zero annotations for that review, and the status line continued to say "before the second multi-AI review". The synthesis was the plan, not the record.

**Rule for next time:** Write the "applied" section of a synthesis after the edits are on disk. Prove it with a search for the review tag in each document that the section names. A review pass is complete when the tag count in the documents agrees with the synthesis.

## 2026-09-07 - Slice 1: lattice edge cases that the rules do not answer

Six readings went into the LOS code. Each is a project decision until the owner or a ruling changes it.

- Rule 7.1 stops the LOS when the obstacle shows on the two sides of the string. So a thread that touches a polygon vertex, or runs along a polygon edge, is not stopped. The v0.1 architecture said "touch is blocked". That was incorrect. The code and the document follow the rule text.
- Rule 17.7 gives the firer a choice when the LOS runs along a hexside. The code makes one choice for each collinear run, and different runs on one LOS get different choices. The evaluator selects the side with the smallest obstacle when no choice is given.
- Two multi-story buildings (rules 7.4 and 7.6): the blind hex reading is applied at the two ends, so the LOS is symmetric. Rule 43.8 gives symmetry only in the Scale rules, but a symmetric basic LOS keeps the property test simple.
- A LOS can go through the end vertex of a wall or hedge hexside. The code then counts that hexside as one the LOS goes through (rule 11.51). The rule text does not cover a LOS through a hexside vertex.
- Rule 7.9 lets a player select the top level or the ground level of a multi-story building for one attack. The evaluator uses the top level, which is the level that sees above obstacles. The ground-level alternative waits for rule 17 (penetration) in slice 3.
- A board has 346 hexes with its half hexes (odd-index columns have rows 0 to 10), not 330. The architecture text is corrected.

**Rule for next time:** when a rule gives a geometric condition in words, write the geometric predicate in the test case before the code. Read the rule text again after the checker rewrites the sentence.

## 2026-09-07 - Slice 2: project rulings for movement, stacking, and set up

Six project rulings went into `src/sldata/rulings/project.json` (PR-01 to PR-06). They cover the Rally Phase player sequence, the Close Combat declaration sequence, and the road hexside proxy. They also cover the reserve rule for an over-limit hex, the fixed stack for the leader bonus, and the lowest-ID unit in set up. Two items are not in the code: two leaders that carry one MMG or HMG one hex (chart note A), and the level choice of rule 7.9.

**Rule for next time:** when the rules text gives no sequence or no decision rule, write the project ruling in the data file first, with its cause. Then write the code that reads it.

## 2026-09-07 - A golden vector needs a second implementation

The C reference for xoshiro128** did not compile on this machine (the msys gcc has no headers). A JavaScript port run with Node gave the 1,000 outputs, and the Python port agreed. The command ID table came the same way: a JavaScript canonical encoder plus SHA-256. The first version of that test had invented IDs, and it did not pass.

**Rule for next time:** do not type a golden value by hand. Generate it from a second implementation in a different language. Store the source of the values in the file, and let the test read the file.

## 2026-09-07 - Slice 3: four more project rulings, and a corpus that does not test itself

Rules 8 to 21 got four more project rulings (PR-07 to PR-10). They cover the moment the core records building control and the bounded close combat target list. They also cover the hexside choice after the target hex, and the one-hex condition for machine gun penetration. Each one is in `src/sldata/rulings/project.json` with its cause.

The first version of the command identity test held IDs from a keyboard. The first conformance cases held results that came from a run of the code. Both are checks of the code against itself.

The corpus gives the rule outcome from the rule text. The harness finds a generator state that gives the dice the case names, so no seed is in a case file.

**Rule for next time:** a conformance case gives the situation and the outcome from the rules text. It does not read a value out of the code. When a case is about dice, name the dice and let the harness find a generator state that gives them.

## 2026-09-07 - Scenario 1 plays on a generated board, so its set up areas are zones

The printed board layout is not in the repository (DR-06), so scenario 1 cannot use the hex lists of the card. Its set up areas are zones on the generated city board: a stone building selected by size and position. The engine checks at construction that the areas do not overlap, and that each group fits in the limits of rule 6.1. That check found two errors in the first scenario file.

**Rule for next time:** when a scenario uses zones, validate the resolved areas at engine construction, not at set up time. A validation error names the group, and a missing legal command does not.

## 2026-09-07 - A read of the code after slice 3 found four rule defects

The tests gave zero failures and the games ran. A read of the fire code against the rules text found four defects.

- The Prep Fire counter went on when a fire group resolved. Page 41 step 2.3 puts it at the end of the phase. The counter then stopped rule 8.4, which lets a squad fire a support weapon at a second hex in the same phase.
- A weapon that fired marked its carrier as fired, which stopped the same rule.
- Rule 15.2 holds a leader in place after it gives its rating to a fire group in the Prep Fire Phase. The code let it move.
- Rules 17.6 and 20.83 make fire affect the units of the two sides. This applies in the hexes after the target of a machine gun, and in a melee hex. The code skipped the firing side in each hex.

Each defect has a conformance case in `tests/conformance/cases/rules_extra.json`.

**Rule for next time:** after a slice of rules code, read each rule of the slice against the code one time, and write a case for each difference. Green tests prove the cases that exist, not the rules that have no case.

## 2026-09-07 - A measurement is not valid across a code change

Four rule corrections went to disk during the TC-09 benchmark. Its worker processes start with a spawn, so some workers read the corrected code and some read the code before it. The run stopped, and it started again on one version.

**Rule for next time:** start a gate measurement only when the code of the tier is complete. When a change lands during a run, stop the run and start it again.

## 2026-09-07 - The first throughput number was 84 steps/s, and four memos gave 519

The first TC-09 measurement on the complete scenario 1 gave 84 environment steps/s for one worker. The movement drill gave 1,131. A profile of one game showed where the time went, and four changes took the number to 519 for one worker.

- The line of sight answer was calculated again for each pair on each frame. Scenario 1 has no smoke and no vehicle, so the board alone gives the answer for a pair. A memo on the line of sight table made it a dictionary lookup. This was the largest of the four.
- `apply` built the legal list a second time, to validate a command that the caller took from the first list. The caller can hand the frame to `apply`. The core compares the frame ID with the hash of the state, so it refuses a stale frame.
- The state hash and the command IDs are SHA-256 on a JSON document. The core calculates the state hash one time for each state, and the command ID one time for each command.
- The clip of a segment against a hex made a fraction object for each edge. The clip uses integer pairs and makes two fractions at the end.

The gate is 3,500 steps/s. One worker at 519 gives about 8,300 at 16 workers on this machine.

**Rule for next time:** measure before the architecture decision, then profile before the rewrite. The architecture named the line of sight cache as the largest lever, and the profile agreed. The profile also showed three costs that no document names. Keep the Rust decision (AR-05) closed until a profile shows the cost in the rules.

## 2026-09-07 - The throughput run found two rule defects that 100 games did not

Two of eight benchmark workers stopped with "no legal command". The core gave a frame
with no command in a state that was not at its end, so the player had nothing to do.
The 100-game run of TC-04 did not come to that state, and 399 random games from seed 1
did not come to it. The benchmark plays from other seeds and found it.

The state was a Movement Phase with a hex above the stacking limit, and the units in it
could not move. Two defects made it.

- Rule 6.1 gives the stacking limit to each player, and rule 6.2 lets the two sides
  share a hex in close combat. The code counted the units of the two sides together, so
  a shared hex read as above the limit.
- The melee record was refreshed only when a close combat attack was declared. A hex
  that the enemy left kept its melee mark, and rule 20.81 then held its units in place
  for the rest of the game. Units came into it in the Advance Phase, the hex went above
  the limit, and no unit could go out of it.

`tests/determinism/test_invariants.py` plays the seeds of the two workers and asserts
that each state gives a legal command.

**Rule for next time:** an invariant of the core is a test of the core, not a hope. "A
state that is not at its end always has a legal command" is the first one. Play from the
seed ranges the benchmark uses, and not only from seed 1.

## 2026-09-08 - Slice 5: two boundary defects that only a browser found

Each host test on a raw WebSocket gave zero failures, and the browser could not connect.
Two causes, and a raw client shows one of them.

- A browser sends an `Origin` header and a tool does not. The origin check had an empty
  allowlist by default, so it refused each browser. The host accepts the origin of the
  page it served itself, from the `Host` header, and the `--origin` option adds more. A
  tool with no origin continues to connect with the room code alone.
- A hot seat room holds one seat. A test opened a second socket from the page for a
  line of sight question. It got "the room is full" and waited for a message that did
  not come. The test uses the client's own call, which is also the real path.

**Rule for next time:** a test of a browser client runs in a browser. A raw socket
client is a good test of the protocol and a weak test of the page.

## 2026-09-08 - The action log needs a space in the markup, not in the style sheet

The log panel put the rule ID in a span with a margin and the text in the next node.
The page looked correct and `innerText` gave "21.2place weapon", so a test that looked
for a rule number with a word boundary did not find one.

**Rule for next time:** when a test reads text from a page, put the separator in the
markup. A margin is for the eye, and it is not in the text.

## 2026-09-08 - Slice 6: a set up area must say how much room is necessary

The zone set up areas of scenario 1 named a stone building by index from one end of the
board. Seed 19771001 gave each group a building it could use, and each test passed. A
measurement on more seeds found the defect immediately. On some boards the Russian
guards got a three-hex building, and twelve squads do not stack in three hexes (rule
6.1). The engine reported it at load, so no game played on a bad set up. But generated
mode was not available for those seeds.

The correction has two halves that hold the same number. The zone names the minimum
hexes for the group and the rank of the building by hex count. Thus the largest group
gets the largest building. The generator constraints have the same number, and pass 2
tests it before it gives a board.

**Rule for next time:** when a rule of the game limits what fits in a place, the data
that selects the place has the limit. And measure on the seed range, not on the seed in
the file. One correct seed hides a defect for a day.

## 2026-09-08 - Slice 7: a rule that names weapons wants data that names weapons

Rule 27.3 keeps the heavy machine gun, the mortar, the one hundred and five millimetre
gun, and the anti-tank gun out of the sewers. The first code tested a weapon class, and
the counter data gives the same class `mg` to the light, the medium, and the heavy machine
gun. So the heavy machine gun went down the ladder with the squad, and one conformance
case found it.

The counter data has a `heavy` field on each weapon the rule names, with the rule in the
provenance note of the file.

**Rule for next time:** when a rule names a set of things, the data marks that set. A
class that exists for a different purpose is not the same set, and a test that uses the
class tests the incorrect thing.

## 2026-09-08 - Slice 8: a test of two clients reads the frames, not the host state

The test of two LAN clients read the host state to find the side that moves. Then it
waited for that client to receive a frame. The host applies an intent after the send
completes, so the state the test read was one command behind. The test then sent a
command against a state that the host left. The host refused it, and the test waited for
a frame that did not come.

The two clients read the frames the host sends them. Each client keeps the identities it
read and the newest frame it holds. So a second read gives the same frame, and it does
not wait for a command that nobody sent.

**Rule for next time:** a test of a protocol reads the protocol. The internal state of
the other side is one step in front or one step behind, and a test that reads it is a
race.

## 2026-09-08 - Slice 11: a hundred games find what ten games do not

The gate of TC-15 plays a hundred games of each scenario with each agent. Its first run
gave six errors in nine hundred games, and each one was a game that did not end. Neither
cause appeared in the games of the test suite, because each cause needs a board position
that is rare.

The first cause was in the core. Rule 13.43 gives a broken unit a movement allowance for
its rout. The core gave that allowance to each rout command, and not to the phase. A unit
with two cover hexes near it then moved between them without end.

The second cause was in an agent. The Movement Phase stays open while a hex is above a
stacking limit. The core counts a sewer move as a way out of that hex, and the agent
looked for a move and a stack move only. So it answered the window with a pickup and a
drop, again and again.

**Rule for next time:** when the core keeps a window open until a condition is satisfied,
the agent and the core must agree on that condition. And a gate of a hundred games is not
a formality. It is the one test that finds a cycle in a rare position.

## 2026-09-08 - Slice 12: rule 43 must be symmetrical before it can be correct

Rule 43.8 tells us this: when A has a clear LOS to B, B has a clear LOS to A. Two ways to
apply the elevation rules broke that rule. Each one looked correct on its own.

The first was the test that stops the thread. A test that compares the level of a hex with
the level of the firer gives one answer in one direction. It gives a different answer in
the other direction. The test that holds is the height of the thread above that hex. That
height comes from the two ends together, so it is the same number from each end.

The second was the blind hex of rule 43.6. The hex behind an obstacle changes with the
direction of view, so the rule as written is not symmetrical. The correct reading is in the
words of the rule. It says "assuming a unit has sufficient height advantage", so the count
of blind hexes starts at the end with the height advantage. It does not start at the firer.

**Rule for next time:** when a rule tells us a property of itself, test that property
first. The property test found the two defects. The cases written by hand found no defect.

## 2026-09-08 - Slice 12: do not write Python through a shell heredoc

Some patch scripts in this session went through a shell heredoc, and two of them were
incorrect. One stopped on a parse error before it ran. The other ran, and it put a line
break where the source had a backslash and an n. That made a test file that Python could
not read.

**Rule for next time:** write a patch script with the file tools, then run the file. Keep a
heredoc for a short command that has no backslash and no quotation mark of its own.

## 2026-09-08 - Slice 14: a constant that no code reads is not a constant

FR-24 says that one generated board connects to each other generated board. The edge pass set
the woods half hexes and the road entries, and the check read the same two sets. So the
check passed on each board and on each pair, and the requirement did not hold. The other
edge hexes came from the fill pass, and two boards disagreed on almost all of them.

The defect stayed out of sight for six slices, because nothing put two boards next to each
other. The first composition found it in one call.

**Rule for next time:** a constant that no consumer reads is a guess. When a requirement
says that two parts connect, write the code that connects them in the slice that writes
the constant. A small piece of code will do. The check that reads only what the writer wrote proves
nothing.

## 2026-09-08 - Slice 15: a legal list is for one player, so it can hide a thing

Rule 42.5 says that a unit which walks into a hidden unit stops and goes back. That looked
like a problem for a core with one legal list. The list would have to change with the
player that reads it.

It does not. The core gives the list for the active player, and the active player is the
one that moves. So the list leaves out what that player does not know, and it is correct
for that player by construction. The information does not leak, because no other player
reads that list.

**Rule for next time:** when the design looks like it cannot hold a rule, write down who
reads the value first. A list for one reader can hold what a second reader must not see.

## 2026-09-08 - Slice 16: a new generator version breaks each scenario at one time

The generator went from version 4 to version 5, and then to version 6, in one session. Each
new version changes the seed of the random state, so each board changes. A scenario for which
five buildings in eight columns are necessary may not get them from the seed it names.

The first change gave eleven failures across four test files. The second gave twenty-one
failures and six errors across six files. In each case the cause was one thing: a scenario
could not build its board.

`tests/boards/test_every_scenario_builds.py` is that one place. It reads the scenario
directory, builds each board, and sets up each group. It also holds each scenario eight
retries below its budget, so the next change to the generator has room to move.

**Rule for next time:** when a data file carries a number that a code change can
invalidate, write the test that reads all of the directory. One clear failure is worth more
than twenty failures that each say something different.

The two tests of the engineer agent broke on the same cause, for the second time. Each one
read a single game on a single board. It then looked for a sewer entrance and a building
next to an enemy. Those are properties of the board, and the rule that the tests state is
about the agent. Each test reads six seeds and counts the events of all of them. So a new
board changes the count and it does not change the answer.

**Second rule:** a test of an agent must not read one game. The board gives the positions,
and the agent makes the decision in each one.

## 2026-09-08 - Slice 17: a text search is not proof that a document holds no table

The project recorded for two sessions that the armor tables were out of reach. The evidence
was a search of the text layer of the rulebook for two names of tables. The search found
the rules that name the tables, and no table. So the note said that the tables were on a
card that no person could read.

The four tables are on page 13 of that same rulebook. They are graphics, so they put no
words in a text layer. A text search finds no part of them. A read of the page as an
image finds all four, and each number is clear.

A second signal went by with no reader. A count of the characters on each page put page 13 at
3,421, and its neighbours held 8,000 to 10,000. A sparse page in a rulebook of two columns
is a page of pictures.

**Rule for next time:** to answer "does this document hold X", look at the pages. A text
search answers a different question: "does the text layer hold X". For a table, a diagram,
or a chart, the two questions have different answers.

## 2026-09-08 - Slice 18: a shared field has one unit, and a limit keeps the unit of its rule

Rule 37.35 gives the panzerfaust half the cost of a machine gun for portage. Portage was an
integer count of full points in nine positions, so a half point had no home.

Two answers looked equal at the start. One: give the counter a full point and give up the
rule. Two: move each of the nine positions to half points.

The second answer was correct, and one test failure showed why. The test reads the hex load
of rule 6.1 and it wants full points. That load is a number a rule gives, and the rule
gives it in full points. The sum in the function is a different thing, because it adds
costs that are not full points. So the sum moved to half points and the report kept its
full points. It rounds up, because half a point of load is load.

**Rule for next time:** when a new rule gives a fraction of a unit that the code counts in
full numbers, look at each position that reads the count. Find out if that position is a
sum or a limit. A sum moves to the smaller unit. A limit keeps the unit of its own rule,
and the conversion goes where the two touch.

## 2026-09-08 - Slice 19: a hex grid punishes an incorrect constant in two ways

Two defects of this slice were one mistake each about the lattice. Each of them was in
plain sight for a full slice.

One: the window multiplied the y value by half of the square root of three, and the
constant is that square root itself. Each hexagon was half as tall as it must be. No test
stopped, because a hexagon that is too short is a closed shape, and each test read colours
and not shapes.

Two: the east to west road took row 5 of one column and row 6 of the next. A column of an
odd index is half a hex lower on this lattice, so that gave a line of hexes two apart. The
road was 21 pieces, and no test read it as a graph.

The two are the same class of mistake. The code said what looked correct, and no test read
the property that the geometry must hold.

**Rule for next time:** for a thing that is drawn on the lattice, write the test that reads
a property of the shape. The six sides of a hexagon have one length. A road is one
connected group. A test that reads a colour finds no defect in the two of them.

## 2026-09-08 - Slice 20: a colour change can delete a requirement

The task was to make each terrain look like what the owner's boards show. The window and the
browser each held a copy of the colours, so the change touched the two files.

While the browser file changed, the hex centre dot went away with it. The dot was three
lines of code adjacent to the colours that the change replaced. No test stopped. The browser
tests count the pixels of a terrain colour, and the dot is not a terrain colour.

FR-30 makes the centre dot necessary. Item 1 of the board rubric (TC-14b) scores it. Rule
7.1 threads a line of sight from one centre dot to the next, so the dot is a fact of the
rules and not decoration. The documentation pass found it, and the code got it back. The
window had none before, so the window has one at this time.

**Rule for next time:** when you replace a group of constants, write down what the code
around them does before you write the new group. Then read the requirement for each item on
that list. A test that counts one colour does not see a shape that goes away.

A second form of the same lesson: `tests/window/test_desktop_window.py` had a building test
that counted the pixels of the outline colour. A building of one hex has a line on all four
sides. So that count is more than zero for each way that the code makes the line.

The test reads two pixels at this time. The pixel on the hexside in the building must not be
the line colour, and the pixel on the outer edge must be. A count cannot make that
difference.

## 2026-09-12 - A win rate of 50 percent was 20 draws, and a draw was a game that did not end

The TC-18 evaluation of the 1 million step run gave 42.5 to 50 percent against each
opponent. The first reading of the number said "the German side won and the Russian side
lost", because that is what each scripted agent does on that scenario. The rows of the
artifact say 0 wins, 7 losses, and 153 draws of 160. A draw in that evaluation is a game
that got to the 20,000 command limit with no result, and it counts as half a win. The
policy had learned a pickup and drop cycle, and the score column hid it.

**Rule for next time:** read the win, loss, and draw counts of an evaluation before the
score. A score of 50 percent with the sides balanced has three readings, and only the
counts tell which one it is. An evaluation that counts a truncation as half a win reports
a cycle as a draw, so the truncation gets its own count in the row.

## 2026-09-12 - A discount below one hides a cost that is far away

The second shaped run gave the command limit a cost of 100, the same as a loss, and the
policy learned the pickup and drop loop again. The run had a discount of 0.995. The limit
is twenty thousand commands away, and 0.995 to that power is zero, so the cost was not
there. The loss by the card is a few hundred decisions away, so its cost was there. The
loop was cheaper than the fight, again.

**Rule for next time:** a cost that must stop a behavior has to arrive where the behavior
is. A repeated position is a defeat on the spot, in the environment, and no discount can
hide it. Do not set a discount below one when the environment holds a cost at a far
horizon, and check each terminal cost against the discount at its distance before a run.

## 2026-09-13 - Check the geometry of the scenario against the card before you blame the agent

Three agents and four training runs failed the Russian attack of scenario 1, and each
failure got an explanation about the agent: the threat term was too large, the schedule was
wrong, the reward was sparse, the policy cycled. The tempo pass wrote down the doubt about
the set up distances and then tuned parameters for a day. The scenario file had the front on
the wrong axis, and the two sides were twice as far apart as the card puts them. The 6-2-8
has range 2. No parameter set finds an attack across six hexes of street in five turns.

**Rule for next time:** when every agent fails one side of a scenario, measure the scenario
before the agent. The distance between the set up areas, the ranges of the counters, and the
turn count are three numbers, and the card gives each of them. Compare them with what the
board gives. An agent result on a scenario whose geometry is not the card's is a result
about the board.

A second lesson from the same day: the row band and the `near` predicate were built, tested,
and left unused, with no line in the history. Code that a scenario does not read is not in
the game. Write the data file in the same session as the predicate.

## 2026-10-10 - A test fixture in the wrong shape hides a feature that never worked

The options overlay of the 3D window (`o`) read `command["action"]` from each legal entry.
The host sends `{"id": ..., "payload": {...}}`, so in a live game the overlay drew nothing.
Its test built the legal list by hand in the shape the code expected, so the test passed.
The 3D window was also called a player in its docstring ("it sends intents") and it never
sent one.

**Rule for next time:** a fixture that stands for a protocol message comes from the code that
makes that message (`DecisionFrame.to_dict`, `frame_message`), or from a real host. Do not
write the shape by hand. And a feature claim in a docstring needs a test that uses it: a
window that "plays" needs a test that plays a game through it.

## 2026-10-10 - Look at the picture, not only at the test result

The pick tests passed, and the 3D board was a mirror of the 2D board: the lattice y grows to
the south and the Panda3D world y grows to the north. The adjacency of a mirror is the same,
so every rule and every pick agreed, and each hex label read backwards. One screenshot showed
it in one second.

**Rule for next time:** after a change to a view, render it and look at it before the change
is called done. A test of a view checks what it measures; the eye checks the rest.

## 2026-10-10 - A secrecy test must cover each part of the outbound message

TC-34 checked the view of each frame and passed for a hundred games. The same frame held
the action log, the same for each seat, and the log named each hidden unit's set up hex and
each concealed unit's moves. The test covered the part of the message that had the filter,
and not the part that had none.

**Rule for next time:** a secrecy test reads the whole outbound message, each key, and not
the one document that was built for secrecy. When a message gets a new key (a preview, a
log, a hint), the secrecy test gets a check for it in the same change. And a secrecy test
must show that the game did hide something, or it can pass with nothing to find.

## 2026-10-10 - A screenshot must have the widgets of the live window

The briefing screenshot had no host frame, so the status panel of the right side was not
there, and the screenshot showed a clear Begin button. In the live window the panel comes
with the first frame and drew over the button. The owner found it in the first look.

**Rule for next time:** a picture that proves a screen must have each widget the live
window has at that time (the status panel, the buttons, the banner), made in the order the
live window makes them. A modal screen goes in its own bin over all other widgets.

# Squad_Leader_AI: Consolidated Multi-AI Architecture and Security Review

- Synthesized by: Claude Fable 5.1 (referee across the reviews below)
- Reviewers: gemini (gemini-3.1-pro-preview), xai (grok-4.3), openai (gpt-5.6-terra, on a retry with a 40,000 token budget)
- Mistral did not run. The account tier does not let the large model run (HTTP 403). The medium and small models gave HTTP 429 on each of three tries.
- Date: 2026-09-07, 16:06 to 16:10
- Material reviewed: 9 files, about 37,800 tokens, 0 secrets redacted, repository state docs-only. The eight research appendices, the reference scans, and the `.claude` folder were not sent.

## Bottom line

All three reviewers say the concept is worth the build. All three say the first milestone is too large for one developer. That is the high-confidence verdict.

Two reviewers found the same arithmetic contradiction between the training throughput gate and the single-game time bound. One reviewer found a contradiction between the Python-first core and the "no server" hot seat requirement, and I agree. One reviewer found that my STE rewrite inverted the meaning of the reference-data requirement, and I agree. The documents were not in a condition to build from. With the edits in the remediation plan, they are.

## Validated contradictions and feasibility problems

### 1. The first milestone is more than one project

Flagged by gemini, xai, and openai. I agree. The MVP tag covered the 27-rule engine, three scenarios, the generator, the client, hot seat, and LAN. It also covered three scripted agents, five SaaS adapters, a local model, PPO, a league, replay, and a 24-hour run.

Resolution: re-tier the requirements into v0.1 (headless core and throughput gate), v0.2 (browser hot seat), v0.3 (scenarios 2 and 3A, LAN, three scripted agents), v0.4 (training ladder and model agents), and a release candidate. Year one keeps all of them, in sequence.

### 2. The throughput arithmetic does not agree with itself

Flagged by gemini and openai. I agree. NFR-01 gave 3,500 steps/s with 8 to 16 workers, which is 218 to 437 steps/s for each worker. NFR-03 and TC-10 gave a 1,000 to 4,000 decision game in 2 seconds on one core, which is 500 to 2,000 steps/s. Also, "environment step" had no definition.

Resolution: one environment step is one agent decision (one PettingZoo step, one composed command or one end-phase command). NFR-03 becomes a sanity bound of 15 seconds for each game on one core. A frozen benchmark specification is added. The gate is measured on a vertical slice before the full rule set is available.

### 3. Python-first core against "no server" hot seat

Flagged by openai as critical. I agree. FR-36 said the client runs without a server, and AR-05 says the core is Python. A browser cannot run a Python core without a local process or a WebAssembly build.

Resolution: hot seat runs against a local Python host process on the owner's machine. "No server" becomes "no remote server". The WebAssembly path stays as the option if the core moves to Rust.

### 4. Integer-only arithmetic against vector LOS

Flagged by gemini. I agree that it is a design conflict. I do not accept the reviewer's alternative B (floats in the LOS function). Floats give the same results on x86 for the same operation sequence. But the project cannot prove that across a Rust port and a WebAssembly build.

Resolution: put the hex geometry on an integer lattice with scaled coordinates. Test each segment against the polygons with integer cross products. This is deterministic with no rounding. Cache the LOS result for each hex pair for each board at load time, so the per-step cost is a table lookup.

### 5. The model agent fallback target has no support

Flagged by gemini and openai. I agree. TC-16 gave a local 14B to 32B model a fallback rate below 20 percent with one retry. The WARBENCH figure for small models is up to 70 percent violations.

Resolution: retries are configurable with a default of 2. TC-16 records the rates for each model. A target applies only to the SaaS model in v0.4. The local model rate is a measurement, not a gate.

### 6. Public scenarios and private boards are two products

Flagged by openai and xai. I agree. The scenario force lists and victory conditions are facts and ship. The board layouts do not.

Resolution: two named modes. Reference mode plays the 12 printed scenarios on the private layouts on the owner's machine. Generated mode plays the same scenario data on a generated board of the same type, with set up areas that resolve by zone. The public build ships generated mode only.

### 7. The reference-data requirement said the opposite of its intent

Flagged by openai. I agree. My STE rewrite changed "which `.gitignore` excludes" to "which `.gitignore` does not include", which inverts the meaning.

Resolution: "which `.gitignore` lists, so that git does not record it". A release audit also scans built archives and run artifacts, because an ignore rule does not stop `git add -f`, screenshots, or fixtures.

### 8. Hidden information must have a per-player view

Flagged by openai as high. Gemini flagged the related problem of client-calculated hashes. I agree. If the browser receives the full state and hides units in the client, a player can read the network messages.

Resolution: new AR-09, a per-player state projection calculated by the host for each outbound message, prompt, log, and replay. DR-04 says the host calculates the state hash, not the client. A secrecy test becomes an acceptance criterion.

### 9. The rule boundary for scenario 3

Flagged by openai. I agree. The survey said scenarios 1 to 3 use rules 1 to 41. That is the "Rules Introduced" line of the scenario 3 card, and rules 28 to 41 belong to variation 3B (armor).

Resolution: the survey and the requirements say scenarios 1, 2, and 3A use rules 1 to 27. Variation 3B waits with the armor rules. A rule-by-scenario matrix goes into the architecture.

## Concept and scope: synthesized view

The reviewers agree on the thesis. One deterministic, auditable rules core is the product. The browser, LAN, training, and model agents are consumers of it. The reviewers also agree that the rules core must be derisked first. The throughput gate must be measured on a thin slice before the rule set is complete.

Reconciled tiers:

- v0.1, headless rules proof: Python core, scenario 1 rules only, one generated city fixture, one scripted agent, command log, hashes, replay, conformance corpus, and the throughput benchmark. Exit gate: 100 headless games complete, replay hashes agree, and the benchmark number is recorded.
- v0.2, browser hot seat: the client against a local Python host, pan, zoom, action log, tabletop switch, scenario 1 in hot seat. Exit gate: the owner completes scenario 1 and audits each result from the log.
- v0.3, scenarios and LAN: rules to 27, scenarios 2 and 3A, three scripted agents, the LAN host with per-player views and a room code, the tournament runner. Exit gate: a two-browser LAN game with no hidden-state disclosure.
- v0.4, agents that learn: PettingZoo environment, the learning ladder (1 million, 10 million, then 100 million steps), the snapshot league, one local model agent and one SaaS model agent with metrics. Exit gate: the ladder shows a learning signal at 10 million steps, or the core moves to Rust before 100 million.
- Release candidate: the last art pass, four board types, the look rubric, the counter rubric, the content audit, the public title.

I agree with openai's cut to one local plus one SaaS provider for v0.4. The five adapters are thin. The validation cost of five real-call tests before a release is not thin.

## Critical path and leverage

All three reviewers converge on the same load-bearing component: legal-command generation. The mask for the trainer and the list for the model agent are the same list. LOS, range, modifiers, stacking, and phase state all meet in it. The plan derisks it first, in v0.1, with LOS cached for each board.

Openai adds the right design questions. What is one command during movement, fire-group declaration, rout, and close combat? What does each player see at each sub-phase? How do optional rules enter the hash? Those go into the architecture document.

## Contested or single-reviewer items

- FR-34, the LOS tool restriction decreases playability (gemini). Real. A 2D board removes the depth cues a physical board gives. Resolution: casual mode is the default for human play, and the strict rule 19.3 mode is the option.
- TC-14 mixes a geometric test with taste (gemini). Real. Resolution: an automated geomorphic edge test plus the subjective rubric.
- One case for each rule is not conformance (openai). Real. Resolution: a conformance matrix by rule family with case types, and each case cites its source.
- TC-18 is satisfied by a weak bot (openai). Real. Resolution: frozen scripted bot versions in the run artifact, the learning ladder, and confidence intervals with side balance.
- The binding clause in section 4 is too broad (openai). Partly real. The clause comes from the family's own lessons and stays. Its scope becomes "each external service in the tier".
- Room code security (openai). Real as a framing problem. Resolution: LAN play is trusted-party convenience with no confidentiality guarantee, plus the cheap controls (a high-entropy code, an origin check, per-address connection limits).
- Provider URL as an SSRF boundary (openai). Real as a missing requirement. Resolution: SR-05 gives the allowlist as scheme plus host from the config file only, with no UI-editable URL.
- Prompts and logs can leak hidden state and keys (openai). Real. Resolution: SR-09, prompts come from the acting agent's view, and logs redact keys and headers.
- "Model agent" naming (gemini). Real. Resolution: a terms section in the requirements.
- The Rust port is not "mechanical" (openai). Fair. Resolution: the Vision says the port is bounded by the conformance battery and planned as its own milestone.

## Where the reviewers were incorrect or shallow

- openai on GPL-3. The reviewer says GPL-3 has no network disclosure duty and that the section 7 notice is an invention. The research did not claim a network-interaction duty. To send a browser bundle to a browser is to give a copy, which is conveyance in section 6. The FSF LibreJS guidance recommends the section 7 added permission for minified code.

  The item is half right, because the survey sentence was terse. Resolution: SR-06 and the survey say "conveyance of the served bundle" and "added permission", not "duty".
- openai on missing documents. The reviewer counts the absence of the architecture, README, and history files as a defect. Those are subsequent phases of the init pipeline. The review was scoped to the Vision, Requirements, and Success Criteria. Not a defect. The reviewer's point that the architecture must resolve the browser topology stands.
- xai on document drift. The reviewer says the requirements moved model agents and training to v0.2 while the Vision kept them in year one. At review time the two documents had them in the MVP. The finding was not correct for the material. After the re-tiering it becomes the right instruction.
- gemini on the 49 percent fallback arithmetic. Correct only for the 70 percent edge-model figure. The frontier figures in the same research are 6 to 14 percent. The resolution above covers the two.
- All three reviewers were shallow on the board generator. None examined if zone-based set up areas can move the printed scenarios onto generated boards. That question gives the answer: is "generated mode" a game or a demo? It goes into the architecture.

## Security posture: merged view

Threat model: one owner's workstation, a trusted LAN with a second player, and outbound calls to model providers. The merged findings, by severity:

1. Hidden information: per-player projection for each outbound message, prompt, log, and replay (openai, gemini). New AR-09 and a secrecy test.
2. Host authority: the host applies the command and calculates the hash. The client sends intent only (gemini, openai). DR-04 rewritten.
3. LAN access: trusted-party convenience, with a high-entropy room code, an origin check, and connection limits (openai). SR-03 rewritten.
4. Provider allowlist: scheme and host from the config file only (openai). SR-05 rewritten.
5. Leak paths: prompts from the agent's view, logs with keys and headers redacted, run artifacts with no opponent-hidden state (openai). New SR-09.
6. Reference data: an ignore rule is not a control. Add a release audit of archives and artifacts (openai). TC-29 extended.

No control is overclaimed after these edits. The key-file practice stays, with the note that it is a private-workstation practice.

## Efficacy, performance, and the gates

The reviewers agree that the engine-verified model agent design absorbs the failure modes the research reports. They agree that the PPO action design follows the published template. They also agree that a 100 million step run must not be the first sign of learning. The learning ladder (1 million sanity, 10 million pilot, then 100 million) and frozen bot versions become gates.

Model agents get an interactive latency budget. A decision that has a median time of more than 5 seconds makes the agent an asynchronous opponent, not a real-time one.

Gates that change: TC-01 (conformance matrix), TC-09 (benchmark specification), TC-10 (15 seconds), TC-14 (divided), TC-16 (measured, target for SaaS only), TC-18 (ladder and frozen bots), TC-20 (one SaaS provider), TC-29 (archives and artifacts), and the binding clause (scoped).

## What the reviewers say is missing

- The architecture document, with the command model, the state model, the player-view model, the browser topology, the replay schema, and the Python-to-Rust boundary (all three).
- A rule-by-scenario matrix (openai).
- A definition of "environment step" and a frozen benchmark (gemini, openai).
- A written look rubric before generator work (xai, gemini). The rubric is in the Success Criteria, and a counter rubric is added.
- A traceability table from the initial goal items (EA-1 to EA-8) to requirement and criterion IDs (openai).
- ADRs for the topology, the command model, the player view, the scenario modes, the visual policy, the RL representation, and the provider policy (openai).

## Unified remediation plan by priority

P0, before code:

1. Re-tier the requirements into v0.1 to v0.4 plus release candidate. Align the Vision's year-one list to the sequence. Files: `docs/REQUIREMENTS.md`, `docs/VISION.md`.
2. Rewrite FR-36 and AR-06 for a local Python host.
3. Give the definition of the environment step, add the benchmark specification, and set NFR-03 to 15 seconds. Files: `docs/REQUIREMENTS.md`, `docs/SUCCESS_CRITERIA.md`.
4. Rewrite NFR-05 and FR-28 for an integer lattice and a cached LOS table.
5. Add AR-09 (player view). Rewrite DR-04 (host calculates the hash), SR-03, and SR-05. Add SR-09.
6. Name the two scenario modes in FR-19, FR-21, and FR-27.
7. Correct DR-06 and extend TC-29 to archives and artifacts.
8. Correct the "rules 1 to 41" sentence in the survey and add the rule-by-scenario scope to FR-19.

P1, before the vertical slice gets larger:

9. Replace TC-01 with the conformance matrix. Add the learning ladder to TC-18. Make TC-16 a measurement. Divide TC-14. Scope TC-20 to one SaaS provider. Scope the binding clause.
10. Make casual mode the FR-34 default.
11. Add the terms section and the EA traceability appendix.
12. Write `docs/ARCHITECTURE.md` with the command model, the player-view model, the topology, the replay schema, the rule-by-scenario matrix, and the ADR list. This is the next pipeline phase.

P2, before a public release:

13. A counter originality and readability rubric.
14. A content provenance record for each table, counter value, ruling, and art asset.
15. A legal review by a lawyer of the name, the board style, and the counter composition.

## Proposed revised scope

v0.1 ships the headless rules proof and the throughput number. Nothing else. The tiers above follow.

## Open questions for the team

- Can zone-based set up areas move the 12 printed scenarios onto generated boards sufficiently for a game? A prototype on scenario 1 gives the answer in v0.2.
- Which SaaS provider is the one for v0.4? Recommendation: Anthropic, because the key is in place and the structured-output mode is documented.
- What is the training workstation (CPU cores, GPU)? The benchmark specification must name it.

## Final judgment

Worth the build. The engine, not the client or the agents, is the product. The reviews are unanimous that the engine must be built and measured first. With the P0 edits applied, the documents describe a plan a solo developer can complete in sequence. Without them, the project would build breadth before fidelity and find the topology and throughput contradictions in code.

# RV-6: LLM agents as players of turn-based strategy board games

Research vector RV-6 for Squad_Leader_AI.
Fetch date for all web sources: 2026-09-07.

Rules of evidence: each claim has a source URL. I made sure that each arXiv ID agrees with the arXiv abstract page. I dropped items for which I could not find a source that I could open. Cost figures in section 7 are estimates.

Scope note: the web search budget for this session ended after about 25 searches. All subsequent work used page fetches. Two gaps stay open. I show them in the text: the OpenAI structured-output numeric schema limits (the doc page was truncated by the fetch tool) and the full CICERO Science citation (science.org returned HTTP 403, the DOI is given).

---

## 1. Benchmarks and papers, 2023-2026

### 1.1 General game-agent benchmarks

| Benchmark | arXiv | Games | Models tested | Result on tactical competence | Failure modes named |
|---|---|---|---|---|---|
| SmartPlay | 2310.01557 (Oct 2023, v5 Mar 2024) | Two-armed bandits, rock-paper-scissors, Tower of Hanoi, Messenger, Crafter, Minecraft | GPT-3.5/GPT-4 class (see paper) | LLMs "significantly underperform humans in many SmartPlay games" | Planning, spatial reasoning, randomness, learning from mistakes |
| GTBench | 2402.12348 (Feb 2024) | 10 game-theoretic tasks (board and card games, complete and incomplete information) | GPT-4, CodeLlama-34b, Llama-2-70b, Llama-3-70b-Instruct | LLMs "fail in complete and deterministic games yet they are competitive in probabilistic gaming scenarios". Code pretraining helps. CoT and ToT "do not always help" | Weak in deterministic complete-information games |
| GameBench | 2406.06613 (Jun 2024) | 9 games chosen so strategy text is rare in pretraining data | GPT-3, GPT-4, with CoT and RAP scaffolds | "none of the tested models match human performance, and at worst GPT-4 performs worse than random action". CoT and RAP "improve scores but not comparable to human levels" | Below random in some games |
| BALROG | 2411.13543 (Nov 2024, ICLR 2025) | BabyAI, Crafter, TextWorld, Baba Is AI, MiniHack, NetHack | Claude 3.5 Sonnet, GPT-4o, Llama 3.1 8B/70B, Llama 3.2 1B/3B/11B/90B, Gemini 1.5, GPT-4o Mini | Average progress (language-only): Claude 3.5 Sonnet 32.64%, GPT-4o 32.34%, Llama 3.1 70B 27.88%, Llama 3.1 8B 15.14%, Llama 3.2 3B 10.13%. NetHack: o1-preview 1.57%. Vision input made most models worse (GPT-4o 32.34% to 22.56%) | "knowing-doing gap". Invalid actions get engine feedback. Agents do not "place objects adjacent to other objects" and do not succeed in confined-corridor combat |
| CivRealm | 2401.10568 (Jan 2024) | FreeCiv (Civilization) | RL and LLM agents | "RL-based and LLM-based agents struggle to make substantial progress in the full game" | Long-horizon, imperfect information |
| TextArena | 2504.11442 (Apr 2025) | 57+ competitive text games, TrueSkill leaderboard | Any model, online play | Framework, used in SPIRAL self-play training | (framework paper) |
| lmgame-Bench | 2505.15146 (May 2025, ICLR 2026) | Sokoban, Tetris, 2048, Candy Crush, Super Mario, Ace Attorney | 13 models incl. o3, o1, Gemini-2.5-pro, Llama-4-Maverick | "40% of game runs without the harness fail to outperform a random-play baseline". With perception and memory harness "86.7% of game runs beat the random baseline". Llama-4-Maverick: Sokoban 0.0 | Brittle vision, prompt sensitivity, data contamination |
| DSGBench | 2503.06047 (Mar 2025) | 6 strategic games | 6 LLM agents, open and closed | Five-dimension scoring and decision tracking | (abstract only) |
| Game Reasoning Arena | 2508.03368 (Aug 2025) | OpenSpiel board and matrix games | liteLLM for API models, vLLM for local models | Framework that compares LLM agents to random, heuristic, and RL agents | (framework paper) |

Sources: https://arxiv.org/abs/2310.01557 , https://arxiv.org/abs/2402.12348 , https://arxiv.org/abs/2406.06613 , https://arxiv.org/abs/2411.13543 , https://arxiv.org/html/2411.13543 , https://balrogai.com/ , https://arxiv.org/abs/2401.10568 , https://arxiv.org/abs/2504.11442 , https://arxiv.org/abs/2505.15146 , https://arxiv.org/html/2505.15146 , https://arxiv.org/abs/2503.06047 , https://arxiv.org/abs/2508.03368

BALROG leaderboard (balrogai.com, fetched 2026-09-07) open-weight rows: DeepSeek-R1 34.9% (2025-04-10), Llama-3.1-70B-it 27.9%, Llama-3.2-90B-it 27.3%, Llama-3.3-70B-it 23.0%, Mistral-Nemo-it-2407 17.6%, Qwen2.5-72B-it 16.2%, Qwen2-VL-72B-it 12.8%.

### 1.2 Diplomacy, social deduction, StarCraft, Pokemon

- CICERO (Meta FAIR, Science 2022, DOI 10.1126/science.ade9097, PubMed 36413172).
  - 40 games in an online Diplomacy league. "more than double the average score of the human players" and "top 10% of participants who played more than one game". 
  - CICERO is not a pure LLM player: it pairs a language model with a planning and RL strategic-reasoning module. 
  - The parameter count of 2.7B comes from the search summary only. The Meta research page does not give it. Record the parameter count as unverified in this session. Source: https://ai.meta.com/research/cicero/
- Democratizing Diplomacy harness, arXiv 2508.07485 (Aug 2025).
  - 16 models from 9B to o3. Invalid order rate (rejected by the engine) "6-14% across tested models". 
  - Retry one time, then default action ("hold for movement, no communication for negotiation").
  - Text state includes unit-level "nearest enemy units, uncontrolled supply centers, and adjacent territory details". 
  - A 24B model completes full games at about "$1 per game with inference providers". Larger models score higher, with o3 and Kimi-K2 at the top.
  - Source: https://arxiv.org/abs/2508.07485 , https://arxiv.org/html/2508.07485
- AI Diplomacy (Every / GoodStartLabs, 2025). 
  - Frontier models play full-press Diplomacy. A sample game log shows 91 invalid moves for o3 and 67 for claude-sonnet-4. Source: https://github.com/EveryInc/AI_Diplomacy (the every.to article returned HTTP 404 on fetch).
- Werewolf with LSPO, arXiv 2502.04686 (Feb 2025, ICML 2025). Maps free-form text into a finite latent strategy space, runs CFR, then DPO fine-tunes the LLM. Agents "outperform existing Werewolf agents". Source: https://arxiv.org/abs/2502.04686
- Avalon agent society, arXiv 2310.14985 (Oct 2023). Not fetched in this session, listed from search results only.
- TextStarCraft II, arXiv 2312.11865 (Dec 2023). Chain of Summarization of text observations.
  - LLM agents beat the built-in AI at Harder (Level 5). Experts rated play like "an average player who has played StarCraft II for eight years". Source: https://arxiv.org/abs/2312.11865
- PokeLLMon, arXiv 2402.01118 (Feb 2024). In-context RL from battle feedback, knowledge-augmented generation against hallucination, and a fix for "panic switching". 49% ladder win rate and 56% in invited battles against humans. Source: https://arxiv.org/abs/2402.01118

### 1.3 Chess and Go with LLMs

- Acher, "Debunking the Chessboard" (blog, 2023-09-30), 858 games.
  - gpt-3.5-turbo-instruct: about 1750 Elo, illegal move in 16% of games and 0.3% of moves.
  - gpt-4 (chat): about 1305-1371 Elo, illegal move in 32% of games.
  - gpt-3.5-turbo (chat): 93% of games had an illegal move.
  - Source: https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/
- Acher, "GPT-5 ... Illegal Move After 4th Turn" (2025-08-07). GPT-5 and GPT-5 Thinking make the illegal move 4.exf7+ on a fixed 4-move line, as did GPT-3.5, GPT-4, o3, o4-mini. The author cautions that it is one position and "should not be too much interpreted". Source: https://blog.mathieuacher.com/GPT5-IllegalChessBench/
- dynomight, "OK, I can partly explain the LLM chess weirdness now" (updated Nov 2024).
  - gpt-3.5-turbo-instruct plays at about 1750 Elo. Chat models play at a low level.
  - Prompt fixes: make the model write the full move list again first ("regurgitation"). Then give three in-context examples. 
  - gpt-4o then gets to about 1540 Elo.
  - A list of legal moves in the prompt made play worse.
  - Source: https://dynomight.net/more-chess/
- I did not find a Go-specific LLM paper with a source that I could open in this session. Dropped.

### 1.4 Military and wargame papers

- Escalation Risks from Language Models in Military and Diplomatic Decision-Making, arXiv 2401.03408 (Jan 2024, ACM FAccT 2024). Five off-the-shelf LLMs in a turn-based nation-agent wargame. "all five studied off-the-shelf LLMs show forms of escalation and difficult-to-predict escalation patterns". Source: https://arxiv.org/abs/2401.03408
- Human vs. Machine: Behavioral Differences Between Expert Humans and Language Models in Wargame Simulations, arXiv 2403.03407 (Mar 2024). 214 national-security experts compared with LLMs in a US-China crisis game. LLMs "more aggressive and significantly affected by changes in the scenario". Source: https://arxiv.org/abs/2403.03407
- Open-Ended Wargames with Large Language Models ("Snow Globe"), arXiv 2404.11446 (Apr 2024). LLM system for qualitative (free-text) wargames, not discrete-move games. Source: https://arxiv.org/abs/2404.11446
- WGSR-Bench, arXiv 2506.10264 (Jun 2025). Wargame-based strategic reasoning benchmark on the MiaoSuan platform (more than 400,000 battle replays, 225 scenarios, 3v3 to 30v30).
  - Situation awareness: humans 79.9 compared with best model (Doubao-v1) 58.2.
  - Opponent modeling: professional humans 85.7 compared with DeepSeek R1 49.1, Qwen3 47.9.
  - Policy generation: elite humans 92.3 compared with GPT-4.1 60.0, Gemini 2.5 30.0.
  - Coalition coordination: humans 94.2 compared with GPT-4.1 61.2.
  - Source: https://arxiv.org/abs/2506.10264 , https://arxiv.org/html/2506.10264
- Shall We Play a Game? Language Models for Open-ended Wargames, arXiv 2509.17192 (Sep 2025, rev. Jul 2026). 
  - Scoping review of 223 papers. Only 20 of 223 let the LLM control player actions and also adjudication.
  - The authors argue that the adjudicator (world model) role and the player role are two different evaluation tasks.
  - Source: https://arxiv.org/abs/2509.17192
- WARBENCH, arXiv 2603.21280 (Mar 2026). 
  - 136 historical tactical scenarios, nine models.
  - Tactical reasoning "systematically collapses with complex terrain and high force asymmetry". Small edge models had "legal violation rates approaching 70 percent".
  - "catastrophic performance degradation under 4-bit quantization". Explicit reasoning was a "highly effective structural safeguard". Source: https://arxiv.org/abs/2603.21280
- Geo-Commander: "A framework of large language model commander agent for spatial reasoning in combat simulation", Scientific Reports, 2026-03-13, DOI 10.1038/s41598-026-43365-3.
  - Hex-grid tank-detachment wargame (maps 13x23 to 100x100 hexes, 200 m for each hex).
  - Hex encoding: offset column and row coordinates, elevation in 5 m steps, terrain class for each hex. ReAct loop with a "Geo-Choice" hex pre-screen.
  - Models: GPT-4V, Qwen-VL-Max, ERNIE-4.5-Turbo-VL, DeepSeek-VL2.
  - Beat the prior AlphaWar agent on win rate across four terrains.
  - Cost: "3,000-3,500 tokens per decision cycle" and "40-50 seconds per cycle".
  - Source: https://www.nature.com/articles/s41598-026-43365-3
- Hierarchical Control in Multi-Agent Games: LLM-based Planning and RL Execution, arXiv 2606.20014 (Jun 2026). LLM as high-level controller above RL skill policies in a 2v2 King of the Hill game. LLM+RL 46.4% compared with behavior tree 51.5% (p=0.103, not different). The two agents beat flat RL. Source: https://arxiv.org/abs/2606.20014

### 1.5 Summary of failure modes across the papers

1. Illegal or invalid moves. 6-14% invalid orders in Diplomacy with a strong text harness (2508.07485). 16-93% of chess games had an illegal move as a function of the model (Acher 2023). up to about 70% legal violations for small edge models in WARBENCH.
2. Hallucinated state and the "knowing-doing gap" (BALROG): the model knows a rule in a question but does not apply it in play.
3. Spatial reasoning. BALROG: cannot place objects adjacent to targets, does not succeed in corridors. The Geo-Commander authors built it because LLMs "struggle significantly with dynamic decision-making tasks involving spatial elements". WARBENCH: collapse with complex terrain.
4. Vision input decreases scores. BALROG: most models did worse with images than with text.
5. Chat tuning decreases the level of play. Chess: instruct completion model 1750 Elo compared with chat models far lower (Acher, dynomight).
6. Quantization decreases scores. WARBENCH: catastrophic at 4-bit. This is important for local 7B-32B GGUF models.

---

## 2. Agent architectures that work

Evidence, ordered from strongest to weakest for a hex wargame:

| Pattern | Evidence | Effect |
|---|---|---|
| Engine enumerates legal moves. LLM picks. engine verifies. retry then scripted default | Diplomacy harness 2508.07485: retry on malformed or invalid, then default "hold". BALROG: engine feedback on invalid action. | Games always get to the end. The design absorbs the 6-14% invalid rate. This is the "LLM proposes, engine verifies" pattern. |
| Rich unit-level tactical annotations in the text state (nearest enemy, reachable objectives, path costs) | Diplomacy harness: state includes "nearest enemy units, uncontrolled supply centers, and adjacent territory details" and shortest paths. Geo-Commander: explicit hex coordinates, elevation, terrain for each hex, plus a hex pre-screen module. | Lets a 24B model finish full Diplomacy games, and Geo-Commander beat AlphaWar. |
| Perception and memory scaffold (harness) | lmgame-Bench: runs beating random go from 60% to 86.7% with harness. | Large improvement, model-independent. |
| ReAct (reason then act, interleaved) | ReAct 2210.03629: +34% absolute on ALFWorld, +10% on WebShop compared with imitation and RL baselines. Geo-Commander uses ReAct. | Standard baseline loop. |
| Chain-of-thought and Reasoning-with-Planning (RAP) | GameBench: CoT and RAP "improve scores but not comparable to human levels". GTBench: CoT and ToT "do not always help". WARBENCH: explicit reasoning is a "highly effective structural safeguard". | Helps on average. not a fix. |
| Reflection memory across episodes | Reflexion 2303.11366: 91% pass@1 HumanEval compared with GPT-4 80%, and sequential decision tasks. ExpeL 2308.10144: insights retrieved at inference, improvement with experience. PokeLLMon: in-context RL from battle feedback. | Low cost, no weights change. |
| Retrieval of rules or knowledge text | SPRING 2305.15486: GPT-4 with the Crafter paper as input "outperforms all state-of-the-art RL baselines, trained for 1M steps, without any training". PokeLLMon: knowledge-augmented generation decreases hallucination. | Strong for rule-heavy games such as Squad Leader. |
| LLM planner above a scripted or RL executor | Hierarchical LLM+RL 2606.20014: equal to a behavior tree, better than flat RL. CICERO: LM plus planning/RL module reached top 10% of humans. | Executor guarantees legality, LLM supplies intent. |
| Structured JSON output with schema enforcement | Vendor docs (section 3). "Let Me Speak Freely?" 2408.02442: "significant decline in LLMs reasoning abilities" with format restrictions, and "stricter format constraints generally lead to greater performance degradation in reasoning tasks". | Guarantees parseable output. Do the reasoning in free text first, then emit JSON, or use a two-call design. |
| Legal-move list in the prompt | dynomight (chess): listing legal moves made gpt-4o play at a lower level. Diplomacy harness and BALROG list available actions and also get invalid moves. | Mixed for strength. Use the list for validation and constrained choice, not as the only prompt content. |
| Move regurgitation and few-shot examples | dynomight: gpt-4o from a low level to about 1540 Elo with "repeat the move list" plus three examples. | Low cost and large improvement in chess. |

Sources: https://arxiv.org/abs/2508.07485 , https://arxiv.org/html/2505.15146 , https://arxiv.org/abs/2210.03629 , https://arxiv.org/abs/2406.06613 , https://arxiv.org/abs/2402.12348 , https://arxiv.org/abs/2303.11366 , https://arxiv.org/abs/2308.10144 , https://arxiv.org/abs/2305.15486 , https://arxiv.org/abs/2402.01118 , https://arxiv.org/abs/2606.20014 , https://arxiv.org/abs/2408.02442 , https://dynomight.net/more-chess/ , https://www.nature.com/articles/s41598-026-43365-3

---

## 3. Structured output support across providers (docs fetched 2026-09-07)

### SaaS

| Provider | Mechanism | Doc URL | Limits given on the page |
|---|---|---|---|
| Anthropic Claude | `output_config.format` with `type: "json_schema"` (old `output_format` beta field deprecated, Python SDK v1.0+ rejects it), and `strict: true` on tools for validated tool inputs. Models: claude-fable-5-1, claude-opus-5, claude-sonnet-5, claude-haiku-4-5-20251001 and others listed. | https://platform.claude.com/docs/en/build-with-claude/structured-outputs | `additionalProperties` must be `false`. Not supported: recursive schemas, external `$ref`, `minimum`, `maximum`, `multipleOf`, `minLength`, `maxLength`, `minItems` other than 0 or 1, and non-primitive enums. Compiled grammar cached 24 hours, so the first request is slower. |
| OpenAI | `text.format` = `{type: "json_schema", strict: true, schema}` (Responses API). Available from GPT-4o and subsequent models, the page recommends `gpt-6-astra` for new projects. | https://developers.openai.com/api/docs/guides/structured-outputs | `additionalProperties: false` and all properties in `required`. Page says "some features are unavailable". GAP: the numeric limits (nesting depth, property count) live in the "Supported schemas" section, which the fetch tool cut. Not reported here. |
| Google Gemini | `response_format` with `type`, `mime_type: "application/json"`, `schema`. Supported keywords: types, `properties`, `required`, `additionalProperties`, `enum`, `format`, `minimum`, `maximum`, `items`, `prefixItems`, `minItems`, `maxItems`. | https://ai.google.dev/gemini-api/docs/structured-output | "Very large or deeply nested schemas may be rejected" and "Not all JSON Schema features are supported". No numeric limits given. |
| Mistral | `response_format` set to a schema (SDK `client.chat.parse()` with Pydantic, Zod, or JSON schema). Mistral prepends "Your output should be an instance of a JSON object following this schema". Also plain JSON mode. | https://docs.mistral.ai/studio/conversations/structured-output/custom | The fetch tool cut the page, so the "which models support custom structured outputs" FAQ answer was not in the fetched text. |
| xAI Grok | `response_format.type = "json_schema"` with `response_format.json_schema`, or `json_object`, on the Grok 4 family for structured outputs with tools. | https://docs.x.ai/docs/guides/structured-outputs | Guaranteed: `minLength`/`maxLength` up to 2,048, `minItems`/`maxItems` up to 256, `minProperties`/`maxProperties` up to 64. Rejected: empty `enum`/`anyOf`, `items` as array, `maxContains`/`minContains`. Best effort only: `not`, `if/then/else`, multi-schema `allOf`, and no regex backreferences or lookaround. |

### Local (OpenAI-compatible HTTP)

| Server | Mechanism | Doc URL | Limits given |
|---|---|---|---|
| llama.cpp llama-server | `/completion`: `grammar` (GBNF) or `json_schema`, and `/v1/chat/completions`: `response_format` as `{"type":"json_object"}`, `{"type":"json_object","schema":{...}}`, or `{"type":"json_schema","schema":{...}}`. The server converts the schema to GBNF. | https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md and https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md | Supported: types, `minLength`/`maxLength`/`pattern`, integer `minimum`/`maximum`, `minItems`/`maxItems`, `required`, `$ref` (local), `anyOf`/`oneOf`, `enum`. Not supported: `uniqueItems`, `contains`, `if/then/else`, `not`, `patternProperties`, nested `$ref`, `prefixItems`, number-type min/max, email and URI formats. `additionalProperties` defaults to false. Grammar guarantees syntax, it does not stop truncation at `max_tokens`. |
| Ollama | `format` field takes `"json"` or a JSON schema object. | https://docs.ollama.com/capabilities/structured-outputs | "Ollama's Cloud currently does not support structured outputs." The doc says to also put the schema in the prompt and use temperature 0. |
| vLLM | `structured_outputs` dict with `json`, `regex`, `choice`, `grammar`, `structural_tag`. OpenAI `response_format` also accepted. Backends: xgrammar, guidance, outlines, default `auto`. Old `guided_json` fields removed in v0.12.0. | https://docs.vllm.ai/en/latest/features/structured_outputs.html | With reasoning models, structured output can be disabled unless reasoning is parsed out, flag `--structured-outputs-config.enable_in_reasoning=True`. The regex dialect is not the same for each backend. vLLM has no official Windows support (from project memory, 2026-07). |
| LM Studio | `response_format.json_schema`. GGUF models use llama.cpp grammar sampling, MLX models use Outlines. | https://lmstudio.ai/docs/app/api/structured-output | "Not all models are capable of structured output, particularly LLMs below 7B parameters." Output is a JSON string in `message.content`, your code must parse it. |

Consequence for the design: keep the move schema flat (one object, string enums for move IDs, no recursion, no numeric ranges) so that one schema works on Anthropic, llama.cpp, and the others without edits.

---

## 4. Local model capability and cost

### 4.1 Which open-weight models play games acceptably at 7B-32B

- BALROG (2411.13543): Llama 3.1 8B 15.14% average progress compared with Llama 3.1 70B 27.88% and Claude 3.5 Sonnet 32.64%. An 8B model is at half the frontier score. Llama 3.2 3B 10.13%, 1B 6.65%.
- Diplomacy harness (2508.07485): "24B parameter models can complete full games". Mistral-Small-3.2-24B, qwq-32b, and GLM-4.1v-9B were in the small tier. "larger models perform best while smaller ones also play competently". invalid order rate 6-14% across all sizes.
- lmgame-Bench (2505.15146): Llama-4-Maverick (a large MoE) got 0.0 on Sokoban also with harness. spatial puzzle play is weak in open models tested.
- GTBench (2402.12348): Llama-3-70b-Instruct closes the gap to GPT-4. Llama-2-70b and CodeLlama-34b did not.
- WGSR-Bench (2506.10264): DeepSeek R1 49.1 and Qwen3 47.9 compared with professional humans 85.7 on opponent modeling.
- WARBENCH (2603.21280): "catastrophic performance degradation with 4-bit quantization" and up to about 70% legal violations for small edge models. Prefer Q5/Q6/Q8 or FP8 for the agent model when VRAM is sufficient.
- SPIRAL (2506.24119): Qwen and Llama models from about 3B to 7B (incl. DeepSeek-R1-Distill-Qwen-7B) went through self-play training on TicTacToe, Kuhn Poker, and Simple Negotiation with TextArena. up to +10% on 8 reasoning benchmarks. Shows 7B-class models can get game self-play training on modest hardware.
- No verified source in this session ranks Qwen 3, Gemma 3, or gpt-oss on a game-agent benchmark at 7B-32B. Treat that as a gap to measure in-project.

### 4.2 Tokens/s on RTX 4090 / 5090 (llama.cpp)

| Source | Hardware and build | Model and quant | Prompt processing | Generation |
|---|---|---|---|---|
| llama.cpp discussion #15013 "Performance of llama.cpp on Nvidia CUDA" (opened 2025-08-01. `llama-bench -m llama-2-7b.Q4_0.gguf -ngl 99 -fa 0,1`) | RTX 4090, flash attention on | Llama 2 7B Q4_0 | pp512 14,770.63 +/- 102.93 t/s | tg128 188.96 +/- 0.05 t/s |
| same | RTX 5090, flash attention off | Llama 2 7B Q4_0 | pp512 14,073.41 +/- 115.16 t/s | tg128 290.02 +/- 1.10 t/s |
| hardware-corner.net RTX 5090 benchmarks (2025-11-06. llama-bench build 466c1911. EPYC 7642, Ubuntu 24.04) | RTX 5090 32 GB | Qwen3 8B Q4_K_XL | 10,406 t/s at 4K ctx | 186 t/s at 4K, 112 t/s at 32K |
| same | RTX 5090 | Qwen3 14B Q4_K_XL | 6,498 t/s at 4K | 124 t/s at 4K |
| same | RTX 5090 | Qwen3 30B-A3B MoE Q4_K_XL | 6,630 t/s at 4K | 234 t/s at 4K, 111 t/s at 32K. 52 t/s at 147K ctx (31 GB VRAM) |
| same | RTX 5090 | Qwen3 32B dense Q4_K_XL (18.64 GiB) | 2,931 t/s at 4K | 61 t/s at 4K, 44 t/s at 32K |
| same | RTX 5090 | gpt-oss-20B Q4_K_XL | 9,444 t/s at 4K | not reported |

Sources: https://github.com/ggml-org/llama.cpp/discussions/15013 , https://www.hardware-corner.net/rtx-5090-llm-benchmarks/

Implication for one 6,000-token agent call (section 7): prompt processing is 0.5-2 s and a 300-token JSON answer is 1.5-5 s on an RTX 5090, for 8B to 32B dense models at Q4. A 64-call game uses about 3-8 minutes of GPU time. Electricity is the only added cost.

---

## 5. SaaS model IDs and prices (fetched 2026-09-07, USD for each million tokens)

### Anthropic (https://platform.claude.com/docs/en/about-claude/pricing)

| Model | Input | 5m cache write | 1h cache write | Cache read | Output | Batch in/out |
|---|---|---|---|---|---|---|
| Claude Fable 5.1 (`claude-fable-5-1`) | $10 | $12.50 | $20 | $0.25 (0.025x) | $50 | $5 / $25 |
| Claude Opus 5 (`claude-opus-5`) | $5 | $6.25 | $10 | $0.50 | $25 | $2.50 / $12.50 |
| Claude Sonnet 5 (`claude-sonnet-5`) | $2 | $2.50 | $4 | $0.20 | $10 | $1 / $5 |
| Claude Sonnet 4.6 | $3 | $3.75 | $6 | $0.30 | $15 | $1.50 / $7.50 |
| Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) | $1 | $1.25 | $2 | $0.10 | $5 | $0.50 / $2.50 |

Notes from the page:

- Batch is 50% off input and output. Cache multipliers stack with batch.
- Minimum cacheable prompt: 512 tokens (Fable 5.1, Opus 5), 1,024 tokens (Sonnet 5, Sonnet 4.6, Opus 4.8), 4,096 tokens (Haiku 4.5, Opus 4.6, Opus 4.5). Source: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Claude 4.7 and subsequent models use a tokenizer that yields "approximately 30% more tokens for the same text".
- Sonnet 5 $2/$10 is the standard price at this time.

### OpenAI (https://developers.openai.com/api/docs/pricing)

| Model ID | Input | Cached input | Output | Batch |
|---|---|---|---|---|
| gpt-6-astra | $10.00 | $1.00 | $50.00 | 50% |
| gpt-5.6-sol | $4.00 | $0.40 | $20.00 | 50% |
| gpt-5.6-terra | $2.00 | $0.20 | $12.00 | 50% |
| gpt-5.6-luna | $0.20 | $0.02 | $1.20 | 50% |
| gpt-5.4-mini | $0.75 | $0.075 | $4.50 | 50% |
| gpt-5-mini | $0.25 | $0.025 | $2.00 | 50% |
| gpt-5-nano | $0.05 | $0.005 | $0.40 | 50% |

Prompt caching is on by default, minimum cacheable prefix 1,024 tokens for GPT-5.6 and subsequent models, 2,048 tokens for older models, cache reads "cost only 0.1x" the input rate. (https://developers.openai.com/api/docs/guides/prompt-caching)

### Google Gemini (https://ai.google.dev/gemini-api/docs/pricing, paid tier)

| Model ID | Input | Output | Context cache | Batch |
|---|---|---|---|---|
| gemini-3.8-flash | $0.75 (to 2026-12-31, $1.50 from 2027-01-01) | $3.75 (then $7.50) | $0.075 (then $0.15) | 50% |
| gemini-3.5-flash | $1.50 | $9.00 | $0.15 | 50% |
| gemini-3.5-flash-lite | $0.30 | $2.50 | not available | 50% |
| gemini-3.1-flash-lite | $0.25 | $1.50 | $0.025 | 50% |
| gemini-3.1-pro-preview | $2.00 (<=200k) / $4.00 | $12.00 / $18.00 | $0.20 / $0.40 | 50% |
| gemini-2.5-flash | $0.30 | $2.50 | $0.03 | 50% |
| gemini-2.5-flash-lite | $0.10 | $0.40 | $0.01 | 50% |

Implicit caching is on by default for Gemini 2.5 and newer, minimum 4,096 tokens on 3.x models, 2,048 on 2.5 models. (https://ai.google.dev/gemini-api/docs/caching)

### xAI (https://docs.x.ai/docs/models)

| Model ID (<200k context) | Input | Cached input | Output |
|---|---|---|---|
| grok-4.6 | $2.00 | $0.50 | $6.00 |
| grok-4.5 | $2.00 | $0.30 | $6.00 |
| grok-4.3 | $1.25 | $0.20 | $2.50 |
| grok-4.20-0309-reasoning | $1.25 | $0.20 | $2.50 |

Prices are two times higher at >=200k context. A Batch API exists with "Reduced pricing", the discount percent was not on the fetched page (https://docs.x.ai/docs/guides/batch-api).

### Mistral (https://mistral.ai/pricing/api)

| Model ID | Input | Output |
|---|---|---|
| mistral-medium-latest (Medium 3.5) | $1.5 | $7.5 |
| mistral-large-latest (Large 3) | $0.5 | $1.5 |
| mistral-small-latest (Small 4) | $0.15 | $0.6 |
| ministral-14b-latest | $0.2 | $0.2 |
| ministral-8b-latest | $0.15 | $0.15 |

Batch 50% off, cached input up to 90% off.

---

## 6. Learning and evolution with LLM agents

| Method | arXiv | What it does | Hobby-workstation practicality |
|---|---|---|---|
| Reflexion | 2303.11366 (Mar 2023) | Agent writes a verbal reflection after each episode into an episodic memory. next trial reads it. 91% pass@1 HumanEval compared with 80% GPT-4. | High. No training. Store scenario-level lessons in a text file or SQLite and prepend them. |
| ExpeL | 2308.10144 (Aug 2023, AAAI-24) | Collects trajectories, extracts natural-language insights, retrieves them at inference. | High. Same as above with a retrieval step. |
| Agent Workflow Memory | 2409.07429 (Sep 2024) | Induces re-usable "workflows" from earlier successes and injects them. +24.6% Mind2Web, +51.1% WebArena relative. | High. Workflows map to "opening moves for scenario X". |
| PokeLLMon in-context RL | 2402.01118 | Feeds battle feedback back into the prompt. knowledge retrieval against hallucination. | High. |
| Promptbreeder | 2309.16797 (Sep 2023) | Evolves task prompts and mutation prompts with the LLM as the mutation operator. | Medium. Requires many evaluation games for each generation. possible with a local model and fast engine. |
| EvoPrompt | 2309.08532 (Sep 2023) | GA and DE on discrete prompts. "up to 25% on BBH" compared with human prompts. | Medium. The cost profile is the same. simpler than Promptbreeder. |
| SPIN | 2401.01335 (Jan 2024) | Self-play fine-tuning: model discriminates its own outputs from target data. no added human data. | Low-medium. Requires a target distribution (strong-play traces) and LoRA fine-tuning of a 7B model. |
| Self-Rewarding LMs | 2401.10020 (Jan 2024) | Model judges its own outputs. iterative DPO. Demonstrated on Llama 2 70B. | Low at 70B. medium at 7B with LoRA. |
| SPIRAL | 2506.24119 (Jun 2025, ICLR 2026) | Multi-turn self-play RL on zero-sum games with TextArena. role-conditioned advantage estimation to prevent "thinking collapse". 3B-7B Qwen and Llama. +10% on reasoning benchmarks. | Medium. Open code at https://github.com/spiral-rl/spiral . 7B full RL is heavy for one GPU but LoRA variants are possible. |
| LSPO for Werewolf | 2502.04686 (Feb 2025, ICML 2025) | Map free-form text to a finite strategy space, run CFR, then DPO. | Low for v0.1. Relevant in a subsequent phase for a discrete-action wargame: the "finite latent strategy space" is the legal-move list. |
| LLM planner + RL executor | 2606.20014 (Jun 2026). CICERO (Science 2022) | LLM selects intent. RL or scripted skills execute legally. | Medium. Fits the project plan (self-play RL exists in the sibling SpaceWar_AI). |

Practical order for this project:

1. Reflexion-style lesson memory for each scenario.
2. EvoPrompt on the system prompt, with win rate as fitness, on a local model.
3. Log each game as a trace. Then LoRA-fine-tune a 7B-14B model on winning traces (SPIN-like).
4. SPIRAL-style self-play RL, only if step 3 shows an improvement.

---

## 7. Cost model (ESTIMATE)

Assumptions. Each is an estimate. Measure each one in-project with the vendor token counters.

- Agent plays one side of a Squad Leader scenario. The engine calls the agent one time for each phase in which the agent has a decision.
  - Phases: Rally, Prep Fire, Movement, Defensive Fire (during the enemy turn), Advancing Fire, Rout, Advance, Close Combat.
  - That is 8 calls for each game turn and 64 calls for each 8-turn game. 
  - (Variant B: one call for each game turn with all phase orders in one JSON: 8 calls for each game.)
- System prompt (role, rules digest, output schema): 2,500 tokens. Identical each call, so it is cacheable.
- Game-state summary (20-30 units with position, morale, status, plus terrain and LOS notes for relevant hexes and a short history): 1,500 tokens.
- Legal-move list (for example 20 units x 6 options x about 12 tokens): 1,500 tokens.
- Output: JSON move plus one short rationale field: 300 tokens for a non-reasoning model. Reasoning models add hidden output tokens, assume 2,000 for each call in the reasoning row.
- Geo-Commander reports 3,000-3,500 tokens for each decision cycle on a hex tank wargame, so 5,500 input for each call is in the same range.

For each call: 5,500 input, 300 output. For each game (64 calls): 352,000 input, 19,200 output. Uncached arithmetic: cost = 0.352 x price_in + 0.0192 x price_out.

| Model | Price in/out | Cost for each 8-turn game, uncached |
|---|---|---|
| gpt-5-nano | $0.05 / $0.40 | 0.352 x 0.05 + 0.0192 x 0.40 = $0.018 + $0.008 = $0.03 |
| Mistral Small 4 | $0.15 / $0.60 | 0.0528 + 0.0115 = $0.06 |
| ministral-14b | $0.20 / $0.20 | 0.0704 + 0.0038 = $0.07 |
| gpt-5.6-luna | $0.20 / $1.20 | 0.0704 + 0.0230 = $0.09 |
| gemini-3.5-flash-lite | $0.30 / $2.50 | 0.1056 + 0.0480 = $0.15 |
| Mistral Large 3 | $0.50 / $1.50 | 0.176 + 0.0288 = $0.20 |
| gemini-3.8-flash | $0.75 / $3.75 | 0.264 + 0.072 = $0.34 |
| gpt-5.4-mini | $0.75 / $4.50 | 0.264 + 0.0864 = $0.35 |
| Claude Haiku 4.5 | $1 / $5 | 0.352 + 0.096 = $0.45 |
| grok-4.3 | $1.25 / $2.50 | 0.44 + 0.048 = $0.49 |
| grok-4.6 | $2 / $6 | 0.704 + 0.115 = $0.82 |
| Claude Sonnet 5 | $2 / $10 | 0.704 + 0.192 = $0.90 |
| gpt-5.6-terra | $2 / $12 | 0.704 + 0.230 = $0.93 |
| gemini-3.1-pro-preview | $2 / $12 | 0.704 + 0.230 = $0.93 |
| Claude Opus 5 | $5 / $25 | 1.76 + 0.48 = $2.24 |
| Claude Fable 5.1 | $10 / $50 | 3.52 + 0.96 = $4.48 |

Adjustments:

- Prompt caching of the 2,500-token system prompt: 63 cache reads x 2,500 = 157,500 tokens at 0.1x in place of 1.0x, one write at 1.25x.
  - Claude Sonnet 5: saves about 157,500 x $2 x 0.9 / 1M = $0.28, so about $0.62 for each game.
  - The Haiku 4.5 minimum is 4,096 tokens, so a 2,500-token system prompt does not cache on Haiku. Pad the prefix with the rules digest to pass 4,096, or accept no cache.
  - OpenAI and Gemini cache automatically above their minimums (1,024 and 4,096 tokens). The 0.1x cache read rate applies on OpenAI GPT-5.6 and subsequent models.
- Batch API: 50% off on Anthropic, OpenAI, Gemini, Mistral. Batch fits AI-against-AI tournaments that are not real-time. It does not fit a human that waits for a move.
- Reasoning models with 2,000 hidden output tokens for each call: output increases to 128,000 tokens for each game. Sonnet 5 adds 0.128 x $10 = $1.28, and gpt-5.6-terra adds $1.54.
- Claude 4.7+ tokenizer: add about 30% to the Claude rows.
- Variant B (8 calls for each game, all orders in one JSON) divides the input cost by about 8. Output increases to maybe 1,500 tokens for each call. Sonnet 5 is then near $0.20 for each game.
- Local (llama.cpp on RTX 5090): $0 added cost. 64 calls x (about 1 s prompt + about 2-5 s generation) is 3-7 minutes for each game for 8B-32B Q4 models (section 4.2).

---

## Recommended LLM agent architecture for v0.1

1. Engine owns legality. For each phase the rules engine emits two items. Item (a) is a compact text state with unit-level annotations (hex, terrain, LOS to nearest enemies, morale, status). Item (b) is the full legal-move list with short move IDs.
2. Two-stage answer.
   - Stage 1: the model writes free-text reasoning (ReAct style, 100-300 tokens).
   - Stage 2: the model emits JSON constrained to a flat schema in which the `move_id` field is an enum of the legal IDs.
   - On SaaS use the vendor schema mode. On llama-server use `response_format` `json_schema`.
   - Keep the schema flat: no recursion, no numeric ranges, `additionalProperties: false`.
3. Verify, retry one time, then fall back. If the engine rejects the move, resend with the rejection reason. On the second failure apply a scripted default (hold, or the top move from a simple heuristic). Log each fallback as a metric.
4. Text only. No board images to the model in v0.1.
5. Memory. Keep the last N turns of the agent's own plans in the prompt. Write a scenario-level Reflexion note at game end.
6. Provider abstraction. One OpenAI-compatible client for local servers and thin adapters for Anthropic, Gemini, xAI, Mistral. Cache the static prefix. Record tokens, latency, invalid-move count, and outcome for each call in the run artifact.
7. Metrics from day one: invalid-move rate before fallback, fallback rate, win rate compared with scripted AI, tokens and cost for each game. These are the numbers each paper above reports. They are also the fitness values for EvoPrompt in a subsequent phase.

---

## References

Papers (arXiv ID, title, first author, date)

- 2210.03629 ReAct: Synergizing Reasoning and Acting in Language Models. Yao and others, Oct 2022. https://arxiv.org/abs/2210.03629
- 2303.11366 Reflexion: Language Agents with Verbal Reinforcement Learning. Shinn and others, Mar 2023. https://arxiv.org/abs/2303.11366
- 2305.15486 SPRING: Studying the Paper and Reasoning to Play Games. Wu and others, May 2023. https://arxiv.org/abs/2305.15486
- 2305.16291 Voyager: An Open-Ended Embodied Agent with Large Language Models. Wang and others, May 2023. https://arxiv.org/abs/2305.16291
- 2308.10144 ExpeL: LLM Agents Are Experiential Learners. Zhao and others, Aug 2023. https://arxiv.org/abs/2308.10144
- 2309.08532 EvoPrompt. Guo and others, Sep 2023. https://arxiv.org/abs/2309.08532
- 2309.16797 Promptbreeder. Fernando and others, Sep 2023. https://arxiv.org/abs/2309.16797
- 2310.01557 SmartPlay. Wu and others, Oct 2023. https://arxiv.org/abs/2310.01557
- 2312.11865 Large Language Models Play StarCraft II. Ma and others, Dec 2023. https://arxiv.org/abs/2312.11865
- 2401.01335 Self-Play Fine-Tuning (SPIN). Chen and others, Jan 2024. https://arxiv.org/abs/2401.01335
- 2401.03408 Escalation Risks from Language Models in Military and Diplomatic Decision-Making. Rivera and others, Jan 2024. https://arxiv.org/abs/2401.03408
- 2401.10020 Self-Rewarding Language Models. Yuan and others, Jan 2024. https://arxiv.org/abs/2401.10020
- 2401.10568 CivRealm. Qi and others, Jan 2024. https://arxiv.org/abs/2401.10568
- 2402.01118 PokeLLMon. Hu and others, Feb 2024. https://arxiv.org/abs/2402.01118
- 2402.12348 GTBench. Duan and others, Feb 2024. https://arxiv.org/abs/2402.12348
- 2403.03407 Human vs. Machine: ... Wargame Simulations. Lamparth and others, Mar 2024. https://arxiv.org/abs/2403.03407
- 2404.11446 Open-Ended Wargames with Large Language Models. Hogan and Brennen, Apr 2024. https://arxiv.org/abs/2404.11446
- 2406.06613 GameBench. Costarelli and others, Jun 2024. https://arxiv.org/abs/2406.06613
- 2408.02442 Let Me Speak Freely? Tam and others, Aug 2024. https://arxiv.org/abs/2408.02442
- 2409.07429 Agent Workflow Memory. Wang and others, Sep 2024. https://arxiv.org/abs/2409.07429
- 2411.13543 BALROG. Paglieri and others, Nov 2024. https://arxiv.org/abs/2411.13543
- 2502.04686 Learning Strategic Language Agents in the Werewolf Game with Iterative Latent Space Policy Optimization. Xu and others, Feb 2025. https://arxiv.org/abs/2502.04686
- 2503.06047 DSGBench. Tang and others, Mar 2025. https://arxiv.org/abs/2503.06047
- 2504.11442 TextArena. Guertler and others, Apr 2025. https://arxiv.org/abs/2504.11442
- 2505.15146 lmgame-Bench. Hu and others, May 2025. https://arxiv.org/abs/2505.15146
- 2506.10264 WGSR-Bench. Yin and others, Jun 2025. https://arxiv.org/abs/2506.10264
- 2506.24119 SPIRAL. Liu and others, Jun 2025. https://arxiv.org/abs/2506.24119
- 2508.03368 Game Reasoning Arena. Cipolina-Kun and others, Aug 2025. https://arxiv.org/abs/2508.03368
- 2508.07485 Democratizing Diplomacy. Duffy and others, Aug 2025. https://arxiv.org/abs/2508.07485
- 2509.17192 Shall We Play a Game? Language Models for Open-ended Wargames. Matlin and others, Sep 2025. https://arxiv.org/abs/2509.17192
- 2603.21280 WARBENCH. Li and others, Mar 2026. https://arxiv.org/abs/2603.21280
- 2606.20014 Hierarchical Control in Multi-Agent Games: LLM-based Planning and RL Execution. Hosch and others, Jun 2026. https://arxiv.org/abs/2606.20014
- CICERO. Meta FAIR Diplomacy Team, Science, Dec 2022, DOI 10.1126/science.ade9097. https://ai.meta.com/research/cicero/
- Geo-Commander. Chen and others, Scientific Reports, 2026-03-13, DOI 10.1038/s41598-026-43365-3. https://www.nature.com/articles/s41598-026-43365-3

Blogs, leaderboards, code

- Acher, GPTs chess Elo and legal moves, 2023-09-30. https://blog.mathieuacher.com/GPTsChessEloRatingLegalMoves/
- Acher, GPT-5 illegal chess bench, 2025-08-07. https://blog.mathieuacher.com/GPT5-IllegalChessBench/
- dynomight, LLM chess weirdness, Nov 2024. https://dynomight.net/more-chess/
- BALROG leaderboard. https://balrogai.com/
- AI Diplomacy repo. https://github.com/EveryInc/AI_Diplomacy
- SPIRAL code. https://github.com/spiral-rl/spiral
- llama.cpp CUDA performance discussion #15013. https://github.com/ggml-org/llama.cpp/discussions/15013
- hardware-corner RTX 5090 llama.cpp benchmarks, 2025-11-06. https://www.hardware-corner.net/rtx-5090-llm-benchmarks/

Vendor docs (fetched 2026-09-07)

- Anthropic structured outputs. https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Anthropic pricing. https://platform.claude.com/docs/en/about-claude/pricing
- Anthropic prompt caching. https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- OpenAI structured outputs. https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI pricing. https://developers.openai.com/api/docs/pricing
- OpenAI prompt caching. https://developers.openai.com/api/docs/guides/prompt-caching
- Gemini structured output. https://ai.google.dev/gemini-api/docs/structured-output
- Gemini pricing. https://ai.google.dev/gemini-api/docs/pricing
- Gemini caching. https://ai.google.dev/gemini-api/docs/caching
- xAI structured outputs. https://docs.x.ai/docs/guides/structured-outputs
- xAI models and pricing. https://docs.x.ai/docs/models
- xAI batch API. https://docs.x.ai/docs/guides/batch-api
- Mistral structured output. https://docs.mistral.ai/studio/conversations/structured-output/custom
- Mistral pricing. https://mistral.ai/pricing/api
- llama.cpp grammars. https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
- llama.cpp server README. https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Ollama structured outputs. https://docs.ollama.com/capabilities/structured-outputs
- vLLM structured outputs. https://docs.vllm.ai/en/latest/features/structured_outputs.html
- LM Studio structured output. https://lmstudio.ai/docs/app/api/structured-output

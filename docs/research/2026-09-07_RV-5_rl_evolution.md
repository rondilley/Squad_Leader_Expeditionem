# RV-5: Reinforcement learning, self-play, and evolution for Squad Leader

Date: 2026-09-07
Project: Squad_Leader_AI
Scope: turn-based, stochastic, hex-and-counter tactical wargames with two players, dice-driven combat, concealment, phases in each turn, and many unit moves in each turn.

## Rules of evidence

- Each claim has a source URL. arXiv papers show the arXiv ID in the form YYMM.NNNNN. The YYMM part gives the month of first submission.
- I opened the arXiv abstract page, or an equivalent record, for each paper in the References list.
- Section 9 gives the papers that I could not open. Do not cite them before you open them.
- Numbers keep their qualifiers (hardware, game size, step counts). Derived numbers are marked "derived".

## 1. Peer-reviewed and preprint work on RL for turn-based strategy and wargames

### 1.1 AlphaZero and MuZero family, and stochastic games

- Stochastic MuZero (Antonoglou, Schrittwieser, Ozair, Hubert, Silver), ICLR 2022 spotlight [R1]. The model learns "afterstates" and uses it in a stochastic MCTS. It was equal to or better than the best known results in 2048 and backgammon. It kept MuZero performance in Go. There is no arXiv ID. The record is on OpenReview (id X6D9bAHhBQ1).
- Relevance: dice-driven combat is a chance node after a decision. The afterstate idea maps directly to "fire declared, dice not yet rolled". Stochastic MuZero does not model hidden information (concealment).
- Pgx (arXiv 2303.17503, first submitted March 2023) [R2] gives Gumbel AlphaZero training numbers on single GPUs. See section 5.
- Playing Hex and Counter Wargames using RL and RNNs (Palma, Santos, Dias, arXiv 2502.13918, February 2025) [R3]. This is the closest paper to Squad Leader.

  - Engine: a custom version of the Standard Combat Series ruleset. The authors put together AlphaZero and a recurrent, fully convolutional network that uses hexagonal convolutions (Hexagdly).

  - Scale: training used 5x5 maps and two unit types (infantry, armour). Scenarios had 3 to 8 units. Movement is one tile at a time, and combat is a sequence of unit selections. The action tensor is (9S+3) x Height x Width, where S is the stack depth. Combat is deterministic in their ruleset.

  - Compute: all training and testing ran on CPU only. The randomized scenario got to 3640 training steps with 32 weight updates for each step and a replay buffer of 6000 games. The paper reports no wall-clock time.

  - Results: the policy alone won about 80% against a random agent. With MCTS it won about 100%. Against a "Goal Rush" scripted agent, player 1 won 100% and player 2 won 70% with MCTS.

### 1.2 Imperfect information

- Player of Games / Student of Games (Schmid et al., arXiv 2112.03178, December 2021, revised November 2023) [R4]. One algorithm for perfect and imperfect information games. It beat Slumbot in heads-up no-limit poker and the state-of-the-art agent in Scotland Yard, and it is strong in chess and Go. The authors prove convergence to perfect play with more calculation.
- DeepNash (Perolat et al., arXiv 2206.15378, June 2022, and Science, DOI 10.1126/science.add4679) [R5]. Model-free, no search. The R-NaD algorithm converges to an approximate Nash equilibrium in Stratego (game tree of 10^535 nodes). It got a top-3 all-time rank on the Gravon platform.
- Ataraxos (Sokota, Vinitsky, Hu, Kolter, Farina, arXiv 2511.07312, November 2025) [R6]. Superhuman Stratego with self-play RL and test-time planning with imperfect information.

  - Compute: training used 16 H100 GPUs for one week, then 4 H100 GPUs for 4 days for the belief network. The environment ran 1,536 parallel games for each GPU at about 10 million environment updates each second on one H100. The authors say the run cost "a few thousand dollars".

  - Method: the method is "dynamically damped" RL: strong regularization and aggressive updates when the policy is weak, weak regularization and small updates when it is strong.
- Relevance: concealment in Squad Leader is a small hidden-information problem. DeepNash-style R-NaD or the damped self-play of Ataraxos are the proven methods. The two methods used far more computer power than one workstation has, for Stratego. But Squad Leader scenarios are much smaller than a 10x10 Stratego board with 40 pieces on each side.

### 1.3 Frameworks and turn-based strategy games

- OpenSpiel (Lanctot et al., arXiv 1908.09453, August 2019, v6 September 2020) [R7]. Supports n-player, zero-sum and general-sum, turn-taking and simultaneous-move, perfect and imperfect information games. The current docs [R8] show these algorithms: MCTS, IS-MCTS, minimax, CFR and its Monte Carlo variants, Deep CFR, NFSP, PSRO, and PSRO-rn. They also show AlphaZero (C++/LibTorch and Python/TF), DQN, PPO, A2C, ESCHER, NeuRD, exploitability descent, alpha-Rank, and Nash averaging. The repository is Apache-2.0, has 5,467 stars, and was pushed on 2026-08-31 [R9].
- Tribes (Perez-Liebana, Hsu, Emmanouilidis, Khaleque, Gaina, AIIDE 2020) [R10]. A Java re-implementation of The Battle of Polytopia with hidden information, stochasticity, multi-unit control, and a large variable action space. Agents are MCTS and RHEA. The repository has no license file and was last pushed on 2022-08-25 [R11].
- Generating Diverse and Competitive Play-Styles for Strategy Games (Perez-Liebana et al., arXiv 2104.08641, April 2021) [R12]. Portfolio MCTS with Progressive Unpruning plus MAP-Elites makes different play-styles in Tribes that stay competitive on levels not used in training.
- tribes-rl (pham-tuan-binh, GitHub, created 2026-07-07) [R13]. A C re-implementation of Polytopia for PufferLib. This is a hobby repository, not a paper.

  - Throughput: the README reports about 1.8 million agent steps/s end to end, with learning, on an RTX 5090. The run uses 4096 parallel agents and an 8.2M-parameter MinGRU policy (768 hidden, 4 layers). A 10-billion-step run finishes in less than 2 hours.

  - Design and license: the policy uses one Discrete(197) head with a mask. The README says MIT. The GitHub API reports "NOASSERTION".
- CivRealm (Qi et al., arXiv 2401.10568, January 2024, and ICLR 2024) [R14]. Freeciv environment with a Gymnasium tensor interface for RL and a language interface for LLM agents. RL agents get good results in mini-games. Both RL and LLM agents "struggle to make substantial progress in the full game".
- Gym-uRTS (Huang, Ontanon, Bamford, Grela, arXiv 2105.13807, May 2021) [R15]. Real-time, not turn-based, but the action-space work applies. See section 2 and section 5.

### 1.4 Military wargame AI papers

- Large Scale Deep Reinforcement Learning in War-games (Wang, Tang, Hao, Hao, Fu, Ma), IEEE BIBM 2020, DOI 10.1109/BIBM49941.2020.9313387 [R16]. A hierarchical multi-agent RL framework for a wargame on a hexagon grid. The high-level network does cooperative agent assignment with a QMIX architecture. The low-level network does path planning.

  - Note: the DOI and summary come from the web query result. The IEEE page returned no text when I opened it.
- MiaoSuan Wargame: A Multi-Mode Integrated Platform for Imperfect Information Game (Xu, Hu, Wang, Yang, Ni), IEEE CoG 2022, pages 457-464, DOI 10.1109/CoG51982.2022.9893656 [R17]. This is the platform used by the Chinese Academy of Sciences wargame competitions. The record I opened has no abstract.
- Method for making multi-attribute decisions in wargames by combining intuitionistic fuzzy numbers with reinforcement learning (Sun, Yuan, Xue, Zhou, Zhang, Zhou, arXiv 2109.02354, September 2021) [R18]. Hybrid decision method to decrease sparse-reward and convergence problems in a wargame simulation.
- Self Generated Wargame AI: Double Layer Agent Task Planning Based on Large Language Model (Sun, Zhao, Yu, Wang, Zhou, arXiv 2312.01090, December 2023) [R19]. An LLM commands units in natural language. The abstract claims the LLM agent is stronger than "commonly used reinforcement learning AI and rule AI" on their wargame, and that the prompt has a strong effect on the results.
- WGSR-Bench (Yin et al., arXiv 2506.10264, June 2025) [R20]. A wargame-based benchmark of strategic reasoning for LLMs, with situation awareness, opponent risk modeling, and policy generation.
- Scaling Intelligent Agents in Combat Simulations for Wargaming (Black, Darken, arXiv 2402.06694, February 2024, and I/ITSEC 2023) [R21]. Five research lines for hierarchical RL in combat simulations.
- Mastering the Digital Art of War (Black, arXiv 2408.13333, August 2024) [R22]. Hierarchical RL with a "localized observation abstraction using piecewise linear spatial decay" and a hybrid of learned and scripted agents. The abstract gives no hardware or time.
- A Hierarchical Hybrid AI Approach (Black, Darken, arXiv 2512.00249, November 2025) [R23]. Scripted agents make tactical decisions. RL agents make strategic decisions.
- Advance Wars, Battle for Wesnoth, ASL, Squad Leader: I found no peer-reviewed or arXiv paper that trains an RL agent on these games. The Wesnoth wiki describes a neural "Machine Learning Recruiter" (search result only, not opened). No paper on ASL or Squad Leader was in the results of the web queries.

## 2. Action space design for many units and many moves in each turn

Concrete methods with citations:

1. Action composition plus invalid action masking (Gym-uRTS, arXiv 2105.13807) [R15]. The action is a tuple (source unit, action type, parameters). Composition decreases the logits from 9216 (h w alpha r^2) to h w + 36 + alpha r^2. Masking replaces invalid logits with large negative numbers. The pafor each calls masking "essential".
2. GridNet versus UAS (same paper) [R15]. GridNet predicts one action for each map cell in one forward pass. UAS (unit action simplification) "calls the policy iteratively until all units have actions". UAS is the unit-by-unit, autoregressive form. Squad Leader phases fit UAS: the policy picks a unit, then an action, then a NO-OP to end the phase.
3. Theory and ablation of masking (Huang, Ontanon, arXiv 2006.14171, June 2020, and FLAIRS 2022) [R24]. Masking is a correct policy-gradient method. Its effect increases with the number of invalid actions.
4. Transformer encoder on unit tokens (Zwingenberger, arXiv 2301.03679, January 2023, and AIIDE 2022 workshop) [R25]. The policy attends to a variable number of units in Gym-uRTS and got a higher reward with half the computer time of GridNet.
5. Per-tile sequential decisions on a hex map (arXiv 2502.13918) [R3]. Movement is one hex for each decision. Combat is a sequence of unit selections. The action tensor is (9S+3) x H x W with S stacking levels. This is a direct template for a hex-and-counter game with stacks.
6. Centralized policy for a variable-size fleet (Creus Castanyer, arXiv 2304.13004, April 2023, on Lux AI v2) [R26]. One centralized policy controls all units.
7. Shared per-agent PPO policy (MAPPO, Yu et al., arXiv 2103.01955, March 2021, and NeurIPS 2022) [R27]. One PPO policy with parameter sharing is a strong baseline in StarCraft micromanagement and Hanabi.
8. Hierarchical policies for wargames: QMIX high level plus path-planning low level [R16], and scripted tactical plus RL strategic [R23].
9. Single discrete head with a mask (tribes-rl) [R13]. One Discrete(197) head with a mask runs at 1.8M steps/s. Simple heads keep throughput high.

Recommendation for Squad Leader: use design 2 (unit-by-unit, one decision per step) with design 1 (masking from the rules engine). Add a "pass/end phase" action. Encode the phase in the observation. This keeps the action head small and lets the rules engine reject nothing.

## 3. Self-play and league training

- AlphaStar (Vinyals et al., Nature 2019, DOI 10.1038/s41586-019-1724-z) [R28]. The league extends fictitious self-play to a group of agents: primary agents maximize the win rate against the league. Exploiter agents find weak points in the primary agents [R29]. Agents start from imitation learning on human replays and are "better than 84% of active players" before RL [R29]. TStarBot-X reports AlphaStar's resources as 3,072 TPU v3 cores and 50,400 preemptible CPU cores for 44 days [R30].
- TStarBot-X (Han et al., arXiv 2011.13729, November 2020) [R30]. League training used 144 V100 GPUs (96 for training) and 13,440 CPU cores for 57 days. The last run had one primary agent and 8 exploiters. The league made 583 agents in total. Its throughput was about 1/30 of AlphaStar's.
- PSRO (Lanctot et al., arXiv 1711.00832, November 2017, and NeurIPS 2017) [R31]. Best responses to mixtures of policies, with meta-strategies from empirical game analysis. PSRO includes single-agent RL, fictitious play, and double oracle as special cases.
- NFSP (Heinrich, Silver, arXiv 1603.01121, March 2016) [R32]. Fictitious self-play with deep RL. Comes near to Nash in Leduc and is competitive with superhuman bots in Limit Hold'em.
- Population Based Training (Jaderberg et al., arXiv 1711.09846, November 2017) [R33]. Evolves hyperparameters in a population during training.
- Survey on self-play methods (Zhang et al., arXiv 2408.01072, August 2024, revised October 2025) [R34]. Taxonomy of self-play algorithms and open problems.
- Sample Factory (Petrenko et al., arXiv 2006.11751, June 2020, and ICML 2020) [R35]. Supports self-play and population-based training on one machine at more than 10^5 frames each second.

What is practical on one workstation with one GPU:

- AlphaStar-scale leagues are not practical. TStarBot-X, the "cheap" version, used 144 GPUs for 57 days.
- A snapshot pool with prioritized fictitious self-play is practical. This is what the SpaceWar_AI sibling does today: a snapshot each 100 episodes, a pool of 5, 30% games against the current self and 70% against earlier snapshots, plus an ELO tournament (source: G:\git\SpaceWar_AI\spacewar_ai\config.py and main.py).
- Add scripted bots (rule-based Squad Leader tactics) to the pool as constant exploiters. Sample opponents by win rate, so the learner plays the opponents that defeat it.
- PSRO with a small population (4 to 8 policies) is practical if each best-response run is short. OpenSpiel has a reference implementation [R8].
- R-NaD (DeepNash) is a single-policy method with no league. It is the cheapest method for concealment-aware play if it converges on the smaller game. Ataraxos shows the damped variant works, but on 16 H100 GPUs for Stratego [R6].

## 4. Evolutionary and neuroevolution approaches

- NEAT (Stanley, Miikkulainen, Evolutionary Computation 10(2):99-127, 2002, DOI 10.1162/106365602320169811) [R36]. Evolves weights and topology with speciation. Note: DOI from the ACM record in the web query result. I did not open it.
- Evolution Strategies (Salimans, Ho, Chen, Sidor, Sutskever, arXiv 1703.03864, March 2017) [R37]. Scales to more than 1,000 workers with shared random numbers. Solves 3D humanoid walking in 10 minutes and gets competitive Atari scores in one hour on a cluster.
- Deep Neuroevolution with a simple GA (Such et al., arXiv 1712.06567, December 2017) [R38]. Evolves networks with more than 4 million parameters. Trains Atari in about 4 hours on one desktop or 1 hour on 720 cores.
- CMA-ES tutorial (Hansen, arXiv 1604.00772, April 2016, revised March 2023) [R39]. The standard reference for continuous parameter search. Good for tuning the weights of a scripted policy.
- MAP-Elites with RL populations (Pierrot, Flajolet, arXiv 2303.12803, March 2023) [R40]. Evolves full agents, with hyperparameters, in a quality-diversity archive. Results are on robotics, not games.
- MAP-Elites for strategy games (arXiv 2104.08641) [R12]. Direct evidence on Tribes, a turn-based multi-unit game: diverse and competitive play-styles.
- Generational Adversarial MAP-Elites (Anne, Syrkis, et al., arXiv 2505.06617, May 2025, v5 May 2026) [R41]. Co-evolves the two sides of a competitive game by alternating which side evolves each generation. Tested on a multi-agent battle game, a soft-robot wrestling task, and a deck-building game. The authors say open-ended discovery "remains constrained by the nature of the search spaces".
- EvolvingBehavior (Partlan et al., arXiv 2209.01020, September 2022, and FDG 2022) [R42]. Genetic programming of behavior trees for Unreal Engine NPCs.
- Parameterized behavior trees that mimic playstyle (Kozik et al., arXiv 2111.12144, November 2021) [R43]. Adapts expert-made behavior trees to human gameplay as a mixed discrete and continuous optimization problem in an RTS prototype.
- Hybrid GP and Q-learning for behavior trees in MicroRTS (Chikh Touami, Salem, Khelfi, Informatica 2026, DOI 10.31449/inf.v50i14.14678) [R44]. Q-learning gates terminal nodes of evolved trees. Best fitness increased from 22.0 to 26.44 (20.2%) against a deterministic opponent.
- Population Based Training [R33] is the evolutionary tool that fits an RL league best: it evolves learning rate, entropy, and reward weights while PPO trains.

Assessment: evolution works for (a) tuning scripted policies and behavior trees, (b) producing diverse opponents for a league, and (c) hyperparameter schedules. Evidence that pure neuroevolution beats PPO on a multi-unit strategy game is thin. Use evolution to build the opponent pool and the scripted baselines, and use PPO for the primary learner.

## 5. Compute reality on one RTX-class GPU

Reported numbers, with hardware:

| Source | Game | Hardware | Steps or frames | Wall-clock |
|---|---|---|---|---|
| Gym-uRTS [R15] | uRTS, one map, PPO | 1 GPU, 3 vCPU, 16 GB RAM | 300,000,000 timesteps, 24 parallel envs | about 60 hours |
| Pgx [R2] | Hex, Gumbel AlphaZero | 1 x A4000 | 400 iterations, about 105M frames | 17.6 hours |
| Pgx [R2] | Othello, Gumbel AlphaZero | 1 x A4000 | about 105M frames | 11.4 hours |
| Pgx [R2] | Animal shogi | 1 x A4000 | about 105M frames | 6.2 hours |
| Pgx [R2] | Gardner chess | 4 x A4000 | about 105M frames | 14.3 hours |
| Pgx [R2] | Go 9x9 | 1 x A100 | about 105M frames | 8.6 hours |
| tribes-rl [R13] | Polytopia clone, PPO | RTX 5090 | 10,000,000,000 steps, 4096 agents | less than 2 hours (1.8M steps/s) |
| PufferLib 2.0 [R45] | 12 C environments | one CPU core for each env | 1M steps/s for each env | n/a |
| Sample Factory [R35] | 3D control from pixels | one workstation | more than 100,000 frames/s | n/a |
| Deep GA [R38] | Atari | one desktop | n/a | about 4 hours |
| Hex and Counter [R3] | SCS 5x5, AlphaZero | CPU only | 3640 steps x 32 updates, 6000-game buffer | not reported |
| Ataraxos [R6] | Stratego | 16 H100, then 4 H100 | 1,536 envs for each GPU, 10M environment updates/s | 7 days + 4 days |
| TStarBot-X [R30] | StarCraft II league | 144 V100, 13,440 CPU cores | n/a | 57 days |

Derived estimates for Squad Leader (10 to 30 units on each side, 6 to 10 turns, 8 phases in each player turn):

- Decision steps for each game (derived). With unit-by-unit actions, one step for each unit in each phase, 15 active units, 8 phases, 2 players, and 8 turns: 15 x 8 x 2 x 8 = 1,920 steps. Many units do nothing in many phases, and movement adds one step for each hex. A range of 1,000 to 4,000 decision steps for each game is a reasonable planning figure.
- Sample budget (derived). Gym-uRTS got to state-of-the-art bot play at 300M steps on one map [R15]. Pgx AlphaZero runs used about 105M frames for each game [R2]. Plan for 100M to 300M steps for v0.1. That is 25,000 to 300,000 full games.
- Throughput needed (derived). To finish 300M steps in 24 hours, the full loop must sustain 3,500 steps/s. To finish in 6 hours, it must sustain 14,000 steps/s. Gym-uRTS sustained about 1,400 steps/s end to end (300M steps in 60 hours, derived) with a Java engine and 24 envs. tribes-rl sustains 1.8M steps/s with a C engine and 4096 envs [R13].
- Engine requirement (derived). A pure-Python rules engine at 1,000 to 5,000 steps/s for each core with 8 to 16 worker processes gives 8,000 to 80,000 raw env steps/s. The PPO update then becomes the limit. This is sufficient for a 24-hour, 300M-step run if the observation build is cheap. A C or Rust core, or a JAX port as in Pgx and Lux S3, is a v0.2 alternative, not a v0.1 requirement.
- MCTS-based methods (AlphaZero family) multiply the engine load by the number of simulations for each move (32 in Pgx [R2]). With stochastic combat, MCTS must also include chance nodes. Use model-free PPO first.

## 6. Tooling

Activity and licenses from the GitHub API on 2026-09-07 [R9, R11, R13, R46 to R53]:

| Tool | Role | License | Last push | Stars | Notes |
|---|---|---|---|---|---|
| Gymnasium [R46, R54] | single-agent env API | MIT | 2026-09-07 | 12,483 | paper arXiv 2407.17032, NeurIPS D&B 2025 |
| PettingZoo [R47, R55] | multi-agent env API (AEC for turn-taking) | MIT | 2026-09-05 | 3,508 | AEC fits phased, alternating turns |
| CleanRL [R48, R56] | single-file PPO, DQN, PPG | MIT (LICENSE file) | 2026-04-20 | 10,375 | reference implementations, not a framework |
| RLlib (Ray) [R49, R57] | multi-machine RL | Apache-2.0 | 2026-09-07 | 43,729 | heavy for one workstation |
| Sample Factory [R50, R35] | async PPO, self-play, PBT | MIT | 2026-07-02 | 1,021 | one-machine throughput |
| PufferLib [R51, R45] | vectorization, fast PPO | MIT | 2026-09-07 | 6,329 | RLJ 2025 paper, 1M steps/s envs |
| OpenSpiel [R9, R7] | games and game-theory algorithms | Apache-2.0 | 2026-08-31 | 5,467 | PSRO, NFSP, AlphaZero, CFR |
| Pgx [R52, R2] | JAX board games, AlphaZero | Apache-2.0 | 2025-03-06 | 644 | JAX template for a fast engine |
| Tribes [R11, R10] | Polytopia in Java | none | 2022-08-25 | 103 | not active, no license file |
| tribes-rl [R13] | Polytopia in C for PufferLib | README MIT, API NOASSERTION | 2026-07-08 | 14 | new hobby project |
| MicroRTS [R53] | Java RTS | GPL-3.0 | 2025-08-11 | 360 | GPL is a constraint for a BSD project |
| MicroRTS-Py [R58] | Python wrapper | MIT | 2025-08-11 | 292 | README says deprecated on 2025-08-11 (search result) |
| Lux-Design-S3 [R59] | JAX 1v1 unit game | Apache-2.0 | 2025-02-05 | 350 | NeurIPS 2024 competition, JAX env |

Suitability for Squad Leader:

- Use PettingZoo AEC as the environment contract. It models alternating turn-taking games, and it is active. Wrap the AEC env as a single-agent Gymnasium env for the learner, with the opponent in the env.
- Keep the algorithm in raw torch. The sibling repos (SpaceWar_AI, learn2drive, Scorched_Earth_MOAG) have PPO and DQN in raw torch with a snapshot-based league. That remains the right choice for v0.1 for three reasons. First, unit-by-unit action heads with rules-engine masks need custom code in all frameworks. Second, CleanRL is the reference for the PPO code (advantage normalization, clipping, n_steps rollouts), and the sibling lesson "never update PPO per episode" comes from that reference. Third, RLlib and Sample Factory add process management that is not necessary at 8 to 16 envs.
- Use PufferLib in v0.2 if throughput becomes the limit. It is MIT, active, and it works with CleanRL-style loops.
- Use OpenSpiel as a reference for PSRO and NFSP code, not as the engine. Its game API is C++-first and does not fit a browser-based rules engine.
- Do not import MicroRTS code (GPL-3.0) if the project license is BSD.
- Tribes is not active. tribes-rl is a useful reference for a fast C engine with one head and a mask.

## 7. Learning from human games and LLM-generated games

- Behavior cloning from replays, then RL: AlphaStar started from imitation learning on human replays and was better than 84% of active players before RL [R29]. This is the strongest indication that replays cut the RL budget.
- CivRealm [R14] runs tensor RL agents and LLM agents in the same environment with a shared interface. It is the template for "one env, two agent kinds".
- Werewolf (Xu, Yu, Fang, Wang, Wu, arXiv 2310.18940, October 2023, and ICML 2024) [R60]. An LLM does deduction and proposes a set of candidate actions. An RL policy selects the action. This is the cleanest published hybrid of LLM reasoning and RL decision.
- Agents of Change (Belle et al., arXiv 2506.04651, June 2025) [R61]. Self-evolving LLM agents in Settlers of Catan store strategy as executable artifacts and get a 54% win rate against baselines.
- Sun et al. 2023 [R19] compare an LLM agent with RL and rule agents in a wargame and claim the LLM is stronger. Treat this as a single-lab result.
- MARSHAL (Yuan, Xu, Tan, et al., arXiv 2510.15414, October 2025) [R62] and Multi-Agent Evolve (Chen et al., arXiv 2510.23595, October 2025) [R63] train LLMs by self-play in games with RL. They make LLM reasoning better. They do not train a game policy.
- Cicero (Bakhtin, Brown, Dinan, et al., Science 2022, DOI 10.1126/science.ade9097) [R64]. A 2.7B language model plus planning and RL got into the top 10% in an online Diplomacy league in 40 games.
- LLM agents as opponents in an RL league: I found no 2024 to 2026 paper that puts LLM agents into a self-play population as opponents for an RL learner. The nearest are CivRealm (same env), Werewolf (LLM in the policy), and the SpaceWar_AI sibling, which used LLM demonstrations as an imitation loss (LLMConfig.demonstration_episodes = 100, imitation_weight = 0.1).
- Practical plan: log each human and LLM game in a replay format. Use behavior cloning from these replays to warm-start the policy and to seed the opponent pool.

  - LLM agents: use them as slow, diverse, constant opponents in evaluation. Give them a small share of league games. Do not make them the primary training opponent. The sibling lesson on LLM latency (200 to 2000 ms for each call) applies.

## 8. Recommended training approach for v0.1 on one workstation

1. Build the rules engine as a PettingZoo AEC env with a legal-action mask in each observation.
2. Use unit-by-unit discrete actions: (unit, action, target) as one composed head with masks, plus an end-phase action. Encode phase, turn, and side in the observation.
3. Train PPO in raw torch, CleanRL style, with 8 to 16 env processes and 2048 to 8192 steps in each rollout. Target a minimum of 3,500 steps/s end to end.
4. Start from behavior cloning on scripted-bot and human replays if more than 200 games are available.
5. Use a snapshot league: keep 10 to 20 snapshots, add 3 to 5 scripted bots, and sample opponents by loss rate (prioritized fictitious self-play). Keep the ELO tournament from SpaceWar_AI.
6. Use PBT or CMA-ES to tune the scripted bots and the reward weights, not the network.
7. Budget 100M to 300M steps for each run, 24 to 72 hours on one RTX GPU, and measure engine steps/s before the first long run.
8. Defer AlphaZero and MCTS, R-NaD, and LLM opponents in the league to v0.2.

## 9. Papers not opened by fetch

Do not cite these before you open them:

- Boron, Darken, "Developing Combat Behavior through Reinforcement Learning in Wargames and Simulations", IEEE CoG 2020 (ResearchGate blocked, Semantic Scholar rate-limited).
- Moy, Shekh, "The Application of AlphaZero to Wargaming", 2019 (ResearchGate blocked).
- "Deep Reinforcement Learning in Wargaming", Journal of Aerospace Information Systems, DOI 10.2514/1.I011766 (AIAA page blocked).
- Xue, Sun, et al., "Multi-attribute decision-making in wargames leveraging the entropy-weight method ... deep reinforcement learning", IEEE Transactions on Games 2023 (search result only).
- "A Training Model of Wargaming Based on Imitation Learning and Deep Reinforcement Learning", Springer, DOI 10.1007/978-981-19-6203-5_78 (Springer login redirect).
- "BeClone: Behavior Cloning with Inference for Real-Time Strategy Games", CEUR Vol-3217 paper 27 (PDF downloaded, text not parsed).
- Wesnoth "Machine Learning Recruiter" wiki page (search result only).

## References

- [R1] Antonoglou et al., "Planning in Stochastic Environments with a Learned Model", ICLR 2022. https://iclr.cc/virtual/2022/spotlight/6833 and https://openreview.net/forum?id=X6D9bAHhBQ1
- [R2] Koyamada et al., "Pgx: Hardware-Accelerated Parallel Game Simulators for Reinforcement Learning", arXiv 2303.17503. https://arxiv.org/abs/2303.17503 (Appendix E table at https://ar5iv.labs.arxiv.org/html/2303.17503)
- [R3] Palma, Santos, Dias, "Playing Hex and Counter Wargames using Reinforcement Learning and Recurrent Neural Networks", arXiv 2502.13918. https://arxiv.org/abs/2502.13918 (full text https://arxiv.org/html/2502.13918)
- [R4] Schmid et al., "Student of Games: A unified learning algorithm for both perfect and imperfect information games", arXiv 2112.03178. https://arxiv.org/abs/2112.03178
- [R5] Perolat et al., "Mastering the Game of Stratego with Model-Free Multiagent Reinforcement Learning", arXiv 2206.15378, and Science, DOI 10.1126/science.add4679. https://arxiv.org/abs/2206.15378
- [R6] Sokota, Vinitsky, Hu, Kolter, Farina, "Superhuman AI for Stratego Using Self-Play Reinforcement Learning and Test-Time Search", arXiv 2511.07312. https://arxiv.org/abs/2511.07312 (full text https://arxiv.org/html/2511.07312v1)
- [R7] Lanctot et al., "OpenSpiel: A Framework for Reinforcement Learning in Games", arXiv 1908.09453. https://arxiv.org/abs/1908.09453
- [R8] OpenSpiel algorithms page. https://github.com/google-deepmind/open_spiel/blob/master/docs/algorithms.md
- [R9] OpenSpiel repository metadata. https://api.github.com/repos/google-deepmind/open_spiel
- [R10] Perez-Liebana, Hsu, Emmanouilidis, Khaleque, Gaina, "Tribes: A New Turn-Based Strategy Game for AI Research", AIIDE 2020. https://ojs.aaai.org/index.php/AIIDE/article/download/7438/7287 and https://github.com/GAIGResearch/Tribes
- [R11] Tribes repository metadata. https://api.github.com/repos/GAIGResearch/Tribes
- [R12] Perez-Liebana et al., "Generating Diverse and Competitive Play-Styles for Strategy Games", arXiv 2104.08641. https://arxiv.org/abs/2104.08641
- [R13] tribes-rl README and metadata. https://github.com/pham-tuan-binh/tribes-rl and https://api.github.com/repos/pham-tuan-binh/tribes-rl
- [R14] Qi et al., "CivRealm: A Learning and Reasoning Odyssey in Civilization for Decision-Making Agents", arXiv 2401.10568. https://arxiv.org/abs/2401.10568
- [R15] Huang, Ontanon, Bamford, Grela, "Gym-uRTS: Toward Affordable Full Game Real-time Strategy Games Research with Deep Reinforcement Learning", arXiv 2105.13807. https://arxiv.org/abs/2105.13807 (full text https://ar5iv.labs.arxiv.org/html/2105.13807)
- [R16] Wang, Tang, Hao, Hao, Fu, Ma, "Large Scale Deep Reinforcement Learning in War-games", IEEE BIBM 2020, DOI 10.1109/BIBM49941.2020.9313387. https://ieeexplore.ieee.org/document/9313387/
- [R17] Xu, Hu, Wang, Yang, Ni, "MiaoSuan Wargame: A Multi-Mode Integrated Platform for Imperfect Information Game", IEEE CoG 2022, DOI 10.1109/CoG51982.2022.9893656. https://researchr.org/publication/XuHWYN22
- [R18] Sun et al., "Method for making multi-attribute decisions in wargames by combining intuitionistic fuzzy numbers with reinforcement learning", arXiv 2109.02354. https://arxiv.org/abs/2109.02354
- [R19] Sun, Zhao, Yu, Wang, Zhou, "Self Generated Wargame AI: Double Layer Agent Task Planning Based on Large Language Model", arXiv 2312.01090. https://arxiv.org/abs/2312.01090
- [R20] Yin et al., "WGSR-Bench: Wargame-based Game-theoretic Strategic Reasoning Benchmark for Large Language Models", arXiv 2506.10264. https://arxiv.org/abs/2506.10264
- [R21] Black, Darken, "Scaling Intelligent Agents in Combat Simulations for Wargaming", arXiv 2402.06694. https://arxiv.org/abs/2402.06694
- [R22] Black, "Mastering the Digital Art of War: Developing Intelligent Combat Simulation Agents for Wargaming Using Hierarchical Reinforcement Learning", arXiv 2408.13333. https://arxiv.org/abs/2408.13333
- [R23] Black, Darken, "A Hierarchical Hybrid AI Approach: Integrating Deep Reinforcement Learning and Scripted Agents in Combat Simulations", arXiv 2512.00249. https://arxiv.org/abs/2512.00249
- [R24] Huang, Ontanon, "A Closer Look at Invalid Action Masking in Policy Gradient Algorithms", arXiv 2006.14171. https://arxiv.org/abs/2006.14171
- [R25] Zwingenberger, "Transformers as Policies for Variable Action Environments", arXiv 2301.03679. https://arxiv.org/abs/2301.03679
- [R26] Creus Castanyer, "Centralized control for multi-agent RL in a complex Real-Time-Strategy game", arXiv 2304.13004. https://arxiv.org/abs/2304.13004
- [R27] Yu et al., "The Surprising Effectiveness of PPO in Cooperative, Multi-Agent Games", arXiv 2103.01955. https://arxiv.org/abs/2103.01955
- [R28] Vinyals et al., "Grandmaster level in StarCraft II using multi-agent reinforcement learning", Nature 2019, DOI 10.1038/s41586-019-1724-z. https://www.nature.com/articles/s41586-019-1724-z (record through https://api.semanticscholar.org/graph/v1/paper/DOI:10.1038/s41586-019-1724-z)
- [R29] DeepMind blog, "AlphaStar: Grandmaster level in StarCraft II using multi-agent reinforcement learning". https://deepmind.google/blog/alphastar-grandmaster-level-in-starcraft-ii-using-multi-agent-reinforcement-learning/
- [R30] Han et al., "TStarBot-X: An Open-Sourced and Comprehensive Study for Efficient League Training in StarCraft II Full Game", arXiv 2011.13729. https://arxiv.org/abs/2011.13729 (full text https://ar5iv.labs.arxiv.org/html/2011.13729)
- [R31] Lanctot et al., "A Unified Game-Theoretic Approach to Multiagent Reinforcement Learning", arXiv 1711.00832. https://arxiv.org/abs/1711.00832
- [R32] Heinrich, Silver, "Deep Reinforcement Learning from Self-Play in Imperfect-Information Games", arXiv 1603.01121. https://arxiv.org/abs/1603.01121
- [R33] Jaderberg et al., "Population Based Training of Neural Networks", arXiv 1711.09846. https://arxiv.org/abs/1711.09846
- [R34] Zhang et al., "A Survey on Self-play Methods in Reinforcement Learning", arXiv 2408.01072. https://arxiv.org/abs/2408.01072
- [R35] Petrenko et al., "Sample Factory: Egocentric 3D Control from Pixels at 100000 FPS with Asynchronous Reinforcement Learning", arXiv 2006.11751. https://arxiv.org/abs/2006.11751
- [R36] Stanley, Miikkulainen, "Evolving Neural Networks through Augmenting Topologies", Evolutionary Computation 10(2), 2002, DOI 10.1162/106365602320169811. https://dl.acm.org/doi/10.1162/106365602320169811
- [R37] Salimans, Ho, Chen, Sidor, Sutskever, "Evolution Strategies as a Scalable Alternative to Reinforcement Learning", arXiv 1703.03864. https://arxiv.org/abs/1703.03864
- [R38] Such et al., "Deep Neuroevolution: Genetic Algorithms Are a Competitive Alternative for Training Deep Neural Networks for Reinforcement Learning", arXiv 1712.06567. https://arxiv.org/abs/1712.06567
- [R39] Hansen, "The CMA Evolution Strategy: A Tutorial", arXiv 1604.00772. https://arxiv.org/abs/1604.00772
- [R40] Pierrot, Flajolet, "Evolving Populations of Diverse RL Agents with MAP-Elites", arXiv 2303.12803. https://arxiv.org/abs/2303.12803
- [R41] Anne et al., "Adversarial Coevolutionary Illumination with Generational Adversarial MAP-Elites", arXiv 2505.06617. https://arxiv.org/abs/2505.06617
- [R42] Partlan et al., "EvolvingBehavior: Towards Co-Creative Evolution of Behavior Trees for Game NPCs", arXiv 2209.01020. https://arxiv.org/abs/2209.01020
- [R43] Kozik, Machalewski, Marek, Ochmann, "Mimicking Playstyle by Adapting Parameterized Behavior Trees in RTS Games", arXiv 2111.12144. https://arxiv.org/abs/2111.12144
- [R44] Chikh Touami, Salem, Khelfi, "Hybrid Genetic Programming and Q-Learning for Behavior Tree Evolution in MicroRTS Tactical Scenarios", Informatica 2026, DOI 10.31449/inf.v50i14.14678. https://www.informatica.si/index.php/informatica/article/view/14678
- [R45] Suarez, "PufferLib 2.0: Reinforcement Learning at 1M steps/s", Reinforcement Learning Journal vol. 6, 2025, pp. 1378-1388. https://rlj.cs.umass.edu/2025/papers/Paper151.html
- [R46] Gymnasium repository metadata. https://api.github.com/repos/Farama-Foundation/Gymnasium
- [R47] PettingZoo repository metadata. https://api.github.com/repos/Farama-Foundation/PettingZoo
- [R48] CleanRL repository metadata and LICENSE. https://api.github.com/repos/vwxyzjn/cleanrl and https://raw.githubusercontent.com/vwxyzjn/cleanrl/master/LICENSE
- [R49] Ray repository metadata. https://api.github.com/repos/ray-project/ray
- [R50] Sample Factory repository metadata. https://api.github.com/repos/alex-petrenko/sample-factory
- [R51] PufferLib repository metadata. https://api.github.com/repos/PufferAI/PufferLib
- [R52] Pgx repository metadata. https://api.github.com/repos/sotetsuk/pgx
- [R53] MicroRTS repository metadata. https://api.github.com/repos/Farama-Foundation/MicroRTS
- [R54] Towers et al., "Gymnasium: A Standard Interface for Reinforcement Learning Environments", arXiv 2407.17032. https://arxiv.org/abs/2407.17032
- [R55] Terry et al., "PettingZoo: Gym for Multi-Agent Reinforcement Learning", arXiv 2009.14471. https://arxiv.org/abs/2009.14471
- [R56] Huang, Dossa, Ye, Braga, "CleanRL: High-quality Single-file Implementations of Deep Reinforcement Learning Algorithms", arXiv 2111.08819. https://arxiv.org/abs/2111.08819
- [R57] Liang et al., "RLlib: Abstractions for Distributed Reinforcement Learning", arXiv 1712.09381. https://arxiv.org/abs/1712.09381
- [R58] MicroRTS-Py repository metadata. https://api.github.com/repos/Farama-Foundation/MicroRTS-Py
- [R59] Lux-Design-S3 README and metadata. https://github.com/Lux-AI-Challenge/Lux-Design-S3/ and https://api.github.com/repos/Lux-AI-Challenge/Lux-Design-S3
- [R60] Xu, Yu, Fang, Wang, Wu, "Language Agents with Reinforcement Learning for Strategic Play in the Werewolf Game", arXiv 2310.18940. https://arxiv.org/abs/2310.18940
- [R61] Belle et al., "Agents of Change: Self-Evolving LLM Agents for Strategic Planning", arXiv 2506.04651. https://arxiv.org/abs/2506.04651
- [R62] Yuan et al., "MARSHAL: Incentivizing Multi-Agent Reasoning via Self-Play with Strategic LLMs", arXiv 2510.15414. https://arxiv.org/abs/2510.15414
- [R63] Chen et al., "Multi-Agent Evolve: LLM Self-Improve through Co-evolution", arXiv 2510.23595. https://arxiv.org/abs/2510.23595
- [R64] Bakhtin et al., "Human-level play in the game of Diplomacy by combining language models with strategic reasoning", Science 2022, DOI 10.1126/science.ade9097. https://api.semanticscholar.org/graph/v1/paper/DOI:10.1126/science.ade9097

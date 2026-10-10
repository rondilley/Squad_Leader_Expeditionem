# Training run report: the 1 million step rung, 2026-09-12

This is the report of the first rung of the learned agent ladder (slice 9, TC-13, TC-18,
TC-19). The run artifact is `runs/20260912T192005Z-ppo-s01-guards-counterattack`. The
snapshots and the TensorBoard scalars are in `runs/train_1m/`.

## Summary

The run completed its 1,000,000 steps on the GPU in 89 minutes with no error. The
pipeline, the league, the snapshots, and the evaluation all did their work. The policy did
not learn to play. At the end of the run it holds one command pair in the Advance Phase of
turn 1, a pickup and a drop, without end. Each evaluation game stopped at the command limit
with no result.

The evaluation numbers of 42.5 to 50 percent are truncated games, not wins. An earlier
message of this session read them as "the German side won and the Russian side lost". That
reading was incorrect, and this report corrects it.

## The command

```
sl-cli train --scenario s01_guards_counterattack --steps 1000000 --device cuda \
  --seed 20260912 --snapshot-every 50000 --out runs/train_1m \
  --tensorboard runs/train_1m/tb --eval-games 20
```

The learner held player 0, the Russian attacker. The league held random, v0 to v6, and each
snapshot. The PPO parameters were the defaults: 512 steps for each update, 4 epochs,
minibatch 128, clip 0.2, entropy coefficient 0.01, learning rate 0.0003, discount 1.0. The
net has 1,852,306 parameters (32 channels, hidden width 256).

## The run

| Measure | Value |
|---|---|
| Steps | 1,000,000 |
| Time | 5,321 s (89 minutes) |
| Rate | 188 steps/s at the end, 368 at the peak |
| Updates | 1,954 |
| Snapshots | 21, one at each 50,000 steps |
| GPU | RTX 5070 Laptop, 33 percent busy, 479 MiB |
| Stop cause | the step count is complete |

The rate fell from 368 to 157 steps/s between step 250,000 and step 625,000, and then
came back to 188. The cause is the league. Each snapshot is an opponent that runs the net
for each of its moves, and a scripted opponent does not. The more snapshots, the more of
the rollout time goes to the opponent.

## What the curves show

The values below are the TensorBoard scalars at nine points of the run.

| Step | Learner Elo | Win rate against v0 | Entropy | Value loss |
|---|---|---|---|---|
| 512 | 1484 | 1.00 | 2.71 | 0.018 |
| 125,440 | 1015 | 0.50 | 1.50 | 0.006 |
| 250,368 | 1031 | 0.33 | 0.006 | 0.000 |
| 375,296 | 1165 | 0.25 | 0.000 | 0.000 |
| 500,224 | 1156 | 0.20 | 1.58 | 0.003 |
| 625,152 | 1075 | 0.33 | 0.007 | 0.001 |
| 750,080 | 1134 | 0.33 | 0.365 | 0.000 |
| 875,008 | 1200 | 0.32 | 0.001 | 0.000 |
| 1,000,000 | 1286 | 0.32 | 0.000 | 0.000 |

Three things are in this table.

1. The entropy fell to zero by step 250,000 and stayed there, with two short rises. A
   policy with zero entropy gives one command for each state. This is the collapse of the
   policy, and it came before the first win.
2. The value loss went to zero with the entropy. The value head learned that each game
   gives zero, which is what a truncated game gives. So the critic agreed with the collapse.
3. The win rate against v0 fell from 1.0 to 0.3. Agent v0 walks to the objective and does
   nothing else, so the learner can no longer win the one game a random policy wins. The
   win rate against each other member of the league stayed between 0.0 and 0.04 for the
   full run.

The league Elo at the end: learner 1286, v0 1367, random 1556, v4 1596, v5 1615, v6 1619,
v2 1622, v1 1622, v3 1626. The snapshots are between 1363 and 1579. The snapshot of step
50,688, from before the collapse, has the highest rating of all the snapshots (1579).

## The evaluation (TC-18)

Twenty games against each constant opponent, sides balanced, the policy on its best
command with no sampling.

| Opponent | Wins | Losses | Draws | Score |
|---|---|---|---|---|
| random | 0 | 0 | 20 | 50.0 percent |
| v0 | 0 | 0 | 20 | 50.0 percent |
| v1 | 0 | 1 | 19 | 47.5 percent |
| v2 | 0 | 0 | 20 | 50.0 percent |
| v3 | 0 | 0 | 20 | 50.0 percent |
| v4 | 0 | 0 | 20 | 50.0 percent |
| v5 | 0 | 3 | 17 | 42.5 percent |
| v6 | 0 | 3 | 17 | 42.5 percent |

A draw here is a game that got to the limit of 20,000 commands with no result
(`SquadLeaderEnv.max_commands`). The evaluation counts a draw as half a win, so twenty
truncated games give 50 percent. The seven losses are games where the opponent won before
the limit. The policy won zero games of 160.

## The cause

A replay of the last snapshot (`learned:runs/train_1m/snapshots/snapshot-1000000.pt`)
against a random opponent shows the cycle. On each side the policy plays its set up, its
prep fire, and a small number of moves. Then, in the Advance Phase of turn 1, it plays
`pickup` and `drop` in turn: 1,426 and 1,425 times in the first 3,000 commands. It does not
play `end_phase`, so the game stays on turn 1. The same cycle occurs with the learner as
player 1.

The mechanism is the reward. The reward is terminal only: +1, -1, or 0. A game that gets
to the command limit gives 0. On the Russian side of scenario 1 a random policy does not
win. The gauntlet of this morning showed that the scripted agents win that side in 1 to 5
games of 20 against a competent German.

So a loss is -1 and a truncation is 0, and the best result a policy on that side can find
is the truncation. The pickup and drop pair is the cheapest procedure that holds the game
there. The policy learned what the reward told it to learn.

Two things made it worse. The discount is 1.0, so a 20,000 command truncation costs
nothing against a loss. And the entropy coefficient of 0.01 did not hold the policy open
for a sufficient time. On that side the wins are rare, and the search stopped first.

## What this means for the gates

- TC-13 (the ladder rung has a run artifact with the tournament): the 1 million rung has
  its artifact. The measurement is honest and it says the policy did not learn.
- TC-18 (win rate against each constant opponent, with intervals): measured. Zero wins.
- TC-19 (an Elo table with the learner and each member): the table is in the artifact.

The 10 million rung must not start on this configuration. Ten times more of the same
signal gives the same cycle.

## What to change before the next run

In this order, each with its test:

1. The truncation must not be worth more than a loss. Give a truncated game the loss
   reward for the attacker. Or give a small negative reward for each command. Then a cycle
   costs more than a defeat. This is the one change that removes the cycle on its own.
2. Put the learner on player 1 (`--player 1`, the German defender) for the sanity run. A
   policy that stands in a stone building and fires wins that side, so the run shows the
   pipeline learns when a win is possible.
3. A shaped reward for the attacker (item (e) of the strong-AI follow-ups): a term for
   each objective building held at the end of a turn, and a term for distance closed.
   Without it the attacker side has no gradient in the direction of the buildings.
4. A larger entropy coefficient (0.03 or more) with a discount below 1.0 (0.99), so the
   policy stays open longer and a long game costs something.
5. The evaluation must report a truncation as its own count and not as half a win. The
   `beats_opponent` flag was false in each row, so the gate was not misread by the code,
   but a reader of the win rate column was.

## Files

- `runs/20260912T192005Z-ppo-s01-guards-counterattack/`: the artifact (manifest, stats
  with the evaluation and the Elo table, the rate reports).
- `runs/train_1m/snapshots/`: 21 snapshots, `snapshot-50176.pt` to `snapshot-1000000.pt`.
- `runs/train_1m/tb/`: the TensorBoard scalars.
- `runs/train_1m/train.log`: the console report of the trainer.

## Addendum, the same day

The owner gave the design after this report. A loss and a game that does not end are
the two defeats, and each has a large cost. The reward scores each thing that changes
the chance of a win. The doctrine research sets the weights of each side. It is built in
`src/slagents/learned/reward.py`, with its tests, and the 1 million rung runs again on it
as `runs/train_1m_shaped/`.

Items 1, 3, 4, and 5 of the list above are in it. Item 2, the defender side run, is not
necessary first, because the attacker side has a gradient.

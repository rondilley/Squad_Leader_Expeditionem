# Player guide

This guide tells you how to play Squad Leader Expeditionem in the 3D window. It is for a
person who plays the game. It does not tell you the rules of the 1977 board game. The game
applies the rules for you, and the action log gives the rule number of each result.

This project is not affiliated with, sponsored by, or endorsed by Hasbro or Multi-Man
Publishing.

## Start a game

From the package (no Python necessary):

- Windows: double-click `SquadLeaderExpeditionem.exe`.
- Linux: run `./SquadLeaderExpeditionem` in the folder of the package.

The program opens the menu. Select the scenario, your side, the opponent, and the view (the
3D window or the 2D window). Then click Play. The opponent is the computer (`easy`, `normal`,
or `hard`), a person at this computer, or a person on your LAN.

From the source tree, with the venv active:

```
sl-cli launch
sl-cli window3d --scenario lib01_grain_office --agent normal
```

`--agent easy`, `normal`, or `hard` gives the computer opponent (agent v5, v6, or v7).
`--agent-side` gives the computer a side by its key in the scenario. The keys are `german`
and `russian` in scenarios s01 to s03a, and `allied` and `axis` in the library scenarios
and in s04.
The default is the second side. With no `--agent`, two persons play at one screen.

## The scenarios

The menu offers the 12 scenarios of the project library, from `lib01_grain_office` to
`lib12_the_long_front`. They are not copies of the 1977 scenario cards. Each one has a
balance test: the hard computer player wins between 45 and 55 percent of its games against
itself, when it plays each side.

From the source tree, `sl-cli window3d --scenario NAME` also starts these scenarios:
`s01_guards_counterattack`, `s02_tractor_works`, `s03a_streets_of_stalingrad`, and
`s04_armor_probe` (the armor game).

The window first shows the scenario card: the situation, the forces of each side, the turn
record, and the victory conditions. Press Begin, Space, or Enter to start the game.

## The turn

Each game turn has two player turns. In each player turn, the side that moves goes through
these phases (rule 4):

1. Rally Phase
2. Prep Fire Phase
3. Movement Phase
4. Defensive Fire Phase (the other side fires)
5. Advancing Fire Phase
6. Rout Phase
7. Advance Phase
8. Close Combat Phase

The panel on the right shows the turn and the phase, for example "turn 2 of 5: 3 more turns
after this one". In the last turn it says "the last turn". The game does the steps that
have no decision for you, for example the dice of a morale check.

## Set up your units

- A tray at the bottom of the board shows each counter of your side. Click a counter, and
  the hexes where it can go show in amber. Click one of them to place it. Or drag the
  counter from the tray, and release it on an amber hex.
- The amber hex at the pointer shows in green: the counter goes there.
- When a hex refuses the counter, the line above the tray gives the cause: the set up area
  of the counter, or the limit of rule 6.1 that the hex would go above. A hex of the set up
  area that the stacking limit closes shows in dark red.
- To move a counter that is on the board, click it on the board or in the tray. It goes
  back to the tray, and you place it again. You can also drag it to a different amber hex.
- Set up for me (or Ctrl and a) puts each counter of your side on the board for you.
- Click Finish set up when you are satisfied.

Support weapons:

- A machine gun or other support weapon goes with a unit that carries it. Put your squads
  and leaders on the board first. Then drag the weapon onto a shaded unit.
- A leader cannot carry an MMG or an HMG, so only squads are shaded for them. On the board,
  the weapon shows on top of the stack of its unit.
- A load above the free portage of a unit costs movement factors. Right click the unit to
  see its movement factors with the load.
- In the set up, right click a counter, on the board or in the tray, to read what each
  value of the counter means. Escape, a click, or a second right click closes the box.

## Give commands

There are three ways to give a command. They give the same commands.

1. The board. Click a hex to put its top unit in focus. A second click gets the next unit
   of the stack. The overlay shades where the unit can move and what it can fire at. Click
   a shaded hex to give that command. When the hex has more than one command, the list on
   the right shows them.
2. The unit menu. Right click a unit on the board, or click it and press Ctrl and Space.
   The menu shows the phase and each command of the unit in this phase, in groups: fire,
   smoke, close combat, move, weapons and equipment, and rally. Each row of a fire command
   gives its odds. Click a row to give that command.

   The menu also has the commands of your side (end the phase, resolve the fire group),
   About this unit, and Undo. Escape, a click off the menu, or a right click closes it.
3. The list. The list on the right has all the legal commands. Click a row, or move with
   Tab and press Enter. Type letters to make the list shorter. Backspace removes a letter,
   and Escape clears the list filter.

### Move

- In the Movement Phase, the hexes of the next step are blue. The pale blue hexes are the
  hexes that the unit can get to in the remaining part of the phase, with its remaining
  movement factors.
- Click a pale blue hex to move the unit there by the path of lowest cost. If a hex on the
  path stops the move, the unit stays at the last hex it entered, and the window says where.
  To select the path, click one blue hex at a time.
- To move a weapon, move the unit that carries it. The move label names the weapon, for
  example "move 6-2-8 (with MMG) to C3". A weapon alone on a hex moves only after a unit in
  that hex picks it up in the Movement Phase.
- A vehicle also shows the hexes it can get to, by its movement points. On the path it
  faces each next hex, so only its first hex can cost more for the covered arc. When a
  pivot makes the path cost less, the vehicle uses its one free pivot first. At the end it
  faces the direction of its last step.
- A hex with a different vehicle of your side is not pale blue: a vehicle can go through
  it, but it cannot stop there (rule 30.8). A move into rough terrain can roll the
  breakdown die (rule 39.1), and then the move stops.

### Fire

- In a fire phase, the legal targets are red. The orange hexes are in the range of the unit
  or of a weapon it carries (rule 9.1), with a clear line of sight. The pale orange hexes
  are in the long range (rule 9.2, half firepower). With strict line of sight the window
  shows the targets only.
- The fire phases are the Prep Fire Phase, the Defensive Fire Phase, and the Advancing Fire
  Phase. In each fire phase, the menu shows these commands:
  - the fire of the unit with its own firepower
  - the fire of each weapon of the unit
  - the leader of a fire group
  - the special weapons. The rules have no different command for suppressive fire.
- The pointer on a hex shades the line of sight from the unit in focus to that hex.
- Each fire has its animation: tracers in the colours of the army, the shell of a gun, the
  flame, the smoke, and the burst. A small burst on the target shows the result.
- The panel gives the action log with the rule, the dice, and the modifiers of each result.

### Undo

The Undo button is below the status at the top of the panel on the right. Ctrl and z does
the same. It cancels the last command when no die rolled in it and the command showed you
nothing new of the other side: a placement, a move, or a unit that you added to a fire
group. One undo cancels a full move to a pale blue hex. When the button is dim, you cannot
cancel a command.

## Win the game

- The hexes of the victory conditions are violet on the map. A violet hex that your side
  controls is green.
- Click "Victory conditions" in the panel, or press Ctrl and v, to make them strong. A box
  then gives the condition of the card and where you are at this time, for example:
  `You control 0 of the 5 violet hexes. You need 1 at the end of turn 5.`
  Click the button again, or press Escape, to close the box.
- At the end of the game a box in the middle of the board says "You won." or "You lost.".
  It also gives the side that wins, the victory condition and its result, and the losses of
  each side. Escape or a click closes the box.

## Keys and the mouse

When you hold a side, a letter that you type goes to the filter of the list. Thus the
shortcuts of the window use Ctrl. A person who only watches a game can use the letter
without Ctrl.

| Key or mouse | What it does |
|---|---|
| Click | Put a unit in focus, or give the command of a shaded hex |
| Right click | Open the unit menu (in the set up: the about box) |
| Drag | Move the board |
| Right-drag | Tilt and turn the 3D camera |
| Wheel, plus, minus | Zoom |
| Arrow keys | Move the board |
| `[` and `]` | Tilt the camera |
| Tab, Shift and Tab, Page Up, Page Down | Move in the list |
| Enter | Give the command of the selected row |
| Escape | Close a box, clear the filter, or clear the focus |
| Ctrl and Space | Open the menu of the unit in focus |
| Ctrl and z | Undo |
| Ctrl and a | Set up your side for you |
| Ctrl and v | Show the victory conditions |
| Ctrl and t | Change between the 3D camera and the 2D camera |
| Ctrl and r | Set the view again |
| Ctrl and i | Hide or show the overlay |
| Ctrl and o | Hide or show the shades of the unit in focus |
| Ctrl and m | Sound off or on |
| Ctrl and q | Stop the game |

The 2D window has the same tray, menu, overlay, and buttons. Its own keys are Ctrl and f (fit
the board in the window) and Ctrl and s (write a picture of the window).

## Save and continue a game

The game saves after each command. A game from the package goes in the folder `games` of
your data folder:

- Windows: `%LOCALAPPDATA%\SquadLeaderExpeditionem\games`
- Linux: `~/.local/share/squad-leader-expeditionem/games`

A game from the source tree goes in `runs/games/`. The window gives the path of the file
when it starts. The menu of the package has no command to continue a game. To continue a
game, start the program with the save file. On Windows, in PowerShell, in the package folder:

```
.\SquadLeaderExpeditionem.exe window3d --resume "$env:LOCALAPPDATA\SquadLeaderExpeditionem\games\GAME.jsonl"
```

On Linux:

```
./SquadLeaderExpeditionem window3d --resume ~/.local/share/squad-leader-expeditionem/games/GAME.jsonl
```

From the source tree: `sl-cli window3d --resume runs/games/GAME.jsonl`. The game plays each
command of the file again, checks that each result is the same, and then you continue. The
game saves the next commands in the same file.

## Play a person on your LAN

The person who hosts the game selects "A person on the LAN: you are the host". The menu
shows the address of the computer and a room code. The other person selects "A person on
the LAN: join a game", types the address and the room code, and clicks Play. The host plays
the side that moves first.

The game uses TCP port 8731. When Windows shows a firewall
question, let SquadLeaderExpeditionem use the private network.

## The collection of your games

At the first start, the menu asks if the game can send your recorded games to the
collection server of the project. The computer players learn from these games. You can
change your answer in the menu at all times. The game sends a game only when you agreed and
when you have a player key (`collect.key.txt`). `READ_ME_FIRST.txt` in the package tells
what a sent game holds.

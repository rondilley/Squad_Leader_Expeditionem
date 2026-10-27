Squad Leader Expeditionem

A tactical game of infantry and armor, with the 4th edition rules of a 1977 board game.
This project is not affiliated with, sponsored by, or endorsed by Hasbro or Multi-Man
Publishing. The licence is GPL-3.0-or-later (see LICENSE).


To start the game

Windows: double-click SquadLeaderExpeditionem.exe in this folder.
Linux: run ./SquadLeaderExpeditionem in this folder.

You do not have to install Python or other software.

At the first start, the game shows a question: can it send your recorded games to the
collection server of the project? The computer players learn from these games. You can change your
answer in the menu at all times.

In the menu, select:

1. The scenario.
2. Your side.
3. The opponent: the computer (easy, normal, or hard), a person at this computer, or a
   person on your LAN.
4. The view: the 3D window or the 2D window.

Then click Play.


Your player key

The game sends your games only when you agreed and when you have a player key. The project
owner gives you a key file, collect.key.txt. Put it in this folder, next to the program.
Do not give your key file to other persons.


Where the game keeps your data

Windows: %LOCALAPPDATA%\SquadLeaderExpeditionem
Linux:   ~/.local/share/squad-leader-expeditionem

The folder "games" has one file for each game. The game keeps these files also when it
sends them. The file "settings.json" has your answer about the collection. The folder
"logs" has the messages of the program.


What a sent game has

The scenario, the dice seed, and the commands of each side. Each command shows if a person
or the computer gave it. The name of your player key, and the version of the game. The server also records the network
address of your computer. A sent game has no other data about you.


A game on your LAN

The person who hosts the game selects "A person on the LAN: you are the host". The menu
shows the address of the computer and a room code. The other person selects "A person on
the LAN: join a game", types the address and the room code, and clicks Play. The host
plays the side that moves first.

The game uses TCP port 8731. When Windows shows a firewall question, let
SquadLeaderExpeditionem use the private network.

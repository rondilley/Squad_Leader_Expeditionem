"""The collection of played games, for the training of the computer players.

The packaged game saves each game to the player's disk (`slhost.savegame`). When the player
agreed at the first start (`settings`), the uploader (`client`) sends each game that a person
played to the collector (`server`). The collector checks the key of the player, plays each game
again through the core, and keeps the games whose hashes agree.

A game is its seed, its switches, and its command log, so the save file is the whole record:
the trainer makes each position and each decision again from it. Each command line has its
source (`human`, `agent`, `route`, `forced`), so the decisions of a person are known.

The wire (`wire`) is HTTP with an HMAC of each request, by a key for each player (`keys`).
"""

"""The rules core.

No file access, no network, no clock, no print. The core gets a state and a
command and gives a new state, events, and a hash. Slice 1 holds the geometry,
the board data model, and line of sight (rule 7).
"""

__version__ = "0.1.0"

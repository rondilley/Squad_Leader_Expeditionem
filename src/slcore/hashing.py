"""The state hash (FR-13, DR-04): SHA-256 over the canonical state document.

A state never changes, so the hash is computed one time and kept on the object. The
memo is not a field of the record, so it is not part of the document, the equality, or
a copy made with `with_`.

The canonical document is `json.dumps(state.to_dict(), sort_keys=True,
separators=(",", ":"), ensure_ascii=True)`. Most units do not change from one state to
the next, so the JSON text of each unit is kept on the unit (UNIT_JSON_ATTRIBUTE), and
the text of a state is the text of its other fields with the unit texts put in the
place of the unit list. The bytes are the same as the full `json.dumps`, and
`tests/perf/test_state_bytes.py` compares the two on the states of real games (NFR-01).
"""

from __future__ import annotations

import hashlib
import json

from slcore.game import State
from slcore.units import Unit

CACHE_ATTRIBUTE = "_hash_memo"
# The JSON text of one unit record. It is not a field of the record.
UNIT_JSON_ATTRIBUTE = "_json_memo"

_ENCODER = json.JSONEncoder(sort_keys=True, separators=(",", ":"), ensure_ascii=True)
# The mark that holds the place of the unit list. The encoder writes the zero
# characters as escapes, and the key comes before it, so the pair is found only there.
_UNITS_MARK = "\x00units\x00"
_UNITS_SLOT = '"units":' + _ENCODER.encode(_UNITS_MARK)


def unit_json(unit: Unit) -> str:
    """The canonical JSON text of one unit record, made one time for each unit object."""
    found = unit.__dict__.get(UNIT_JSON_ATTRIBUTE)
    if found is None:
        found = _ENCODER.encode(unit.to_dict())
        unit.__dict__[UNIT_JSON_ATTRIBUTE] = found
    return found


def state_text(state: State, with_seq: bool = True) -> str:
    """The canonical JSON text of the state document.

    With `with_seq` false the command count is not in the text: that is the position
    of the state, which a cycle guard compares.
    """
    head = state.document(_UNITS_MARK)
    if not with_seq:
        del head["seq"]
    text = _ENCODER.encode(head)
    before, slot, after = text.partition(_UNITS_SLOT)
    if not slot:
        raise ValueError("the state document has no unit list")
    return before + '"units":[' + ",".join([unit_json(u) for u in state.units]) + "]" + after


def state_bytes(state: State) -> bytes:
    return state_text(state).encode("ascii")


def position_key(state: State) -> str:
    """SHA-256 of the state document without its command count (`seq`)."""
    return hashlib.sha256(state_text(state, with_seq=False).encode("ascii")).hexdigest()


def hash_state(state: State) -> str:
    found = getattr(state, CACHE_ATTRIBUTE, None)
    if found is not None:
        return found
    value = hashlib.sha256(state_bytes(state)).hexdigest()
    object.__setattr__(state, CACHE_ATTRIBUTE, value)
    return value

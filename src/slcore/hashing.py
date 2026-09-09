"""The state hash (FR-13, DR-04): SHA-256 over the canonical state document.

A state never changes, so the hash is computed one time and kept on the object. The
memo is not a field of the record, so it is not part of the document, the equality, or
a copy made with `with_`.
"""

from __future__ import annotations

import hashlib
import json

from slcore.game import State

CACHE_ATTRIBUTE = "_hash_memo"


def state_bytes(state: State) -> bytes:
    return json.dumps(state.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def hash_state(state: State) -> str:
    found = getattr(state, CACHE_ATTRIBUTE, None)
    if found is not None:
        return found
    value = hashlib.sha256(state_bytes(state)).hexdigest()
    object.__setattr__(state, CACHE_ATTRIBUTE, value)
    return value

"""The answer schema of the model agent (FR-46).

The model writes its analysis in free text first, and then one JSON object. The object is
flat and it has three fields: the command it selects, the plan it wants to keep, and the
reason in one line.

The command field is an enum of the legal command identities of this decision. A model
that answers with an identity outside that list has given an invalid command, and the
harness counts it and asks again (FR-47). A model that answers with an identity inside it
cannot have given an illegal command, because the list came from the core.

The schema is flat because a nested schema raises the invalid rate of a small model, and
the local model of this project is a small model (RV-6).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

COMMAND_FIELD = "command_id"
PLAN_FIELD = "plan"
REASON_FIELD = "reason"
MAX_PLAN = 240
MAX_REASON = 240
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


class SchemaError(Exception):
    """The answer of the model does not satisfy the schema."""


@dataclass(frozen=True)
class Decision:
    """What the harness takes from one answer."""

    command_id: str
    plan: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {COMMAND_FIELD: self.command_id, PLAN_FIELD: self.plan, REASON_FIELD: self.reason}


def json_schema(legal_ids: Sequence[str]) -> dict[str, Any]:
    """The flat schema, with the legal identities as the enum of the command field.

    Each field is in `required`, because a provider in its strict mode refuses a schema
    whose `required` does not name each property. The parser is not strict in the same
    way: a plan and a reason that are empty are still an answer (FR-46).
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [COMMAND_FIELD, PLAN_FIELD, REASON_FIELD],
        "properties": {
            COMMAND_FIELD: {"type": "string", "enum": list(legal_ids)},
            PLAN_FIELD: {"type": "string"},
            REASON_FIELD: {"type": "string"},
        },
    }


def describe(legal_ids: Sequence[str]) -> str:
    """The part of the prompt that says what the answer must look like."""
    return (
        "End your answer with one JSON object and nothing after it. The object has three "
        f"fields. `{COMMAND_FIELD}` is one of the command identities of the list above, and "
        f"nothing else. `{PLAN_FIELD}` is one line that says what you want to do in the "
        f"next phases. `{REASON_FIELD}` is one line that says why you selected this command."
    )


def balanced_objects(text: str) -> list[str]:
    """Each outer `{...}` span of the text with its braces in balance, in order.

    A brace inside a JSON string does not count, and a backslash escapes the next
    character of a string. The pattern `\\{.*\\}` that this replaces was greedy: it took
    the text from the first brace of the analysis to the last brace of the answer, and an
    analysis that named a set such as {A1, B2} made the whole answer fail to parse (L6).
    """
    spans: list[str] = []
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"' and depth > 0:
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append(text[start : i + 1])
    return spans


def extract(text: str) -> dict[str, Any]:
    """The last JSON object of an answer, from a fence or from the raw text."""
    if not text or not text.strip():
        raise SchemaError("the answer is empty")
    fences = FENCE.findall(text)
    candidates = list(reversed(fences)) if fences else []
    candidates.extend(reversed(balanced_objects(text)))
    for candidate in candidates:
        try:
            document = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(document, dict):
            return document
    raise SchemaError("the answer holds no JSON object")


def parse(text: str, legal_ids: Sequence[str]) -> Decision:
    """One decision from one answer. Raises SchemaError with the reason to send back."""
    document = extract(text)
    if COMMAND_FIELD not in document:
        raise SchemaError(f"the object has no {COMMAND_FIELD} field")
    command_id = str(document[COMMAND_FIELD]).strip()
    if command_id not in set(legal_ids):
        raise SchemaError(
            f"the value of {COMMAND_FIELD} is not one of the command identities of this decision"
        )
    plan = str(document.get(PLAN_FIELD, ""))[:MAX_PLAN]
    reason = str(document.get(REASON_FIELD, ""))[:MAX_REASON]
    return Decision(command_id=command_id, plan=plan, reason=reason)

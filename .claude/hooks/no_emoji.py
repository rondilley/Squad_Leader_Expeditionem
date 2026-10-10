"""Hook: Rule 1 - NO Icons/Emoji/Symbols in code, output, or documentation.

PreToolUse hook for Edit|Write tools.
Checks new_string (Edit) or content (Write) for emoji/unicode symbols.

Path allow-list (2026-04-19): certain files exist specifically to carry
non-ASCII adversarial fixtures (multilingual rulepacks, Unicode
obfuscation / homoglyph / confusable / leetspeak / encoding-evasion test
cases, the benchmark corpus). Those files bypass the check entirely —
the whole point of them is to contain oddball encodings and foreign
scripts. Every other path in the repo remains strict: no emoji, no
geometric shapes, no decorative symbols, no stars, no checkmarks.
"""

import json
import re
import sys


# Paths that may contain any non-ASCII content because adversarial
# detection work REQUIRES foreign-script and oddball-encoding fixtures.
# Matched as a substring of the target path (Write `file_path` or Edit
# `file_path`), with forward-slash normalization so Windows paths work.
ALLOW_PATHS = (
    "/rulepack/",
    "/tox-bench-v0/",
    "/tests/unit/test_unicode_detector.py",
    "/tests/unit/test_mixed_script.py",
    "/tests/unit/test_confusables.py",
    "/tests/unit/test_leetspeak.py",
    "/tests/unit/test_encoding_evasion.py",
    "/tests/unit/test_model_imperatives.py",
    "/tests/unit/test_translate_imperatives.py",
)


def is_allowlisted_path(path: str) -> bool:
    if not path:
        return False
    norm = path.replace("\\", "/")
    return any(fragment in norm for fragment in ALLOW_PATHS)


# Regex matching common emoji and symbol ranges
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Misc symbols and pictographs
    "\U0001F680-\U0001F6FF"  # Transport and map
    "\U0001F1E0-\U0001F1FF"  # Flags
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"  # Enclosed characters
    "\U0001F900-\U0001F9FF"  # Supplemental symbols
    "\U0001FA00-\U0001FA6F"  # Chess symbols
    "\U0001FA70-\U0001FAFF"  # Symbols extended-A
    "\U00002600-\U000026FF"  # Misc symbols
    "\U0000FE00-\U0000FE0F"  # Variation selectors
    "\U0000200D"             # Zero-width joiner
    "\U00002B50"             # Star
    "\U00002714"             # Check mark
    "\U00002716"             # X mark
    "\U0000274C"             # Cross mark
    "\U000025CF"             # Black circle
    "\U000025CB"             # White circle
    "\U000025A0"             # Black square
    "\U000025A1"             # White square
    "\U00002022"             # Bullet (allow this one - common in text)
    "]",
    re.UNICODE,
)

# Exemption: bullet point U+2022 is acceptable in documentation
ALLOWED = {"\u2022"}


def check_text(text):
    """Return list of found emoji/symbols with their positions."""
    findings = []
    for match in EMOJI_PATTERN.finditer(text):
        char = match.group()
        if char in ALLOWED:
            continue
        line_num = text[:match.start()].count("\n") + 1
        findings.append((line_num, repr(char)))
    return findings


def main():
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})

    # Skip allow-listed paths: rulepack YAML, benchmark corpus, and
    # evasion-detector test cases are supposed to contain adversarial
    # oddball encodings.
    target_path = tool_input.get("file_path", "")
    if is_allowlisted_path(target_path):
        sys.exit(0)

    # Edit tool uses new_string, Write tool uses content
    text = tool_input.get("new_string", "") or tool_input.get("content", "")
    if not text:
        sys.exit(0)

    findings = check_text(text)
    if findings:
        locations = ", ".join(f"line {ln}: {ch}" for ln, ch in findings[:5])
        msg = f"RULE 1 VIOLATION: No emoji/icons/symbols allowed. Found: {locations}"
        if len(findings) > 5:
            msg += f" (and {len(findings) - 5} more)"
        print(msg, file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()

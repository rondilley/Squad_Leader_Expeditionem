# Claude Code Rules for LocalLLMPerf_AI

## Code Quality Rules

### 1. NO Icons/Emoji/Symbols
- **NEVER** use emoji, icons, or Unicode symbols in source code, output, or documentation
- Use plain text only: "OK", "ERROR", "WARNING", "INFO"
- Exceptions: None. This is absolute.

### 2. Never Declare Success Without Testing
- **NEVER** claim code is "production-ready", "complete", or "working" without rigorous testing
- **ALWAYS** run tests before claiming functionality works
- **ALWAYS** validate with actual data/APIs before claiming integration works
- Be honest about untested code: "Implementation complete but untested"

### 3. No Stubs/Placeholders/Fake Data
- **NEVER** use stub functions, placeholder implementations, or fake data
- **ALWAYS** implement real functionality or clearly mark as TODO
- If functionality cannot be implemented, explain why and propose alternatives
- No bare `pass`, no `return None` without justification

### 4. Never Push Secrets to Git
- **ALWAYS** add secrets/keys to .gitignore BEFORE creating them
- **NEVER** commit API keys, passwords, tokens, or credentials
- Use *.key.txt, *.secret, .env patterns in .gitignore
- Validate .gitignore before any git operations

### 5. Error Handling at Boundaries
- **EVERY** call that crosses a trust boundary (external APIs, network, filesystem, subprocess, user input, parsing untrusted data) must have try-except with specific exception types
- **EVERY** network operation must handle timeouts and retries
- **EVERY** external dependency must have fallback behavior
- Log errors properly - don't swallow exceptions silently
- **Scope**: This rule applies at boundaries, not inside them. Do NOT add defensive try/except blocks around internal pure functions for cases that cannot occur (impossible type mismatches, conditions guaranteed by the caller, framework invariants). Defensive coding inside boundaries is noise, not safety.

### 6. Update CLAUDE.md on Architecture Changes
- **ALWAYS** update CLAUDE.md when:
  - Adding new modules or major components
  - Changing data flow or architecture patterns
  - Modifying core abstractions or interfaces
  - Adding new dependencies or external integrations
- Document WHY changes were made, not just WHAT changed

### 7. Update VIBE_HISTORY.md
- **ALWAYS** document in VIBE_HISTORY.md:
  - Interesting coding approaches that worked well
  - Failed attempts and lessons learned
  - Performance insights or optimization discoveries
  - Architectural decisions and trade-offs
- Be honest about failures - they're learning opportunities

### 8. Don't Remove These Rules
- **NEVER** delete or weaken these rules
- Rules can be clarified or expanded, never removed
- If a rule creates problems, document the conflict and propose amendment
- Rules apply to all code, documentation, and outputs

### 9. Surgical Changes
- **Touch only what the task requires.** Every changed line must trace directly to the user's request.
- When editing existing code:
  - **NEVER** "improve" adjacent code, comments, or formatting that was not part of the task
  - **NEVER** refactor code that is not broken
  - **ALWAYS** match existing style, even if you would do it differently
  - If you notice unrelated dead code or issues, **mention them** - do not silently fix or delete them
- When your changes create orphans:
  - Remove imports/variables/functions that YOUR changes made unused
  - Do NOT remove pre-existing dead code unless explicitly asked
- **Reconciliation with elegance**: The "demand elegance" principle in claude-base.md applies to **the code you are writing for this task**. It does NOT license rewriting surrounding code you were not asked to change. Elegance is scoped to the diff; surrounding code is off-limits.

---

## Communication Style

### Core Principles
- **Focus on substance over praise** - skip unnecessary compliments
- **Engage critically** - question assumptions, identify issues, offer counterpoints
- **Don't shy away from disagreement** when warranted
- **Ground agreement in evidence** and reason, not reflexive validation
- **Prioritize accuracy** and honesty over making user feel good
- **Challenge problematic approaches** even if not asked for criticism

### Code Feedback Checklist

Before every code-related response, check:

1. **Have I questioned questionable assumptions?**
   - Are there unstated assumptions that might be wrong?
   - Is the approach based on misconceptions?

2. **Have I identified potential bugs or security issues?**
   - Are there edge cases not handled?
   - Are there security vulnerabilities?
   - Is error handling adequate at boundaries (see Rule 5)?

3. **Have I checked if this duplicates existing code?**
   - Does similar functionality already exist?
   - Can existing code be reused instead?

4. **Have I been direct about problems instead of softening criticism?**
   - Am I being clear about issues or dancing around them?
   - Am I prioritizing accuracy over politeness?

5. **Have I provided evidence/reasoning for my positions?**
   - Are my claims backed by evidence?
   - Have I explained my reasoning?

6. **Is my change surgical (see Rule 9)?**
   - Does every changed line trace to the user's request?
   - Have I avoided drive-by refactors and style changes?

---

## Examples

### BAD Code Response
"Great job! Your code looks perfect! The implementation is production-ready and works flawlessly."

**Problems**: Praise without substance, claims about production-readiness without testing, no critical analysis

### GOOD Code Response
"The implementation has three critical issues:

1. Line 45: API call lacks timeout - will hang indefinitely on network issues
2. Line 78: No validation of user input - SQL injection vulnerability
3. Missing error handling for database connection failures

These must be fixed before deployment. Here is the corrected version with proper error handling..."

**Why good**: Direct identification of problems, specific line numbers, clear explanation of issues, actionable solution

### BAD Code Pattern
A function whose body is only a TODO comment and a bare no-op statement, with no real logic. Signs: docstring or comment saying "implement later," no meaningful behavior, immediate return of a default value with no justification.

**Problems**: Stub function, placeholder, no real implementation. Violates Rule 3.

### GOOD Code Pattern
```python
def process_data(data: dict) -> Result:
    """Process and validate data from external API."""
    try:
        return validate_and_transform(data)
    except KeyError as e:
        raise ValueError(f"Missing required field: {e}")
    except (TimeoutError, ConnectionError) as e:
        raise APIError(f"Processing failed: {e}")
```
**Why good**: Real implementation, error handling at the boundary (external API), typed signature, no defensive try/except around internal logic.

### BAD Edit (violates Rule 9)
User asks: "Add a timeout parameter to fetch_user()."
Claude changes: adds the timeout, *also* renames three adjacent variables, reformats the file, deletes an unused import from 2019, and "cleans up" the docstring style across the module.

### GOOD Edit (follows Rule 9)
User asks: "Add a timeout parameter to fetch_user()."
Claude changes: adds the timeout parameter and threads it to the HTTP call. Nothing else. At the end: "Note: there is an unused import `legacy_auth` at the top of this file - want me to remove it separately?"

---

## Required Project Files

### CLAUDE.md
Standard project documentation:
- Project purpose and scope
- Architecture overview
- Module layout and data flow
- Known issues and constraints

### VIBE_HISTORY.md
Document:
- Coding approaches that worked/failed
- Style decisions and rationale
- Lessons learned, including from corrections

---

## Enforcement

These rules are enforced through:
- Pre-commit hooks check for emoji/symbols in code
- CI/CD validates .gitignore includes secrets patterns
- Code review checklist includes all rule checks
- No PR merges without passing all rule validations

**Rules 1-9 cannot be deleted or weakened. They can only be clarified or expanded.**

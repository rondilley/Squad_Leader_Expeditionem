## Workflow Orchestration

### 0. Think Before Coding
Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- **State your assumptions explicitly.** If the task depends on a fact you are inferring (not verifying), name it.
- **If uncertain, ask.** Do not guess silently.
- **If multiple interpretations exist, present them — do not pick silently.** List the options, say which you'd pick and why, then wait for confirmation on non-trivial forks.
- **If a simpler approach exists, say so.** Push back when the request looks overcomplicated.
- **If something is unclear, stop.** Name what's confusing. Ask. Do not code around confusion.

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately – don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done (Goal-Driven Execution)
- **Define success criteria before implementing.** Convert vague asks into verifiable goals:
  - "Add validation" -> "Write tests for invalid inputs, then make them pass"
  - "Fix the bug" -> "Write a test that reproduces it, then make it pass"
  - "Refactor X" -> "Ensure the existing tests pass before and after"
- **For multi-step tasks, state a brief plan with a verify step per item:**
  1. [Step] -> verify: [check]
  2. [Step] -> verify: [check]
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness
- Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification - push back and get them tightened before starting.

### 5. Demand Elegance (Balanced, Scoped)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes – don't over-engineer
- Challenge your own work before presenting it
- **Scope (reconciles with claude-code-rules.md Rule 9 - Surgical Changes)**: "Elegance" applies only to **the code you are writing for the current task**. It does NOT license rewriting, reformatting, or "cleaning up" surrounding code that was not part of the ask. If adjacent code looks ugly, note it and offer a follow-up - do not silently fold it into this change.

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests – then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
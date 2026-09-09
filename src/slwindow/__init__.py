"""The desktop window: a separate window on Windows and on Unix, and not a browser.

The window is one more consumer of the core. It talks to the same host the browser client
talks to, over the same protocol, so it holds no rule and no rule table (AR-06). The
`embedded` module starts a host inside the same process when nobody named one, which is
what a person who wants to watch a game wants: one command, one window.
"""

from __future__ import annotations

__all__ = ["app", "client", "counters", "embedded", "layout", "panel", "render", "theme"]

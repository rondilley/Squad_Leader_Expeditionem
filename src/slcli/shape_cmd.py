"""`sl-cli shape`: record a position corpus, analyze it, and write the report.

`sl-cli shape --record --pairs v7:v7,v7:v6 --games 100 --out runs/shape_v7` plays the
games and writes the corpus. `sl-cli shape --analyze runs/shape_v7` reads it and writes
`analysis.json` and `report.md` next to it. `--cnn` adds the picture model of question 3,
which needs torch. The two steps go in one call when both flags are set.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # the type only, so the module imports with no array library
    from slshape.record import Corpus


class ShapeNotInstalled(Exception):
    """The array library is not installed, and the shape study cannot run without it."""

    def __init__(self) -> None:
        super().__init__(
            "the shape study needs numpy. Install it with: pip install -e \".[train]\""
        )


def load_shape():
    """Import the study late, so `sl-cli --help` works with no array library installed."""
    try:
        from slshape import analyze as analysis
        from slshape.record import Corpus, CorpusError, record_corpus
    except ImportError as exc:  # the boundary of an optional dependency
        raise ShapeNotInstalled() from exc
    return analysis, Corpus, CorpusError, record_corpus


def pairs_of(text: str) -> list[tuple[str, str]]:
    """`v7:v7,v7:v6` as pairs. A colon inside a bracket belongs to the agent name."""
    out: list[tuple[str, str]] = []
    for part in _split(text, ","):
        names = _split(part, ":")
        if len(names) != 2:
            raise ValueError(f"a pair is first:second, not {part!r}")
        out.append((names[0], names[1]))
    return out


def _split(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def pairs_from_evolve(directory: str | Path, panel: list[str], limit: int = 0) -> list[tuple[str, str]]:
    """Each candidate text of an evolution artifact against each agent of the panel.

    The candidates of a search play with different parameters, so their games hold the
    variety of shape a corpus of one doctrine does not. The candidates come in the order
    of their mean score, best first, and `limit` keeps the first ones.
    """
    try:
        stats = json.loads((Path(directory) / "stats.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read the evolution artifact in {directory}: {exc}") from exc
    seen: list[str] = []
    for cand in sorted(stats["candidates"], key=lambda c: (-c["mean"], c["id"])):
        if cand["text"] not in seen:
            seen.append(cand["text"])
    if limit > 0:
        seen = seen[:limit]
    return [(text, opponent) for text in seen for opponent in panel]


def _model_line(name: str, m: dict[str, Any] | None) -> str:
    if not m:
        return f"| {name} | no fit | | |"
    return f"| {name} | {m['accuracy'] * 100:.1f} | {m['log_loss']:.3f} | {m['base_rate'] * 100:.1f} |"


def report_text(result: dict[str, Any], corpus: Corpus, cnn: dict[str, dict[str, Any]] | None = None) -> str:
    """The report in Markdown: the corpus, the models, and the shapes that go with a win."""
    sides = ("player 0", "player 1")
    lines = [
        f"# Shape analysis of {corpus.scenario}",
        "",
        f"Corpus: {result['games']} games, {result['games_with_a_winner']} with a winner, {result['positions']} positions on board {corpus.board}.",
        f"Wins: player 0 {result['wins_by_player']['0']}, player 1 {result['wins_by_player']['1']}. Turns {result['turns'][0]} to {result['turns'][-1]}.",
        "",
        "A position is the end of a Movement Phase or an Advance Phase. Each row is one side of a position, with the label 'this side won the game'.",
        "",
    ]
    for p in (0, 1):
        entry = result["players"][str(p)]
        lines.append(f"## {sides[p]}")
        lines.append("")
        lines.append("### Does the shape hold information the material does not? (all turns, cross validation by game)")
        lines.append("")
        lines.append("| Model | Accuracy percent | Log loss | Base rate percent |")
        lines.append("|---|---|---|---|")
        models = entry["all_turns"]["models"]
        lines.append(_model_line("material", models["material"]))
        lines.append(_model_line("shape", models["shape"]))
        lines.append(_model_line("both", models["both"]))
        if cnn and str(p) in cnn:
            c = cnn[str(p)]
            lines.append(f"| picture net | {c['accuracy'] * 100:.1f} | {c['log_loss']:.3f} | |")
        lines.append("")
        lines.append("### The shape statistics that differ most between the winners and the losers (all turns)")
        lines.append("")
        lines.append("| Statistic | AUC | Winners | Losers | Positions won | Positions lost |")
        lines.append("|---|---|---|---|---|---|")
        for a in entry["all_turns"]["top_shape"]:
            lines.append(f"| {a['feature']} | {a['auc']:.3f} | {a['winners']} | {a['losers']} | {a['n_win']} | {a['n_lose']} |")
        lines.append("")
        lines.append("### The gain of each shape statistic on top of the material (all turns)")
        lines.append("")
        lines.append("| Statistic | Gain in log loss | Accuracy percent with it |")
        lines.append("|---|---|---|")
        for g in entry["all_turns"]["partial_gains"][:8]:
            lines.append(f"| {g['feature']} | {g['gain']:+.4f} | {g['accuracy'] * 100:.1f} |")
        lines.append("")
        tactical = entry.get("tactical")
        if tactical and tactical.get("both"):
            lines.append("### The tactical label: does the side lose a squad before its next position?")
            lines.append("")
            lines.append(f"{tactical['n']} positions, a loss in {tactical['rate'] * 100:.1f} percent of them.")
            lines.append("")
            lines.append("| Model | Accuracy percent | Log loss | Base rate percent |")
            lines.append("|---|---|---|---|")
            lines.append(_model_line("material", tactical["material"]))
            lines.append(_model_line("shape", tactical["shape"]))
            lines.append(_model_line("both", tactical["both"]))
            lines.append("")
            lines.append("| Statistic | Gain in log loss | Accuracy percent with it |")
            lines.append("|---|---|---|")
            for g in tactical["gains"][:8]:
                lines.append(f"| {g['feature']} | {g['gain']:+.4f} | {g['accuracy'] * 100:.1f} |")
            lines.append("")
        lines.append("### By turn: the models and the top shape statistics")
        lines.append("")
        for turn, t in entry["by_turn"].items():
            m = t["models"]
            if not m.get("both"):
                lines.append(f"- Turn {turn}: {m['n']} positions, no fit.")
                continue
            top = ", ".join(f"{a['feature']} {a['auc']:.2f}" for a in t["top_shape"][:5])
            lines.append(
                f"- Turn {turn} ({m['n']} positions): material {m['material']['accuracy'] * 100:.0f} percent, "
                f"shape {m['shape']['accuracy'] * 100:.0f}, both {m['both']['accuracy'] * 100:.0f}, base {m['both']['base_rate'] * 100:.0f}. Top shape: {top}."
            )
        lines.append("")
    lines.append("## How to read it")
    lines.append("")
    lines.append("An AUC above 0.5 means the winners have the higher value, below 0.5 the losers. The gain of 'both' over 'material' is the information the shape holds beyond the counts. The gain of one statistic is the fall of the held-out log loss when it joins the material model: a statistic that is a proxy of the material gives none, whatever its AUC. A picture net above 'both' means the picture holds a shape the statistics do not name.")
    lines.append("")
    return "\n".join(lines)


def run(args: Any) -> int:
    analysis, Corpus, CorpusError, record_corpus = load_shape()
    out = Path(args.out)
    corpus: Corpus | None = None
    if args.record:
        pairs = pairs_of(str(args.pairs)) if args.pairs else []
        if args.pairs_from_evolve:
            pairs.extend(pairs_from_evolve(args.pairs_from_evolve, _split(str(args.panel), ","), args.limit))
        corpus = record_corpus(args.scenario, pairs, args.games, args.seed, workers=args.workers, progress=bool(args.progress))
        corpus.write(out)
        print(f"corpus: {corpus.size} positions from {len(corpus.games)} games in {out}")
    if args.analyze:
        try:
            corpus = corpus or Corpus.read(out)
        except CorpusError as exc:
            print(str(exc))
            return 1
        result = analysis.analyze(corpus)
        cnn: dict[str, dict[str, Any]] | None = None
        if args.cnn:
            cnn = {str(p): analysis.picture_model(corpus, p) for p in (0, 1)}
            result["picture_model"] = cnn
        (out / "analysis.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        text = report_text(result, corpus, cnn)
        (out / "report.md").write_text(text, encoding="utf-8")
        print(text)
    if not args.record and not args.analyze:
        print("nothing to do: give --record, --analyze, or both")
        return 1
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("shape", help="record a position corpus of games and analyze the shapes of the winners")
    p.add_argument("--record", action="store_true", help="play the games and write the corpus")
    p.add_argument("--analyze", action="store_true", help="read the corpus and write the analysis and the report")
    p.add_argument("--pairs", default="v7:v7,v7:v6", help="the pairs to play, as first:second,first:second")
    p.add_argument("--pairs-from-evolve", default=None, help="an evolution artifact: each of its candidates plays each agent of --panel, in addition to --pairs")
    p.add_argument("--panel", default="v7,v6", help="the opponents of the candidates with --pairs-from-evolve")
    p.add_argument("--limit", type=int, default=0, help="with --pairs-from-evolve, the count of candidates, best first (0 is all)")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--games", type=int, default=40, help="games of each pair, half with the sides swapped")
    p.add_argument("--seed", type=int, default=1)
    from slcli.worker_limit import workers_argument

    p.add_argument("--workers", type=workers_argument, default=1)
    p.add_argument("--out", default="runs/shape", help="the corpus directory")
    p.add_argument("--cnn", action="store_true", help="add the picture model (needs torch)")
    p.add_argument("--progress", action="store_true")
    p.set_defaults(func=run)

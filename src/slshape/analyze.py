"""The analysis of a position corpus: which shapes go with a win, beyond the material.

Three questions, each with a number:

1. For each statistic, each side, and each turn: does the side that wins the game have a
   different value from the side that loses? The number is the AUC of the statistic
   between the winners and the losers (the chance that a winner's value is above a
   loser's), with the two means. An AUC of 0.5 is no difference.
2. Does the shape hold information the material does not? Three logistic models predict
   the winner from a position: one from the material counts, one from the shape
   statistics, one from both. Each is fitted and scored by cross validation with the
   games as the folds, so a game never scores itself. The gain of "both" over
   "material" is the information of the shape.
3. Does the picture hold information the statistics do not? A small convolutional net
   on the pictures, scored the same way, against the "both" model. Its occlusion map
   says which hexes move its answer, which is the shape it found. This part needs torch
   and runs on request.

The models are small on purpose. A corpus of a few thousand positions does not support
a large one, and the question is the gain between the models, not the score of one.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from slshape import features
from slshape.record import Corpus


def auc(positive: np.ndarray, negative: np.ndarray) -> float:
    """The Mann-Whitney AUC: the chance a positive value is above a negative one, with
    ties at one half."""
    if positive.size == 0 or negative.size == 0:
        return 0.5
    values = np.concatenate([positive, negative])
    order = values.argsort(kind="mergesort")
    ranks = np.empty(values.size, dtype=np.float64)
    sorted_values = values[order]
    i = 0
    while i < values.size:
        j = i
        while j + 1 < values.size and sorted_values[j + 1] == sorted_values[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    rank_sum = ranks[: positive.size].sum()
    n1, n2 = positive.size, negative.size
    return float((rank_sum - n1 * (n1 + 1) / 2.0) / (n1 * n2))


def side_table(corpus: Corpus, player: int, turn: int | None = None, phase: int | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The statistics of one player, the win label, and the game index of each position,
    in the turns and the phases asked for."""
    keep = np.ones(corpus.size, dtype=bool)
    if turn is not None:
        keep &= corpus.turn == turn
    if phase is not None:
        keep &= corpus.phase == phase
    x = corpus.feats[keep, player, :]
    y = (corpus.winner[keep] == player).astype(np.float64)
    return x, y, corpus.game[keep]


def feature_aucs(corpus: Corpus, player: int, turn: int | None = None, phase: int | None = None) -> list[dict[str, Any]]:
    """The AUC, the winner mean, and the loser mean of each statistic of one player."""
    x, y, _ = side_table(corpus, player, turn, phase)
    won = y > 0.5
    out = []
    for i, name in enumerate(corpus.feature_names):
        column = x[:, i].astype(np.float64)
        out.append(
            {
                "feature": name,
                "kind": "material" if name in features.MATERIAL else "shape",
                "auc": round(auc(column[won], column[~won]), 4),
                "winners": round(float(column[won].mean()), 3) if won.any() else None,
                "losers": round(float(column[~won].mean()), 3) if (~won).any() else None,
                "n_win": int(won.sum()),
                "n_lose": int((~won).sum()),
            }
        )
    return out


# ------------------------------------------------------------- the logistic models


def _fit_logistic(x: np.ndarray, y: np.ndarray, l2: float = 1.0, steps: int = 600, lr: float = 0.1) -> tuple[np.ndarray, float]:
    """A logistic regression by gradient descent with an L2 term, on standardized inputs."""
    n, d = x.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(steps):
        z = x @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        g = p - y
        w -= lr * (x.T @ g / n + l2 * w / n)
        b -= lr * g.mean()
    return w, b


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    eps = 1e-7
    p = np.clip(p, eps, 1 - eps)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def cross_validate(x: np.ndarray, y: np.ndarray, groups: np.ndarray, folds: int = 5, l2: float = 1.0) -> dict[str, Any]:
    """The held-out accuracy and log loss of a logistic model, with the games as folds.

    The folds cut the games and not the positions, so the positions of one game are
    all in or all out. The inputs are standardized on the fitting fold alone.
    """
    unique = np.unique(groups)
    if unique.size < folds:
        folds = max(2, int(unique.size))
    rng = np.random.default_rng(0)
    order = rng.permutation(unique)
    fold_of = {int(g): i % folds for i, g in enumerate(order)}
    fold_index = np.array([fold_of[int(g)] for g in groups])
    predictions = np.zeros(y.size)
    for f in range(folds):
        train = fold_index != f
        test = ~train
        if train.sum() == 0 or test.sum() == 0:
            continue
        mean = x[train].mean(axis=0)
        std = x[train].std(axis=0)
        std[std == 0] = 1.0
        xt = (x[train] - mean) / std
        w, b = _fit_logistic(xt, y[train], l2=l2)
        xs = (x[test] - mean) / std
        predictions[test] = 1.0 / (1.0 + np.exp(-(xs @ w + b)))
    accuracy = float(((predictions > 0.5) == (y > 0.5)).mean())
    base_rate = float(max(y.mean(), 1 - y.mean()))
    return {"accuracy": round(accuracy, 4), "log_loss": round(_log_loss(predictions, y), 4), "base_rate": round(base_rate, 4), "n": int(y.size), "folds": folds}


def _columns(names: Sequence[str], wanted: Sequence[str]) -> list[int]:
    return [i for i, name in enumerate(names) if name in wanted]


def model_comparison(corpus: Corpus, player: int, turn: int | None = None) -> dict[str, Any]:
    """The three logistic models of one player: material, shape, and both. With no turn
    the positions of every turn go in, and the turn and the phase are inputs."""
    x, y, groups = side_table(corpus, player, turn)
    if y.size == 0 or np.unique(y).size < 2:
        return {"material": None, "shape": None, "both": None, "n": int(y.size)}
    material = x[:, _columns(corpus.feature_names, features.MATERIAL)]
    shape = x[:, _columns(corpus.feature_names, features.SHAPE)]
    extra = []
    if turn is None:
        keep = np.ones(corpus.size, dtype=bool)
        extra = [corpus.turn[keep].astype(np.float64)[:, None], corpus.phase[keep].astype(np.float64)[:, None]]
    material = np.concatenate([material] + extra, axis=1) if extra else material
    shape = np.concatenate([shape] + extra, axis=1) if extra else shape
    both = np.concatenate([material, shape[:, : len(features.SHAPE)]], axis=1)
    return {
        "material": cross_validate(material, y, groups),
        "shape": cross_validate(shape, y, groups),
        "both": cross_validate(both, y, groups),
        "n": int(y.size),
    }


def partial_gains(corpus: Corpus, player: int, turn: int | None = None) -> list[dict[str, Any]]:
    """The gain of each shape statistic on top of the material: the fall of the held-out
    log loss when the statistic joins the material model. A statistic that is a proxy
    of the material gives no gain, whatever its AUC."""
    x, y, groups = side_table(corpus, player, turn)
    if y.size == 0 or np.unique(y).size < 2:
        return []
    material_columns = _columns(corpus.feature_names, features.MATERIAL)
    extra = []
    if turn is None:
        extra = [corpus.turn.astype(np.float64)[:, None], corpus.phase.astype(np.float64)[:, None]]
    material = x[:, material_columns]
    material = np.concatenate([material] + extra, axis=1) if extra else material
    base = cross_validate(material, y, groups)
    out = []
    for i, name in enumerate(corpus.feature_names):
        if name not in features.SHAPE:
            continue
        joined = np.concatenate([material, x[:, i : i + 1]], axis=1)
        m = cross_validate(joined, y, groups)
        out.append({"feature": name, "gain": round(base["log_loss"] - m["log_loss"], 4), "accuracy": m["accuracy"], "material_log_loss": base["log_loss"]})
    out.sort(key=lambda r: -r["gain"])
    return out


# ---------------------------------------------------------- the tactical label


def next_loss(corpus: Corpus, player: int) -> tuple[np.ndarray, np.ndarray]:
    """The tactical label of each position: the unbroken squads the player loses before
    its next recorded position of the game (broken or killed in the fire between), and
    a mask of the positions that have a next one. The game label is coarse: a shape
    that is good on the table shows in the next fire, not only at the end."""
    squads = corpus.feats[:, player, list(corpus.feature_names).index("squads")]
    loss = np.zeros(corpus.size, dtype=np.float64)
    has_next = np.zeros(corpus.size, dtype=bool)
    for i in range(corpus.size - 1):
        if corpus.game[i + 1] == corpus.game[i]:
            loss[i] = max(0.0, float(squads[i] - squads[i + 1]))
            has_next[i] = True
    return loss, has_next


def tactical_comparison(corpus: Corpus, player: int) -> dict[str, Any]:
    """The three models on the tactical label: does the side lose a squad before its
    next position? With the gain of each shape statistic on top of the material."""
    loss, has_next = next_loss(corpus, player)
    y = (loss > 0).astype(np.float64)[has_next]
    x = corpus.feats[has_next, player, :]
    groups = corpus.game[has_next]
    if y.size == 0 or np.unique(y).size < 2:
        return {"material": None, "shape": None, "both": None, "n": int(y.size), "gains": []}
    extra = [corpus.turn[has_next].astype(np.float64)[:, None], corpus.phase[has_next].astype(np.float64)[:, None]]
    material = np.concatenate([x[:, _columns(corpus.feature_names, features.MATERIAL)]] + extra, axis=1)
    shape = np.concatenate([x[:, _columns(corpus.feature_names, features.SHAPE)]] + extra, axis=1)
    both = np.concatenate([material, x[:, _columns(corpus.feature_names, features.SHAPE)]], axis=1)
    base = cross_validate(material, y, groups)
    gains = []
    for i, name in enumerate(corpus.feature_names):
        if name in features.SHAPE:
            m = cross_validate(np.concatenate([material, x[:, i : i + 1]], axis=1), y, groups)
            gains.append({"feature": name, "gain": round(base["log_loss"] - m["log_loss"], 4), "accuracy": m["accuracy"]})
    gains.sort(key=lambda r: -r["gain"])
    return {
        "material": base,
        "shape": cross_validate(shape, y, groups),
        "both": cross_validate(both, y, groups),
        "n": int(y.size),
        "rate": round(float(y.mean()), 4),
        "gains": gains,
    }


# -------------------------------------------------------------- the whole analysis


def analyze(corpus: Corpus, top: int = 8) -> dict[str, Any]:
    """The tables of questions 1 and 2 for each player, over all turns and by turn."""
    out: dict[str, Any] = {
        "positions": corpus.size,
        "games": len(corpus.games),
        "games_with_a_winner": int(len({int(g) for g in corpus.game})),
        "wins_by_player": {str(p): int(sum(1 for g in corpus.games if g["winner"] == p)) for p in (0, 1)},
        "turns": sorted(int(t) for t in np.unique(corpus.turn)),
        "players": {},
    }
    for player in (0, 1):
        entry: dict[str, Any] = {"all_turns": {}, "by_turn": {}}
        aucs = feature_aucs(corpus, player)
        entry["all_turns"]["aucs"] = aucs
        shape_aucs = sorted((a for a in aucs if a["kind"] == "shape"), key=lambda a: -abs(a["auc"] - 0.5))
        entry["all_turns"]["top_shape"] = shape_aucs[:top]
        entry["all_turns"]["models"] = model_comparison(corpus, player)
        entry["all_turns"]["partial_gains"] = partial_gains(corpus, player)
        entry["tactical"] = tactical_comparison(corpus, player)
        for turn in out["turns"]:
            aucs_t = feature_aucs(corpus, player, turn)
            shape_t = sorted((a for a in aucs_t if a["kind"] == "shape"), key=lambda a: -abs(a["auc"] - 0.5))
            entry["by_turn"][str(turn)] = {
                "top_shape": shape_t[:top],
                "material": [a for a in aucs_t if a["kind"] == "material"],
                "models": model_comparison(corpus, player, turn),
            }
        out["players"][str(player)] = entry
    return out


# ------------------------------------------------------------------ the picture net


def picture_model(corpus: Corpus, player: int, folds: int = 5, epochs: int = 12, device: str | None = None) -> dict[str, Any]:
    """Question 3: a small convolutional net on the pictures, cross validated by game,
    and its occlusion map: the mean change of its answer when one hex is emptied, over
    the positions the player won. Needs torch."""
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise RuntimeError("the picture model needs torch: pip install -e '.[train]'") from exc
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    x_all = torch.tensor(corpus.pictures, dtype=torch.float32)
    y_all = torch.tensor((corpus.winner == player).astype(np.float32))
    turn_plane = torch.tensor(corpus.turn, dtype=torch.float32)[:, None, None, None] / 5.0
    x_all = torch.cat([x_all, turn_plane.expand(-1, 1, x_all.shape[2], x_all.shape[3])], dim=1)
    groups = corpus.game
    unique = np.unique(groups)
    folds = max(2, min(folds, int(unique.size)))
    rng = np.random.default_rng(0)
    order = rng.permutation(unique)
    fold_of = {int(g): i % folds for i, g in enumerate(order)}
    fold_index = np.array([fold_of[int(g)] for g in groups])
    channels = x_all.shape[1]

    def make_net() -> nn.Module:
        return nn.Sequential(
            nn.Conv2d(channels, 16, 3, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 16, 3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
            nn.Flatten(),
            nn.Linear(16 * 16, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
        ).to(dev)

    predictions = np.zeros(y_all.shape[0])
    for f in range(folds):
        train = torch.tensor(fold_index != f)
        test = ~train
        if train.sum() == 0 or test.sum() == 0:
            continue
        net = make_net()
        optim = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
        xt, yt = x_all[train].to(dev), y_all[train].to(dev)
        n = xt.shape[0]
        for _ in range(epochs):
            perm = torch.randperm(n, device=dev)
            for start in range(0, n, 64):
                idx = perm[start : start + 64]
                logits = net(xt[idx]).squeeze(1)
                loss = nn.functional.binary_cross_entropy_with_logits(logits, yt[idx])
                optim.zero_grad()
                loss.backward()
                optim.step()
        net.eval()
        with torch.no_grad():
            p = torch.sigmoid(net(x_all[test].to(dev)).squeeze(1)).cpu().numpy()
        predictions[test.numpy()] = p
    y = y_all.numpy()
    accuracy = float(((predictions > 0.5) == (y > 0.5)).mean())
    result = {"accuracy": round(accuracy, 4), "log_loss": round(_log_loss(predictions, y), 4), "n": int(y.size), "folds": folds, "epochs": epochs}

    # The occlusion map from one net fitted on every position: the mean fall of the win
    # answer when the units of one hex go away, over the positions the player won.
    net = make_net()
    optim = torch.optim.Adam(net.parameters(), lr=1e-3, weight_decay=1e-4)
    xd, yd = x_all.to(dev), y_all.to(dev)
    n = xd.shape[0]
    for _ in range(epochs):
        perm = torch.randperm(n, device=dev)
        for start in range(0, n, 64):
            idx = perm[start : start + 64]
            loss = nn.functional.binary_cross_entropy_with_logits(net(xd[idx]).squeeze(1), yd[idx])
            optim.zero_grad()
            loss.backward()
            optim.step()
    net.eval()
    won = torch.tensor(y > 0.5)
    sample = xd[won.to(dev)][:256]
    unit_planes = [i for i, name in enumerate(corpus.plane_names) if name.startswith("side")]
    with torch.no_grad():
        base = torch.sigmoid(net(sample).squeeze(1))
        cols, rows = sample.shape[2], sample.shape[3]
        heat = np.zeros((cols, rows), dtype=np.float32)
        for c in range(cols):
            for r in range(rows):
                if not sample[:, unit_planes, c, r].any():
                    continue
                masked = sample.clone()
                masked[:, unit_planes, c, r] = 0.0
                p = torch.sigmoid(net(masked).squeeze(1))
                heat[c, r] = float((base - p).mean())
    result["occlusion"] = heat.round(4).tolist()
    result["occlusion_note"] = "the mean fall of the win answer when the units of the hex go away, over won positions; a positive value is a hex that holds the win"
    return result

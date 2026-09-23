"""The shape study: the picture, the statistics, the corpus, and the analysis.

The tests build positions from real games of the scripted agents, so a count in a plane
is the count on the board. The analysis tests use small synthetic tables where the
answer is known, and one real corpus of two short games.
"""

from __future__ import annotations

import numpy as np
import pytest

from slcli.play import build_engine, make_agent
from slcli.shape_cmd import pairs_of, report_text
from slshape import analyze, features, picture
from slshape.record import Corpus, record_corpus

SCENARIO = "s01_guards_counterattack"


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


def after_setup(engine, seed: int = 3):
    """The state at the first Prep Fire Phase: the two sides set up and nothing moved."""
    state = engine.new_game(seed)
    scripted = {p: make_agent("v1", engine, seed, p) for p in (0, 1)}
    while state.phase in ("setup", "rally"):
        frame = engine.legal_commands(state)
        chosen = frame.by_id(scripted[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    return state


def test_the_picture_counts_each_unit_in_its_hex(engine):
    state = after_setup(engine)
    objectives = picture.objective_buildings(engine)
    fixed = picture.terrain_planes(engine.board, objectives)
    pic = picture.picture(engine.board, state, engine.types, fixed, objectives)
    assert pic.shape == picture.shape_of(engine.board)
    for player in (0, 1):
        squads = sum(1 for u in state.player_units(player) if u.hex is not None and u.kind in ("squad", "crew") and not u.broken)
        leaders = sum(1 for u in state.player_units(player) if u.hex is not None and u.kind == "leader" and not u.broken)
        assert int(picture.plane(pic, f"side{player}_squads").sum()) == squads
        assert int(picture.plane(pic, f"side{player}_leaders").sum()) == leaders
        assert int(picture.plane(pic, f"side{player}_broken").sum()) == 0
    objective_hexes = {h for hexes in objectives.values() for h in hexes}
    assert int(picture.plane(pic, "objective").sum()) == len(objective_hexes)
    # The terrain planes are one-hot over the kinds the study names.
    terrain = pic[: len(picture.TERRAIN_KINDS)].sum(axis=0)
    assert terrain.max() <= 1


def test_the_statistics_read_the_set_up_position(engine):
    """At set up each side stands in its own buildings, in cover, out of contact, and the
    counts are the counts of the board."""
    state = after_setup(engine)
    objectives = picture.objective_buildings(engine)
    buildings_of = features.side_buildings(engine, objectives)
    assert buildings_of[0] and buildings_of[1]
    for player in (0, 1):
        f = features.features_of(engine, state, objectives, buildings_of, player)
        value = dict(zip(features.FEATURE_NAMES, f.tolist()))
        squads = sum(1 for u in state.player_units(player) if u.hex is not None and u.kind in ("squad", "crew"))
        assert value["squads"] == squads
        assert value["in_own_buildings"] == 1.0
        assert value["cover_share"] == 1.0 and value["open_share"] == 0.0
        assert value["contact"] == 0.0
        assert value["clusters"] >= 1 and value["hexes"] >= 1
        assert value["to_enemy_buildings"] > 0
        assert 0.0 <= value["leader_at_hand"] <= 1.0
        assert 0.0 <= value["flank_balance"] <= 0.5
        assert value["seen_by"] >= 0.0 and value["sees"] >= 0.0


def test_the_auc_is_the_chance_a_winner_is_above_a_loser():
    assert analyze.auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert analyze.auc(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0
    assert analyze.auc(np.array([1.0, 1.0]), np.array([1.0, 1.0])) == 0.5
    assert analyze.auc(np.array([1.0, 3.0]), np.array([2.0, 2.0])) == 0.5
    assert analyze.auc(np.array([]), np.array([1.0])) == 0.5


def test_the_cross_validation_separates_what_is_separable():
    rng = np.random.default_rng(1)
    n = 400
    x = rng.normal(size=(n, 3))
    y = (x[:, 0] + 0.5 * x[:, 1] > 0).astype(np.float64)
    groups = np.arange(n) // 4
    good = analyze.cross_validate(x, y, groups)
    assert good["accuracy"] > 0.9
    noise = rng.normal(size=(n, 3))
    poor = analyze.cross_validate(noise, y, groups)
    assert poor["accuracy"] < 0.65


def test_the_pairs_split_on_the_commas_outside_the_brackets():
    assert pairs_of("v7:v7,v7[a=1,b=2]:v6") == [("v7", "v7"), ("v7[a=1,b=2]", "v6")]
    with pytest.raises(ValueError):
        pairs_of("v7")


def test_a_corpus_of_two_games_writes_reads_and_analyzes(tmp_path):
    """Two short games give positions with a winner label, the corpus survives the disk,
    and the analysis and the report run on it."""
    corpus = record_corpus(SCENARIO, [("v1", "v1")], games=2, first_seed=7, workers=1)
    assert len(corpus.games) == 2
    winners = [g["winner"] for g in corpus.games]
    assert corpus.size == sum(1 for w in corpus.winner)
    assert corpus.pictures.shape[0] == corpus.feats.shape[0] == corpus.turn.shape[0]
    assert set(corpus.winner.tolist()) <= {w for w in winners if w >= 0}
    assert set(corpus.phase.tolist()) <= {0, 1}
    directory = corpus.write(tmp_path / "shape")
    again = Corpus.read(directory)
    assert again.size == corpus.size and again.feature_names == features.FEATURE_NAMES
    assert np.array_equal(again.pictures, corpus.pictures)
    result = analyze.analyze(again)
    assert result["positions"] == corpus.size
    assert set(result["players"]) == {"0", "1"}
    text = report_text(result, again)
    assert "Shape analysis" in text and "player 0" in text


def test_the_pairs_of_an_evolution_artifact_are_its_candidates_against_the_panel(tmp_path):
    import json

    from slcli.shape_cmd import pairs_from_evolve

    stats = {
        "candidates": [
            {"id": 0, "text": "v7", "mean": 0.6},
            {"id": 1, "text": "v7[loss_scale=9]", "mean": 0.7},
            {"id": 2, "text": "v7[loss_scale=9]", "mean": 0.5},
            {"id": 3, "text": "v7[aggression=4]", "mean": 0.4},
        ]
    }
    (tmp_path / "stats.json").write_text(json.dumps(stats), encoding="utf-8")
    pairs = pairs_from_evolve(tmp_path, ["v6"], limit=2)
    assert pairs == [("v7[loss_scale=9]", "v6"), ("v7", "v6")]
    assert len(pairs_from_evolve(tmp_path, ["v6", "v1"])) == 6

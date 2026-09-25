"""The parameter evolution of v7 (FR-44, FR-50).

The search is tested with a fitness that is a function of the genome and no game, so
the test says what the loop does: the genome is a command line, a child differs from its
parent and stays in the space, the elites play again, the best is the elite with the
best mean, and the run is deterministic for its seed. The command is tested on the
movement drill with real games, two candidates and two generations.
"""

from __future__ import annotations

import random

import pytest

from slagents.scripted import evolve as search
from slagents.scripted.v7 import Parameters, parameters_from_text
from slcli.evolve import base_of, generation_jobs, run_evolve, side_index
from slcli.play import build_engine, make_agent


def test_a_genome_is_a_command_line_and_back():
    """The text of a genome names the values that differ from the base, `make_agent`
    builds it, and the record it builds is the genome."""
    genome = search.genome_of(Parameters())
    assert search.text_of(genome) == "v7"
    genome["loss_scale"] = 9
    genome["rout_block"] = False
    text = search.text_of(genome)
    assert text == "v7[loss_scale=9,rout_block=0]"
    params = parameters_from_text(text[3:-1])
    assert params.loss_scale == 9 and params.rout_block is False
    assert search.genome_of(params) == genome
    engine = build_engine("s00_movement_drill")
    agent = make_agent(text, engine, 1, 0)
    assert agent.v7.loss_scale == 9


def test_a_child_differs_from_its_parent_and_stays_in_the_space():
    rng = random.Random(7)
    parent = search.genome_of(Parameters())
    for _ in range(200):
        child = search.mutate(parent, rng)
        assert child != parent
        for name, (low, high) in search.SPACE.items():
            assert low <= child[name] <= high
        for name in search.FLAGS:
            assert isinstance(child[name], bool)


def test_a_crossover_takes_each_parameter_from_one_parent():
    rng = random.Random(3)
    a = search.genome_of(Parameters())
    b = {name: (search.SPACE[name][1] if name in search.SPACE else not a[name]) for name in a}
    child = search.crossover(a, b, rng)
    assert all(child[name] in (a[name], b[name]) for name in a)
    assert child != a and child != b


def synthetic_fitness(target: int):
    """A score that is highest when loss_scale is at the target: the search has to find it."""

    def fitness(candidates, index):
        out = []
        for cand in candidates:
            distance = abs(cand.genome["loss_scale"] - target)
            out.append((1.0 / (1.0 + distance), {"distance": distance}))
        return out

    return fitness


def test_the_best_is_the_candidate_with_the_best_lower_bound():
    """A candidate with one lucky generation is not the best of a run. The bound falls
    with the count of games, so five generations at 32 percent win against two at 32,
    and a candidate of the last generation alone is not the best."""
    lucky = search.Candidate(1, {}, scores={0: 0.50, 1: 0.15})
    steady = search.Candidate(2, {}, scores={g: 0.32 for g in range(5)})
    assert steady.mean < lucky.mean + 1e-9
    assert steady.lower_bound(40) > lucky.lower_bound(40)
    assert steady.lower_bound(0) == steady.mean
    run = search.Evolution(base=Parameters(), candidates=[lucky, steady], games=40)
    run.generations = [search.Generation(index=0, elites=[1, 2], scored=[(1, 0.5), (2, 0.32)])]
    assert run.best() is steady
    fresh = search.Candidate(3, {}, scores={0: 0.9})
    run.candidates.append(fresh)
    run.generations[-1] = search.Generation(index=0, elites=[3, 1, 2], scored=[(3, 0.9), (1, 0.5), (2, 0.32)])
    assert run.best() is steady


def test_the_search_climbs_to_the_target_and_keeps_the_elites():
    """Twelve generations of eight find a loss_scale near 30 from 16, and each elite of
    a generation plays again in the next one, so its score list grows."""
    run = search.run_evolution(synthetic_fitness(30), generations=12, population=8, parents=3, seed=5)
    best = run.best()
    assert abs(best.genome["loss_scale"] - 30) <= 2
    assert best.evaluations >= 2
    for earlier, later in zip(run.generations, run.generations[1:]):
        for cid in earlier.elites:
            assert later.index in run.candidate(cid).scores
    assert run.candidates[0].genome == search.genome_of(Parameters())
    assert run.candidates[0].scores[0] == pytest.approx(1.0 / 15.0)


def test_the_search_is_deterministic_for_its_seed():
    a = search.run_evolution(synthetic_fitness(20), generations=4, population=6, parents=2, seed=11)
    b = search.run_evolution(synthetic_fitness(20), generations=4, population=6, parents=2, seed=11)
    c = search.run_evolution(synthetic_fitness(20), generations=4, population=6, parents=2, seed=12)
    assert a.to_dict() == b.to_dict()
    assert a.to_dict() != c.to_dict()


def test_a_setting_that_cannot_run_is_an_error():
    with pytest.raises(search.EvolveError):
        search.run_evolution(synthetic_fitness(1), generations=0)
    with pytest.raises(search.EvolveError):
        search.run_evolution(synthetic_fitness(1), generations=1, population=1)
    with pytest.raises(search.EvolveError):
        base_of("v6")


def test_the_generation_plays_each_candidate_on_the_same_seeds_as_each_side():
    base = Parameters()
    candidates = [search.Candidate(0, search.genome_of(base)), search.Candidate(1, {**search.genome_of(base), "aggression": 4})]
    jobs, keys = generation_jobs(candidates, base, ["v6", "v1"], "s00_movement_drill", 4, 500)
    assert len(jobs) == 2 * 2 * 4
    seeds_of = {ci: sorted(seed for c, seed, _, _ in keys if c == ci) for ci in (0, 1)}
    # The two games of a side pair share one seed (L7), for each of the two opponents.
    assert seeds_of[0] == seeds_of[1] == [500, 500, 500, 500, 501, 501, 501, 501]
    pairs = {}
    for c, seed, opponent, first in keys:
        if c == 1:
            pairs.setdefault((seed, opponent), []).append(first)
    assert all(sorted(sides) == [False, True] for sides in pairs.values()), "each seed plays the candidate on each side"
    firsts = [first for c, _, _, first in keys if c == 1]
    assert firsts.count(True) == firsts.count(False) == 4
    texts = {job[2] for job in jobs} | {job[3] for job in jobs}
    assert "v7" in texts and "v7[aggression=4]" in texts and "v6" in texts and "v1" in texts


def test_the_command_writes_an_artifact_with_the_best_text(tmp_path):
    """Two generations of two on the movement drill against v0: the artifact has each
    candidate with its text, its wins by side, and the best is one of the elites."""
    art = run_evolve("v7", ["v0"], "s00_movement_drill", games=2, generations=2, population=2, parents=1, seed=3, workers=1)
    directory = art.write(tmp_path)
    assert (directory / "stats.json").exists()
    s = art.stats
    assert s["games"] == 2 * 2 + 3 * 2
    assert len(s["generations"]) == 2
    best = s["best"]
    assert best["evaluations"] >= 2 and best["games"] == best["evaluations"] * 2
    assert best["text"] == "v7" or best["text"].startswith("v7[")
    for detail in best["details"].values():
        assert detail["games"] == 2 and set(detail["by_side"]) == {"russian", "german"}


def test_the_side_option_holds_the_candidate_to_one_side():
    """With a side the candidate takes that player in each game, so the score is the
    attack alone or the defence alone. The first run mixed the two, and the easy German
    wins hid the Russian attack."""
    base = Parameters()
    candidates = [search.Candidate(0, search.genome_of(base))]
    sides = ("russian", "german")
    assert side_index(sides, "both") is None
    assert side_index(sides, "russian") == 0 and side_index(sides, "german") == 1
    assert side_index(sides, "first") == 0 and side_index(sides, "second") == 1
    with pytest.raises(search.EvolveError):
        side_index(sides, "british")
    jobs, keys = generation_jobs(candidates, base, ["v6"], "s00_movement_drill", 4, 500, player=0)
    assert all(first for _, _, _, first in keys)
    assert all(job[2] == "v7" and job[3] == "v6" for job in jobs)
    jobs, keys = generation_jobs(candidates, base, ["v6"], "s00_movement_drill", 4, 500, player=1)
    assert not any(first for _, _, _, first in keys)
    assert all(job[2] == "v6" and job[3] == "v7" for job in jobs)


def test_the_command_records_the_side_of_the_run(tmp_path):
    art = run_evolve("v7", ["v0"], "s00_movement_drill", games=2, generations=1, population=2, parents=1, seed=3, workers=1, side="russian")
    assert art.config["side"] == "russian" and art.config["player"] == 0
    for cand in art.stats["candidates"]:
        for detail in cand["details"].values():
            assert detail["by_side"]["german"] == 0


def test_the_final_stage_plays_the_best_and_the_base_on_new_seeds(tmp_path):
    """The elite of a search is in part the noise of the seeds it played, so the command
    plays the best candidates and the base again at the end, on seeds no generation
    used. The table holds the base, and each row has its search score and its final
    score."""
    art = run_evolve(
        "v7", ["v0"], "s00_movement_drill", games=2, generations=2, population=2, parents=1,
        seed=3, workers=1, final_games=2, final_top=2,
    )
    rows = art.stats["final"]
    assert rows and any(row["is_base"] for row in rows)
    assert all(row["games"] == 2 for row in rows)
    assert all(row["final"] >= rows[i + 1]["final"] for i, row in enumerate(rows[:-1]))
    from slruns.seeds import family_seed

    seeds = set(art.seeds)
    seed = art.config["seed"]
    final_seeds = {family_seed("evolve_final", seed)}
    confirm_seeds = {family_seed("evolve_confirm", seed)}
    generation_seeds = {family_seed("evolve", seed, 1000 * (i + 1)) for i in range(2)}
    assert final_seeds <= seeds and confirm_seeds <= seeds and generation_seeds <= seeds
    assert not (final_seeds & generation_seeds) and not (confirm_seeds & (final_seeds | generation_seeds))
    assert seeds == final_seeds | confirm_seeds | generation_seeds, "two games of a side pair share one seed"
    assert min(seeds) >= family_seed("evolve", 0), "the evolve seeds are not the seeds of a training run or a gauntlet"
    # L7: the pick of the final stage plays again on new seeds, after the pick.
    confirm = art.stats["confirm"]
    assert confirm and confirm[0]["id"] == rows[0]["id"]
    assert confirm[-1]["is_base"] and all(row["games"] == 2 for row in confirm)
    assert len(confirm) == (1 if rows[0]["is_base"] else 2)
    assert art.stats["games"] == 2 * 2 + 3 * 2 + sum(row["games"] for row in rows) + sum(row["games"] for row in confirm)


def test_a_search_moves_the_parameters_of_the_only_list_and_no_other():
    """A rule with three parameters is a search of three. Each child differs from the
    base in the named parameters alone, and a name that is not a parameter is an error
    before the first game."""
    rng = random.Random(5)
    base = search.genome_of(Parameters())
    only = ["smoke_floor", "smoke_horizon", "rout_block"]
    for _ in range(50):
        child = search.mutate(base, rng, only=only)
        moved = {name for name in child if child[name] != base[name]}
        assert moved and moved <= set(only)
    other = {**base, "loss_scale": 40, "smoke_floor": 400}
    crossed = search.crossover(base, other, rng, only=only)
    assert crossed["loss_scale"] == base["loss_scale"]
    assert crossed["smoke_floor"] in (base["smoke_floor"], 400)
    with pytest.raises(search.EvolveError):
        search.moved_names(["no_such_parameter"])
    with pytest.raises(search.EvolveError):
        search.run_evolution(synthetic_fitness(1), generations=1, only=["no_such_parameter"])


def test_the_command_records_the_only_list(tmp_path):
    art = run_evolve(
        "v7", ["v0"], "s00_movement_drill", games=2, generations=2, population=2, parents=1,
        seed=3, workers=1, final_games=0, only=["smoke_floor"],
    )
    assert art.config["only"] == ["smoke_floor"]
    base = art.stats["candidates"][0]["genome"]
    for cand in art.stats["candidates"][1:]:
        moved = {name for name, value in cand["genome"].items() if value != base[name]}
        assert moved <= {"smoke_floor"}


def test_a_run_on_a_nation_record_names_that_nation_in_its_candidates():
    """A study of one rule on a profile has to name the profile, or the name plays the
    defaults with a few values on top. `v7:german[smoke_horizon=1]` is that name, and
    `make_agent` builds it."""
    from slagents.scripted.v7 import parameters_of_name, profile_for
    from slcli.evolve import name_of

    german = profile_for("german")
    genome = search.genome_of(german)
    assert name_of("v7:german", genome, german) == "v7:german"
    moved = {**genome, "smoke_horizon": 1}
    name = name_of("v7:german", moved, german)
    assert name == "v7:german[smoke_horizon=1]"
    built = parameters_of_name(name)
    assert built.smoke_horizon == 1
    assert built.fire_floor == german.fire_floor and built.loss_scale == german.loss_scale
    # `make_agent` reads the role of the side (`side_defends`), so the record it builds
    # is the record of that role with the values of the name on top.
    from slagents.scripted.v7 import side_defends

    engine = build_engine("s00_movement_drill")
    agent = make_agent(name, engine, 1, 0)
    wanted = parameters_of_name(name, side_defends(engine, 0))
    assert agent.v7 == wanted and agent.v7.smoke_horizon == 1
    # A run with no nation keeps the plain name.
    assert name_of("v7", moved, german).startswith("v7[")

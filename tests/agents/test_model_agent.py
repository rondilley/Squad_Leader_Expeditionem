"""The model agent harness (FR-45 to FR-49, FR-59, SR-04, SR-09, TC-16, TC-17).

The tests that need a network carry the `integration` mark. The rest use a provider stub
that gives a fixed answer, which is a test of the harness and not of a provider: TR-05
forbids a substitute for a provider in a provider test, and these are harness tests.
"""

from __future__ import annotations

import json

import pytest

from slagents.prompted import keys, schema
from slagents.prompted.harness import ASYNCHRONOUS_SECONDS, PromptedAgent, position_key, text_state
from slagents.prompted.oddsview import CONCEALED_TARGET, NO_ENEMY_FIRE, OddsView, percent
from slagents.scripted import odds
from slagents.prompted.providers import Answer, ProviderUnavailable, load_config, make_provider
from slagents.prompted.providers.base import Provider, ProviderConfig
from slcli.play import build_engine, make_agent

SCENARIO = "s01_guards_counterattack"


class ScriptedProvider(Provider):
    """A provider stub that gives the answers a test names, in sequence."""

    def __init__(self, answers, config, allowlist):
        super().__init__(config, allowlist)
        self.answers = list(answers)
        self.prompts: list[str] = []
        self.systems: list[str] = []

    def health(self) -> bool:
        return True

    def complete(self, system, user, max_tokens=700, temperature=0.2, json_schema=None) -> Answer:
        self.systems.append(system)
        self.prompts.append(user)
        if not self.answers:
            raise ProviderUnavailable("the stub has no answer left")
        nxt = self.answers.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return Answer(text=nxt, seconds=0.01, provider=self.name, model=self.model)


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


def a_decision(engine, seed: int = 3):
    """A state in the Prep Fire Phase, where a decision has more than one command."""
    state = engine.new_game(seed)
    scripted = {p: make_agent("v1", engine, seed, p) for p in (0, 1)}
    while state.phase in ("setup", "rally"):
        frame = engine.legal_commands(state)
        chosen = frame.by_id(scripted[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    return state, engine.legal_commands(state)


def a_phase(engine, phase: str, seed: int = 3, agent: str = "v1"):
    """The first decision of a phase with more than one command, in a game of one agent."""
    state = engine.new_game(seed)
    scripted = {p: make_agent(agent, engine, seed, p) for p in (0, 1)}
    steps = 0
    while not state.game_over and steps < 5000:
        frame = engine.legal_commands(state)
        if state.phase == phase and len(frame.commands) > 1:
            return state, frame
        chosen = frame.by_id(scripted[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
        steps += 1
    raise AssertionError(f"no decision in the {phase} phase")


def stub(config, answers) -> ScriptedProvider:
    row = ProviderConfig(name="stub", kind="openai_compatible", endpoint=config.allowlist[1] + "/v1", model="stub-1")
    return ScriptedProvider(answers, row, config.allowlist)


def test_the_prompt_holds_the_state_and_the_legal_list(engine):
    """FR-45: the text state and the legal command list with their identities."""
    state, frame = a_decision(engine)
    text = text_state(engine, state, frame, frame.player, [])
    assert "Your units (" in text
    assert "Legal commands" in text
    for legal in frame.commands[:3]:
        assert legal.id in text
    assert schema.COMMAND_FIELD in text


def test_the_prompt_holds_no_unit_that_the_player_cannot_see(engine):
    """SR-09 with rule 25.2: the prompt is the acting player's view and nothing else."""
    from slcore.rules import r25_concealment
    from slcore import view as view_module

    state, frame = a_decision(engine)
    enemy = next(u for u in state.player_units(1 - frame.player) if u.hex is not None)
    state, _ = r25_concealment.add(state, enemy.player, enemy.hex)
    frame = engine.legal_commands(state)
    text = text_state(engine, state, frame, frame.player, [])
    hidden = view_module.hidden_unit_ids(state, frame.player)
    assert enemy.id in hidden
    assert f"  {enemy.id}: " not in text
    assert "Concealment counters" in text


def test_the_agent_gives_a_command_of_the_frame(engine, config):
    state, frame = a_decision(engine)
    wanted = frame.commands[1].id
    provider = stub(config, [f'I will hold the building.\n```json\n{{"command_id": "{wanted}", "plan": "hold"}}\n```'])
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    assert agent.select(state, frame) == wanted
    report = agent.report()
    assert report["decisions"] == 1 and report["fallbacks"] == 0
    assert report["invalid_commands"] == 0


def test_an_answer_outside_the_list_is_refused_and_asked_again(engine, config):
    """FR-47: the harness sends the rejection message back and asks again."""
    state, frame = a_decision(engine)
    wanted = frame.commands[0].id
    provider = stub(
        config,
        ['{"command_id": "0000000000000000"}', f'{{"command_id": "{wanted}"}}'],
    )
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    assert agent.select(state, frame) == wanted
    report = agent.report()
    assert report["invalid_commands"] == 1
    assert report["retries"] == 1
    assert report["fallbacks"] == 0
    assert "was refused" in provider.prompts[1], "the second prompt says what was wrong"


def test_the_scripted_default_takes_over_after_the_last_failure(engine, config):
    """FR-47: after the retries, the scripted agent decides and the run records a fallback."""
    state, frame = a_decision(engine)
    provider = stub(config, ["not json at all", "still not json", "and not this time"])
    default = make_agent("v1", engine, 3, frame.player)
    agent = PromptedAgent(engine, frame.player, provider, default, retries=2)
    chosen = agent.select(state, frame)
    assert chosen == default.select(state, frame)
    report = agent.report()
    assert report["fallbacks"] == 1
    assert report["invalid_commands"] == 3
    assert report["retries"] == 2
    assert report["fallback_rate"] == 1.0


def test_a_provider_that_does_not_answer_is_a_timeout_and_a_fallback(engine, config):
    """FR-59 and TC-16: a timeout is counted, and the scripted default keeps the game going."""
    state, frame = a_decision(engine)
    provider = stub(config, [ProviderUnavailable("stub did not answer inside its timeout")])
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    assert frame.by_id(agent.select(state, frame)) is not None
    report = agent.report()
    assert report["timeouts"] == 1
    assert report["fallbacks"] == 1


def test_the_report_holds_the_four_rates_and_the_decision_time(engine, config):
    """TC-16 and OR-02: the invalid rate, the retry rate, the fallback rate, the timeout rate."""
    state, frame = a_decision(engine)
    wanted = frame.commands[0].id
    provider = stub(config, [f'{{"command_id": "{wanted}"}}'])
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    agent.select(state, frame)
    report = agent.report()
    for field in ("invalid_rate", "retry_rate", "fallback_rate", "timeout_rate", "median_seconds", "asynchronous"):
        assert field in report, field
    assert report["asynchronous"] is (report["median_seconds"] > ASYNCHRONOUS_SECONDS)
    assert report["provider"] == "stub"


def test_the_plan_of_one_decision_reaches_the_next_prompt(engine, config):
    """FR-49: the harness keeps the last plans of the agent in the prompt."""
    state, frame = a_decision(engine)
    first = frame.commands[0].id
    provider = stub(
        config,
        [
            f'{{"command_id": "{first}", "plan": "take the north building"}}',
            f'{{"command_id": "{first}", "plan": "hold"}}',
        ],
    )
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    agent.select(state, frame)
    agent.select(state, frame)
    assert "take the north building" in provider.prompts[1]


def test_the_harness_sends_text_and_never_an_image(engine, config):
    """FR-48 and TC-17: the prompt is text, and the code has no image path."""
    state, frame = a_decision(engine)
    wanted = frame.commands[0].id
    provider = stub(config, [f'{{"command_id": "{wanted}"}}'])
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    agent.select(state, frame)
    assert all(isinstance(p, str) for p in provider.prompts)
    from pathlib import Path

    source = Path("src/slagents/prompted")
    text = "\n".join(p.read_text(encoding="utf-8") for p in source.rglob("*.py"))
    for word in ("image_url", "base64", "png", "jpeg", "data:image"):
        assert word not in text, f"the harness has the word {word}"


def test_the_harness_never_runs_the_model_output(engine, config):
    """SR-04 and TC-17: the answer is data. The command comes from the frame."""
    state, frame = a_decision(engine)
    wanted = frame.commands[0].id
    plan = "__import__('os').system('echo no')"
    dangerous = json.dumps({"command_id": wanted, "plan": plan})
    provider = stub(config, [dangerous])
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    chosen = agent.select(state, frame)
    assert chosen == wanted
    from pathlib import Path

    source = Path("src/slagents/prompted")
    text = "\n".join(p.read_text(encoding="utf-8") for p in source.rglob("*.py"))
    for word in ("eval(", "exec(", "subprocess", "os.system", "pickle.loads"):
        assert word not in text, f"the harness has {word}"


def test_a_decision_with_one_legal_command_asks_no_model(engine, config):
    """A decision with one command is not a decision, and a call for it is a waste."""
    state = engine.new_game(3)
    frame = engine.legal_commands(state)
    while len(frame.commands) != 1:
        chosen = frame.commands[0]
        state, _ = engine.apply(state, chosen.command, frame)
        frame = engine.legal_commands(state)
        if state.game_over:
            pytest.skip("this seed has no decision with one command")
    provider = stub(config, [])
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    assert agent.select(state, frame) == frame.commands[0].id
    assert provider.prompts == [], "the harness made no call"


@pytest.mark.integration
def test_a_real_model_plays_one_decision_and_the_rates_are_recorded(config):
    """TC-16 and TC-20 in the harness: a real call, with the rates recorded."""
    name = "openai"
    if not keys.available(name):
        pytest.skip(f"no key for {name} on this machine")
    engine = build_engine(SCENARIO)
    state, frame = a_decision(engine)
    agent = PromptedAgent(engine, frame.player, make_provider(name, config), make_agent("v1", engine, 3, frame.player))
    chosen = agent.select(state, frame)
    assert frame.by_id(chosen) is not None
    report = agent.report()
    assert report["decisions"] == 1
    assert report["calls"] >= 1
    assert report["fallback_rate"] <= 0.2, f"TC-16 asks for a fallback rate below 20 percent: {agent.log}"


def test_a_tournament_records_the_rates_of_each_model_agent(config, tmp_path):
    """TC-16 and OR-02: the run artifact of a tournament holds the four rates and the
    decision time of each model agent of each game, not only the win rate."""
    from slcli.tournament import run_tournament

    def factory(kind, engine, seed, player):
        if kind == "model:test":
            # A provider with no answer left: each decision is a timeout and a fallback,
            # so the rates the artifact has to hold are not all zero.
            return PromptedAgent(engine, player, stub(config, []), make_agent("v1", engine, seed, player), retries=0)
        return make_agent(kind, engine, seed, player)

    art = run_tournament("s00_movement_drill", None, "v1", "model:test", games=2, seed=3, factory=factory)
    rows = art.stats["harness"]
    assert len(rows) == 2, "one row for the model agent of each game"
    assert {row["side"] for row in rows} == {"russian", "german"} or len({row["side"] for row in rows}) == 2
    for row in rows:
        assert row["agent"] == "model:test"
        for field in ("invalid_rate", "retry_rate", "fallback_rate", "timeout_rate", "median_seconds", "asynchronous"):
            assert field in row, field
        # A decision with one legal command asks no model, so the rates are below one,
        # and each decision that asked got a timeout and then the fallback.
        assert row["fallbacks"] == row["timeouts"] > 0
        assert 0 < row["fallback_rate"] <= 1.0
    assert "harness" not in run_tournament("s00_movement_drill", None, "v1", "v0", games=1, seed=3).stats



def test_the_prompt_carries_the_odds_of_a_shot_from_the_core(engine):
    """FR-45: a fire command in the prompt carries the odds that `odds.shot` gives from
    the tables of the core, so the model reads the number the doctrine agent reads."""
    from slcore.game import FireGroup

    state, frame = a_decision(engine)
    view = OddsView(engine, state, frame.player)
    adds = [lc for lc in frame.commands if lc.command.action == "group_add" and view.target_visible(lc.command.hex)]
    assert adds, "the prep fire decision offers a shot at a visible target"
    text = text_state(engine, state, frame, frame.player, [])
    checked = 0
    for lc in adds[:5]:
        shot = odds.shot(engine, state, FireGroup(lc.command.hex, ((lc.command.units[0], None),), None), state.phase)
        if shot.halves <= 0 or not shot.breaks:
            continue
        line = next(line for line in text.splitlines() if line.strip().startswith(lc.id))
        assert f"result {percent(shot.effect)}%" in line
        top = max(shot.breaks.items(), key=lambda item: (item[1], -item[0]))
        assert f"unit {top[0]} {percent(top[1])}%" in line
        checked += 1
    assert checked > 0


def test_a_concealed_target_and_a_concealed_shooter_give_no_odds(engine):
    """SR-09 with rule 25.2: the odds name the units of a hex, so a hex below a concealment
    counter has none, and the loss of a hex counts the enemy units the player sees. With
    every enemy hex concealed the prompt says that no visible enemy fires, in place of a
    number that would come from units the player cannot see."""
    from slcore.rules import r25_concealment

    state, frame = a_decision(engine)
    enemy_hexes = sorted({u.hex for u in state.player_units(1 - frame.player) if u.hex is not None})
    for hex_ref in enemy_hexes:
        state, _ = r25_concealment.add(state, 1 - frame.player, hex_ref)
    frame = engine.legal_commands(state)
    text = text_state(engine, state, frame, frame.player, [])
    assert "break chance here" not in text and "break chance " not in text.split("Legal commands")[1]
    assert NO_ENEMY_FIRE in text
    for lc in frame.commands:
        if lc.command.action in ("group_add", "group_add_weapon"):
            line = next(line for line in text.splitlines() if line.strip().startswith(lc.id))
            assert CONCEALED_TARGET in line
    for unit in state.player_units(1 - frame.player):
        assert f"unit {unit.id} " not in text


def test_the_prompt_carries_the_break_chance_of_a_move(engine):
    """FR-45: a move in the Movement Phase carries the chance that the mover breaks under
    the worst visible enemy group at any hex of its track, as `odds.loss` gives it."""
    state, frame = a_phase(engine, "movement")
    view = OddsView(engine, state, frame.player)
    text = text_state(engine, state, frame, frame.player, [])
    moves = [lc for lc in frame.commands if lc.command.action == "move"]
    assert moves
    seen_number = False
    for lc in moves[:12]:
        line = next(line for line in text.splitlines() if line.strip().startswith(lc.id))
        unit = state.units[lc.command.units[0]]
        groups = odds.enemy_groups(engine, state, lc.command.hex, view.enemies)
        if not groups:
            assert NO_ENEMY_FIRE in line
            continue
        chance = odds.loss(engine, state, unit, lc.command.hex, True, groups)
        for h in unit.track:
            track_groups = odds.enemy_groups(engine, state, h, view.enemies)
            if track_groups:
                chance = max(chance, odds.loss(engine, state, unit, h, True, track_groups))
        assert f"break chance {percent(chance)}%" in line
        seen_number = True
    assert seen_number


def test_the_prompt_names_the_victory_conditions_and_their_buildings(engine):
    """FR-45: the card is public, so the prompt of each side holds the conditions and the
    buildings they name, and not the standing that counts hidden units (AR-09)."""
    state, frame = a_decision(engine)
    for viewer in (0, 1):
        text = text_state(engine, state, frame, viewer, [])
        assert "Victory conditions" in text
        for condition in engine.scenario.victory:
            note = dict(condition.params).get("note")
            if note:
                assert note in text
        assert "buildings of the russian side: " in text
        assert "buildings of the other side: " in text
        assert "took [" not in text


def test_the_rally_odds_read_the_desperation_and_the_self_casualty_roll(engine):
    """Rules 14.2, 14.6, and 18.3: the chance of a rally is the rolls of 36 at or below
    the morale, less four under desperation morale, and the roll of twelve never rallies."""
    from slcore.rules import r15_leadership, r26_fanaticism
    from slcore.rules.r12_morale import morale_value

    state, frame = a_decision(engine)
    squad = next(u for u in state.player_units(frame.player) if u.kind == "squad" and u.hex is not None)
    for dm in (False, True):
        broken = squad.with_(broken=True, dm=dm)
        trial = state.with_unit(broken)
        view = OddsView(engine, trial, frame.player)
        modifier, _ = r15_leadership.modifier_for_check(trial, engine.types, broken)
        modifier += r26_fanaticism.modifier_for(trial, broken)
        target = morale_value(engine.types, broken) - (4 if dm else 0)
        ways = sum(count for roll, count in odds.DICE_WAYS.items() if roll + modifier <= target and roll != 12)
        assert view._rally_text(broken) == f"rally {percent(ways, 36)}%"



def a_drop(engine, seed: int = 3):
    """A decision that offers a drop of a weapon, in a game of v1."""
    state = engine.new_game(seed)
    scripted = {p: make_agent("v1", engine, seed, p) for p in (0, 1)}
    steps = 0
    while not state.game_over and steps < 5000:
        frame = engine.legal_commands(state)
        if any(lc.command.action == "drop" for lc in frame.commands):
            return state, frame
        chosen = frame.by_id(scripted[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
        steps += 1
    raise AssertionError("no decision with a drop")


def answer_for(command_id: str) -> str:
    return "Analysis.\n" + json.dumps({schema.COMMAND_FIELD: command_id, "plan": "hold", "reason": "test"})


def test_the_cycle_guard_holds_back_the_command_that_returns_the_position(engine, config):
    """A drop and then the pickup of the same weapon give the position the phase began
    in, a new state hash and the same board. The guard offers the model no pickup, the
    prompt says how many commands it held back, and the counters record the decision."""
    state, frame = a_drop(engine)
    drop = next(lc for lc in frame.commands if lc.command.action == "drop")
    provider = stub(config, [answer_for(drop.id)])
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    assert agent.select(state, frame) == drop.id
    after, _ = engine.apply(state, drop.command, frame)
    assert engine.hash_state(after) != engine.hash_state(state)
    frame_after = engine.legal_commands(after)
    pickup = next(lc for lc in frame_after.commands if lc.command.action == "pickup" and lc.command.weapon == drop.command.weapon)
    back, _ = engine.apply(after, pickup.command, frame_after)
    assert engine.hash_state(back) != engine.hash_state(state)
    assert position_key(back) == position_key(state)
    commands, held = agent.offered(after, frame_after)
    assert held == [pickup.id]
    assert pickup.id not in [lc.id for lc in commands]
    assert len(commands) == len(frame_after.commands) - 1
    text = text_state(engine, after, frame_after, frame.player, [], commands)
    assert pickup.id not in text
    assert "1 command that would return the game to a position of this phase" in text
    provider.answers.append(answer_for(commands[0].id))
    assert agent.select(after, frame_after) == commands[0].id
    assert agent.counters.refused == 1 and agent.counters.refused_commands == 1
    report = agent.report()
    assert report["refused"] == 1 and report["refused_rate"] == 0.5 and report["refused_commands"] == 1
    assert agent.log[-1]["held"] == [pickup.id]


def test_the_cycle_guard_forgets_its_positions_at_the_next_phase(engine, config):
    """The positions of one phase mean nothing in the next: a guard that kept them would
    hold back a rally or a move that gives a board the last phase had."""
    state, frame = a_drop(engine)
    agent = PromptedAgent(engine, frame.player, stub(config, []), make_agent("v1", engine, 3, frame.player))
    agent.offered(state, frame)
    assert agent._window == (state.turn, state.phase) and position_key(state) in agent._seen
    scripted = make_agent("v1", engine, 3, frame.player)
    later = state
    while later.phase == state.phase:
        frame_now = engine.legal_commands(later)
        chosen = frame_now.by_id(scripted.select(later, frame_now)) if frame_now.player == frame.player else frame_now.commands[0]
        later, _ = engine.apply(later, chosen.command, frame_now)
    agent.offered(later, engine.legal_commands(later))
    assert agent._window == (later.turn, later.phase)
    assert position_key(state) not in agent._seen and position_key(later) in agent._seen


def test_the_cycle_guard_stands_down_when_each_command_returns(engine, config):
    """When every legal command gives a position of the phase, the guard offers the full
    list, so the model always has a command to take (FR-47)."""
    state, frame = a_drop(engine)
    agent = PromptedAgent(engine, frame.player, stub(config, []), make_agent("v1", engine, 3, frame.player))
    agent._window = (state.turn, state.phase)
    for lc in frame.commands:
        after, _ = engine.apply(state, lc.command, frame)
        agent._seen.add(position_key(after))
    commands, held = agent.offered(state, frame)
    assert held == [] and [lc.id for lc in commands] == [lc.id for lc in frame.commands]


def test_the_fallback_stands_under_the_cycle_guard(engine, config):
    """After the last failure the scripted default takes over (FR-47). Its choice of a
    command the guard held back would be the cycle again, so the harness gives the first
    offered command of the same kind in its place."""
    state, frame = a_drop(engine)
    drop = next(lc for lc in frame.commands if lc.command.action == "drop")
    after, _ = engine.apply(state, drop.command, frame)
    frame_after = engine.legal_commands(after)
    pickup = next(lc for lc in frame_after.commands if lc.command.action == "pickup" and lc.command.weapon == drop.command.weapon)

    class PicksTheReturn:
        def select(self, state, frame):
            return pickup.id

    agent = PromptedAgent(engine, frame.player, stub(config, []), PicksTheReturn(), retries=0)
    agent._window = (state.turn, state.phase)
    agent._seen.add(position_key(state))
    chosen = agent.select(after, frame_after)
    assert chosen != pickup.id
    assert frame_after.by_id(chosen) is not None
    assert agent.counters.fallbacks == 1

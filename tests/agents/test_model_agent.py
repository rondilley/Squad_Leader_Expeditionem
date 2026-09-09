"""The model agent harness (FR-45 to FR-49, FR-59, SR-04, SR-09, TC-16, TC-17).

The tests that need a network carry the `integration` mark. The rest use a provider stub
that gives a fixed answer, which is a test of the harness and not of a provider: TR-05
forbids a substitute for a provider in a provider test, and these are harness tests.
"""

from __future__ import annotations

import json

import pytest

from slagents.prompted import keys, schema
from slagents.prompted.harness import ASYNCHRONOUS_SECONDS, PromptedAgent, text_state
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


def stub(config, answers) -> ScriptedProvider:
    row = ProviderConfig(name="stub", kind="openai_compatible", endpoint=config.allowlist[1] + "/v1", model="stub-1")
    return ScriptedProvider(answers, row, config.allowlist)


def test_the_prompt_holds_the_state_and_the_legal_list(engine):
    """FR-45: the text state and the legal command list with their identities."""
    state, frame = a_decision(engine)
    text = text_state(engine, state, frame, frame.player, [])
    assert "Your units:" in text
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

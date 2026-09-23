"""The provider layer (IR-01 to IR-05, SR-02, SR-05) and its real calls (TR-05, TR-06).

The tests that reach a network carry the `integration` mark and the default run skips
them. A test that reaches a network never uses a substitute object for the provider: the
requirement says a real call or no test (TR-05).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slagents.prompted import keys, schema
from slagents.prompted.providers import (
    Answer,
    ProviderError,
    ProviderUnavailable,
    allowed_host,
    load_config,
    make_provider,
    providers_for,
)
from slagents.prompted.providers.base import Provider, ProviderConfig
from slagents.prompted.router import Router

LOCAL = "local"
SAAS = "openai"
# TC-20 asks for a real call to each SaaS provider of the release. The list comes from the
# configuration, so a provider added there is tested here without a change to this file.
SAAS_PROVIDERS = tuple(row.name for row in load_config().providers if row.name != LOCAL)


@pytest.fixture(scope="module")
def config():
    return load_config()


# ------------------------------------------------------------------ the key loader


def test_a_key_file_gives_its_first_line_that_is_not_a_comment(tmp_path: Path):
    """SR-02: the loader skips comments and empty lines."""
    (tmp_path / "demo.key.txt").write_text("# a comment\n\nsk-the-value\nsecond line\n", encoding="utf-8")
    assert keys.load("demo", tmp_path) == "sk-the-value"
    assert keys.available("demo", tmp_path)
    assert keys.source_of("demo", tmp_path).kind == "file"


def test_a_missing_key_makes_the_provider_unavailable(tmp_path: Path):
    """SR-02: a provider with no key is unavailable, which is a state and not a fault."""
    assert not keys.available("absent", tmp_path)
    with pytest.raises(keys.KeyMissing) as exc:
        keys.load("absent", tmp_path)
    assert "absent.key.txt" in str(exc.value)


def test_the_environment_variable_takes_the_place_of_the_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DEMO_API_KEY", "from-the-environment")
    assert keys.load("demo", tmp_path) == "from-the-environment"
    assert keys.source_of("demo", tmp_path).kind == "environment"


def test_a_provider_name_cannot_leave_the_project_root(tmp_path: Path):
    """SR-02: the path resolves against the project root and nowhere else."""
    for name in ("../secret", "a/b", "a\\b", ".hidden"):
        with pytest.raises(keys.KeyMissing):
            keys.key_path(name, tmp_path)


def test_a_message_never_holds_the_key(tmp_path: Path):
    (tmp_path / "demo.key.txt").write_text("sk-secret-value\n", encoding="utf-8")
    text = keys.redact("the call failed with sk-secret-value in the body", "demo", tmp_path)
    assert "sk-secret-value" not in text
    assert "[redacted]" in text


# ------------------------------------------------------------------- the allowlist


def test_only_a_host_of_the_allowlist_is_allowed(config):
    """SR-05: the scheme and the host of a request come from the configuration file."""
    assert allowed_host("https://api.openai.com/v1/chat/completions", config.allowlist)
    assert allowed_host("http://tars.uberadmin.com:5150/v1/models", config.allowlist)
    assert not allowed_host("https://api.openai.com.evil.example/v1", config.allowlist)
    assert not allowed_host("http://127.0.0.1:5150/v1", config.allowlist)
    assert not allowed_host("file:///etc/passwd", config.allowlist)
    assert not allowed_host("not a url", config.allowlist)


def test_a_provider_with_an_endpoint_outside_the_allowlist_is_refused(config):
    row = ProviderConfig(name="rogue", kind="openai_compatible", endpoint="https://evil.example/v1", model="m")
    with pytest.raises(ProviderError) as exc:
        Provider(row, config.allowlist)
    assert "allowlist" in str(exc.value)


def test_a_path_cannot_change_the_host(config):
    """SR-05: the address of a call is the endpoint plus a path, so the host never moves."""
    import urllib.parse

    provider = make_provider(LOCAL, config)
    endpoint = urllib.parse.urlsplit(provider.config.endpoint)
    for path in ("/models", "models", "http://evil.example/v1/chat", "//evil.example/v1", "../../evil"):
        built = urllib.parse.urlsplit(provider.url(path))
        assert (built.scheme, built.netloc) == (endpoint.scheme, endpoint.netloc), path


def test_the_configuration_names_the_local_endpoint_as_the_one_private_entry(config):
    """SR-05: the local endpoint is the exception the requirement allows. It is four
    hosts of the owner's network with one model each, and no other private host."""
    private = [host for host in config.allowlist if host.startswith("http://")]
    assert 1 <= len(private) <= 5, private
    assert all(host.endswith(".uberadmin.com:5150") or host.startswith("http://172.20.1.") for host in private), private
    assert "http://127.0.0.1:5150" not in private, "the loopback address is never a provider"
    local_rows = [row for row in config.providers if row.name.startswith(LOCAL)]
    assert len(local_rows) == len(private)
    for row in local_rows:
        assert any(row.endpoint.startswith(host) for host in private), row.endpoint
    assert make_provider(LOCAL, config).config.endpoint.startswith(private[0])


def test_the_local_rows_turn_the_thinking_off_and_the_adapter_sends_it(config):
    """A `request` field of a row goes into each request of that provider."""
    from slagents.prompted.providers import pool_names
    from slagents.prompted.providers.openai_compatible import OpenAiCompatibleProvider

    row = config.by_name(LOCAL)
    assert row.request_fields() == {"chat_template_kwargs": {"enable_thinking": False}}

    class Captured(OpenAiCompatibleProvider):
        """The adapter with its network call replaced by a record of the payload."""

        sent: list = []

        def post(self, path, payload, headers):
            self.sent.append(payload)
            return {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {}}

    provider = Captured(row, config.allowlist)
    provider.complete("system", "user", 10)
    assert provider.sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert provider.sent[0]["model"] == row.model
    # The pool of the four hosts: the seed picks the first, and the others follow.
    names = pool_names("local*", config, seed=0)
    assert names[0] == LOCAL and len(names) == len([r for r in config.providers if r.name.startswith(LOCAL)])
    turned = pool_names("local*", config, seed=1)
    assert turned[0] == names[1] and turned[-1] == names[0]
    assert pool_names("openai", config, seed=5) == ["openai"]
    with pytest.raises(ProviderError):
        pool_names("nosuch*", config)
    # A process that a worker pool bound to one host starts each game there.
    from slagents.prompted.providers import set_pool_offset

    try:
        set_pool_offset(2)
        assert pool_names("local*", config, seed=0)[0] == names[2]
        assert pool_names("local*", config, seed=7)[0] == names[2]
    finally:
        set_pool_offset(None)
    assert pool_names("local*", config, seed=0)[0] == names[0]


def test_the_tier_lists_the_providers_that_have_a_key_here(config):
    names = providers_for("v0.4", config)
    assert LOCAL in names, "the local endpoint needs no key"


# ----------------------------------------------------------------------- the router


class FailingProvider(Provider):
    """A provider that always fails. It is a test double for the router, not for a provider."""

    def __init__(self, name: str, config, allowlist):
        super().__init__(config, allowlist)
        self.calls = 0

    def health(self) -> bool:
        return False

    def complete(self, system, user, max_tokens=700, temperature=0.2, json_schema=None) -> Answer:
        self.calls += 1
        raise ProviderUnavailable(f"{self.name} did not answer inside its timeout")


class SteadyProvider(Provider):
    """A provider that always answers."""

    def health(self) -> bool:
        return True

    def complete(self, system, user, max_tokens=700, temperature=0.2, json_schema=None) -> Answer:
        return Answer(text='{"command_id": "abc"}', seconds=0.01, provider=self.name, model=self.model)


def rows(config):
    first = ProviderConfig(name="first", kind="openai_compatible", endpoint=config.allowlist[0] + "/v1", model="a")
    second = ProviderConfig(name="second", kind="openai_compatible", endpoint=config.allowlist[1] + "/v1", model="b")
    return first, second


def test_the_router_moves_to_the_next_provider_and_logs_it(config):
    """TC-22 and IR-05: one timeout, one failover record."""
    first, second = rows(config)
    bad = FailingProvider("first", first, config.allowlist)
    good = SteadyProvider(second, config.allowlist)
    router = Router([bad, good])
    answer = router.complete("system", "user")
    assert answer.provider == "second"
    report = router.report()
    assert report["sequence"] == ["first", "second"]
    assert len(report["failovers"]) == 1
    assert "did not answer" in report["failovers"][0]["cause"]
    assert bad.calls == 1


def test_the_breaker_opens_after_a_count_of_failures(config):
    """IR-05: a provider that fails twice leaves the sequence for a rest."""
    first, second = rows(config)
    bad = FailingProvider("first", first, config.allowlist)
    good = SteadyProvider(second, config.allowlist)
    router = Router([bad, good], failures_to_open=2, rest_seconds=300.0)
    router.complete("s", "u")
    router.complete("s", "u")
    assert bad.calls == 2
    router.complete("s", "u")
    assert bad.calls == 2, "the breaker kept the failing provider out of the sequence"
    causes = [row["cause"] for row in router.report()["failovers"]]
    assert "the breaker is open" in causes


def test_a_router_with_no_provider_that_answers_raises(config):
    first, second = rows(config)
    router = Router([FailingProvider("first", first, config.allowlist), FailingProvider("second", second, config.allowlist)])
    with pytest.raises(ProviderUnavailable) as exc:
        router.complete("s", "u")
    assert "no provider answered" in str(exc.value)


# ------------------------------------------------------------------- the real calls


@pytest.mark.integration
def test_the_local_endpoint_satisfies_the_health_check(config):
    """IR-01 and TC-21: a real call to the models endpoint."""
    provider = make_provider(LOCAL, config)
    if not provider.health():
        pytest.skip("the local llama-server does not answer on this machine")
    assert provider.health()


@pytest.mark.integration
def test_the_local_model_gives_a_move_that_the_schema_accepts(config):
    """TC-21 and TR-06: one real decision from the local llama-server."""
    provider = make_provider(LOCAL, config)
    if not provider.health():
        pytest.skip("the local llama-server does not answer on this machine")
    decision = _one_decision(provider)
    assert decision is not None


# What a provider says when the key is good and the account is not. These are states of
# the owner's account with that company, and not defects of this project, so the test says
# so and stops. A skip is not a pass, and TC-20 stays open for that provider.
ACCOUNT_STATES = (
    "credit balance is too low",
    "insufficient_quota",
    "exceeded your current quota",
    "rate limit",
    "rate_limited",
    "billing",
)


def account_state(log) -> str:
    """The account message in the harness log, or an empty string."""
    for entry in log:
        problem = str(entry.get("problem", "")).lower()
        for marker in ACCOUNT_STATES:
            if marker in problem:
                return f"{marker}: {problem[:160]}"
    return ""


@pytest.mark.integration
@pytest.mark.parametrize("name", SAAS_PROVIDERS)
def test_a_saas_provider_gives_a_move_that_the_schema_accepts(config, name):
    """TC-20 and TR-05: one real call to each SaaS provider that has a key here."""
    row = config.by_name(name)
    if row.key is None or not keys.available(row.key):
        pytest.skip(f"no key for {name} on this machine")
    provider = make_provider(name, config)
    try:
        decision = _one_decision(provider)
    except AssertionError as exc:
        state = account_state(getattr(exc, "log", []) or _last_log)
        if state:
            pytest.skip(f"{name} answered with an account state, not an answer: {state}")
        raise
    assert decision is not None


@pytest.mark.integration
def test_the_release_reaches_five_saas_providers(config):
    """TC-20: the gate counts providers, so the count is its own check."""
    with_keys = [
        row.name
        for row in config.providers
        if row.name in SAAS_PROVIDERS and row.key is not None and keys.available(row.key)
    ]
    assert len(with_keys) >= 5, f"only {with_keys} have a key on this machine"


def test_the_configuration_names_five_saas_providers():
    """The count of TC-20 is a property of the configuration, and needs no network."""
    assert len(SAAS_PROVIDERS) >= 5


def test_each_provider_kind_has_an_adapter(config):
    """A row with no adapter would fail at the first call and not at the first read."""
    for row in config.providers:
        provider = make_provider(row.name, config)
        assert provider.name == row.name
        assert provider.model == row.model


def test_the_gemini_response_schema_drops_the_keys_that_api_refuses():
    """FR-62: the schema goes to the wire in the subset the Generative Language API takes."""
    from slagents.prompted.providers.gemini import to_response_schema

    source = schema.json_schema(["a1b2c3", "d4e5f6"])
    out = to_response_schema(source)
    assert "additionalProperties" not in out
    assert out["type"] == "object"
    assert out["required"] == source["required"]
    assert out["propertyOrdering"] == list(source["properties"])
    assert out["properties"][schema.COMMAND_FIELD]["enum"] == ["a1b2c3", "d4e5f6"]


def test_the_gemini_adapter_holds_the_model_to_the_schema(config):
    """FR-62: this adapter constrains the answer, and the harness may rely on it."""
    assert make_provider("gemini", config).supports_constraint()


_last_log: list = []


def _one_decision(provider):
    """One real game decision through the harness, with the schema check of FR-46."""
    from slagents.prompted.harness import PromptedAgent
    from slcli.play import build_engine, make_agent

    engine = build_engine("s01_guards_counterattack")
    state = engine.new_game(3)
    scripted = {p: make_agent("v1", engine, 3, p) for p in (0, 1)}
    while state.phase in ("setup", "rally"):
        frame = engine.legal_commands(state)
        chosen = frame.by_id(scripted[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    frame = engine.legal_commands(state)
    agent = PromptedAgent(engine, frame.player, provider, make_agent("v1", engine, 3, frame.player))
    command_id = agent.select(state, frame)
    global _last_log
    _last_log = list(agent.log)
    assert frame.by_id(command_id) is not None, "the answer names a command of the frame"
    report = agent.report()
    assert report["decisions"] == 1
    assert report["fallbacks"] == 0, f"the model did not answer: {agent.log}"
    assert report["median_seconds"] > 0.0
    return command_id

"""The reference-mode loader (FR-27, DR-06, SR-07, SR-10).

The printed layouts are not in this repository, so the test writes a board of its own
into a temporary reference directory and reads it back. That exercises the loader, the
path guard, and the source tag with real files and no substitute objects.
"""

from __future__ import annotations

import json

import pytest

from slboards import reference
from slboards.generator import GeneratorParameters, generate
from sldata.loaders import load_terrain

TERRAIN = load_terrain()


def make_root(tmp_path, monkeypatch, name="board11"):
    layouts = tmp_path / reference.LAYOUT_DIRECTORY
    layouts.mkdir()
    board = generate(GeneratorParameters(seed=404, cols=9, rows=10), TERRAIN)
    (layouts / f"{name}.json").write_text(json.dumps(board.to_dict()), encoding="utf-8")
    monkeypatch.setenv(reference.ENVIRONMENT_OVERRIDE, str(tmp_path))
    return board


def test_the_loader_is_off_when_the_reference_directory_is_absent(tmp_path, monkeypatch):
    monkeypatch.setenv(reference.ENVIRONMENT_OVERRIDE, str(tmp_path / "not_here"))
    assert reference.available() is False
    with pytest.raises(reference.ReferenceUnavailable) as exc:
        reference.load_layout("board11", TERRAIN)
    assert "generated mode" in str(exc.value)


def test_the_default_root_is_the_directory_that_git_does_not_record(monkeypatch):
    monkeypatch.delenv(reference.ENVIRONMENT_OVERRIDE, raising=False)
    assert reference.reference_root().as_posix() == "background/reference"


def test_a_layout_reads_back_as_the_board_that_was_written(tmp_path, monkeypatch):
    written = make_root(tmp_path, monkeypatch)
    board, record = reference.load_layout("board11", TERRAIN)
    assert board.cols == written.cols and board.rows == written.rows
    assert len(board) == len(written)
    assert [h.terrain for h in board] == [h.terrain for h in written]


def test_a_loaded_layout_carries_the_private_source_tag(tmp_path, monkeypatch):
    make_root(tmp_path, monkeypatch)
    board, record = reference.load_layout("board11", TERRAIN)
    assert record == {"board_source": "reference_private", "layout": "board11"}
    assert reference.source_of(board) == "reference_private"


def test_a_generated_board_is_not_tagged_private():
    board = generate(GeneratorParameters(seed=5, cols=9, rows=10), TERRAIN)
    assert reference.source_of(board) == "generated"


def test_a_name_that_leaves_the_reference_directory_is_refused(tmp_path, monkeypatch):
    make_root(tmp_path, monkeypatch)
    with pytest.raises(reference.ReferenceUnavailable) as exc:
        reference.load_layout("../../secrets", TERRAIN)
    assert "outside the layouts directory" in str(exc.value)


def test_a_name_beside_the_layouts_directory_is_refused(tmp_path, monkeypatch):
    """A path that climbs out of layouts and sits next to that directory does not load."""
    make_root(tmp_path, monkeypatch)
    (tmp_path / "beside.json").write_text("{}", encoding="utf-8")
    with pytest.raises(reference.ReferenceUnavailable) as exc:
        reference.load_layout("../beside", TERRAIN)
    assert "outside the layouts directory" in str(exc.value)
    assert not (tmp_path / "layouts" / "beside.json").exists()


def test_a_layout_that_is_not_there_names_the_directory(tmp_path, monkeypatch):
    make_root(tmp_path, monkeypatch)
    with pytest.raises(reference.ReferenceUnavailable) as exc:
        reference.load_layout("board99", TERRAIN)
    assert "board99" in str(exc.value)


def test_a_layout_that_is_not_a_board_record_says_so(tmp_path, monkeypatch):
    make_root(tmp_path, monkeypatch)
    (tmp_path / reference.LAYOUT_DIRECTORY / "broken.json").write_text("{\"hexes\": 3}", encoding="utf-8")
    with pytest.raises(reference.ReferenceUnavailable) as exc:
        reference.load_layout("broken", TERRAIN)
    assert "not a board this build reads" in str(exc.value)


def test_a_layout_that_is_not_json_says_so(tmp_path, monkeypatch):
    make_root(tmp_path, monkeypatch)
    (tmp_path / reference.LAYOUT_DIRECTORY / "torn.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(reference.ReferenceUnavailable) as exc:
        reference.load_layout("torn", TERRAIN)
    assert "not valid JSON" in str(exc.value)


def test_a_layout_with_a_key_the_build_does_not_read_is_refused(tmp_path, monkeypatch):
    """A misspelled key would turn a board feature off with no sign (M2), so it is refused."""
    make_root(tmp_path, monkeypatch)
    path = tmp_path / reference.LAYOUT_DIRECTORY / "board11.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["hexs"] = data.pop("hexes")
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(reference.ReferenceUnavailable) as exc:
        reference.load_layout("board11", TERRAIN)
    assert "hexs" in str(exc.value)

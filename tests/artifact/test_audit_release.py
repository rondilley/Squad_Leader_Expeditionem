"""The release audit (SR-01, SR-06, SR-07, SR-08, TC-25, TC-28, TC-29).

Each test builds a small tree that holds one problem, and asks the audit to find it. The
last test runs the audit over this repository, which is the check the owner runs before a
release.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import audit_release as audit

PAGE = """<html><head><title>{title}</title></head>
<body><footer>{footer}</footer></body></html>
"""
NOTICE = (
    'GPL-3 or later. The <a href="https://example.invalid/src">Corresponding Source</a> is '
    "available. This project is not affiliated with, sponsored by, or endorsed by Hasbro or "
    "Multi-Man Publishing."
)


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def criteria(findings) -> list[str]:
    return [f.criterion for f in findings]


# ------------------------------------------------------------------ TC-25, the key files


def test_a_key_file_that_gitignore_names_is_where_sr_01_puts_it(tmp_path: Path):
    tree(tmp_path, {".gitignore": "*.key.txt\n", "openai.key.txt": "not a real key"})
    assert audit.check_keys(tmp_path) == []


def test_a_key_file_in_a_tree_that_does_not_ignore_it_is_a_finding(tmp_path: Path):
    tree(tmp_path, {".gitignore": "runs/\n", "openai.key.txt": "not a real key"})
    found = audit.check_keys(tmp_path)
    assert criteria(found) == ["TC-25"]
    assert "gitignore" in found[0].detail


def test_a_tree_with_no_key_file_and_no_ignore_rule_is_clean(tmp_path: Path):
    tree(tmp_path, {"README.md": "nothing here"})
    assert audit.check_keys(tmp_path) == []


# ---------------------------------------------------------- TC-29, the scans and the art


def test_an_image_in_the_tree_is_a_finding(tmp_path: Path):
    tree(tmp_path, {"docs/board.png": "not a real image"})
    assert criteria(audit.check_images(tmp_path)) == ["TC-29"]


def test_an_image_in_the_private_directory_is_not_a_finding(tmp_path: Path):
    tree(tmp_path, {"background/board.png": "the owner's own scan"})
    assert audit.check_images(tmp_path) == []


def test_a_block_quote_after_a_rule_tag_is_a_finding(tmp_path: Path):
    tree(tmp_path, {"docs/notes.md": "Rule 7.2 [RULES-4E]:\n\n```\nsome text\n```\n"})
    found = audit.check_quotes(tmp_path)
    assert criteria(found) == ["TC-29"]
    assert found[0].line > 0


def test_a_block_quote_after_a_card_section_is_a_finding(tmp_path: Path):
    tree(tmp_path, {"docs/notes.md": "Victory Conditions:\n\n```\nsome text\n```\n"})
    assert criteria(audit.check_quotes(tmp_path)) == ["TC-29"]


def test_a_markdown_quote_after_a_rule_tag_is_a_finding(tmp_path: Path):
    tree(tmp_path, {"docs/notes.md": "Rule 7.2 [RULES-4E]:\n\n> the quoted sentence\n"})
    assert criteria(audit.check_quotes(tmp_path)) == ["TC-29"]


def test_a_code_block_that_follows_ordinary_prose_is_not_a_finding(tmp_path: Path):
    tree(tmp_path, {"docs/notes.md": "How to run the gate:\n\n```\nsl-cli boards\n```\n"})
    assert audit.check_quotes(tmp_path) == []


def test_a_board_file_named_after_a_printed_board_is_a_finding(tmp_path: Path):
    tree(tmp_path, {"src/sldata/boards/board1.json": "{}", "src/sldata/boards/city-7-v4.json": "{}"})
    found = audit.check_boards(tmp_path)
    assert criteria(found) == ["TC-29"]
    assert "board1.json" in found[0].path


# ------------------------------------------------- TC-28 and SR-08, the page it serves


def test_a_page_with_no_notice_and_the_brand_as_its_name_gives_four_findings(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(PAGE.format(title="Squad Leader AI", footer="ready"), encoding="utf-8")
    found = audit.check_page(tmp_path, page)
    assert criteria(found) == ["TC-28", "TC-28", "SR-08", "SR-08"]


def test_a_page_with_the_notice_and_a_name_of_its_own_is_clean(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(PAGE.format(title="Hex Infantry Combat", footer=NOTICE), encoding="utf-8")
    assert audit.check_page(tmp_path, page) == []


def test_the_public_title_the_owner_named_is_clean_with_the_notice(tmp_path: Path):
    page = tmp_path / "index.html"
    page.write_text(PAGE.format(title=audit.PUBLIC_TITLE, footer=NOTICE), encoding="utf-8")
    assert audit.check_page(tmp_path, page) == []


def test_the_public_title_without_the_notice_is_a_finding(tmp_path: Path):
    page = tmp_path / "index.html"
    body = 'GPL-3. <a href="src">Corresponding Source</a>.'
    page.write_text(PAGE.format(title=audit.PUBLIC_TITLE, footer=body), encoding="utf-8")
    assert criteria(audit.check_page(tmp_path, page)) == ["SR-08"]


def test_a_page_that_names_the_brand_needs_the_non_affiliation_notice(tmp_path: Path):
    page = tmp_path / "index.html"
    body = 'GPL-3. <a href="src">Corresponding Source</a>. A game like Squad Leader.'
    page.write_text(PAGE.format(title="Hex Infantry Combat", footer=body), encoding="utf-8")
    found = audit.check_page(tmp_path, page)
    assert criteria(found) == ["SR-08"]
    assert "non-affiliation" in found[0].detail


def test_a_tree_with_no_built_page_says_so(tmp_path: Path):
    found = audit.check_page(tmp_path, None)
    assert criteria(found) == ["TC-28"]
    assert "no built page" in found[0].detail


# ------------------------------------------------------- SR-10, the public run artifacts


def test_a_run_artifact_from_a_reference_board_is_a_finding(tmp_path: Path):
    runs = tmp_path / "runs" / "20260908T000000Z-x"
    runs.mkdir(parents=True)
    (runs / "manifest.json").write_text(
        json.dumps({"config": {"board_source": "reference_private"}}), encoding="utf-8"
    )
    assert criteria(audit.check_artifacts(tmp_path, tmp_path / "runs")) == ["SR-10"]


def test_a_jsonl_artifact_from_a_reference_board_is_a_finding(tmp_path: Path):
    runs = tmp_path / "runs" / "20260908T000000Z-x"
    runs.mkdir(parents=True)
    (runs / "trace.jsonl").write_text('{"board_source": "reference_private"}\n', encoding="utf-8")
    assert criteria(audit.check_artifacts(tmp_path, tmp_path / "runs")) == ["SR-10"]


def test_a_force_added_key_is_a_finding(tmp_path: Path):
    import subprocess

    tree(tmp_path, {".gitignore": "*.key.txt\n", "openai.key.txt": "secret\n"})
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "-f", "openai.key.txt"], cwd=tmp_path, check=True, capture_output=True)
    found = audit.check_keys(tmp_path)
    assert any(item.path.endswith("openai.key.txt") for item in found)


def test_a_run_artifact_from_a_generated_board_is_clean(tmp_path: Path):
    runs = tmp_path / "runs" / "20260908T000000Z-x"
    runs.mkdir(parents=True)
    (runs / "manifest.json").write_text(
        json.dumps({"config": {"board_source": "generated"}}), encoding="utf-8"
    )
    assert audit.check_artifacts(tmp_path, tmp_path / "runs") == []


def test_a_run_directory_that_is_not_there_is_not_a_finding(tmp_path: Path):
    assert audit.check_artifacts(tmp_path, tmp_path / "runs") == []


# ------------------------------------------------------------------ the exit code and us


def one_problem(tmp_path: Path) -> Path:
    """A tree whose only problem is an image. The page and the ignore rule are in order."""
    return tree(
        tmp_path,
        {
            ".gitignore": "*.key.txt\n",
            "client/index.html": PAGE.format(title="Hex Infantry Combat", footer=NOTICE),
            "docs/board.png": "not a real image",
        },
    )


def test_the_command_gives_one_when_it_finds_something(tmp_path: Path, capsys):
    one_problem(tmp_path)
    assert audit.main(["--root", str(tmp_path), "--runs", str(tmp_path / "runs")]) == 1
    out = capsys.readouterr().out
    assert "TC-29" in out
    assert "1 findings" in out


def test_the_command_gives_zero_when_the_tree_is_clean(tmp_path: Path, capsys):
    tree(
        tmp_path,
        {
            ".gitignore": "*.key.txt\n",
            "client/index.html": PAGE.format(title="Hex Infantry Combat", footer=NOTICE),
        },
    )
    assert audit.main(["--root", str(tmp_path), "--runs", str(tmp_path / "runs")]) == 0
    assert "0 findings" in capsys.readouterr().out


def test_the_json_form_holds_the_criterion_of_each_finding(tmp_path: Path, capsys):
    one_problem(tmp_path)
    audit.main(["--root", str(tmp_path), "--runs", str(tmp_path / "runs"), "--json"])
    document = json.loads(capsys.readouterr().out)
    assert [item["criterion"] for item in document] == ["TC-29"]
    assert document[0]["path"].endswith("board.png")


@pytest.mark.skipif(not Path("client/dist/index.html").is_file(), reason="the client is not built")
def test_this_repository_holds_nothing_that_must_not_leave_the_machine():
    """TC-25, TC-28, and TC-29 over the tree the owner is about to release."""
    root = Path(".").resolve()
    found = audit.audit(root, root / "runs", None)
    assert found == [], "\n".join(str(f) for f in found)

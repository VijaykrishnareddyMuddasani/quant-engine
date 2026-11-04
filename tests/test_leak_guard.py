"""Tests for the leak guard.

Fake secrets are assembled at run time, so this file never contains one and the guard can scan
its own repository cleanly.
"""

import subprocess
from pathlib import Path

import pytest

from quant_engine.devtools.leak_guard import Finding, LeakGuard, install_hooks, load_denylist, main

FAKE_BOT_TOKEN = "1234567890" + ":" + "A" * 35
PUBLIC_IP = ".".join(["8"] * 4)


def rule_names(findings: list[Finding]) -> list[str]:
    return [f.rule for f in findings]


def word_list(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "words.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def git_add(root: Path, *paths: str) -> None:
    subprocess.run(["git", "add", *paths], cwd=root, check=True)


def test_a_bot_token_is_found_and_masked() -> None:
    findings = LeakGuard().scan_text(f'BOT = "{FAKE_BOT_TOKEN}"', "settings.py")
    assert rule_names(findings) == ["telegram-bot-token"]
    assert FAKE_BOT_TOKEN not in findings[0].excerpt
    assert "1234****" in findings[0].excerpt


def test_secrets_assigned_in_code_are_found() -> None:
    line = "api_secret = '" + "x" * 16 + "'"
    assert rule_names(LeakGuard().scan_text(line, "config.py")) == ["assigned-secret"]


def test_private_keys_are_found() -> None:
    header = "-----BEGIN " + "RSA PRIVATE KEY-----"
    assert rule_names(LeakGuard().scan_text(header, "key.txt")) == ["private-key"]


@pytest.mark.parametrize(
    ("address", "flagged"),
    [
        (PUBLIC_IP, True),
        ("10.0.0.1", False),
        ("192.168.1.20", False),
        ("127.0.0.1", False),
        ("203.0.113.7", False),  # reserved for documentation
        ("999.1.1.1", False),  # not an address at all
    ],
)
def test_only_public_ip_addresses_are_flagged(address: str, flagged: bool) -> None:
    findings = LeakGuard().scan_text(f"host = {address}", "deploy.cfg")
    assert (rule_names(findings) == ["public-ipv4"]) is flagged


@pytest.mark.parametrize(
    ("name", "forbidden"),
    [
        (".env", True),
        ("config/.env.local", True),
        (".env.example", False),
        ("deploy/server.pem", True),
        ("notes.md", False),
    ],
)
def test_forbidden_file_names(name: str, forbidden: bool) -> None:
    findings = LeakGuard().scan_blob(name, b"harmless")
    assert ("forbidden-file" in rule_names(findings)) is forbidden


def test_binary_contents_are_skipped() -> None:
    assert LeakGuard().scan_blob("image.png", b"\x00\x01" + FAKE_BOT_TOKEN.encode()) == []


def test_word_list_ignores_comments_and_is_case_insensitive(tmp_path: Path) -> None:
    rules = load_denylist(word_list(tmp_path, "# a comment", "", r"\bsecret sauce\b"))
    assert len(rules) == 1
    findings = LeakGuard(rules).scan_text("The SECRET Sauce is here", "doc.md")
    assert rule_names(findings) == ["private-word-list:3"]


def test_a_bad_pattern_is_an_error_not_a_skipped_rule(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=":1: bad pattern"):
        load_denylist(word_list(tmp_path, "unclosed[group"))


def test_file_names_are_checked_against_the_word_list(tmp_path: Path) -> None:
    guard = LeakGuard(load_denylist(word_list(tmp_path, "sauce")))
    findings = guard.scan_blob("research/sauce_backtest.py", b"print('hi')")
    assert [(f.line, f.rule) for f in findings] == [(0, "private-word-list:1")]


def test_worktree_scan_skips_ignored_files(repo: Path, tmp_path: Path) -> None:
    (repo / ".gitignore").write_text("ignored.txt\n")
    (repo / "ignored.txt").write_text("sauce")
    (repo / "kept.txt").write_text("sauce")
    guard = LeakGuard(load_denylist(word_list(tmp_path, "sauce")))
    assert [f.path for f in guard.scan_worktree(repo)] == ["kept.txt"]


def test_staged_scan_reads_the_index_not_the_working_copy(repo: Path, tmp_path: Path) -> None:
    guard = LeakGuard(load_denylist(word_list(tmp_path, "sauce")))
    notes = repo / "notes.md"
    notes.write_text("clean\n")
    git_add(repo, "notes.md")
    notes.write_text("sauce\n")  # edited after staging: not part of the commit
    assert guard.scan_staged(repo) == []
    git_add(repo, "notes.md")
    assert rule_names(guard.scan_staged(repo)) == ["private-word-list:1"]


def test_commit_message_comment_lines_are_ignored(tmp_path: Path) -> None:
    guard = LeakGuard(load_denylist(word_list(tmp_path, "sauce")))
    assert guard.scan_message("Add loader\n# sauce in a line git added\n") == []
    assert len(guard.scan_message("Add the sauce\n")) == 1


def test_a_missing_word_list_fails_closed(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path), "--denylist", str(tmp_path / "missing.txt")]) == 2


def test_main_exits_1_on_findings_and_0_when_clean(repo: Path, tmp_path: Path) -> None:
    words = word_list(tmp_path, "sauce")
    (repo / "a.txt").write_text("plain")
    assert main(["--root", str(repo), "--denylist", str(words)]) == 0
    (repo / "a.txt").write_text("sauce")
    assert main(["--root", str(repo), "--denylist", str(words)]) == 1


def test_install_hooks_points_both_hooks_at_the_word_list(repo: Path, tmp_path: Path) -> None:
    words = word_list(tmp_path, "sauce")
    hooks = install_hooks(repo, words)
    assert sorted(h.name for h in hooks) == ["commit-msg", "pre-commit"]
    for hook in hooks:
        assert words.resolve().as_posix() in hook.read_text()

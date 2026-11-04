"""Leak guard: keep secrets and private strategy details out of a public repository.

Two kinds of rule:

* **Built-in rules**, safe to run in public CI: bot tokens, cloud and GitHub tokens, private keys,
  secrets assigned in code, public IP addresses, and file names that must never be committed
  (``.env``, ``*.pem`` ...). A matched secret is masked in the report, so a CI log never shows it.
* **A private word list** kept *outside* the repository: terms and numbers that would reveal a
  private strategy. Only the local git hooks use it, because publishing the list would publish
  exactly what it protects.

The guard fails closed: a word list that was asked for but cannot be read blocks the commit.
Blocking a clean commit costs a minute; a leak cannot be taken back.

Usage::

    qe-leak-guard                                   # built-in rules over the working tree
    qe-leak-guard --denylist PATH                   # ... plus a private word list
    qe-leak-guard --staged --denylist PATH          # the staged versions only (pre-commit)
    qe-leak-guard --message FILE --denylist PATH    # a commit message (commit-msg)
    qe-leak-guard --install-hooks --denylist PATH   # write both git hooks
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

BINARY_SNIFF_BYTES = 8192
EXCERPT_CHARS = 100


@dataclass(frozen=True)
class Rule:
    """A named pattern. ``accept`` can veto a match; ``secret`` masks it in reports."""

    name: str
    pattern: re.Pattern[str]
    secret: bool = False
    accept: Callable[[str], bool] | None = None


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.excerpt}"


def _is_public_ip(text: str) -> bool:
    try:
        return ipaddress.ip_address(text).is_global
    except ValueError:
        return False


BUILTIN_RULES: tuple[Rule, ...] = (
    Rule("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), secret=True),
    Rule("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), secret=True),
    Rule("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), secret=True),
    Rule("private-key", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----")),
    Rule(
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?secret|api[_-]?key|access[_-]?token|secret[_-]?key|password)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']"
        ),
        secret=True,
    ),
    Rule("public-ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), accept=_is_public_ip),
)

# File names that are never committed, whatever they contain.
FORBIDDEN_NAMES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "id_rsa*",
    "id_ed25519*",
    "token.json",
    "credentials.json",
)
ALLOWED_NAMES = (".env.example",)


def load_denylist(path: Path) -> tuple[Rule, ...]:
    """Read a private word list: one case-insensitive regular expression per line.

    Blank lines and lines starting with ``#`` are ignored. A pattern that does not compile is an
    error, not a skipped line: a typo must not quietly switch a rule off.
    """
    rules = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            pattern = re.compile(line, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"{path}:{number}: bad pattern {line!r}: {exc}") from exc
        rules.append(Rule(f"private-word-list:{number}", pattern))
    return tuple(rules)


def _excerpt(line: str, match: re.Match[str], secret: bool) -> str:
    text = match.group(0)
    shown = text[:4] + "****" if secret else text
    start = max(match.start() - EXCERPT_CHARS // 2, 0)
    before = line[start : match.start()]
    after = line[match.end() : match.end() + EXCERPT_CHARS // 2]
    return f"{before}{shown}{after}".strip()


def _forbidden_name(path: str) -> bool:
    name = PurePosixPath(path)
    if any(name.match(p) for p in ALLOWED_NAMES):
        return False
    return any(name.match(p) for p in FORBIDDEN_NAMES)


class LeakGuard:
    """Scans text, files, a working tree or the git index against a set of rules."""

    def __init__(self, rules: Sequence[Rule] = BUILTIN_RULES) -> None:
        self.rules = tuple(rules)

    @classmethod
    def with_denylist(cls, denylist: Path | None) -> LeakGuard:
        extra = load_denylist(denylist) if denylist is not None else ()
        return cls((*BUILTIN_RULES, *extra))

    def scan_text(self, text: str, origin: str) -> list[Finding]:
        findings = []
        for number, line in enumerate(text.splitlines(), start=1):
            for rule in self.rules:
                for match in rule.pattern.finditer(line):
                    if rule.accept is not None and not rule.accept(match.group(0)):
                        continue
                    findings.append(
                        Finding(origin, number, rule.name, _excerpt(line, match, rule.secret))
                    )
        return findings

    def scan_blob(self, path: str, data: bytes) -> list[Finding]:
        """Check one file: its name, then (unless it is binary) its contents."""
        findings = []
        if _forbidden_name(path):
            findings.append(Finding(path, 0, "forbidden-file", "this file must never be committed"))
        findings += [
            Finding(path, 0, f.rule, f"in the file name: {f.excerpt}")
            for f in self.scan_text(path, path)
        ]
        if b"\x00" not in data[:BINARY_SNIFF_BYTES]:
            findings += self.scan_text(data.decode("utf-8", errors="replace"), path)
        return findings

    def scan_worktree(self, root: Path) -> list[Finding]:
        """Every file git would let you commit: tracked plus untracked-but-not-ignored."""
        findings = []
        for path in _git_paths(
            root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        ):
            file = root / path
            if file.is_file():
                findings += self.scan_blob(path, file.read_bytes())
        return findings

    def scan_staged(self, root: Path) -> list[Finding]:
        """The staged version of each staged file, which is what the commit will contain."""
        findings = []
        for path in _git_paths(
            root, ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"]
        ):
            findings += self.scan_blob(path, _git(root, ["show", f":{path}"]))
        return findings

    def scan_message(self, message: str) -> list[Finding]:
        """A commit message, without the comment lines git adds to the editor."""
        kept = "\n".join(line for line in message.splitlines() if not line.startswith("#"))
        return self.scan_text(kept, "commit message")


def _git(root: Path, args: Sequence[str]) -> bytes:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def _git_paths(root: Path, args: Sequence[str]) -> list[str]:
    return [p for p in _git(root, args).decode("utf-8").split("\0") if p]


HOOK_TEMPLATE = """#!/bin/sh
# Written by qe-leak-guard --install-hooks. Blocks the commit when the guard finds anything.
cd "$(git rev-parse --show-toplevel)" || exit 1
PYTHONPATH=src exec "{python}" -m quant_engine.devtools.leak_guard {mode} --denylist "{denylist}"
"""


def install_hooks(root: Path, denylist: Path) -> list[Path]:
    """Write pre-commit and commit-msg hooks that run the guard with ``denylist``."""
    hooks = root / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    written = []
    for name, mode in (("pre-commit", "--staged"), ("commit-msg", '--message "$1"')):
        hook = hooks / name
        hook.write_text(
            HOOK_TEMPLATE.format(
                python=Path(sys.executable).as_posix(),
                mode=mode,
                denylist=denylist.resolve().as_posix(),
            ),
            encoding="utf-8",
            newline="\n",
        )
        hook.chmod(0o755)
        written.append(hook)
    return written


def _report(findings: Iterable[Finding]) -> int:
    found = list(findings)
    for finding in found:
        print(finding, file=sys.stderr)
    if found:
        print(
            f"\nleak guard: {len(found)} finding(s) - nothing may be committed until they "
            "are removed",
            file=sys.stderr,
        )
        return 1
    print("leak guard: clean")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qe-leak-guard",
        description="Keep secrets and private strategy details out of a public repository.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--denylist",
        type=Path,
        default=os.environ.get("QE_DENYLIST"),
        help="private word list (default: $QE_DENYLIST)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true", help="scan the git index only")
    mode.add_argument("--message", type=Path, help="scan this commit-message file")
    mode.add_argument("--install-hooks", action="store_true", help="write the git hooks")
    args = parser.parse_args(argv)

    denylist = Path(args.denylist) if args.denylist else None
    if denylist is not None and not denylist.is_file():
        print(f"leak guard: word list {denylist} not found - refusing to pass", file=sys.stderr)
        return 2
    if args.install_hooks:
        if denylist is None:
            parser.error("--install-hooks needs --denylist")
        for hook in install_hooks(args.root, denylist):
            print(f"installed {hook}")
        return 0

    guard = LeakGuard.with_denylist(denylist)
    if args.message is not None:
        return _report(guard.scan_message(args.message.read_text(encoding="utf-8")))
    if args.staged:
        return _report(guard.scan_staged(args.root))
    return _report(guard.scan_worktree(args.root))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Decide whether a PR's changed files are safe to merge unattended.

Exits 0 when every changed file is clear of the protected list, 1 when any
file matches. Fails closed: an unreadable pattern file or an empty file list
is a refusal, not an approval.

Usage:
    git diff --name-only base...head | auto_merge_guard.py <patterns-file>
"""
import re
import sys


def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a gitignore-ish glob into an anchored regex.

    `**/` matches any directory prefix including none, a trailing `/**`
    matches everything beneath, and a lone `*` stops at a path separator so
    `**/requirements*.txt` cannot reach into a subdirectory.
    """
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append(r"(?:.*/)?")
            i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append(r"/.*")
            i += 3
        elif pattern[i] == "*":
            out.append(r"[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def load_patterns(path: str) -> list[tuple[str, re.Pattern]]:
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    return [
        (line.strip(), glob_to_regex(line.strip()))
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: auto_merge_guard.py <patterns-file>", file=sys.stderr)
        return 1

    try:
        patterns = load_patterns(sys.argv[1])
    except OSError as exc:
        print(f"::error::Cannot read protected-path list: {exc}", file=sys.stderr)
        return 1

    changed = [line.strip() for line in sys.stdin if line.strip()]
    if not changed:
        print("::error::No changed files reported — refusing to auto-merge.", file=sys.stderr)
        return 1

    hits = [
        (path, raw)
        for path in changed
        for raw, rx in patterns
        if rx.match(path)
    ]

    if hits:
        print("Auto-merge blocked. Protected paths touched:")
        for path, raw in hits:
            print(f"  {path}  (matched `{raw}`)")
        return 1

    print(f"No protected paths touched ({len(changed)} file(s) changed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

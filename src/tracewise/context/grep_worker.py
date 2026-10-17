"""Isolated regex matcher for the `grep` tool (T-305).

Run as `python -I -m tracewise.context.grep_worker` with JSON on stdin. Model-supplied patterns can be
catastrophic (ReDoS), so matching happens in this short-lived process under CPU and memory rlimits;
the parent kills it on timeout. No file or network access: input is the text to search.
"""

from __future__ import annotations

import json
import re
import resource
import sys


def main() -> int:
    resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    req = json.loads(sys.stdin.buffer.read())
    try:
        rx = re.compile(req["pattern"], re.IGNORECASE if req.get("ignore_case") else 0)
    except (re.error, RecursionError, OverflowError):
        sys.stdout.write(json.dumps({"error": "invalid pattern"}))
        return 0
    max_matches, max_line = int(req["max_matches"]), int(req["max_line_chars"])
    matches: list[list[object]] = []
    truncated = False
    for path, text in req["files"]:
        for no, line in enumerate(text.splitlines(), 1):
            if rx.search(line[:2000]):
                if len(matches) >= max_matches:
                    truncated = True
                    break
                matches.append([path, no, line[:max_line]])
        if truncated:
            break
    sys.stdout.write(json.dumps({"matches": matches, "truncated": truncated}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

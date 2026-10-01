"""A minimal ``.env`` reader so provider API keys can live in a file instead of the shell.

Only names are ever reported or printed; values never leave this module except into
``os.environ``. A variable that is already set in the environment is never overridden.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Union

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    # An unquoted value ends at an inline comment.
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def load_env_file(path: Union[str, Path]) -> list[str]:
    """Set variables from ``path`` that are not already set; return the names it set.

    A missing or unreadable file, comment lines and malformed lines are skipped silently.
    """

    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    applied: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _LINE.match(line)
        if not match:
            continue
        name, value = match.group(1), _unquote(match.group(2))
        if name in os.environ:
            continue
        os.environ[name] = value
        applied.append(name)
    return applied

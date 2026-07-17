"""Generic append-only JSONL snapshot store (moat #2 trend persistence).

Parametrized by the pydantic snapshot model so both the held-out detector trend
(EvalSnapshot) and the self-heal outcome-match trend (HealSnapshot) share one
writer/loader. Mirrors eval_history.append_snapshot/load_history, but load skips
malformed lines too (matches the dashboard reader), so a hand-edited or
half-written history never crashes --history.
"""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def append_jsonl(snapshot: BaseModel, path: str | PathLike[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as fh:
        fh.write(snapshot.model_dump_json() + "\n")


def load_jsonl(model_cls: type[T], path: str | PathLike[str]) -> list[T]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[T] = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(model_cls.model_validate_json(line))
        except ValidationError:
            continue  # skip a malformed/half-written line; rest is valid
    return out

"""Append-only JSONL trajectory storage and replay verification."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Event:
    step: int
    kind: str
    actual_before: str
    actual_after: str
    move: str | None
    plan_version: int
    payload: dict[str, object]


class Trajectory:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def write_jsonl(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(asdict(event), sort_keys=True) + "\n" for event in self.events),
            encoding="utf-8",
        )

    @classmethod
    def read_jsonl(cls, path: str | Path) -> "Trajectory":
        trajectory = cls()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            trajectory.append(Event(**json.loads(line)))
        return trajectory

    def verify_chain(self) -> None:
        for previous, current in zip(self.events, self.events[1:]):
            if previous.actual_after != current.actual_before:
                raise ValueError(f"broken state chain at step {current.step}")


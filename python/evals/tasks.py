"""Declarative task fixtures for the eval harness.

Each task is a JSON file under `python/eval/tasks/` shaped:

    {
      "name": "manual_alert_create",
      "prompt": "<natural language brief for the LLM>",
      "gold_yaml_path": "examples/demo_alert_action.yaml",  // optional
      "notes": "..."
    }

The `gold_yaml_path` is resolved relative to the repo root. When set,
the harness compiles the gold YAML once for byte-equality comparison
in scoring.gold. When absent, the gold gate is skipped.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = Path(__file__).resolve().parent / "tasks"


@dataclass(frozen=True)
class Task:
    name: str
    prompt: str
    gold_yaml_path: Optional[str] = None  # repo-relative
    notes: str = ""

    def gold_yaml_text(self) -> Optional[str]:
        if not self.gold_yaml_path:
            return None
        p = REPO_ROOT / self.gold_yaml_path
        if not p.exists():
            return None
        return p.read_text(encoding="utf-8")


def load_tasks(filter_names: list[str] | None = None) -> list[Task]:
    """Load every `*.json` task fixture, optionally filtered by name."""
    tasks: list[Task] = []
    for p in sorted(TASKS_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        tasks.append(Task(
            name=data["name"],
            prompt=data["prompt"],
            gold_yaml_path=data.get("gold_yaml_path"),
            notes=data.get("notes", ""),
        ))
    if filter_names:
        wanted = set(filter_names)
        tasks = [t for t in tasks if t.name in wanted]
    return tasks

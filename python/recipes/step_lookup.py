"""Step recipe library: validated YAML fragments the agent can paste in.

Recipes live as one .yaml file each in `recipes/steps/` and contain a
small block of one or more steps that compile clean. Each carries
`intent_keywords` for fuzzy-matching agent intents and an optional
`connector` for filtering. The MCP `find_step_recipe` tool wraps this
module.

The point: instead of the agent re-deriving the valid param set for a
common scenario (FortiGate block IP, approval gate, manual trigger,
…), it picks a recipe by intent and customizes the placeholders. Saves
the validate-fix-validate spiral.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

STEPS_DIR = Path(__file__).resolve().parent / "steps"


@dataclass
class StepRecipe:
    name: str
    description: str
    intent_keywords: list[str]
    connector: str | None
    operation: str | None
    step_types: list[str]
    steps_yaml: str
    notes: str | None
    source_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description.strip(),
            "intent_keywords": self.intent_keywords,
            "connector": self.connector,
            "operation": self.operation,
            "step_types": self.step_types,
            "steps_yaml": self.steps_yaml,
            "notes": (self.notes or "").strip() or None,
        }


def _load_one(path: Path) -> StepRecipe:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return StepRecipe(
        name=data["name"],
        description=data.get("description", ""),
        intent_keywords=list(data.get("intent_keywords") or []),
        connector=data.get("connector"),
        operation=data.get("operation"),
        step_types=list(data.get("step_types") or []),
        steps_yaml=data.get("steps_yaml", ""),
        notes=data.get("notes"),
        source_path=path,
    )


def load_all() -> list[StepRecipe]:
    if not STEPS_DIR.exists():
        return []
    return sorted(
        (_load_one(p) for p in STEPS_DIR.glob("*.yaml")),
        key=lambda r: r.name,
    )


def _score(recipe: StepRecipe, intent: str, connector: str | None) -> float:
    """Cheap keyword-overlap score; deterministic, no embedding model."""
    intent_l = (intent or "").lower()
    if not intent_l and not connector:
        return 0.0
    score = 0.0
    # Connector match is a strong filter — when the user names a connector
    # and the recipe binds to one, require an exact match (or skip).
    if connector and recipe.connector:
        if recipe.connector.lower() == connector.lower():
            score += 5.0
        else:
            return 0.0
    elif connector and not recipe.connector:
        # Generic recipe still useful if the intent matches.
        pass
    # Keyword overlap: substring of any keyword in the intent string.
    for kw in recipe.intent_keywords:
        kw_l = kw.lower()
        if kw_l in intent_l:
            score += 2.0
        else:
            # Partial word overlap fallback.
            tokens = set(kw_l.split())
            intent_tokens = set(intent_l.split())
            overlap = tokens & intent_tokens
            if overlap:
                score += 0.5 * len(overlap)
    # Light bonus when the recipe name itself appears in intent.
    if recipe.name.replace("_", " ") in intent_l:
        score += 1.5
    return score


def find(intent: str = "", connector: str | None = None,
         step_type: str | None = None,
         limit: int = 5) -> list[StepRecipe]:
    """Top-N recipes by keyword overlap; deterministic.

    Pass `step_type` to filter by step-type tag (e.g. only manual_input).
    Returns an empty list when nothing scores >0.
    """
    recipes = load_all()
    if step_type:
        recipes = [r for r in recipes if step_type in r.step_types]
    scored = [(r, _score(r, intent, connector)) for r in recipes]
    scored = [(r, s) for r, s in scored if s > 0]
    scored.sort(key=lambda x: (-x[1], x[0].name))
    return [r for r, _ in scored[:limit]]


def by_name(name: str) -> StepRecipe | None:
    for r in load_all():
        if r.name == name:
            return r
    return None

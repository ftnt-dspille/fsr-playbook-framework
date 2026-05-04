"""List + load YAML examples from FSRPlaybookYaml/examples/."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = REPO_ROOT / "examples"


router = APIRouter(prefix="/api/examples", tags=["examples"])


@router.get("")
def list_examples() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if not EXAMPLES_DIR.exists():
        return out
    for p in sorted(EXAMPLES_DIR.glob("*.yaml")):
        if p.name.endswith(".test.yaml"):
            continue
        first = ""
        try:
            with p.open() as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("#") or not s:
                        continue
                    first = s
                    break
        except OSError:
            pass
        out.append({"name": p.stem, "filename": p.name, "preview": first[:120]})
    return out


@router.get("/{name}")
def load_example(name: str) -> dict[str, str]:
    safe = name.replace("/", "").replace("..", "")
    p = EXAMPLES_DIR / f"{safe}.yaml"
    if not p.exists():
        raise HTTPException(404, f"example {name!r} not found")
    return {"name": p.stem, "text": p.read_text()}

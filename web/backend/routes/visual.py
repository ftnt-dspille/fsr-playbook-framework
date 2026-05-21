"""Visual editor backend.

Phase 1 of VISUAL_EDITOR_PLAN: serve the projected graph for an
existing YAML file or an in-flight YAML buffer. POST is used for the
in-buffer case (Monaco unsaved text) and GET for files on disk.

Phase 3 will add a write endpoint that delegates to
`compiler.visual_model.from_visual` and persists the layout block.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from compiler.visual_model import to_visual, from_visual
from compiler.samples import (
    append_samples,
    extract_samples_block,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = REPO_ROOT / "examples"

router = APIRouter(prefix="/api/visual", tags=["visual"])


class GraphIn(BaseModel):
    text: str


def _safe_resolve(rel_path: str) -> Path:
    """Resolve `rel_path` under `examples/` and reject any escape.

    Frontend passes paths like `decision_branch.yaml`; we keep
    everything relative to a fixed root so this endpoint can never
    read /etc/hosts.
    """
    candidate = (EXAMPLES_DIR / rel_path).resolve()
    if not str(candidate).startswith(str(EXAMPLES_DIR.resolve())):
        raise HTTPException(400, "path escapes examples/ root")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(404, f"no such file: {rel_path}")
    return candidate


@router.get("/list")
def list_examples() -> dict[str, Any]:
    """List authored YAML fixtures available for read-only canvas viewing.

    Filters out `*.test.yaml` snapshots so the picker stays clean.
    """
    files = []
    for p in sorted(EXAMPLES_DIR.glob("*.yaml")):
        if p.name.endswith(".test.yaml"):
            continue
        files.append({"name": p.name, "size": p.stat().st_size})
    return {"count": len(files), "files": files}


@router.get("/file")
def graph_for_file(path: str) -> dict[str, Any]:
    """Return the visual graph for an examples/* fixture by name."""
    target = _safe_resolve(path)
    text = target.read_text()
    graph = to_visual(text)
    graph["source"] = {"path": path, "yaml": text}
    return graph


@router.post("/")
def graph_for_buffer(payload: GraphIn) -> dict[str, Any]:
    """Project an in-flight YAML buffer (Monaco unsaved text)."""
    graph = to_visual(payload.text)
    graph["source"] = {"path": None, "yaml": payload.text}
    return graph


class WriteIn(BaseModel):
    original_yaml: str
    graph: dict[str, Any]


@router.post("/write")
def write_graph(payload: WriteIn) -> dict[str, Any]:
    """Apply a graph back to YAML via `from_visual`.

    Returns `{ok, yaml, graph}` so the caller can refresh both the
    Monaco buffer and the canvas without an extra round-trip. On
    structural-edit limits not yet supported (edge rewiring), surfaces
    `{ok: false, code: 'unsupported_edit', message}` instead of 500.
    """
    try:
        new_yaml = from_visual(payload.graph, payload.original_yaml)
    except NotImplementedError as e:
        return {"ok": False, "code": "unsupported_edit", "message": str(e)}
    except Exception as e:
        return {"ok": False, "code": "write_failed",
                "message": f"{type(e).__name__}: {e}"}
    graph = to_visual(new_yaml)
    graph["source"] = {"path": None, "yaml": new_yaml}
    return {"ok": True, "yaml": new_yaml, "graph": graph}


class DraftStepIn(BaseModel):
    step_type: str
    intent: str
    module: str | None = None
    current_args: dict[str, Any] | None = None
    provider: str | None = None


@router.post("/draft-step")
async def draft_step(payload: DraftStepIn) -> dict[str, Any]:
    """AI-driven "describe → step args" drafter.

    Posts the user's natural-language intent + the current step type
    (and module, when relevant) to the configured LLM provider with a
    focused system prompt: corpus patterns, schema fields, picklist
    values. Returns proposed JSON args the inspector can preview as a
    diff against the current step.

    See ``backend/step_drafter.py`` for the prompt-building logic.
    """
    from backend.step_drafter import draft_step_args, STEP_INTROS

    if payload.step_type not in STEP_INTROS:
        raise HTTPException(400,
            f"step type {payload.step_type!r} not supported by drafter; "
            f"supported: {sorted(STEP_INTROS)}")
    if not payload.intent.strip():
        raise HTTPException(400, "intent must not be empty")

    return await draft_step_args(
        step_type=payload.step_type,
        intent=payload.intent,
        module=payload.module,
        current_args=payload.current_args,
        provider_name=payload.provider,
    )


class FileWriteIn(BaseModel):
    path: str
    graph: dict[str, Any]


@router.post("/write_file")
def write_file(payload: FileWriteIn) -> dict[str, Any]:
    """Same as /write, but persists the result back to the file.

    Examples are reference fixtures; allowing in-place edits caused the
    test suite to break when the visual editor wrote scratch graphs
    over them (incomplete Decision steps etc.). Writes are now refused
    with a structured `examples_readonly` response so the frontend can
    redirect through `playbookStore.cloneExample` instead.
    """
    # Validate the path resolves under examples/ before refusing so an
    # attacker can't probe arbitrary filesystem locations through this
    # endpoint.
    _safe_resolve(payload.path)
    return {
        "ok": False,
        "code": "examples_readonly",
        "message": (
            "examples/ are read-only — clone to a draft before saving. "
            "Use POST /api/playbooks/draft/from-example."
        ),
    }


class SamplesIn(BaseModel):
    """Replace the entire `# fsrpb:samples` sidecar block.

    Whole-map writes are fine here — the block is tiny, the diff cost
    is dominated by network not bytes, and per-step PATCH would invite
    last-writer-wins races with no real upside.
    """
    yaml_text: str
    samples: dict[str, dict[str, Any]]


@router.post("/samples")
def write_samples(payload: SamplesIn) -> dict[str, Any]:
    """Rewrite the samples sidecar block on a YAML buffer.

    Returns `{ok, yaml}` so the caller can splice the new buffer back
    into the playbook store without an extra round-trip. The samples
    map is per-playbook → per-step → arbitrary payload (today: just
    `{input: {...}}` for `manual_input`); the backend doesn't validate
    keys against the IR so future step types can drop in samples
    without a backend release.
    """
    _existing, body = extract_samples_block(payload.yaml_text)
    new_yaml = append_samples(body, payload.samples)
    return {"ok": True, "yaml": new_yaml}

"""FSR Playbook Studio — FastAPI entrypoint.

Phase 0: skeleton with /api/health. Imports the existing compiler package
to verify the in-process integration works before we add real routes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = REPO_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

# Smoke-import the compiler so we fail fast if the integration is broken.
try:
    import compiler  # noqa: F401
    _compiler_ok = True
    _compiler_err: str | None = None
except Exception as e:  # pragma: no cover
    _compiler_ok = False
    _compiler_err = f"{type(e).__name__}: {e}"


app = FastAPI(title="FSR Playbook Studio", version="0.0.1")

from .routes.yaml_routes import router as yaml_router  # noqa: E402
from .routes.chat import router as chat_router  # noqa: E402
from .routes.playbook import router as playbook_router  # noqa: E402
from .routes.ref import router as ref_router  # noqa: E402
from .routes.examples import router as examples_router  # noqa: E402

app.include_router(yaml_router)
app.include_router(chat_router)
app.include_router(playbook_router)
app.include_router(ref_router)
app.include_router(examples_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _probe_fsr() -> dict:
    """Live ping of FSR. Cheap and non-throwing; surfaces in the UI as a pill."""
    try:
        from probes import _env  # type: ignore
    except Exception as e:
        return {"ok": False, "error": f"probes import failed: {e}"}
    try:
        cfg = _env.get_config()
        if not cfg.is_live():
            return {"ok": False, "error": "FSR_BASE_URL / auth missing in .env"}
        client = _env.get_client()
        # /api/3/picklists is universally available across FSR versions and
        # cheap (one row). Auth-required, so a 200 also confirms the JWT is good.
        r = client.session.get(
            client.base_url + "/api/3/picklists/?$limit=1",
            verify=client.verify_ssl,
            timeout=4,
        )
        if r.status_code == 200:
            return {"ok": True, "base_url": cfg.base_url}
        return {"ok": False, "error": f"HTTP {r.status_code}", "base_url": cfg.base_url}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": _compiler_ok,
        "compiler": {"ok": _compiler_ok, "error": _compiler_err},
        "fsr": _probe_fsr(),
        "llm": {"configured": bool(os.environ.get("ANTHROPIC_API_KEY"))},
    }

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


# Self-signed FSR appliances (e.g. dev VMs) trigger urllib3's
# InsecureRequestWarning every probe. Suppress in the backend's own log
# unless the operator explicitly turns it back on. Subprocess output is
# filtered separately (see routes/playbook.py).
if os.environ.get("FSR_SUPPRESS_INSECURE_WARNING", "true").lower() != "false":
    try:
        import urllib3  # noqa: E402

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

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
from .routes.llm_config import router as llm_config_router  # noqa: E402
from .routes.history import router as history_router  # noqa: E402

app.include_router(yaml_router)
app.include_router(chat_router)
app.include_router(playbook_router)
app.include_router(ref_router)
app.include_router(examples_router)
app.include_router(llm_config_router)
app.include_router(history_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:47822"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


_FSR_PROBE_CACHE: dict = {"ts": 0.0, "result": None}
_FSR_PROBE_TTL_SECONDS = 5.0


def _probe_fsr() -> dict:
    """Live ping of FSR. Cheap and non-throwing; surfaces in the UI as a pill.

    Result cached for 5 seconds so concurrent /api/health calls don't pile up
    on the sync threadpool when FSR is slow or unreachable (each probe waits
    up to 4 s on the network round-trip).
    """
    import time as _t
    now = _t.monotonic()
    cached = _FSR_PROBE_CACHE.get("result")
    if cached is not None and (now - _FSR_PROBE_CACHE["ts"]) < _FSR_PROBE_TTL_SECONDS:
        return cached

    try:
        from probes import _env  # type: ignore
    except Exception as e:
        result = {"ok": False, "error": f"probes import failed: {e}"}
        _FSR_PROBE_CACHE["result"] = result
        _FSR_PROBE_CACHE["ts"] = now
        return result
    try:
        cfg = _env.get_config()
        if not cfg.is_live():
            result = {"ok": False, "error": "FSR_BASE_URL / auth missing in .env"}
        else:
            client = _env.get_client()
            r = client.session.get(
                client.base_url + "/api/3/picklists/?$limit=1",
                verify=client.verify_ssl,
                timeout=4,
            )
            if r.status_code == 200:
                result = {"ok": True, "base_url": cfg.base_url}
            else:
                result = {"ok": False, "error": f"HTTP {r.status_code}",
                          "base_url": cfg.base_url}
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    _FSR_PROBE_CACHE["result"] = result
    _FSR_PROBE_CACHE["ts"] = now
    return result


@app.get("/api/health")
def health() -> dict:
    from . import settings as _settings  # local import: avoids touching keyring at import time
    active = _settings.get_active_provider_name()
    cfg = _settings.load_provider(active)
    return {
        "ok": _compiler_ok,
        "compiler": {"ok": _compiler_ok, "error": _compiler_err},
        "fsr": _probe_fsr(),
        "llm": {
            "configured": cfg.is_configured(),
            "provider": active,
            "model": cfg.model or None,
        },
        "secrets": _settings.secrets_health(),
    }

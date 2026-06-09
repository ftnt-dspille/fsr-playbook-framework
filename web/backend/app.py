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


def _load_dotenv() -> None:
    """Load repo-root `.env` into os.environ before anything reads it.

    `settings._DEFAULTS` resolves OPENAI_ENDPOINT/OPENAI_MODEL (and other
    providers read keys) at import time, and `make backend` runs bare
    uvicorn with no env sourcing — so without this the .env is invisible to
    the backend. setdefault: never clobber a real shell-exported value."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value and value[0] not in ('"', "'"):
            hash_idx = value.find("#")
            if hash_idx >= 0:
                value = value[:hash_idx].rstrip()
        os.environ.setdefault(key.strip(), value.strip('"').strip("'"))


_load_dotenv()


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
    import fsr_core.compiler as compiler  # noqa: F401
    _compiler_ok = True
    _compiler_err: str | None = None
except Exception as e:  # pragma: no cover
    _compiler_ok = False
    _compiler_err = f"{type(e).__name__}: {e}"


app = FastAPI(title="FSR Playbook Studio", version="0.0.1")

# Install the backend-settings-backed ConfigProvider so fsr_core.llm
# can resolve provider configs without importing the web backend.
from fsr_core.llm import factory as _llm_factory  # noqa: E402
from . import settings as _settings  # noqa: E402
from fsr_core.protocols import ProviderConfig as _CoreProviderConfig  # noqa: E402


class _BackendConfigProvider:
    """Adapter from `backend.settings` to fsr_core's ConfigProvider."""
    def get_active_provider_name(self) -> str:
        return _settings.get_active_provider_name()

    def load_provider(self, name: str):
        cfg = _settings.load_provider(name)
        return _CoreProviderConfig(
            name=cfg.name, base_url=cfg.base_url,
            api_key=cfg.api_key, model=cfg.model,
        )


_llm_factory.set_config_provider(_BackendConfigProvider())


def _install_approval_persistence() -> None:
    """Phase 3.2 — back the HITL approval gateway with sqlite so suspended
    tier-3+ sessions survive a backend restart. Installs as the process-wide
    default so both the provider (stash side) and the chat route (resolve
    side) share one persisted store. Also pins a stable HMAC key (3.1) in the
    secrets store so persisted tokens still verify after a restart; without a
    stable key the binding check fails closed and the analyst re-issues."""
    import secrets as _secrets
    from fsr_core.llm import approvals as _approvals

    if not os.environ.get("FSR_APPROVAL_HMAC_KEY"):
        try:
            from .secrets_store import get_secrets
            sb = get_secrets()
            ok, _why = sb.available()
            if ok:
                key = sb.get("approval_hmac_key")
                if not key:
                    key = _secrets.token_hex(32)
                    sb.set("approval_hmac_key", key)
                os.environ["FSR_APPROVAL_HMAC_KEY"] = key
            # else: keyring unavailable → fall through to approvals' per-process
            # random secret (persisted sessions won't verify across a restart).
        except Exception:
            pass

    try:
        db_path = Path(__file__).resolve().parent / "approvals.db"
        _approvals.set_default_gateway(
            _approvals.SqliteApprovalGateway(str(db_path))
        )
    except Exception:
        # Never block startup on persistence — fall back to the in-memory
        # default gateway already installed at import.
        pass


from .routes.yaml_routes import router as yaml_router  # noqa: E402
from .routes.chat import router as chat_router  # noqa: E402
from .routes.playbook import router as playbook_router  # noqa: E402
from .routes.ref import router as ref_router  # noqa: E402
from .routes.examples import router as examples_router  # noqa: E402
from .routes.llm_config import router as llm_config_router  # noqa: E402
from .routes.history import router as history_router  # noqa: E402
from .routes.mcp import router as mcp_router  # noqa: E402
from .routes.visual import router as visual_router  # noqa: E402
from .routes.playbooks import router as playbooks_router  # noqa: E402

app.include_router(yaml_router)
app.include_router(chat_router)
app.include_router(playbook_router)
app.include_router(ref_router)
app.include_router(examples_router)
app.include_router(llm_config_router)
app.include_router(history_router)
app.include_router(mcp_router)
app.include_router(visual_router)
app.include_router(playbooks_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:47822"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup() -> None:
    # Defer to startup (not import) so we don't touch keyring at import time —
    # mirrors the keyring-deferral the /api/health handler relies on.
    _install_approval_persistence()


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

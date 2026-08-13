"""Run the agentic evals without a FortiSOAR appliance (`EVAL_OFFLINE=1`).

Every agentic eval dispatches its tool calls through
`fsr_playbooks.llm.tools.dispatch`, and the live-touching tools resolve their
HTTP client through one seam: `probes._env.get_client()`, memoised by
`_shared._live_client()`. That means a degrading box scores as agent
regression -- pool exhaustion and 8s read timeouts on a connector healthcheck
poisoned a screening run mid-flight, and the matrix had no way to say so.

This module points that seam at the simulated client
(`fsr_playbooks.mcp_server._sim_client`), which already serves the three
live-touching integration endpoints from canned fixtures and is the same bridge
`build_trace_fixture` and `test_sim_run_op_integration` use. Nothing about the
agent loop, the tool registry or the scoring changes -- only where the bytes
come from.

Sealing matters as much as substituting: `install()` also clears the FSR_*
credentials out of the process env, so a tool that resolves its client by some
path this module does not know about gets *nothing* rather than a live box.
An offline run that quietly reached an appliance would be worse than no
offline mode, because the number would look trustworthy.

Not covered by the sim client: record reads (`/api/3/<module>`). Those return
an empty-but-ok envelope. A fixture that depends on reading real records is
not offline-ready yet, and says so by scoring low -- see `FixtureBox` in the
connector repo for the bundle format that would fill this in.
"""
from __future__ import annotations

import os
import sys
import types
from typing import Any

#: env vars that could carry a live target into the run.
_SEALED = (
    "FSR_BASE_URL", "FSR_API_KEY", "FSR_USERNAME", "FSR_PASSWORD",
    "FSR_PORT", "FSR_INSTANCE_LABEL",
)


def enabled() -> bool:
    """True when the caller asked for an offline run."""
    return os.environ.get("EVAL_OFFLINE", "").strip().lower() in (
        "1", "true", "yes", "on")


def install() -> dict[str, Any]:
    """Point every live seam at the simulated client and seal the env.

    Idempotent: safe to call once per run, or per test. Returns the modules it
    displaced, for `uninstall()`.
    """
    from fsr_playbooks.mcp_server import _sim_client as sc
    from fsr_playbooks.mcp_server import _shared, tools_execution as te

    for key in _SEALED:
        os.environ.pop(key, None)

    env_mod = types.ModuleType("probes._env")
    # Carry the real module's other attributes across. A bare stub would break
    # any caller reaching for `_load_dotenv` / `EnvConfig` -- offline mode
    # should remove the box, not the module.
    try:
        import probes._env as _real
        for attr in dir(_real):
            if not attr.startswith("__"):
                setattr(env_mod, attr, getattr(_real, attr))
    except Exception:  # noqa: BLE001 - probes may not be importable at all
        pass
    env_mod.get_client = sc.get_client      # type: ignore[attr-defined]
    env_mod.get_config = sc.get_config      # type: ignore[attr-defined]
    probes_mod = types.ModuleType("probes")
    probes_mod._env = env_mod               # type: ignore[attr-defined]
    saved = {"probes": sys.modules.get("probes"),
             "probes._env": sys.modules.get("probes._env")}
    sys.modules["probes"] = probes_mod
    sys.modules["probes._env"] = env_mod

    # A client cached from an earlier live call would outlive the swap -- the
    # exact shape of "the flag was set and nothing happened".
    _shared._LIVE_CLIENT_CACHE.pop("client", None)
    te._CONFIGURED_CACHE["rows"] = None
    te._CONFIGURED_CACHE["ts"] = 0.0
    return saved


def uninstall(saved: dict[str, Any]) -> None:
    """Undo one `install()`, restoring the module objects it displaced.

    A run does not need this -- the process exits. Tests do: the swapped-in
    `probes._env` lives in `sys.modules` for the rest of the session, and the
    offline-gate tests assert on the REAL module's `is_live()`. Leaving the
    stub behind made an unrelated test fail depending on order.
    """
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod
    from fsr_playbooks.mcp_server import _shared
    _shared._LIVE_CLIENT_CACHE.pop("client", None)


def active_client_name() -> str:
    """Type name of the client the tools would use right now.

    Reported into the matrix so a run states which substrate produced it
    instead of leaving the reader to infer it from timings.
    """
    from fsr_playbooks.mcp_server import _shared
    client: Any = _shared._live_client()
    return type(client).__name__ if client is not None else "none"

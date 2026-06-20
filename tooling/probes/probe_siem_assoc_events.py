"""Ad-hoc probe: why does get_associated_events_new 400 for incident 17?

Tries several param shapes against the live FortiSIEM connector to pin the
exact cause behind session sess-2avs5bgw's repeated 400s, and to discover what
shape DOES work (so the wrapper can coerce to it).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

from probes._env import get_config  # noqa: E402
from fsr_playbooks.mcp_server.tools_execution import run_op  # noqa: E402


def show(label, res):
    if isinstance(res, dict):
        ok = res.get("ok")
        status = res.get("status") or res.get("code")
        msg = res.get("message") or res.get("error")
        data = res.get("data")
        n = None
        if isinstance(data, list):
            n = len(data)
        elif isinstance(data, dict):
            for k in ("samples", "events", "data", "result", "records"):
                if isinstance(data.get(k), list):
                    n = f"{k}={len(data[k])}"
                    break
        print(f"\n### {label}\n  ok={ok} status={status} rows={n}")
        if msg:
            print("  msg:", str(msg)[:300])
        if ok and data is not None:
            print("  data sample:", json.dumps(data, default=str)[:500])
    else:
        print(f"\n### {label}\n  (non-dict) {str(res)[:300]}")


cfg = get_config()
print("live:", cfg.is_live(), "base:", cfg.base_url)

# A couple candidate incident ids: the SIEM incidentId from the session (17),
# and the related mail incident (7) seen in alert sourcedata.
trials = [
    ("incident_id=17 perPage=50 (session repro)", {"incident_id": "17", "perPage": 50}),
    ("incident_id=17 only", {"incident_id": "17"}),
    ("incident_id=17 int", {"incident_id": 17}),
    ("incident_id=17 perPage=10 (schema default)", {"incident_id": "17", "perPage": 10}),
    ("incident_id=7 perPage=50", {"incident_id": "7", "perPage": 50}),
]

# add a windowed variant using the incident's firstSeen/lastSeen epoch range
import datetime as _dt
# firstSeen 1776353025, lastSeen 1777043985 from the alert records
fs = _dt.datetime.fromtimestamp(1776353025, _dt.timezone.utc)
ls = _dt.datetime.fromtimestamp(1777043985, _dt.timezone.utc)
# clamp to <=24h window ending at lastSeen
fs24 = ls - _dt.timedelta(hours=23)
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
trials.append((
    "incident_id=17 +24h window",
    {"incident_id": "17", "perPage": 50, "timeFrom": iso(fs24), "timeTo": iso(ls)},
))

for label, params in trials:
    try:
        res = run_op("fortinet-fortisiem", "get_associated_events_new", params, confirm=True)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "message": f"EXC {e!r}"}
    show(label, res)

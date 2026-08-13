"""A record-table cassette backend -- a fake FortiSOAR that actually queries.

WHY THIS EXISTS
---------------
The URL-substring cassette in `local_turn.py` answers one canned body per URL
fragment. That is enough for a persona lookup and a single mounted record, and
it is NOT enough for any question about RELATED records, because every such
question is a filter:

    "steps on this device"          -> ztpfDevices.uuid == <uuid>
    "steps with no run group"       -> ztpfRunGroups IS NULL
    "the latest run group"          -> sort by createDate, take one

A substring rule cannot tell those apart -- it returns the same rows for all
three. A fixture that answers "pending steps" with a completed step does not
merely fail to catch a defect, it MANUFACTURES one: the model reads the rows,
sees they contradict the question, and either flails or narrates something
false. That failure would be graded against the model.

So this serves a real record table instead: the same rows the box has, with the
filter/sort/limit semantics the connector's query path actually uses. `filters`
that mean "no run group" return exactly the two ungrouped steps, and nothing
else.

WHAT IT IS NOT
--------------
Not FortiSOAR. It implements the read surface the assistant reaches through --
`GET /api/3/<module>`, `GET /api/3/<module>/<uuid>`, `POST /api/query/<module>`
-- and refuses everything else LOUDLY (`599`), because the whole value here is
that an unanswered read is visible rather than silently empty. Writes are not
served at all: a write must stop at the approval gate, and a fixture box that
accepted one would hide exactly that.

WHERE IT LIVES
--------------
This started life in the connector's `scripts/fixture_box.py`, where only the
connector's own scenario harness could reach it. It lives here now because the
framework's `--offline` eval mode needs it: `_sim_client` serves the three
integration endpoints and answers every record read with `{"data": []}`, so an
investigation fixture ran twelve reads and learned nothing -- a harness gap that
scored as an agent result. Binding a bundle (`_sim_client.bind_box`) is the only
way `--offline` means for the record surface what it already means for execute.

Binding is OPT-IN. With no bundle bound, `_sim_client` behaves byte-for-byte as
before.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                      r"[0-9a-f]{4}-[0-9a-f]{12}", re.I)


class FixtureBoxError(RuntimeError):
    """The bundle is malformed -- a build-time error, never a turn outcome."""


#: Where a bare bundle name resolves. The packaged dir is the default so a
#: bundle ships with the wheel and a fresh checkout can run offline with no
#: setup; `FSR_FIXTURE_BUNDLE_ROOT` points at a checkout-local dir (the
#: connector's `scripts/eval_fixtures/ztpf`, say) without a copy.
BUNDLE_ROOT = Path(__file__).parent / "fixture_bundles"


def _roots(root: Path | None) -> list[Path]:
    if root is not None:
        return [Path(root)]
    out = []
    env = os.environ.get("FSR_FIXTURE_BUNDLE_ROOT", "").strip()
    if env:
        out += [Path(p) for p in env.split(os.pathsep) if p.strip()]
    return out + [BUNDLE_ROOT]


def load_bundle(name_or_path: str, *, root: Path | None = None,
                _depth: int = 0) -> dict:
    """Load a fixture bundle by bare name (`soc_invest_surface`) or path."""
    roots = _roots(root)
    fname = (name_or_path if name_or_path.endswith(".json")
             else f"{name_or_path}.json")
    cands = [Path(name_or_path)] + [r / fname for r in roots]
    for cand in cands:
        if cand.exists():
            p = cand
            break
    else:
        raise FixtureBoxError(
            f"no fixture bundle {name_or_path!r} (looked at "
            + ", ".join(str(c) for c in cands) + ")")
    bundle = json.loads(p.read_text())

    # `extends` lets a variant re-present the SAME captured box under a
    # different persona substrate, or with house rules layered on, without a
    # second copy of the capture. A copy would drift, and a drifted fixture
    # reads as a model result.
    parent = bundle.pop("extends", None)
    if parent:
        if _depth > 4:
            raise FixtureBoxError(f"{p}: `extends` chain is too deep / cyclic")
        base = load_bundle(parent, root=root, _depth=_depth + 1)
        merged = dict(base)
        merged.update({k: v for k, v in bundle.items() if k != "modules"})
        mods = dict(base.get("modules") or {})
        mods.update(bundle.get("modules") or {})
        merged["modules"] = mods
        bundle = merged

    if not isinstance(bundle.get("modules"), dict):
        raise FixtureBoxError(f"{p}: bundle has no `modules` map")

    # A module row written as `{"$file": "alert_c2_exfil"}` is loaded from the
    # standalone triage fixture instead of being pasted in. The alert/incident
    # captures are already mounted BY FILE as the drawer record (`record:` in a
    # scenario spec); copying them into a bundle so the TABLE can answer too
    # would leave the same record living in two places -- and "mounting a copy
    # is how a fixture starts lying about what the box holds" is the exact
    # hazard the mount path warns about. One file, both roles.
    for mod, rows in bundle["modules"].items():
        if not isinstance(rows, list):
            continue
        bundle["modules"][mod] = [
            _load_record_file(r["$file"], p)
            if isinstance(r, dict) and set(r) == {"$file"} else r
            for r in rows
        ]
    return bundle


def _record_roots() -> list[Path]:
    """Where a `{"$file": ...}` row may be found besides beside the bundle.

    In the connector this was one hardcoded path to its triage fixtures. Here it
    is `FSR_FIXTURE_RECORD_ROOT` (os.pathsep-separated), so the same bundle can
    reference the connector's captured alert/incident records from a checkout
    without either repo copying the other's fixtures -- a copy is how a fixture
    starts lying about what the box holds.

    `FSR_CONNECTOR_REPO` is honored too, and that matters more than it looks:
    it is the var the eval harness ALREADY sets to find the triage tools, and
    an investigation row needs both. Deriving the second from the first is the
    difference between a bundle assertion that runs on a normal dev machine and
    one that quietly skips -- a gate selecting zero files looks exactly like a
    passing one.
    """
    env = os.environ.get("FSR_FIXTURE_RECORD_ROOT", "").strip()
    roots = [Path(p) for p in env.split(os.pathsep) if p.strip()] if env else []
    repo = os.environ.get("FSR_CONNECTOR_REPO", "").strip()
    if repo:
        # The repo root and the connector package dir are both natural things
        # to point at; accept either rather than making the caller be right.
        roots += [Path(repo) / sub / "fsr_soc_triage" / "tests" / "fixtures"
                  / "triage" for sub in ("connector-fsr-soc-assistant", ".")]
    return roots


def _load_record_file(name: str, bundle_path: Path) -> dict:
    """Resolve a `{"$file": ...}` row: bundle-relative first, then the extra
    record roots."""
    cands = [bundle_path.parent / name, bundle_path.parent / f"{name}.json"]
    for r in _record_roots():
        cands += [r / name, r / f"{name}.json"]
    for cand in cands:
        if cand.exists():
            rec = json.loads(cand.read_text())
            if not isinstance(rec, dict):
                raise FixtureBoxError(f"{cand}: expected one record object")
            return rec
    raise FixtureBoxError(
        f"{bundle_path}: no record file {name!r} (looked at "
        + ", ".join(str(c) for c in cands)
        + "; set FSR_FIXTURE_RECORD_ROOT to add a search root)")


# --------------------------------------------------------------------------
# Field access + condition evaluation
# --------------------------------------------------------------------------
def _get_path(rec: Any, field: str) -> Any:
    """`ztpfDevices.uuid` -> rec["ztpfDevices"]["uuid"], `None` if any hop is
    missing. Picklists are followed the way the query API does: a bare
    `status` compared against a string matches its `itemValue`."""
    cur = rec
    for part in field.split("."):
        if isinstance(cur, list):
            # A to-many hop: collect, so `ztpfDevices.uuid` works whether the
            # relationship came back as one object or a list of them.
            cur = [(_get_path(i, part) if isinstance(i, (dict, list)) else None)
                   for i in cur]
            cur = [v for v in cur if v is not None]
            continue
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _is_empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _scalarize(v: Any) -> Any:
    """Compare against the value a human (and the query API) means: a picklist
    by its display value, a relationship by its iri."""
    if isinstance(v, dict):
        for k in ("itemValue", "@id", "uuid", "name"):
            if v.get(k) is not None:
                return v[k]
    return v


def _match(rec: dict, cond: dict) -> bool:
    field = cond.get("field") or cond.get("key") or ""
    op = (cond.get("operator") or cond.get("op") or "eq").lower()
    want = cond.get("value")
    got = _get_path(rec, field)

    if op == "isnull":
        return _is_empty(got) is bool(want)
    if _is_empty(got) and op in ("eq", "in", "contains"):
        # An absent field never equals a wanted value. Explicit, because the
        # `None == None` case would otherwise make "no run group" match a
        # filter for a SPECIFIC run group.
        return False

    cand = [_scalarize(g) for g in (got if isinstance(got, list) else [got])]
    if op in ("eq", "="):
        return any(str(cv) == str(want) for cv in cand)
    if op in ("neq", "ne", "!="):
        return all(str(cv) != str(want) for cv in cand)
    if op == "in":
        wants = {str(w) for w in (want if isinstance(want, list) else [want])}
        return any(str(cv) in wants for cv in cand)
    if op in ("contains", "like"):
        return any(str(want).lower() in str(cv).lower() for cv in cand)
    if op in ("gt", "gte", "lt", "lte"):
        try:
            fns = {"gt": lambda a, b: a > b, "gte": lambda a, b: a >= b,
                   "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b}
            rhs = float(str(want))
            return any(fns[op](float(str(cv)), rhs) for cv in cand)
        except (TypeError, ValueError):
            return False
    # An operator we do not implement must not silently pass everything --
    # that would be the substring cassette's failure mode wearing a filter.
    raise FixtureBoxError(f"fixture box does not implement operator {op!r}")


def _match_body(rec: dict, body: dict) -> bool:
    conds = body.get("filters") or []
    if not conds:
        return True
    logic = (body.get("logic") or "AND").upper()
    results = []
    for c in conds:
        if isinstance(c, dict) and ("filters" in c or "logic" in c):
            results.append(_match_body(rec, c))
        elif isinstance(c, dict):
            results.append(_match(rec, c))
    return all(results) if logic == "AND" else any(results)


def _qs_conditions(query: str) -> list[dict]:
    """The field filters carried on a GET query string, as `_match` conditions.

    crudhub takes plain `?<field>=<value>` equality filters on a collection read,
    and the persona resolver's direct lookup is exactly that
    (`?scopeModule=<module>&$limit=1`). A box that ignored them would hand back
    whichever row sorts first -- the same wrong-persona failure the `keys`
    handler already guards against, one URL shape over.

    `$`-prefixed params are crudhub controls (`$limit`, `$search`,
    `$relationships`), not fields, and are handled by the caller.
    """
    conds: list[dict] = []
    for part in query.split("&"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if not k or k.startswith("$"):
            continue
        field = unquote(k)
        if "[" in field:
            # A structured param (`sort[0][field]`, `filters[0][operator]`) is
            # not an equality filter. Treating it as one would match nothing and
            # return a confidently empty page -- the silent-wrong-answer failure
            # this box exists to make impossible.
            raise FixtureBoxError(
                f"fixture box does not implement query param {field!r}")
        conds.append({"field": field, "operator": "eq", "value": unquote(v)})
    return conds


def _search_text(rec: dict, q: str) -> bool:
    return q.lower() in json.dumps(rec, default=str).lower()


def _sort(rows: list[dict], sort: Any) -> list[dict]:
    if not sort:
        return rows
    specs = sort if isinstance(sort, list) else [sort]
    for spec in reversed(specs):
        if isinstance(spec, dict):
            field = spec.get("field")
            desc = str(spec.get("direction", "ASC")).upper() == "DESC"
        else:
            field, desc = str(spec), False
            if field.startswith("-"):
                field, desc = field[1:], True
        if not field:
            continue

        def key(r: dict, _f: str = str(field)) -> tuple:
            v = _scalarize(_get_path(r, _f))
            return (v is None, str(v) if not isinstance(v, (int, float)) else v)

        def str_key(r: dict, _f: str = str(field)) -> str:
            return str(_scalarize(_get_path(r, _f)))

        try:
            rows = sorted(rows, key=key, reverse=desc)
        except TypeError:
            # Mixed numeric/string values in one column: fall back to a total
            # order rather than dropping the sort the caller asked for.
            rows = sorted(rows, key=str_key, reverse=desc)
    return rows


# --------------------------------------------------------------------------
# The persona substrate + learned house rules
# --------------------------------------------------------------------------
PERSONA_MODULE = "assistant_personas"
SKILL_MODULE = "assistant_skills"


def _personas_as_module_rows(personas: dict[str, dict]) -> list[dict]:
    """The bundle's captured Key Store personas, re-expressed as
    `assistant_personas` module records.

    Uses the connector's OWN serializer (`profile_to_module_record`) rather than
    re-deriving the column names here: the round trip
    `parse_persona_module_record(profile_to_module_record(p)) == p` is a property
    the connector's tests already hold, so a persona served through the module
    path resolves to the same `Profile` the Key Store path resolves to. Anything
    less and a module-path failure could be the fixture's spelling rather than
    the code's behavior -- and a second hand-copied column list is exactly the
    parallel-name drift that bites during a rename.

    Requires the connector package importable (the harness bootstrap does that);
    a failure here is a build-time error, never a turn outcome.
    """
    try:
        from fsr_soc_triage.profiles import (  # noqa: PLC0415
            parse_profile_record,
            profile_to_module_record,
        )
    except Exception as exc:  # noqa: BLE001
        raise FixtureBoxError(
            "persona_source=module needs the connector package importable "
            f"(fsr_soc_triage.profiles): {exc}") from exc

    rows: list[dict] = []
    for key, rec in (personas or {}).items():
        module = str(rec.get("key") or key).split(":", 1)[-1]
        prof = parse_profile_record(rec, module)
        if prof is None:
            raise FixtureBoxError(
                f"bundle persona {key!r} does not parse as a Profile; a fixture "
                "that silently drops a persona serves the wrong assistant")
        row = profile_to_module_record(prof)
        row.setdefault("uuid", f"persona-{module}")
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# The box
# --------------------------------------------------------------------------
class _PlaybooksAPI:
    """The slice of pyfsr's typed `client.playbooks` that discovery uses.

    Without it, `list_module_playbooks` returns `no_playbooks_api` and the
    whole "what can I run here / run it" arc is unreachable offline. That is
    not a hypothetical: the first offline drive of "run the pending steps"
    ended with the agent unable to discover a playbook name and (correctly)
    refusing to invent one -- a harness gap wearing the costume of a model
    result.

    `find` honors `active` and `trigger_type` because discovery depends on
    both: a deactivated playbook is absent from the real Execute menu, and
    offering one is an offer that cannot be honored.
    """

    def __init__(self, rows: list[dict]):
        self._rows = rows

    def find(self, *, trigger_type: str | None = None,
             relationships: bool = False, limit: int = 100,
             active: bool | None = None, **_kw: Any) -> list[dict]:
        rows = self._rows
        if active is not None:
            rows = [r for r in rows if bool(r.get("isActive")) is bool(active)]
        if trigger_type and trigger_type != "manual":
            # Only the manual/record-action surface is captured. Say so rather
            # than returning the manual rows under another trigger's name.
            return []
        return [dict(r) for r in rows[:max(1, int(limit))]]


class FixtureBox:
    """Answers the read surface from an in-memory record table.

    `reads` records every request; `misses` records the ones this box could not
    answer -- same contract as the substring cassette, so the sweep's unserved
    work list covers both backends.
    """

    def __init__(self, bundle: dict):
        self.modules: dict[str, list[dict]] = {
            m: list(rows) for m, rows in (bundle.get("modules") or {}).items()}
        self.personas: dict[str, dict] = bundle.get("personas") or {}
        self.playbooks = _PlaybooksAPI(bundle.get("playbooks") or [])
        self.reads: list[str] = []
        self.misses: list[str] = []

        # Which persona substrate this box presents. The 8.0 native path reads
        # the `assistant_personas` MODULE first and only then falls back to the
        # Key Store; a box that serves `keys` alone leaves the native path
        # unexercised -- which is exactly how it shipped, unexercised by 100% of
        # offline rows. `both` is the real 8.0 box (module wins); `module`
        # proves the native path resolves on its own, with no fallback to hide
        # behind. `keys` (the default) keeps every existing row on the legacy
        # path it was written against.
        self.persona_source: str = str(
            bundle.get("persona_source") or "keys").lower()
        if self.persona_source not in ("keys", "module", "both"):
            raise FixtureBoxError(
                "persona_source must be keys|module|both, not "
                f"{self.persona_source!r}")
        if self.persona_source in ("module", "both"):
            self.modules.setdefault(
                PERSONA_MODULE, _personas_as_module_rows(self.personas))

        # Learned house rules. `load_skills` reads `/api/3/assistant_skills`
        # unfiltered and fails open on anything but a 200, so an unserved module
        # and a feature that did nothing are indistinguishable from the turn's
        # side. Only an opted-in bundle serves it, so an existing row's behavior
        # is unchanged.
        skills = bundle.get("skills")
        if skills is not None:
            if not isinstance(skills, list):
                raise FixtureBoxError("bundle `skills` must be a list of records")
            self.modules.setdefault(SKILL_MODULE, [dict(s) for s in skills])

    # -- helpers ---------------------------------------------------------
    def keys_body(self, key: str | None = None) -> dict:
        """`/api/3/keys` as the persona resolver expects it.

        The `key=` filter is HONORED, and that is not a detail. The resolver's
        direct lookup is `?key=fsr_assistant_profile:<module>&$limit=1`; a
        fixture that ignores the filter and returns the whole key list hands
        back whichever persona happens to sort first, and the turn then runs
        as the wrong assistant with the wrong tool slice. Observed exactly
        that: a `ztpf_devices` turn came back as the ZTPF Template Author.

        With no filter the full list is served, which is what the
        `bind_modules` scan fallback reads.
        """
        if self.persona_source == "module":
            # The native path is the ONLY substrate here. An empty key list is
            # the honest answer for a box with no legacy keys, and it is what
            # makes a module-path failure show up as a failure instead of being
            # papered over by the Key Store fallback.
            return {"hydra:member": [], "hydra:totalItems": 0}
        members = [dict(p) for p in self.personas.values()]
        if key:
            members = [m for m in members if m.get("key") == key]
        return {"hydra:member": members, "hydra:totalItems": len(members)}

    def record(self, module: str, uuid: str) -> dict | None:
        for r in self.modules.get(module, []):
            if r.get("uuid") == uuid or str(r.get("id")) == str(uuid):
                return r
        return None

    def _collection(self, module: str, *, body: dict | None = None,
                    q: str = "", limit: int = 30,
                    sort: Any = None) -> dict | None:
        rows = self.modules.get(module)
        if rows is None:
            return None
        out = [r for r in rows if (not body or _match_body(r, body))
               and (not q or _search_text(r, q))]
        out = _sort(out, sort)
        total = len(out)
        return {"hydra:member": out[:max(1, int(limit))],
                "hydra:totalItems": total}

    # -- the HTTP-ish surface -------------------------------------------
    def get(self, url: str) -> tuple[int, dict]:
        self.reads.append(url)
        path = url.split("?", 1)[0]
        query = url.split("?", 1)[1] if "?" in url else ""

        if "/api/3/keys" in path:
            m = re.search(r"(?:^|[?&])key=([^&]+)", query)
            return 200, self.keys_body(unquote(m.group(1)) if m else None)

        m = re.search(r"/api/3/([a-zA-Z0-9_]+)(?:/([^/]+))?/?$", path)
        if not m:
            self.misses.append(url)
            return 404, {"hydra:member": [], "hydra:totalItems": 0}
        module, ident = m.group(1), m.group(2)

        if ident:
            rec = self.record(module, ident)
            if rec is None:
                self.misses.append(url)
                return 404, {"message": f"no {module} record {ident}"}
            return 200, rec

        if module not in self.modules:
            self.misses.append(url)
            return 404, {"hydra:member": [], "hydra:totalItems": 0}
        qs = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
        conds = _qs_conditions(query)
        body = self._collection(module, q=unquote(qs.get("$search", "")),
                                limit=int(qs.get("$limit") or 30),
                                body={"filters": conds} if conds else None)
        return 200, (body or {"hydra:member": [], "hydra:totalItems": 0})

    def post(self, url: str, json_body: dict | None = None) -> tuple[int, dict]:
        self.reads.append(f"POST {url}")
        path = url.split("?", 1)[0]
        qs = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&")
                  if "=" in p) if "?" in url else {}
        m = re.search(r"/api/query/([a-zA-Z0-9_]+)", path)
        if not m:
            # A POST that is not a query is a WRITE. Refusing it loudly is the
            # point: a write has to stop at the approval gate, and a box that
            # accepted one would hide the gate not firing.
            self.misses.append(f"POST {url}")
            return 599, {"message": "fixture box serves reads only; this POST "
                                    "looks like a write and was not served"}
        module = m.group(1)
        if module not in self.modules:
            self.misses.append(f"POST {url}")
            return 404, {"hydra:member": [], "hydra:totalItems": 0}
        body = json_body or {}
        return 200, (self._collection(
            module, body=body, limit=int(qs.get("$limit") or 30),
            sort=body.get("sort")) or {"hydra:member": [], "hydra:totalItems": 0})

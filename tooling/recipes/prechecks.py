"""Recipe pre-emission prechecks (building blocks for the Runs rung).

A recipe that compiles is not a recipe that runs. Each function below
catches one silent-failure surface that today only surfaces at runtime
on the FSR appliance:

- `check_connector_installed`  — recipe targets a connector that isn't
  installed on this FSR. Today: recipe ships, first connector step
  fails with "configuration not found". Now: fail at generation time
  with a "solution pack X needed" message.

- `check_picklist_value`       — `{{ 'PL' | picklist('value') }}` won't
  resolve on this FSR (picklist missing or value not in the picklist).
  Today: recipe emits the unresolved IRI as a `{{…}}` placeholder.
  Now: surface the failure plus close-match suggestions.

Each function returns a `PrecheckResult` with a uniform shape so the CLI
and the MCP tool render the same way.

Designed to be optional — recipes can still be generated `--skip-prechecks`
when the user is offline or hitting a different appliance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PrecheckResult:
    ok: bool
    code: str            # e.g. "connector_not_installed"
    message: str
    suggestions: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "suggestions": self.suggestions,
            "detail": self.detail,
        }


def check_connector_installed(
    client: Any, name: str, version: str | None = None
) -> PrecheckResult:
    """GET /api/integration/connectors/?name=… on the live FSR.

    `client` must be a live pyfsr-style client with `.get(path, params=…)`.
    Returns ok=True when the connector (any version, or the requested
    version) is installed.

    On failure, suggestions list contains close-match connector names
    drawn from the live appliance's catalog so the user knows what *is*
    installed.
    """
    try:
        resp = client.get(
            "/api/integration/connectors/",
            # NB: the integration API is Django-REST — it paginates on
            # `page_size`/`page` (default 30) and returns rows under `data`,
            # NOT the crudhub's `$limit`/`hydra:member`. Passing `$limit` here
            # silently caps results at 30.
            params={"name": name, "page_size": 1000},
        )
    except Exception as exc:  # noqa: BLE001
        return PrecheckResult(
            ok=False,
            code="connector_check_failed",
            message=f"could not reach FSR to verify connector {name!r}: {exc}",
        )
    rows = (resp or {}).get("data") or (resp or {}).get("hydra:member") or []
    if not rows:
        # Try a broader catalog scan for close matches.
        suggestions: list[str] = []
        try:
            broad = client.get(
                "/api/integration/connectors/", params={"page_size": 1000}
            )
            installed = [
                (r.get("name") or "")
                for r in ((broad or {}).get("data") or (broad or {}).get("hydra:member") or [])
            ]
            needle = name.lower().replace("-", "").replace("_", "")
            suggestions = sorted({
                n for n in installed
                if needle in n.lower().replace("-", "").replace("_", "")
                or n.lower().replace("-", "").replace("_", "") in needle
            })[:5]
        except Exception:
            pass
        return PrecheckResult(
            ok=False,
            code="connector_not_installed",
            message=(
                f"connector {name!r} is not installed on this FSR. "
                "Install the corresponding solution pack or add the "
                "connector via Content Hub before running this recipe."
            ),
            suggestions=suggestions,
        )
    if version:
        versions_seen = sorted({r.get("version") for r in rows if r.get("version")})
        if version not in versions_seen:
            return PrecheckResult(
                ok=False,
                code="connector_version_mismatch",
                message=(
                    f"connector {name!r} is installed but version {version!r} "
                    f"is not present (have: {', '.join(versions_seen) or 'none'})."
                ),
                suggestions=versions_seen,
                detail={"installed_versions": versions_seen},
            )
    return PrecheckResult(
        ok=True,
        code="connector_installed",
        message=f"connector {name!r} is installed",
        detail={"rows": len(rows)},
    )


def check_picklist_value(
    client: Any, picklist_name: str, value: str
) -> PrecheckResult:
    """Resolve a friendly value against a picklist on the live FSR.

    Returns ok=True if the value is a valid `itemValue` for the picklist.
    On miss, suggestions contain prefix/substring matches drawn from the
    live picklist's items.
    """
    try:
        from picklists import resolve_iri, picklist_values  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return PrecheckResult(
            ok=False,
            code="picklist_helper_unavailable",
            message=f"picklist helper not importable: {exc}",
        )
    iri = resolve_iri(client, value, picklist_name=picklist_name)
    if iri:
        return PrecheckResult(
            ok=True,
            code="picklist_value_resolved",
            message=f"{picklist_name!r}/{value!r} resolves to {iri}",
            detail={"iri": iri},
        )
    items = picklist_values(client, picklist_name) or []
    valid = [it.get("itemValue") for it in items if it.get("itemValue")]
    if not valid:
        return PrecheckResult(
            ok=False,
            code="picklist_not_found",
            message=(
                f"picklist {picklist_name!r} has no items (or does not "
                "exist) on this FSR. Create it under Settings → Picklists "
                "before running this recipe."
            ),
        )
    import difflib
    vl = value.lower()
    cheap = [
        v for v in valid
        if v and (v.lower().startswith(vl) or vl in v.lower() or v.lower() in vl)
    ]
    fuzzy = difflib.get_close_matches(value, valid, n=5, cutoff=0.4)
    # Token-overlap fallback: catches "In Progress" → "Investigating" (shared "in").
    tokens = {t for t in re.split(r"\W+", vl) if t}
    token_hits = [
        v for v in valid
        if v and tokens & {t for t in re.split(r"\W+", v.lower()) if t}
    ]
    # First-token startswith catches "In Progress" → "Investigating".
    first_tok = next(iter(re.split(r"\W+", vl)), "")
    first_hits = [
        v for v in valid
        if first_tok and v.lower().startswith(first_tok)
    ] if first_tok else []
    seen: set[str] = set()
    suggestions: list[str] = []
    for s in cheap + fuzzy + first_hits + token_hits:
        if s and s not in seen:
            suggestions.append(s)
            seen.add(s)
        if len(suggestions) >= 5:
            break
    # Fallback: when no fuzzy match found, surface the top valid values
    # so the agent has *something* to work with.
    if not suggestions:
        suggestions = valid[:5]
    return PrecheckResult(
        ok=False,
        code="picklist_value_invalid",
        message=(
            f"{value!r} is not a valid value for picklist {picklist_name!r}."
        ),
        suggestions=suggestions,
        detail={"valid_values": valid},
    )


def run_recipe_prechecks(
    client: Any,
    *,
    connector_name: str,
    connector_version: str | None = None,
    picklist_values: list[tuple[str, str]] | None = None,
) -> list[PrecheckResult]:
    """Run the standard recipe-emission prechecks in order.

    Order matters: if the connector isn't installed, picklist checks
    are skipped (would-be cascade failures add noise without value).
    """
    results: list[PrecheckResult] = []
    conn_check = check_connector_installed(
        client, connector_name, connector_version
    )
    results.append(conn_check)
    if conn_check.ok and picklist_values:
        for pl_name, val in picklist_values:
            results.append(check_picklist_value(client, pl_name, val))
    return results

"""Sample-data sidecar for `manual_input` steps (and future use).

Authors test downstream Jinja against synthetic answers without running
the playbook. The data lives in a YAML comment block — same pattern as
`# fsrpb:layout` — so it never reaches FSR on push but survives parse →
round-trip writes.

Shape:

    # fsrpb:samples
    # {
    #   "<playbook name>": {
    #     "<step id>": { "input": { "ip_address": "1.2.3.4", "reason": "test" } }
    #   }
    # }
    # fsrpb:samples-end

Per-step values are merged into `vars.steps.<step_id>` before rendering.
For `manual_input` the convention is `{input: {<name>: <value>}}` —
matching the runtime shape FSR exposes — but the merge is generic so
later step types (e.g. fake connector outputs) can drop into the same
block without code changes.
"""
from __future__ import annotations

import json
import re
from typing import Any

_HEAD_RE = re.compile(r"(?m)^\s*#\s*fsrpb:samples\s*\n")
_END_RE = re.compile(r"#\s*fsrpb:samples-end\s*\n?")


def extract_samples_block(text: str) -> tuple[dict[str, dict[str, Any]], str]:
    """Pull the samples block out of the YAML if present.

    Returns `(samples_map, text_without_block)`. Missing/malformed →
    `({}, text)` so callers don't have to special-case the empty path.
    """
    head = _HEAD_RE.search(text)
    if not head:
        return {}, text
    before = text[: head.start()]
    rest = text[head.end():]
    end = _END_RE.search(rest)
    if not end:
        return {}, text
    block = rest[: end.start()]
    after = rest[end.end():]
    json_lines: list[str] = []
    for ln in block.splitlines():
        s = ln.lstrip()
        if not s.startswith("#"):
            return {}, text
        json_lines.append(s[1:].lstrip())
    try:
        data = json.loads("\n".join(json_lines))
        if not isinstance(data, dict):
            return {}, text
    except Exception:
        return {}, text
    return data, before + after


def emit_samples_block(samples: dict[str, dict[str, Any]]) -> str:
    """Inverse of `extract_samples_block`. Empty map → "" so files that
    never had a samples block stay byte-identical on round-trip."""
    if not samples:
        return ""
    body = json.dumps(samples, indent=2, sort_keys=True)
    out = ["# fsrpb:samples"]
    for ln in body.splitlines():
        out.append(f"# {ln}" if ln else "#")
    out.append("# fsrpb:samples-end")
    return "\n".join(out) + "\n"


def append_samples(body: str, samples: dict[str, dict[str, Any]]) -> str:
    """Tack the samples footer onto `body`. No-op on empty map."""
    footer = emit_samples_block(samples)
    if not footer:
        return body
    sep = "" if body.endswith("\n") or not body else "\n"
    return body + sep + footer


def overlay_into_vars(samples_for_playbook: dict[str, Any],
                       vars_ctx: dict[str, Any]) -> dict[str, Any]:
    """Merge `{step_id: {...}}` into `vars_ctx["steps"]`.

    Deep-merge per step so an explicit `vars["steps"][sid][k]` from a
    real run wins over the static sample if the caller already pre-seeded
    it. Returns `vars_ctx` for chaining; mutation is in-place.
    """
    if not samples_for_playbook:
        return vars_ctx
    steps = vars_ctx.setdefault("steps", {})
    for sid, payload in samples_for_playbook.items():
        if not isinstance(payload, dict):
            continue
        existing = steps.get(sid)
        if isinstance(existing, dict):
            _deep_fill(existing, payload)
        else:
            steps[sid] = _deep_copy(payload)
    return vars_ctx


def _deep_fill(dst: dict[str, Any], src: dict[str, Any]) -> None:
    """Recursively setdefault: real values in `dst` win, but missing
    leaves anywhere in `src` get filled in. Lets a sample provide both
    `input.ip_address` and `input.reason` when the runtime only seeded
    `input.ip_address`."""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_fill(dst[k], v)
        else:
            dst.setdefault(k, _deep_copy(v))


def _deep_copy(v: Any) -> Any:
    """Cheap structural copy for the sample payload — keeps the source
    map immutable when callers later mutate the vars context."""
    if isinstance(v, dict):
        return {k: _deep_copy(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_deep_copy(x) for x in v]
    return v

"""The gate round-trip fidelity cannot provide: does AUTHORED yaml produce the
same wire shape the platform itself writes?

Round-trip proves decompile(compile(x)) == x for playbooks that already exist.
It starts from wire JSON, so anything the corpus already gets right -- a
`?$limit=` suffix on the module, say -- is preserved through the cycle and the
gate passes. That says nothing about the shape we emit when a human authors a
step from scratch with the friendly keys.

The `limit` bug lived precisely in that blind spot: `limit: 5000` compiled to
`query.limit` only, the platform ignored it, and every find step silently
truncated to 30 rows. Round-trip was green the whole time, because no corpus
playbook is authored that way.

This gate closes it from the other side: author the friendly form, then assert
the emitted arguments carry the same *structural conventions* the live corpus
uses. Conventions are asserted, not byte equality -- the corpus is 302 find
steps across 1,857 playbooks with wildly different filters, so only the shape
is comparable.

Corpus facts these assertions encode (measured on a live 7.x box, 7,675 steps):
  find_record   302 steps; 301 carry query.sort, 301 query.limit, 215
                __selectFields, and the module suffix `$limit=` appears on
                every step that sets a non-default limit
  relationships expansion is always paired with `$fsr_max_relation_count=` in
                60+ steps
"""
from __future__ import annotations

from fsr_playbooks.compiler import compile_yaml


def _args(result, frag="Find"):
    assert result.ok, [e.to_dict() for e in result.errors]
    wf = result.fsr_json["data"][0]["workflows"][0]
    for s in wf["steps"]:
        if frag in s["name"]:
            return s["arguments"]
    raise AssertionError(f"no step matching {frag!r}")


_AUTHORED = """
collection: T
playbooks:
  - name: P
    steps:
      - name: trigger
        type: start
        next: Find rows
      - name: Find rows
        type: find_record
        module: alerts
        limit: 5000
        logic: AND
        sort:
          - field: createDate
            direction: DESC
        select: [name, status]
        relationships: true
        max_relations: 100
        filters:
          - type: primitive
            field: name
            value: x
            operator: eq
            _operator: eq
"""


def test_authored_find_matches_corpus_conventions(db_path):
    a = _args(compile_yaml(_AUTHORED, db_path))
    mod = a["module"]

    # 1. the limit rides on the module -- the whole point of the bug
    assert "$limit=5000" in mod, f"limit missing from module: {mod}"
    # 2. relationship expansion + its cap, as the corpus always pairs them
    assert "$relationships=true" in mod
    assert "$fsr_max_relation_count=100" in mod
    # 3. exactly one `?`, the rest joined with `&`
    assert mod.count("?") == 1, mod
    assert mod.startswith("alerts?")
    # 4. the query envelope still carries the four keys every corpus step has
    q = a["query"]
    for k in ("sort", "limit", "logic", "filters"):
        assert k in q, f"query missing {k}"
    # 5. a projection implies the flag that makes it survive
    assert q["__selectFields"] == ["name", "status"]
    assert a["checkboxFields"] is True


def test_max_relations_without_relationships_warns(db_path):
    y = _AUTHORED.replace("        relationships: true\n", "")
    r = compile_yaml(y, db_path)
    msgs = " ".join(e.message for e in r.errors)
    assert "max_relations" in msgs and "no effect" in msgs, msgs


def test_default_limit_matches_bare_module(db_path):
    # The corpus does carry `$limit=30` explicitly on some steps, but emitting
    # it for every unremarkable find would churn the module string on playbooks
    # that never asked for a limit. 30 is the platform default either way.
    y = _AUTHORED.replace("limit: 5000", "limit: 30")
    y = y.replace("        relationships: true\n", "")
    y = y.replace("        max_relations: 100\n", "")
    a = _args(compile_yaml(y, db_path))
    assert a["module"] == "alerts"
    assert a["query"]["limit"] == 30

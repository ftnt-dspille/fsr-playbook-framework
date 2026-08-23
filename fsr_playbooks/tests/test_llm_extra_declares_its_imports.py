"""Every third-party module `llm/*.py` imports at MODULE level must be declared.

This is a gate for a defect that already shipped: the FortiAI proxy provider
imports `httpx` at module scope, `httpx` was in nobody's dependency list, and it
rode in on whatever the OpenAI/Anthropic SDKs happened to pull. That is not a
guarantee -- CI installs the declared deps and nothing else, so main went red for
four consecutive runs, and a box installing `fsr_playbooks[mcp]` would have hit
the same ImportError at import time rather than at first use.

An undeclared module-level import is invisible on any machine that happens to
have the package. This test reads the PUBLISHED dist's extras and refuses that.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LLM_DIR = Path(__file__).resolve().parents[1] / "llm"
PYPROJECT = (Path(__file__).resolve().parents[2]
             / "packaging" / "fsr_playbooks" / "pyproject.toml")

#: Distributions whose import name differs from their requirement name.
_IMPORT_TO_DIST = {
    "yaml": "pyyaml",
    "ruamel": "ruamel.yaml",
    "jinja2": "jinja2",
}


def _declared_dists() -> set[str]:
    if sys.version_info >= (3, 11):
        import tomllib
    else:  # pragma: no cover - the 3.10 floor
        import tomli as tomllib  # type: ignore[no-redef]
    data = tomllib.loads(PYPROJECT.read_text())
    proj = data["project"]
    reqs = list(proj.get("dependencies") or [])
    for extra in (proj.get("optional-dependencies") or {}).values():
        reqs += list(extra)
    out = set()
    for r in reqs:
        # "openai>=1.0" -> "openai"; "fsr_playbooks[llm]" -> "fsr_playbooks"
        name = r.split(";")[0].strip()
        for sep in ("[", ">", "<", "=", "!", "~", " "):
            name = name.split(sep)[0]
        out.add(name.strip().lower().replace("_", "-"))
    return out


def _module_level_imports(path: Path) -> set[str]:
    """Top-level import names only.

    A function-scoped import is a deliberate deferral (the provider modules use
    them so an unconfigured backend costs nothing), and deferring is exactly the
    fix when a dependency should stay optional -- so those are not the subject
    of this test.
    """
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_every_module_level_third_party_import_is_declared() -> None:
    declared = _declared_dists()
    stdlib = set(sys.stdlib_module_names)
    first_party = {"fsr_playbooks", "agent", "probes", "evals"}
    undeclared: dict[str, set[str]] = {}
    for path in sorted(LLM_DIR.glob("*.py")):
        for mod in _module_level_imports(path):
            if mod in stdlib or mod in first_party or mod.startswith("_"):
                continue
            dist = _IMPORT_TO_DIST.get(mod, mod).lower().replace("_", "-")
            if dist not in declared:
                undeclared.setdefault(path.name, set()).add(mod)
    assert not undeclared, (
        "module-level imports not declared by the published dist "
        f"({PYPROJECT}): "
        + "; ".join(f"{f}: {sorted(m)}" for f, m in sorted(undeclared.items()))
        + ". Either declare it in the [llm] extra or move the import inside "
          "the function that needs it -- an undeclared module-level import is "
          "invisible on any machine that happens to have the package, and "
          "fails at IMPORT time on one that does not."
    )

# Releasing fsr_playbooks

The published version comes **entirely from the git tag** (hatch-vcs). There is
no version string to bump in any file — the old `fsr_playbooks/__init__.py`
`__version__ = "..."` and `packaging/.../pyproject.toml` version literals are
gone. Tag, push, release. That's it.

## Cut a release

```sh
git tag v0.4.11            # next free version — see "Version floor" below
git push origin v0.4.11
```

Then on GitHub: **Releases → Draft a new release → choose tag `v0.4.11` →
Publish**. The `Publish to PyPI` workflow (`.github/workflows/publish.yml`)
fires on the published release, builds the wheel, and uploads it to PyPI via
Trusted Publishing (OIDC — no stored token).

- The wheel's version is derived from the tag: `v0.4.11` → `0.4.11`. The `v`
  prefix is stripped automatically.
- `workflow_dispatch` (Actions → Run workflow) builds off a branch with no tag
  at HEAD, which yields a **dev** version like `0.4.11.devN+g<sha>`. Useful for a
  dry run; don't publish those to PyPI.

## Version floor

PyPI rejects re-uploading an existing version, and the project's history drifted
once (versions `0.4.9` and `0.4.10` were published from the old hardcoded
`__version__` **without** matching git tags — tags stopped at `v0.4.8`). So the
next tag must clear what's already on PyPI:

> **The first hatch-vcs release must be `v0.4.11` or higher** (PyPI's latest is
> `0.4.10`). Check `https://pypi.org/project/fsr_playbooks/#history` if unsure.

## How the build is wired (for maintainers)

This dist is unusual: its `pyproject.toml` lives at `packaging/fsr_playbooks/`
but the source tree is at the repo root (`../../fsr_playbooks`), because the root
`pyproject.toml` is taken by the dev-only `fsrpb` CLI dist.

- Hatchling forbids `..` in `packages`/`only-include`, so the package is grafted
  in via `[tool.hatch.build.targets.wheel.force-include]`, which lists each
  top-level module and subpackage **explicitly** (force-include can't honour
  `exclude`, which is how `fsr_playbooks/tests/` is kept out of the wheel).
- **If you add a new top-level module or subpackage under `fsr_playbooks/`, add
  it to that force-include manifest**, or it won't ship.
  `fsr_playbooks/tests/test_packaging_manifest_complete.py` guards this — it fails
  if the manifest drifts from the real tree.
- We ship **wheels only**; the `..` source layout cannot produce a correct sdist.

## Two version notes

- **Dev `__version__` reflects whatever is installed.** `__version__` is read
  from installed dist metadata (`importlib.metadata`), which is frozen at install
  time:
  - If a `fsr_playbooks` dist is installed (`pip install -e packaging/fsr_playbooks`
    or the published wheel), it reports that build's version — and an editable
    install can read **stale** until you reinstall.
  - If only the root `fsrpb` dist is installed and no `fsr_playbooks` dist, or the
    tree is a raw checkout with nothing installed, it falls back to
    `0.0.0+unknown`.
  Either way this is dev-only cosmetics; the **published** wheel always carries
  the exact tag version.
- The **root `fsrpb` dist** (`pyproject.toml`, `version = "0.0.1"`) is a dev-only
  CLI shim that is never published to PyPI. Its hardcoded version is irrelevant
  and intentionally left alone.

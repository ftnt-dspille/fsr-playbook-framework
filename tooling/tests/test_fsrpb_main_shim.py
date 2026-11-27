"""The fsrpb console script must find the CLI modules outside a source checkout.

A wheel or git install has no tooling/ directory beside fsrpb_main; the CLI
modules ship as package data of fsrpb_tooling instead.
"""
from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def shim(monkeypatch):
    sys.modules.pop("fsrpb_main", None)
    module = importlib.import_module("fsrpb_main")
    yield module
    sys.modules.pop("fsrpb_main", None)


def test_checkout_tooling_dir_is_used_when_present(shim):
    assert shim._tooling_dir().endswith("tooling")


def test_installed_package_is_used_without_a_checkout(shim, monkeypatch, tmp_path):
    installed = tmp_path / "site" / "fsrpb_tooling"
    installed.mkdir(parents=True)
    (installed / "cli.py").write_text("def main(argv=None):\n    return 0\n")
    monkeypatch.setattr(shim, "_REPO_ROOT", str(tmp_path / "no-checkout"))
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    sys.modules.pop("fsrpb_tooling", None)
    assert shim._tooling_dir() == str(installed)


def test_missing_cli_modules_fail_with_a_message(shim, monkeypatch, tmp_path):
    monkeypatch.setattr(shim, "_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(SystemExit, match="cannot find the CLI modules"):
        shim._tooling_dir()

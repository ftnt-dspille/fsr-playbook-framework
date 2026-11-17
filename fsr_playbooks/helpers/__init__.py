"""Importable helpers for FortiSOAR ``code_snippet`` playbook steps.

These run on the playbook worker (where ``fsr_playbooks`` is installed) and
are imported from a ``code_snippet`` step whose connector config lists
``fsr_playbooks.helpers`` in ``allow_imports``. They are stdlib-only so they
also work under the code-snippet connector's restricted default imports.

Surface is intentionally small: CSV report building and set-diff
reconciliation -- the two pieces a compare-and-report playbook needs before
its notification step. Notification-param helpers live here too once their
connector op shapes are pinned down.
"""
from __future__ import annotations

from .csv_report import build_csv, write_csv
from .reconcile import reconcile

__all__ = ["build_csv", "write_csv", "reconcile"]

"""Suite-wide isolation for `fsr_playbooks/tests/`.

Everything here exists because a test's outcome must not depend on which other
tests ran first. That property is only observable under randomized collection
order (`pytest-randomly`, wired into `make tests-random`), which is exactly why
these leaks survived for so long: in the one fixed order the suite always ran
in, they were invisible.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_approval_grants():
    """Empty the process-global approval-grant table around every test.

    `fsr_playbooks.llm.tools._APPROVAL_GRANTS` is module state keyed by
    (session, tool, op_key) and nothing in the suite cleaned it up, so grants
    accumulated across tests. `test_clear_session_grants_removes_all_grants_for
    _session` counts the table's absolute size, and under a randomized order it
    saw a `('session-1', 'tool_b', ...)` grant left behind by an earlier test
    and read 4 where it asserts 3.

    A dispatch-authorization table that carries over between tests is also the
    worst possible thing to leave dirty: a P2-gating test could pass because
    some earlier test had already granted the approval it means to require.
    """
    from fsr_playbooks.llm import tools as tools_mod

    tools_mod._APPROVAL_GRANTS.clear()
    try:
        yield
    finally:
        tools_mod._APPROVAL_GRANTS.clear()

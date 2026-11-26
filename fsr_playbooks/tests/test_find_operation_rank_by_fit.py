"""`find` ranks ops by fit to a caller holding a name or key, not a record id.

Read from the op's output schema and param types: a search/list op (list-valued
output) outranks a single-record getter that needs an id; ops needing a select,
datetime or payload the caller cannot supply rank behind those it can fill; a
write op never outranks a read.
"""
from fsr_playbooks.mcp_server.tools_discovery import find_operation


def _names(q, limit=40):
    return [m["op_name"] for m in find_operation("servicenow", q, limit=limit)["matches"]]


def test_a_search_op_outranks_an_id_getter():
    names = _names("")
    assert names.index("search_record") < names.index("get_change_request_details")


def test_an_op_needing_a_datetime_ranks_behind_the_ones_a_key_can_fill():
    names = _names("search")
    assert names.index("search_record") < names.index("fetch_incidents")


def test_a_write_op_never_outranks_a_read():
    names = _names("incident")
    assert names.index("get_SIR") < names.index("delete_SIR")


def test_the_cut_to_limit_happens_after_ranking():
    # search_record sorts after 10 alphabetical ops; it must still make a top 6.
    assert "search_record" in _names("record", limit=6)

"""A live turn streams each tool_use twice under one id (empty input first,
full input second). tool_calls must yield one call per id with the full input."""
from fsr_playbooks.harness.frames import tool_calls


def _turn():
    return {"transcript": [
        {"type": "tool_use", "id": "t1", "name": "run_op", "input": {}},
        {"type": "tool_use", "id": "t1", "name": "run_op",
         "input": {"connector": "virustotal", "op": "query_ip", "params": {"ip": "198.51.100.7"}}},
        {"type": "tool_result", "tool_use_id": "t1", "content": "{\"ok\": true}"},
        {"type": "tool_use", "id": "t2", "name": "get_record", "input": {"iri": "/api/3/alerts/x"}},
        {"type": "tool_use", "id": "t2", "name": "get_record", "input": {}},
    ]}


def test_one_call_per_id_in_first_position():
    calls = tool_calls(_turn())
    assert [c.id for c in calls] == ["t1", "t2"]
    assert [c.name for c in calls] == ["run_op", "get_record"]


def test_the_full_input_wins_over_the_empty_copy():
    calls = tool_calls(_turn())
    assert calls[0].args == {"connector": "virustotal", "op": "query_ip", "params": {"ip": "198.51.100.7"}}
    assert calls[0].has_result is True


def test_a_later_empty_copy_does_not_erase_the_input():
    assert tool_calls(_turn())[1].args == {"iri": "/api/3/alerts/x"}


def test_tools_called_counts_one_name_per_call_id():
    from fsr_playbooks.harness.frames import tools_called
    fs = [{"type": "tool_use", "id": "a", "name": "get_record", "input": {}},
          {"type": "tool_use", "id": "a", "name": "get_record", "input": {"iri": "/x"}},
          {"type": "tool_use", "id": "b", "name": "run_op", "input": {}},
          {"type": "tool_use", "id": "b", "name": "run_op", "input": {"op": "q"}}]
    assert tools_called({"transcript": fs}) == ["get_record", "run_op"]


def test_cards_of_type_finds_frame_and_nested_cards():
    from fsr_playbooks.harness.frames import cards_of_type
    fs = [{"type": "choice_card", "id": "c1", "options": []},
          {"type": "card", "card": {"type": "choice_card", "id": "c2"}},
          {"type": "verdict_card", "id": "v1"}]
    assert [c["id"] for c in cards_of_type({"transcript": fs}, "choice_card")] == ["c1", "c2"]

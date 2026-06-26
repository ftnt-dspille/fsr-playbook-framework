"""Test apply_async + for_each.break_loop cleanup during emit.

When apply_async=true on a workflow_reference or connector step, the
compiler should delete for_each.break_loop to prevent conflicts:
- apply_async: fire-and-forget, no loop tracking
- break_loop: requires sync tracking of loop state
These are mutually exclusive.

Covers: emitter.py _emit_step cleanup logic.
"""
from fsr_playbooks.compiler.ir import Collection, Playbook, Step
from fsr_playbooks.compiler.emitter import emit


def test_workflow_reference_apply_async_deletes_break_loop():
    """When workflow_reference has apply_async=True, break_loop should be deleted."""
    pb_target = Playbook(
        name="Target Playbook",
        steps=[
            Step(id="start", type="start", name="Start"),
            Step(id="end", type="stop", name="End"),
        ]
    )

    pb_caller = Playbook(
        name="Caller Playbook",
        steps=[
            Step(id="start", type="start", name="Start"),
            Step(
                id="call",
                type="workflow_reference",
                name="Call Async",
                arguments={
                    "target": "Target Playbook",
                    "apply_async": True,
                },
                for_each={
                    "item": "{{ vars.items }}",
                    "break_loop": "{{ vars.should_break }}",
                }
            ),
            Step(id="end", type="stop", name="End"),
        ]
    )

    collection = Collection(name="Test Collection", playbooks=[pb_target, pb_caller])

    # Manually fill in step_type_uuids (normally done by resolver)
    for pb in collection.playbooks:
        for step in pb.steps:
            if step.type == "start":
                step.step_type_uuid = "cybersponse.abstract_trigger"
            elif step.type == "stop":
                step.step_type_uuid = "Connectors"
            elif step.type == "workflow_reference":
                step.step_type_uuid = "WorkflowReference"

    result = emit(collection)

    # Find the Call Async step
    for wf in result["data"][0]["workflows"]:
        if wf["name"] == "Caller Playbook":
            for step in wf["steps"]:
                if "Call" in step["name"]:
                    for_each = step["arguments"].get("for_each")
                    assert for_each is not None, "for_each should exist"
                    assert "break_loop" not in for_each, (
                        "break_loop should be deleted when apply_async=True"
                    )
                    assert "item" in for_each, "other for_each keys should be preserved"


def test_connector_apply_async_deletes_break_loop():
    """When connector has apply_async=True, break_loop should be deleted."""
    pb = Playbook(
        name="Connector Test",
        steps=[
            Step(id="start", type="start", name="Start"),
            Step(
                id="conn",
                type="connector",
                name="Connector Op",
                arguments={
                    "connector": "SomeConnector",
                    "operation": "some_op",
                    "apply_async": True,
                    "params": {},
                },
                for_each={
                    "item": "{{ vars.items }}",
                    "break_loop": "{{ vars.should_break }}",
                }
            ),
            Step(id="end", type="stop", name="End"),
        ]
    )

    collection = Collection(name="Test", playbooks=[pb])

    # Manually fill in step_type_uuids
    for step in pb.steps:
        if step.type == "start":
            step.step_type_uuid = "cybersponse.abstract_trigger"
        elif step.type == "stop":
            step.step_type_uuid = "Connectors"
        elif step.type == "connector":
            step.step_type_uuid = "Connectors"

    result = emit(collection)

    # Check the connector step
    for wf in result["data"][0]["workflows"]:
        if wf["name"] == "Connector Test":
            for step in wf["steps"]:
                if "Connector" in step["name"]:
                    for_each = step["arguments"].get("for_each")
                    assert for_each is not None, "for_each should exist"
                    assert "break_loop" not in for_each, (
                        "break_loop should be deleted when apply_async=True"
                    )
                    assert "item" in for_each, "other for_each keys should be preserved"


def test_workflow_reference_without_apply_async_keeps_break_loop():
    """When apply_async is False/missing, break_loop should be preserved."""
    pb = Playbook(
        name="Caller No Async",
        steps=[
            Step(id="start", type="start", name="Start"),
            Step(
                id="call",
                type="workflow_reference",
                name="Call Sync",
                arguments={
                    "target": "Target Playbook",
                    "apply_async": False,
                },
                for_each={
                    "item": "{{ vars.items }}",
                    "break_loop": "{{ vars.should_break }}",
                }
            ),
            Step(id="end", type="stop", name="End"),
        ]
    )

    collection = Collection(name="Test", playbooks=[pb])

    # Manually fill in step_type_uuids
    for step in pb.steps:
        if step.type == "start":
            step.step_type_uuid = "cybersponse.abstract_trigger"
        elif step.type == "stop":
            step.step_type_uuid = "Connectors"
        elif step.type == "workflow_reference":
            step.step_type_uuid = "WorkflowReference"

    result = emit(collection)

    # Check the Call Sync step
    for wf in result["data"][0]["workflows"]:
        if wf["name"] == "Caller No Async":
            for step in wf["steps"]:
                if "call" in step["name"].lower():
                    for_each = step["arguments"].get("for_each")
                    assert for_each is not None, "for_each should exist"
                    assert "break_loop" in for_each, (
                        "break_loop should be preserved when apply_async=False"
                    )
                    assert for_each["break_loop"] == "{{ vars.should_break }}"


def test_connector_without_apply_async_keeps_break_loop():
    """When apply_async is False/missing on connector, break_loop should be preserved."""
    pb = Playbook(
        name="Connector Sync",
        steps=[
            Step(id="start", type="start", name="Start"),
            Step(
                id="conn",
                type="connector",
                name="Connector Op",
                arguments={
                    "connector": "SomeConnector",
                    "operation": "some_op",
                    "params": {},
                },
                for_each={
                    "item": "{{ vars.items }}",
                    "break_loop": "{{ vars.should_break }}",
                }
            ),
            Step(id="end", type="stop", name="End"),
        ]
    )

    collection = Collection(name="Test", playbooks=[pb])

    # Manually fill in step_type_uuids
    for step in pb.steps:
        if step.type == "start":
            step.step_type_uuid = "cybersponse.abstract_trigger"
        elif step.type == "stop":
            step.step_type_uuid = "Connectors"
        elif step.type == "connector":
            step.step_type_uuid = "Connectors"

    result = emit(collection)

    # Check the connector step
    for wf in result["data"][0]["workflows"]:
        if wf["name"] == "Connector Sync":
            for step in wf["steps"]:
                if "Connector" in step["name"]:
                    for_each = step["arguments"].get("for_each")
                    assert for_each is not None, "for_each should exist"
                    assert "break_loop" in for_each, (
                        "break_loop should be preserved when apply_async is missing"
                    )
                    assert for_each["break_loop"] == "{{ vars.should_break }}"


def test_apply_async_without_for_each():
    """apply_async=True without for_each should not cause errors."""
    pb = Playbook(
        name="Simple Async",
        steps=[
            Step(id="start", type="start", name="Start"),
            Step(
                id="call",
                type="workflow_reference",
                name="Call Async No Loop",
                arguments={
                    "target": "Target",
                    "apply_async": True,
                }
            ),
            Step(id="end", type="stop", name="End"),
        ]
    )

    collection = Collection(name="Test", playbooks=[pb])

    # Manually fill in step_type_uuids
    for step in pb.steps:
        if step.type == "start":
            step.step_type_uuid = "cybersponse.abstract_trigger"
        elif step.type == "stop":
            step.step_type_uuid = "Connectors"
        elif step.type == "workflow_reference":
            step.step_type_uuid = "WorkflowReference"

    result = emit(collection)

    # Should not raise, and apply_async should still be present
    for wf in result["data"][0]["workflows"]:
        if wf["name"] == "Simple Async":
            for step in wf["steps"]:
                if "async" in step["name"].lower():
                    assert step["arguments"].get("apply_async") is True
                    assert step["arguments"].get("for_each") is None

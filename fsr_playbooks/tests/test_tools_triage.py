

# --------------------------------------------------------------------------
# Relationship fields are called out separately from the flat field list.
#
# The `fields=[...]` hint works -- it took one row from 30 get_record calls to
# 2 tool calls. What it did NOT do is tell the model which entries point at
# other records, so it picked scalars named in the question's own words and
# produced a summary that could not say which run each step belonged to. The
# omission is invisible: the answer reads complete.
# --------------------------------------------------------------------------
def test_relationship_fields_are_detected_by_shape():
    from fsr_playbooks.mcp_server.tools_triage import _relationship_fields

    rows = [{
        "name": "Create Loopback",
        "status": {"itemValue": "Complete"},          # picklist, NOT a relation
        "ztpfRunGroups": {"@id": "/api/3/ztpf_run_groups/abc", "name": "rg-1"},
        "ztpfDevices": [{"@id": "/api/3/ztpf_devices/xyz"}],   # to-many
        "@id": "/api/3/ztpf_device_automation_steps/1",        # own iri
    }]
    assert _relationship_fields(rows) == {"ztpfRunGroups", "ztpfDevices"}


def test_a_picklist_is_never_reported_as_a_relationship():
    """`status` is a value to select, not a record to group by. Reporting it
    would send the model chasing an attribution that does not exist."""
    from fsr_playbooks.mcp_server.tools_triage import _relationship_fields

    assert _relationship_fields(
        [{"status": {"itemValue": "Complete"},
          "severity": {"itemValue": "High", "@id": None}}]) == set()


def test_relationship_detection_survives_junk_rows():
    from fsr_playbooks.mcp_server.tools_triage import _relationship_fields

    assert _relationship_fields([None, "x", {}, []]) == set()

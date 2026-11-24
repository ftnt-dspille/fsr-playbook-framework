# microsoft-graph-api-security - no scenario playbooks

No sample playbooks are staged for this package yet.

The M365 trial scenarios (A-C) exercise the security surface through the
`microsoft-graph_dev` package, whose operations already cover what those
scenarios need (risky-user listing, session revocation, Conditional Access IP
named locations, security-alert comments, mailbox search and bulk delete).
`microsoft-graph-api-security` targets the same Graph security plane with a
different auth/profile (its own subset of incident and alert operations), so a
playbook written against it would duplicate Scenario A or B step-for-step with
only the connector name swapped.

If a scenario later needs an operation that only this package ships, add its
`playbooks/playbooks.yaml` + `build.py` here, mirroring the sibling packages:
fortiaigate-style YAML, `mock_result` on every connector step in the production
`{data, status, message, operation}` envelope, and the build stamping the
collection name with the version from this package's `info.json`.

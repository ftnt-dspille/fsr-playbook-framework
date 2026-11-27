# Scenario playbooks (staging)

Sample playbooks for the M365 trial scenarios, authored in the fortinet-fortiaigate
style: one `playbooks.yaml` per connector as the source of truth, compiled to
`playbooks.json` by the sibling `build.py`, with a `mock_result` on every step that
would otherwise need the connector configured - so each playbook runs end-to-end
(`fsrpb run-playbook <name> --mock`) on an appliance with none of the connectors
configured.

## Layout

    scenarios/
      README.md                          this file
      microsoft-graph_dev/               "Microsoft Graph API (fork)" package
        playbooks/playbooks.yaml         Scenarios A + C (source of truth)
        playbooks/build.py               compile + stamp + freeze
        playbooks/playbooks.json         compiled artefact (committed)
      microsoft-365-defender/            "Microsoft 365 Defender" package
        playbooks/playbooks.yaml         Scenario B (source of truth)
        playbooks/build.py               compile + stamp + freeze
        playbooks/playbooks.json         compiled artefact (committed)
      microsoft-purview-ediscovery/      "Microsoft Purview eDiscovery" package
        playbooks/playbooks.yaml         Scenario D (source of truth)
        playbooks/build.py               compile + stamp + freeze
        playbooks/playbooks.json         compiled artefact (committed)
      microsoft-graph-api-security/      no playbooks - see its README

## Build

Each `build.py` compiles its YAML with the fsrpb compiler, then stamps the sample
collection name with the connector version read from the package's `info.json`
(`--info`; defaults to `../info.json`, i.e. the packaged location) and pins
`lastModifyDate` to the YAML's mtime (`SOURCE_DATE_EPOCH` overrides) so a rebuild
is byte-identical. Strict compile first; if the catalog does not know the
connector it falls back to `--lax` (unknown-connector errors become warnings).

From this repo (the scenarios here are outside the connector packages, so the
packaged `info.json` must be passed explicitly):

    .venv/bin/python scenarios/microsoft-graph_dev/playbooks/build.py \
        --fsrpb .venv/bin/fsrpb --info /path/to/package/microsoft-graph_dev/info.json
    .venv/bin/python scenarios/microsoft-365-defender/playbooks/build.py \
        --fsrpb .venv/bin/fsrpb --info /path/to/package/microsoft-365-defender/info.json
    .venv/bin/python scenarios/microsoft-purview-ediscovery/playbooks/build.py \
        --fsrpb .venv/bin/fsrpb --info /path/to/package/microsoft-purview-ediscovery/info.json

The committed Scenario D artefact was built against the committed tooling
fixture store (`FSRPB_DB=tooling/tests/fixtures/tooling_reference.db`), which
carries the seeded WorkflowPriority picklist IRIs the compiler stamps onto the
workflow's default priority; a store whose picklists ship empty IRIs rebuilds
the same playbook with an empty priority and the staleness gate then calls the
artefact stale.

## Mock discipline

Every mock payload is the op's raw return shape, wrapped in the production
`{data, status, message, operation}` envelope, so `vars.steps.<step>.data.<field>`
references render the same way live and under `--mock`. Payloads are sanitized
synthetic shapes (all-zero tenant ids, `@contoso.example` users, RFC 5737
TEST-NET addresses); when a real capture lands, promote it into the mock block
unchanged. The same payloads validate against the typed op models in
`fsr_playbooks/connectors/typed/` (see `tooling/tests/test_m365_scenario_playbooks.py`).

## Scenarios

| # | Playbook | Package | Shape |
|---|----------|---------|-------|
| A | Respond to Compromised User Report | microsoft-graph_dev | risky-user sweep -> Teams approval -> revoke sessions + block reported IP -> close-out comment on the alert |
| B | Triage Defender Incident to Response | microsoft-365-defender (+ microsoft-graph_dev) | oldest Active Defender incident -> Advanced Hunting -> SOAR alert -> Teams approval -> update incident + block IP + revoke sessions (or reject -> comment, incident stays open) |
| C | Purge Reported Phishing Mail | microsoft-graph_dev | subject search across mailboxes -> Teams approval -> per-user delete -> close-out comment (partial purge reported, not silent) |
| D | EDiscovery Multi Mailbox Search and Triage | microsoft-purview-ediscovery | find-or-create case -> bulk custodians with hold -> custodian mailboxes -> find-or-create KQL search -> wait for estimate statistics -> preselected or Teams-card response (soft purge / hard purge / export / keep) -> delete the search it created -> outcome onto the incident |

Scenario D's connector surface (bulk custodians, wait-for-operation,
wait-for-search-statistics) lives in the connector since its 1.0.0.

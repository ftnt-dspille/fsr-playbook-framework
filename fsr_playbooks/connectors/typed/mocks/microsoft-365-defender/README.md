# Mock fixtures for the Microsoft 365 Defender connector

Sanitized, source-derived fixtures for the `microsoft-365-defender` connector
(FortiSOAR 1.2.x). They exist so playbook authoring, the linter and the agent
tooling stay testable OFFLINE once the trial tenant is gone
(m365-trial-test-plan §8.2/§8.3).

## What lives here

| File | Op | Model (`fsr_playbooks.connectors.typed.microsoft_365_defender`) |
|---|---|---|
| `list_incidents.json` | `list_incidents` | `IncidentListResponse` |
| `get_incident.json` | `get_incident` | `Incident` (`GetIncidentResponse`) |
| `update_incident.json` | `update_incident` | `UpdateIncidentResponse` (dict OR `True`) |
| `advanced_hunting.json` | `advanced_hunting` | `AdvancedHuntingResponse` |
| `errors/token_aadsts_invalid_client.json` | token endpoint (all ops) | `defender_common.AADSTSError` (also registered as `m365def-aadsts-7000215-invalid-secret` in the shared loader) |
| `errors/api_401_unauthorized.json` | every op (expired/absent token) | `defender_common.DefenderAPIError` |
| `errors/api_403_forbidden.json` | every op (missing OAuth permission/consent) | `defender_common.DefenderAPIError` |
| `errors/api_403_not_provisioned.json` | every op (tenant not onboarded to the Defender service — the EXPECTED trial-tenant outcome until endpoint onboarding) | `defender_common.DefenderAPIError` |
| `errors/api_404_incident_not_found.json` | `get_incident`, `update_incident` | `defender_common.DefenderAPIError` (NOTE: the connector RETURNS a raw `requests.Response` on 404 instead of raising — the body never reaches the playbook) |
| `errors/api_429_throttled.json` | every op (connector retries 10x/10s internally, then raises) | `defender_common.DefenderAPIError` |
| `errors/api_400_bad_query.json` | `advanced_hunting` (KQL syntax), `list_incidents` (bad filter) | `defender_common.DefenderAPIError` |

Every model's docstring carries the provenance line
`source-derived (operations.py), live-capture pending`; nothing here is
live-verified yet. Promote captured shapes over these files when
`capture_m365_defender.py` runs against a live tenant.

All fixtures are registered in the shared loader
(`typed/mocks/__init__.py`): op fixtures under `MOCK_FIXTURES`, error bodies
under `ERROR_FIXTURES` with the `m365def-` key prefix (the graph pair uses
`graph-*` / `aadsts-*`). The live suite
(`tooling/tests/test_m365_defender_live.py`) accepts 401/403/404/429 as
legal trial-tenant outcomes and asserts every failure still parses as one of
these documented shapes.

## Sanitization contract

- Synthetic tenant/object GUIDs are the zero GUID
  `00000000-0000-0000-0000-000000000000` (or zero-derived siblings).
- Users are `alice@contoso.example` / `bob@contoso.example`; hostnames are
  `win11-workstation-NN`; incident/alert/device ids are `*-NNNN` placeholders.
- No tenant ids, real user names, hostnames, or capture dates tied to a real
  box — same rule as the rest of this public repo.

## Shape contract (matches the compiler linter)

Fixtures are RAW op payloads — exactly what a `mock_result` on a connector
step should carry. The linter (`fsr_playbooks/compiler/linter.py`,
`_MOCK_ENVELOPE_STEP_TYPES`) returns connector `mock_result` VERBATIM under
`--mock`: no `{data, status, message, operation}` envelope, and a top-level
`data` key would flip how `.data` references are interpreted. The tests pin
this (`test_op_fixtures_are_raw_payloads_without_the_mock_envelope`).

## Provenance sources

- `operations.py` / `constant.py` / `microsoft_api_auth.py` of the connector
  (read-only source in the public soarshelf repo).
- `info.json` `configuration` + per-op `parameters` / `output_schema`.
- The reference store's `operation_params` rows for connector
  `microsoft-365-defender` (a dev cache, gitignored — the tests never read it).
- Connector sample playbook (`playbooks/playbooks.json`) for representative
  parameter sets.

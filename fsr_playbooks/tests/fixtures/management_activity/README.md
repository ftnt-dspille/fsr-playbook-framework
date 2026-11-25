Fixtures for test_management_activity_typed.py -- OFFLINE, docs-derived.

Provenance: docs-derived (Microsoft Learn, Office 365 Management Activity
API reference + schema), live-capture pending. NO fixture here is
live-verified; raw captures land under scratch/captures/microsoft-
management-activity/ and get promoted here sanitized, never raw.

Per-file provenance:

- subscriptions_list.json
  Verbatim "Sample response" of "List current subscriptions" in the
  reference page (an Audit.SharePoint item with a webhook, then an
  Audit.Exchange item whose webhook is null and whose status key is
  absent -- the doc's own inconsistency the model tolerates).

- start_subscription.json
  Verbatim "Sample response" of "Start a subscription" in the reference
  page.

- content_list.json
  Verbatim "Sample response" of "List available content" in the reference
  page (the five documented properties).

- content_list.is_fulfilled.json
  The same sample plus the community-observed "isFulfilled": true key,
  which the reference page does NOT document. Extension is marked here;
  pending capture confirmation.

- content_records_aad.json
  Verbatim "Sample response" of "Retrieve content" in the reference page:
  two Microsoft Entra logon records (RecordType 9) and one Entra admin
  record ("Add User.", RecordType 8 -- note it carries NO ClientIP key
  despite the Common schema marking it Mandatory, and spells the
  intra-system GUID IntraSystemId where the schema table says
  IntraSystemsId).

- content_records_general.json
  ASSEMBLED, not a verbatim doc sample: four records built field-by-field
  from the schema page's documented tables (Common + Exchange Admin +
  SharePoint Base + SharePoint file operations + Microsoft Teams + DLP).
  Placeholders: org GUID 00000000-0000-0000-0000-000000000000, users
  @contoso.example, IPs in RFC 5737 TEST-NET-3 (203.0.113.0/24). No such
  combined sample exists in the docs; live-capture pending.

- error_af20022.json
  The reference page "Errors" body shape with the documented AF20022 code
  and message ("No subscription found for the specified content type."),
  constructed from the Errors table.

- content_records_general_scc_parameters_string.json
  LIVE-CAPTURE REBASELINED: one SecurityComplianceCenter-workload record
  (RecordType 18, Get-Label) sanitized from a real Audit.General blob.
  Pins the wire truth that Parameters and NonPIIParameters arrive as a
  plain cmdlet string here, not the documented NameValuePair list.

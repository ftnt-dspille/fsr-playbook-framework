# FortiSOAR connectors cheatsheet

Generated from `store/fsr_reference.db` by `python/store/export_connectors.py`. Source-of-truth is the live FSR appliance's `/api/integration/connectors/` endpoint plus the catalog via `/api/query/solutionpacks`.

**714** connectors · **6749** operations · **4753** parameters across **85** categories.

Format per operation: `op_name(req: type, [opt: type])`. Square brackets denote optional parameters. Conditional / nested params (rendered when a parent value is set) are omitted from the inline signature — use `fsrpb explain connector <name>` to see them.

---

## Categories

- [ Authentication](#-authentication) — 1
- [ Network Security](#-network-security) — 2
- [ Threat Intelligence](#-threat-intelligence) — 1
- [Analytics & SIEM](#analytics-&-siem) — 1
- [Analytics and SIEM](#analytics-and-siem) — 44
- [Asset Management](#asset-management) — 7
- [Asset Management,Attack surface management,Cloud Security](#asset-management,attack-surface-management,cloud-security) — 1
- [Attack Surface Management](#attack-surface-management) — 1
- [Attack surface management](#attack-surface-management) — 5
- [Authentication](#authentication) — 3
- [Automation controller](#automation-controller) — 3
- [Breach and Attack Simulation (BAS)](#breach-and-attack-simulation-(bas)) — 3
- [CMDB](#cmdb) — 2
- [Case Management](#case-management) — 1
- [Case Management,Threat Intelligence](#case-management,threat-intelligence) — 1
- [Centralized Security Management](#centralized-security-management) — 3
- [Cloud Security](#cloud-security) — 12
- [Cloud Security Log](#cloud-security-log) — 1
- [Cloud access security broker (CASB)](#cloud-access-security-broker-(casb)) — 2
- [Communication](#communication) — 1
- [Communication and Coordination](#communication-and-coordination) — 14
- [Compliance and Reporting](#compliance-and-reporting) — 1
- [Compute Platform](#compute-platform) — 11
- [Container Services](#container-services) — 2
- [Content Management](#content-management) — 1
- [Data Enrichment & Threat Intelligence](#data-enrichment-&-threat-intelligence) — 1
- [Database](#database) — 14
- [Deception](#deception) — 2
- [DevOps and Digital Operations](#devops-and-digital-operations) — 8
- [Digital assistant](#digital-assistant) — 1
- [Directory Service](#directory-service) — 1
- [Email Gateway](#email-gateway) — 1
- [Email Security](#email-security) — 17
- [Email Server](#email-server) — 4
- [Endpoint Management](#endpoint-management) — 1
- [Endpoint Protection](#endpoint-protection) — 1
- [Endpoint Security](#endpoint-security) — 38
- [Enterprise mobility management](#enterprise-mobility-management) — 1
- [Firewall](#firewall) — 1
- [Firewall and Network Protection](#firewall-and-network-protection) — 23
- [FortiSOAR Essentials](#fortisoar-essentials) — 1
- [HTTP Requests](#http-requests) — 1
- [IT Service](#it-service) — 1
- [IT Service Management](#it-service-management) — 18
- [IT Service Management,Network Security,Compliance and Reporting](#it-service-management,network-security,compliance-and-reporting) — 1
- [IT Services](#it-services) — 12
- [Identity Management](#identity-management) — 1
- [Identity and Access Management](#identity-and-access-management) — 20
- [Information](#information) — 3
- [Insider Threat](#insider-threat) — 1
- [Investigation](#investigation) — 1
- [Logging](#logging) — 4
- [ML Service](#ml-service) — 3
- [Machine Learning](#machine-learning) — 2
- [Malware Analysis](#malware-analysis) — 26
- [Message Queueing Service](#message-queueing-service) — 1
- [Miscellaneous](#miscellaneous) — 1
- [Monitoring](#monitoring) — 4
- [Network Protection](#network-protection) — 1
- [Network Security](#network-security) — 51
- [Network Security,Cloud Security,Endpoint Security](#network-security,cloud-security,endpoint-security) — 1
- [Network Visibility](#network-visibility) — 1
- [OT & IoT Security](#ot-&-iot-security) — 4
- [OT & IoT Security ](#ot-&-iot-security-) — 2
- [Query Service](#query-service) — 2
- [Security Posture Management](#security-posture-management) — 10
- [Source Code Management](#source-code-management) — 3
- [Storage](#storage) — 4
- [System Monitoring](#system-monitoring) — 1
- [Task Management](#task-management) — 1
- [Threat Detection](#threat-detection) — 7
- [Threat Hunting and Search](#threat-hunting-and-search) — 2
- [Threat Intelligence](#threat-intelligence) — 169
- [Ticket Creation](#ticket-creation) — 1
- [Ticket Management](#ticket-management) — 10
- [Translator](#translator) — 1
- [Uncategorized](#uncategorized) — 33
- [Utilities](#utilities) — 34
- [Vulnerability Management](#vulnerability-management) — 2
- [Vulnerability and Risk Management](#vulnerability-and-risk-management) — 20
- [Web Application](#web-application) — 7
- [information](#information) — 1
- [investigation](#investigation) — 2
- [network_security](#network_security) — 1
- [utilities](#utilities) — 4

---

##  Authentication

### `duo` v1.0.1 _(installed)_
_Duo_

Duo provides secure, rapid transition to the cloud use Duo Beyond to protect their on-premises and hosted applications, while securing their mobile workforce and their chosen devices.

**4 operation(s)** (+1 hidden):

- `authenticate_user()` — Authenticate User
- `get_auth_status()` — Get Auth Status
- `get_preauth_details()` — Get Preauth Details


---

##  Network Security

### `empire` v1.0.0 _(installed)_
_Empire_

Empire is a pure PowerShell post-exploitation agent built on cryptologically-secure communications and a flexible architecture. This connector facilitates automated operations like get listeners, get agents, execute modules, get stagers etc.

**16 operation(s)**:

- `create_listener()` — Create Listener
- `create_stager()` — Create Stager
- `execute_module()` — Execute Modules
- `get_agent_results()` — Get Agent Results
- `get_agents()` — Get Agents
- `get_credentials()` — Get Credentials
- `get_listener_options()` — Get Listener Options
- `get_listeners()` — Get Listeners
- `get_stagers()` — Get Stagers
- `get_stale_agents()` — Get Stale Agents
- `remove_agent()` — Remove Agent
- `remove_agent_results()` — Remove Agent Results
- `run_shell_command_on_agent()` — Execute Shell Command
- `search_module()` — Get/Search Modules
- `terminate_agent()` — Terminate Agent
- `terminate_listener()` — Terminate Listener


### `foresight` v1.1.0 _(installed)_
_Foresight_

Foresight connector performs actions like create, update, search, close, cancel and add comment to ticket.

**12 operation(s)**:

- `comment_ticket()` — Add Comment
- `create_ticket()` — Create Ticket
- `get_comment_ticket()` — Get Comment
- `search_ticket()` — Search Ticket
- `ticket_action_acquire()` — Acquire Ticket
- `ticket_action_cancel()` — Cancel Ticket
- `ticket_action_close()` — Close Ticket
- `ticket_action_negotiate()` — Negotiate Ticket
- `ticket_action_reassign()` — Reassign Ticket
- `ticket_action_resolved()` — Resolved Ticket
- `ticket_action_start()` — Start Ticket
- `update_ticket()` — Update Ticket


---

##  Threat Intelligence

### `dnstools` v1.0.0 _(installed)_
_DNSTools_

Perform investigative actions like DNS Lookup and Reverse DNS Lookup

**2 operation(s)**:

- `dns_lookup()` — DNS Lookup
- `reverse_dns_lookup()` — Reverse DNS Lookup


---

## Analytics & SIEM

### `fortinet-fortianalyzer` v3.4.0 _(installed, ingestion)_
_Fortinet FortiAnalyzer_

FortiAnalyzer is the NOC-SOC security analysis tool built with operations perspective. With action-oriented views and deep drill-down capabilities, FortiAnalyzer not only gives organizations critical insight into threats, but also accurately scopes risk across the attack surface, pinpointing where immediate response is required.

**39 operation(s)**:

_investigation_
- `add_attachment(incid: text, data: json, adom_name: text, attachtype: text, [attachsrc: text], [attachsrcid: text], [attachsrctrigger: text], [lastuser: text])` — Add Incident Attachment
- `add_master_device(name: text, ip: text, sn: text, adom_name: text, [os_ver: text])` — Add a Primary Device
- `add_new_device(name: text, ip: text, sn: text, adom_name: text, [os_ver: text])` — Add a New Device
- `add_slave_device(slave_name: text, slave_sn: text, master_name: text, master_sn: text, adom_name: text)` — Add a Secondary Device
- `authorize_device(name: text, sn: text, adom_name: text, [os_ver: text])` — Authorize Device
- `count_alerts_for_multiple_adoms(group-by: text, [start: datetime], [end: datetime], [filter: text])` — Count Events for Multiple ADOMs
- `count_incidents_for_multiple_adoms([incids: text], [filter: text])` — Count Incidents for Multiple ADOMs
- `create_incident(reporter: text, endpoint: text, adom_name: text, [assigned-to: text], [category: text], [severity: select], [status: select], [euid: integer], [description: textarea], [other_fields: json])` — Create Incident
- `delete_device(name: text, adom_name: text)` — Delete a Device
- `fetch_log_search_result_by_task_id(tid: text, adom_name: text, [offset: integer], [limit: integer], [wait_for_search_process_to_complete: checkbox])` — Fetch Log Search Result by Task ID
- `get_adoms()` — Get ADOMs
- `get_alert_event_logs(alertid: text, adom_name: text, [limit: integer], [offset: integer], [time-order: select])` — Get Event Logs
- `get_alerts(adom_name: text, [start: datetime], [end: datetime], [alertid: text], [filter: text], [limit: integer], [offset: integer])` — Get Event
- `get_alerts_for_multiple_adoms([start: datetime], [end: datetime], [alertid: text], [filter: text], [limit: integer], [offset: integer])` — Get Event for Multiple ADOMs
- `get_attachments_for_incident(incid: text, adom_name: text, [attachtype: text], [limit: integer], [offset: integer])` — Get Incident Attachments
- `get_device_info(name: text, adom_name: text)` — Get Device Information
- `get_devices(adom_name: text)` — Get Devices
- `get_endpoints(adom_name: text, fetch_type: select, [filter: text], [limit: integer], [offset: integer], [sort-by: checkbox])` — Get Endpoint Information
- `get_events_for_incident(incid: text, adom_name: text, [limit: integer], [offset: integer])` — Get Events For Incident
- `get_generated_report(tid: text, adom_name: text)` — Get Report File
- `get_incident_assets(incid: text, adom_name: text, [limit: integer], [offset: integer])` — Get Incident Assets
- `get_log_file_content(devid: text, filename: text, vdom: text, adom_name: text, [data-type: text], [offset: integer], [length: integer])` — Get Log-File Content
- `get_log_file_state(adom_name: text, [devid: text], [filename: text], [vdom: text], [start: datetime], [end: datetime])` — Get Log-File State
- `get_log_status(adom_name: text, [devid: text])` — Get Log Status
- `get_outbreak_alerts_summary(adom_name: text, [start: datetime], [end: datetime], [filter: text])` — Get Outbreak Alerts Summary
- `get_reports(state: text, start: datetime, end: datetime, adom_name: text)` — Get Executed Report List
- `get_schedules(adom_name: text)` — Get Report Schedule List
- `get_users(adom_name: text, fetch_type: select, [filter: text], [detail-level: select], [limit: integer], [offset: integer], [sort-by: checkbox])` — Get User Information
- `json_rpc_freeform(data: json)` — Execute an API Request
- `list_incidents(adom_name: text, [incids: text], [status: select], [filter: text], [detail-level: select], [limit: integer], [offset: integer], [sort-by: checkbox])` — Get Incident
- `list_incidents_for_multiple_adoms([incids: text], [status: select], [filter: text], [detail-level: select], [limit: integer], [offset: integer], [sort-by: checkbox])` — Get Incident for Multiple ADOMs
- `list_log_fields(devtype: text, logtype: select, adom_name: text, [subtype: text])` — List Log Fields
- `log_search_over_log_file(devid: text, filename: text, vdom: text, logtype: select, adom_name: text, [case-sensitive: checkbox], [filter: text], [offset: integer], [limit: integer])` — Log Search over Log-File
- `run_report(schedule: text, id: text, adom_name: text)` — Run Report
- `start_and_fetch_bulk_device_logs(devid: select, start: datetime, end: datetime, logtype: select, adom_name: text, [filter: text], [case-sensitive: checkbox], [time-order: select], [offset: integer], [limit: integer], [wait_for_search_process_to_complete: checkbox])` — Start and Fetch Bulk Device Logs
- `start_bulk_device_log_search_request(devid: select, start: datetime, end: datetime, logtype: select, adom_name: text, [filter: text], [case-sensitive: checkbox], [time-order: select])` — Start bulk device log Search Request
- `start_log_search_request(devid: text, devname: text, start: datetime, end: datetime, logtype: select, adom_name: text, [filter: text], [case-sensitive: checkbox], [time-order: select])` — Start Log Search Request
- `update_attachment(attachid: text, data: json, adom_name: text, [attachsrc: text], [attachsrcid: text], [attachsrctrigger: text], [lastuser: text])` — Update Incident Attachment
- `update_incident_details(incid: text, adom_name: text, [assigned-to: text], [category: select], [status: select], [endpoint: text], [severity: select], [euid: integer], [description: textarea], [other_fields: json])` — Update Incident


---

## Analytics and SIEM

### `alienvault-usm-anywhere` v1.2.0 _(installed)_
_AlienVault USM Anywhere_

AlienVault USM Anywhere Connector can be used to automate actions like get events, get event details, get alarm details, get alarms, get alarm labels, add alarm labels and delete alarm labels

**7 operation(s)**:

- `add_alarm_label()` — Add Alarm Label
- `delete_alarm_label()` — Delete Alarm Label
- `get_alarm_details()` — Get Alarm Details
- `get_alarm_labels()` — Get Alarm Labels
- `get_alarms()` — Get Alarms
- `get_event_details()` — Get Event Details
- `get_events()` — Get Events


### `alphasoc` v1.0.0 _(installed)_
_AlphaSOC Network Behavior Analytics_

AlphaSOC Network Behavior Analytics connector provide action fetch alert to retrieve alerts from AplhaSOC.

**1 operation(s)**:

- `get_alerts()` — Fetch Alerts


### `arcsight` v4.1.1 _(installed)_
_Micro Focus ArcSight ESM_

Micro Focus ArcSight Enterprise Security Manager (ESM) is a threat detection, analysis, triage, and compliance management SIEM platform, This connector can be use to ingesting events from ArcSight, search and case management

**23 operation(s)** (+1 hidden):

- `add_case_event()` — Add Events To Case
- `annotate_event()` — Annotate Event
- `annotate_event_by_stage_id()` — Annotate Event By Stage ID
- `clear_active_list_entries()` — Clear Active List Entries
- `create_case()` — Create Case
- `delete_active_list_entries()` — Delete Active List Entries
- `delete_case_event()` — Delete Case Events
- `delete_report()` — Delete Archive Report
- `get_active_list_entries()` — Get Active List Entries
- `get_active_list_info()` — Get Active List Information
- `get_case_info()` — Get Case Information
- `get_event_details()` — Get Event Details Using XML API
- `get_event_info()` — Get Event Details
- `get_events_list()` — Get Events List
- `get_fields()` — Get Event Fields
- `get_query_viewer_data()` — Get Query Viewer Data
- `run_report()` — Run Report with Default Parameters
- `run_report_params()` — Run Report
- `run_search()` — Search Query
- `update_active_list()` — Add Active List Entries
- `update_case_info()` — Update Case
- `upload_report()` — Download Report


### `azure-log-analytics` v2.0.1 _(installed)_
_Azure Log Analytics_

Log Analytics is a tool in the Azure portal that's used to edit and run log queries against data in the Azure Monitor Logs store. This connector facilitates the automated operations related to query and saved searches.

**6 operation(s)**:

- `create_saved_searches()` — Create Saved Searches
- `delete_saved_search()` — Delete Saved Search
- `execute_query()` — Execute Query
- `get_saved_searches()` — Get Saved Searches
- `list_saved_searches()` — List Saved Searches
- `update_saved_searches()` — Update Saved Searches


### `azure-sentinel` v1.1.0 _(installed)_
_Azure Sentinel_

Azure Sentinel is Cloud-native SIEM for intelligent security analytics for your entire enterprise. These connector connects to azure sentinel using microsoft graph API to investigate on alerts, threats intelligence indicator, incidents and secure score.

**15 operation(s)**:

- `create_threat_intelligence_indicator()` — Create Threat Intelligence Indicator
- `delete_threat_intelligence_indicator()` — Delete Threat Intelligence Indicator
- `fetch_alert_query()` — Fetch Alert Query
- `get_alert()` — Get Alert
- `get_alert_events()` — Get Alert Events
- `get_alert_list()` — Get Alert List
- `get_all_secure_score_control_profiles()` — Get All Secure Score Control Profiles
- `get_all_secure_scores()` — Get All Secure Scores
- `get_all_threat_intelligence_indicators()` — Get All Threat Intelligence Indicators
- `get_incident()` — Get Incident
- `get_incident_list()` — Get Incident List
- `get_threat_intelligence_indicator()` — Get Threat Intelligence Indicator
- `update_alert()` — Update Alert
- `update_incident()` — Update Incident
- `update_threat_intelligence_indicator()` — Update Threat Intelligence Indicator


### `crowdstrike-falcon-logscale` v1.0.0 _(installed)_
_CrowdStrike Falcon LogScale_

CrowdStrike Falcon® LogScale™ is a next-generation Security Information and Event Management (SIEM) platform designed to provide real-time log management, threat detection, and observability at scale.

**6 operation(s)**:

- `cancel_query_job()` — Cancel Query Job
- `get_custom_lookup_file()` — Get Custom Lookup File
- `get_managed_lookup_file()` — Get Managed Lookup File
- `get_search_results()` — Get Search Results
- `initiate_search()` — Initiate Search
- `upload_file()` — Upload File


### `darktrace` v1.4.0 _(installed)_
_Darktrace_

Darktrace is enterprise immune system for threat detecation. This connector provided automated operations for Get Watch List, Update Watch List, Get Incidents, Search Query, etc

**24 operation(s)**:

- `acknowledge_breach()` — Acknowledge Breach
- `add_to_list()` — Add To Watch List
- `create_manual_antigena()` — Create Manual Antigena
- `execute_api_request()` — Execute an API Request
- `get_antigena()` — Get Antigena List
- `get_antigena_summary()` — Get Antigena Summary
- `get_breach_details()` — Get Breach Details
- `get_comments()` — Get Incident Comments
- `get_components()` — Get Components
- `get_device_information()` — Get Device Information
- `get_devices()` — Get Devices
- `get_entity_details()` — Get Entity Details
- `get_enums()` — Get Enums
- `get_external_endpoint_details()` — Get External Endpoint Details
- `get_incidents()` — Get Incidents
- `get_mb_comments()` — Get Model Breach Comments
- `get_model_breaches()` — Get Model Breaches
- `get_models()` — Get Models
- `get_similar_devices()` — Get Similar Devices
- `get_watch_list()` — Get Watch List
- `remove_from_list()` — Remove From Watch List
- `search_query()` — Search Query
- `unacknowledge_breach()` — Unacknowledge Breach
- `update_antigena()` — Update Antigena


### `datadog-siem-cloud` v1.0.0 _(installed)_
_Datadog Cloud SIEM_

Datadog Cloud SIEM is a real time threat detection platform paired with rich observability context to achieve faster security outcomes.

**8 operation(s)**:

- `get_attachments()` — Get Attachments
- `get_event_details()` — Get Event Details
- `get_hosts()` — Get Hosts
- `get_incident_details()` — Get Incident Details
- `get_incidents()` — Get Incidents
- `search_events()` — Search Events
- `search_incidents()` — Search Incidents
- `update_incident()` — Update Incident


### `devo` v1.0.0 _(installed)_
_Devo_

Devo connector performs actions like get alerts, run query etc.

**3 operation(s)**:

- `get_alert_definitions()` — List Alert Definitions
- `get_alerts()` — Get Alerts
- `run_query()` — Run Query


### `elastic-kibana` v1.0.0 _(installed)_
_Elastic Kibana_

Elastic Kibana provides a powerful UI for interacting with the Elastic Stack. It enables users to search, visualize, and manage data from Elasticsearch, build dashboards, monitor systems, and secure their environment.

**9 operation(s)**:

- `add_and_remove_detection_alert_tags()` — Add and Remove Detection Alert Tags
- `create_a_live_query()` — Create Live Query
- `generic_action()` — (Deprecation Warning) Generic Action
- `generic_api_call()` — Execute an API Request
- `get_all_data_views()` — Get All Data Views
- `get_case_information()` — Get Case Information
- `get_live_query_results()` — Get Live Query Results
- `get_saved_queries()` — Get Saved Queries
- `search_cases()` — Search cases


### `elastic-security` v1.0.0 _(installed)_
_Elastic Security_

Elastic Security provides threat prevention, detection, and response capabilities built on the Elastic Stack. It unifies SIEM, endpoint security, and cloud security in a single solution.

**8 operation(s)**:

- `eql_search_api()` — (Deprecation Warning) EQL Search API
- `esql_search_api()` — (Deprecation Warning) ESQL Search API
- `generic_action()` — (Deprecation Warning) Generic Action
- `generic_api_call()` — Execute an API Request
- `get_eql_search_results()` — Get EQL Search Results
- `get_status()` — (Deprecation Warning) Get Status
- `get_the_cluster_health_status()` — Get Cluster Health Status
- `run_an_esql_query()` — Run an ES|QL Query


### `exabeam` v1.0.0 _(installed)_
_Exabeam_

The Exabeam Security Management Platform provides end-to-end detection, User Event Behavioral Analytics.

**8 operation(s)**:

- `delete_watchlist()` — Delete Watchlist
- `get_asset_data()` — Get Asset Data
- `get_notable_users()` — Get Notable Users
- `get_peer_groups()` — Get Peer Groups
- `get_user_info()` — Get User Information
- `get_user_labels()` — Get User Labels
- `get_user_sessions()` — Get User Sessions
- `get_watchlists()` — Get Watchlists


### `exabeam-data-lake` v1.0.0 _(installed)_
_Exabeam Data Lake_

Exabeam Data Lake provides centralized logging, advanced search, cloud storage and reporting.

**1 operation(s)**:

- `run_query()` — Run Query


### `fireeye-helix` v1.0.0 _(installed)_
_FireEye Helix_

FireEye Helix is a security operations platform. FireEye Helix integrates security tools and augments them with next-generation SIEM, orchestration and threat intelligence tools such as alert management, search, analysis, investigations and reporting.

**23 operation(s)**:

- `add_list_item()` — Add List Item
- `create_an_alert_note()` — Create Alert Note
- `delete_alert_note()` — Delete Alert Note
- `delete_list()` — Delete List
- `edit_rule()` — Edit Rule
- `get_alert_details()` — Get Alert Details
- `get_alert_notes()` — Get Alert Notes
- `get_alerts()` — Get All Alert List
- `get_assets_by_alert()` — Get Alert Assets
- `get_cases()` — Get All Case List
- `get_cases_by_alert()` — Get Alert Cases
- `get_cases_details()` — Get Cases Details
- `get_endpoints_by_alert()` — Get Alert Endpoints
- `get_events()` — Get All Event List
- `get_events_by_alert()` — Get Alert Events
- `get_list_details()` — Get List Details
- `get_list_items()` — Get List Items
- `get_lists()` — Get Lists
- `get_rules_list()` — Get Rules List
- `get_sensors_list()` — Get Sensors List
- `remove_list_item()` — Remove List Item
- `update_list()` — Update List
- `update_list_item()` — Update List Item


### `fortinet-fortisiem` v5.4.2 _(installed)_
_Fortinet FortiSIEM_

FortiSIEM provides integrations that allow you to query and make changes to the CMDB, query events, and send incident notifications. Provide actions like get incidents, comment incident, cleared incident, get device details, get monitored organizations, report related actions and get all associated events for an incident from FortiSIEM.

**45 operation(s)**:

_investigation_
- `add_watch_list_entries_to_watch_list_groups(watch_list_id: text, other_params: json)` — Add Watch List Entries to Watch List
- `check_import_task_status(lookupTableId: text, taskId: text)` — Check Import Task Status
- `clear_incident(id: text, comment_text: text)` — Clear Incident With Reason
- `create_case(organization: text, assignee: text, summary: text, severity: select, [status: select], [stage: select], [incidentIds: text], [note: text], [caseMgmtPolicy: text], [dueDate: datetime])` — Create Case
- `create_lookup_table(name: text, columnList: json, [description: text], [organizationName: text])` — Create Lookup Table
- `create_task(task_metadata: json, triggeredByUser: text, [assignedToUser: text], [comment: text])` — Create Task
- `create_watchlist_group(json_object: json)` — Create Watch List
- `delete_lookup_table(lookupTableId: text)` — Delete Lookup Table
- `delete_lookup_table_data(lookupTableId: text, keys_data: json)` — Delete Lookup Table Data
- `delete_watch_list(watch_list_ids: text)` — Delete Watch List
- `delete_watch_list_entry(watch_list_entry_ids: text)` — Delete Watch List Entry
- `execute_api_request(endpoint: text, method: select, [headers: json], [query_params: json], [payload_format: select], [payload: json])` — Execute an API Request
- `get_all_lookup_tables([stat: integer], [size: integer])` — Get All Lookup Table
- `get_associated_events(incident_id: text, [timeFrom: datetime], [timeTo: datetime], [perPage: integer])` — Get Events For Incident (Deprecated)
- `get_associated_events_new(incident_id: text, [timeFrom: datetime], [timeTo: datetime], [perPage: integer])` — Get Events For Incident
- `get_case_analysts([organization: text], [timeFrom: datetime], [timeTo: datetime], [start: integer], [size: integer])` — Get Case Analysts
- `get_case_field_schema()` — Get Case Field Schema
- `get_device_info(ip: text, [org: text])` — Get Device Information
- `get_devices_details([org: text])` — Get All Devices
- `get_devices_details_in_address(includeIps: text, [excludeIps: text], [org: text])` — Get All Devices For Specified IP Address Range
- `get_event_details(event_id: text, select_clause: text, [from: datetime], [to: datetime])` — Get Event Details
- `get_events_by_query_id(query_id: text, [perPage: integer], [start: integer])` — Get Events Data By Query ID
- `get_host_context(value: text)` — Get Host Context
- `get_incident_attributes()` — Get Event Attributes
- `get_incident_details(incidentId: text)` — Get Incident Details
- `get_incidents(timeFrom: datetime, timeTo: datetime, [incidentStatus: multiselect], [incidentCategory: multiselect], [incidentSubCategory: text], [severity: multiselect], [eventType: text], [search: json], [size: integer], [start: integer], [orderBy: text], [fields: text])` — List Incidents
- `get_ip_context(value: text)` — Get IP Context
- `get_list_cases(selectFields: text, [condition: text], [orderBy: text], [runForOrganization: text], [start: integer], [size: integer])` — Get List Cases
- `get_lookup_table_data(lookupTableId: text, [start: integer], [size: integer], [searchText: text], [sortBy: text])` — Get Lookup Table Data
- `get_monitored_devices()` — List Monitored Devices and Attributes
- `get_monitored_organizations()` — List Monitored Organizations
- `get_org_name_by_org_id(domain_id: text)` — Get Organization Details
- `get_user_context(value: text)` — Get User Context
- `get_watch_list_entries_count()` — Get Watch List Entries Count
- `get_watch_list_entry(watch_list_entry_id: text)` — Get Watch List Entry
- `get_watch_lists([get_watch_list_by: select])` — Get Watch Lists
- `import_lookup_table_data(input: select, lookupTableId: text, mapping: json, [fileSeparator: text], [fileQuoteChar: text], [skipHeader: checkbox], [updateType: select])` — Import Lookup Table Data
- `incident_comment(id: text, comment_text: text)` — Comment Incident
- `run_report([query_type: select], [perPage: integer], [start: integer])` — Run Advanced Search Query
- `search_events(attribute: multiselect, select_clause: text, [time_selection: select], [perPage: integer], [start: integer])` — Search Events
- `update_cases(caseId: text, [assignee: text], [summary: text], [severity: select], [status: select], [stage: select], [incidentIds: text], [note: text], [caseMgmtPolicy: text], [dueDate: datetime])` — Update Case
- `update_incident(incidentId: text, [comments: text], [incidentStatus: select], [severity: select], [resolution: select], [externalTicketType: select], [externalTicketId: text], [externalTicketState: select], [actionStatus: text], [externalAssignedUser: text])` — Update Incident
- `update_lookup_table_data(lookupTableId: text, key: text, columnData: json)` — Update Lookup Table Data
- `update_watch_list_entry(watch_list_entry_id: text, [count: integer], [lastSeenTime: text], [state: select], [other_params: json])` — Update Watch List Entry
- `upload_attachment_for_case(caseID: text, [upload_option: select])` — Upload Attachment for Case


### `gigamon` v1.0.0 _(installed)_
_Gigamon_

Gigamon Connector

**5 operation(s)**:

- `add_rule()` — Add Rule
- `delete_rules()` — Delete Rules
- `get_map()` — Get Map
- `get_maps()` — Get Maps
- `update_rule()` — Update Rule


### `google-chronicle-backstory` v1.0.0 _(installed)_
_Google Chronicle BackStory_

Google Chronicle BackStory is used to detect and investigate potential cyber threats.

**9 operation(s)**:

- `get_alerts()` — Get Alerts
- `get_assets()` — List All Assets
- `get_detection_details()` — Get Detection Details
- `get_detections()` — List All Detections
- `get_domain_reputation()` — Get Domain Reputation
- `get_events()` — List All Events
- `get_iocs()` — List All IOCs
- `get_ip_reputation()` — Get IP Reputation
- `get_rules()` — List All Rules


### `google-secops-siem` v1.0.0 _(installed)_
_Google SecOps SIEM_

Google Security Operations (SecOps) is a cloud-native security information and event management (SIEM) platform built on Google Cloud's infrastructure. It is designed to help enterprises detect, investigate, and respond to cybersecurity threats at scale and speed. By normalizing, indexing, and analyzing vast amounts of security telemetry, Google SecOps provides real-time insights into potential risks, enabling security teams to act swiftly and effectively.

**5 operation(s)**:

- `check_health()` — Check Health
- `execute_api_endpoint()` — Execute API Endpoint
- `legacyfetchalertsview()` — Fetch Legacy Alerts View
- `legacygetalert()` — Get Legacy Alert
- `udm_search()` — UDM Search


### `grafana` v1.1.0 _(installed)_
_Grafana_

Grafana Alerting Service provides a unified, powerful system for monitoring and notifying users, allowing them to fetch alert data, including the status and details of active or past alerts.

**4 operation(s)**:

- `generic_rest_api_call()` — Execute an API Request
- `get_alerts()` — Get Alerts
- `get_data_sources()` — Get Data Sources
- `run_datasource_query()` — Run Data Source Query


### `graylog` v1.0.0 _(installed)_
_Graylog_

Graylog is a leading centralized log management solution for capturing, storing, and enabling real-time analysis of terabytes of machine data. This connector facilitates automated operations related to alerts, clusters, events, and search messages.

**15 operation(s)**:

- `get_alerts()` — Get Alerts
- `get_cluster_input_states()` — Get Cluster Input States
- `get_cluster_lookup_tables()` — Get Clusters Lookup Tables
- `get_cluster_metrics()` — Get Cluster Metrics
- `get_cluster_node_jvm()` — Get Cluster Node JVM
- `get_cluster_node_metrics()` — Get Cluster Node Metrics
- `get_cluster_node_metrics_names()` — Get Cluster Node Metrics Names
- `get_cluster_processing_status()` — Get Cluster Processing Status
- `get_clusters()` — Get Clusters
- `get_indexer_cluster_health()` — Get Indexer Cluster Health
- `get_streams()` — Get Streams
- `get_system_lookup_tables()` — Get System Lookup Tables
- `search_absolute()` — Search Absolute
- `search_events()` — Search Events
- `search_relative()` — Search Relative


### `imperva-counterbreach` v1.0.0 _(installed)_
_Imperva CounterBreach_

Imperva CounterBreach protects enterprise data stored in enterprise databases, file shares and SaaS applications from the theft and loss caused by compromised, careless or malicious users. Imperva CounterBreach connector performs action like get security events, get allow list rule, update incident/anomaly etc.

**6 operation(s)**:

- `get_allow_list_rule()` — Get Allow List Rule
- `get_security_events()` — Get Security Events
- `get_specific_allow_list_rule()` — Get Specific Allow List Rule
- `update_anomaly()` — Update Anomaly
- `update_incident()` — Update Incident
- `update_rule()` — Update Allow List Rule


### `jask-asoc` v1.0.0 _(installed)_
_JASK ASOC_

Pull data from Alerts, Signals, and Assets within JASK's ASOC platform

**9 operation(s)**:

- `get_alert_details()` — Get Alert Details
- `get_asset_details()` — Get Asset Details
- `get_asset_details_by_ip()` — Get Asset Details By IP
- `get_intel_sources()` — Get Intel Sources
- `get_sensor_details()` — Get Sensor Details
- `get_sensors_list()` — Get Sensor List
- `get_signal_details()` — Get Signal Details
- `post_threat_intel()` — Post Threat Intel
- `search()` — Search


### `logpoint` v2.0.2 _(installed)_
_LogPoint_

LogPoint enables organizations to convert data into actionable intelligence, improving their cybersecurity posture and creating immediate business value. LogPoint connector provides automated actions for collecting, analyzing, and monitoring your machine data.

**13 operation(s)** (+1 hidden):

- `get_devices()` — Get Devices
- `get_incident()` — Get Incident
- `get_incident_states()` — Get Incident States
- `get_incident_users()` — Get Incident Users
- `get_live_search()` — Get Live Search
- `get_log_points()` — Get Log Points
- `get_repos()` — Get Repos
- `get_search_id()` — Get Search ID
- `get_search_logs()` — Get Search Logs
- `get_timezone()` — Get Time Zone
- `list_incidents()` — Fetch Incidents
- `update_incident()` — Update Incident


### `logrhythm` v3.1.0 _(installed)_
_LogRhythm_

LogRhythm delivers in-depth endpoint visibility, automated threat hunting and breach response across the entire enterprise. LogRhythm  enhances investigator productivity with extensive rules and user behavior analytics that brings the skills and best practices of the most experienced security analysts to any organization, resulting in significantly lower costs. This connector supports the investigation actions like Get Alarm, Update Alarm etc on LogRhythm SIEM.

**33 operation(s)**:

- `add_alarm_comment()` — Add Alarm Comment
- `add_alarm_evidence()` — Add Alarm Evidence
- `add_case_tags()` — Add Case Tags
- `add_file_evidence()` — Add File Evidence
- `add_note_evidence()` — Add Note Evidence
- `create_case()` — Create Case
- `delete_case_evidence()` — Delete Case Evidence
- `download_file_evidence()` — Download File Evidence
- `get_alarm_details()` — DrillDown - Get Alarm Details
- `get_alarm_details_ex()` — Get Alarm Details
- `get_alarm_events()` — DrillDown - Get Alarm Events
- `get_alarm_events_ex()` — Get Alarm Events
- `get_alarm_history()` — Get Alarm History
- `get_alarm_summary()` — Get Alarm Summary
- `get_associated_cases_list()` — Get Associated Cases List
- `get_case()` — Get Case
- `get_case_collaborators()` — Get Case Collaborators
- `get_case_metrics()` — Get Case Metrics
- `get_evidence()` — Get Evidence
- `get_evidence_list()` — Get Evidence list
- `get_evidence_progress()` — Get Evidence Progress
- `get_host_by_entities()` — Get Hosts by Entities
- `get_hosts()` — Get Hosts
- `get_list_details()` — Get List Details
- `get_network_list()` — Get Network List
- `get_user_list()` — Get User List
- `list_alarm()` — Search Alarm
- `list_case_tags()` — List Case Tags
- `list_cases()` — Get Case List
- `list_user_events_evidence()` — Get User Event List
- `remove_case_tags()` — Remove Case Tags
- `update_alarm()` — Update Alarm
- `update_case()` — Update Case


### `logz-io` v1.0.0 _(installed)_
_Logz.io_

Logz.io delivers unified, full stack observability and security as a fully-managed SaaS based on best-of-breed open source. The Open 360 platform brings together logs, metrics, traces, and security data, applying powerful AI/ML features to improve troubleshooting, reduce response times, and help manage costs.

**8 operation(s)**:

- `delete_an_alert()` — Delete Alert By ID
- `disable_alert_by_id()` — Disable Alert By ID
- `enable_alert_by_id()` — Enable Alert By ID
- `fetch_security_events()` — Get Security Events List
- `get_list_of_insights()` — Get Insights List
- `retrieve_alert_by_id()` — Get Alert By ID
- `retrieve_all_alerts()` — Get Alerts List
- `search_logs()` — Search Logs


### `manage-engine-log360` v1.0.0 _(installed)_
_ManageEngine Log360_

ManageEngine Log360 is a unified SIEM solution with integrated DLP and CASB capabilities that detects, prioritizes, investigates, and responds to security threats.

**3 operation(s)**:

- `get_alert_profiles()` — Get Alert Profiles List
- `get_alerts()` — Get Alerts List
- `invoke_search()` — Get Events List


### `mcafee-esm` v2.6.0 _(installed)_
_McAfee ESM_

McAfee ESM(Enterprise Security Manager) connector can be used to automate actions related to cases, alarms, watchlist and data sources.

**20 operation(s)** (+1 hidden):

- `acknowledge_alarm()` — Acknowledge Alarm
- `add_note_to_event()` — Add Note to event
- `add_watchlist_values()` — Add WatchList Values
- `create_case()` — Create Case
- `delete_watchlist()` — Delete WatchList
- `delete_watchlist_values()` — Delete WatchList Values
- `get_alarm_detail()` — Get Alarm Detail
- `get_case_details()` — Get Case Details
- `get_cases()` — Get Cases
- `get_data_source_details()` — Get Data Source Details
- `get_data_source_list()` — Get Data Source List
- `get_device_tree()` — Get Device Tree
- `get_event_detail()` — Get Event Detail
- `get_watchlist_values()` — Get WatchList Values
- `get_watchlists()` — Get WatchLists
- `list_alarms()` — Get Alarms
- `parse_uri()` — Parse URL
- `unacknowledge_alarm()` — Unacknowledge Alarm
- `update_case()` — Update Case


### `micro-focus-arcsight-logger` v1.1.0 _(installed)_
_Micro Focus ArcSight Logger_

ArcSight Logger delivers a cost-effective universal log management solution that unifies searching, reporting, alerting, and analysis across any type of enterprise machine data. This unified machine data can be used for compliance, regulations, security, IT operations, and log analytics.

**9 operation(s)**:

- `close()` — Release Search Session
- `drilldown()` — Get Events from Time Range
- `get_events()` — Get Search Result
- `histogram()` — Get Histogram
- `raw_events()` — Get Raw Events
- `search()` — Start Search
- `search_events()` — Search Events
- `status()` — Get Search Status
- `stop()` — Stop Search


### `micro-focus-interset` v1.0.0 _(installed)_
_Micro Focus Interset_

Interset is powerful investigation and hunting interface. This connector can be use to get entity related information, risky user details, get or delete workflows etc

**26 operation(s)**:

- `add_tag_to_elements()` — Add Tag To Elements
- `create_tag()` — Create Tag
- `delete_rule()` — Delete Rule
- `delete_tag()` — Delete Tag
- `get_anomalies_alerts_aggregates()` — Get Anomalies/Alerts/Aggregates
- `get_anomaly_weights()` — Get Anomaly Weights
- `get_associated_entities()` — Get Associated Entities
- `get_authentication_attempts()` — Get Authentication Attempts
- `get_bot_users()` — Get Bot Users
- `get_context()` — Get Context
- `get_entities()` — Get Entities
- `get_entities_by_tags()` — Get Entities By Tags
- `get_entity_details()` — Get Entity Details
- `get_entity_risk_distribution()` — Get Entity Risk Distribution
- `get_entity_risk_graph()` — Get Entity Risk Graph
- `get_entity_risk_score()` — Get Entity Risk Score
- `get_raw_events()` — Get Raw Events
- `get_session_info()` — Get Session
- `get_tags()` — Get Tags
- `get_top_accessed_entities_by_entitytype()` — Get Top Accessed Entities
- `get_top_risky_entities_by_entitytype()` — Get Top Risky Entities
- `get_workflows()` — Get Rules
- `get_working_hours()` — Get Working Hours
- `remove_tag_from_elements()` — Remove Tag From Elements
- `search_users()` — Search Users
- `set_anomaly_weight()` — Set Anomaly Weight


### `microsoft-sentinel` v1.1.0 _(installed)_
_Microsoft Sentinel_

Microsoft Sentinel is Cloud-native SIEM for intelligent security analytics for your entire enterprise. These connector connects to Microsoft sentinel using Sentinel APIs to investigate on alerts, threats intelligence indicator, incidents, incident entities, incident relations, incident comments, and incident bookmarks.

**31 operation(s)**:

- `create_incident_comment()` — Create Incident Comment
- `create_incident_relations()` — Create Incident Relations
- `create_threat_intelligence_indicator()` — Create Threat Intelligence Indicator
- `create_watchlist()` — Create Watchlist
- `create_watchlist_item()` — Create Watchlist Item
- `delete_incident_comment()` — Delete Incident Comment
- `delete_incident_relation()` — Delete Incident Relation
- `delete_threat_intelligence_indicator()` — Delete Threat Intelligence Indicator
- `delete_watchlist()` — Delete Watchlist
- `delete_watchlist_item()` — Delete Watchlist Item
- `get_alert_list()` — Get Incident Alert List
- `get_all_incident_comments()` — Get All Incident Comments
- `get_all_incident_relations()` — Get All Incident Relations
- `get_all_threat_intelligence_indicators()` — Get All Threat Intelligence Indicators
- `get_all_watchlist()` — Get All Watchlist
- `get_all_watchlist_items()` — Get All Watchlist Items
- `get_bookmarks_list()` — Get Incident Bookmarks List
- `get_entities_list()` — Get Incident Entities List
- `get_incident()` — Get Incident Details
- `get_incident_comment()` — Get Incident Comment
- `get_incident_list()` — Get Incident List
- `get_incident_relations()` — Get Incident Relation
- `get_threat_intelligence_indicator()` — Get Threat Intelligence Indicator
- `get_watchlist()` — Get Watchlist
- `get_watchlist_item()` — Get Watchlist Item
- `update_incident()` — Update Incident
- `update_incident_comment()` — Update Incident Comment
- `update_incident_relations()` — Update Incident Relations
- `update_threat_intelligence_indicator()` — Update Threat Intelligence Indicator
- `update_watchlist()` — Update Watchlist
- `update_watchlist_item()` — Update Watchlist Item


### `netwitness` v1.0.1 _(installed)_
_NetWitness_

RSA NetWitness connector

**5 operation(s)**:

- `get_meta_from_type()` — Get Meta
- `get_pcap()` — Get PCAP for Session Ids
- `get_pcap_from_type()` — Get PCAP
- `get_raw_query()` — Make Raw NetWitness Query
- `get_session_ids_from_where_stmnt()` — Get Session Ids from a where statement


### `qradar` v1.6.2 _(installed)_
_IBM QRadar_

IBM QRadar is an enterprise security information and event management (SIEM) product. Fortinet FortiSOAR connector for IBM QRadar allows users to invoke QRadar API, perform Ariel Queries and operations like Get Offense,related events,update and close offenses.

**23 operation(s)**:

- `add_notes()` — Create Note
- `add_table_element()` — Add or Update Table Element
- `close_offense()` — Close Offense
- `create_case()` — Create Case
- `delete_reference_table()` — Delete or Purge Reference Table
- `delete_table_element()` — Delete Table Element
- `fetch_offenses()` — Fetch Offenses from QRadar
- `get_assets()` — Get Assets
- `get_assets_properties()` — Get Assets Properties
- `get_cases()` — Get Cases
- `get_closing_reasons()` — Get Offense Closing Reasons
- `get_destination_ip()` — Get Destination IP Addresses
- `get_events_related_to_offense()` — Get Events Related to an Offense
- `get_notes()` — Get Offense Notes
- `get_offense_type()` — Get Offense Types
- `get_offenses()` — Get Offenses from QRadar
- `get_reference_tables()` — Get Reference Tables
- `get_source_ip()` — Get Source IP Addresses
- `get_table_elements()` — Get Table Elements
- `handle_reference_set_value()` — Manipulate Reference Set Content
- `invoke_api()` — Invoke QRadar REST API
- `query_qradar()` — Make an Ariel Query to QRadar
- `update_asset()` — Update Asset


### `rapid7-insightidr` v2.1.0 _(installed)_
_Rapid7 InsightIDR_

Rapid7 InsightIDR is an intruder analytics solution that gives you the confidence to detect and investigate security incidents faster. This connector facilitates automated operations like get investigations, update status of the investigation, close investigation, add/ update indicators to threat.

**12 operation(s)**:

- `add_indicators_to_threat()` — Add Indicators to Threat
- `close_investigations()` — Close Investigations
- `create_comment()` — Create Comment
- `create_investigation()` — Create Investigation
- `delete_comment()` — Delete Comment
- `get_alerts_associated_with_investigation()` — Get Alerts Associated With Investigation
- `get_comments()` — Get Comments
- `get_investigations()` — Get Investigation List
- `get_investigations_details()` — Get Investigation Details
- `search_investigations()` — Search Investigations
- `update_indicators_to_threat()` — Replace Indicators for Threat
- `update_investigation()` — Update Investigation


### `rsa-netwitness-siem` v1.2.1 _(installed)_
_RSA Netwitness SIEM_

The RSA NetWitness Platform is an evolved SIEM and threat detection and response solution that allows security teams to rapidly detect and respond to any threat, anywhere. This connector facilitates the automated operations like Get Incident, Get Incidents by Date Range and Get Incident Related Alerts.

**6 operation(s)**:

- `get_alerts()` — Get Alerts
- `get_hosts()` — Get Hosts List
- `get_incident()` — Get Incident
- `get_incident_by_date_range()` — Get Incidents by Date Range
- `get_incidents_alerts()` — Get Incident Related Alerts
- `get_service_id()` — Get Service IDs


### `sap-etd` v1.1.0 _(installed)_
_SAP Enterprise Threat Detection_

SAP Enterprise Threat Detection (ETD) helps you to identify the real attacks as they are happening and analyze the threats quickly enough to neutralize them before serious damage occurs. SAP Enterprise Threat Detection connector performs action like get alerts.

**1 operation(s)**:

- `get_alert()` — Get Alerts


### `securonix-snypr` v2.3.0 _(installed)_
_Securonix SNYPR_

Connector facilitates automated operations to Analyze and detect the Threats, Violations and Risk associated with users in organisation.

**26 operation(s)**:

- `add_comment()` — Add Comment
- `check_task_on_incident()` — Check Task on Incident
- `create_incident()` — Create Incident
- `custom_query()` — Custom Query
- `get_available_threat_action()` — Get Available Threat Action
- `get_incident_details()` — Get Incident Details
- `get_incident_status()` — Get Incident Status
- `get_incident_workflow()` — Get Incident Workflow
- `get_possible_action_for_incident()` — Get Possible Actions for Incident
- `get_risk_history()` — Get Risk History
- `get_risk_score()` — Get Risk Score
- `get_top_threats()` — Get Top Threats
- `get_top_violations()` — Get Top Violations
- `get_top_violators()` — Get Top Violators
- `get_workflow_default_assignee()` — Get Workflow Default Assignee
- `get_workflows()` — Get Workflows
- `list_incidents()` — List Incidents
- `list_peer_groups()` — List All Peer Groups
- `list_policies()` — List All Policies
- `list_resource_groups()` — List All Resource Groups
- `list_users()` — List All Users
- `query_tpi()` — Query Third Party Intelligence
- `query_users()` — Query Users
- `query_violations()` — Query Violations
- `query_watchlist()` — Query Watchlist
- `take_action_on_incident()` — Task Action on Incident


### `sekoia-io-xdr` v1.1.0 _(installed)_
_SEKOIA.IO XDR_

SEKOIA.IO eXtended Detection and Response SaaS platform leverages Cyber Threat Intelligence to combine anticipation with automated incident response. SEKOIA.IO XDR offers open, transparent and flexible security oversight to break down silos and neutralise threats before impact, using intelligence. This connector facilitates automated operations related to alerts, assets and events.

**10 operation(s)**:

- `activate_countermeasure()` — Activate a Countermeasure
- `add_comment_to_alert()` — Add Comment to Alert
- `delete_asset()` — Delete Asset
- `deny_countermeasure()` — Deny a Countermeasure
- `get_alert()` — Get Alert
- `get_asset()` — Get Asset
- `get_events()` — Get Events
- `list_alerts()` — List Alerts
- `update_alert_status()` — Update Alert Status
- `update_asset()` — Update Asset


### `sentinelone` v3.5.3 _(installed)_
_SentinelOne_

SentinelOne that provides threat detection, hunting, and response features that enable organizations to discover vulnerabilities and protect IT operations. This connector facilitates automated operations related to events, threats, agents, query, and applications.

**45 operation(s)** (+3 hidden):

- `abort_agent_scan()` — Abort Agent Scan
- `add_note_to_a_threat()` — Add Note to a Threat
- `agent_action()` — Agent Action
- `broadcast_message_to_agent()` — Broadcast Message to Agent
- `cancel_running_query()` — Cancel Running Query
- `change_incident_status()` — Change Incident Status
- `create_blacklist_item()` — Create Blocklist Item
- `create_query()` — Create Query And Get Query ID
- `custom_endpoint()` — Execute an API Request
- `delete_threat_note()` — Delete Threat Note
- `export_applications_risk()` — Export Applications Risk
- `export_forensics_threat()` — Export Threat
- `fetch_agent_logs()` — Fetch Agents Logs
- `fetch_threat_file()` — Fetch Threat File
- `fetch_threats()` — Fetch Threats
- `free_text_filters()` — Free Text
- `get_agent_application()` — Get Agent Application
- `get_agent_count()` — Get Agent Count
- `get_agent_passphrase()` — Get Agent Passphrase
- `get_agents()` — Get Agents
- `get_alerts()` — Get Alerts
- `get_application_count()` — Get Application Count
- `get_application_cve()` — Get Application CVEs
- `get_applications()` — Get Applications
- `get_cve()` — Get CVEs
- `get_events()` — Get Events
- `get_events_by_type()` — Get Events By Type
- `get_hash_details()` — Get Hash Details
- `get_query_status()` — Get Query Status
- `get_threat_details()` — Get Threat Details
- `get_threat_events()` — Get Threat Events List
- `get_threat_notes()` — Get Threat Notes
- `get_threat_timeline()` — Get Threat Timeline
- `initiate_agent_scan()` — Initiate Agent Scan
- `list_all_threats()` — List All Threats
- `mark_threat_as_benign()` — Mark Threat as Benign
- `mitigate_threats()` — Mitigate Threat
- `reconnect_agent()` — Reconnect Agent
- `threat_forensic_details()` — Threat Forensic Details
- `threat_forensics()` — Get Threat Forensics
- `threat_seen_on_network()` — Get Threat Seen on Network
- `update_threat_note()` — Update Threat Note


### `splunk` v2.0.2 _(installed, ingestion)_
_Splunk_

Splunk connector allows users to invoke search, fetch events to related search, invoke alert actions, update notables, sync splunk users to FortiSOAR etc.

**18 operation(s)**:

_investigation_
- `add_new_collection(app_name: text, collection: text, [owner: text])` — Add New Collection to Splunk App
- `add_notable_comment(eventIds: text, comment: text)` — Add Comment to Splunk Notables
- `add_record_to_collection(app_name: text, collection: text, record_key: text, record_value: text, [owner: text])` — Add Record to a Collection
- `bulk_add_record_to_collection([owner: text], app_name: text, collection: text, record_key_value: json)` — Bulk Add Record to a Collection
- `delete_record_from_collection([owner: text], app_name: text, collection: text, record_id: text)` — Delete Record From a Collection
- `fetch_events(query: textarea, [app: text], [earliest_time: datetime], [latest_time: datetime], [exec_mode: select], [auto_cancel: text], [additional_search_args: json])` — Fetch Events
- `get_alert_action([action_name: text])` — Get Splunk Action
- `get_alert_details(alert_name: text)` — Get Details Of Triggered Alert
- `get_all_collections(app_name: text, [owner: text])` — Get All Collections from Splunk App
- `get_events(sid: text, [app: text], [additional_args: text])` — Get Events for a Search
- `get_records_in_collection(app_name: text, collection: text, [owner: text])` — Fetch Records from Collection
- `get_results(sid: text, [app: text], [additional_args: text])` — Get Results for a Search
- `get_search_info(sid: text, [app: text])` — Get Details for a Search
- `invoke_alert_action(action_name: text, action_params: text, frequency: select, [event_id: text], [sid: text])` — Run Splunk Action
- `invoke_search(query: textarea, [app: text], [earliest_time: text], [latest_time: text], [exec_mode: select], [auto_cancel: text], [additional_search_args: json])` — Invoke Search
- `list_alerts([count: integer], [offset: integer], [search_value: text], [sort_dir: select], [sort_key: text], [sort_mode: select])` — Get List Of Triggered Alerts
- `update_splunk_notables(event_id: text, [status: text], [urgency: text], [record_owner: text])` — Update Splunk Notables

_miscellaneous_
- `sync_splunk_users()` — Sync Splunk Users to FortiSOAR


### `stellar-cyber` v1.0.0 _(installed)_
_Stellar Cyber_

Connector facilitates automated operations to perform ElasticSearch DSL query of the index on your Stellar Cyber(Starlight) server.

**2 operation(s)** (+1 hidden):

- `search_query()` — Search Query


### `sumo-logic` v1.1.1 _(installed)_
_Sumo Logic_

Sumo Logic provides best-in-class cloud monitoring, log management, Cloud SIEM tools, and real-time insights for web and SaaS based apps.

**8 operation(s)**:

- `create_search_job()` — Create Search Job
- `delete_search_job()` — Delete Search Job
- `get_details_by_insights_id()` — Get Details By Insights ID
- `get_list_of_all_insights()` — Get the List of All Insights
- `get_list_of_insights_by_query()` — Get the List of Insights By Query
- `get_messages_founded_by_search_job()` — Get Messages Founded by Search Job
- `get_records_founded_by_search_job()` — Get Records Founded by Search Job
- `get_search_job_status()` — Get Search Job Status


### `symantec-ica` v1.0.0 _(installed)_
_Symantec ICA_

Integrate with Symantec ICA to retrieve entity risk scores for entities like users, IPs, and hosts.

**9 operation(s)**:

- `get_action_plans()` — Get Action Plans
- `get_host_risk()` — Get Host Risk
- `get_ip_risk()` — Get IP Risk
- `get_risk_model_details()` — Get Risk Model Instance Details
- `get_risk_model_instances()` — Get Risk Model Instances
- `get_user_risk()` — Get User Risk
- `set_action_plan_comment()` — Create Comment on Action Plan
- `set_event_classifications()` — Set Event Classifications
- `set_event_mitigations()` — Set Event Mitigations


### `symantec-security-analytics` v2.0.0 _(installed)_
_Symantec Security Analytics_

Symantec Security Analytics connector provides automated operations for advanced network forensics, and real-time content inspection for all network traffic.

**15 operation(s)**:

- `get_alerts_list()` — Get Alerts
- `get_alerts_timeline_data()` — Get Alerts Timeline Data
- `get_all_providers()` — List All Enrichment Providers
- `get_artifact_reputation()` — Get Artifact Reputation
- `get_artifact_rootcause()` — Get Artifact Rootcause
- `get_details_extractions()` — Search for Artifacts in Extraction
- `get_sensor_list()` — Get Sensor List
- `get_sensor_status()` — Get Sensors Status
- `start_extractions()` — Start Artifact Extractions
- `start_extractions_for_ip_address()` — Start Extractions for IP Address
- `start_extractions_for_md5()` — Start Extractions for MD5
- `start_extractions_for_port()` — Start Extractions for Port
- `start_extractions_for_protocol()` — Start Extractions for Protocol
- `start_extractions_for_sha1()` — Start Extractions for SHA1
- `start_extractions_for_sha256()` — Start Extractions for SHA256


### `wazuh-siem` v1.0.0 _(installed)_
_Wazuh SIEM_

Wazuh provides a security solution capable of monitoring your infrastructure, detecting threats, intrusion attempts, system anomalies, poorly configured applications and unauthorized user actions. This connector facilitates automated operations to Get Alerts by Lucene search, DSL search etc.

**4 operation(s)**:

- `get_alert_by_id()` — Get Alert Details
- `get_alerts_by_DSL_search()` — Execute DSL Search
- `get_alerts_by_lucene_search()` — Execute Lucene Search
- `get_all_alerts_in_last_x_minutes()` — Get All Alerts in Last X Minutes


---

## Asset Management

### `axonius` v1.0.0 _(installed)_
_Axonius_

Axonius provides the unified view of all your assets, users, vulnerabilities, and more by aggregating data from business management and security tools. This connector provides action to Get Devices, Get Assets

**2 operation(s)**:

- `get_device_assets()` — Get Device Assets
- `get_user_assets()` — Get User Assets


### `azure-commands` v1.0.1 _(installed)_
_Azure Commands_

Azure Commands are used to run Azure native commands for Azure resources configurations directly from FortiSOAR.

**10 operation(s)**:

- `delete_resource()` — Delete Resource
- `delete_vm()` — Delete Virtual Machine
- `generic_command()` — Execute Azure Command
- `get_resource()` — Get Resource
- `get_vm()` — Get Virtual Machine
- `list_resource()` — Get Resources List
- `list_ssh_keys()` — Get SSH Keys List
- `list_storage_fs_directory()` — Get Storage FS Directory List
- `list_vm()` — Get Virtual Machines List
- `list_webapp()` — Get Webapp List


### `dragos-sitestore` v1.0.0 _(installed)_
_Dragos SiteStore_

Dragos SiteStore is a key component of the Dragos Platform, designed to enhance cybersecurity for industrial control systems (ICS) and operational technology (OT) environments. It serves as the management and reporting console for data collected by Dragos sensors, providing comprehensive visibility and threat detection capabilities.

**8 operation(s)**:

- `execute_an_api_call()` — Execute an API Request
- `get_assets()` — Get All Assets
- `get_detections()` — Get All Detections
- `get_notification_details()` — Get Notifications Details
- `get_notifications()` — Get All Notifications
- `get_stats_of_notification()` — Get Statistics of Notification
- `get_vulnerabilities()` — Get All Vulnerabilities
- `get_vulnerability_detections()` — Get All Vulnerability Detections


### `forticloud-asset-management` v1.0.0 _(installed)_
_FortiCloud Asset Management_

Asset Management is an easy-to-use portal to register, organize and view all Fortinet products and services in FortiCloud. New products, licenses, or contracts can be registered and managed with the Asset Management portal. Registered products are displayed in the Product List as well as a customizable folder structure called My Assets.

**10 operation(s)**:

_investigation_
- `decommission_product(serial_numbers: text)` — Decommission Product
- `download_license(serial_number: text)` — Download License
- `generic_api_call(method: select, endpoint: text, [payload: json])` — Generic API Call
- `list_assets(filter: select)` — List Assets
- `product_details(serial_number: text)` — Get Product Details
- `register_license(license_registration_code: text, [serial_number: text], [description: text], [additional_info: text], [is_government: checkbox])` — Register License
- `register_product(serial_number: text, [contract_number: text], [description: text], [asset_group_ids: text], [replaced_serial_number: text], [additional_info: text], [cloud_key: text], [is_government: checkbox])` — Register Product
- `register_service(contract_number: text, [description: text], [additional_info: text], [is_government: checkbox])` — Register Service
- `update_description(serial_number: text, description: text)` — Update Description
- `update_location(serial_number: text, address: text, city: text, stateOrProvince: text, countryCode: text, postalCode: text, [company: text], [email: text], [phone: text], [fax: text])` — Update Location


### `fortinet-fortiflex` v1.0.0 _(installed)_
_Fortinet FortiFlex_

FortiFlex is a points-based program that empowers organizations to provision the Fortinet services and solutions, and offers the flexibility to scale their security solutions and services up or down as well as in or out to meet their dynamic deployment demands and evolving requirements.

**17 operation(s)**:

_investigation_
- `create_configuration(programSerialNumber: text, name: text, productTypeId: select, [accountId: integer])` — Create Configuration
- `create_hardware_entitlements(configId: integer, serialNumbers: text, [endDate: datetime])` — Create Hardware Entitlements
- `create_vm_entitlements(configId: integer, count: integer, folderPath: text, [description: text], [endDate: datetime])` — Create VM Entitlements
- `disable_configuration(id: integer)` — Disable Configuration
- `enable_configuration(id: integer)` — Enable Configuration
- `get_configurations(programSerialNumber: text, [accountId: integer])` — Get All Configuration List
- `get_entitlements(filter: select)` — Get All Entitlement List
- `get_group_next_token(accountId: integer, [configId: text], [folderPath: text])` — Get NextToken for Group
- `get_groups(accountId: integer)` — Get All Group List
- `get_point_usage_for_vm(filter: select, startDate: datetime, endDate: datetime)` — Get Point Usage for VM
- `get_programs()` — Get All Program List
- `reactivate_entitlement(serialNumber: text)` — Reactivate Entitlement
- `regenerate_token_for_vm(serialNumber: text)` — Regenerate Token for VM
- `stop_entitlement(serialNumber: text)` — Stop Entitlement
- `transfer_entitlement(sourceAccountId: integer, sourceConfigId: integer, serialNumbers: text, targetAccountId: integer, [targetConfigId: integer])` — Transfer Entitlement
- `update_configuration(id: integer, name: text, productTypeId: select)` — Update Configuration
- `update_entitlements(configId: integer, serialNumber: text, description: text, endDate: datetime)` — Update Entitlements


### `microsoft-onedrive` v1.0.0 _(installed)_
_Microsoft OneDrive_

OneDrive is a cloud storage and file synchronization service developed by Microsoft. It allows users to store their files and documents securely in the cloud, making them accessible from various devices with an internet connection. OneDrive integrates seamlessly with Microsoft Office applications, enabling users to create, edit, and collaborate on documents in real time. It offers features such as automatic backup of photos and videos from mobile devices, file sharing with others, version history for documents, and the ability to access files offline.

**7 operation(s)**:

- `create_folder()` — Create Folder
- `download_file()` — Download File
- `get_document_library()` — Get Document Library
- `get_drive_by_id()` — Get Drive By ID
- `get_user_onedrive()` —  Get User OneDrive
- `list_drives()` — List Drives
- `upload_file()` — Upload File


### `netbox` v1.0.0 _(installed)_
_NetBox_

NetBox is the leading solution for modeling and documenting modern networks. By combining the traditional disciplines of IP address management (IPAM) and datacenter infrastructure management (DCIM) with powerful APIs and extensions, NetBox provides the ideal "source of truth" to power network automation.

**24 operation(s)**:

- `delete_cable()` — Delete Cable
- `delete_device()` — Delete Device
- `delete_ip_address()` — Delete IP Address
- `delete_prefix()` — Delete Prefix
- `delete_rack()` — Delete Rack
- `delete_vm()` — Delete Virtual Machine
- `get_cable()` — Get Cable
- `get_cable_list()` — Get Cables List
- `get_device()` — Get Device
- `get_device_list()` — Get Devices List
- `get_ip_address()` — Get IP Address
- `get_ip_address_list()` — Get IP Address List
- `get_prefix()` — Get Prefix
- `get_prefix_list()` — Get Prefix List
- `get_rack()` — Get Rack
- `get_rack_list()` — Get Rack List
- `get_vm()` — Get Virtual Machine
- `get_vm_list()` — Get Virtual Machines List
- `update_cable()` — Update Cable
- `update_device()` — Update Device
- `update_ip_address()` — Update IP Address
- `update_prefix()` — Update Prefix
- `update_rack()` — Update Rack
- `update_vm()` — Update Virtual Machine


---

## Asset Management,Attack surface management,Cloud Security

### `wiz-io` v2.0.0 _(installed)_
_Wiz.io_

Wiz provides a comprehensive analysis engine that integrates: Cloud Security Posture Management (CSPM) Kubernetes Security Posture Management (KSPM) Cloud Workload Protection (CWPP) + vulnerability management. Infrastructure-as-Code (IaC) scanning.

**5 operation(s)**:

- `add_comment_to_issue()` — Add Comment to Issue
- `get_inventory_assets()` — Get Inventory Assets
- `get_issues()` — Get Issues
- `get_projects()` — Get Projects
- `get_vulnerabilities()` — Get Vulnerabilities


---

## Attack Surface Management

### `fortinet-fortirecon-easm` v1.2.1 _(installed)_
_Fortinet FortiRecon EASM_

FortiRecon is a Digital Risk Protection Service (DRPS) product that provides an outside-the-network view to the risks posed to your enterprise.

**43 operation(s)** (+2 hidden):

_investigation_
- `generate_report([tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text])` — Generate Report
- `get_archived_assets([user_action: select], [asset_type: select], [asset: text], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Archived Assets
- `get_archived_issue_comments(issue_id: text, [comment_type: select], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Archived Issue Comments
- `get_archived_issues([status: select], [asset_type: select], [asset: text], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Archived Issues
- `get_asns_by_asset_id(asset_id: text, [linked_assets: checkbox])` — Get ASNs by Asset ID
- `get_asset_asns([search_type: select], [asset: text], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select], [discovered_by_fgt_integration: select], [cloud_metadata: json], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Asset ASNs
- `get_asset_statistics([ports: text], [countries: text], [technologies: text], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select])` — Get Asset Statistics
- `get_breaches([name: text], [q: text], [has_password: select], [is_relevant: select], [page: integer], [size: integer])` — Get Breaches
- `get_breaches_by_id(breach_id: text)` — Get Breaches by ID
- `get_cloud_integrations([provider: select], [connection_status: select], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Cloud Integrations
- `get_domain_by_asset_id(asset_id: text, [linked_assets: checkbox])` — Get Domain by Asset ID
- `get_domains([ports: text], [technologies: text], [asset: text], [search_type: select], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select], [discovered_by_fgt_integration: select], [is_live: select], [discovered_by_cloud_integration: select], [cloud_metadata: json], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Domains
- `get_exposed_services([asset: text], [ports: text], [services: text], [products: text], [service_banner: text], [after_primary_scan: select], [has_ssl: select], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Exposed Services
- `get_fgt_integrations([connection_status: select], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get FortiGate Integrations
- `get_group_by_id(group_id: text, [linked_assets: checkbox])` — Get Group Details
- `get_groups([scope: select], [name: text], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Groups
- `get_ips([ports: text], [countries: text], [asset: text], [search_type: select], [ip_prefix: text], [version: select], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select], [discovered_by_fgt_integration: select], [is_live: select], [discovered_by_cloud_integration: select], [cloud_metadata: json], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get IPs
- `get_ips_by_asset_id(asset_id: text, [linked_assets: checkbox])` — Get IP by Asset ID
- `get_issue_by_id(issue_id: text)` — Get Issue By ID
- `get_issue_comments(issue_id: text, [comment_type: select], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Issue Comments
- `get_issue_summary([tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select])` — Get Issue Summary
- `get_issues_discovered([status: select], [severity: select], [nvd_severity: select], [recon_severity: select], [countries: text], [bucket_id: multiselect], [issue_name_identifier: text], [asset_type: select], [asset: text], [search_type: select], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Issues Discovered
- `get_leaked_credentials([q: text], [breach_id: integer], [email: text], [domain: text], [status: select], [has_password: select], [show_plaintext_password: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Leaked Credentials
- `get_prefixes([asset: text], [search_type: select], [asn: text], [version: select], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select], [discovered_by_fgt_integration: select], [cloud_metadata: json], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Prefixes
- `get_prefixes_by_asset_id(asset_id: text, [linked_assets: checkbox])` — Get Prefixes by Asset ID
- `get_report(report_id: text, [get_link: checkbox])` — Get Report
- `get_scan_statistics([tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text])` — Get Scan Statistics
- `get_security_insights(domain: text)` — Get Security Insights
- `get_subdomain_by_asset_id(asset_id: text)` — Get Subdomain by Asset ID
- `get_subdomains([ports: text], [technologies: text], [domain: text], [asset: text], [search_type: select], [tags_in: text], [tags_match_all: text], [groups_in: text], [groups_match_all: text], [after_primary_scan: select], [discovered_by_fgt_integration: select], [is_live: select], [discovered_by_cloud_integration: select], [cloud_metadata: json], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Subdomains
- `get_tag_by_id(tag_id: text, [linked_assets: checkbox])` — Get Tag Details
- `get_tags([scope: select], [name: text], [created_ts: text], [modified_ts: text], [page: integer], [size: integer])` — Get Tags
- `update_archived_asset(asset_id: text)` — Update Archived Asset
- `update_archived_issue(issue_id: text)` — Mark Archived Issue as Active
- `update_asn_asset_status_to_false_positive(asset_id: text)` — Update ASN Asset To False Positive
- `update_domain_asset_status_to_false_positive(asset_id: text)` — Update Domain Asset To False Positive
- `update_ip_asset_status_to_false_positive(asset_id: text)` — Update IP Asset To False Positive
- `update_issue_status(issue_id: text, status: select)` — Update Issue Status
- `update_leaked_credential_status(leaked_cred_id: text, status: select)` — Update Leaked Credential Status
- `update_prefix_asset_status_to_false_positive(asset_id: text)` — Update IP Prefix Asset To False Positive
- `update_subdomain_asset_status_to_false_positive(asset_id: text)` — Update Sub-Domain Asset To False Positive


---

## Attack surface management

### `acronis` v1.0.0 _(installed)_
_Acronis Cyber Protect Cloud_

Acronis Cyber Protect Connect is a remote access solution to remotely manage workloads - quickly and easily. This connector facilitates automated operations to fetch alerts, target, service etc.

**5 operation(s)**:

- `create_alert()` — Create an Alert
- `delete_alert()` — Delete an Alert
- `get_alert_types()` — Get Alert Types
- `get_alerts()` — Get Alerts
- `get_categories()` — Get Categories


### `censys` v2.0.0 _(installed)_
_Censys_

Censys is a search engine that focuses on providing comprehensive information about devices and systems connected to the Internet. It is specifically designed to help researchers, security professionals, and organizations gain insights into various aspects of the global Internet infrastructure. Censys employs a variety of techniques to continuously scan and analyze the Internet, collecting data on IP addresses, websites, certificates, open ports, and other network-related information. This extensive dataset allows users to search for specific devices, services, or vulnerabilities, helping them understand the security posture of different entities on the Internet.

**3 operation(s)**:

- `get_host_details()` — Get Host Details Using IP Address
- `lookup_certificate()` — Lookup Certificate
- `search_hosts()` — Search Hosts


### `fortinet-fortirecon-aci` v2.1.2 _(installed, ingestion)_
_Fortinet FortiRecon ACI_

FortiRecon is a Digital Risk Protection Service (DRPS) product that provides an outside-the-network view to the risks posed to your enterprise.The Adversary Centric Intelligence (ACI) module leverages FortiGuard Threat Analysts to provide comprehensive coverage of dark web, open source, and technical threat intelligence, including threat actor insights. This information enables administrators to proactively assess risks, respond faster to incidents, better understand their attackers, and protect assets. This connector facilitates the automated operations related to ACI. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**37 operation(s)** (+2 hidden):

_investigation_
- `get_icl_saved_searches([q: text], [alert: select], [query_type: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get ICL Saved Searches
- `get_icl_saved_searches_by_id(based_on: select, id: text, [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get ICL Saved Searches By ID
- `get_intel_ioc(ioc_id: text)` — Get Specific Adversary Centric Intelligence ACI IOCs
- `get_intel_iocs([name: text], [report_ids: text], [type: text], [first_seen: datetime], [last_seen: datetime], [keyword: text], [sort: text], [page: integer], [size: integer], [get_all_records: checkbox])` — Get Intel IOCs
- `get_intel_report(report_id: text)` — Get Specific Adversary Centric Intelligence ACI Report
- `get_intel_reports([report_id: text], [tag: text], [adversaries: text], [source: text], [source_category: text], [report_type: text], [industries: text], [geographies: text], [iocs: text], [source_reliability: text], [information_reliability: text], [report_generator_source: text], [insight_relevance: text], [motivations: text], [keyword: text], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Adversary Centric Intelligence ACI Reports
- `get_leaked_cards([type: text], [bin: text], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Leaked Cards
- `get_leaked_stealers_infections([q: text], [stealer_name: text], [affiliated_domain: text], [status: select], [show_plaintext_password: select], [user_type: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Leaked Stealers Infections
- `get_osint_feeds([widget_id: text], [keyword: text], [page: integer], [size: integer])` — Get OSINT Feeds
- `get_ransomware_group_info(group_name: text)` — Get Ransomware Group Information
- `get_ransomware_intel_org_watchlist([type: select], [page: integer], [size: integer])` — Get Ransomware Intelligence Orgs Watchlist To Monitor
- `get_ransomware_intel_org_watchlist_matched([page: integer], [size: integer])` — Get The Matched Organizations For Ransomware Intelligence Monitoring
- `get_ransomware_intel_vendors_watchlist([page: integer], [size: integer])` — Get Ransomware Vendors Added For Ransomware Intelligence Monitoring
- `get_ransomware_intel_vendors_watchlist_matched([page: integer], [size: integer])` — Get Ransomware Vendors Matched
- `get_ransomware_intelligence_statistics(type_of_info: select, [time_range_type: select], [start_date: datetime], [end_date: datetime])` — Get Ransomware Intelligence Stats
- `get_ransomware_potential_victims([actor: text], [country: text], [sectors: text], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Potential Ransomware Victims
- `get_ransomware_threat_campaigns([page: integer], [size: integer])` — Get Ransomware Threat Campaign
- `get_ransomware_victims([q: text], [ransomware_name: text], [country: text], [sectors: text], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Ransomware Victims
- `get_ransomware_victims_details_by_id(id: text)` — Get Ransomware Victim Details By ID
- `get_stealers_infections_leaked_count(based_on: select)` — Get Stealers Infections Leaked Count
- `get_stealers_infections_on_sale([search_string: text], [stealers: text], [marketplaces: text], [isps: text], [countries: text], [states: text], [matched_domains: text], [status: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Stealers Infections On Sale
- `get_stealers_infections_on_sale_count(based_on: select)` — Get Stealers Infections On Sale Count
- `get_technical_indicators_for_given_ransomware_group(group_name: text, [page: integer], [size: integer])` — Get The Technical Indicators For The Given Ransomware Group
- `get_vendor_details_by_id(id: text)` — Get Vendor Details By ID
- `get_vendor_exposures_by_id(type_of_info: select, id: text)` — Get Vendor Exposures By Vendor ID
- `get_vendor_watchlist([domain: text], [name: text], [approval_status: select], [status: select], [page: integer], [size: integer])` — Get Vendor Watchlist
- `get_vulnerability_intelligence_cves(input_src_type: select, [recon_severity: select], [nvd_severity: select], [years: text], [input_src_subtype: select], [vuln_exploitation: select], [vendors: text], [products: text], [tags: text], [keyword: text], [is_elevated: select], [sort: select], [data_sources: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Vulnerability Intelligence CVEs
- `get_vulnerability_intelligence_cves_by_id(id: text)` — Get Vulnerability Intelligence CVEs By ID
- `get_vulnerability_intelligence_hits_by_cve_id(based_on: select, id: text, [page: integer], [size: integer])` — Get Vulnerability Intelligence hits By CVE ID
- `get_vulnerability_intelligence_stats_for_cve_id(based_on: select, id: text, [page: integer], [size: integer])` — Get Vulnerability Intelligence Stats For CVE ID
- `get_vulnerability_intelligence_vulnerable_products(input_src_type: select, [sort: select], [page: integer], [size: integer])` — Get Vulnerability Intelligence vulnerable products
- `get_vulnerability_intelligence_vulnerable_vendors(input_src_type: select, [sort: select], [page: integer], [size: integer])` — Get Vulnerability Intelligence vulnerable vendors
- `get_widgets([page: integer], [size: integer])` — Get Widgets
- `update_stealers_leaked_status(stealers_leaked_id: text, status: select)` — Update Stealers Leaked Status
- `update_stealers_on_sale_status(stealers_on_sale_id: text, status: select)` — Update Stealers On Sale(Marketplaces) Status


### `horizon3-ai` v1.0.0 _(installed)_
_Horizon3.ai_

Horizon3.ai is a cybersecurity company specializing in automated security solutions. Their flagship product, NodeZero, is an autonomous penetration testing platform that simulates real-world cyberattacks to identify vulnerabilities and provide actionable remediation insights. Designed for ease of use, NodeZero empowers organizations to continuously assess and improve their security posture without relying heavily on manual intervention. It supports cloud, on-premise, and hybrid environments, making it adaptable to diverse IT setups.

**3 operation(s)**:

- `get_attack_paths()` — Get Attack Paths
- `get_pentests()` — Get Pentests
- `get_weaknesses()` — Get Weaknesses


### `ibm-randori` v1.0.0 _(installed)_
_IBM Randori_

IBM Randori is an attack surface management SaaS that monitors internal and external attack surfaces for unexpected changes, blind spots, misconfigurations, and process failures. This connector facilitates automated operations to fetch network, target, service etc.

**13 operation(s)**:

- `get_all_detections_for_target()` — Get All Detections for Target
- `get_artifact()` — Get Artifact by UUID
- `get_hostnames()` — Get Hostname List
- `get_ips()` — Get IP Objects
- `get_ips_for_hostname()` — Get IPs for Hostname
- `get_ips_for_network()` — Get IPs for Network
- `get_networks()` — Get Network List
- `get_policy()` — Get Policy List
- `get_report()` — Get Report List
- `get_services()` — Get Service List
- `get_single_detection_for_target()` — Get Single Detection for Target
- `get_statistics()` — Get Statistics List
- `get_targets()` — Get Target List


---

## Authentication

### `fortinet-fortiauthenticator` v1.0.0 _(installed)_
_Fortinet FortiAuthenticator_

FortiAuthenticator provides centralized authentication services for the Fortinet Security Fabric including single sign on services, certificate management, and guest management.

**13 operation(s)**:

_investigation_
- `create_local_user(username: text, password: password, email: text, first_name: text, last_name: text, [active: checkbox], [additional_fields: json])` — Create Local User
- `get_ldap_user(output_mode: select)` — Get Specific LDAP User
- `get_ldap_user_list([limit: integer], [offset: integer])` — Get LDAP User List
- `get_local_user(output_mode: select)` — Get Specific Local User
- `get_radius_user(output_mode: select)` — Get Specific Radius User
- `get_radius_user_list([limit: integer], [offset: integer])` — Get Radius User List
- `get_schema()` — Get Schema
- `get_userlockout_policy()` — Get User Lockout Policy Info
- `get_users([limit: integer], [offset: integer])` — Get Local User List
- `make_generic_request(endpoint: text, method: select, [params: json], [data: json], [headers: json])` — Make Generic Request
- `update_ldapuser_status(userid: text, active: checkbox)` — Update LDAP User Status
- `update_radiususer_status(userid: text, active: checkbox)` — Update Radius User Status
- `update_user_status(userid: text, active: checkbox)` — Update Local User Status


### `gogetssl` v1.0.0 _(installed)_
_GOGETSSL_

GOGETSSL offers SSL/TLS certificates and digital security solutions to secure websites, emails, and networks. With this connector, users can enhance security, streamline certificate management, and ensure trusted encryption for online communications

**18 operation(s)**:

- `add_ssl_order()` — Add SSL Order
- `add_ssl_renew_order()` — Add SSL Renew Order
- `add_ssl_san_order()` — Add SSL SAN Order
- `cancel_order()` — Cancel Order
- `decode_csr()` — Decode CSR
- `generate_csr()` — Generate CSR
- `get_all_orders_status()` — Get All Orders Status
- `get_all_products()` — Get All Products
- `get_domain_alternative()` — Get Domain Alternative
- `get_domain_emails()` — Get Domain Emails
- `get_domain_emails_for_geo_trust()` — Get Geotrust Approval Emails
- `get_domain_from_whois()` — Get Approver Emails
- `get_orders_details()` — Get Orders Details
- `get_orders_metadata()` — Get Orders Metadata
- `get_product_details()` — Get Product Details
- `get_total_order_count()` — Get Total Order Count
- `reissue_ssl_order()` — Reissue SSL Order
- `validate_csr()` — Validate CSR


### `jumpcloud` v1.1.0 _(installed)_
_JumpCloud_

JumpCloud is Directory-as-a-Service (DaaS) is the single point of authority to authenticate, authorize, and manage the identities of a business's employees and the systems and IT resources they need access to.

**7 operation(s)**:

- `create_command()` — Create Command
- `get_commands()` — Get Commands
- `get_organizations()` — Get Organizations
- `get_systems()` — Get Systems
- `get_users()` — Get Users
- `manage_associations_of_command()` — Manage Command Associations
- `trigger_command()` — Trigger Command


---

## Automation controller

### `ansible-tower` v2.0.0 _(installed)_
_Ansible Tower_

Ansible Tower connector perform automated operations, such as retrieving job status, launching jobs, retrieving job template, list job, list users etc from resources within Tower.

**16 operation(s)**:

- `cancel_job()` — Cancel Job
- `create_host_for_inventory()` — Create Host for Inventory
- `delete_host()` — Delete Host
- `get_credentials()` — Get Credentials
- `get_hosts_for_inventory()` — Get Hosts for Inventory
- `get_inventories()` — Get Inventories
- `get_job_status()` — Get Job Status
- `get_job_templates()` — Get Job Templates
- `get_jobs()` — Get Jobs
- `get_specific_job_events()` — Get Specific Job Event
- `get_specific_job_template_details()` — Get Specific Job Template Details
- `get_templates_for_inventory()` — Get Templates for Inventory
- `launch_job_template()` — Launch Job Template
- `list_job_templates()` — List Job Templates
- `list_users()` — List Users
- `relaunch_job()` — Relaunch a Job


### `connectwise-manage` v2.1.1 _(installed)_
_ConnectWise Manage_

ConnectWise has a CRM, ticketing system, help desk, and tools for project management, billing, and procurement.

**7 operation(s)**:

- `create_service_note()` — Create Service Note
- `create_ticket()` — Create Ticket
- `delete_ticket()` — Delete Ticket
- `get_boards()` — Get Boards
- `get_companies()` — Get Companies
- `get_ticket()` — Get Ticket
- `update_ticket()` — Update Ticket


### `radware-alteon` v1.0.0 _(installed)_
_Radware Alteon_

Radware Alteon is a robust and feature-rich application delivery controller that helps organizations optimize application performance, enhance security, and ensure high availability, making it a valuable component of modern IT infrastructure

**5 operation(s)**:

- `add_table_element()` — Add Table Element
- `delete_table_element()` — Delete Table Element
- `edit_table_element()` — Edit Table Element
- `view_table()` — View Table
- `view_table_element()` — View Table Element


---

## Breach and Attack Simulation (BAS)

### `ridgebot` v1.0.1 _(installed)_
_Ridge Security RidgeBot_

RidgeBot validates security vulnerabilities in your organization by using real POC codes to exploit the vulnerability. This connector facilitates automated operation such as creating and executing penetration testing tasks.

**5 operation(s)**:

- `create_task()` — Create Task
- `generate_and_download()` — Generate And Download
- `get_task_info()` — Get Task Info
- `get_task_statistics()` — Get Task Statistics
- `stop_task()` — Stop Task


### `safebreach` v1.0.0 _(installed)_
_SafeBreach_

SafeBreach simulates attacks across the kill chain, to validate security policy, configuration, and effectiveness. Use this connector to get a simulation from SafeBreach and rerun the simulation on your system

**2 operation(s)**:

- `get_simulation()` — Get Simulation
- `rerun_simulation()` — Rerun Simulation


### `verodin` v1.0.0 _(installed)_
_Verodin_

Verodin’s Instrumented Security platform is a foundational technology. It is a new approach to managing your cyber-security lifecycle

**12 operation(s)**:

- `cancel_job()` — Cancel Job
- `delete_simulation()` — Delete Simulation
- `delete_zone()` — Delete Zone
- `get_job()` — Get Job
- `get_job_actions()` — Get Job Actions
- `get_map()` — Get Map
- `get_nodes()` — Get Nodes
- `get_simulation()` — Get Simulation
- `get_simulations_actions()` — Get Simulations Actions
- `get_zone()` — Get Zone
- `run_job()` — Run Job
- `run_simulation()` — Run Simulation


---

## CMDB

### `servicenow` v3.5.0 _(installed, ingestion)_
_ServiceNow_

ServiceNow connector provides functionality to create, read, update and delete records of Table and Catalog type

**34 operation(s)**:

_investigation_
- `add_item_to_cart(sys_id: text, [other_fields: json], [submit_order: checkbox])` — Add Item to Cart
- `advance_search(table_name: text, adv_query: text, [sysparm_limit: text])` — Advanced Search
- `create_SIR(table_name: text, short_description: textarea, [description: textarea], [location: text], [category: select], [severity: select], [state: select], [risk_score: integer], [impact: select], [work_notes: text], [urgency: select], [other_fields: json])` — Create Security Incident
- `create_change_request(change_type: select)` — Create Change Request
- `create_change_request_task(change_sys_id: text, short_description: text, description: textarea, [other_params: json])` — Create Change Request Task
- `create_incident(caller_id: text, short_description: textarea, [description: textarea], [location: text], [category: text], [severity: text], [urgency: text], [state: text], [impact: text], [work_notes: text], [assigned_to: text], [assignment_group: text], [other_fields: json])` — Create Incident
- `create_new_record(table_name: text, value: text)` — Create Table Record
- `delete_SIR(sir_sys_id: text, table_name: text)` — Delete Security Incident
- `delete_cart_item(cart_item_id: text)` — Delete Cart Item
- `delete_change_request(change_request_type: select, sys_id: text)` — Delete Change Request
- `delete_change_request_task(change_sys_id: text, task_sys_id: text)` — Delete Change Request Task
- `delete_file(sys_id: text)` — Delete Attachment
- `download_file(sys_id: text)` — Download Attachment
- `fetch_incidents(table_name: text, adv_query: text, start_time: datetime, end_time: datetime, [sysparm_limit: text])` — Fetch Incidents
- `get_SIR(table_name: text, adv_query: text, [sysparm_limit: integer])` — Search Security Incident Record
- `get_all_change_requests(change_request_type: select, [order: text], [sysparm_offset: integer], [sysparm_limit: integer], [other_filter_params: json], [textSearch: text])` — Get All Change Requests
- `get_assignment_group()` — Get Assignment Groups
- `get_attachments(table_sys_id: text)` — Get Attachments
- `get_cart()` — Get Cart
- `get_catalogs([sys_id: text])` — Get Catalogs
- `get_categories_for_catalog(sys_id: text)` — Get Catalog Categories
- `get_change_request_details(change_request_type: select, sys_id: text)` — Get Change Request Details
- `get_change_request_tasks(change_sys_id: text, [order: text], [sysparm_offset: integer], [sysparm_limit: integer])` — Get Change Request Tasks
- `get_items([sys_id: text])` — Get Items
- `get_location()` — Get Location
- `get_users(response_fields: multiselect)` — Get Users
- `search_record(table_name: text, column_name: text, value: text, [active: checkbox])` — Search Table Record
- `submit_sample(table_name: text, table_sys_id: text, input: select)` — Submit Attachment
- `update_SIR(sys_id: text, table_name: text, [state: select], [severity: select], [description: textarea], [work_notes: textarea], [risk_score: integer], [other_fields: json])` — Update Security Incident
- `update_cart_item(cart_item_id: text, [other_fields: json])` — Update Cart Item
- `update_change_request(change_request_type: select, sys_id: text, [other_params: json])` — Update Change Request
- `update_change_request_task(change_sys_id: text, task_sys_id: text, [other_params: json])` — Update Change Request Task
- `update_servicenow_incident(sys_id: text, [state: text], [severity: text], [description: textarea], [work_notes: textarea], [category: textarea], [subcategory: textarea], [other_fields: json])` — Update ServiceNow Incident
- `update_servicenow_ticket(table_name: text, sys_id: text, [description: textarea], [payload: json])` — Update ServiceNow Table Record


### `servicenow_tmobile` v3.2.0 _(installed)_
_ServiceNow T-Mobile_

ServiceNow connector provides functionality to create, read, update and delete records of Table and Catalog type

**32 operation(s)**:

_investigation_
- `add_item_to_cart(sys_id: text, [other_fields: json], [submit_order: checkbox])` — Add Item to Cart
- `advance_search(table_name: text, adv_query: text, [sysparm_limit: text])` — Advanced Search
- `create_SIR(short_description: textarea, [description: textarea], [location: text], [category: select], [severity: select], [state: select], [risk_score: integer], [impact: select], [work_notes: text], [urgency: select], [other_fields: json])` — Create Security Incident
- `create_change_request(change_type: select)` — Create Change Request
- `create_change_request_task(change_sys_id: text, short_description: text, description: textarea, [other_params: json])` — Create Change Request Task
- `create_incident(caller_id: text, short_description: textarea, [description: textarea], [location: text], [category: text], [severity: text], [urgency: text], [state: text], [impact: text], [work_notes: text], [assigned_to: text], [assignment_group: text], [other_fields: json])` — Create Incident
- `create_new_record(table_name: text, value: text)` — Create Table Record
- `delete_SIR(sir_sys_id: text)` — Delete Security Incident
- `delete_cart_item(cart_item_id: text)` — Delete Cart Item
- `delete_change_request(change_request_type: select, sys_id: text)` — Delete Change Request
- `delete_change_request_task(change_sys_id: text, task_sys_id: text)` — Delete Change Request Task
- `download_file(sys_id: text)` — Download File
- `extract_value_by_column_and_query(table_name: text, column_name: text, query: text, [filter_out_blank_field: checkbox], [deduplicate_values: checkbox], [merge_ips_into_cidrs: checkbox])` — Extract Table Value by Column and Query
- `get_SIR(table_name: text, adv_query: text, [sysparm_limit: text])` — Search Security Incident Record
- `get_all_change_requests(change_request_type: select, [order: text], [sysparm_offset: integer], [sysparm_limit: integer], [other_filter_params: json], [textSearch: text])` — Get All Change Requests
- `get_assignment_group()` — Get Assignment Groups
- `get_attachments(table_sys_id: text)` — Get Attachments
- `get_cart()` — Get Cart
- `get_catalogs([sys_id: text])` — Get Catalogs
- `get_categories_for_catalog(sys_id: text)` — Get Catalog Categories
- `get_change_request_details(change_request_type: select, sys_id: text)` — Get Change Request Details
- `get_change_request_tasks(change_sys_id: text, [order: text], [sysparm_offset: integer], [sysparm_limit: integer])` — Get Change Request Tasks
- `get_items([sys_id: text])` — Get Items
- `get_location()` — Get Location
- `get_users(response_fields: multiselect)` — Get Users
- `search_record(table_name: text, column_name: text, value: text, [active: checkbox])` — Search Table Record
- `update_SIR(sys_id: text, [state: select], [severity: select], [description: textarea], [work_notes: textarea], [risk_score: integer], [other_fields: json])` — Update Security Incident
- `update_cart_item(cart_item_id: text, [other_fields: json])` — Update Cart Item
- `update_change_request(change_request_type: select, sys_id: text, [other_params: json])` — Update Change Request
- `update_change_request_task(change_sys_id: text, task_sys_id: text, [other_params: json])` — Update Change Request Task
- `update_servicenow_incident(sys_id: text, [state: text], [severity: text], [description: textarea], [work_notes: textarea], [other_fields: json])` — Update ServiceNow Incident
- `update_servicenow_ticket(table_name: text, sys_id: text, [description: textarea], [payload: json])` — Update ServiceNow Table Record


---

## Case Management

### `thehive` v1.0.0 _(installed)_
_TheHive_

TheHive Security Incident Response Platform involves connecting external security tools, systems, or data sources with TheHive's platform. This integration facilitates centralized incident management, response coordination, and automation, enhancing overall security operations by streamlining incident detection, investigation, and resolution processes.

**21 operation(s)**:

- `add_alert_attachment()` — Add Alert Attachment
- `create_alert()` — Create Alert
- `create_case()` — Create Case
- `create_observable_in_alert()` — Create Observable in Alert
- `create_observable_in_case()` — Create Observable in Case
- `create_task()` — Create Task in Case
- `delete_alert()` — Delete Alert
- `delete_alert_attachment()` — Delete Alert Attachment
- `delete_case()` — Delete Case
- `delete_observable()` — Delete Observable
- `delete_task()` — Delete Task
- `download_alert_attachment()` — Download Alert Attachment
- `get_alert()` — Get Alert
- `get_alert_attachment()` — Get Alert Attachment
- `get_case()` — Get Case
- `get_observable()` — Get Observable
- `get_task()` — Get Task
- `update_alerts()` — Update Alerts
- `update_case()` — Update Case
- `update_observable()` — Update Observable
- `update_task()` — Update Task


---

## Case Management,Threat Intelligence

### `proofpoint-trap` v1.1.0 _(installed)_
_Proofpoint TRAP_

Perform actions like Get incident details, Retrieve incidents, Close Incidents and Create Alert from JSON source using Proofpoint TRAP

**5 operation(s)**:

- `close_incidents()` — Close Incidents
- `create_alert_from_json_source()` — Create Alert from JSON Source
- `execute_api_request()` — Execute an API Request
- `get_incident_details()` — Get Incident Details
- `get_incidents()` — Get Incidents


---

## Centralized Security Management

### `fortinet-fortimanager` v4.1.2 _(installed, ingestion)_
_Fortinet FortiManager_

Fortinet FortiManager provides easy centralized configuration, policy-based provisioning, update management and end-to-end network monitoring for your Fortinet-installed environment.

**70 operation(s)** (+4 hidden):

_containment_
- `adom_block_ip([adom: text], ngfw_mode: select, pkg: select, [pkg_path: text], policy_name: text, ip_group_name: text, ip: text)` — ADOM Level Block IP Address
- `block_applications(level_type: select)` — Block Application
- `block_url(level_type: select)` — Block URL
- `global_block_ip(pkg: select, [pkg_path: text], policy_type: select, policy_name: text, ip_group_name: text, ip: text)` — Global Level Block IP Address

_investigation_
- `create_address(level_type: select, type: select, [policy-group: text], [comment: text], [additional_args: json])` — Create Address
- `create_address_group(level_type: select, [type: select], member: text, [exclude: checkbox], [comment: text], [additional_args: json])` — Create Address Group
- `create_custom_service(level_type: select, [category: text], [proxy: select], [app-category: text], [app-service-type: select], [application: text], [check-reset-range: select], [helper: text], [session-ttl: text], [tcp-halfclose-timer: text], [tcp-halfopen-timer: text], [tcp-rst-timer: integer], [tcp-timewait-timer: integer], [udp-idle-timer: integer], [comment: text], [additional_args: json])` — Create Custom Service
- `create_incident([adom: text], reporter: text, endpoint: text, [epid: text], [euid: text], [category: select], [severity: select], [status: select], [description: text])` — Create Incident
- `create_ldap_server(level_type: select, name: text, username: text, password: password, dn: text, server: text, [account-key-processing: select], [antiphish: select], [group-member-check: select], [interface-select-method: select], [obtain-user-info: select], [source-ip: text], [source-port: text], [additional_args: json])` — Create LDAP Server
- `create_policy(level_type: select, pkg: text, name: text, srcintf: text, dstintf: text, service: text, schedule: text, srcaddr: text, dstaddr: text, action: select, [srcaddr6: text], [dstaddr6: text], [ngfw_mode: select], [status: select], [comments: text], [logtraffic: select], [additional_args: json])` — Create Firewall Policy
- `create_policy_package(level_type: select, type: select, [additional_args: json])` — Create Policy Package
- `create_service_group(level_type: select, member: text, [proxy: select], [comment: text], [additional_args: json])` — Create Service Group
- `create_user_group(level_type: select, name: text, member: text, [additional_args: json])` — Create User Group
- `delete_address(level_type: select)` — Delete Address
- `delete_address_group(level_type: select)` — Delete Address Group
- `delete_custom_service(level_type: select)` — Delete Custom Service
- `delete_ldap_server(level_type: select, name: text)` — Delete LDAP Server
- `delete_policy(level_type: select, [ngfw_mode: select], pkg: text, policy: text)` — Delete Firewall Policy
- `delete_policy_package(level_type: select, [pkg_path: text])` — Delete Policy Package
- `delete_service_group(level_type: select)` — Delete Service Group
- `delete_user_group(level_type: select, name: text)` — Delete User Group
- `get_address_groups(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Address Groups List
- `get_addresses(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Addresses List
- `get_adom_blocked_ip([adom: text], ngfw_mode: select, pkg: select, [pkg_path: text], policy_name: text, ip_group_name: text)` — ADOM Level Get Blocked IP Addresses
- `get_adom_policy([adom: text], pkg: select, [pkg_path: text], [ngfw_mode: select], [policy_name: text])` — List ADOM Firewall Policies
- `get_adom_policy_package([adom: text], [pkg: select], [pkg_path: text])` — List ADOM Policy Package
- `get_alert_event([adom: text], [filter: text], [time-range: checkbox], [limit: integer], [offset: integer])` — Get Events
- `get_alert_logs(alertid: text, [adom: text], [time-order: select], [limit: integer], [offset: integer])` — Get Event Details
- `get_application_control_list(level_type: select)` — Get Applications Control List
- `get_blocked_applications(level_type: select)` — Get Blocked Applications
- `get_blocked_urls(level_type: select)` — Get Blocked URLs
- `get_custom_service(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Custom Services List
- `get_device_groups(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Device Groups List
- `get_devices([adom: text], [device_name: text])` — Get Device List
- `get_dynamic_interface(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Dynamic Interface List
- `get_global_blocked_ip(pkg: select, [pkg_path: text], policy_type: select, policy_name: text, ip_group_name: text)` — Global Level Get Blocked IP Addresses
- `get_global_policy(pkg: select, [pkg_path: text], policy_type: select, [policy_name: text])` — List Global Firewall Policies
- `get_global_policy_package([pkg: text], [pkg_path: text])` — List Global Policy Package
- `get_incident_events(incid: text, [adom: text], [attachtype: select], [limit: integer], [offset: integer])` — Get Events Related to Incident
- `get_incidents([adom: text], [incids: text], [detail-level: select], [filter: text], [sort-by: select], [limit: integer], [offset: integer])` — List Incident
- `get_ldap_server(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get LDAP Server List
- `get_list_of_applications()` — Get Applications Detail
- `get_service_categories(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Service Categories List
- `get_service_group(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Service Groups List
- `get_ssl_vpn(device: text, vdom: text, [option: select])` — Get SSL VPN Settings
- `get_user_group(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get User Groups List
- `get_web_filter(level_type: select, [fields: text], [filter: text], [range_limit: integer], [range_offset: integer], [sortings: select])` — Get Web Filter List
- `global_assign_policy(pkg: select, adom: multiselect, [dest_pkg: multiselect], [excluded: checkbox])` — Assign Global Policy Package
- `install_policy([adom: text], pkg: select, scopes: json, [adom_rev_comments: text], [adom_rev_name: text], [dev_rev_comments: text], [flags: text])` — Install Policy
- `install_policy_status(task: text)` — Get Installation Policy Package Status
- `move_policy(level_type: select, [ngfw_mode: select], pkg: text, policy: text, target: text, option: select)` — Move Firewall Policy
- `reinstall_policy([adom: text], pkg: select, scopes: json, [flags: text], [pkg_path: text])` — Re-install Policy
- `update_address(level_type: select, type: select, [policy-group: text], [comment: text], [additional_args: json])` — Update Address
- `update_address_group(level_type: select, method: multiselect, [exclude: checkbox], [comment: text], [additional_args: json])` — Update Address Group
- `update_custom_service(level_type: select, [category: text], [proxy: select], [app-category: text], [app-service-type: select], [application: text], [check-reset-range: select], [helper: text], [session-ttl: text], [tcp-halfclose-timer: text], [tcp-halfopen-timer: text], [tcp-rst-timer: integer], [tcp-timewait-timer: integer], [udp-idle-timer: integer], [comment: text], [additional_args: json])` — Update Custom Service
- `update_incident(incid: text, [adom: text], [endpoint: text], [epid: text], [euid: text], [category: select], [severity: select], [status: select], [description: text], [lastrevision: text], [lastuser: text])` — Update Incident
- `update_ldap_server(level_type: select, name: text, [username: text], [password: password], [dn: text], [server: text], [account-key-processing: select], [antiphish: select], [group-member-check: select], [interface-select-method: select], [obtain-user-info: select], [source-ip: text], [source-port: text], [additional_args: json])` — Update LDAP Server
- `update_policy(level_type: select, pkg: text, name: text, method: multiselect, action: select, [ngfw_mode: select], [status: select], [schedule: text], [comments: text], [additional_args: json])` — Update Firewall Policy
- `update_policy_package(level_type: select, [type: select], [additional_args: json])` — Update Policy Package
- `update_service_group(level_type: select, method: multiselect, [proxy: select], [comment: text], [additional_args: json])` — Update Service Group
- `update_ssl_vpn(device: text, vdom: text, [default-portal: text], [source-interface: text], [port: text], [servercert: text], [authentication-rule: checkbox], [source-address: text], [source-address-negate: select], [source-address6: text], [source-address6-negate: select], [user-peer: text], [additional_args: json])` — Update SSL VPN Settings
- `update_user_group(level_type: select, name: text, method: multiselect, [additional_args: json])` — Update User Group

_remediation_
- `adom_unblock_ip([adom: text], ngfw_mode: select, pkg: select, [pkg_path: text], policy_name: text, ip_group_name: text, ip: text)` — ADOM Level Unblock IP Address
- `global_unblock_ip(pkg: select, [pkg_path: text], policy_type: select, policy_name: text, ip_group_name: text, ip: text)` — Global Level Unblock IP Address
- `unblock_application(level_type: select)` — Unblock Application
- `unblock_url(level_type: select)` — Unblock URL


### `fortinet-fortimanager-json-rpc` v1.2.5 _(installed)_
_Fortinet FortiManager JSON RPC_

The Fortinet FortiManager JSON RPC Connector is an advanced connector with freeform actions to use the JSON-RPC API directly. This connector puts the onus on the user to understand the FortiManager API. To use the connector that simplify actions please see the original Fortinet FortiManager Connector.

**10 operation(s)**:

_investigation_
- `get_device_vulnerabilities(adom_oid: integer, [fortios_only: checkbox], [simplify: checkbox], [exclude_impacted_versions: checkbox], [severity_filter: select])` — Get Device Vulnerabilities
- `get_fortimanager_device_stats([adom: text], [vdom: text], [device_filter: json], [device_fields: json], [device_options: json], [include_policies: checkbox], [include_policy_stats: checkbox], [merge_stats: checkbox], [include_policy_target: checkbox], [include_uptime: checkbox], [policy_fields: json], [stat_fields: json], [include_resource_usage: checkbox], [resource_summary_mode: select], [resource_metrics: multiselect], [resource_time_windows: multiselect], [additional_calls: json])` — Get FortiManager Device Stats
- `get_package_policies(adom: text, policy_package: text, [fields: text])` — Get Package Policies
- `json_rpc_add(url: text, data: json)` — JSON RPC Add
- `json_rpc_delete(url: text, data: json)` — JSON RPC Delete
- `json_rpc_execute(url: text, data: json, [track_task: checkbox])` — JSON RPC Exec
- `json_rpc_freeform(method: select, data: json)` — JSON RPC Freeform
- `json_rpc_get(url: text, [data: json])` — JSON RPC Get
- `json_rpc_gui(gui_method: select, url: text, [data: json])` — JSON RPC GUI
- `json_rpc_set(url: text, data: json)` — JSON RPC Set


### `fortinet-fortimanager-policy-management` v1.0.1 _(installed)_
_Fortinet FortiManager Policy Management_

The Fortinet FortiManager

**1 operation(s)**:

_investigation_
- `get_package_policies(adom: text, policy_package: text, [fields: text])` — Get Package Policies


---

## Cloud Security

### `azure-network-security-group` v1.2.0 _(installed)_
_Azure Network Security Group_

Azure network security group to filter network traffic to and from Azure resources in an Azure virtual network. This connector facilitates automated operations to get list of network security groups, get details of network security group, create network security group, update network security group and delete network security group etc.

**10 operation(s)** (+5 hidden):

- `create_network_security_group()` — Create Network Security Group
- `delete_network_security_group()` — Delete Network Security Group
- `get_network_security_group_info()` — Get Network Security Group Info
- `list_of_network_security_groups()` — List Network Security Groups
- `update_network_security_group()` — Update Network Security Group


### `cisco-umbrella-investigate` v2.0.0 _(installed)_
_Cisco Umbrella Investigate_

Cisco Umbrella Investigate provides the most complete view of the relationships and evolution of domains, IPs, autonomous systems (ASNs), and file hashes. Investigate is accessible using a web console and an API and its rich threat intelligence adds the security context needed to uncover and predict threats.

**3 operation(s)**:

- `domain_information()` — Get Information About a Domain
- `latest_malicious_domains()` — Fetch Latest Malicious Domains of an IP
- `whois()` — Fetch WHOIS Information


### `cloudpassage-halo` v1.0.0 _(installed)_
_CloudPassage Halo_

Provide investigative actions like list process, list user and list vulnerabilities

**7 operation(s)**:

- `get_cve_details()` — Get CVE Details
- `get_system_info()` — Get System Information
- `get_user()` — Get Local User Account Details
- `list_server_processes()` — List Server Processes
- `list_servers()` — List Server
- `list_users()` — List All Local User Accounts
- `list_vulnerabilities()` — List Server Vulnerabilities


### `fortinet-forticnapp` v1.1.0 _(installed)_
_Lacework FortiCNAPP_

Lacework delivers end-to-end visibility into what’s happening across your cloud environment, including detecting threats, vulnerabilities, misconfigurations, and unusual activity, so you can innovate with speed and safety.

**11 operation(s)**:

- `add_comment_to_alert()` — Add Comment to Alert
- `close_alert()` — Close Alert
- `get_alert_details()` — Get Alerts Details
- `get_alert_entities()` — Get Alert Entities
- `get_alert_entity_details()` — Get Alert Entity Details
- `lql_query()` — Run LQL Query
- `search_alerts()` — Search Alerts
- `search_configuration()` — Search Configuration
- `search_container_vulnerabilities()` — Search Container Vulnerabilities
- `search_host_vulnerabilities()` — Search Host Vulnerabilities
- `send_custom_request()` — Execute an API Call


### `fortinet-forticwp` v1.0.0 _(installed)_
_Fortinet FortiCWP_

Fortinet's FortiCWP integrates with APIs provided by cloud vendors including AWS, Azure, and Google Cloud Platform to monitor and track all security components, including configurations, user activity, and traffic flow logs. This Connector automated operations such as retrieving the user account details from Fortinet FortiCWP, etc

**5 operation(s)**:

- `get_account_role()` — Get User Account Details
- `get_account_severity_level()` — Get Account Severity Level
- `get_alert_by_filter()` — Get Alerts
- `get_alert_severities()` — Get Alert Severities
- `get_resource_map()` — Get Resource Map


### `fortinet-fortindr-cloud` v1.1.0 _(installed, ingestion)_
_Fortinet FortiNDR Cloud_

Fortinet FortiNDR Cloud is a cloud-native network detection and response solution built for the rapid detection of threat activity, investigation of suspicious behavior, proactive hunting for potential risks, and directing a fast and effective response to active threats. This connector facilitates automated operation related to detection, entity, and sensors.

**19 operation(s)**:

_investigation_
- `delete_pcap_task(task_uuid: text)` — Delete PCAP Task
- `download_pcap_task_file(task_uuid: text, [file_name: text])` — Download PCAP Task File
- `get_detection_events(detection_uuid: text, [limit: integer], [offset: integer])` — Get Detection Events
- `get_detection_rule_details(rule_uuid: text, [rule_account_uuid: text])` — Get Detection Rule Details
- `get_detection_rule_events(rule_uuid: text, [limit: integer], [offset: integer])` — Get Detection Rule Events List
- `get_detection_rule_indicators([rule_uuid: text], [detection_muted: checkbox], [detection_status: multiselect], [sort_by: text], [sort_order: select], [limit: integer], [offset: integer])` — Get Detection Rule Indicators
- `get_detection_rules([rule_account_uuid: text], [search: text], [has_detections: checkbox], [detection_device_ip: text], [indicator_value: text], [severity: multiselect], [confidence: multiselect], [category: multiselect], [rule_account_muted: checkbox], [enabled: checkbox], [sort_by: select], [sort_order: select], [limit: integer], [offset: integer])` — Get Detection Rules List
- `get_detections([rule_uuid: text], [sensor_id: text], [status: multiselect], [device_ip: text], [muted: checkbox], [muted_device: checkbox], [muted_rule: checkbox], [include: multiselect], [indicator_value: text], [created_start_date: datetime], [created_end_date: datetime], [sort_by: select], [sort_order: select], [limit: integer], [offset: integer])` — Get Detections List
- `get_devices_with_detection([account_uuid: text], [search: text], [muted: checkbox], [muted_device: checkbox], [muted_rule: checkbox], [status: multiselect], [sort_by: select], [sort_order: select], [limit: integer], [offset: text])` — Get Devices with Detection
- `get_entity_pdns(entity: text, [record_type: select], [start_date: datetime], [end_date: datetime], [limit: integer])` — Get Passive DNS Details
- `get_entity_summary(entity: text)` — Get Entity Summary
- `get_entity_tracking(entity_type: select, entity_value: text, [start_time: datetime], [end_time: datetime], [limit: integer], [offset: integer])` — Get Entity Tracking
- `get_pcap_tasks([task_uuid: text], [sensor_id: text], [created_start: datetime], [created_end: datetime], [search_text: text], [has_files_only: checkbox], [page_size: integer], [page_num: integer])` — Get PCAP Tasks
- `get_sensors([sensor_id: text], [account_code: text], [include: multiselect])` — Get Sensors List
- `get_telemetry_bandwidth([account_code: text], [start_date: datetime], [end_date: datetime], [interval: select], [latest_each_month: text], [sort_order: select], [limit: integer], [offset: text])` — Get Telemetry Bandwidth
- `get_telemetry_events([sensor_id: text], [account_code: text], [interval: select], [start_date: datetime], [end_date: datetime], [event_type: select], [group_by: select])` — Get Telemetry Events
- `get_telemetry_packetstats([sensor_id: text], [interval: select], [start_date: datetime], [end_date: datetime], [group_by: select])` — Get Telemetry Packetstats
- `resolve_detection(detection_uuid: text, resolution: select, [resolution_comment: text])` — Resolve Detection
- `terminate_pcap_task(task_uuid: text)` — Terminate PCAP Task


### `fortinet-fortiweb-cloud` v2.0.0 _(installed)_
_Fortinet FortiAppSec Cloud_

FortiAppSec Cloud simplifies and strengthens application security and delivery across hybrid and cloud environments. This SaaS platform secures network availability and accelerates application performance while delivering consistent security.

**13 operation(s)**:

- `add_ip_protection()` — Add IP Protection
- `delete_ip_protection()` — Delete IP Protection
- `execute_an_api_call()` — Execute an API Request
- `get_application_list()` — Get Applications List
- `get_incident_aggregated_details()` — Get Incident Aggregated Details
- `get_incident_dashboard_details()` — Get Incident Dashboard Details
- `get_incident_details()` — Get Incident Details
- `get_incident_list()` — Get Incidents List
- `get_incident_timeline_details()` — Get Incident Timeline Details
- `get_insight_events()` — Get Insight Events
- `get_insight_events_summary()` — Get Insight Events Summary
- `get_ip_protection()` — Get IP Protection
- `update_geo_ip_block_list()` — Update Geo IP Block List


### `microsoft-defender-for-cloud` v1.2.0 _(installed)_
_Microsoft Defender For Cloud_

Microsoft Defender for Cloud is a solution for cloud security posture management (CSPM) and cloud workload protection (CWP) that finds weak spots across your cloud configuration, helps strengthen the overall security posture of your environment, and can protect workloads across multicloud and hybrid environments from evolving threat.This connector facilitates the automated operations related to alerts, managing APS, ATP etc.

**15 operation(s)**:

- `get_alert_list()` — Get Alert List
- `get_aps()` — Get APS
- `get_aps_list()` — Get APS List
- `get_atp()` — Get ATP
- `get_jit_list()` — Get JIT List
- `get_locations_list()` — Get Locations List
- `get_secure_score()` — Get Secure Score
- `get_storage_list()` — Get Storage List
- `get_subscriptions_list()` — Get Subscriptions List
- `list_management_groups()` — Get Management Group List
- `list_subscriptions_by_management_group_id()` — Get Subscription List By Management Group ID
- `search_alerts()` — Search Alerts
- `update_alert()` — Update Alert
- `update_aps()` — Update APS
- `update_atp()` — Update ATP


### `netapp-ontap` v1.0.0 _(installed)_
_NetApp ONTAP_

ONTAP helps you create a storage infrastructure that reduces costs, accelerates critical workloads, and protects and secures data across your hybrid multicloud.

**4 operation(s)**:

- `get_security_accounts()` — Get Security Accounts
- `get_security_audit_messages()` — Get Security Audit Messages
- `get_security_roles()` — Get Security Roles
- `update_user_password()` — Update User Password


### `rapid7-insightcloudsec` v1.0.0 _(installed)_
_Rapid7 InsightCloudSec_

InsightCloudSec secures your public cloud environment from development to production with a modern, integrated, and automated approach. This connector facilitates automated operation such as retrieving resource related information.

**3 operation(s)**:

- `get_list_resource_tags()` — Get Resource Tags List
- `get_resource_details()` — Get Resource Details
- `run_resource_query()` — Run Resource Query


### `trend-micro-cloud-app-security` v1.0.0 _(installed)_
_Trend Micro Cloud App Security_

Trend Micro Cloud App Security provides advanced protection for the following cloud applications and services to enhance security with powerful enterprise-class threat and data protection control: Microsoft Office 365 services (Exchange Online, SharePoint Online, OneDrive, Microsoft Teams), Box, Dropbox, and Google Workspace (Google Drive, Gmail).Cloud App Security provides protection against ransomware, phishing, Business Email Compromise (BEC), zero-day and hidden malware, and unauthorized transmission of sensitive data. It integrates cloud-to-cloud with the protected applications and services to maintain high availability and administrative functionality.

**10 operation(s)**:

- `get_blocked_list()` — Get Blocked List
- `get_email()` — Get Email
- `get_email_action_result()` — Get Email Action Result
- `get_quarantine_events()` — Get Quarantine Events
- `get_security_logs()` — Get Security Logs
- `get_user_action_result()` — Get User Action Result
- `get_virtual_analyzer_report()` — Get Virtual Analyzer Report
- `take_action_on_email()` — Take Action On Email
- `take_action_on_user()` — Take Action On User
- `update_blocked_list()` — Update Blocked List


### `zscaler-internet-access` v1.0.0 _(installed)_
_Zscaler Internet Access_

Zscaler Internet Access (ZIA) connector enables automated operations such as Get Firewall Filtering Rules, Get Specific Firewall Filtering Rule, Get Time Windows, Get Network Applications, Get Network Services, Get Network Services Groups, Get Network Applications Groups, and Execute an API Request.

**8 operation(s)**:

- `execute_api_request()` — Execute an API Request
- `get_firewall_filtering_rules()` — Get Firewall Filtering Rules
- `get_network_application_groups()` — Get Network Applications Groups
- `get_network_applications()` — Get Network Applications
- `get_network_service_groups()` — Get Network Services Groups
- `get_network_services()` — Get Network Services
- `get_specific_firewall_filtering_rule()` — Get Specific Firewall Filtering Rule
- `get_time_windows()` — Get Time Windows


---

## Cloud Security Log

### `symantec-cloudsoc` v1.0.0 _(installed)_
_Symantec CloudSOC_

The Symantec CloudSOC platform enables companies to confidently leverage cloud applications and services while staying safe, secure, and compliant

**9 operation(s)**:

_containment_
- `modify_user(email: text, action: select)` — Modify User Activation

_investigation_
- `get_audit_data_source()` — Get Audit Sources
- `get_audit_service(latest_date: text, earliest_date: text, [ds_id: text], [service_type: select], [allowed: checkbox], [blocked: checkbox])` — Get Audit Services
- `get_audit_summary(latest_date: text, earliest_date: text, [ds_id: text], [service_type: select], [allowed: checkbox], [blocked: checkbox], [resolution: select])` — Get Audit Summary
- `get_audit_user(latest_date: text, earliest_date: text, [ds_id: text], [service_type: select], [allowed: checkbox], [blocked: checkbox], [next_page: text], [resolution: select], [service_ids: text])` — Get Audit Users
- `get_audit_username(user_ids: text, [limit: text])` — Get Audit Usernames
- `get_content_iqprofile([profile_name: text], [api_enabled: checkbox])` — Get Content IQ Profile
- `get_logs(app: select, [user: text], [service: text], [severity: select], [inserted_timestamp: text], [updated_timestamp: text], [search: text], [from: integer], [limit: integer], [sort_inserted_timestamp: text], [sort: text], [threat_score: text])` — Get Event Logs
- `get_protect_policies([policy_name: text], [policy_type: select], [is_active: checkbox])` — Get Protect Policies


---

## Cloud access security broker (CASB)

### `fortinet-forticasb` v1.0.0 _(installed)_
_Fortinet FortiCASB_

FortiCASB (Cloud Access Security Broker) is Fortinet’s cloud-native CASB solution, designed for comprehensive visibility, compliance, data security, and threat protection across SaaS and IaaS environments via API integration.

**6 operation(s)** (+1 hidden):

- `get_datapatterns()` — Get Data Patterns
- `get_policies()` — Get Policies
- `get_resource_url_map()` — Get Resource URL Map
- `search_activity()` — Search Activity
- `search_alerts()` — Search Alerts


### `microsoft-casb` v2.0.0 _(installed)_
_Microsoft Defender for Cloud Apps_

Microsoft Cloud App Security is a Cloud Access Security Broker (CASB) that operates on multiple clouds. It provides rich visibility, control over data travel, and sophisticated analytics to identify and combat cyberthreats across all your cloud services.

**13 operation(s)**:

- `close_benign()` — Close Benign
- `close_false_positive()` — Close False Positive
- `close_true_positive()` — Close True Positive
- `fetch_activity()` — Fetch Activity
- `fetch_alert()` — Fetch Alert
- `fetch_entity()` — Fetch Entity
- `fetch_file()` — Fetch File
- `list_activities()` — List Activities
- `list_alerts()` — List Alerts
- `list_entities()` — List Entities
- `list_files()` — List Files
- `mark_alert_as_read()` — Mark Alert as Read
- `mark_alert_as_unread()` — Mark Alert as Unread


---

## Communication

### `slack` v3.2.0 _(installed)_
_Slack_

Slack is a cloud-based set of proprietary team collaboration tools and services. This connector facilitates automated operations like list channels, list users, send message etc. This release of Slack connector supports bi-directional communication between Slack and FortiSOAR, allowing you to leverage the power of FortiSOAR as part of your daily communications and threat investigation routines.

**21 operation(s)**:

_investigation_
- `add_reactions(channel: text, timestamp: text, name: text)` — Add Reactions
- `close_channel(channel: text)` — Close Channel
- `create_channel(name: text, [is_private: checkbox])` — Create Channel
- `create_group(group_name: text, [description: text], [handle: text], [channels: text], [include_count: checkbox], [team_id: text])` — Create User Group
- `create_multi_person_direct_message(create_by: select)` — Create Multi Person Direct Message
- `get_channel_info(channel: text, [include_locale: checkbox], [include_num_members: checkbox])` — Get Channel Information
- `get_conversations_replies(channel: text, ts: text, [include_all_metadata: checkbox], [inclusive: checkbox], [oldest: datetime], [latest: datetime], [limit: text], [create_attachments: checkbox])` — Get Conversations Replies
- `get_emojis([include_categories: checkbox])` — Get Emojis
- `get_message_history(channel: text, [cursor: text], [inclusive: checkbox], [oldest: datetime], [latest: datetime], [limit: integer])` — Get Message History
- `get_user(search_by: select)` — Get User Information
- `get_user_groups([include_count: checkbox], [include_disabled: checkbox], [include_users: checkbox], [team_id: text])` — Get User Groups
- `get_users_from_group(usergroup: text, [include_disabled: checkbox], [team_id: text])` — Get Users from User Group
- `invite_user_to_channel(channel: text, users: text)` — Invite Users To Channel
- `list_channels([exclude_archived: checkbox], [limit: integer], [types: multiselect], [cursor: text])` — Get Channels List
- `list_users([limit: integer], [cursor: text])` — Get User List
- `rename_channel(channel: text, name: text)` — Rename Channel
- `search_channel(search_name: text, search_type: select)` — Search Channel
- `send_input(input: json, [confirm_inputs: checkbox])` — Send Manual Input/Approval Form to Slack
- `send_message([channel: text], [email_id: text], message: text, [blocks: text], [attachments: text], [thread_ts: text])` — Send Message
- `update_users_in_user_group(usergroup: text, user_mail_list: text, [include_count: checkbox], [team_id: text])` — Update Users in User Group

_miscellaneous_
- `upload_file(path: select, [channel: text], [title: text], [file_name: text], [file_type: text], [comment: text])` — Upload File


---

## Communication and Coordination

### `bandwidth` v1.0.0 _(installed)_
_Bandwidth_

Bandwidth is the only API platform provider that owns a Tier 1 network, giving you better quality, rates, and control.

**1 operation(s)**:

- `send_message()` — Send Message


### `cisco-spark` v1.0.0 _(installed)_
_Cisco Spark_

Pulls lists of users and rooms, and allows for sending of messages

**3 operation(s)**:

- `get_rooms()` — List Rooms
- `get_users()` — Get Users
- `send_message()` — Send a Message


### `clicksend` v2.0.0 _(installed)_
_ClickSend_

ClickSend is a cloud-based service that lets you send and receive SMS, Email, Voice, Fax, and Letters worldwide.

**3 operation(s)**:

- `get_contact_list()` — Get Contact List
- `send_message()` — Send Message
- `send_voice_message()` — Send Voice Message


### `ducont-sms` v1.0.0 _(installed)_
_Ducont SMS_

The WCF Restful Service - Push SMS supports single and bulk messages request with parameterized or customized message.

**2 operation(s)**:

- `push_sms()` — Push SMS
- `push_sms_sub()` — Push SMS SUB


### `fortinet-fortivoice` v1.0.0 _(installed)_
_Fortinet FortiVoice_

FortiVoice Secure Unified Communications, along with FortiFone IP phones, helps organizations keep up with changing communication needs due to evolving infrastructure, remote/hybrid work, and BYOD.

**1 operation(s)**:

- `get_devices_list()` — Get Devices List


### `google-cloud-pub-sub` v1.0.0 _(installed)_
_Google Cloud Pub/Sub_

Google Cloud Pub/Sub is a fully-managed real-time messaging service
  that enables you to send and receive messages between independent applications.

**20 operation(s)**:

- `acknowledge_messages_from_subscriptions()` — Acknowledge Messages from Subscriptions
- `create_snapshots()` — Create Snapshots
- `create_subscription()` — Create Subscription
- `create_topic()` — Create Topic
- `delete_snapshots()` — Delete Snapshots
- `delete_subscription()` — Delete Subscription
- `delete_topic()` — Delete Topic
- `get_subscription_details()` — Get Subscription Details
- `get_topic_details()` — Get Topic Details
- `list_all_snapshots()` — List All Snapshots
- `list_all_subscriptions()` — List All Subscriptions
- `list_all_topic_snapshots()` — List All Topic Snapshots
- `list_all_topic_subscriptions()` — List All Topic Subscriptions
- `list_all_topics()` — List All Topics
- `publish_messages_to_topic()` — Publish Messages to Topic
- `pull_messages_from_subscriptions()` — Pull Messages from Subscriptions
- `seeks_subscriptions()` — Seeks Subscriptions
- `update_snapshots()` — Update Snapshots
- `update_subscription()` — Update Subscription
- `update_topic()` — Update Topic


### `hip-chat` v1.0.0 _(installed)_
_HipChat_

HipChat is a web service for internal private online chat and instant messaging.

**3 operation(s)**:

- `get_all_rooms()` — Get All Rooms
- `get_all_users()` — Get All Users
- `send_massage()` — Send Message


### `messagebird` v1.0.1 _(installed)_
_MessageBird_

MessageBird is a platform for communications and connecting companies to their customers on billions of devices. sending outbound SMS messages with MessageBird

**4 operation(s)**:

- `delete_message()` — Delete Message
- `get_messages()` — Get Messages
- `get_specific_message_details()` — Get Specific Message Details
- `send_message()` — Send Message


### `microsoft-intune` v1.0.0 _(installed)_
_Microsoft Intune_

Microsoft Intune is a cloud-based endpoint management solution. This connector facilitates automated operation related to managed device.

**20 operation(s)**:

- `bypass_activation_lock_of_device()` — Bypass Activation Lock for Device
- `clean_windows_device()` — Clean Windows Device
- `delete_user_from_shared_apple_device()` — Delete User from Apple Device
- `disable_lost_mode_of_device()` — Disable Lost Mode for Device
- `get_managed_device_details()` — Get Managed Device Details
- `list_managed_devices()` — Get Managed Devices List
- `locate_device()` — Locate a Device
- `logout_shared_apple_device_active_user()` — Logout Apple Device for Active User
- `reboot_device()` — Reboot Device
- `recover_passcode_of_device()` — Recover Passcode for Device
- `remote_lock_of_device()` — Remote Lock Device
- `request_remote_assistance_of_device()` — Request Remote Assistance for Device
- `reset_passcode_of_device()` — Reset Passcode Device
- `retire_device()` — Retire Device
- `shutdown_device()` — Shutdown Device
- `sync_device()` — Sync Device
- `update_windows_device_account()` — Update Account for Windows Device
- `windows_defender_scan()` — Windows Defender Scan
- `windows_defender_update_signature()` — Update Signature for Windows Defender
- `wipe_device()` — Wipe Device


### `microsoft-teams` v3.1.1 _(installed)_
_Microsoft Teams_

Microsoft Teams is a chat-based workspace in Office 365 that provides global, remote, and dispersed teams with the ability to work together and share information using a common space. This connector facilitates automated operation related to teams.

**36 operation(s)**:

- `add_member()` — Add Group's Member
- `add_owner()` — Add Group's Owner
- `archive_team()` — Archive Team
- `clone_team()` — Clone Team
- `create_channel()` — Create Channel
- `create_group()` — Create Group
- `create_meeting()` — Create Meeting
- `create_team()` — Create Team
- `create_user()` — Create User
- `delete_group()` — Delete Group
- `delete_meeting()` — Delete Meeting
- `delete_user()` — Delete User
- `get_channel()` — Get Channel Details
- `get_channel_messages()` — Get Channel's Messages
- `get_chat_messages()` — Get Chat Messages
- `get_group_member()` — Get Group's Member
- `get_group_owner()` — Get Group's Owner
- `get_groups()` — Get Groups
- `get_meeting()` — Get Meeting Details
- `get_replies_to_channel_message()` — Get Replies to Channel Message
- `get_team()` — Get Team Details
- `get_users()` — Get User Details
- `get_users_all_messages()` — Get User's all Chat Messages
- `list_user_joined_teams()` — Get User's Teams
- `list_users()` — Get All Users
- `messages_mention()` — Tag User in Message
- `remove_group_member()` — Remove Group's Member
- `remove_group_owner()` — Remove Group's Owner
- `reply_messages()` — Reply Message
- `send_chat()` — Send Direct Message
- `send_message()` — Send Message to Channel
- `send_message_or_approval_form_to_bot()` — Send Bot Message/Input Form
- `unarchive_team()` — Unarchive Team
- `update_meeting()` — Update Meeting Details
- `update_team()` — Update Team Details
- `update_user()` — Update User Details


### `sap-rfc` v1.1.0 _(installed)_
_SAP NetWeaver_

SAP NetWeaver Remote Function Call (RFC) is the standard SAP interface for communication between SAP systems. SAP NetWeaver connector performs action like list out session, end user session and, send popup message.

**10 operation(s)** (+1 hidden):

- `assign_user_role()` — Assign User Role
- `end_session()` — End User Session
- `get_session_list()` — Get Session List
- `lock_user()` — Lock User
- `remove_all_user_profiles()` — Remove User Profiles
- `remove_all_user_roles()` — Remove User Roles
- `run_rfc_functions()` — Run RFC Function
- `send_popup()` — Send Popup
- `unlock_user()` — Unlock User


### `twilio` v2.0.0 _(installed)_
_Twilio_

Twilio provides its users with a platform and a robust API capable of sending messages using the carrier network all over the world, while also exposing a globally available cloud API that developers can interact with to build intelligent and complex communications systems. This connector facilitates operations to Send Message and Make Outbound Call.

**2 operation(s)**:

- `make_outbound_call()` — Make Outbound Call
- `send_sms()` — Send Message


### `twitter` v1.0.0 _(installed)_
_Twitter_

Twitter is an online news and social networking service. This Connector facilitates automated interactions, such as posting tweets and searching for tweets, in Twitter accounts using CyOPs™ playbooks

**5 operation(s)**:

- `get_user()` — Get User
- `get_user_timeline()` — Get User Timeline
- `post_tweet()` — Post Tweet
- `search_tweets()` — Search Tweets
- `send_direct_message()` — Send Direct Message


### `zoom` v1.0.0 _(installed)_
_Zoom_

Zoom Connector can be used to automate actions like Create New Meeting, Get Meetings, Get Meeting Details, Update Meeting, Delete Meeting and Get Users

**6 operation(s)**:

- `create_new_meeting()` — Create New Meeting
- `delete_meeting()` — Delete Meeting
- `get_meeting_details()` — Get Meeting Details
- `get_meetings()` — Get Meetings
- `get_users()` — Get Users
- `update_meeting()` — Update Meeting


---

## Compliance and Reporting

### `word-templated-report` v1.0.1 _(installed)_
_FortiSOAR MS Word Report Templating_

This connector allows for Microsoft Word documents containing Jinja syntax to be used to generate reports in either .docx or .pdf formats. The 'docxtpl' Python library  is used to do this. For more information on how to format your templates, see the library's official documentation: https://docxtpl.readthedocs.io/en/latest/

**1 operation(s)**:

- `generate_report()` — Generate Report


---

## Compute Platform

### `aws` v3.1.2 _(installed)_
_AWS EC2_

Amazon Elastic Compute Cloud (Amazon EC2) provides scalable computing capacity in the Amazon Web Services (AWS) cloud. You can use Amazon EC2 to launch as many or as few virtual servers as you need, configure security and networking, and manage storage.

**32 operation(s)**:

- `add_network_acl_rule()` — Add Network ACL Rule
- `add_security_group_to_instance()` — Add Security Group To Instance
- `add_tag_to_instance()` — Add Instance Tag
- `attach_instance_to_auto_scaling_group()` — Attach Instance To Auto Scaling Group
- `attach_volume()` — Attach Volume
- `authorize_egress()` — Authorize Egress
- `authorize_ingress()` — Authorize Ingress
- `create_network_acl()` — Create Network ACL
- `create_security_group()` — Create Security Groups
- `delete_network_acl()` — Delete Network ACL
- `delete_network_acl_rule()` — Delete Network ACL Rule
- `delete_security_group()` — Delete Security Groups
- `delete_volume()` — Delete Volume
- `deregister_instance_from_elb()` — Deregister Instance from ELB
- `describe_instance()` — Get Instance Details
- `describe_network_acls()` — Get Details of Network ACLs
- `describe_user()` — Get User Details
- `detach_instance_from_autoscaling_group()` — Detach Instance From Auto Scaling Group
- `detach_volume()` — Detach Volume
- `get_details_for_all_images()` — Get AMIs Detail
- `get_details_of_security_group()` — Get Details of Security Group
- `get_security_groups()` — Get Security Groups
- `instance_api_termination()` — Instance API Termination 
- `launch_instance()` — Launch Instance
- `reboot_instance()` — Reboot Instance
- `register_instance_to_elb()` — Register Instance To ELB
- `revoke_egress()` — Revoke Egress
- `revoke_ingress()` — Revoke Ingress
- `snapshot_volume()` — Capture Volume Snapshot
- `start_instance()` — Start Instance
- `stop_instance()` — Stop Instance
- `terminate_instance()` — Terminate Instance


### `aws-lambda` v1.0.0 _(installed)_
_AWS Lambda_

Using AWS Lambda user can run code without provisioning or managing servers.

**7 operation(s)**:

- `get_account_settings()` — Get Account Settings
- `get_function()` — Get Function
- `get_policy()` — Get Policy
- `invoke()` — Invoke
- `list_aliases()` — List Aliases
- `list_functions()` — List Functions
- `list_layers()` — List Layers


### `azure-compute` v1.2.0 _(installed)_
_Azure Compute_

Azure Virtual Machines are image service instances that provide on-demand and scalable computing resources with usage-based pricing. This connector facilitates automated operations to get list of Azure Compute VM, get information about an Azure Compute VM, create, start, restart, stop and delete of an Azure Compute VM

**26 operation(s)** (+12 hidden):

- `create_instance()` — Create an Instance
- `create_snapshot()` — Create Snapshot
- `delete_instance()` — Delete an Instance
- `delete_snapshot()` — Delete Snapshot
- `get_instance_details()` — Get Instance Details
- `get_nic_details()` — Get NIC Details
- `get_nsg_details()` — Get NSG Details
- `get_snapshot_details()` — Get Snapshot Details
- `list_of_instances()` — List Instances
- `list_snapshot()` — List Snapshot
- `restart_instance()` — Restart an Instance
- `start_instance()` — Start an Instance
- `stop_instance()` — Stop an Instance
- `update_snapshot()` — Update Snapshot


### `fortinet-fortios` v3.0.0 _(installed)_
_Fortinet FortiOS_

FortiOS connector uses rest apis to perform automated operations such as Block IP, Unblock IP, List Blocked IP, Clear IP Block List etc

**16 operation(s)**:

- `ban_ip()` — Ban IPs
- `block_ip()` — Block IP Address
- `block_url()` — Block URL
- `get_address_group()` — Get Address Group
- `get_banned_ips()` — Get Banned IP Addresses
- `get_blocked_ip()` — Get Blocked IP Addresses
- `get_blocked_urls()` — Get Blocked URLs
- `get_policy()` — Get Policy
- `get_quarantine_hosts()` — Get Quarantine Hosts
- `get_url_profiles()` — Get Web Filter Profiles
- `purge_ip_block_list()` — Purge IP Block List
- `quarantine_host()` — Quarantine Host
- `remove_banned_ips()` — Remove Banned IPs
- `unblock_ip()` — Unblock IP Address
- `unblock_url()` — Unblock URL
- `unquarantine_host()` — Unquarantine Host


### `google-cloud-compute` v1.2.0 _(installed)_
_Google Cloud Compute_

Google Compute Engine's tooling and workflow supports to create advanced networks on the regional levels and load balancing capabilities in cloud computing. This connector facilitates automated operation related to GCE operations.

**9 operation(s)**:

- `delete_instance()` — Delete Instance
- `describe_instance()` — Get Instance Details
- `disk_snapshot()` — Disk Snapshot
- `get_aggregated_list_instances()` — Aggregated List Instances
- `list_instances_within_zone()` — List Instances within Zone
- `reset_instance()` — Reset Instance
- `set_label()` — Set Instance Label
- `start_instance()` — Start Instance
- `stop_instance()` — Stop Instance


### `google-cloud-translate` v1.0.0 _(installed)_
_Google Cloud Translate_

Google Cloud translation technology to instantly translate texts into more than one hundred languages

**2 operation(s)**:

- `get_supported_languages()` — Get Languages
- `translate_text()` — Translate Text


### `kafka` v1.0.0 _(installed)_
_Kafka_

Kafka Connector to publish/consume a messages to/from a topic.

**3 operation(s)**:

- `post_topic()` — Publish Message to a Topic
- `topic_details()` — Kafka Topic Details
- `topic_list()` — Kafka Topic List


### `samba` v2.0.0 _(installed)_
_SAMBA_

Performs samba operations such as file transfer or authentication over SMB protocol

**5 operation(s)**:

- `create_directory()` — Create Directory
- `delete_directory()` — Remove Directory Content
- `file_download()` — Download File
- `list_content()` — Get Directory Content
- `upload_file()` — Upload File


### `scp` v1.0.1 _(installed)_
_SCP_

SCP connector to send and receive files and directories to/from a remote machine.

**2 operation(s)**:

- `receive_file()` — Receive File
- `send_file()` — Send File


### `tor` v2.0.0 _(installed)_
_Tor_

Tor Connector facilitates to query information of Tor network

**1 operation(s)**:

- `lookup_ip()` — Check Tor Exit Node


### `vmware-vsphere` v1.1.0 _(installed)_
_VMware vSphere_

VMware vSphere connector handle virtual machine actions like start and stop VM, snapshot VM etc.

**14 operation(s)** (+6 hidden):

- `create_vm()` — Create VM
- `get_vm_info()` — Get VM Information
- `list_vms()` — Get Registered VMs List
- `revert_snapshot()` — Revert Snapshot
- `snapshot_vm()` — Snapshot VM
- `start_vm()` — Start VM
- `stop_vm()` — Stop VM
- `suspend_vm()` — Suspend VM


---

## Container Services

### `azure-kubernetes-services` v1.0.0 _(installed)_
_Azure Kubernetes Services_

Deploy and manage containerized applications with a fully managed Kubernetes. This connector facilitates the automated operations related to managed cluster.

**8 operation(s)**:

- `create_managed_cluster()` — Create Managed Cluster
- `delete_managed_cluster()` — Delete Managed Cluster
- `get_command_details()` — Get Command Details
- `get_managed_cluster()` — Get Managed Cluster
- `get_managed_clusters_list()` — Get Managed Clusters List
- `managed_cluster_actions()` — Managed Cluster Actions
- `run_command()` — Run Command
- `update_managed_cluster()` — Update Managed Cluster


### `kubernetes` v1.0.0 _(installed)_
_Kubernetes_

Kubernetes, also known as K8s, is an open-source system for automating deployment, scaling, and management of containerized applications.

**13 operation(s)**:

- `apply_yml_file()` — Apply YAML File
- `delete_collection_namespace_config_map()` — Delete Collection Namespace ConfigMap
- `delete_collection_namespace_pod()` — Delete Collection Namespace Pods
- `delete_collection_namespace_secret()` — Delete Collection Namespace Secret
- `delete_namespace_config_map()` — Delete Namespace ConfigMaps
- `delete_namespace_pod()` — Delete Namespace Pod
- `delete_namespace_secret()` — Delete Namespace Secret
- `get_pod_logs()` — Get Pod logs
- `list_config_map_for_all_namespaces()` — Get ConfigMap For All Namespaces
- `list_event_for_all_namespaces()` — Get Events For All Namespaces
- `list_namespace_pod()` — Get Namespace Pods List
- `list_pod_for_all_namespaces()` — Get Pod For All Namespaces
- `list_secret_for_all_namespaces()` — List Secret For All Namespaces


---

## Content Management

### `microsoft-sharepoint` v1.0.0 _(installed)_
_Microsoft Sharepoint_

Microsoft SharePoint is a collaboration, document management platform and content management system. This connector facilitates automated operations related to lists, files.

**6 operation(s)**:

- `delete_file()` — Delete File
- `edit_file()` — Update File Content
- `get_folder_file_list()` — Get Folders or File Lists
- `get_list()` — Get Lists
- `read_file_content()` — Download File
- `upload_file()` — Upload File


---

## Data Enrichment & Threat Intelligence

### `microsoft-management-activity-api` v1.0.1 _(installed)_
_Microsoft Management Activity API_

Office 365 Management Activity API is used to retrieve information about user, admin, system, and policy actions and events from Office 365 and Azure AD activity logs.

**4 operation(s)**:

- `list_content()` — MS Management Activity List Content
- `list_subscription()` — MS Management Activity List Subscription
- `start_subscription()` — MS Management Activity Start Subscription
- `stop_subscription()` — MS Management Activity Stop Subscription


---

## Database

### `aws-dynamodb` v1.0.0 _(installed)_
_AWS DynamoDB_

AWS DynamoDB is a fully managed NoSQL database service that provides fast and predictable performance with seamless scalability. This connector facilitates the automate operations related to manage database table, data and backup.

**16 operation(s)**:

- `create_backup()` — Create Table Backup
- `create_global_table()` — Create Global Table
- `create_or_update_table_item()` — Create or Update Table Item
- `create_table()` — Create Table
- `delete_item()` — Delete Table Item
- `delete_table()` — Delete Table
- `delete_table_backup()` — Delete Table Backup
- `get_global_table_details()` — Get Global Table Details
- `get_global_table_list()` — Get Global Table List
- `get_table_backup_details()` — Get Table Backup Details
- `get_table_backup_list()` — Get Table Backup List
- `get_table_details()` — Get Table Details
- `get_table_list()` — Get Table List
- `list_table_items()` — Get Table Items List
- `search_item()` — Search Table Item
- `update_table()` — Update Table


### `azure-cosmos-db` v1.0.0 _(installed)_
_Azure Cosmos DB_

Azure Cosmos DB is a globally distributed, multi-model database service offered by Microsoft. It is designed to provide high availability, scalability, and low-latency access to data for modern applications.

**6 operation(s)**:

- `delete_document()` — Delete Document
- `get_collections()` — Get Containers
- `get_database_properties()` — Get Database Properties
- `insert_document()` — Insert Document
- `query_document()` — Query Document
- `update_document()` — Update Document


### `databricks` v1.0.1 _(installed)_
_Databricks_

Query an Azure Databricks Cluster table in a catalog's schema (database). Uses Databricks SQL Connector for Python.

**1 operation(s)**:

- `run_query()` — Run Query


### `elasticsearch` v4.0.0 _(installed, ingestion)_
_ElasticSearch_

ElasticSearch is a distributed, RESTful search and analytics engine capable of solving a number of use cases. This connector facilitates automated operations to execute lucene query, get mapping and cluster details.

**9 operation(s)**:

_investigation_
- `apply_alert_tags(ids: text, [tags_to_add: text], [tags_to_remove: text], [port: integer])` — Apply Alert Tags
- `assign_unassign_users_from_alert(ids: text, [add: text], [remove: text], [port: integer])` — Assign or Unassign Users from Alerts
- `execute_lucene_query(query: text, [index: text], [run_as_user: text])` — Execute Lucene Query
- `execute_query(query: text, [index: text], [doc_type: text], [routing: text], [run_as_user: text])` — Execute Query
- `get_alerts_list(start: datetime, end: datetime, [query: json], [size: integer], [port: integer])` — Get Alerts List
- `get_cluster_details([index: text], [run_as_user: text])` — Get Cluster Details
- `get_mapping([index: text], [doc_type: text], [run_as_user: text])` — Get Mapping
- `get_saved_search(object_id: text, [port: integer])` — Get Saved Search
- `set_alert_status(status: text, [signal_ids: text], [query: json], [port: integer])` — Set Alert Status


### `google-bigquery` v1.0.0 _(installed)_
_Google BigQuery_

Google BigQuery is a service user allows to run super-fast queries of large datasets.

**2 operation(s)**:

- `list_tables()` — List Tables
- `run_query()` — Run a Query


### `influxdb` v1.0.0 _(installed)_
_InfluxDB_

Runs database queries against an InfluxDB instance

**1 operation(s)**:

- `run_query()` — Run Query


### `microsoft-sql-server` v2.0.1 _(installed)_
_Microsoft SQL Server_

Microsoft SQL Server Connector which enables to run queries on Microsoft SQL Server database

**4 operation(s)**:

- `list_columns()` — Get Columns
- `list_tables()` — Get Table List
- `run_query()` — Run Query
- `select_query()` — Select Query


### `mongodb` v2.0.0 _(installed)_
_MongoDB_

MongoDB is an open-source document database that provides high performance, high availability, and automatic scaling. Use the MongoDB connector to perform automated operations, such as inserting or updating documents, retrieving a list of all available collections from the MongoDB database, and querying the MongoDB database.

**5 operation(s)**:

- `add_data()` — Insert Documents
- `delete_data()` — Delete Documents
- `get_data()` — Query Documents
- `list_tables()` — Get Collections
- `update_data()` — Update Documents


### `mysql` v1.0.1 _(installed)_
_MySQL_

The MySQL database server manages the databases and tables, controls user access, and processes the SQL queries. perform automated operations, such as executing a query on MySQL database and listing table and column names present in the database.

**3 operation(s)**:

- `list_columns()` — List Columns
- `list_tables()` — List Tables
- `run_query()` — Run Query


### `odbc` v1.0.0 _(installed)_
_ODBC_

ODBC (Open Database Connectivity) allows applications to access data from different database systems (e.g., MySQL, SQL Server, Oracle). It enables interoperability between applications and databases through an ODBC driver.

**1 operation(s)**:

- `execute_query()` — Execute Query


### `oracle-db` v1.0.1 _(installed)_
_Oracle Database_

Use Oracle Database connector to connect to a database and then query the database and retrieve data. supports Oracle v12c onward.

**1 operation(s)**:

- `db_query()` — Query DB


### `postgresql` v1.0.2 _(installed)_
_PostgreSQL_

PostgreSQL Connector provide automated operation to run query on PostgreSQL server

**1 operation(s)**:

- `run_query()` — Run Query


### `sqlite` v1.0.0 _(installed)_
_SQLite_

SQLite Connector allows querying local SQLite database.

**3 operation(s)**:

- `list_columns()` — Get Columns
- `list_tables()` — Get Table List
- `run_query()` — Run Query


### `teradata-db` v1.0.0 _(installed)_
_Teradata DB_

Teradata DB is one of the popular Relational Database Management System. It is mainly suitable for building large scale data warehousing applications. Teradata Query Service is a REST API for Vantage that you can use to run standard SQL statements without managing client-side drivers.

**14 operation(s)**:

- `get_list_of_all_databases()` — Get List Of All Databases
- `get_list_of_all_functions()` — Get List Of All Functions
- `get_list_of_all_macros()` — Get List Of All Macros
- `get_list_of_all_procedures()` — Get List Of All Procedures
- `get_list_of_all_queries()` — Get List Of All Queries
- `get_list_of_all_systems()` — Get List Of All Systems
- `get_list_of_all_tables()` — Get List Of All Tables
- `get_list_of_all_views()` — Get List Of All Views
- `get_query_by_id()` — Get Query By Id
- `get_query_results_by_id()` — Get Query Results By ID
- `get_specific_database_by_name()` — Get Specific Database By Name
- `get_specific_table_by_name()` — Get Specific Table By Name
- `get_specific_view_by_name()` — Get Specific View By Name
- `submit_a_query()` — Submit A Query


---

## Deception

### `attivo-botsink` v1.0.1 _(installed)_
_Attivo BOTsink_

Attivo Botsink connector is network-based threat deception for post-compromise threat detection.

**21 operation(s)**:

- `add_domain_to_whitelist()` — Add Domain to Whitelist
- `check_host()` — Check Host
- `check_user()` — Check User
- `deploy_decoy()` — Deploy Decoy
- `get_MITM_configuration()` — Get MITM Configuration
- `get_MITM_events()` — Get MITM Events
- `get_access_control_rules()` — Get Access Control Rules
- `get_all_faults()` — Get All Faults
- `get_all_vm_status()` — Get All VM Status
- `get_all_vulnerabilities()` — Get All Vulnerabilities
- `get_details_of_object()` — Get Details of Object
- `get_events()` — Get Events
- `get_manager_users()` — Get Manager Users
- `get_network_data()` — Get Network Data
- `get_summary_of_objects()` — Get Summary of Objects
- `get_vm_status()` — Get VM Status
- `get_whitelisted_domains()` — Get Whitelisted Domains
- `list_hosts()` — Get Host List
- `list_playbooks()` — List Playbooks
- `run_endpoint_forensics()` — Run Forensics
- `run_playbook()` — Run Playbook


### `honeydb` v1.0.0 _(installed)_
_HoneyDB_

Provide investigative actions like lookup ip and get bad hosts from HoneyDB

**2 operation(s)**:

- `get_bad_hosts()` — Get Bad Hosts
- `lookup_ip()` — Lookup IP


---

## DevOps and Digital Operations

### `argo-cd` v1.0.1 _(installed)_
_Argo CD_

Argo CD (short for Argo Continuous Delivery) is a declarative, GitOps continuous delivery tool for Kubernetes. It allows you to manage and deploy applications to Kubernetes clusters using Git repositories as the source of truth for both the desired application state and its configuration.

**7 operation(s)**:

- `create_application()` — Create Application
- `delete_application()` — Delete Application
- `get_application_by_name()` — Get Application by Name
- `get_applications()` — Get Applications
- `get_clusters()` — Get Clusters
- `send_custom_request()` — Execute an API Call
- `update_application()` — Update Application


### `circleci` v1.0.0 _(installed)_
_CircleCI_

CircleCI is the continuous integration & delivery platform that helps the development teams to release code rapidly and automate the build, test, and deploy. CircleCI can be configured to run very complex pipelines efficiently with caching, docker layer caching, resource classes and many more. After repositories on GitHub or Bitbucket are authorized and added as a project to circleci.com, every code triggers CircleCI runs jobs. CircleCI also sends an email notification of success or failure after the tests complete.

**5 operation(s)**:

- `get_artifacts_list()` — Get Artifacts List
- `get_workflow_jobs_list()` — Get Workflow Jobs List
- `get_workflow_last_runs()` — Get Workflow Last Runs
- `get_workflows_list()` — Get Workflows List
- `trigger_workflow()` — Trigger Workflow


### `gitlab` v2.1.0 _(installed)_
_GitLab_

GitLab is a single application for the entire software development lifecycle. From project planning and source code management to CI/CD, monitoring, and security.

**45 operation(s)**:

- `add_member_to_project_or_group()` — Add Member to Repository
- `clone_repository()` — Clone Repository
- `compare_commit()` — Get Commit Comparison
- `create_issue()` — Create Issue
- `create_issue_comment()` — Create Issue Comment
- `create_merge_request()` — Create Merge Request
- `create_merge_request_comment()` — Create Merge Request Comment
- `create_new_file_in_repository()` — Create File
- `create_project()` — Create Repository
- `create_project_using_templates()` — Create Repository Using Templates
- `create_release()` — Create Release
- `create_repository_branch()` — Create Repository Branch
- `delete_existing_file_in_repository()` — Delete File
- `delete_project()` — Delete Repository
- `delete_repository_branch()` — Delete Repository Branch
- `edit_project()` — Update Repository
- `fetch_upstream()` — Fetch Upstream
- `fork_project()` — Fork Repository
- `get_commit()` — Get Commit
- `get_file_from_repository()` — Get File
- `get_member_list_of_project()` — Get Member List of Repository
- `get_merge_request_approval_state()` — Get Approval State of Merge Request
- `get_project()` — Get Repository
- `get_single_repository_branch()` — Get Repository Branch
- `get_web_url()` — Get Server URL
- `list_authenticated_user_projects()` — List Authenticated User Repositories
- `list_fork_projects()` — List Fork Repositories
- `list_group_projects()` — List Group Repositories
- `list_merge_requests_comments()` — List Merge Request Comments
- `list_merge_requests_reviewers()` — List Merge Request Reviewers
- `list_project_issues()` — List Repository Issues
- `list_project_merge_requests()` — List Repository Merge Requests
- `list_releases()` — List Releases
- `list_repository_branches()` — List Repository Branches
- `list_starrers()` — List Starrers
- `list_user_projects()` — List User Repositories
- `merge_merge_request()` — Merge a Merge Request
- `push_repository()` — Push Changes
- `review_merge_request()` — Review Merge Request
- `set_project_notification_level()` — Update Repository Notification Level
- `star_project()` — Star Repository
- `update_clone_repository()` — Update Remote Repository
- `update_file_in_repository()` — Update File
- `update_issue()` — Update Issue
- `update_merge_request()` — Update Merge Request


### `jenkins` v1.0.0 _(installed)_
_Jenkins_

Jenkins is an open-source automation server widely used to implement Continuous Integration (CI) and Continuous Delivery (CD) pipelines. It helps automate the parts of software development related to building, testing, and deploying, facilitating faster and more reliable software delivery.

**5 operation(s)**:

- `generic_rest_api_call()` — Execute an API Request
- `get_job_status()` — Get Job Status
- `get_list_jobs()` — Get List Jobs
- `resume_jenkins_job_with_input()` — Resume Jenkins Job with Input
- `trigger_job()` — Trigger Job


### `kiuwan` v1.2.0 _(installed)_
_Kiuwan_

Kiuwan is a software as a service (SaaS) static application security testing multi-technology software for software analysis, code quality, software composition and security measurement/management. This connector facilitates automated operations related to Action Plan, Analyses, and Defect.

**25 operation(s)**:

- `create_mutes_for_rule_or_file()` — Create Mutes for Rule or File
- `create_suppression_rule()` — Create Suppression Rule
- `delete_analysis()` — Delete Analysis
- `get_analysis_codes_list()` — Get Analysis Codes List
- `get_analysis_defects_list()` — Get Analysis Defects List
- `get_analysis_list()` — Get Analysis List
- `get_application_analysis()` — Get Application Analysis
- `get_application_defects_list()` — Get Application Defects List
- `get_application_details()` — Get Application Details
- `get_application_list()` — Get Application List
- `get_available_action_plans()` — Get Available Action Plans
- `get_comparison_defects()` — Get Comparison Defects
- `get_defect_notes()` — Get Defect Notes
- `get_defects_list_for_action_plan()` — Get Defects List for Action Plan
- `get_file_defects()` — Get File Defects
- `get_files_defects_details()` — Get Files Defects Details
- `get_last_analysis()` — Get Latest Analysis
- `get_latest_analysis_files_list()` — Get Latest Analysis Files List
- `get_new_removed_defects_list()` — Get New/Removed Defects List
- `get_pending_defects_for_action_plan()` — Get Pending Defects for Action Plan
- `get_progress_summary_for_action_plan()` — Get Progress Summary for Action Plan
- `get_removed_defects_for_action_plan()` — Get Removed Defects for Action Plan
- `get_violated_rule_files()` — Get Violated Rule Files
- `get_violated_rules()` — Get Violated Rules
- `update_defect_status()` — Update Defect Status


### `ops-genie` v1.1.0 _(installed)_
_OpsGenie_

OpsGenie connector provides alert management service

**16 operation(s)**:

- `add_note_to_alert()` — Add Note to Alert
- `add_responder_to_alert()` — Add Responder to Alert
- `add_team_to_alert()` — Add Team to Alert
- `assign_alert()` — Assign Alert
- `close_alert()` — Close Alert
- `create_alert()` — Create Alert
- `delete_alert()` — Delete Alert
- `get_alert()` — Get Alert
- `get_alert_status()` — Get Alert Action Status
- `get_attachment()` — Get Attachment
- `get_list_of_alerts()` — Get List of Alerts
- `get_list_of_attachments()` — Get Alert Attachments
- `get_request_status()` — Get Request Status
- `update_alert_description()` — Update Alert Description
- `update_alert_message()` — Update Alert Message
- `update_alert_priority()` — Update Alert Priority


### `pagerduty` v2.1.0 _(installed)_
_PagerDuty_

PagerDuty connects to monitoring systems so that you can collect events, surface what's important, and resolve critical issues to proactively manage your uptime. This Connector a facilitates automated operations to create incident, list notification, list teams, list users, send event, update event get user and notification details

**13 operation(s)**:

- `create_incident()` — Create Incident
- `get_escalation_policies_list()` — Get All Escalation Policies
- `get_incident_alerts_list()` — Get Incident Alerts List
- `get_incident_details()` — Get Incident Details
- `get_incidents()` — Get All Incidents List
- `get_services_list()` — Get All Services List
- `get_user_details()` — Get User Details
- `get_user_notification_rules()` — Get User Notification Rules
- `list_notifications()` — List Notifications
- `list_teams()` — List Teams
- `list_users()` — List Users
- `send_event()` — Send Event
- `update_event()` — Update Event


### `xmatters` v2.0.0 _(installed)_
_xMatters_

xMatters Connector can be used to automate actions like get events, update events, get groups and get device

**4 operation(s)**:

- `event_list()` — Get Event List
- `event_update()` — Update Event
- `get_device()` — Get Device
- `get_groups()` — Get Groups


---

## Digital assistant

### `amazon-alexa` v1.0.0 _(installed)_
_Amazon Alexa_

Amazon alexa provide automated operation for URL Lookup

**1 operation(s)**:

- `url_lookup()` — URL Lookup


---

## Directory Service

### `activedirectory` v2.4.0 _(installed)_
_Active Directory_

Active Directory (AD) is a directory service that Microsoft developed for Windows domain networks. You can directly query AD to retrieve information about users, groups, and computers, in an organization, by using the Lightweight Directory Access Protocol (LDAP) to directly query the AD.

**17 operation(s)**:

_containment_
- `disable_computer(search_attr_name: select, search_attr_value: text)` — Disable Computer
- `disable_user_account(search_attr_name: select, search_attr_value: text)` — Disable User Account
- `force_password_reset_next_logon(search_attr_name: select, search_attr_value: text)` — Force password reset on next logon
- `reset_password(search_attr_name: select, search_attr_value: text, new_password: password)` — Reset Password

_investigation_
- `add_group_members(group_dn: text, object_class: select)` — Add Group Members
- `add_object(object_class: select, [custom_attributes: json])` — Add Object
- `advanced_search(query: text, [page_size: integer], [size_limit: integer], [cookie: text])` — Advanced Search
- `delete_object(object_class: select)` — Delete Object
- `get_all_object_details(search_object: select, [page_size: integer], [size_limit: integer], [cookie: text])` — Get All Objects Details
- `get_specific_object_details(search_object: select)` — Get Specific Object Details
- `global_search(search_object: select, search_attr_name: select, search_attr_value: text, [page_size: integer], [size_limit: integer], [cookie: text])` — Global Search
- `move_computer_ou(computer_dn: text, computer_name: text, target_dn: text)` — Move Computer to Targeted Organization Unit(OU)
- `move_user_ou(search_attr_name: select, search_attr_value: text, destinationOU: text)` — Move User to Targeted Organization Unit(OU)
- `remove_group_members(group_dn: text, object_class: select)` — Remove Group Members
- `update_object(object_class: select, [custom_attributes: json])` — Update Object

_remediation_
- `enable_computer(search_attr_name: select, search_attr_value: text)` — Enable Computer
- `enable_user_account(search_attr_name: select, search_attr_value: text)` — Enable User Account


---

## Email Gateway

### `cisco-esa` v3.1.0 _(installed)_
_Cisco ESA_

The Cisco Email Security Virtual Appliance significantly lowers the cost of deploying email security, especially in highly distributed networks. Spam and malware are part of a complex email security picture that includes inbound threats and outbound risks. The all-in-one Cisco ESA (Email Security Appliance) offers simple, fast deployment with few maintenance requirements, low latency, and low operating costs.

**29 operation(s)**:

- `add_policy_entries()` — Add Entries In Policy
- `add_to_dictionary()` — Add Entries In Dictionary
- `block_mail()` — Block Email
- `block_sender()` — Block Sender
- `delete_blocklist_entries()` — Delete Blocklist Entries
- `delete_message()` — Delete Message
- `delete_safelist_entries()` — Delete Safelist Entries
- `download_attachment()` — Download Attachment
- `get_all_dictionaries()` — Get All Dictionaries
- `get_all_policies()` — Get All Policies
- `get_blocklist_entries()` — Get Blocklist Entries
- `get_dictionary_entries()` — Get Dictionary Entries
- `get_message_details()` — Get Message Details
- `get_safelist_entries()` — Get Safelist Entries
- `list_msg_filters()` — Get Message Filters List
- `message_tracking()` — Message Tracking
- `query_report()` — Query-based Report
- `release_emails_from_quarantine()` — Release Emails From Quarantine
- `remove_from_dictionary()` — Remove Entries From Dictionary
- `remove_policy_entries()` — Remove Entries From Policy
- `run_report()` — Run Report
- `search_in_other_quarantine()` — Search Emails From Other Quarantine
- `search_in_spam_quarantine()` — Search Emails From SPAM Quarantine
- `simple_report()` — Simple Report
- `topN_report()` — Top-N Report
- `unblock_mail()` — Unblock Email
- `unblock_sender()` — Unblock Sender
- `update_blocklist_entries()` — Update Blocklist Entries
- `update_safelist_entries()` — Update Safelist Entries


---

## Email Security

### `abnormal-security` v1.0.1 _(installed)_
_Abnormal Security_

Abnormal Security helps to prevent email and email-like attacks, automate your security operations and reduce your total spend with one extensible platform.

**20 operation(s)**:

_investigation_
- `check_case_action_status(caseId: text, actionId: text, [mock-data: checkbox])` — Check Case Action Status
- `check_threat_action_status(threatId: text, actionId: text, [mock-data: checkbox])` — Check Threat Action Status
- `download_data_from_threat_log([filter: text], [source: select], [mock-data: checkbox])` — Download Data from Threat Log
- `get_abuse_campaign_details(campaignId: text, [mock-data: checkbox])` — Get Abuse Campaign Details
- `get_abuse_campaigns([filter: text], [sender: text], [recipient: text], [subject: text], [reporter: text], [attackType: select], [threatType: select], [mock-data: checkbox], [pageSize: integer], [pageNumber: integer])` — Get Abuse Campaigns
- `get_case_analysis(caseId: text, [mock-data: checkbox])` — Get Case Analysis
- `get_case_details(caseId: text, [mock-data: checkbox])` — Get Case Details
- `get_cases([filter: text], [mock-data: checkbox], [pageSize: integer], [pageNumber: integer])` — Get Cases
- `get_detection_reports(inquiry_type: select, [start: text], [end: text], [status: multiselect])` — Get Detection Reports
- `get_employee_identity_analysis(emailAddress: text, [mock-data: checkbox])` — Get Employee Identity Analysis
- `get_employee_info(emailAddress: text, [mock-data: checkbox])` — Get Employee Information
- `get_employee_login_info(emailAddress: text, [mock-data: checkbox])` — Get Employee Login Information
- `get_message_details(messageId: text)` — Get Message Details
- `get_threat_attachments(threatId: text, [mock-data: checkbox])` — Get Threat Attachments
- `get_threat_details(threatId: text, [mock-data: checkbox], [pageSize: integer], [pageNumber: integer])` — Get Threat Details
- `get_threat_links(threatId: text, [mock-data: checkbox])` — Get Threat Links
- `get_threats([filter: text], [source: select], [sender: text], [recipient: text], [subject: text], [topic: select], [attackType: select], [attackVector: select], [attackStrategy: select], [impersonatedParty: select], [mock-data: checkbox], [pageSize: integer], [pageNumber: integer])` — Get Threats
- `manage_abnormal_case(caseId: text, action: json, [mock-data: checkbox])` — Manage Abnormal Case
- `manage_threat(threatId: text, action: json, [mock-data: checkbox])` — Manage Threat
- `submit_false_positive_report(report_data: json, [mock-data: checkbox])` — Submit a Missed Attack or False Positive Report


### `cisco-esa-rest` v1.0.0 _(installed)_
_Cisco ESA(REST)_

The Cisco Email Security Virtual Appliance significantly lowers the cost of deploying email security, especially in highly distributed networks. Spam and malware are part of a complex email security picture that includes inbound threats and outbound risks. The all-in-one Cisco ESA (Email Security Appliance) offers simple, fast deployment with few maintenance requirements, low latency, and low operating costs.

**11 operation(s)**:

- `delete_quarantine_message()` — Delete Quarantine Messages
- `delete_safelist_or_blocklist_entries()` — Delete Safelist or Blocklist Entries
- `edit_safelist_or_blocklist_entries()` — Edit Safelist or Blocklist Entries
- `get_message_amp_details()` — Get Message AMP Details
- `get_message_dlp_details()` — Get Message DLP Details
- `get_message_url_details()` — Get Message URL Details
- `get_quarantine_message()` — Get Quarantine Message By ID
- `get_report()` — Get Report
- `release_quarantine_message()` — Release Quarantine Messages
- `search_quarantine_messages()` — Search Quarantine Messages
- `search_safelist_or_blocklist_entries()` — Search Safelist or Blocklist Entries


### `cofense-vision` v1.0.0 _(installed)_
_Cofense Vision_

Cofense Vision is a security solution designed to help organizations quickly detect, locate, and quarantine phishing emails across all employee inboxes.

**2 operation(s)**:

- `quarantine_email()` — Quarantine Email
- `search_email()` — Search Email


### `fireeye-etp` v1.0.0 _(installed)_
_FireEye ETP_

FireEye ETP helps you secure and control inbound and outbound email through an easy-to-use cloud-based solution. Perform actions like alerts and messages information using FireEye ETP.

**13 operation(s)**:

- `delete_bulk_quarantined_email()` — Delete Bulk Emails From Quarantine
- `delete_quarantined_email()` — Delete Quarantined Email
- `get_alert()` — Get Alert
- `get_alert_artifact()` — Get Alert Artifact
- `get_alert_list()` — List All Alerts
- `get_alert_malware_files()` — Get Alert Malware Files
- `get_alert_pcap_files()` — Get Alert PCAP Files
- `get_message()` — Get Message
- `get_quarantined_email()` — Get Quarantine Email
- `query_quarantined_email()` — Query Quarantined Email
- `release_bulk_quarantined_email()` — Release Bulk Emails From Quarantine
- `release_quarantined_email()` — Release Quarantined Email
- `search_messages()` — Search Messages


### `fireeye-ex` v1.1.0 _(installed)_
_FireEye EX_

FireEye EX connector perform automated operations such as retrieving a list of all guest image profiles and applications details, get alerts details and retrieving data for artifacts etc.

**16 operation(s)**:

- `add_custom_feed()` — Add Custom Feed
- `add_yara_rule()` — Add YARA Rule
- `delete_custom_feed()` — Delete Custom Feed
- `delete_quarantined_emails()` — Delete Quarantined Emails
- `delete_yara_rule()` — Delete YARA Rule
- `download_quarantined_email()` — Download Quarantined Email
- `download_yara_rule()` — Download YARA Rule
- `get_alert_details()` — Get Alert Details
- `get_alert_ioc()` — Get Alert Related IOC
- `get_alerts()` — Get Alerts
- `get_artifacts_metadata_by_uuid()` — Get Artifacts Metadata By UUID
- `get_config()` — Get Config
- `get_custom_feeds()` — Get Custom Feeds
- `list_quarantined_emails()` — List Quarantined Emails
- `list_yara_rule()` — List YARA Rule
- `release_quarantined_emails()` — Release Quarantined Emails


### `gmail` v3.1.0 _(installed)_
_GSuite for Gmail_

Allows for searching emails, send emails, import emails,listing users, and deleting emails using the GSuite for Gmail

**8 operation(s)** (+1 hidden):

- `delete_messages()` — Delete Emails
- `get_unread_emails()` — Get Unread Emails
- `import_email()` — Import Email
- `list_users()` — List Users (Deprecated)
- `modify_email_label()` — Modify Email Label
- `search_emails()` — Search for Emails
- `send_email()` — Send Email


### `know-b4-phisher` v1.0.1 _(installed)_
_KnowBe4 PhishER_

KnowBe4 PhishER helps your InfoSec and Security Operations team cut through the inbox noise and respond to the most dangerous threats more quickly.

**6 operation(s)**:

- `add_comment()` — Add Comment
- `add_tags()` — Add Tags
- `get_message_by_id()` — Get Message by ID
- `get_message_list()` — Get Messages
- `remove_tags()` — Remove Tags
- `update_message()` — Update Message


### `mailboxlayer` v1.0.0 _(installed)_
_Mailboxlayer_

Mailboxlayer simple and powerful API offering instant email address validation & verification via syntax checks, typo and spelling checks, SMTP checks, free and disposable provider filtering.This connector facilitates the automated operations email verification and check email validation.

**1 operation(s)**:

- `get_email_verification_details()` — Get Email Verification Detail


### `microsoft-defender-office-365` v1.1.0 _(installed)_
_Microsoft Defender For Office 365_

Microsoft Defender for Office 365 safeguards your organization against malicious threats posed by email messages, links (URLs), and collaboration tools. This connector facilitates automated operations related to alerts.

**3 operation(s)**:

- `get_alert()` — Get Alert
- `list_alerts()` — List Alerts
- `update_alert()` — Update Alert


### `mimecast` v3.0.0 _(installed)_
_Mimecast_

This connector integrate with Mimecast endpoints provide cloud-based email management for Microsoft Exchange and Microsoft Office 365, and offers security, archiving, and continuity services to protect business mail.

**26 operation(s)**:

- `add_group_member()` — Add Group Member
- `archive_search()` — Archive Search
- `blacklist_url()` — Add URL to Block List
- `block_sender()` — Block Sender
- `create_blocked_sender_policy()` — Create Blocked Sender Policy
- `create_group()` — Create Group
- `decode_url()` — Decode URL
- `delete_group()` — Delete Group
- `find_groups()` — Find Groups
- `get_aliases()` — Get Aliases
- `get_archive_search_message_details()` — Get Archive Search Message Details
- `get_attachment_protection_logs()` — Get Attachment Protection Logs
- `get_blocked_sender_policy()` — Get Blocked Sender Policy
- `get_dlp_logs()` — Get DLP Logs
- `get_group_members()` — Get Group Member
- `get_managed_url()` — Get Managed URL
- `get_message_info()` — Get Message Info
- `get_message_list()` — Get Message List
- `get_search_url_logs()` — Get Search URL Logs
- `get_ttp_impersonation_protect_logs()` — Get TTP Impersonation Protect Logs
- `get_ttp_url_logs()` — Get TTP URL Logs
- `message_search()` — Message Search
- `remove_group_member()` — Remove Group Member
- `unblock_sender()` — Unblock Sender
- `update_group()` — Update Group
- `whitelist_url()` — Add URL to Allow List


### `mimecast-s2` v3.0.0 _(installed)_
_Mimecast S2_

This connector integrate with Mimecast S2 endpoints provide cloud-based email management for Microsoft Exchange and Microsoft Office 365, and offers threat monitoring and remediation service for internally generated emails

**5 operation(s)**:

- `archive_search()` — Archive Search
- `create_incident()` — Create Incident
- `get_archive_search_message_details()` — Get Archive Search Message Details
- `get_message_info()` — Get Message Info
- `message_search()` — Message Search


### `proofpoint-email-gateway` v2.0.0 _(installed)_
_Proofpoint Email Gateway_

Proofpoint Email Protection helps you secure and control inbound and outbound email through an easy-to-use cloud-based solution. Perform actions like organizational block list and search quarantine message information using Proofpoint Email Gateway.

**4 operation(s)**:

- `add_remove_organizational_block_list()` — Add or Remove Organizational Block List
- `get_organizational_block_list()` — Get Organizational Block List
- `quarantine_message_actions()` — Quarantine Message Actions (Deprecated)
- `search_quarantine_messages()` — Search Quarantine Messages (Deprecated)


### `proofpoint-tap` v1.0.2 _(installed)_
_Proofpoint TAP_

Perform actions like get events, get campaign details and get forensic information using Proofpoint TAP

**8 operation(s)**:

- `get_all_events()` — Get All Events
- `get_campaign_details()` — Get Campaign Details
- `get_clicks_blocked_event()` — Get Blocked Malicious URL Events
- `get_clicks_delivered_event()` — Get Delivered Threat Message Events
- `get_clicks_permitted_event()` — Get Permitted Malicious URL Events
- `get_forensic()` — Get Forensic Details
- `get_issues_event()` — Get Events for All Issues
- `get_messages_blocked_event()` — Get Blocked Threat Message Events


### `sendgrid` v1.1.0 _(installed)_
_SendGrid_

SendGrid

**10 operation(s)** (+1 hidden):

- `create_batch_id()` — Create Batch ID
- `delete_scheduled_send()` — Delete Scheduled Send
- `get_alerts()` — Get Alerts
- `get_contact_list()` — Get Contact List
- `get_email_stats()` — Get Email Statistics
- `get_scheduled_send()` — Get Scheduled Send
- `search_email()` — Search Emails
- `send_email()` — Send Email
- `update_scheduled_send()` — Update Scheduled Send


### `smime-messaging` v1.0.0 _(installed)_
_S/MIME Messaging_

Secure/Multipurpose Internet Mail Extensions (S/MIME) is an email security protocol that uses encryption to protect the confidentiality and integrity of email messages. S/MIME can be used to encrypt email messages or digitally sign email messages. 

<b><i> Prerequisites: </i></b> User need to install swig using following command: <b><i> yum install swig </i></b>

**4 operation(s)**:

- `decrypt_email()` — Decrypt Email
- `encrypt_email()` — Encrypt Email
- `sign_email()` — Sign Email
- `verify_sign()` — Verify Sign


### `symantec-cloud` v2.0.1 _(installed)_
_Symantec Email Security.cloud_

Symantec Email Security.cloud stops targeted spear phishing and other email threats by blocking sender IP, Domain and Email address etc.

**12 operation(s)**:

- `block_domain()` — Blacklist Domain
- `block_email()` — Blacklist Email Address
- `block_ip()` — Blacklist IP Address
- `block_md5()` — Blacklist MD5
- `block_sha2()` — Blacklist SHA-2
- `block_subject()` — Block Subject Text
- `block_url()` — Blacklist URL
- `delete_ioc()` — Remove IOC from Blacklist
- `download_iocs()` — Download IOCs
- `merge_iocs()` — Merge IOCs In Blacklist
- `renewall_ioc()` — Renew All Blacklist IOC
- `replace_iocs()` — Replace All IOCs In Blacklist


### `symantec-messaging-gateway` v1.1.1 _(installed)_
_Symantec Messaging Gateway_

Symantec Messaging Gateway is an email security solution which provides inbound and outbound messaging security. Also it can perform containment and corrective actions like block Domain/Email/IP or unblock Domain/Email/IP

**8 operation(s)**:

- `advanced_audit_logs_search()` — Advanced Audit Log Search
- `audit_logs_search()` — Quick Audit Log Search
- `blacklist_domain()` — Block Domain
- `blacklist_email()` — Block Email
- `blacklist_ip()` — Block IP
- `unblacklist_domain()` — Unblock Domain
- `unblacklist_email()` — Unblock Email
- `unblacklist_ip()` — Unblock IP


---

## Email Server

### `exchange` v4.7.0 _(installed, ingestion)_
_Exchange_

The Exchange connector provides a robust, platform-independent, and simple interface for communicating with Microsoft Exchange 2007-2016 Server or Office 365 using Exchange Web Services (EWS).

**20 operation(s)** (+1 hidden):

_containment_
- `add_category([source: select], message_id: text, categories: text)` — Add Category

_investigation_
- `create_calendar_event(subject: text, start_date: datetime, end_date: datetime, required_attendees: text, [optional_attendees: text], [body: richtext], [location: text], [categories: text], [legacy_free_busy_status: select], [reminder_min: select], [is_all_day: checkbox], [private: checkbox])` — Create Calendar Event
- `create_folder([target_email: text], [parent_folder_path: text], folder_name: text)` — Create Folder
- `delete_email(message_id: text, delete_type: select, [folder_name: text], [target_email: text])` — Delete Email
- `get_calendar_events([subject: text], [from_time: datetime], [to_time: datetime])` — Get Calendar Events
- `get_category([source: select], message_id: text)` — Get Category
- `get_contacts()` — Get Contacts
- `get_email([source: select], [mark_read: checkbox], [pull_oldest: checkbox], [limit: integer], [parse_inline: checkbox], [save_as_attachment: checkbox], [extract_attach_data: checkbox])` — Get Unread Emails (Deprecated)
- `get_email_new([target_email: text], [source: select], [mark_read: checkbox], [pull_oldest: checkbox], [limit: integer], [parse_inline: checkbox], [save_as_attachment: checkbox], [extract_attach_data: checkbox], [exclude_absolute_path: checkbox])` — Get Unread Emails
- `get_folder_metadata([source: select])` — Get Folder Metadata
- `mark_as_read(message_id: text, [folder_name: text])` — Mark Email as Read
- `mark_emails_as_junk(message_ids: text, [folder_name: text], [mark_read: checkbox], [target_email: text])` — Mark Emails as Junk
- `remove_category([source: select], message_id: text, categories: text)` — Remove Category
- `run_query([target_email: text], [folder: text], [query_method: select], [pull_oldest: checkbox], [parse_inline: checkbox], [extract_attach_data: checkbox], [exclude_absolute_path: checkbox], [save_as_attachment: checkbox], [range: integer])` — Search Email
- `send_email(to_recipients: text, [subject: text], [cc_recipients: text], [bcc_recipients: text], [body: richtext], [iri_list: text], [inline_iri_list: text])` — Send Email
- `send_email_new(to_recipients: text, [cc_recipients: text], [bcc_recipients: text], body_type: select, [iri_list: text], [inline_iri_list: text])` — Send Email (Advanced)
- `send_reply([target_email: text], message_id: text, [reply_all: checkbox], [subject: text], [to_recipients: text], [cc_recipients: text], body: richtext, [iri_list: text])` — Send Reply

_miscellaneous_
- `copy_email([source_email: text], [source: select], message_id: text, [target_email: text], [destination: select])` — Copy Email
- `move_email([source_email: text], [source: select], message_id: text, [target_email: text], [destination: select])` — Move Email


### `microsoft-graph-mail` v1.4.0 _(installed)_
_Microsoft Graph Mail_

Using Microsoft Graph integrate with Outlook by creating an app and get authorized access to a user's Outlook mail in a personal or organization account.

**16 operation(s)** (+1 hidden):

- `add_email_category()` — Add Email Category
- `copy_email()` — Copy Email
- `create_email_threat_submission()` — Create Email Threat Submission
- `delete_email()` — Delete Email
- `execute_api_request()` — Execute an API Request
- `forward_email()` — Forward Email
- `get_child_folders()` — Get Child Folders
- `get_email_categories()` — Get Email Categories
- `get_folders()` — Get Folders
- `get_unread_emails()` — Get Unread Emails
- `move_email()` — Move Email
- `remove_email_category()` — Remove Email Category
- `search_emails()` — Search Emails
- `send_email()` — Send Email
- `send_email_as_reply()` — Send Mail as Reply


### `zimbra-administrator` v1.0.0 _(installed)_
_Zimbra Administrator_

Zimbra Collaboration is the world’s leading open source messaging and collaboration solution. Zimbra includes complete email, contacts, calendar, file sharing, tasks and chat and can be accessed from the Zimbra Web client via any device and any other email client. Using Zimbra Administrator integration user can search across mailboxe, delete emails etc.

**3 operation(s)**:

- `delete_email()` — Delete Email
- `get_account_details()` — Get Account Details
- `search_emails()` — Search Email


### `zimbra-mailbox` v1.0.0 _(installed)_
_Zimbra Mailbox_

Zimbra Collaboration is the world's leading open source messaging and collaboration solution. Zimbra includes complete email, contacts, calendar, file sharing, tasks, and chat solution. It can be accessed from the Zimbra Web client via any device and any other email client. Using Zimbra integration, users can search emails, retrieve unread emails, import, and export emails.

**5 operation(s)**:

- `export_mailbox()` — Export Mailbox
- `get_contact()` — Get Contacts
- `get_unread_emails()` — Get Unread Emails
- `import_email()` — Import Email
- `search_emails()` — Search Emails


---

## Endpoint Management

### `microsoft-scom` v1.0.0 _(installed)_
_Microsoft SCOM_

Microsoft SCOM Connector

**6 operation(s)**:

- `close_alert()` — Close Alert
- `get_device_info()` — Get Device Information
- `list_alerts()` — Get Alerts
- `list_endpoints()` — List Endpoints
- `set_resolution_state()` — Set Resolution State
- `update_alert()` — Update Alert


---

## Endpoint Protection

### `fortinet-fortiedr` v2.1.0 _(installed, ingestion)_
_Fortinet FortiEDR_

FortiEDR protects endpoints pre and post infection, stopping data breaches in real-time and automatically orchestrating incident investigation and response. This connector facilitates the automated operations related to events, forensics and collectors.

**31 operation(s)**:

_investigation_
- `count_events([eventIds: text], [device: text], [collectorGroups: text], [operatingSystems: text], [deviceIps: text], [macAddresses: text], [fileHash: text], [process: text], [paths: text], [firstSeenFrom: datetime], [firstSeenTo: datetime], [lastSeenFrom: datetime], [lastSeenTo: datetime], [classifications: multiselect], [actions: select], [destinations: text], [rule: text], [seen: select], [handled: select], [signed: select], [muted: select], [loggedUser: text], [organization: select], [archived: checkbox], [strictMode: checkbox], [deviceControl: checkbox], [expired: checkbox], [pageNumber: integer], [itemsPerPage: integer], [sorting: json])` — Get Event Count
- `create_exception(eventId: integer, [allCollectorGroups: select], [allOrganizations: select], [allDestinations: select], [comment: text], [forceCreate: select], [exceptionJson: json])` — Create Exception
- `create_ipset([organization: select], name: text, description: text, include: text, exclude: text)` — Create IPSet
- `delete_ipset(ipSets: text, [organization: select])` — Delete IPSet
- `generic_rest_api_call(endpoint: text, method: select, [Query Parameters: json], [payload: json])` — Execute an API Request
- `get_agent_group([organization: select])` — Get Agent Groups
- `get_collector_list([type: select], [collectorGroups: text], [ips: text], [operatingSystems: text], [osFamilies: text], [states: multiselect], [lastSeenStart: datetime], [lastSeenEnd: datetime], [versions: text], [strictMode: checkbox], [showExpired: select], [loggedUser: text], [organization: select], [pageNumber: integer], [itemsPerPage: integer], [sorting: json])` — Get Collector List
- `get_event_by_id(eventIds: integer)` — Get Event by ID
- `get_event_exceptions(eventId: integer, [organization: text])` — Get Event Exceptions
- `get_event_file(rawEventId: text, retrieve_from: select, [organization: text])` — Retrieve File or Memory
- `get_event_list([eventIds: text], [device: text], [collectorGroups: text], [operatingSystems: text], [deviceIps: text], [macAddresses: text], [fileHash: text], [process: text], [paths: text], [firstSeenFrom: datetime], [firstSeenTo: datetime], [lastSeenFrom: datetime], [lastSeenTo: datetime], [classifications: multiselect], [actions: select], [destinations: text], [rule: text], [loggedUser: text], [seen: select], [handled: select], [signed: select], [severities: multiselect], [muted: select], [organization: select], [archived: checkbox], [strictMode: checkbox], [deviceControl: select], [expired: select], [pageNumber: integer], [itemsPerPage: integer], [sorting: json])` — Get Events
- `get_event_list_extended([eventIds: text], [device: text], [collectorGroups: text], [operatingSystems: text], [deviceIps: text], [macAddresses: text], [fileHash: text], [process: text], [paths: text], [firstSeenFrom: datetime], [firstSeenTo: datetime], [lastSeenFrom: datetime], [lastSeenTo: datetime], [classifications: multiselect], [actions: multiselect], [destinations: text], [rule: text], [loggedUser: text], [seen: select], [handled: select], [signed: select], [severities: multiselect], [muted: select], [organization: select], [strictMode: select], [deviceControl: select], [expired: select], [pageNumber: integer], [itemsPerPage: integer], [sorting: json])` — Get Event List Extended
- `get_file(type: select, filePaths: text, [organization: text])` — Get File
- `get_ipset_list(ip: text, [organization: select])` — Get IPSet List
- `get_organizations()` — Get Organizations
- `get_raw_data_items(eventId: integer, [device: text], [collectorGroups: text], [firstSeenFrom: datetime], [firstSeenTo: datetime], [lastSeenFrom: datetime], [lastSeenTo: datetime], [strictMode: checkbox], [fullDataRequested: checkbox], [rawEventIds: text], [pageNumber: integer], [itemsPerPage: integer], [sorting: json])` — Get Raw Data Items
- `get_raw_json_event_data(rawItemIds: text, [organization: text])` — Get Raw JSON Event Data
- `get_system_summary([organization: select], [addLicenseBlob: checkbox])` — Get System Summary
- `isolate_collector(type: select, [organization: text])` — Isolate Collector
- `list_exception([createdBefore: datetime], [createdAfter: datetime], [updatedBefore: datetime], [updatedAfter: datetime], [organization: select], [exceptionIds: text], [rules: text], [collectorGroups: text], [process: text], [path: text], [comment: text], [destination: text], [user: text])` — Get Exception List
- `move_collectors(collectors: text, targetCollectorGroup: text, [organization: select], [forceAssign: checkbox])` — Move Collectors
- `search(fileHashes: text, [organization: select])` — Search Filehash
- `search_ioc([organization: text], [category: select], [devices: text], [time: select], [filters: json], [query: text], [sorting: checkbox], [pageNumber: integer], [itemsPerPage: integer])` — Search IOC
- `unisolate_collector(type: select, [organization: text])` — Unisolate Collector
- `update_event(update_fields: multiselect, [eventIds: text], [device: text], [collectorGroups: text], [operatingSystems: text], [deviceIps: text], [fileHash: text], [process: text], [paths: text], [firstSeenFrom: datetime], [firstSeenTo: datetime], [lastSeenFrom: datetime], [lastSeenTo: datetime], [seen: select], [handled: select], [severities: multiselect], [destinations: text], [actions: multiselect], [rule: text], [strictMode: select], [classifications: multiselect], [organization: select], [muted: select], [deviceControl: select], [expired: select])` — Update Events
- `update_exception(eventId: integer, exceptionId: integer, organization: text, [destination: select], [collector_grp: select], [comment: text])` — Update Exception
- `update_ipset([organization: select], name: text, description: text, add_items: checkbox, [include: text], [exclude: text])` — Update IPSet

_management_
- `get_collector_installers(organization: text)` — Get Collector Installers
- `set_collector_state(collectorIds: text, organizationId: decimal, enabled: select)` — Set Collector State
- `update_collector_installer([collectorGroups: text], [organization: text], updateVersions: json)` — Update Collector Installer

_remediation_
- `remediate_device(type: select, [organization: text], remediate_action: select)` — Remediate Device


---

## Endpoint Security

### `bitdefender` v1.0.0 _(installed)_
_Bitdefender_

Bitdefender Endpoint Detection and Response (EDR) is a security solution designed to detect, investigate, and respond to advanced cyber threats on endpoints. This connector enables automated operations such as Get Computers Quarantine List, Get Exchange Quarantine List, and others.

**22 operation(s)**:

- `add_to_blocklist()` — Add to Blocklist
- `change_incident_status()` — Change Incident Status
- `createRestoreEndpointFromIsolationTask()` — Create Restore Endpoint from Isolation
- `create_add_file_to_quarantine_task()` — Create Add File To Quarantine Task
- `create_isolate_endpointtask()` — Create Isolate Endpoint Task
- `create_scan_task()` — Create Scan Task
- `create_scan_task_by_mac()` — Create Scan Task By Mac Address
- `delete_custom_rule()` — Delete Custom Rule
- `get_accounts_list()` — Get Accounts List
- `get_block_list_items()` — Get Block List Items
- `get_computers_quarantine_items_list()` — Get Computers Quarantine List
- `get_custom_rule_list()` — Get Custom Rules List
- `get_endpoints_list()` — Get Endpoints List
- `get_exchange_quarantine_items_list()` — Get Exchange Quarantine List
- `get_managed_endpoints_details()` — Get Managed Endpoints Details
- `get_policies_list()` — Get Policies List
- `get_scan_tasks_list()` — Get Scan Task List
- `get_scan_tasks_status()` — Get Scan Task Status
- `move_endpoints()` — Move Endpoints
- `remove_from_blocklist()` — Remove from BlockList
- `set_endpoint_label()` — Set Endpoint Label
- `update_incident_note()` — Update Incident Note


### `bmc-discovery` v1.0.0 _(installed)_
_BMC Discovery_

BMC Discovery is a data center discovery solution that automatically discovers data center inventory, configuration and relationship data, and maps applications to the IT infrastructure. This connector facilitates automated operation related to run search.

**1 operation(s)**:

- `search_query()` — Run Search


### `carbonblack-defense` v3.0.0 _(installed)_
_CarbonBlack Defense_

CarbonBlack Defense is the most powerful Next-Generation Anti Virus platform. This connector facilitates automated operations related to devices, policies, alerts, notifications etc.

**21 operation(s)**:

- `add_rule_to_policy()` — Add Rule To Policy
- `change_device_status()` — Change Device Status
- `create_policy()` — Create Policy
- `delete_policy()` — Delete Policy
- `delete_rule_from_policy()` — Delete Rule from Policy
- `execute_file_commands()` — Execute Live Commands - File
- `execute_process_commands()` — Execute Live Commands - Process
- `execute_registry_commands()` — Execute Live Commands - Registry
- `find_event_by_id()` — Find Event By ID
- `find_events()` — Find Events
- `find_processes()` — Find Processes
- `get_alert_by_id()` — Get Alert by ID
- `get_alert_details()` — Get Alert Details
- `get_all_policies()` — Get All Policies
- `get_device_status()` — Get Device Status
- `get_devices_status()` — Get Devices Status
- `get_notifications()` — Get Notifications
- `get_policy_by_id()` — Get Policy By ID
- `search_alerts()` — Search Alerts
- `update_policy()` — Update Policy
- `update_rule_in_policy()` — Update Rule in Policy


### `carbonblack-protect-bit9` v1.0.2 _(installed)_
_CarbonBlack Protection Bit9_

CarbonBlack Protection is a comprehensive endpoint threat protection solution. This connector facilitates automated operation related to file white listing operations.

**8 operation(s)**:

- `block_file()` — Block File
- `get_approval_request()` — Get Approval Requests
- `get_policies()` — Get Policies
- `get_system_info()` — Get System Information
- `hunt_file()` — Hunt File
- `remove_filerule()` — Remove File Rule
- `unblock_file()` — Unblock File
- `update_approval_request()` — Update Approval Request


### `carbonblack-response` v2.0.2 _(installed)_
_VMware Carbon Black EDR_

VMware Carbon Black EDR is purpose-built for enterprise SOC and IR teams.This connector facilitates automated operation related to endpoint protection like isolate endpoint, unisolate endpoint, hunt file, terminate process etc. with VMware Carbon Black EDR server.

**17 operation(s)**:

- `block_hash()` — Block Hash
- `bulk_update_alert()` — Bulk Update Alerts
- `delete_file()` — Delete file
- `get_blacklisted_hash()` — Get All Block Hashes
- `get_file_info_md5()` — Get File Information
- `get_host_details()` — Get Sensor(s) Information
- `get_process_list()` — Get All Processes
- `get_watchlist()` — Get Watchlist
- `hunt_file()` — Hunt file
- `isolate_sensor()` — Isolate Sensor
- `list_connections()` — Get Process Connections
- `run_query()` — Run Query
- `search_alert()` — Search Alerts
- `terminate_process()` — Terminate Process
- `unblock_hash()` — Unblock Hash
- `unisolate_sensor()` — Remove Isolation
- `update_alert()` — Update Alert


### `cisco-amp-endpoints` v1.0.1 _(installed)_
_Cisco AMP For Endpoints_

Cisco AMP for Endpoints provides complete protection against the most advanced attacks. Cisco AMP Connector facilitates automated operation related to endpoints,hunt indicator, blacklist hash, policies etc.

**22 operation(s)**:

- `application_blocking_list()` — Get Application Blocking Filelist
- `create_file_list_item()` — Add Hash to Blacklist
- `create_group()` — Create Group
- `delete_file_list_item()` — Delete Filelist Item
- `get_all_policies()` — Get All Policies
- `get_device_trajectory()` — Get Device Trajectory
- `get_device_trajectory_by_user()` — Get Device Trajectory By User
- `get_endpoint_by_guid()` — Get Computer Information
- `get_endpoints_by_activity()` — Hunt Indicator
- `get_event_types()` — Get Event Types
- `get_file_list()` — Get Specific Filelist
- `get_group()` — Get Specific Group
- `get_group_list()` — Get Group List
- `get_item()` — Get Item from Filelist
- `get_list_of_items()` — Get Items from Filelist
- `get_simple_custom_detection_list()` — Get Simple Custom Detection Filelist
- `get_specific_policy()` — Get Specific Policy
- `list_endpoints()` — Get All Computers
- `move_computer_to_group()` — Move Computer to Group
- `search_endpoints()` — Search Computers
- `search_event()` — Search Events
- `update_group()` — Update Group


### `crowd-strike-falcon` v3.1.0 _(installed)_
_CrowdStrike Falcon_

The CrowdStrike Falcon® platform is pioneering cloud-delivered endpoint protection. It both delivers and unifies IT Hygiene, next-generation antivirus, endpoint detection and response (EDR), managed threat hunting, and threat intelligence — all delivered via a single lightweight agent.

**55 operation(s)**:

- `add_host_to_host_group()` — Add Host To Host Group
- `admin_cmd_result()` — Get Admin Command Result
- `admin_cmd_run()` — Run Admin Command
- `alert_aggregates()` — Alert Aggregates
- `alert_search()` — Alert Search
- `apply_action_on_quarantine_files_by_file_id()` — Apply Action On Quarantine Files By File ID
- `apply_action_on_quarantine_files_by_query()` — Apply Action On Quarantine Files By Query
- `create_on_demand_scan()` — Create On Demand Scan
- `delete_ioc()` — Delete IOC
- `detection_aggregates()` — Detection Aggregates
- `detection_search()` — Detection Search
- `device_details()` — Get Device Details
- `execute_an_api_request()` — Execute an API Request
- `get_alert_details()` — Get Alert Details
- `get_custom_ioa_rule_name()` — Get Custom IOA Rule Name
- `get_cve_list_by_vulnerability()` — Spotlight: Get CVE List by Vulnerability
- `get_detection_details()` — Get Detection Details
- `get_device_online_status()` — Get Device Online Status
- `get_host_group_list()` — Get Host Group List
- `get_host_list_by_vulnerability()` — Spotlight: Get Host List by Vulnerability
- `get_ioc()` — Get IOC Details
- `get_list_of_processes()` — Get Processes Related to IOC
- `get_quarantine_files()` — Get Quarantine Files List
- `get_quarantine_files_aggregates()` — Get Quarantine Files Aggregates
- `get_quarantine_files_count()` — Get Quarantine Files Count
- `get_quarantine_files_metadata()` — Get Quarantine Files Metadata
- `get_scan_by_id()` — Get Scan By ID
- `get_uid()` — Get User ID
- `get_user_details()` — Get User Details
- `hunt_domain()` — Hunt Domain
- `hunt_file()` — Hunt File
- `incidents_get_crowdscores()` — Get Incidents Crowdstrike Score
- `incidents_get_details()` — Get Incident Details
- `incidents_query()` — Search Incidents
- `list_endpoint()` — Get Endpoint List
- `list_ioc()` — Get IOCs
- `list_user_id()` — Get User IDs List
- `list_usernames()` — Get Usernames List
- `process_details()` — Get Process Details
- `put_files_get()` — Get Executables Details by IDs
- `put_files_list()` — Get Executable List
- `quarantine_device()` — Contain the Host
- `remove_containment()` — Remove Containment
- `remove_host_from_host_group()` — Remove Host From Host Group
- `scripts_get()` — Get Scripts Details by IDs
- `scripts_list()` — Get Scripts List
- `search_devices()` — Search Devices
- `search_vulnerabilities()` — Spotlight: Search Vulnerabilities
- `session_file_download()` — Download Session File
- `session_file_list()` — Download Session File List
- `update_alert()` — Update Alert
- `update_detection()` — Update Detection
- `update_incidents()` — Update Incidents Status
- `update_ioc()` — Update IOC
- `upload_ioc()` — Create IOC


### `cybereason` v1.0.0 _(installed)_
_Cybereason_

The Cybereason Defense Platform combines endpoint prevention, detection, and response all in one lightweight agent.

**14 operation(s)**:

- `blacklist_file()` — Blacklist File
- `blacklist_ip_or_domain()` — Blacklist IP or Domain
- `get_malops()` — Get Incidents
- `get_sensors()` — Query Sensors
- `isolate_sensor_by_ip()` — Isolate Malop Machine by IP Address
- `isolate_sensor_by_pylum_id()` — Isolate Malop Machine by Pylum ID
- `kill_process()` — Kill Process On Endpoint
- `query_file()` — Query File by its Hash
- `query_process()` — Get Process On Endpoint
- `query_user()` — Query User
- `unisolate_sensor_by_ip()` — Un-Isolate Malop Machine by IP Address
- `unisolate_sensor_by_pylum_id()` — Un-Isolate Malop Machine by Pylum ID
- `whitelist_file()` — Whitelist File
- `whitelist_ip_or_domain()` — Whitelist IP or Domain


### `cylance-protect` v1.1.1 _(installed)_
_CylancePROTECT_

CylancePROTECT connector predicts, prevents, and protects threat in device

**14 operation(s)**:

- `block_hash()` — Block Hash
- `get_device_info()` — Get Device Information
- `get_device_threats()` — Get Device Threats
- `get_device_zones()` — Get Device Zones
- `get_devices()` — Get Devices
- `get_global_list()` — Get Global List
- `get_policies()` — Get Policies
- `get_threat_details()` — Get Threat Details
- `get_threat_devices()` — Get Threat Devices
- `get_threats()` — Get Threats
- `get_zones()` — Get Zones
- `unblock_hash()` — Unblock Hash
- `update_device_info()` — Update Device Information
- `update_device_threat()` — Update Device Threat


### `cymulate-endpoint-security` v1.0.0 _(installed)_
_Cymulate Endpoint Security - BAS_

Cymulate’s Endpoint Security vector allows organizations to deploy and run simulations of full attack scenario’s e.g. ransomware or implementation of MITRE ATT&CK TTPs on a dedicated endpoint in a controlled and safe manner, comprehensive testing that covers all aspects of endpoint security.

**14 operation(s)**:

- `create_assessment()` — Create Assessment
- `get_assessment_history()` — Get Assessment History
- `get_assessment_status()` — Get Assessment Status
- `get_attack_navigator_results()` — Get Attack Navigator Results
- `get_attack_navigator_results_by_assessment_id()` — Get Attack Navigator Results By Assessment ID
- `get_detection_results_by_payload_id()` — Get Detection Results By Payload ID
- `get_executive_report_results_by_assessment_id()` — Get Executive Report Results By Assessment ID
- `get_latest_report_results()` — Get Latest Report Results
- `get_latest_siem_detection_results()` — Get Latest SIEM Detection Results
- `get_latest_technical_report_results()` — Get Latest Technical Report Results
- `get_technical_report_results_by_assessment_id()` — Get Technical Report Results By Assessment ID
- `get_template_by_id()` — Get Template By ID
- `get_template_list()` — Get Template List
- `stop_assessment()` — Stop Assessment


### `deepsecurity` v1.1.0 _(installed)_
_Trend Micro Deep Security_

Trend Micro Deep Security

**7 operation(s)**:

- `assign_security_profile_to_host()` — Assign Security Profile
- `get_all_host_info()` — Get All Hosts
- `get_app_control_events()` — Get Application Control Events
- `get_events()` — Get Events
- `get_latest_alerts()` — Get Alerts
- `get_security_profile()` — Get Security Profile
- `scan_computer_by_host()` — Scan Endpoint


### `endgame` v1.0.0 _(installed)_
_Endgame_

This connector interfaces with the Endgame Endpoint Protection Platform to allow users to perform actions such as quarantining hosts

**14 operation(s)**:

- `execute_file()` — Execute File
- `get_alert_details()` — Get Alert Details
- `get_alert_timeline()` — Get Alert Timeline
- `get_alerts()` — Get Alerts
- `get_devices()` — Get Devices
- `get_endpoints()` — Get Endpoints
- `get_investigation_details()` — Get Investigation Details
- `get_investigations()` — Get Investigations
- `get_policies()` — Get policies
- `get_task_descriptions()` — Get Task Descriptions
- `get_users()` — Get Users
- `kill_process()` — Kill Process
- `update_investigation()` — Update Investigation
- `upload_file()` — Upload File


### `eset-protect-enterprise` v1.0.0 _(installed)_
_ESET Protect Enterprise_

ESET Protect Enterprise extended detection and response (XDR) that delivers enterprise-grade visibility, threat hunting and response options.

**11 operation(s)**:

- `block_executables()` — Block Executables
- `create_device_tasks()` — Create Device Task
- `end_computer_isolation_from_network()` — End Computer Isolation From Network
- `get_detection_groups()` — Get Detection Groups List
- `get_detections()` — Get Detections List
- `get_device()` — Get Device by UUID
- `get_device_groups()` — Get Device Groups List
- `get_device_tasks()` — Get Device Tasks List
- `get_executables()` — Get Executables List
- `isolate_computer_from_network()` — Isolate Computer From Network
- `unblock_executables()` — Unblock Executables


### `fidelis-edr` v1.1.0 _(installed)_
_Fidelis EDR_

Fidelis Endpoint EDR detects endpoint activity in real time and retrospectively so you can accelerate your response and stop adversaries at the point of entry. This connector supports following actions Get Alerts, Get Endpoints, Detete Endpoints, etc

**21 operation(s)**:

- `create_custom_task()` — Create Custom Task
- `create_task()` — Execute Task
- `delete_endpoint()` — Delete Endpoint
- `execute_script_package()` — Execute Script Package
- `get_alert_responses()` — Get Alert Responses
- `get_alerts()` — Get Alerts
- `get_api_info()` — Get API version Information
- `get_endpoints()` — Get Endpoints
- `get_endpoints_by_name()` — Get Endpoint By Name
- `get_endpoints_by_search_query()` — Get Endpoints By Search Query
- `get_installed_software()` — Get Installed Software
- `get_job_status_by_job_id()` — Get Job Status By Job ID
- `get_playbooks()` — Get Playbooks
- `get_playbooks_detail()` — Get Playbooks Details
- `get_playbooks_scripts()` — Get Playbooks And Scripts
- `get_script_packages()` — Get Script Packages
- `get_script_packages_file()` — Get Script Packages File
- `get_script_packages_manifest()` — Get Script Packages Manifest
- `get_script_packages_metadata()` — Get Script Packages Metadata
- `get_script_packages_template()` — Get Script Packages Template
- `script_job_results()` — Get Script Job Results


### `fireeye-hx` v1.3.0 _(installed)_
_Trellix Endpoint Security (HX)_

Trellix Endpoint Security (HX) brings advanced protection to endpoints. Its comprehensive endpoint visibility and threat intelligence enables analysts to adapt their defense based on real-time details to deploy informed, tailored responses to threat activity. This connector facilitates automated operations related to host, alerts, acquisition, quarantines, scripts etc.

**34 operation(s)** (+1 hidden):

- `approve_containment()` — Approve Host Containment
- `create_indicator_in_category()` — Create Indicator in Specified Category
- `data_acquisition_request()` — Data Acquisition using Script
- `data_acquisition_status()` — Get Data Acquisition Status
- `delete_indicator()` — Delete Indicator
- `full_containment()` — Contain a Host as an Admin
- `get_alert_details()` — Get Alert Details
- `get_all_scripts()` — Get All Scripts
- `get_category_indicator()` — Get Indicator from Category
- `get_data_acquisition_package()` — Fetch a Data Acquisition Package
- `get_file_acquisition_package()` — Fetch a File Acquisition Package
- `get_file_acquisition_status()` — Get File Acquisition Information
- `get_host()` — Get Host
- `get_quarantine_file_acquisition_status()` — Get Quarantine File Acquisition Information
- `get_quarantined_files_package()` — Get Quarantine File
- `get_script_by_id()` — Fetch a Script by ID
- `get_triage_acquisition_status()` — Get Triage Acquisition Information
- `get_triage_collection()` — Fetch a Triage Collection
- `list_alerts()` — List Alerts
- `list_data_acquisitions()` — List Host Data Acquisitions
- `list_host_alerts()` — List Host Alerts
- `list_hosts()` — List Hosts
- `list_script_for_all_host()` — List All Scripts Details
- `list_triage_acquisitions()` — List Triage Acquisitions
- `new_file_acquisition()` — Create a File Acquisition for a Host
- `new_quarantined_file_acquisition()` — Request Quarantined File Acquisition
- `new_triage_acquisition()` — Create a Triage Acquisition for a Host
- `parse_mans_file()` — Parse Mandiant Analysis File
- `quarantine_list_by_host_id()` — Get Quarantine List
- `release_containment()` — Release Host from Containment
- `request_containment()` — Request Host Containment
- `search_ind_all_category()` — Search Indicator in All Categories
- `start_search()` — Perform Generic Search


### `fortinet-forticlient-ems` v1.2.0 _(installed)_
_Fortinet FortiClient EMS_

FortiClient Enterprise Management Server (FortiClient EMS) is a security management solution that enables scalable and centralized management of multiple endpoints (computers).This connector provides operations related to quarantine/unquarantine endpoints, get endpoint details, etc

**13 operation(s)**:

_investigation_
- `add_custom_tag(ids: text, tag_id: text)` — Add Custom Tag to Endpoint
- `create_custom_tag(tag_name: text, [device_id: text])` — Create Custom Tag
- `create_zero_trust_tag(name: text)` — Create Zero Trust Tag
- `delete_custom_tag(ids: text)` — Delete Custom Tag
- `delete_zero_trust_tag(id: text)` — Delete Zero Trust Tag
- `get_endpoint_details(device_id: integer)` — Get Endpoint Details
- `get_endpoints([device_id: integer], [group_id: integer], [client_id: integer], [client_os: text], [client_version: text], [activity: select], [connection: select], [event_type: select], [management: select], [status: select], [view_type: select], [verification: json], [filters: json], [order_by: text], [order_asc: checkbox], [count: integer], [offset: integer], [custom_attributes: json])` — Get All Endpoints
- `get_zero_trust_rule_sets([filters: json], [sort_col: select], [sort_ord: select], [count: integer], [offset: integer], [custom_attributes: json])` — Get Zero Trust Rule Sets List
- `get_zero_trust_rule_tags()` — Get Zero Trust Rule Tags List
- `get_zero_trust_tag_by_id(id: text)` — Get Zero Trust Tag By ID
- `quarantine_endpoints(ids: text)` — Quarantine Endpoints
- `remove_custom_tag(ids: text, tag_id: text)` — Remove Custom Tag From Endpoint
- `unquarantine_endpoints(ids: text)` — Unquarantine Endpoints


### `harfanglab-edr` v1.1.0 _(installed)_
_HarfangLab EDR_

The connector allows FortiSOAR users to fetch data and take actions on Hurukai HarfangLab EDR platform

**7 operation(s)**:

- `change_security_event_status()` — Change Security Event Status
- `fetch_security_events()` — Fetch Security Events
- `get_event_by_id()` — Get Event By ID
- `isolate_endpoint()` — Isolate an Endpoint
- `search_endpoint()` — Search Endpoints
- `search_multiple_iocs_in_telemetry()` — Search Multiple IoCs
- `unisolate_endpoint()` — Unisolate an Endpoint


### `ibm-bigfix` v1.0.0 _(installed)_
_IBM BigFix_

IBM BigFix connector handle actions like, get endpoints, get patches list etc.

**6 operation(s)**:

- `deploy_patch()` — Create Action
- `get_host()` — Get Bigfix ID
- `list_computer_group()` — Get Computer Groups List 
- `list_endpoints()` — Get Endpoints
- `list_fixlets()` — Get Patches List
- `list_sites()` —  Get Sites List


### `ibm-security-qradar-edr` v1.0.0 _(installed)_
_IBM Security QRadar EDR_

IBM Security QRadar EDR, formerly ReaQta, remediates known and unknown endpoint threats in near real time with easy-to-use intelligent automation that requires little-to-no human interaction.

**5 operation(s)**:

- `add_notes_to_alert()` — Add Notes To Alert
- `close_alert_by_id()` — Close Alert By ID
- `get_alert_by_id()` — Get Alert By ID
- `get_alert_list()` — Get Alert List
- `get_events_related_to_alerts()` — Get Events Related To Alerts


### `kaspersky-security-center` v1.0.2 _(installed)_
_Kaspersky Security Center_

Kaspersky Security Center makes it easy to manage and secure both physical and virtual endpoints from a single, unified management console.

**12 operation(s)**:

- `add_group()` — Add Group
- `add_policy_request()` — Add Policy
- `delete_group()` — Delete Specific Group
- `get_groups()` — Get All Groups Details
- `get_host_details()` — Get Host Details
- `get_hosts_group_static_info()` — Get Host Group Static Info
- `get_listhost_group()` — Get Host List
- `get_policy_request()` — Get Specific Policy
- `get_product_installed()` — Get Products Installed
- `get_software_installed()` — Get Software Installed on Specific Host
- `list_policies_request()` — Get All Policies on Specific Group
- `move_hosts()` — Move Host to Specific Group


### `malwarebytes` v2.0.0 _(installed)_
_Malwarebytes_

Malwarebytes protects endpoints against malware, ransomware, and other advanced online threats, This connector facilitates automated operations like get endpoints, scan endpoints, get threats etc

**24 operation(s)**:

- `assign_group_to_endpoints()` — Assign Group to Endpoints
- `create_group()` — Create Group
- `create_policy()` — Create Policy
- `delete_endpoints()` — Delete Endpoints
- `delete_group()` — Delete Group
- `delete_policy()` — Delete Policy
- `get_endpoint_agent_info()` — Get Endpoint Agent Info
- `get_endpoint_assets()` — Get Endpoint Assets
- `get_endpoint_details()` — Get Endpoint Details
- `get_endpoint_network_info()` — Get Endpoint Network Info
- `get_endpoint_quarantined_items()` — Get Endpoint Quarantined Items
- `get_endpoint_status()` — Get Endpoint Status
- `get_endpoint_suspicious_activities()` — Get Endpoint Suspicious Activities
- `get_endpoints()` — Get Endpoints
- `get_events()` — Get Events
- `get_groups()` — Get Groups
- `get_policies()` — Get Policies
- `get_scan_result()` — Get Scan Result
- `get_tasks()` — Get Tasks
- `quarantine_endpoints()` — Quarantine Endpoints
- `remediate_endpoint_suspicious_activity()` — Remediate Endpoint Suspicious Activity
- `scan_endpoints()` — Scan Endpoints
- `unquarantine_endpoints()` — Unquarantine Endpoints
- `update_endpoint_suspicious_activity()` — Update Endpoint Suspicious Activity


### `mcafee-epo` v1.1.1 _(installed)_
_McAfee ePO_

McAfee ePolicy Orchestrator Connector can used to run client task, add tags, remove tags, search client task,search systems, check task status, wakeup agent, list tables, execute query etc

**11 operation(s)**:

- `apply_tag()` — Apply Tag
- `check_task_status()` — Check Task Status
- `clear_tag()` — Clear Tag
- `execute_query()` — Execute Query
- `list_databases()` — List Databases
- `list_queries()` — List Queries
- `list_tables()` — List Tables
- `run_client_task()` — Run Client Task
- `search_systems()` — Search Systems
- `search_text()` — Search Client Task
- `wakeup_agent()` — Wakeup Agent


### `microsoft-365-defender` v1.2.0 _(installed)_
_Microsoft 365 Defender_

Microsoft 365 Defender For Endpoints is a unified platform for preventative protection, post-breach detection, automated investigation, and response. This connector facilitates the automated operations related to files, machines, IP, Domain, actor etc.

**4 operation(s)**:

- `advanced_hunting()` — Advanced Hunting
- `get_incident()` — Get Incident Details
- `list_incidents()` — Get Incidents List
- `update_incident()` — Update Incident


### `microsoft-sccm` v1.0.0 _(installed)_
_Microsoft SCCM_

Microsoft SCCM Connector

**3 operation(s)**:

- `deploy_patch()` — Deploy Patch
- `get_device_collections()` — Get All Device Collections
- `get_patches()` — Get All Software Updates


### `microsoft-wmi` v1.1.0 _(installed)_
_Microsoft WMI_

Microsoft WMI provides investigative actions like, get system services, get processes, get system information etc. that are executed on a Windows endpoint.

**5 operation(s)**:

- `get_processes()` — Get Processes
- `get_services()` — Get Services
- `get_system_information()` — Get System Information
- `get_users()` — Get Users
- `run_Query()` — Run Query


### `nexthink` v1.0.0 _(installed)_
_Nexthink_

Nexthink is an automation and remediation platform which delivers visibility across all environments so IT teams can continuously improve the digital workplace to optimize productivity and cost.

**1 operation(s)**:

- `nexthink_query_language()` — Run Query


### `paloalto-cortex-xdr` v1.4.0 _(installed)_
_Palo Alto Cortex XDR_

Cortex XDR applies machine learning at cloud scale to rich network, endpoint, and cloud data, so you can quickly find and stop targeted attacks, insider abuse, and compromised endpoints.

**32 operation(s)**:

- `blacklist_files()` — Blacklist Files
- `cancel_scan_endpoints()` — Cancel Scan Endpoints
- `create_distributions()` — Create Distributions
- `delete_endpoints()` — Delete Endpoints
- `fetch_incidents()` — Fetch Incidents
- `get_alerts()` — Get Alerts
- `get_all_endpoints()` — Get All Endpoints
- `get_audit_agent_report()` — Get Audit Agent Report
- `get_audit_management_log()` — Get Audit Management Logs
- `get_device_violations()` — Get Device Violations
- `get_distribution_status()` — Get Distribution Status
- `get_distribution_url()` — Get Distribution URL
- `get_distribution_version()` — Get Distribution Version
- `get_endpoints()` — Get Endpoints
- `get_incident_details()` — Get Incident Details
- `get_policy()` — Get Policy
- `get_quarantine_status()` — Get Quarantine Status
- `get_query_result_by_query_id()` — Get Query Results By Query ID
- `insert_cef_alerts()` — Insert CEF Alerts
- `insert_parsed_alerts()` — Insert Parsed Alerts
- `insert_simple_indicators()` — Insert Simple Indicators
- `isolate_endpoints()` — Isolate Endpoints
- `quarantine_files()` — Quarantine Files
- `restore_file()` — Restore File
- `retrieve_file()` — Retrieve File
- `retrieve_file_details()` — Retrieve File Details
- `scan_endpoints()` — Scan Endpoints
- `unisolate_endpoints()` — Unisolate Endpoints
- `update_alerts()` — Update Alerts
- `update_incident()` — Update Incident
- `whitelist_files()` — Whitelist Files
- `xql_query()` — Execute XQL Query


### `rapid7-velociraptor` v1.0.0 _(installed)_
_Rapid7 Velociraptor_

Rapid7 Velociraptor is a unique, advanced open-source endpoint monitoring, digital forensic and cyber response platform. It provides you with the ability to more effectively respond to a wide range of digital forensic and cyber incident response investigations and data breaches.

**11 operation(s)**:

- `create_flow_download()` — Create Flow Download
- `create_hunt()` — Create Hunt
- `create_hunt_download()` — Create Hunt Download
- `dump_artifact_definitions()` — Dump Artifact Definitions
- `get_flow_results()` — Get Flow Results
- `get_hunt_results()` — Get Hunt Results
- `list_clients()` — Get Clients List
- `list_flows()` — Get Flows List
- `list_hunts()` — Get Hunts List
- `run_artifacts_collection()` — Run Artifacts Collection
- `run_vql_query()` — Run VQL Query


### `red-canary` v1.0.0 _(installed)_
_Red Canary_

Red Canary collects endpoint data using Carbon Black Response and CrowdStrike Falcon. The collected data is standardized into a common schema, which allows teams to detect, analyze and respond to security incidents.

**9 operation(s)**:

- `acknowledge_detection()` — Acknowledge Detection
- `deisolate_endpoint()` — Deisolate Endpoint
- `get_detection()` — Get Detection Details
- `get_endpoint()` — Get Endpoint Details
- `isolate_endpoint()` — Isolate Endpoint
- `list_detection_marked_indicators_of_compromise()` — List Detection Marked Indicators of Compromise
- `list_detections()` — Get Detections List
- `list_endpoints()` — Get Endpoints List
- `update_remediation_state()` — Update Remediation State


### `symantec-edr` v2.0.0 _(installed)_
_Symantec EDR_

Symantec Endpoint Detection and Response(EDR) performs the critical security tasks that detect, protect and respond to threats to your network.

**32 operation(s)**:

- `add_incident_comment()` — Add Comment to Incident
- `cancel_command()` — Cancel Command
- `close_incident()` — Close Incident
- `command_result()` — Get Command Result
- `create_blacklist_policies()` — Create Blacklist Policy
- `delete_blacklist_policy()` — Delete Blacklist Policy
- `delete_endpoint_file()` — Delete File from Endpoint
- `endpoint_eoc_search()` — Search EOC on Endpoint
- `endpoint_recorder_search()` — Search Artifact on Endpoint
- `execute_sandbox_commands()` — Execute Sandbox Commands
- `get_appliance_information()` — Get Appliance Information
- `get_blacklist_policies()` — Get Blacklist Policies
- `get_command_status()` — Get Command State
- `get_domain_entities()` — Get Domain Entities
- `get_domain_instance()` — Get Domain Instances
- `get_domain_instance_by_domain_name()` — Get Domain Instance by Domain Name
- `get_endpoint_entities()` — Get Endpoint Entities
- `get_endpoint_instances()` — Get Endpoint Instances
- `get_entities()` — Get Entities
- `get_events()` — Get Events
- `get_file_entities()` — Get File Entities
- `get_file_entity_by_sha2()` — Get File Entity by SHA256
- `get_file_from_endpoint()` — Get File from Endpoint
- `get_file_instances()` — Get File Instances
- `get_incident_comment()` — Get Incident Comments
- `get_incidentevents()` — Get Incident Related Events
- `get_incidents()` — Get Incidents
- `get_sandbox_command_status()` — Get Sandbox Commands Status
- `get_specific_endpoint_instances()` — Get Specific Endpoint Instances
- `isolate_endpoint()` — Isolate Endpoint
- `rejoin_endpoint()` — Rejoin Endpoint
- `update_blacklist_policy_comment()` — Update Blacklist Policy Comment


### `symantec-edr-cloud` v2.0.0 _(installed)_
_Symantec EDR Cloud_

Symantec Endpoint Detection and Response Cloud helps in keeping attacks from turning into breaches and eliminate intrusions across all endpoints

**5 operation(s)**:

- `add_whitelist()` — Add SHA256 to Whitelist
- `delete_whitelist()` — Delete SHA256 from Whitelist
- `get_alerts()` — Get Alerts
- `get_report()` — Get Alert Details
- `list_whitelist()` — Get Whitelist


### `symantec-sepm` v1.1.1 _(installed)_
_Symantec EPM (SEPM)_

Integrate with Symantec Endpoint Protection to execute investigative actions like list endpoints, and scan endpoint, in addition to actions like add blacklist and delete blacklist.

**26 operation(s)**:

- `active_scan_endpoint()` — Active Scan Endpoint
- `add_blacklist()` — Add Blacklist
- `assign_fingerprint_to_group()` — Assign Fingerprint List To Group
- `client_list_group_by_content_version()` — List Client For Group By Content Version
- `client_list_reporting_malware_events()` — Get Malware Reporting Clients
- `create_domain()` — Create Domain
- `critical_events_info()` — Get Critical Events Information
- `delete_blacklist()` — Delete Blacklist
- `delete_domain()` — Delete Domain
- `full_scan_endpoint()` — Full Scan Endpoint
- `get_command_status()` — Get Command Status
- `get_computers()` — List Endpoints
- `get_domain_info()` — Get Domain Information
- `get_domain_name()` — Get Domain Name
- `get_domains()` — List Domains
- `get_fingerprint_list_info()` — Get Fingerprint List Information
- `get_group_info()` — Get Group Information
- `get_threat_stats()` — Get Threat Status
- `list_client_groups_by_content_source()` — Get Client Groups By Content Source
- `list_groups()` — List Groups
- `list_infected_clients()` — List Infected Client
- `quarantine_endpoints()` — Quarantine Endpoints/Groups
- `scan_endpoint()` — Scan Endpoint
- `unquarantine_endpoints()` — Unquarantine Endpoints/Groups
- `update_blacklist()` — Update Blacklist
- `updates_domain_info()` — Update Domain


### `tanium` v2.0.1 _(installed)_
_Tanium_

Tanium is an endpoint security and system management solution. This connector facilitates the automated operations like get computer information,installed softwares,running processes,execute package on machine,issue saved question, ask question and reissue action

**7 operation(s)**:

- `ask_question()` — Ask Question
- `execute_package_on_machine()` — Execute Package on Machine
- `get_computer_information()` — Get Computer Information
- `get_installed_software()` — Get Installed Softwares
- `get_running_processes()` — Get Running Processes
- `issue_saved_question()` — Issue a Saved Question
- `reissue_action()` — Reissue Action


### `tanium-threat-response` v1.0.0 _(installed)_
_Tanium Threat Response_

Tanium Threat Response monitors the entire IT ecosystem for suspicious files, misconfiguration of registry settings, and other security risks while alerting security teams in real-time. This connector facilitates automated operations to manage endpoints processes, evidence, alerts, files, snapshots, and connections.

**12 operation(s)**:

- `create_evidence()` — Create Evidence
- `create_snapshot()` — Create Snapshot
- `get_connections()` — Get Connections
- `get_downloaded_file()` — Get Downloaded File
- `get_events_by_process()` — Get Events By Process
- `get_file_download_info()` — Get File Download Info
- `get_file_info()` — Get File Info
- `get_parent_process()` — Get Parent Process
- `get_parent_process_tree()` — Get Parent Process Tree
- `get_process_children()` — Get Process Children
- `get_process_tree()` — Get Process Tree
- `update_alert_state()` — Update Alert State


### `tehtris-edr` v1.0.0 _(installed)_
_TEHTRIS EDR_

TEHTRIS EDR (Endpoint Detection and Response) is designed to detect, analyze, and respond to security incidents on endpoints (such as computers, servers, and mobile devices) in real time.

**41 operation(s)**:

- `create_filter()` — Create Filter
- `create_new_global_policies()` — Create New Global Policies
- `delete_filter()` — Delete Filter
- `execute_an_api_call()` — Execute an API Request
- `fetch_events()` — Fetch Events
- `fetch_info_about_endpoint()` — Fetch Endpoint Details
- `get_accesslogs()` — Get Access Logs
- `get_all_endpoints()` — Get All Endpoints
- `get_all_global_policies()` — Get All Global Policies
- `get_browser_security()` — Get Browser Security
- `get_current_scan_status()` — Get Current Scan Status
- `get_disk_scan_status()` — Get Disk Scan Status
- `get_filter_by_id()` — Get Filter by ID
- `get_history_of_processes()` — Get Processes History
- `get_isolation_status()` — Get Isolation Status
- `get_last_offline_forensic_report()` — Get Last Offline Forensic Report
- `get_network_infos()` — Get Network Information
- `get_offline_forensic_status()` — Get Offline Forensic Status
- `get_persistence_entries()` — Get Persistence Entries
- `get_process_tree()` — Get Process Tree
- `get_software_list()` — Get Software List
- `get_tags()` — Get Tags
- `get_unmanaged_hosts()` — Get Unmanaged Hosts
- `get_usb_history()` — Get USB History
- `get_users_connected()` — Get Users Connected
- `launch_disk_scan()` — Launch Disk Scan
- `list_folders_and_filters()` — List Folders and Filters
- `list_quarantine_files()` — Get All Quarantine Files
- `quarantine_file()` — Quarantine a File
- `restore_file_from_quarantine()` — Restore File from Quarantine
- `search_binaries()` — Search Binaries
- `search_persistent_entries()` — Search Persistent Entries
- `search_persistent_entries_category()` — Search Persistent Entries by Category
- `search_user_accesslogs()` — Search User Access Logs
- `send_isolation_action()` — Send Isolation Action
- `set_event_status()` — Set an event status
- `start_offline_forensic()` — Start Offline Forensic
- `stop_current_scan()` — Stop Current Scan
- `stop_offline_forensic()` — Stop Offline Forensic
- `update_endpoints_tags()` — Update Endpoints Tags
- `update_filter()` — Update Filter


### `trendmicro-endpoint-sensor` v1.0.0 _(installed)_
_Trend Micro Endpoint Sensor_

Connector for Trend Micro Endpoint Sensor which can be used to automate retro scans and retrieve their results

**5 operation(s)**:

- `check_task_status()` — Check Task Status
- `get_endpoints_for_task()` — Get Endpoints for Task
- `get_report_summary()` — Get Report Summary
- `retro_scan()` — Retro Scan
- `search_endpoint_by_ip()` — Search Endpoint By IP


### `vmware-carbon-black-enterprise-edr` v1.0.0 _(installed)_
_VMware Carbon Black Enterprise EDR_

VMware Carbon Black Enterprise EDR is an advanced threat hunting and incident response solution delivering unfiltered visibility for top security operations centers (SOCs) and incident response (IR) teams. This connector facilitates automated operations related to devices, watchlists, reports etc.

**22 operation(s)**:

- `create_report()` — Create Report
- `create_watchlist()` — Create Watchlist
- `delete_watchlist()` — Delete Watchlist
- `disable_watchlist_alerts()` — Disable Watchlist Alerts
- `enable_watchlist_alerts()` — Enable Watchlist Alerts
- `get_all_watchlist()` — Get All Watchlists
- `get_device_details()` — Get Device Details
- `get_ioc_ignore_status()` — Get IOC Ignore Status
- `get_report()` — Get Report
- `get_report_ignore_status()` — Get Report Ignore Status 
- `get_watchlist()` — Get Watchlist
- `get_watchlist_alert_status()` — Get Watchlist Alert Status
- `get_watchlist_telemetry()` — Get Watchlist Telemetry
- `ignore_ioc()` — Ignore IOC
- `ignore_report()` — Ignore Report
- `quarantine_device()` — Quarantine Device
- `reactive_ioc()` — Re-activate IOC
- `reactive_report()` — Re-activate Report
- `search_devices()` — Search Devices
- `search_watchlist_alerts()` — Search Watchlist Alerts
- `unquarantine_device()` — Unquarantine Device
- `update_watchlist()` — Update Watchlist


### `windows-defender-atp` v3.0.0 _(installed)_
_Microsoft Defender For Endpoints_

Microsoft Defender For Endpoints is a unified platform for preventative protection, post-breach detection, automated investigation, and response. This connector facilitates the automated operations related to files, machines, IP, Domain, actor etc.

**35 operation(s)**:

- `advanced_hunting()` — Run Advanced Hunting Query
- `collect_investigation_package()` — Collect Investigation Package
- `collect_investigation_package_link()` — Get Investigation Package SAS URI
- `delete_indicator()` — Delete Indicator
- `get_alert_by_id()` — Get Alert by ID
- `get_alert_list()` — Get Alert List
- `get_alert_related_domain()` — Get Domains by Alert
- `get_alert_related_file()` — Get Files by Alert
- `get_alert_related_ip()` — Get IPs by Alert
- `get_alert_related_machine()` — Get Machines by Alert
- `get_domain_related_alerts()` — Get Domain Related Alerts
- `get_domain_related_machines()` — Get Domain Related Machines
- `get_domain_statistics()` — Get Domain Statistics
- `get_file_info()` — Get File Information
- `get_file_related_alerts()` — Get File Related Alerts
- `get_file_related_machines()` — Get File Related Machines
- `get_file_statistics()` — Get File Statistics
- `get_indicator_list()` — Get Indicator List
- `get_ip_related_alerts()` — Get IP Related Alerts
- `get_ip_statistics()` — Get IP Statistics
- `get_machine_action()` — Get Machine Action
- `get_machine_action_collection_list()` — Get Machine Action List
- `get_machine_alerts()` — Get Machine Alerts
- `get_machine_by_id()` — Get Machine By ID
- `get_machine_info_ip()` — Find Machine Information by IP
- `get_machine_list()` — Get Machines List
- `get_machine_logged_user()` — Get Machine Logged on Users
- `isolate_machine()` — Isolate Machine
- `offboard_machine()` — Offboard Machine
- `remove_app_restriction()` — Remove Application Restriction
- `remove_isolation()` — Remove Isolation
- `restrict_app()` — Restrict Application Execution
- `run_antivirus_scan()` — Run Antivirus Scan
- `submit_indicator()` — Submit Indicator
- `update_alert()` — Update Alert


---

## Enterprise mobility management

### `airwatch` v1.0.0 _(installed)_
_AirWatch_

AirWatch Connector which enables profile and product settings to be manipulated within the platform

**7 operation(s)**:

- `activate_product()` — Activate Product
- `activate_profile()` — Activate Profile
- `deactivate_product()` — Deactivate Product
- `deactivate_profile()` — Deactivate Profile
- `get_device_information()` — Get Device Information
- `get_product()` — Get Product
- `get_profile()` — Get Profile


---

## Firewall

### `cisco-asa` v2.0.2 _(installed)_
_Cisco ASA_

Cisco ASA connector that you can use to Get Version of the device, Block and Unblock IP Address, List and Terminate Sessions etc.

**8 operation(s)**:

_Remediation_
- `terminate_sessions(username: text)` — Terminate Sessions

_containment_
- `block_ip(dest: text, src: text, direction: select, access_list: text, interface: text)` — Block IP
- `run_custom_commands(custom_commands: text)` — Run Custom Commands
- `update_group(group_name: text, method: select, ip: text)` — Update Network Group

_investigation_
- `get_network_group(group_name: text)` — Get Network Group
- `get_version()` — Get Version
- `list_sessions()` — List Sessions

_remediation_
- `unblock_ip(dest: text, src: text, direction: select, access_list: text, interface: text)` — Unblock IP


---

## Firewall and Network Protection

### `akamai-waf` v1.0.2 _(installed)_
_Akamai WAF_

Akamai Web Application Firewall (WAF) is a cloud-based security solution designed to protect web applications from various cyber threats. It acts as a shield between internet traffic and web servers, inspecting incoming requests to detect and block malicious activities

**9 operation(s)**:

- `activate_network_list()` — Activate Network List
- `append_elements_to_network_list()` — Append Elements to Network List
- `create_network_list()` — Create Network List
- `delete_element_from_network_list()` — Delete an Element from Network List
- `delete_network_by_id()` — Delete Network by ID
- `get_activation_status_of_network_list()` — Get Activation Status of Network List
- `get_network_by_id()` — Get Network by ID
- `get_network_list()` — Get Network List
- `update_network_list()` — Update Network List


### `azure-firewall` v2.0.1 _(installed)_
_Azure Firewall_

Azure Firewall connector helps to protect your Azure Virtual Network resources. It is a fully stateful firewall as a service with built-in high availability and unrestricted cloud scalability.

**18 operation(s)**:

- `block_ip()` — Block IP
- `delete_firewall()` — Delete Firewall
- `delete_firewall_policy()` — Delete Firewall Policy
- `delete_firewall_policy_rule_collection()` — Delete Firewall Policy Rule Collection Group
- `delete_ip_group()` — Delete Firewall IP Group
- `get_all_ip_group()` — Get IP Groups List
- `get_firewall()` — Get Firewall
- `get_firewall_policies()` — Get Firewall Policies List
- `get_firewall_policy()` — Get Firewall Policy
- `get_firewall_policy_rule_collection()` — Get Firewall Policy Rule Collection Group
- `get_firewall_policy_rule_collection_groups()` — Get Firewall Policy Rule Collection Groups List
- `get_firewalls_list()` — Get Firewalls List
- `get_ip_group()` — Get Firewall IP Group
- `get_service_tag()` — Get Service Tag
- `list_learned_prefixes()` — List Learned Prefixes
- `unblock_ip()` — Unblock IP
- `update_firewall_policy_tags()` — Update Firewall Policy Tags
- `update_firewall_tags()` — Update Firewall Tags


### `azure-front-door-waf` v1.0.0 _(installed)_
_Azure Front Door WAF_

Azure Front Door Service enables you to define, manage, and monitor the global routing for your web traffic by optimizing for best performance and instant global failover for high availability. With Front Door, you can transform your global (multi-region) consumer and enterprise applications into robust, high-performance personalized modern applications, APIs, and content that reach a global audience with Azure.

**6 operation(s)**:

- `block_ip()` — Block IP
- `create_or_update_policy()` — Create or Update Policy
- `delete_policy()` — Delete Policy
- `get_policies_list()` — Get Policies List
- `get_policy_details()` — Get Policy Details
- `unblock_ip()` — Unblock IP


### `azure-web-application-firewall` v1.0.0 _(installed)_
_Azure Web Application Firewall_

The Azure WAF (Web Application Firewall) integration provides centralized protection of your web applications from common exploits and vulnerabilities. It enables you to control policies that are configured in the Azure Firewall management platform, and allows you to add, delete, or update policies, and also to get details of a specific policy or a list of policies.

**4 operation(s)**:

- `create_or_update_policy()` — Create Or Update Policy
- `delete_policy()` — Delete Policy
- `get_policy()` — Get Policy
- `list_policies()` — Get Policy List


### `checkpoint-firewall` v2.1.0 _(installed)_
_Check Point Firewall_

Check Point Firewall that can use for block/unblock IP, Application, URL

**14 operation(s)**:

- `block_applications()` — Block Applications
- `block_ip()` — Block IP Address
- `block_urls()` — Block URLs
- `check_policies()` — Validate Configuration Policies
- `discard_session()` — Terminate Session
- `get_blocked_application_names()` — Get Blocked Application Names
- `get_blocked_ip_addresses()` — Get Blocked IP Addresses
- `get_blocked_urls()` — Get Blocked URLs
- `get_list_of_applications()` — Get Applications Detail
- `get_session()` — Get Session
- `show_sessions()` — Get Sessions
- `unblock_applications()` — Unblock Applications
- `unblock_ip()` — Unblock IP Address
- `unblock_urls()` — Unblock URLs


### `checkpoint-management-console` v1.0.0 _(installed)_
_CheckPoint Management Console_

CheckPoint Management Console helps you to configure and view the security policy and objects in a Security Management Server or Multi Domain Server using CLI tools and web-services.

**5 operation(s)**:

- `add_host()` — Create Host
- `delete_host()` — Delete Host
- `get_host_details()` — Get Host Details
- `get_hosts_list()` — Get Hosts List
- `update_host()` — Update Host


### `cisco-firepower` v3.0.2 _(installed)_
_Cisco Firepower_

Cisco Firepower is your administrative nerve center for managing critical Cisco network security solutions. It provides a complete and unified management of firewalls, application control, intrusion prevention, URL filtering, and advanced malware protection.

**6 operation(s)**:

- `assign_policy_to_device()` — Assign Policy To Device
- `block_ip()` — Block IP
- `delete_access_policy()` — Delete Access Policy
- `get_policy()` — List Access Policy
- `list_device()` — List Device
- `unblock_ip()` — Unblock IP


### `cisco-meraki-mx-l3` v1.0.0 _(installed)_
_Cisco Meraki MX L3 Firewall_

Cisco Meraki MX L3 Firewall gives administrators complete control over the users, content, and applications on their network. This connector facilitates automated operations to fetch firewall rules, update the firewall rules etc.

**2 operation(s)**:

- `get_network_appliance_firewall_rules()` — Get Network Appliance Firewall L3 Firewall Rules
- `update_network_appliance_firewall_rules()` — Update Network Appliance Firewall L3 Firewall Rules


### `cisco-meraki-mx-l7-firewall` v1.1.0 _(installed)_
_Cisco Meraki MX L7 Firewall_

Cisco Meraki MX L7 Firewall gives administrators complete control over the users, content, and applications on their network. This connector facilitates automated operations to fetch firewall rules, update the firewall rules etc.

**3 operation(s)**:

- `get_network_firewall_rules()` — Get Network L7 Firewall Rules
- `get_network_firewall_rules_application_categories()` — Get Network L7 Firewall Rules Application Categories
- `update_network_firewall_rules()` — Update Network L7 Firewall Rules


### `cisco-meraki-mx-vpn-firewall` v1.0.0 _(installed)_
_Cisco Meraki MX VPN Firewall_

Cisco Meraki MX VPN Firewall gives administrators the ability to add firewall rules to restrict the traffic flow through the VPN tunnel for a Cisco Meraki MX Security Appliance. This connector facilitates automated operations to fetch firewall rules, update the firewall rules etc.

**2 operation(s)**:

- `get_vpn_firewall_rules()` — Get Organization VPN Firewall Rules
- `update_organization_firewall_rules()` — Update Organization VPN Firewall Rules


### `cloudflare-waf` v1.0.0 _(installed)_
_Cloudflare WAF_

Cloudflare Web Application Firewall (WAF) integration allows customers to manage firewall rules, filters, and IP Lists. It also allows to retrieve zones list for each account.

**16 operation(s)**:

- `create_filter()` — Create Filter
- `create_firewall_rule()` — Create Firewall Rule
- `create_ip_items_list()` — Create IP Items List
- `create_ip_list()` — Create IP List
- `delete_filter()` — Delete Filter
- `delete_firewall_rule()` — Delete Firewall Rule
- `delete_ip_list()` — Delete IP List
- `delete_ip_list_item()` — Delete IP List Items
- `get_ip_list_item()` — Get IP List Items
- `get_ip_lists()` — Get IP Lists
- `list_filters()` — List Filters
- `list_firewall_rules()` — List Firewall Rules
- `list_zones()` — List Zones
- `update_filter()` — Update Filter
- `update_firewall_rule()` — Update Firewall Rule
- `update_ip_list_item()` — Update IP List Items


### `cymulate-web-application-firewall` v1.0.0 _(installed)_
_Cymulate Web Application Firewall - BAS_

The Cymulate Web Application Firewall will validate the configuration, implementation, and efficacy, to ensure that the Web Application Firewall blocks malicious payloads before they get to your Web Application. Technical reports provide analysis of the attacks and actionable mitigation guidance that help security teams to shore up their defenses against web application attacks.

**14 operation(s)**:

- `get_executive_report_results_by_id()` — Get Executive Report Results By Assessment ID
- `get_technical_report_results()` — Get Technical Report Results
- `get_technical_report_results_by_id()` — Get Technical Report Results By Assessment ID
- `get_waf_assessment_history()` — Get WAF Assessment History
- `get_waf_assessment_status()` — Get WAF Assessment Status
- `get_waf_payload_response()` — Get WAF Payload Response
- `get_waf_report_results()` — Get WAF Report Results
- `get_waf_site_ids()` — Get WAF Site IDs
- `get_waf_site_results()` — Get WAF Site Results
- `get_waf_sites()` — Get WAF Sites
- `get_waf_template_by_id()` — Get WAF Template By ID
- `get_waf_templates()` — Get WAF Templates
- `launch_waf_assessment()` — Launch WAF Assessment
- `stop_waf_assessment()` — Stop WAF Assessment


### `f5-big-ip` v1.0.0 _(installed)_
_F5 BIG IP_

This connector supports containment and remediation Actions like block IP or unblock IP

**2 operation(s)**:

- `block_ip()` — Block IP
- `unblock_ip()` — Unblock IP


### `fastly-next-gen-waf` v1.0.0 _(installed)_
_Fastly Next-Gen WAF_

Fastly Next-Gen WAF offers advanced web application protection with automated security measures, real-time monitoring, and rapid incident response. It provides robust defense by managing security policies, detecting threats, and enforcing rule sets to protect web applications.

**16 operation(s)**:

- `add_ip_to_allow_list()` — Add IP Address to Allow List
- `add_ip_to_block_list()` — Add IP Address to Block List
- `expire_event_by_id()` — Expire Event By ID
- `get_alert_details()` — Get Alert Details
- `get_all_site_lists()` — Get All Site Lists
- `get_event_details()` — Get Event Details
- `get_site_allow_list()` — Get Site Allow List
- `get_site_block_list()` — Get Site Block List
- `get_site_list_by_id()` — Get Site List Details
- `list_alerts()` — List Alerts
- `list_corps()` — List Corporations
- `list_events()` — List Events
- `list_sites_in_corp()` — List Sites in Corporation
- `remove_ip_from_allow_list()` — Remove IP Address from Allow List
- `remove_ip_from_block_list()` — Remove IP Address from Block List
- `update_alert()` — Update Alert


### `fortigate-firewall` v5.4.0 _(installed)_
_Fortinet FortiGate_

Fortinet FortiGate enterprise firewall provide high performance, consolidated advanced security and granular visibility for broad protection across the entire digital attack surface.

**44 operation(s)** (+1 hidden):

_containment_
- `block_applications(app_list: text, [vdom: text])` — Block Application
- `block_ip(method: select)` — Block IP Address (Deprecated)
- `block_ip_new(method: select)` — Block IP Address
- `block_url(url: text, [vdom: text])` — Block URL
- `quarantine_host(macs: text, [vdom: text])` — Quarantine Host
- `unquarantine_host(macs: text, [vdom: text])` — Unquarantine Host

_investigation_
- `create_address(address_category: select, [vdom: text])` — Create Address
- `create_address_group(address_group_category: select, [vdom: text])` — Create Address Group
- `create_firewall_service(name: text, [category: text], [protocol: select], [comment: text], [visibility: select], [vdom: text])` — Create Service
- `create_policy(name: text, srcintf: text, dstintf: text, srcaddr: text, dstaddr: text, service: text, schedule: text, [status: select], [action: select], [comment: text], [additional_args: json], [vdom: text])` — Create Policy
- `create_service_group(name: text, [members: text], [comment: text], [vdom: text])` — Create Service Group
- `create_user(user_type: select, [two-factor: select], [status: select], [user_group: select], [vdom: text])` — Create User
- `delete_address(address_category: select, name: text, [vdom: text])` — Delete Address
- `delete_address_group(address_group_category: select, group_name: text, [vdom: text])` — Delete Address Group
- `delete_firewall_service(name: text, [vdom: text])` — Delete Service
- `delete_policy(policyid: text, [vdom: text])` — Delete Policy
- `delete_service_group(name: text, [vdom: text])` — Delete Service Group
- `delete_user(name: text, [vdom: text])` — Delete User
- `execute_command(cmd_list: text, username: text, [password: password], [private_key: file], [port: integer], [interactive: checkbox], [timeout: integer])` — Execute Command
- `get_address_groups([address_group_category: select], [group_name: text], [vdom: text])` — Get Address Groups
- `get_addresses([address_category: select], [name: text], [vdom: text])` — Get Addresses
- `get_blocked_applications([vdom: text])` — Get Blocked Applications
- `get_blocked_ip(method: select, [vdom: text])` — Get Blocked IP Addresses
- `get_blocked_urls([vdom: text])` — Get Blocked URLs
- `get_entries_from_edl(mkey: text, [status_only: checkbox], [vdom: text])` — Get Entries from External Dynamic List
- `get_firewall_services([name: text], [vdom: text])` — Get Services
- `get_list_of_applications()` — Get Applications Detail
- `get_list_of_policies([policyid: text], [ngfw_mode: select], [vdom: text])` — Get List of Policies
- `get_quarantine_hosts([vdom: text])` — Get Quarantine Hosts
- `get_service_groups([name: text], [vdom: text])` — Get Service Groups
- `get_system_events([filter: text], [location: select], [start: text], [rows: text])` — Get System Events
- `get_user_list_login_details(username: text)` — Get User Last Login Details
- `get_users([name: text], [start: integer], [count: integer], [vdom: text])` — Get Users
- `modify_entries_in_edl(mkey: text, action: select, entries: text, [vdom: text])` — Modify Entries in External Dynamic List
- `update_address(address_category: select, [vdom: text])` — Update Address
- `update_address_group(address_group_category: select, [vdom: text])` — Update Address Group
- `update_firewall_service(name: text, [new_name: text], [category: text], [protocol: select], [comment: text], [visibility: select], [vdom: text])` — Update Service
- `update_policy(policyid: text, [name: text], [status: select], [srcintf: text], [dstintf: text], [add_srcaddr: text], [remove_srcaddr: text], [add_dstaddr: text], [remove_dstaddr: text], [add_service: text], [remove_service: text], [schedule: text], [action: select], [comment: text], [additional_args: json], [vdom: text])` — Update Policy
- `update_service_group(name: text, [new_name: text], [add_member: text], [remove_member: text], [comment: text], [vdom: text])` — Update Service Group
- `update_user(user_type: select, [two-factor: select], [auth_type: select], [fortitoken: text], [send_activation_code: select], [email-to: email], [sms: select], [status: select], [user_group_name: text], [user_group_name_to_remove: text], [vdom: text])` — Update User

_remediation_
- `unblock_applications(app_list: text, [vdom: text])` — Unblock Application
- `unblock_ip(method: select, [vdom: text])` — Unblock IP Address
- `unblock_url(url: text, [vdom: text])` — Unblock URL


### `juniper-junos` v1.0.0 _(installed)_
_Juniper JunOS_

Provides JunOS REST API Integration covering Juniper MX, PTX, QFX, T and SRX Series platforms

**8 operation(s)**:

- `add_to_address_set()` — Add an Object to Global Address Set
- `add_to_prefix_list()` — Add Address(es) to a Prefix List
- `config_action()` — Run Configuration Command
- `delete_from_address_set()` — Delete Object from Global Address Set
- `delete_from_prefix_list()` — Delete Address(es) from a Prefix List
- `get_address_set()` — Get Address Set
- `get_prefix_list()` — Get Prefix List
- `op_action()` — Run Command


### `netscaler-adc` v1.0.1 _(installed)_
_NetScaler ADC_

The NetScaler appliance is an application switch which performs application-specific traffic analysis to intelligently distribute, optimize, and secure Layer 4-Layer 7 (L4–L7) network traffic for web applications.

**4 operation(s)**:

- `change_acl_resource_state()` — Change NetScaler ACL Resource State
- `create_acl_resource()` — Create NetScaler ACL Resource
- `delete_acl_resource()` — Delete NetScaler ACL Resource
- `get_acl_resource()` — Get NetScaler ACL Resource


### `palo-alto-networks-panorama` v3.2.0 _(installed)_
_Palo Alto Networks Panorama_

This app integrates with the Palo Alto Networks Firewall to support containment actions like 'block url', 'block application', 'block ip', 'unblock url', 'unblock application' and 'unblock ip'

**11 operation(s)**:

- `add_host_id_to_quarantine_list()` — Add Host ID To Quarantine List
- `block_app()` — Block Application
- `block_ip()` — Block IP
- `block_url()` — Block URL
- `delete_host_id_from_quarantine_list()` — Delete Host ID From Quarantine List
- `firewall_list()` — Get Connected Firewalls
- `get_application_groups()` — Get Application Groups
- `get_device_groups()` — Get Device Groups
- `unblock_app()` — Unblock Application
- `unblock_ip()` — Unblock IP
- `unblock_url()` — Unblock URL


### `paloalto-firewall` v3.3.0 _(installed)_
_Palo Alto Firewall_

Palo Alto Firewall is serving as a Security Operating Platform for a long time and has been a pioneer in offering cybersecurity services. The Palo Alto Security Operating Platform makes your system and network secured from successful cyber attacks in a highly efficient and automatic way.

**30 operation(s)**:

- `add_address_to_specific_group()` — Add IP Address to Address Group
- `block_app()` — Block Application
- `block_ip()` — Block IP
- `block_url()` — Block URL
- `create_address()` — Create IP Address Object
- `create_address_group()` — Create Address Group
- `create_external_dynamic_list()` — Create External Dynamic List
- `create_security_rule()` — Create Security Policy Rule
- `delete_address()` — Delete IP Address Object
- `delete_address_group()` — Delete Address Group
- `delete_external_dynamic_list()` — Delete External Dynamic List
- `delete_security_rule()` — Delete Security Policy Rule
- `edit_address()` — Update IP Address Object
- `edit_security_rule()` — Update Security Policy Rule
- `get_address_details()` — Get Specific IP Address Object Details
- `get_address_group()` — Get Address Group Details
- `get_address_group_list()` — Get All Address Group List
- `get_address_list()` — Get All Address List
- `get_external_dynamic_list()` — Get External Dynamic List
- `list_security_rule()` — Get All Security Policy Rules List
- `move_security_rule()` — Move Security Policy Rule
- `remove_address_from_specific_group()` — Remove IP Address from Address Group
- `rename_address()` — Rename IP Address Object Name
- `rename_address_group()` — Rename Specific Address Group
- `rename_external_dynamic_list()` — Rename External Dynamic List
- `rename_security_rule()` — Rename Security Policy Rule
- `unblock_app()` — Unblock Application
- `unblock_ip()` — Unblock IP
- `unblock_url()` — Unblock URL
- `update_external_dynamic_list()` — Update External Dynamic List


### `pfsense` v1.0.0 _(installed)_
_PfSense_

PfSense Connector capable of adding/deleting firewall rules on PfSense platform

**3 operation(s)**:

- `add_rule()` — Add Rule
- `delete_rule()` — Delete Rule
- `get_rules()` — Get All Rules


### `sonicwall-firewall` v1.1.0 _(installed)_
_SonicWall Firewall_

SonicWall's advanced firewall appliances with various network and security systems. This connector facilitates seamless communication and data exchange between the SonicWall Firewall and other network elements, providing enhanced security, management, and monitoring capabilities

**10 operation(s)**:

- `add_address_object_to_group()` — Add Address Object to Group
- `create_address_group()` — Create Address Group
- `create_address_object_configuration()` — Create Address Object
- `delete_address_group()` — Delete Address From Group
- `delete_address_object_configuration()` — Delete Address Object
- `get_address_group()` — Get Address Group
- `get_address_object_configuration()` — Get Address Object
- `remove_address_object_from_group()` — Remove Address Object from Group
- `update_address_group()` — Update Address in Group
- `update_address_object_configuration()` — Update Address Object


### `sophos-xg` v1.0.0 _(installed)_
_Sophos XG Firewall_

Sophos XG Firewall

**10 operation(s)**:

- `block_applications()` — Block Applications
- `block_ips()` — Block IP Addresses
- `block_urls()` — Block URLs
- `check_policies()` — Check Policies
- `get_blocked_applications()` — Get List of Blocked Application Names
- `get_blocked_ips()` — Get List of Blocked IPs
- `get_blocked_urls()` — Get List of Blocked URLs
- `unblock_applications()` — Unblock Applications
- `unblock_ips()` — Unblock IP Addresses
- `unblock_urls()` — Unblock URLs


### `tufin` v1.0.0 _(installed)_
_Tufin_

Search for and enforce network security policies, perform network topology searches, and query network device information across managed firewalls, SDNs and cloud environments.

**10 operation(s)**:

- `tufin_get_change_info()` — Get Change Info
- `tufin_get_zone_for_ip()` — Get Zone for IP
- `tufin_policy_search()` — Policy Search
- `tufin_resolve_object()` — Resolve Object
- `tufin_search_application_connections()` — Search Application Connections
- `tufin_search_applications()` — Search Applications
- `tufin_search_devices()` — Search Devices
- `tufin_search_topology()` — Search Topology
- `tufin_search_topology_image()` — Search Topology Image
- `tufin_submit_change_request()` — Submit Change Request


---

## FortiSOAR Essentials

### `cyops-schedule-report` v1.5.0 _(installed, system)_
_Report Engine_

Provides operations to generate a report manually or through schedules.

**4 operation(s)** (+1 hidden):

_investigation_
- `schedule_report(scheduler: text)` — Generate Report From Schedule
- `schedule_report_manual(report_id: text, user_id: text, [timezone: text], [query_params: text])` — Generate Report From Report ID

- `generate_csv_export(query: object, [moduleName: select], [moduleType: text], userId: text, [exportFileName: text], [csvNeutralization: checkbox], [max_record_size: integer], [batchSize: integer])` — Export Data as a CSV


---

## HTTP Requests

### `http` v1.0.0 _(installed)_
_HTTP_

HTTP connector provides http requests

**7 operation(s)**:

_investigation_
- `http_delete(rest_api: text, [header: json], [data: json], [parameter: json])` — HTTP DELETE request
- `http_get(rest_api: text, [header: json], [parameter: json])` — HTTP GET Request
- `http_head(rest_api: text)` — HTTP HEAD request
- `http_options(rest_api: text, [header: json])` — HTTP OPTIONS Request
- `http_patch(rest_api: text, [header: json], [data: json], [parameter: json])` — HTTP PATCH request
- `http_post(rest_api: text, [header: json], [data: json], [parameter: json])` — HTTP POST Request
- `http_put(rest_api: text, [header: json], [data: json], [parameter: json])` — HTTP PUT Request


---

## IT Service

### `google-drive` v1.0.0 _(installed)_
_Google Drive_

Google drive connector can be used to list, add, remove, download and upload files from google drive using playbook.

**5 operation(s)**:

- `delete_file()` — Delete File
- `download_file()` — Download File
- `empty_trash()` — Empty Trash
- `get_all_files()` — Get File List
- `upload_file()` — Upload File


---

## IT Service Management

### `atlassian-confluence-server` v1.0.0 _(installed)_
_Atlassian Confluence Server_

Atlassian Confluence is a team workspace where knowledge and collaboration meet. Create, collaborate, and organize all your work in one place.

**7 operation(s)**:

- `create_content()` — Create Content
- `create_space()` — Create Space
- `delete_content()` — Delete Content
- `get_content_list()` — Get Content List
- `get_content_list_using_cql()` — Get Content List Using CQL
- `get_spaces_list()` — Get Spaces List
- `update_content()` — Update Content


### `atlassian-status-page` v1.0.0 _(installed)_
_Atlassian Status Page_

This connector enables automated operations such as creating incidents, retrieving incident lists, managing active maintenances, and more.

**11 operation(s)**:

- `create_incident()` — Create Incident
- `delete_incident()` — Delete Incident
- `execute_api_request()` — Execute an API Request
- `get_active_maintenance()` — Get Active Maintenance Incidents
- `get_incident()` — Get Incident
- `get_list_incidents()` — Get Incident List
- `get_list_status_pages()` — Get Status Pages
- `get_scheduled_incidents()` — Get Scheduled Incidents
- `get_unresolved_incidents()` — Get Unresolved Incidents
- `get_upcoming_incidents()` — Get Upcoming Incidents
- `update_incident()` — Update Incident


### `axios-assyst` v1.0.0 _(installed)_
_Axios Assyst_

Axios assyst is a comprehensive ITSM platform that supports all ITIL® processes and combines ITSM best practices with modern collaboration features. This connector provides an automated way to create, search, update, and close tickets in Axios Assyst.

**5 operation(s)**:

- `close_ticket()` — Close Ticket
- `create_ticket()` — Create Ticket
- `get_ticket_details()` — Get Ticket Details
- `search_tickets()` — Search Tickets
- `update_ticket()` — Update Ticket


### `azure-resource-health` v1.0.0 _(installed)_
_Azure Resource Health_

Azure Resource Health helps you diagnose and get support for service problems that affect your Azure resources, it reports on the current and past health of your resources. This connector supports actions related to availability status and events.

**7 operation(s)**:

- `get_availability_status()` — Get Availability Status
- `get_availability_status_by_resource_group()` — Get Current Availability Status by Resource Group
- `get_availability_status_by_subscription_id()` — Get Current Availability Status by Subscription ID
- `get_availability_status_list()` — Get Availability Transitions List
- `get_event_list_for_resource()` — Get Event List for Resource
- `get_event_list_for_subscription_id()` — Get Event List for Subscription ID
- `get_event_list_for_tenant_id()` — Get Event List for Tenant ID


### `bmc-remedyforce` v1.2.0 _(installed)_
_BMC Remedyforce_

BMC Remedyforce connector performs actions around creation and updation of incidents, interacts with knowledge base, service and approval requests.

**21 operation(s)** (+1 hidden):

- `add_client_note()` — Add Client Note to a Service Request
- `all_knowledge_articles()` — Get All Knowledge Articles
- `all_service_requests()` — Get All Service Requests
- `approve_pending_request()` — Approve Pending Approval Request
- `create_incident()` — Create Incident
- `download_file()` — Download file
- `get_categories()` — Get Categories
- `get_cmdb_attributes()` — Get CMDB Attributes
- `get_incident_details()` — Get Incident Details
- `get_pending_approval_request()` — Get Pending Approval Request
- `get_queue_details()` — Get Queue Details
- `get_queues()` — Get Sobject's Queue
- `knowledge_search()` — Knowledge Search
- `list_client_ids()` — Get List of Remedyforce Users
- `query_service_request_by_id()` — Get Service Request Detail By IDs
- `reassign_pending_request()` — Reassign Pending Approval Request
- `reject_pending_request()` — Reject Pending Approval Request
- `run_query()` — Run Query
- `search_kb_article()` — Get Knowledge Article Details
- `update_incident()` — Update Incident


### `bmcremedy` v1.5.0 _(installed)_
_BMC Remedy AR System_

BMC Remedy Action Request System (BMC Remedy AR System) enables you to automate a broad range of business solutions, from service desk call tracking to inventory management to integrated systems management.

**14 operation(s)**:

- `add_work_info()` — Add Work Info
- `create_change_request()` — Create Change Management Request
- `create_incident()` — Create Incident
- `create_task()` — Create Task
- `create_work_order()` — Create Work Order
- `get_all_change_mgmt_requests()` — Get All Change Management Requests
- `get_all_incidents()` — Get All Incidents
- `get_change_request()` — Get Change Management Request
- `get_incident_details()` — Get Incident Details
- `query_change_request()` — Query Change Request
- `query_remedy_incident()` — Query Remedy Incident
- `update_change_request()` — Update Change Management Request
- `update_incident()` — Update Incident
- `upload_attachment_to_incident()` — Upload Attachment to Incident


### `cherwell` v1.0.0 _(installed)_
_Cherwell_

Cherwell connector

**6 operation(s)**:

- `advance_search()` — Advance Search
- `create_incident()` — Create Incident
- `quick_search()` — Quick Search
- `report_template()` — Show Incident Template
- `update_cyops_incident()` — Update CyOPs Incident
- `update_incident_in_cherwell()` — Update Cherwell Incident


### `easyvista` v1.0.0 _(installed)_
_EasyVista_

EasyVista Service Manager manages the entire process of designing, managing and delivering IT services. This connector facilitates operations like get employee list, get asset list

**7 operation(s)**:

- `get_asset()` — Get Asset
- `get_employee()` — Get Employee
- `get_manufacturer()` — Get Manufacturer
- `list_assets()` — Get Asset List
- `list_employees()` — Get Employee List
- `list_manufacturers()` — Get Manufacturer List
- `search_query()` — Search Query


### `ibm-security-guardium-insights` v1.0.0 _(installed)_
_IBM Security Guardium Insights_

IBM Security Guardium Insights is a data security platform that provides real-time monitoring, analysis, and protection for sensitive information across hybrid cloud environments. It helps organizations identify and prioritize potential threats, ensuring data privacy and compliance by detecting unusual activities and vulnerabilities. With its advanced analytics and machine learning capabilities, Guardium Insights helps businesses safeguard critical data assets from unauthorized access, ensuring data integrity and reducing the risk of data breaches.

**15 operation(s)**:

- `get_cases_list()` — Get Cases List
- `get_compliance_data()` — Get Compliance Data
- `get_connections_list()` — Get Connections List
- `get_dataset_data()` — Get Dataset Data
- `get_datasets_list()` — Get Datasets List
- `get_group_members_list()` — Get Group Members List
- `get_groups_list()` — Get Groups List
- `get_notifications_list()` — Get Notifications List
- `get_policies_list()` — Get Policies List
- `get_policy_details()` — Get Policy Details
- `get_report_categories_list()` — Get Report Categories List
- `get_reports_list()` — Get Reports List
- `get_scheduled_job_details()` — Get Scheduled Job Details
- `get_schedules_list()` — Get Schedules List
- `get_tasks_list()` — Get Tasks List


### `kaseya` v1.0.0 _(installed)_
_Kaseya_

Kaseya is IT management and monitoring tool used to perform operations for agent procedure, audit and patch scan.

**11 operation(s)**:

- `cancel_agent_procedure()` — Cancel Agent Procedure
- `get_addremoveprograms()` — Get List of All Add/Remove Programs
- `get_agent_procedures()` — Get Agent Procedures
- `get_agents()` — Get Agents
- `get_audit_summary()` — Get Audit Summary
- `get_patch_status()` — Get Patch Status
- `run_agent_procedure()` — Run Agent Procedure
- `run_latest_audit()` — Run Latest Audit
- `run_patch_scan()` — Run Patch Scan
- `schedule_agent_procedure()` — Schedule Agent Procedure
- `schedule_latest_audit()` — Schedule Latest Audit


### `logicmonitor` v1.0.0 _(installed)_
_LogicMonitor_

LogicMonitor is a SaaS-based performance monitoring platform that provides full visibility into complex, hybrid infrastructures, offering granular performance monitoring and actionable data and insights. This connector enables automated operations such as Get Alert List, Get Device Group List, Get Device List, Get Device Alerts, Get Report List, and Get Report by ID.

**6 operation(s)**:

- `get_alert_list()` — Get Alert List
- `get_device_alerts()` — Get Device Alerts
- `get_device_group_list()` — Get Device Group List
- `get_device_list()` — Get Device List
- `get_report_by_id()` — Get Report by ID
- `get_report_list()` — Get Report List


### `manage-engine-service-desk-plus` v3.0.0 _(installed)_
_ManageEngine ServiceDesk Plus_

ManageEngine ServiceDesk Plus is used in turning IT teams from daily fire-fighting to delivering awesome customer service. It provides great visibility and central control in dealing with IT issues to ensure that businesses suffer no downtime. This connector provides automated actions to create, update, delete and close tickets

**10 operation(s)**:

- `add_note()` — Add Note
- `add_request()` — Create Ticket
- `add_resolution()` — Add Resolution
- `close_request()` — Close Ticket
- `delete_request()` — Delete Ticket
- `delete_request_from_trash()` — Delete Ticket From Trash
- `get_all_open_requests()` — Get All Open Tickets
- `get_all_requester()` — Get All Requesters
- `get_request()` — Get Ticket Details
- `update_request()` — Update Ticket


### `micro-focus-service-manager` v1.4.0 _(installed)_
_Micro Focus Service Manager_

Micro Focus service manager connector helps you to create incident, update incident, list incidents, get incident, get device list and get device

**16 operation(s)**:

- `create_change()` — Create Change
- `create_incident()` — Create Incident
- `create_rf()` — Create RF - Request Fulfillment Ticket
- `delete_an_attachment()` — Delete Attachment
- `download_an_attachment()` — Download Attachment
- `get_change_request()` — Get Change Request
- `get_device()` — Get Device
- `get_device_list()` — Get Device List
- `get_incident()` — Get Incident
- `get_rf()` — Get RF - Request Fulfillment Ticket
- `list_changes()` — Get Change List
- `list_incidents()` — Get Incident List
- `retrieve_attachment_information()` — Retrieve Attachment Information
- `update_change()` — Update Change
- `update_incident()` — Update Incident
- `update_rf_attachment()` — Update RF - Request Fulfillment Ticket for an attachment


### `middesk` v1.0.0 _(installed)_
_Middesk_

Middesk is an identity platform that automates business verification and underwrites decisions. It also provides data on businesses and notifies service providers of changes to its customer base allowing them to form an accurate picture of their customers and offer the critical products their customers need to establish,operate, and maintain their businesses.

**4 operation(s)**:

- `create_business()` — Create Business
- `get_business()` — Get Business
- `get_businesses_list()` — Get Businesses List
- `update_business()` — Update Business


### `otrs` v1.0.3 _(installed)_
_OTRS_

OTRS is a service management suite. OTRS connector provides functionality to create, modify, and search tickets.

**4 operation(s)**:

- `create_ticket()` — Create Ticket
- `get_ticket()` — Get Ticket
- `search_tickets()` — List Tickets
- `update_ticket()` — Update Ticket


### `solarwinds-pingdom` v1.0.0 _(installed)_
_Solarwinds Pingdom_

Solarwinds Pingdom makes your websites faster and more reliable with easy-to-use web performance and digital experience monitoring.

**5 operation(s)**:

- `get_alerts_list()` — Get Alerts List
- `get_checks_list()` — Get Checks List
- `get_raw_test_results_list()` — Get Raw Test Results List
- `get_result_of_analysis()` — Get Result of Analysis
- `get_root_cause_analysis()` — Get Root Cause Analysis


### `ssp-portal` v1.0.0 _(installed)_
_SSP Portal_

Connector for the ExxonMobil Self-Service Portal (SSP) to manage On-Premises Port Opening Requests (PORs).

**3 operation(s)**:

_investigation_
- `get_por(por_id: integer)` — Get POR
- `get_pors(porsType: text)` — Get PORs
- `make_http_request(method: select, endpoint: text, [payload: json])` — Make HTTP Request


### `zabbix` v1.0.0 _(installed)_
_Zabbix_

Zabbix is an open-source, enterprise-grade monitoring platform that provides real-time visibility into the performance and availability of IT infrastructure, including servers, networks, applications, services, and cloud environments.

**4 operation(s)**:

- `execute_generic_rest_api_call()` — Execute Generic JSON RPC Request
- `get_alerts()` — Get Alerts
- `get_events()` — Get Events
- `get_problems()` — Get Problems


---

## IT Service Management,Network Security,Compliance and Reporting

### `tcp-wave` v1.0.0 _(installed)_
_TCP Wave_

TCPWave offers automated DDI (DNS, DHCP, IPAM) workflow management, providing significant benefits to large-scale organizations. It reduces manual tasks, enhances IT productivity, and enables a focus on strategic initiatives that drive business growth. By standardizing network management processes, TCPWave enforces best practices and facilitates rapid, scalable service delivery.

**3 operation(s)**:

- `check_object_exists()` — Check Object Exists
- `get_network_details_by_ipaddress()` — Get Network Details by IP Address
- `get_object_details_by_ipaddress()` — Get Object Details By IP Address


---

## IT Services

### `aws-commands` v1.1.0 _(installed)_
_AWS Commands_

AWS Commands are used to run AWS native commands for AWS resources configurations directly from FortiSOAR.

**34 operation(s)**:

- `add_network_acl_rule()` — Add Network ACL Rule
- `add_security_group_to_instance()` — Add Security Group To Instance
- `add_tag_to_instance()` — Add Instance Tag
- `attach_instance_to_auto_scaling_group()` — Attach Instance To Auto Scaling Group
- `attach_volume()` — Attach Volume
- `authorize_egress()` — Authorize Egress
- `authorize_ingress()` — Authorize Ingress
- `create_network_acl()` — Create Network ACL
- `create_security_group()` — Create Security Groups
- `delete_network_acl()` — Delete Network ACL
- `delete_network_acl_rule()` — Delete Network ACL Rule
- `delete_security_group()` — Delete Security Groups
- `delete_volume()` — Delete Volume
- `deregister_instance_from_elb()` — Deregister Instance from ELB
- `describe_instance()` — Get Instance Details
- `describe_network_acls()` — Get Details of Network ACLs
- `describe_user()` — Get User Details
- `detach_instance_from_autoscaling_group()` — Detach Instance From Auto Scaling Group
- `detach_volume()` — Detach Volume
- `generic_command()` — Execute AWS Command
- `get_details_for_all_images()` — Get AMIs Detail
- `get_details_of_security_group()` — Get Details of Security Group
- `get_security_groups()` — Get Security Groups
- `instance_api_termination()` — Instance API Termination 
- `launch_instance()` — Launch Instance
- `reboot_instance()` — Reboot Instance
- `register_instance_to_elb()` — Register Instance To ELB
- `revoke_all_active_sessions()` — Revoke All Active Sessions
- `revoke_egress()` — Revoke Egress
- `revoke_ingress()` — Revoke Ingress
- `snapshot_volume()` — Capture Volume Snapshot
- `start_instance()` — Start Instance
- `stop_instance()` — Stop Instance
- `terminate_instance()` — Terminate Instance


### `azure-blob-storage` v1.1.0 _(installed)_
_Azure Blob Storage_

Azure Blob Storage is Microsoft's object storage solution for the cloud. Blob Storage is optimized for storing massive amounts of unstructured data. Azure Blob Storage stores text and binary data as objects in the cloud. This connector helps you to perform REST operations for working with blobs in the Blob service.

**9 operation(s)**:

- `abort_copy_blob()` — Abort Copy Blob
- `copy_blob()` — Copy Blob
- `create_blob()` — Create Blob
- `delete_blob()` — Delete Blob
- `get_blob()` — Get Blob
- `get_blob_metadata()` — Get Blob Metadata
- `get_blob_properties()` — Get Blob Properties
- `get_blob_tags()` — Get Blob Tags
- `list_blob()` — List Blobs


### `azure-notification-hub` v1.0.0 _(installed)_
_Azure Notification Hub_

Azure Notification Hubs provide an easy-to-use and scaled-out push engine that allows you to send notifications to any platform (iOS, Android, Windows, Kindle, Baidu, etc.) from any backend (cloud or on-premises).

**4 operation(s)**:

- `create_notification_hub()` — Create Notification Hub
- `delete_notification_hub()` — Delete Notification Hub
- `list_notification_hubs()` — Get Notification Hubs List
- `update_notification_hub()` — Update Notification Hub


### `azure-storage` v1.0.0 _(installed)_
_Azure Storage_

Deploy and manage storage accounts and blob services. This connector facilitates the automated operations related to storage account, blob services and blob containers.

**12 operation(s)**:

- `create_blob_container()` — Create Blob Container
- `delete_blob_container()` — Delete Blob Container
- `delete_storage_account()` — Delete Storage Account
- `get_blob_container()` — Get Blob Container
- `get_blob_service_properties()` — Get Blob Service Properties
- `get_storage_account()` — Get Storage Account
- `list_blob_containers()` — List Blob Containers
- `list_blob_services()` — List Blob Services
- `list_storage_accounts()` — List Storage Accounts
- `set_blob_service_properties()` — Set Blob Service Properties
- `update_blob_container()` — Update Blob Container
- `update_storage_account()` — Update Storage Account


### `azure-storage-table` v1.0.0 _(installed)_
_Azure Storage Table_

Azure Table storage is a service that stores non-relational structured data (also known as structured NoSQL data) in the cloud, providing a key/attribute store with a schemaless design. this connector helps you to create, update, delete, query on azure storage table.

**7 operation(s)**:

- `create_table()` — Create Table
- `delete_entity_table()` — Delete Entity Into Table
- `delete_table()` — Delete Table
- `insert_entity_table()` — Insert Entity Into Table
- `query_entity_table()` — Query Entity Into Table
- `query_table()` — Query Table
- `update_entity_table()` — Update Entity Into Table


### `box` v1.0.0 _(installed)_
_Box_

Box is an enterprise content management platform that solves simple and complex challenges, from sharing and accessing files

**13 operation(s)**:

- `create_folder()` — Create Folder
- `create_group()` — Create Group
- `create_user()` — Create User
- `delete_user()` — Delete User
- `download_file()` — Download File
- `get_current_user()` — Get Current User
- `get_file_information()` — Get File Information
- `get_folder_information()` — Get Folder Information
- `get_group()` — Get Group
- `get_user()` — Get User
- `move_folder()` — Move Folder
- `update_user()` — Update User
- `upload_file()` — Upload File


### `goanywhere` v1.0.0 _(installed)_
_GoAnywhere_

GoAnywhere MFT is a secure file transfer solution that organizations use to exchange their data safely. The solution helps organizations automate their data transfers, centralize file transfer activity, monitor file transfers and user access. This connector facilitates automated operation related to File Transfer Summary, Active Sessions Details, and Completed Jobs Summary.

**3 operation(s)**:

- `get_active_sessions_details()` — Get Active Sessions Details
- `get_completed_jobs_summary()` — Get Completed Jobs Summary
- `get_file_transfer_summary()` — Get File Transfer Summary


### `google-resource-manager` v1.0.0 _(installed)_
_Google Cloud Resource Manager_

Google Cloud Resource Manager is a service provided by Google Cloud Platform (GCP) that helps you manage your GCP resources across projects. It provides a unified interface for organizing, viewing, and controlling access to your cloud resources.

**8 operation(s)**:

- `create_project()` — Create Project
- `delete_project()` — Delete Project
- `get_organization_details()` — Get organization Details
- `get_project_details()` — Get Project Details
- `restore_project()` — Restore Project
- `search_organizations()` — Search Organizations
- `search_projects()` — Search Projects
- `update_project()` — Update Project


### `itglue` v1.0.0 _(installed)_
_ITGlue_

ITGlue is IT documentation software designed to help you maximize the efficiency, transparency and consistency of your team. This connector facilitates automated operations such as organizations, locations, configurations, domains, and flexible assets

**5 operation(s)**:

- `get_configurations()` — Get Configurations
- `get_domains()` — Get Domains
- `get_flexible_asset()` — Get Flexible Asset
- `get_locations()` — Get Locations
- `get_organizations()` — Get Organizations


### `rsa-archer` v2.0.0 _(installed)_
_RSA Archer_

RSA Archer connector provide automated operations for Audit Management, Issue Management, Operational Risk Management.

**11 operation(s)**:

- `create_record()` — Create Record
- `get_all_groups()` — Get All Groups Details
- `get_all_modules()` — Get Details For All Modules
- `get_all_users()` — Get All Users Details
- `get_fields_ids()` — Get Fields Details of Module
- `get_record_by_id()` — Get Record
- `get_records_by_report()` — Get Records By Report
- `get_reports()` — Get Details For All Reports
- `get_reports_by_module_id()` — Get Reports Details of Module
- `get_values_list_value()` — Get Values List Item
- `update_record()` — Update Record


### `servicenow-cmdb` v1.0.0 _(installed)_
_ServiceNow CMDB_

ServiceNow Configuration Management Database (CMDB) is a centralized source that gives you full visibility into your IT environment. By storing information about your organization's infrastructure and how it is configured, this system allows you to monitor your network and ensure stability and best performance.

**9 operation(s)**:

- `add_relation_to_configuration_item()` — Add Relation to Configuration Item
- `create_configuration_item()` — Create Configuration Item
- `custom_endpoint()` — Custom API Endpoint
- `delete_relation_for_configuration_item()` — Delete Relation for Configuration Item
- `get_cmdb_rel_type()` — Get CMDB Relation Type
- `get_cmdb_rel_type_by_sys_id()` — Get CMDB Relation Type by System ID
- `get_configuration_item_details()` — Get Configuration Item Details
- `get_configuration_items()` — Get Configuration Items
- `update_configuration_item()` — Update Configuration Item


### `vmware-tanzu-service-mesh` v1.0.0 _(installed)_
_VMware Tanzu Service Mesh_

VMware Tanzu® Service Mesh™ is VMware's enterprise-class service mesh solution that provides consistent control and security for microservices, end users, and data—across all your clusters and clouds—in the most demanding multicluster and multicloud environments.

**24 operation(s)**:

- `create_cluster()` — Create Cluster
- `create_global_namespace()` — Create Global Namespace
- `delete_global_namespace()` — Delete Global Namespace
- `delete_job()` — Delete Job
- `download_job()` — Download Job
- `generate_security_token_for_cluster()` — Generate Security Token for Cluster
- `get_capabilities_enabled_for_global_namespace()` — Get Capabilities Enabled for Global Namespace
- `get_cluster_details()` — Get Clusters Details
- `get_cluster_logs()` — Get Cluster Logs
- `get_cluster_onboard_url()` — Get Cluster Onboard URL
- `get_clusters()` — Get Clusters List
- `get_global_namespace_details()` — Get Global Namespace Details
- `get_global_namespaces()` — Get Global Namespaces
- `get_job_details()` — Get Job Details
- `get_jobs()` — Get Jobs List
- `get_member_services_in_global_namespace()` — Get Member Services in Global Namespace
- `get_resource_groups()` — Get Resource Groups
- `get_status_for_capability_enabled_for_global_namespace()` — Get Status for Capability Enabled for Global Namespace
- `get_tanzu_service_mesh_version()` — Get Tanzu Service Mesh Version
- `remove_cluster_from_tanzu_service_mesh()` — Remove Cluster from Tanzu Service Mesh
- `uninstall_tanzu_service_mesh_from_cluster()` — Uninstall Tanzu Service Mesh from Cluster
- `update_cluster()` — Update Cluster
- `update_global_namespace()` — Update Global Namespace
- `upgrade_tanzu_service_mesh_version_on_cluster()` — Install/Upgrade Tanzu Service Mesh Version on Cluster


---

## Identity Management

### `manage-engine-admanager-plus` v1.0.0 _(installed)_
_ManageEngine ADManager Plus_

ManageEngine ADManager Plus is an Active Directory (AD) management and reporting solution that allows IT administrators and technicians to manage AD objects easily and generate instant reports.

**5 operation(s)**:

- `add_users_to_group()` — Add Users To Group
- `disable_user()` — Disable Users
- `enable_user()` — Enable Users
- `remove_users_from_group()` — Remove Users From Group
- `unlock_user()` — Unlock Users


---

## Identity and Access Management

### `atlassian-iam` v1.0.0 _(installed)_
_Atlassian IAM_

Integrate with Atlassian's services to execute CRUD operations for employee lifecycle processes.

**4 operation(s)**:

- `create_user()` — Create User
- `deactivate_user()` — Deactivate User
- `get_users()` — Get Users
- `update_user()` — Update User


### `aws-access-analyzer` v1.1.0 _(installed)_
_AWS Access Analyzer_

AWS Access Analyzer helps you identify the resources in your organization and accounts, such as Amazon S3 buckets or IAM roles, shared with an external entity, enabling you to identify unintended access to your resources and data, which is a security risk.

**8 operation(s)**:

- `get_analyzed_resources()` — Details of an Analyzed Resources
- `get_analyzers()` — Get analyzer details
- `get_findings()` — Get Finding Details
- `list_analyzed_resources()` — List of Analyzed Resources
- `list_analyzers()` — List Analyzers
- `list_findings()` — List of Findings
- `start_resource_scan()` — Start Resource Scan
- `update_findings()` — Update Findings Status


### `azure-active-directory` v2.2.1 _(installed)_
_Microsoft Entra ID_

Microsoft Entra ID, formerly known as Azure Active Directory (Azure AD), is a cloud-based identity and access management (IAM) service that secures access to Microsoft cloud services and other applications for users. It manages user identities, enforces access policies, and supports single sign-on (SSO) to help organizations protect cloud and on-premises resources

**24 operation(s)**:

- `add_member()` — Add Member
- `add_user()` — Add User
- `delete_user()` — Delete User
- `disable_user()` — Disable User
- `enable_user()` — Enable User
- `get_group_details()` — Get Group Details
- `get_managers()` — Get Managers
- `get_people()` — Get People
- `get_registered_owners()` — List Registered Owners
- `get_registered_users()` — List Registered Users
- `get_user_details()` — Get User Details
- `get_user_membership()` — Get User Membership
- `list_devices()` — List Devices
- `list_direct_reports()` — List Direct Reports
- `list_group_members()` — List Group Members
- `list_groups()` — List Groups
- `list_sign_ins()` — List SignIns Events
- `list_user_owned_devices()` — List User Owned Devices
- `list_user_owned_objects()` — List User Owned Objects
- `list_users()` — List Users
- `remove_member()` — Remove Member
- `reset_password()` — Reset Password
- `rest_api_call()` — Generic REST API Call
- `revoke_sign_in_sessions()` — Revoke SignIn Sessions


### `azure-key-vault` v2.0.0 _(installed)_
_Azure Key Vault_

Azure Key Vault is a cloud based key management and security service that enables in securing cryptographic keys, password and other secret services used by cloud applications and services.This connector provides automated actions to list, get and delete vaults, keys, secrets and certificates

**18 operation(s)** (+2 hidden):

- `delete_certificate()` — Delete Certificate
- `delete_key()` — Delete Key
- `delete_key_vault()` — Delete Key Vault
- `delete_secret()` — Delete Secret
- `get_certificate()` — Get Certificate Details
- `get_certificate_policy()` — Get Certificate Policy
- `get_credentials()` — Get Credentials
- `get_key()` — Get Key Details
- `get_key_vault()` — Get Key Vault
- `get_secret()` — Get Secret Details
- `get_versions()` — Get Versions
- `list_certificate()` — Get All Certificates
- `list_key_vault()` — List Key Vaults
- `list_keys()` — Get All Keys
- `list_secret()` — Get All Secrets
- `update_vault_access_policy()` — Update Vault's Access Policies


### `beyondtrust-privileged-remote-access` v1.0.0 _(installed)_
_BeyondTrust Privileged Remote Access_

BeyondTrust Privileged Remote Access controls, manages, and audits privileged accounts and credentials. This enables just-in-time, zero trust access to on-premises and cloud resources by internal, external, and third-party users.

**18 operation(s)**:

- `checkin_or_checkout_private_key_or_password()` — Checkin or Checkout Credentials From Vault
- `create_account_in_vault()` — Create Account in Vault
- `create_user_in_vendor_group()` — Create User in Vendor Group
- `create_vendor_group()` — Create Vendor Group
- `delete_account_in_vault()` — Delete Account From Vault
- `delete_vendor_group()` — Delete Vendor Group
- `get_all_accounts_in_vault()` — Get Account List From Vault
- `get_all_group_policies()` — Get Group Policy List
- `get_all_users()` — Get User List
- `get_all_users_in_vendor_groups()` — Get User List in Vendor Group
- `get_all_vault_account_groups()` — Get Vault Account Group List
- `get_all_vault_account_policies()` — Get Vault Account Policy List
- `get_all_vault_endpoints()` — Get Vault Endpoint List
- `get_all_vendor_groups()` — Get Vendor Group List
- `get_user_in_vendor_groups()` — Get User Details in Vendor Group
- `get_vendor_group_by_id()` — Get Vendor Group Details
- `remove_user_from_vendor_groups()` — Remove User from Vendor Group
- `update_vendor_group()` — Update Vendor Group


### `cisco-ise` v2.1.1 _(installed)_
_Cisco ISE_

Cisco ISE connector provides actions like, list all active sessions, quarantine IP/Mac address, un-quarantine IP/Mac address etc.

**21 operation(s)**:

- `assign_policy()` — Assign ANC Policy
- `create_anc_policy()` — Create ANC Policy
- `disable_internal_user()` — Disable Internal User
- `enable_internal_user()` — Enable Internal User
- `end_session()` — End a Target MAC Address Session
- `get_anc_endpoint()` — Get ANC Endpoint
- `get_anc_policy()` — Get ANC Policy
- `get_guest_user_details()` — Get Guest User Details
- `get_internal_user_details()` — Get Internal User Details
- `get_ise_endpoint()` — Get Endpoints
- `list_active_sessions()` — List All Active Sessions
- `list_guest_users()` — List Guest Users
- `list_internal_users()` — List Internal Users
- `log_system_off()` — MAC Address Logout
- `quarantine_ip()` — EPS: Quarantine IP Address
- `quarantine_mac()` — EPS: Quarantine MAC Address
- `reinstate_guest_user()` — Reinstate Guest User
- `revoke_policy()` — Revoke ANC Policy
- `suspend_guest_user()` — Suspend Guest User
- `unquarantine_ip()` — EPS: Un-Quarantine IP Address
- `unquarantine_mac()` — EPS: Un-Quarantine MAC Address


### `crowdstrike-identity-platform` v1.0.0 _(installed)_
_CrowdStrike Identity Platform_

CrowdStrike Falcon® Identity Protection is a comprehensive identity security solution designed to protect organizations from modern identity-based threats across hybrid environments.

**10 operation(s)**:

- `execute_an_api_call()` — Execute an API Request
- `get_alert_details_by_ids()` — Get Alert Details by IDs
- `get_alert_ids()` — Get Alert IDs
- `get_alert_list()` — Get Alert List
- `get_incident_details_by_ids()` — Get Incident Details by IDs
- `get_incident_ids()` — Get Incident IDs
- `update_alert()` — Update Alert
- `update_alert_status()` — Update Alert Status
- `update_incident()` — Update Incident
- `update_incident_status()` — Update Incident Status


### `cyberark` v2.1.0 _(installed)_
_CyberArk_

CyberArk provide secure and manage password and other credentials for applications. This connector facilitates automated crud operations for Account Group, User, Safe and Credentials.

**31 operation(s)** (+7 hidden):

- `add_account_group()` — Add Account Group
- `add_safe()` — Add Safe
- `add_safe_member()` — Add Safe Member
- `add_user_to_group()` — Add User to Group
- `delete_account_group_members()` — Delete Member from Account Group
- `delete_safe()` — Delete Safe
- `delete_safe_member()` — Delete Safe Member
- `get_account()` — Get Accounts
- `get_account_group_members()` — Get Account Group Members
- `get_groups()` — Get Groups
- `get_recording_details()` — Get Recording Details by ID
- `get_recordings()` — Get Recordings
- `get_safe_account_groups()` — Get Safe Account Groups
- `get_safe_details()` — Get Safe Details
- `get_user_details()` — Get User Details
- `list_safe_members()` — List Safe Members
- `list_safes()` — List Safes
- `logged_on_user_details()` — Logged on User Details
- `play_recording()` — Get Data Stream of Recorded Session
- `reconcile_credentials()` — Reconcile Credentials
- `reset_user_password()` — Reset User Password
- `search_safe()` — Search Safe
- `update_safe()` — Update Safe
- `update_safe_member()` — Update Safe Member


### `cyolo` v1.0.0 _(installed)_
_Cyolo_

Cyolo helps enterprises provide their global workforce with convenient and secure access to applications, resources, workstations, servers, and files, regardless of location or device used.

**18 operation(s)**:

- `create_policy()` — Create Policy
- `delete_user_by_id_or_name()` — Delete User By ID Or Name
- `delete_user_from_policy()` — Delete User From Policy
- `get_policy_by_id_or_name()` — Get Policy By ID Or Name
- `get_user_by_id_or_name()` — Get User By ID Or Name
- `list_capabilities()` — Get Capabilities List
- `list_certificates()` — Get Certificates List
- `list_constraints()` — Get Constraints List
- `list_device_posture_profiles()` — Get Device Posture Profiles List
- `list_dynamic_groups()` — Get Dynamic Group List
- `list_mapping_categories()` — Get Mapping Categories List
- `list_mappings()` — Get Mappings List
- `list_policies()` — Get Policy List
- `list_simple_groups()` — Get Simple Group List
- `list_user_policies()` — Get User Policies
- `list_users()` — Get Users List
- `list_webhooks()` — Get Webhooks List
- `update_policy()` — Update Policy


### `fortinet-fortipam` v1.0.0 _(installed)_
_Fortinet FortiPAM_

FortiPAM provides privileged access management, control and monitoring of elevated accounts, processes and critical systems across the entire IT environment.

**5 operation(s)**:

- `delete_user()` — Delete User
- `execute_an_api_request()` — Execute an API Request
- `get_all_users()` — Get All Users
- `get_user_details()` — Get User Details
- `update_user()` — Update User


### `ibm-iam` v1.0.0 _(installed)_
_IBM IAM_

The IBM IAM Identity Service API is used to manage service IDs, API key identities, trusted profiles, account security settings and to create IAM access tokens for a user or service ID.

**21 operation(s)**:

- `create_a_service_id()` — Create A Service ID
- `create_an_api_key()` — Create An API Key
- `delete_api_key()` — Delete API Key
- `delete_service_id_and_associated_api_keys()` — Delete Service ID and Associated API keys
- `disable_the_api_key()` — Disable the API key
- `enable_the_api_key()` — Enable the API key
- `get_account_configurations()` — Get Account Configurations
- `get_activity_report_for_the_account()` — Get Activity Report
- `get_api_key_details()` — Get API Key Details
- `get_api_key_details_by_value()` — Get API Key Details By Value
- `get_api_keys()` — Get API Keys
- `list_service_id_by_account_id()` — List Service IDs
- `list_service_id_by_name()` — List Service IDs By Name
- `lock_api_key()` — Lock API Key
- `lock_service_id()` — Lock The Service ID
- `trigger_activity_report_for_the_account()` — Trigger Activity Report
- `unlock_api_key()` — UnLock API Key
- `unlock_service_id()` — Unlock The Service ID
- `update_account_configurations()` — Update Account Configurations
- `update_api_key()` — Update API Key
- `update_service_id()` — Update Service ID


### `manage-engine-key-manager-plus` v1.0.0 _(installed)_
_ManageEngine Key Manager Plus_

ManageEngine Key Manager Plus connector provides a 'key management' solution that helps you consolidate, control, manage, monitor, and audit the entire life cycle of SSH (Secure Shell) keys and SSL (Secure Sockets Layer) certificates.

**3 operation(s)**:

- `get_ssh_keys()` — Get SSH Keys
- `get_ssl_certificates()` — Get SSL Certificates
- `update_credentials()` — Update Credentials


### `okta` v1.1.0 _(installed)_
_OKTA_

Okta is a cloud-based identity and access management (IAM) platform that helps organizations securely manage and connect users to applications, devices, and data. It provides authentication, authorization, and user lifecycle management for employees, partners, and customers.

**11 operation(s)**:

- `activate_user()` — Activate User
- `create_user()` — Create User
- `deactivate_user()` — Deactivate User
- `execute_an_api_call()` — Execute an API Request
- `get_groups_details()` — Get Groups
- `get_list_of_users()` — Get List of Users
- `get_user_details()` — Get User
- `revoke_all_user_sessions()` — Revoke All User Sessions
- `set_password()` — Set Password
- `unlock_user()` — Unlock User
- `update_user()` — Update User


### `oracle-access-manager` v1.0.0 _(installed)_
_Oracle Access Manager_

Oracle Access Manager (OAM) is a robust identity and access management solution that provides secure authentication, single sign-on, and authorization control for web applications and resources within organizations. It ensures only authorized users can access specific data, enhancing security and user experience.

**4 operation(s)**:

- `change_user_status_by_user_id()` — Change User Status By User ID
- `delete_sessions()` — Delete Session
- `get_user_status_by_user_id()` — Get User Status by User ID
- `retrieve_sessions()` — Get Sessions List


### `pipl` v1.0.0 _(installed)_

PIPL provides a way to get work & social contact information of people.

**1 operation(s)**:

- `get_user_details()` — Get User Details


### `sailpoint-identityiq` v1.0.1 _(installed)_
_SailPoint IdentityIQ_

SailPoint IdentityIQ provides enterprise identity governance solutions with on-premises and cloud-based identity management software for the most complex challenges

**16 operation(s)**:

- `check_potential_policy_violations()` — Check Potential Policy Violations
- `get_account_details()` — Get Account Details
- `get_accounts()` — Get Accounts
- `get_application_details()` — Get Application Details
- `get_entitlement_details()` — Get Entitlement Details
- `get_entitlements()` — Get Entitlements
- `get_launched_workflows()` — Get Launched Workflows
- `get_policy_violations()` — Get Policy Violations
- `get_role_details()` — Get Role Details
- `get_roles()` — Get Roles
- `get_task_result_details()` — Get Task Result Details
- `get_task_results()` — Get Task Results
- `get_user_details()` — Get User Details
- `get_users()` — Get Users
- `get_workflow_status()` — Get Workflow Status
- `get_workflows()` — Get Workflows


### `sailpoint-identitynow` v1.0.0 _(installed)_
_SailPoint IdentityNow_

SailPoint IdentityNow that allows you to easily control user access to all systems and applications, enhance audit response and increase your operational efficiency. This connector facilitates automated operation for identity management.

**11 operation(s)**:

_containment_
- `disable_account(id: text, externalVerificationId: text, [forceProvisioning: checkbox])` — Disable Account
- `enable_account(id: text, externalVerificationId: text, [forceProvisioning: checkbox])` — Enable Account
- `grant_request(requestedFor: text, requestedItems: json, [clientMetadata: json])` — Grant Access
- `reset_password(userName: text, sourceName: text, identityId: text, password: password, publicKeyId: text, accountId: text, sourceId: text)` — Reset Password
- `revoke_request(requestedFor: text, [requestedItems: json], clientMetadata: json)` — Revoke Access
- `unlock_account(id: text, externalVerificationId: text, [unlockIDNAccount: checkbox], [forceProvisioning: checkbox])` — Unlock Account

_investigation_
- `get_account_activities([account_type: text], [requested-for: text], [requested-by: text], [regarding-identity: text], [sorters: select], [limit: integer], [offset: text])` — Get Account Activities
- `get_account_activity(id: text)` — Get Account Activity
- `get_account_details(id: text)` — Get Account Details
- `get_accounts([filter: text], [detailLevel: select], [limit: integer], [offset: integer])` — Get Accounts
- `get_password_info(userName: text, sourceName: text)` — Get Password Info


### `sap-cloud-identity-directory-service` v1.0.0 _(installed)_
_SAP Cloud Identity Directory Service_

The identity directory provides a System for Cross-domain Identity Management (SCIM) 2.0 REST API for managing resources (users, groups and custom schemas). Consumers of this REST API should be familiar with System for Cross-domain Identity Management Protocol before managing their own resources.

**8 operation(s)**:

- `create_group()` — Create Group
- `create_user()` — Create User
- `delete_group()` — Delete Group
- `delete_user()` — Delete User
- `get_group_list()` — Get Group List
- `get_user_list()` — Get User List
- `update_group_members()` — Update Group Members
- `update_user_details()` — Update User Details


### `silverfort` v1.0.0 _(installed)_
_Silverfort_

Silverfort delivers adaptive authentication across all corporate networks and cloud environments from a unified platform. This integration is used to gather and update risk associated with a user or resource from Silverfort.

**4 operation(s)**:

- `get_resource_risk()` — Get Resource Risk
- `get_user_risk()` — Get User Risk
- `update_resource_risk()` — Update Resource Risk
- `update_user_risk()` — Update User Risk


### `thycotic-secret-server` v2.0.0 _(installed)_
_Delinea Secret Server_

Delinea Secret Server is an external vault that protects your privileged accounts with enterprise-grade privileged access management (PAM) solutions available both on-premise or in the cloud.

**3 operation(s)** (+3 hidden):

- `get_credential()` — Get Credential
- `get_credentials()` — Get Credentials
- `get_credentials_details()` — Get Credentials Details


---

## Information

### `mitre-attack` v2.0.2 _(installed, ingestion)_
_MITRE ATT&CK_

The MITRE ATT&CK knowledge base is used as a foundation for the development of specific threat models and methodologies. Connector helps to replicate knowledge base of adversary tactics and techniques based on real-world observations

**2 operation(s)**:

- `get_mitre_data(modules: multiselect, [force_ingestion: checkbox])` — Get MITRE Data
- `get_mitre_data_sample()` — Get MITRE Sample Data


### `shodan` v1.0.0 _(installed)_
_Shodan_

Investigating actions like search ip and search domain to get information from the shodan search engine.

**2 operation(s)**:

_investigation_
- `search_domain(domain: text)` — Search Domain
- `search_ip(ip: text)` — Search IP


### `slacalculator` v2.1.0 _(installed)_
_SLA Calculator_

Calculates SLA due dates based on local time and business hours. Requires the SLA Management solution pack to support playbooks and module updates.

**2 operation(s)**:

_miscellaneous_
- `calculateSLA(recordCreateTime: datetime, slaTime: decimal)` — Calculate SLA
- `calculate_elapsed_time(start_datetime: datetime, end_datetime: datetime, [sla_time: decimal])` — Calculate Elapsed SLA Time


---

## Insider Threat

### `insider-security-ueba` v1.0.0 _(installed)_
_InsiderSecurity UEBA_

InsiderSecurity UEBA (User and Entity Behaviour Analytics) detects malicious user activity early in your on-premise or cloud infrastructure, allowing you to take action early and avoid data loss.

**3 operation(s)**:

- `get_alerts_by_id()` — Get Alerts by ID
- `search_alerts()` — Search Alerts
- `search_data_enrichment()` — Search Data Enrichment


---

## Investigation

### `fortinet-forticnp` v2.0.0 _(installed)_
_Fortinet FortiCNP_

Fortinet FortiCNP integrates with APIs provided by cloud vendors including AWS, Azure, and Google Cloud Platform to monitor and track all security components, including configurations, user activity, and traffic flow logs. This Connector automated operations such as retrieving the get alerts from Fortinet FortiCNP, etc

**4 operation(s)**:

- `get_finding_list()` — Get Finding List
- `get_resource_details()` — Get Resource Details
- `get_resource_list()` — Get Resource List
- `get_resource_map()` — Get Resource Map


---

## Logging

### `aws-cloudtrail` v1.1.0 _(installed)_
_AWS CloudTrail_

AWS CloudTrail enables auditing, security monitoring, and operational monitoring by logging your AWS account activity

**9 operation(s)**:

- `add_tags()` — Add Tags
- `create_trail()` — Create Trail
- `delete_trail()` — Delete Trail
- `get_trail_status()` — Get Trail Status
- `list_trails()` — List Trails
- `lookup_events()` — Lookup Events
- `start_logging()` — Start Logging
- `stop_logging()` — Stop Logging
- `update_trail()` — Update Trail


### `coralogix` v1.0.0 _(installed)_
_Coralogix_

Coralogix is a modern log analytics platform that provides real-time insights and monitoring for your log data. It offers advanced indexing, querying, and visualization capabilities, enabling users to efficiently manage and analyze log data from various sources. With features such as anomaly detection, alerting, and machine learning-powered insights, Coralogix helps organizations enhance their observability, troubleshoot issues faster, and improve overall system performance and security.

**1 operation(s)**:

- `search_archived_logs()` — Search Archived Logs


### `google-cloud-logging` v1.0.0 _(installed)_
_Google Cloud Logging_

Cloud Logging is a fully managed service that allows you to store, search, analyze, monitor, and alert on logging data and events from Google Cloud.

**3 operation(s)**:

- `get_exclusions_list()` — Get Exclusions List
- `get_log_entries_list()` — Get Log Entries List
- `get_sinks_list()` — Get Sinks List


### `syslog` v1.3.0 _(installed)_
_Syslog_

FortiSOAR Syslog Connector

**4 operation(s)**:

- `parse()` — Parse Message
- `restart()` — Restart Listener
- `start()` — Start Listener
- `stop()` — Stop Listener


---

## ML Service

### `anything-llm` v1.0.0 _(installed)_
_Anything LLM_

This connector is providing automation actions for Anything LLM that supports using Retrieval Augmented Generation (RAG) with an LLM and user documents embedded in a vector DB. The LLM and vector DB can be fully local for maximum data privacy or configured to use cloud-based services such as OpenAI. A variety of LLMs and vector DBs are supported. Anything LLM itself can be installed on customer infrastructure or accessed as a cloud service.

**15 operation(s)**:

- `add_workspace_embedding()` — Add Workspace Embedding
- `create_document_folder()` — Create Folder in Documents
- `create_workspace()` — Create Workspace
- `delete_document()` — Delete Document
- `delete_workspace_embedding()` — Remove Workspace Embedding
- `get_document()` — Get Document by Name
- `get_documents()` — Get Documents List
- `get_workspace()` — Get Workspace by Slug
- `get_workspace_list()` — Get Workspace List
- `move_document()` — Move Document
- `update_workspace_settings()` — Update Workspace Settings
- `upload_document()` — Upload Document
- `upload_document_link()` — Upload Document Link
- `upload_document_text()` — Upload Document Text
- `workspace_chat()` — Workspace Chat


### `aws-sagemaker` v1.1.0 _(installed)_
_AWS SageMaker_

AWS SageMaker helps data scientists and developers to prepare, build, train, and deploy high-quality machine learning (ML) models quickly by bringing together a broad set of capabilities purpose-built for ML.

**4 operation(s)**:

- `get_actions()` — Get Actions
- `get_algorithms()` — Get Algorithms
- `get_apps()` — Get Applications
- `get_artifacts()` — Get Artifacts


### `cloudera-edh` v1.0.0 _(installed)_
_Cloudera EDH_

Cloudera provides a scalable, flexible, integrated platform that makes it easy to manage rapidly increasing volumes and varieties of data in your enterprise.This connector allows you do operations related to database.

**4 operation(s)**:

- `list_columns()` — Get Columns
- `list_tables()` — Get Table List
- `run_query()` — Run Query
- `select_query()` — Execute Select Query


---

## Machine Learning

### `fortisoar-ml-engine` v1.2.3 _(installed, system)_
_FortiSOAR ML Engine_

Leverage Machine Learning as your bot assistant in identifying record similarity, classification etc.

**7 operation(s)** (+4 hidden):

_investigation_
- `predict(records: text, [module: text])` — Predict
- `similar(records: text)` — Fetch Similar Record(s)
- `train()` — Train


### `phishing-classifier` v1.1.0 _(installed, system)_
_Phishing Classifier_

Classify emails into phishing and non-phishing using machine learning

**5 operation(s)** (+2 hidden):

_investigation_
- `get_training_results()` — Get Training Results
- `predict(record: text, [module: text])` — Predict
- `train()` — Train


---

## Malware Analysis

### `anyrun` v2.0.0 _(installed)_
_ANY.RUN Cloud Sandbox_

ANY.RUN empowers SOC teams to cut MTTD/MTTR with fast verdicts using the Interactive Sandbox. With the ANY.RUN Cloud Sandbox connector for FortiSOAR, your team achieves: <br/> 
- Faster triage: Submit files/URLs for instant analysis across Windows, Linux, Android. Get answers in seconds to catch threats that beat standard defenses and increase the detection rate by up to 36%. <br/>
- Streamlined workflows: Retrieve reports (JSON, HTML, IOCs) directly in FortiSOAR without tool-switching. Act without delays to stop attacks before they have a chance to hurt your infrastructure.

**8 operation(s)**:

- `delete_analysis()` — Delete Sandbox Analysis
- `detonate_file()` — Analyze File in Sandbox
- `detonate_url()` — Analyze URL in Sandbox
- `get_analysis_verdict()` — Retrieve Analysis Verdict
- `get_report()` — Retrieve Analysis Report
- `get_report_attachments()` — Retrieve Report Attachments
- `get_user_history()` — Retrieve Analysis History
- `get_user_limits()` — Retrieve Account Usage Limits


### `checkpoint-sandblast-appliance` v1.0.0 _(installed)_
_Check Point Sandblast Appliance_

Checkpoint Sandblast Appliance connector submits file samples for sandboxing and fetches scan verdicts and reports

**3 operation(s)**:

- `download()` — Download Report
- `query()` — Get File Reputation
- `upload()` — Submit File


### `checkpoint-sandblast-cloud` v1.0.0 _(installed)_
_Check Point Sandblast Cloud_

Check Point Sandblast Threat Emulation Cloud connector submits file samples for sandboxing and fetches reputation verdicts

**4 operation(s)**:

- `download()` — Download Report
- `query()` — Get File Reputation
- `quota()` — Get Sandblast Cloud Quota
- `upload()` — Submit File


### `cisco-threatgrid` v1.3.0 _(installed)_
_Cisco Threat Grid_

Cisco Threat Grid Connector is a malware analysis and threat intelligence platform, this connector allows you to submit the sample for analysis and fetch reports.

**13 operation(s)** (+3 hidden):

- `download_report()` — Download Report
- `get_IOC_json()` — Get IOCs
- `get_all_reports()` — Get All Reports
- `get_curated_feeds()` — Search Report by Feeds
- `get_json_report()` — Get JSON Report
- `get_rate_limit_info()` — Get Rate Limit Information
- `get_status()` — Get Status
- `get_summary()` — Get Summary
- `search_report()` — Search Report
- `submit_sample()` — Submit Sample


### `crowd-strike-falcon-sandbox` v2.1.0 _(installed)_
_CrowdStrike Falcon Sandbox_

Falcon Sandbox can be used submit files/URLs for analysis, pull report data, but also perform advanced search queries

**14 operation(s)** (+1 hidden):

- `download_report()` — Download Report
- `get_analysis_overview()` — Get Analysis Overview
- `get_analysis_summary()` — Get Analysis Summary
- `get_environments()` — Get Environments
- `get_report_summary()` — Get Report Summary
- `get_scanners_list()` — Get Scanners
- `get_submission_state()` — Get Submission State
- `quick_scan_file()` — Quick Scan File
- `quick_scan_url()` — Quick Scan URL
- `search_query()` — Search Query
- `submit_file_to_sandbox()` — Submit File To Sandbox
- `submit_url_hash_to_sandbox()` — Submit URL For Hash
- `submit_url_to_sandbox()` — Submit URL To Sandbox


### `crowdstrike-falcon-x` v1.1.1 _(installed)_
_CrowdStrike Falcon X_

FALCON X Automatically investigate incidents and accelerate alert triage and response. This connector facilitates the automated operations to Submit Files , URLs and to fetch the reports.

**8 operation(s)**:

- `get_analysis_status()` — Get Analysis Status
- `get_full_report()` — Get Full Report
- `get_report_summary()` — Get Report Summary
- `search_reports()` — Search Reports
- `search_submission_id()` — Search Submission ID
- `submit_uploaded_file()` — Submit Uploaded File
- `submit_url()` — Submit URL
- `upload_file()` — Upload File


### `cuckoo` v1.1.0 _(installed)_
_Cuckoo_

Cuckoo sandbox is an open source software for automating analysis of suspicious files. To do so it makes use of custom components that monitor the behavior of the malicious processes while running in an isolated environment.

**3 operation(s)**:

- `get_report()` — Get Report
- `submit_file()` — Submit File
- `submit_url()` — Submit URL


### `ddan` v1.0.2 _(installed)_
_Trend Micro DDAN_

Trend Micro-Deep Discovery Analyzer for Network

**3 operation(s)**:

- `get_open_ioc_by_sha1()` — Get OpenIOC of Submitted Sample using SHA1
- `get_report_by_sha1()` — Get Sample Report using SHA1
- `submit_sample()` — Submit Sample to Trend Micro DDAN


### `fireeye-ax` v1.0.1 _(installed)_
_FireEye AX_

FireEye AX connector perform automated operations such as retrieving a list of all guest image profiles and applications details, submitting files or URLs for analysis and retrieving data for artifacts.

**14 operation(s)**:

- `add_custom_feeds()` — Add or Update Custom Feeds
- `add_yara_rule()` — Add YARA Rule
- `delete_custom_feeds()` — Delete Custom Feeds
- `delete_yara_rule()` — Delete YARA Rule
- `download_custom_feeds()` — Download a Custom IOC File Request
- `get_alert_details()` — Get Alert Details
- `get_alerts()` — Get Alerts
- `get_artifacts_metadata_by_uuid()` — Get Artifacts Metadata By UUID
- `get_config()` — Get Config
- `get_submission_result()` — Get Submission Result
- `get_submission_status()` — Get Submission Status
- `list_custom_feeds()` — List Custom Feeds
- `submit_file()` — Submit File
- `submit_url()` — Submit URL


### `fireeye-detection-on-demand` v1.0.1 _(installed)_
_FireEye Detection On Demand_

FireEye Detection On Demand is a threat detection service that uncovers harmful objects in the cloud. It delivers flexible file and content scanning capabilities to identify file-borne threats in your cloud, SOC, SIEM or files uploaded to web applications. This connector facilitates the automated operations related to submit files / urls , reports, artifacts.

**6 operation(s)**:

- `get_artifacts()` — Get Artifacts
- `get_hashes()` — Get File Reputation
- `get_report_url()` — Get Report URL
- `get_reports()` — Get Report
- `submit_file()` — Submit File
- `submit_urls()` — Submit URLs


### `fortinet-fortiai` v1.3.0 _(installed)_
_Fortinet FortiNDR_

The FortiNDR is a leading-edge product which utilizes machine learning technology for malware detection, intrusion detection and network anomalies.. This connector provides action to submits file samples for analysis and potentially fetches scan verdicts

**3 operation(s)**:

- `get_events()` — Get Events
- `get_file_verdict_results()` — Get File Verdict Result
- `submit_file()` — Submit File


### `fortinet-fortisandbox` v2.1.0 _(installed)_
_Fortinet FortiSandbox_

FortiSandbox utilizes advanced detection, dynamic antivirus scanning, and threat scanning technology to detect viruses and APTs. FortiSandbox executes suspicious files in the VM host module to determine if the file is High, Medium, or Low Risk based on the behaviour observed in the VM sandbox module. Implemented actions like submit file, get scan stats, get file verdict, get job behaviour and get pdf report etc.

**17 operation(s)**:

- `download_hashes_url_from_mwpkg()` — List Filehash or URL From Malware Package or URL Package
- `get_avrescan()` — Get AV-Rescan Result
- `get_file_rating()` — Get File Rating
- `get_file_verdict()` — Get File Verdict
- `get_installed_vm()` — Get All Installed VM
- `get_job_behaviour()` — Get Job Behaviour
- `get_pdf_report()` — Get PDF Report
- `get_scan_result_job()` — Get Job Verdict Detail
- `get_scan_stats()` — Get Scan Stats
- `get_submission_job_list()` — Get Submission Job List
- `get_system_status()` — Get System Status
- `get_url_rating()` — Get URL Rating
- `handle_allow_block_list()` — Update Allow or Block List
- `handle_white_black_list()` — Update White or Black List
- `mark_sample_fp_fn()` — Toggle FPN State
- `submit_file()` — Submit File
- `submit_urlfile()` — Submit URL


### `hatching-triage` v1.0.0 _(installed)_
_Hatching Triage_

A state-of-the-art malware analysis sandbox, with all the features you need. High-volume sample submission in a customizable environment with detections and configuration extraction for many malware families.

**12 operation(s)**:

- `create_profile()` — Create Profile
- `delete_profile()` — Delete Profile
- `get_profiles()` — Get Profiles
- `get_report_triage()` — Get Triage Report
- `get_sample()` — Get Sample by ID
- `get_sample_summary()` — Get Sample Summary
- `get_static_report()` — Get Static Report
- `query_samples()` — Query Samples
- `search_by_query()` — Search By Query
- `set_sample_profile()` — Set Sample Profile
- `submit_sample()` — Submit Sample
- `update_profile()` — Update Profile


### `hybrid-analysis` v2.1.0 _(installed)_
_Hybrid Analysis_

Hybrid Analysis provides a malware analysis service that allows users to automate the analysis of files and URLs for potential threats. This connector facilitates automated operations such as retrieving analysis reports, environment details, submitting files, submitting URLs, etc.

**13 operation(s)**:

- `conditional_search()` — Advanced Search
- `get_api_quota()` — Get API Quota
- `get_environment()` — Get Environment
- `get_feed()` — Get Latest Analysis Reports
- `get_report()` — Get Analysis Report
- `get_sample_dropped_file()` — Get Files Dropped by Sample
- `get_sample_screenshots()` — Get Sample Screenshot
- `get_submitted_sample_state()` — Get Submission State
- `hashes_search()` — Get Analysis Report for Hashcode
- `quick_scan_by_id()` — Quick Scan by ID
- `submit_file()` — Submit File
- `submit_url()` — Submit URL
- `url_quick_scan()` — Quick Scan URL


### `intezer-analyze` v1.0.0 _(installed)_
_Intezer Analyze_

Intezer Analyze enables you to perform malware analysis of suspicious files and a variety of automated investigation process operations. This connector facilitates automated operations like Submit File, Submit Hash, Get Analysis, Generate Vaccine

**6 operation(s)**:

- `analyse_file()` — Submit File
- `analyse_hash()` — Submit Hash
- `generate_vaccine()` — Generate Vaccine
- `get_analysis()` — Get Analysis
- `get_sub_analysis()` — Get Sub Analysis
- `hash_reputation()` — Get Hash Reputation


### `joe-sandbox-cloud` v1.2.0 _(installed)_
_Joe Sandbox Cloud_

Joe sandbox is cloud base malware analysis service, It is a multi technology platform which uses instrumentation, simulation, hardware virtualization, hybrid and graph - static and dynamic analysis

**8 operation(s)**:

- `get_account_info()` — Get Account Information
- `get_all_analysed_sample_details()` — Get All Analysed Sample Details
- `get_all_system_information()` — Get All System Information
- `get_report()` — Get Report
- `get_submitted_sample_state()` — Get Submission Status
- `search_report()` — Search Report
- `submit_file()` — Submit File
- `submit_url()` — Submit URL


### `koodous` v1.0.0 _(installed)_
_Koodous_

Koodous is a collaborative platform that combines the power of online analysis tools with social interactions between the analysts over a vast APKs repository.

**3 operation(s)**:

- `get_report()` — Get Report
- `search_apk()` — Search APK
- `upload_apk()` — Submit APK


### `lastline` v1.0.0 _(installed)_
_Lastline_

LastLine connector

**5 operation(s)**:

- `check_filehash_is_blocked()` — Check Filehash is Blocked
- `get_report()` — Get Report
- `search_report_using_filehash()` — Search Report using Filehash
- `submit_file()` — Submit File
- `submit_url()` — Submit URL


### `malshare` v1.0.0 _(installed)_
_MalShare_

A free Malware repository providing researchers access to samples, malicous feeds, and Yara results.

**5 operation(s)**:

- `get_file_details()` — Get File Information
- `list_hash()` — List Hash
- `list_url()` — List URL
- `search_query()` — Search Query
- `submit_sample()` — Submit Sample


### `malwr` v1.0.0 _(installed)_
_Malwr_

Malwr Connector

**2 operation(s)**:

- `get_report()` — Get Report
- `submit_sample()` — Submit File


### `metadefender` v1.2.0 _(installed)_
_Metadefender Cloud_

Metadefender Cloud provides file, sandbox and IP reputation

**7 operation(s)**:

- `get_hash_lookup_with_sandbox()` — Get Hash Lookup With Sandbox
- `get_hash_reputation()` — Get Filehash Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_sandbox_lookup()` — Get Sandbox Lookup
- `get_scan_file_result()` — Get Scan File Result
- `get_scan_with_sandbox()` — Get Scan With Sandbox
- `submit_file()` — Submit File


### `opswat-metadefender-core` v1.0.0 _(installed)_
_OPSWAT MetaDefender Core_

OPSWAT MetaDefender Core prevents malicious file uploads on web applications that bypass sandboxes and other detection-based security solutions. This connector facilitates operations to Submit File, Get Hashcode Reputation, Download Sanitized Files.

**3 operation(s)**:

- `download_sanitized_files()` — Download Sanitized Files
- `get_hashcode_reputation()` — Get Hashcode Reputation
- `submit_file()` — Submit File


### `reversinglabs-a1000` v1.0.0 _(installed)_
_ReversingLabsA1000_

ReversingLabs A1000 Malware Analysis

**3 operation(s)**:

- `get_report()` — Get Report using File Hash
- `re_analyze_sample()` — Re-analyze Sample using File Hash
- `upload_sample()` — Upload Sample


### `secondwrite` v1.0.1 _(installed)_
_SecondWrite_

SecondWrite Connector

**3 operation(s)**:

- `get_report()` — Get Report
- `submit_file()` — Submit File
- `submit_url()` — Submit URL


### `symantec-cas` v1.0.0 _(installed)_
_Symantec CAS_

Symantec CAS(Content Analysis Service) provides protection against advanced threats through file reputation, multiple antimalware techniques and sophisticated sandbox detonation

**8 operation(s)**:

- `create_task()` — Create Task
- `detonate_file()` — Detonate File
- `get_report()` — Get Report
- `get_risk_score()` — Get Risk Score
- `get_sample_task()` — Get Sample's Task
- `get_task_statistics()` — Get Task Statistics
- `submit_file()` — Submit Sample
- `submit_url()` — Submit URL


### `vmray` v1.1.0 _(installed)_
_VMRAY_

VMRay is a malware analysis platform that uses dynamic analysis to detect and analyze advanced threats by executing suspicious files in a controlled environment and monitoring their behavior.

**23 operation(s)**:

- `add_tag()` — Add Tag
- `delete_job()` — Delete Job
- `delete_submission()` — Delete Submission
- `delete_tag()` — Delete Tag
- `get_analysis()` — Get Analysis
- `get_iocs()` — Get IOCs
- `get_job()` — Get Job Analysis
- `get_md_analysis()` — Get Metadefender Analysis
- `get_md_job()` — Get Metadefender Jobs
- `get_prescript()` — Get Prescripts
- `get_reputation_job()` — Get Reputation Jobs
- `get_reputation_lookup()` — Get Reputation Lookups
- `get_samples()` — Get Samples
- `get_screenshots()` — Get Screenshots
- `get_submission()` — Get Submissions
- `get_system_info()` — Get System Information
- `get_tags()` — Get Tags
- `get_threat_indicators()` — Get Threat Indicators
- `get_vt_analysis()` — Get VirusTotal Analysis
- `get_vt_job()` — Get VirusTotal Jobs
- `submit_cyops_attachment()` — Submit Sample
- `submit_sample_by_url()` — Submit Sample Url
- `submit_url()` — Submit URL


---

## Message Queueing Service

### `aws-sqs` v1.0.1 _(installed)_
_AWS SQS_

Amazon Simple Queue Service (SQS) is a fully managed message queuing service. Connector actions allows to scale and decouple microservices for distributed systems and serverless applications.

**16 operation(s)**:

- `add_permission()` — Add Permission to Queue
- `add_tag_queue()` — Add Tag to Queue
- `create_queue()` — Create Queue
- `delete_message()` — Delete Message
- `delete_queue()` — Delete Queue
- `get_queue_attributes()` — Get Queue Attributes
- `get_queue_url()` — Get Queue URL
- `list_dead_letter_source_queues()` — Get Dead-Letter Queues
- `list_queue_tags()` — Get Queue Tags
- `list_queues()` — Get List of Queues
- `purge_queue()` — Purge Queue
- `receive_message()` — Receive Message
- `remove_permission()` — Remove Permission
- `send_message()` — Send Message
- `untag_queue()` — Remove Tag from Queue
- `update_queue()` — Update Queue


---

## Miscellaneous

### `openai` v3.1.0 _(installed)_
_OpenAI_

This integration supports interacting with OpenAI's powerful language model, ChatGPT from FortiSOAR workflows

**42 operation(s)** (+1 hidden):

_miscellaneous_
- `cancel_run(thread_id: text, run_id: text)` — Cancel Run
- `cancel_vector_store_file_batch(vector_store_id: text, batch_id: text)` — Cancel Vector Store File Batch
- `chat_completions(message: text, [model: text], [temperature: text], [top_p: text], [max_tokens: integer], [timeout: integer], [other_fields: json])` — Ask a Question
- `chat_conversation(messages: json, [model: text], [temperature: text], [top_p: text], [max_tokens: integer], [timeout: integer], [other_fields: json])` — Converse With OpenAI
- `count_tokens(input_text: text, model: text)` — Get Token Count
- `create_assistant(model: text, [name: text], [description: text], [instructions: textarea], [tools: json], [tool_resources: json], [temperature: decimal], [top_p: decimal], [metadata: json])` — Create Assistant
- `create_run(thread_id: text, assistant_id: text, [model: text], [instructions: textarea], [additional_instructions: textarea], [additional_messages: json], [tools: json], [temperature: decimal], [top_p: decimal], [metadata: json], [max_prompt_tokens: integer], [other_fields: json])` — Create Run
- `create_speech(model: select, input: textarea, voice: select, file_path: text, [response_format: select], [speed: decimal])` — Create Speech
- `create_thread([messages: json], [tool_resources: json], [metadata: json])` — Create Thread
- `create_thread_and_run(assistant_id: text, thread: json, [model: text], [instructions: textarea], [tools: json], [tool_resources: json], [metadata: json], [temperature: decimal], [top_p: decimal], [max_prompt_tokens: integer], [other_fields: json])` — Create Thread and Run
- `create_thread_message(thread_id: text, role: select, content: json, [attachments: json], [metadata: json])` — Create Thread Message
- `create_transcription(model: text, file: file, [language: text], [prompt: text], [temperature: decimal], [timestamp_granularities: multiselect])` — Create Transcription
- `create_translation(model: text, file: file, [prompt: text], [temperature: decimal])` — Create Translation
- `create_vector_store(name: text, [file_ids: text], [expires_after: json], [metadata: json])` — Create Vector Store
- `create_vector_store_file(vector_store_id: text, file_id: text)` — Create Vector Store File
- `create_vector_store_file_batch(vector_store_id: text, file_ids: text)` — Create Vector Store File Batch
- `delete_assistant(assistant_id: text)` — Delete Assistant
- `delete_files(file_ids: text)` — Delete File
- `delete_thread(thread_id: text)` — Delete Thread
- `delete_thread_message(thread_id: text, message_id: text)` — Delete Thread Message
- `get_assistant(assistant_id: text)` — Get Assistant Details
- `get_file(file_id: text)` — Get File Details
- `get_run(thread_id: text, run_id: text)` — Get Run Details
- `get_run_step(thread_id: text, run_id: text, step_id: text)` — Get Run Step Details
- `get_thread(thread_id: text)` — Get Thread Details
- `get_thread_message(thread_id: text, message_id: text)` — Get Thread Message Details
- `get_usage(date: datetime)` — Get Tokens Usage
- `get_vector_store(vector_store_id: text)` — Get Vector Store Details
- `get_vector_store_file_batch(vector_store_id: text, batch_id: text)` — Get Vector Store File Batch
- `list_assistants([order: select], [after: text], [before: text], [limit: integer])` — List Assistants
- `list_files([purpose: select])` — List Files
- `list_models()` — List Available Models
- `list_run_steps(thread_id: text, run_id: text, [order: select], [after: text], [before: text], [limit: integer])` — List Run Steps
- `list_runs(thread_id: text, [order: select], [after: text], [before: text], [limit: integer])` — List Runs
- `list_thread_messages(thread_id: text, [run_id: text], [order: select], [after: text], [before: text], [limit: integer])` — List Thread Messages
- `submit_tool_outputs_to_run(thread_id: text, run_id: text, tool_outputs: json)` — Submit Tool Outputs To Run
- `update_assistant(assistant_id: text, [model: text], [name: text], [description: text], [instructions: textarea], [tools: json], [tool_resources: json], [temperature: text], [top_p: text], [metadata: json])` — Update Assistant
- `update_run(thread_id: text, run_id: text, [metadata: json])` — Update Run
- `update_thread(thread_id: text, [tool_resources: json], [metadata: json])` — Update Thread
- `update_thread_message(thread_id: text, message_id: text, [metadata: json])` — Update Thread Message
- `upload_file(file: file, purpose: select)` — Upload File


---

## Monitoring

### `aws-cloudwatch-log` v1.0.0 _(installed)_
_AWS CloudWatch Log_

AWS CloudWatch Log helps you monitor, store, and access your system, application, and custom log files. This connector facilitates the automate operations related to the log group, log streams and metrics.

**13 operation(s)**:

- `create_log_group()` — Create Log Group
- `create_log_stream()` — Create Log Stream
- `delete_log_group()` — Delete Log Group
- `delete_log_stream()` — Delete Log Stream
- `get_list_log_groups()` — Get Log Groups List
- `get_list_log_streams()` — Get Log Streams List
- `get_log_events()` — Get Log Events
- `get_log_insight_query_result()` — Get Log Insight Query Result
- `revert_log_retention_policy()` — Revert Log Retention Policy
- `run_log_insight_query()` — Run Log Insight Query
- `stop_log_insight_query()` — Stop Log Insight Query
- `update_log_retention_policy()` — Update Log Retention Policy
- `upload_log_event()` — Upload Log Event


### `fortinet-fortimonitor` v1.0.1 _(installed)_
_Fortinet FortiMonitor_

FortiMonitor is a cloud-based monitoring SAAS service with full-stack visibility of hybrid IT infrastructure.

**11 operation(s)**:

- `acknowledge_incident()` — Acknowledge Incident
- `create_incident_logs()` — Create Incident Log
- `escalate_incident()` — Escalate Incident
- `get_contact()` — Get Contacts
- `get_incident_logs()` — Get Incident Logs
- `get_incidents()` — Get Incidents
- `get_maintenance_schedule()` — Get Maintenance Schedule
- `get_rotating_contact()` — Get Rotating Contact
- `get_servers()` — Get Servers
- `get_users()` — Get All Customer Users
- `send_broadcast()` — Send Broadcast Message


### `prtg` v1.1.0 _(installed)_
_PRTG_

PRTG is a powerful monitoring solution that analyzes your entire IT infrastructure, monitors your network, performance, hardware, cloud, databases, applications etc.

**8 operation(s)**:

- `acknowledge_alarm()` — Acknowledge Alarm
- `delete_object()` — Delete Object
- `get_sensor_status()` — Get Sensor Status
- `list_object_detail()` — List Object Details
- `pause_sensor()` — Pause Sensor
- `resume_sensor()` — Resume Sensor
- `run_auto_discovery()` — Run Auto Discovery
- `scan_sensor()` — Scan Sensor


### `qualys-fim` v1.0.0 _(installed)_
_Qualys File Integrity Monitoring(FIM)_

Qualys File Integrity Monitoring (FIM) is a highly scalable cloud app that enables a simple way to monitor critical files, directories, and registry paths for changes in real time, and helps adhere to compliance mandates such as PCI-DSS, FedRAMP, HIPAA, GDPR and others. This connector facilitates automated interactions with a Qualys File Integrity Monitoring (FIM) server using FortiSOAR™ playbooks.

**7 operation(s)**:

- `approve_incident ()` — Approve Incident
- `create_manual_incident ()` — Create Manual Incident
- `fetch_incident_events()` — Fetch Incident Events
- `get_assets()` — Get Assets
- `get_event_details()` — Get Event Details
- `get_events()` — Get Events
- `get_incidents()` — Get Incidents


---

## Network Protection

### `seclytics-augur-pxdr` v1.1.0 _(installed)_
_Seclytics Augur pXDR_

Seclytics Augur pXDR: This FortiSOAR connector interacts with Seclytics Augur pXDR API. It can perform IOC lookup for threat context enrichment for threat investigation. It can also download SecLytics' unique predictive threat intel for automated network security response.

**4 operation(s)**:

- `download_predictions()` — Download Predictions
- `query_domain()` — Get Domain Reputation
- `query_file()` — Get File Reputation
- `query_host()` — Get Host Reputation


---

## Network Security

### `akamai` v1.0.0 _(installed)_
_Akamai Prolexic_

Akamai is an American content delivery network (CDN), cybersecurity, and cloud service company, providing web and Internet security services.

**4 operation(s)**:

- `get_an_attack_report()` — Get An Attack Report
- `list_attack_reports()` — List Attack Reports
- `list_critical_events()` — List Critical Events
- `list_events()` — List Events


### `arbor-aed` v1.1.0 _(installed)_
_Netscout AED_

Netscout Arbor Edge Defense (AED) secures the internet data center edge from threats against availability — specifically from application-layer, distributed denial of service (DDoS) attacks.

**26 operation(s)**:

- `add_inbound_blacklist_countries()` — Add Inbound Blacklist Countries
- `add_inbound_blacklist_domains()` — Add Inbound Blacklist Domains
- `add_inbound_blacklist_hosts()` — Add Inbound Blacklist Hosts
- `add_inbound_blacklist_urls()` — Add Inbound Blacklist URLs
- `add_inbound_whitelisted_hosts()` — Add Inbound Whitelisted Hosts
- `add_outbound_blacklist_hosts()` — Add Outbound Blacklist Hosts
- `add_outbound_whitelisted_hosts()` — Add Outbound Whitelist Hosts
- `create_inbound_protection_groups()` — Create Inbound Protection Groups
- `execute_an_api_call()` — Execute an API Request
- `get_countries()` — Get Countries
- `get_inbound_blacklisted_countries()` — Get Inbound Blacklisted Countries
- `get_inbound_blacklisted_domains()` — Get Inbound Blacklisted Domains
- `get_inbound_blacklisted_hosts()` — Get Inbound Blacklisted Hosts
- `get_inbound_blacklisted_urls()` — Get Inbound Blacklisted URLs
- `get_inbound_protection_groups()` — Get Inbound Protection Groups
- `get_inbound_whitelisted_hosts()` — Get Inbound Whitelisted Hosts
- `get_outbound_blacklisted_hosts()` — Get Outbound Blacklisted Hosts
- `get_outbound_whitelisted_hosts()` — Get Outbound Whitelisted Hosts
- `remove_inbound_blacklisted_countries()` — Remove Inbound Blacklisted Countries
- `remove_inbound_blacklisted_domains()` — Remove Inbound Blacklisted Domains
- `remove_inbound_blacklisted_hosts()` — Remove Inbound Blacklisted Hosts
- `remove_inbound_blacklisted_urls()` — Remove Inbound Blacklisted URLs
- `remove_inbound_whitelisted_hosts()` — Remove Inbound Whitelisted Hosts
- `remove_outbound_blacklisted_hosts()` — Remove Outbound Blacklisted Hosts
- `remove_outbound_whitelisted_hosts()` — Remove Outbound Whitelisted Hosts
- `update_inbound_protection_groups()` — Update Inbound Protection Groups


### `arbor-aps` v2.0.0 _(installed)_
_Arbor APS_

Arbor APS connector perform automated operations, such as retrieving all DDoS alerts or alerts based on the search criteria you have specified from Arbor APS, or retrieving network summary reports using various filters you have specified from Arbor APS.

**25 operation(s)**:

- `add_inbound_blacklist_countries()` — Add Inbound Blacklist Countries
- `add_inbound_blacklist_domains()` — Add Inbound Blacklist Domains
- `add_inbound_blacklist_hosts()` — Add Inbound Blacklist Hosts
- `add_inbound_blacklist_urls()` — Add Inbound Blacklist URLs
- `add_inbound_whitelisted_hosts()` — Add Inbound Whitelisted Hosts
- `add_outbound_blacklist_hosts()` — Add Outbound Blacklist Hosts
- `add_outbound_whitelisted_hosts()` — Add Outbound Whitelist Hosts
- `create_inbound_protection_groups()` — Create Inbound Protection Groups
- `get_countries()` — Get Countries
- `get_inbound_blacklisted_countries()` — Get Inbound Blacklisted Countries
- `get_inbound_blacklisted_domains()` — Get Inbound Blacklisted Domains
- `get_inbound_blacklisted_hosts()` — Get Inbound Blacklisted Hosts
- `get_inbound_blacklisted_urls()` — Get Inbound Blacklisted URLs
- `get_inbound_protection_groups()` — Get Inbound Protection Groups
- `get_inbound_whitelisted_hosts()` — Get Inbound Whitelisted Hosts
- `get_outbound_blacklisted_hosts()` — Get Outbound Blacklisted Hosts
- `get_outbound_whitelisted_hosts()` — Get Outbound Whitelisted Hosts
- `remove_inbound_blacklisted_countries()` — Remove Inbound Blacklisted Countries
- `remove_inbound_blacklisted_domains()` — Remove Inbound Blacklisted Domains
- `remove_inbound_blacklisted_hosts()` — Remove Inbound Blacklisted Hosts
- `remove_inbound_blacklisted_urls()` — Remove Inbound Blacklisted URLs
- `remove_inbound_whitelisted_hosts()` — Remove Inbound Whitelisted Hosts
- `remove_outbound_blacklisted_hosts()` — Remove Outbound Blacklisted Hosts
- `remove_outbound_whitelisted_hosts()` — Remove Outbound Whitelisted Hosts
- `update_inbound_protection_groups()` — Update Inbound Protection Groups


### `arbor-ddos` v1.0.0 _(installed)_
_Arbor DDoS_

Arbor DDoS connector perform automated operations, such as retrieving all DDoS alerts or alerts based on the search criteria you have specified from Arbor DDoS, or retrieving network summary reports using various filters you have specified from Arbor DDoS.

**3 operation(s)**:

- `get_alerts()` — Get Alerts
- `get_network_summery_report()` — Get Network Summary Report
- `get_top_talker_report()` — Get TopTalker Report


### `arkime` v1.0.0 _(installed)_
_Arkime_

Arkime is an open-source, large-scale, full packet capture (FPC) and indexing system. It's designed for security professionals to store and analyze network traffic in detail.

**14 operation(s)**:

- `add_tags_to_sessions()` — Add Tags to Sessions
- `execute_an_api_call()` — Execute an API Request
- `get_all_connections()` — Get All Connections
- `get_all_connections_csv()` — Get All Connections CSV
- `get_all_fields()` — Get All Fields
- `get_all_multiple_unique_fields()` — Get All Multiple Unique Fields
- `get_all_pcap_files()` — Get All PCAP Files
- `get_all_sessions()` — Get All Sessions
- `get_all_sessions_csv()` — Get All Sessions CSV
- `get_all_sessions_pcap()` — Get All Sessions PCAP
- `get_all_spi_graph()` — Get All SPI Graph
- `get_all_spi_view()` — Get All SPI View
- `get_all_unique_fields()` — Get All Unique Fields
- `remove_tags_from_sessions()` — Remove Tags from Sessions


### `aruba-clearpass` v1.2.0 _(installed)_
_Aruba ClearPass_

Aruba ClearPass is a policy management platform that enables businesses to effortlessly onboard new devices, grant varying access levels, and keep their networks secure. Aruba ClearPass connector performs actions like list guest and guest details, list endpoints and endpoint details etc.

**13 operation(s)**:

_containment_
- `block_endpoint(mac_adress: text)` — Block Endpoint

_investigation_
- `execute_api_request(endpoint: text, method: select, [query_params: json], [payload: json])` — Execute an API Request
- `get_device_profile([mac_or_ip: text])` — Get Device Profile
- `get_endpoint_details(endpoint_id: text)` — Get Endpoint Detail
- `get_endpoint_details_by_macaddress(mac_address: text)` — Get Endpoint Details by MAC Address
- `get_guest_details(guest_id: text)` — Get Guest Details
- `list_endpoints()` — List Endpoint
- `list_guests()` — Get List of Guests
- `list_sessions([filter: text])` — List Sessions
- `terminate_session(session_id: text)` — Terminate Sessions
- `update_endpoint_status(endpoint_id: text, endpoint_status: select, [description: text])` — Update Endpoint Status

_remediation_
- `disable_device([mac_address: text])` — Disable Device
- `session_coa_mac([mac_address: text], [coa_profile: text])` — Send Session COA by MAC


### `aws-network-firewall` v1.0.0 _(installed)_
_AWS Network Firewall_

AWS Network Firewall is a managed service that makes it easy to deploy essential network protections for all of your Amazon Virtual Private Clouds (VPCs). Network Firewall is a stateful, managed, network firewall and intrusion detection and prevention service. This Connector automated operations such as retrieving create, update and delete operation in AWS Network firewall.

**20 operation(s)**:

- `create_firewall()` — Create Firewall
- `create_firewall_policy()` — Create Firewall Policy
- `create_rule_group()` — Create Rule Group
- `delete_firewall()` — Delete Firewall
- `delete_firewall_policy()` — Delete Firewall Policy
- `delete_resource_policy()` — Delete Resource Policy
- `delete_rule_group()` — Delete Rule Group
- `describe_firewall()` — Describe Firewall
- `describe_firewall_policy()` — Describe Firewall Policy
- `describe_logging_configuration()` — Describe Logging Configuration
- `describe_resource_policy()` — Describe Resource Policy
- `describe_rule_group()` — Describe Rule Group
- `disassociate_subnets()` — Disassociate Subnets
- `get_associate_firewall_policy()` — Get Associate Firewall Policy
- `get_associate_subnets()` — Get Associate Subnets
- `get_list_firewall_policies()` — Get List Firewall Policies
- `get_list_firewalls()` — Get List Firewalls
- `get_list_rule_groups()` — Get List Rule Groups
- `get_list_tag_for_resource()` — Get List Tag For Resource
- `tag_resource()` — Tag Resource


### `centreon` v1.0.0 _(installed)_
_Centreon_

Centreon is a user-friendly and powerful monitoring platform. This connector allows you to actions related to hosts host like get host, add host, delete host and get host parent

**26 operation(s)**:

- `add_contact()` — Add Contact
- `add_host()` — Add Host
- `add_host_group()` — Add Host Group
- `add_parent()` — Add Parent
- `add_template()` — Add Template
- `delete_contact()` — Delete Contact
- `delete_host()` — Delete Host
- `delete_host_group()` — Delete Host Group
- `delete_macro()` — Delete Macro
- `delete_parent()` — Delete Parent
- `delete_template()` — Delete Template
- `disable_host()` — Disable Host
- `enable_host()` — Enable Host
- `get_contacts()` — Get Contacts
- `get_host()` — Get Hosts
- `get_host_group()` — Get Host Groups
- `get_host_status()` — Get Hosts Status
- `get_macro()` — Get Macro
- `get_parent()` — Get Parent
- `get_service_status()` — Get Service Status
- `get_templates()` — Get Templates
- `set_contact()` — Set Contact
- `set_host_group()` — Set Host Group
- `set_macro()` — Set Macro
- `set_parent()` — Set Parent
- `set_template()` — Set Template


### `cisco-catalyst` v1.0.0 _(installed)_
_Cisco Catalyst_

Get information about the configuration, version and perform action like configure system VLAN on a Cisco Catalyst switch

**3 operation(s)**:

- `configure_vlan()` — Configure VLAN
- `get_config()` — Get Configuration
- `get_version()` — Get Version


### `cisco-meraki-dashboard` v1.0.0 _(installed)_
_Cisco Meraki Dashboard_

The Cisco Meraki provide cloud managed devices.

**1 operation(s)**:

- `locate_device()` — Locate Device


### `cisco-umbrella-enforcement` v3.0.1 _(installed)_
_Cisco Umbrella Enforcement_

Cisco Umbrella is a cloud security platform that provides the first line of defense against threats on the internet wherever users go. Cisco Umbrella Enforcement API allows partners and customers who have their own SIEM/Threat Intelligence Platform (TIP) environments to inject events and/or threat intelligence into their Umbrella environment.

**4 operation(s)**:

- `add_destination()` — Add Destinations to Destination List
- `delete_destinations_from_list()` — Delete Destinations from Destination List
- `get_destination_lists()` — Get All Destination List
- `list_destinations()` — Get Destinations in Destination List


### `commvault` v1.0.0 _(installed)_
_Commvault_

Commvault is an Intelligent Data Services platform which helps you close the business integrity gap, keeping your data available and ready for business growth. This connector facilitates operations to get alerts, get and update the user details.

**4 operation(s)**:

- `alert_details()` — Get Alert Details
- `list_of_alerts()` — Get Alerts List
- `list_of_users()` — Get Users List
- `update_user()` — Update User Details


### `fireeye-nx` v1.0.1 _(installed)_
_FireEye NX_

FireEye NX connector perform automated operations such as retrieving a list of all guest image profiles and applications details, retrieving artifacts metadata by alert UUID etc.

**18 operation(s)**:

- `add_event_filters()` — Add Event Filters
- `add_yara_rule()` — Add YARA Rule
- `delete_event_filters()` — Delete Event Filters
- `delete_yara_rule()` — Delete YARA Rule
- `get_alert_details()` — Get Alert Details
- `get_alert_updated_with_ati_info()` — Get Alerts Updated with ATI Information
- `get_alerts()` — Get Alerts
- `get_artifacts_metadata_by_uuid()` — Get Artifacts Metadata By UUID
- `get_ati_details_of_alert()` — Get ATI Information of Alert
- `get_config()` — Get Configuration Information
- `get_event_filter_protocols()` — Get Event Filter Protocols
- `get_event_filters()` — Get Event Filters
- `get_events()` — Get Events
- `get_health_status()` — Get System Health Status
- `get_report_by_id()` — Get Report By ID
- `get_reports_by_time()` — Get Reports By Time
- `get_statistics()` — Get Statistics
- `list_yara_rule()` — List YARA Rule


### `forcepoint-dlp` v1.0.0 _(installed)_
_Forcepoint DLP_

Forcepoint DLP used to prevent data leakage, ensure regulatory compliance, protect intellectual property, manage employee productivity, mitigate risks, and respond to security incidents within organizations.

**10 operation(s)**:

- `get_incidents_by_action()` — Get Incidents by Action
- `get_incidents_by_date_range()` — Get Incidents by Date Range
- `get_incidents_by_ids()` — Get Incidents by IDs
- `get_incidents_by_policy_name()` — Get Incidents by Policy Name
- `get_incidents_by_severity()` — Get Incidents by Severity
- `get_incidents_by_status()` — Get Incidents by Status
- `get_list_of_incidents_by_filter()` — Get List Of Incident By Filter
- `update_incident_status_by_event_ids()` — Update Incident Status By Event IDs
- `update_incident_status_by_incident_id_and_partition_index()` — Update Incident Status By Incident ID And Partition Index
- `update_incident_status_by_scan_partitions()` — Update Incident Status By Scan Partitions


### `forcepoint-websense` v1.0.0 _(installed)_
_Forcepoint Websense_

Forcepoint Websense connector provides actions like, create/delete API-managed categories, list out all or API-managed categories, update API-managed categories.

**6 operation(s)**:

- `add_category()` — Create API-managed Category
- `delete_address_from_category()` — Delete URLs and IP addresses
- `delete_categories()` — Delete API-managed Categories
- `get_category_details()` — Get API-managed Category Details
- `list_categories()` — Get All Categories
- `update_category()` — Update API-managed Category


### `forescout` v1.0.0 _(installed)_
_ForeScout_

ForeScout provides insight into the diverse types of devices connected to your heterogeneous network—from campus and data center to cloud and operational technology networks. Use this connector to get active hosts, get policies

**4 operation(s)**:

- `get_active_hosts()` — Get Active Hosts
- `get_host()` — Get Host Information
- `get_host_properties()` — Get Host Properties
- `get_policies()` — Get Policies


### `fortinet-fortiddos` v1.0.0 _(installed)_
_Fortinet FortiDDoS_

FortiDDoS Protection Solution defends enterprise data centers against DDoS attacks by leveraging an extensive collection of known DDoS methodologies, creating a multi-layered approach to mitigate attacks.  It also analyzes the behavior of data to detect new attacks, allowing it to stop zero-day threats.

**24 operation(s)**:

- `add_distress_acl()` — Add Distress ACL
- `add_lq()` — Add Legitimate DNS Query
- `add_service_protection_profile_policy()` — Add Service Protection Profile Policy
- `delete_distress_acl()` — Delete Distress ACL
- `delete_lq()` — Delete Legitimate DNS Query
- `delete_service_protection_profile_policy()` — Delete Service Protection Profile Policy
- `generate_bgp_flowspec()` — Generate BGP Flowspec
- `get_attack_information()` — Get Attack Information
- `get_bypass_mac()` — Get Bypass MAC
- `get_do_not_track_policy()` — Get Do Not Track Policy
- `get_domain_reputation()` — Get Domain Reputation
- `get_global_acl()` — Get Access Control List
- `get_global_settings()` — Get Global Settings
- `get_global_settings_address()` — Get Global Settings Address
- `get_global_spp()` — Get Global Service Protection Profiles
- `get_ip_reputation()` — Get IP Reputation
- `get_log_settings()` — Get Log Settings
- `get_proxy_ip()` — Get Proxy IP
- `get_proxy_ip_policy()` — Get Proxy IP Policy
- `get_service_protection_profile_policy()` — Get Service Protection Profile Policy
- `get_settings()` — Get Settings
- `get_spp_settings()` — Get Protection Profiles
- `get_system_settings()` — Get System Settings
- `update_service_protection_profile_settings()` — Update Protection Profiles Settings


### `fortinet-fortideceptor` v1.0.0 _(installed)_
_Fortinet FortiDeceptor_

FortiDeceptor is a deception-based Breach Protection Deceive, Expose and Eliminate External and Internal Threats.

**9 operation(s)**:

- `decoy_delete()` — Delete Decoy
- `decoy_deploy()` — Deploy Decoy
- `decoy_start()` — Start Decoy
- `decoy_stop()` — Stop Decoy
- `deploy_nets()` — Get Deployment Networks
- `get_attack_events()` — Get Attack Events
- `get_attack_incidents()` — Get Attack Incidents
- `get_decoy()` — Get Decoy
- `get_templates()` — Get Templates


### `fortinet-fortidlp` v1.1.0 _(installed)_
_Fortinet FortiDLP_

FortiDLP is a data loss prevention (DLP) solution from Fortinet that helps organizations prevent data leaks, detect insider risks, and educate employees on cyber hygiene.

**18 operation(s)**:

- `add_labels_to_agents()` — Add Labels to Agents
- `add_labels_to_users()` — Add Labels to Users
- `agent_action_request()` — Agent Action Request
- `get_agent_details()` — Get Agent Details
- `get_agents_list()` — Get Agents List
- `get_audit_logs()` — Get Audit Logs
- `get_available_actions_list()` — Get Available Actions List
- `get_configured_streams_list()` — Get Configured Streams List
- `get_events_from_event_streaming()` — Get Events from Event Streaming
- `get_incidents_by_id()` — Get Incidents By ID
- `get_incidents_list()` — Get Incidents List
- `get_label_details()` — Get Label Details
- `get_labels_list()` — Get Labels List
- `get_pending_in_flight_actions_list()` — Get Pending In-Flight Actions List
- `get_user_details()` — Get User Details
- `get_users_list()` — Get Users List
- `send_custom_request()` — Execute an API Request
- `update_incidents_by_id()` — Update Incidents


### `fortinet-fortinac` v1.0.0 _(installed)_
_Fortinet FortiNAC_

FortiNAC is the Fortinet network access control solution. It enhances the overall Fortinet Security Fabric with visibility, control, and automated response.

**5 operation(s)**:

- `get_active_hosts()` — Get Active Hosts
- `get_host_information()` — Get Host Information
- `get_policies()` — Get Policies
- `isolate_device()` — Isolate Device
- `update_host_properties()` — Update Host Properties


### `fortinet-fortisase` v1.0.0 _(installed)_
_Fortinet FortiSASE_

FortiSASE is a cloud-delivered security service edge (SSE) solution that provides always-on secure access to private applications. This connector facilitates automated operations to manage services, hosts, host groups, and policies.

**10 operation(s)**:

_investigation_
- `create_from_hub_policy(policy_config: json)` — Create From Hub Policy
- `create_host(primaryKey: text, location: select)` — Create Host
- `create_service(primaryKey: text, category: select, protocol: select, port_range: json)` — Create Service
- `create_to_hub_policy(policy_config: json)` — Create To Hub Policy
- `delete_host(primaryKey: text)` — Delete Host
- `delete_service(primaryKey: text)` — Delete Service
- `generic_api_call(method: select, endpoint: text, [data: json])` — Generic API Call
- `get_host(host_name: text)` — Get Host
- `get_service(service_name: text)` — Get Service
- `get_services()` — Get Services List


### `google-key-management-service` v1.0.0 _(installed)_
_Google Key Management Service_

Google Key Management Service allows you to create, import, and manage cryptographic keys and perform cryptographic operations in a single centralized cloud service. This connector facilitates the automated operations related to location, keyRings, cryptoKey and cryptoKey version.

**15 operation(s)**:

- `create_cryptokey()` — Create CryptoKey
- `create_cryptokey_version()` — Create CryptoKey Version
- `create_keyring()` — Create KeyRing
- `decrypt_cryptokey_details()` — Decrypt CryptoKey Details
- `destroy_cryptokey_version()` — Destroy CryptoKey Version
- `encrypt_cryptokey_details()` — Encrypt CryptoKey Details
- `get_cryptokey_details()` — Get CryptoKey Details
- `get_cryptokey_list()` — Get CryptoKey List
- `get_cryptokey_version_details()` — Get CryptoKey Version Details
- `get_cryptokey_version_list()` — Get CryptoKey Version List
- `get_keyring_details()` — Get KeyRing Details
- `get_keyring_list()` — Get KeyRing List
- `get_locations_list()` — Get Locations List
- `get_public_key_for_cryptokey_version()` — Get Public key for CryptoText Version
- `restore_cryptokey_version()` — Restore CryptoKey Version


### `infoblox-bloxone-threat-defense` v1.2.0 _(installed)_
_Infoblox BloxOne Threat Defense_

Infoblox BloxOne Threat Defense provides foundational security that improves the efficiency of security operations centers by streamlining and automating threat response, reducing complexity, and enhancing the capabilities and performance of existing security investments.

**15 operation(s)** (+3 hidden):

- `create_dossier_source_lookup_job()` — Create a Dossier Source Lookup Job
- `dossier_reputation()` — Get Dossier Reputation of Indicator
- `get_all_dossier_source()` — Get All Dossier Sources
- `get_dossier_lookup_job_status()` — Get Dossier Lookup Job Status
- `get_dossier_sources_by_indicator_type()` — Get Dossier Sources By Indicator Type
- `get_named_lists()` — Get Named Lists
- `get_specific_named_list()` — Get Specific Named List
- `get_task_details_for_lookup_job()` — Get Specific Task Details of Dossier Lookup Job
- `get_task_results_of_dossier_lookup_job()` — Get the Task Results of a Dossier Lookup Job
- `get_valid_indicator_types_for_source()` — Get Valid Indicator Types for Source
- `lookalike_domain_search()` — Search Lookalike Domain
- `lookalike_domain_search_with_classification()` — Search Lookalike Domain With Classification


### `juniper-sky-atp` v1.0.0 _(installed)_
_Juniper Sky ATP_

Juniper Sky Advanced Threat Protection Connector

**3 operation(s)**:

- `add_infected_host()` — Add Infected Host
- `delete_infected_host()` — Delete Infected Host
- `get_infected_hosts()` — Get All Infected Hosts


### `mcafee-network-security-manager` v1.1.0 _(installed)_
_McAfee Network Security Manager_

McAfee Network Security Manager appliance delivers centralized, web-based management and unrivaled ease of use. This connector facilitates the automated operations like block and unblock IP, get domain details etc.

**15 operation(s)**:

- `add_domain()` — Create Domain
- `block_ip()` — Block IP
- `delete_domain()` — Delete Domain
- `delete_policy()` — Delete Policy
- `get_blocked_ip_details()` — Get Blocked IP Details
- `get_blocked_ip_list()` — Get Blocked IP List
- `get_domain_details()` — Get Domain Details
- `get_domain_sensors()` — Get Domain Sensors
- `get_domains()` — Get All Domains
- `get_policy_details()` — Get Policy Details
- `get_sensor_details()` — Get Sensor Details
- `list_policies()` — Get Domain Firewall Policies
- `unblock_ip()` — Unblock IP
- `update_block_ip_duration()` — Update Block IP Duration
- `update_domain()` — Update Domain


### `mcafee-open-dxl` v1.1.0 _(installed)_
_McAfee OpenDXL_

The McAfee Open Data Exchange Layer (DXL) Connector allow automated way to communicate across multiple mcafee products with optimized security actions.

**1 operation(s)**:

- `publish_message()` — Publish Message to Topic


### `mcafee-web-gateway` v1.0.0 _(installed)_
_McAfee Web Gateway_

A McAfee Web Gateway connects your network to the web and filters the traffic that goes out from your network and comes into your network. This connector provides automated actions for list and rules sets on McAfee Web Gateway used for Filtering.

**10 operation(s)**:

- `create_empty_list()` — Create Empty List
- `delete_list()` — Delete List
- `delete_list_entry()` — Delete List Entry
- `get_all_list_entries()` — Get All List Entries
- `get_details_of_list_entry()` — Get Details of List Entry
- `get_list_details()` — Get List Details
- `get_lists()` — Get Lists
- `get_rule_set_details()` — Get Rule Set Details
- `get_rule_sets()` — Get Rule Sets
- `insert_list_entry()` — Insert List Entry in Simple List


### `netbios` v1.0.1 _(installed)_
_NetBIOS_

This connector provides various investigation actions over the NetBIOS protocol.

**1 operation(s)**:

- `ip_lookup()` — Get Hostname


### `netscaler` v1.0.0 _(installed)_
_Netscaler VPX_

Citrix NetScaler VPX Connector

**5 operation(s)**:

- `create_responder_action()` — Create Responder Action
- `create_responder_policy()` — Create Responder Policy
- `get_fwpolicy_details()` — Get App FW Policy
- `ip_reputation()` — Create IP Reputation Policy
- `update_policy()` — Update Application Firewall Policy Expression


### `netskope` v2.0.0 _(installed)_
_Netskope_

Netskope provides smart cloud security which controls activities across any cloud service or website and provides 360-degree data and threat protection that works everywhere. This connector facilitates automated operations like get alerts list, get events list, and urls related operations.

**10 operation(s)**:

- `add_url_list()` — Add URL List
- `create_url_list()` — Create URL List
- `delete_url_list()` — Delete URL List
- `get_alerts_list()` — Get Alerts List
- `get_client_list()` — Get Client List
- `get_events_list()` — Get Events List
- `get_url_list()` — Get All URL List
- `get_url_list_details()` — Get URL List Details
- `send_custom_request()` — Execute an API Request
- `update_url_list()` — Update URL List


### `orca` v2.0.0 _(installed)_
_Orca_

Orca Security provides Agentless, Workload-Deep, Context-Aware Cloud Infrastructure Security and Compliance for IaaS platforms AWS, Azure, and GCP. This connector facilitates automated operations related to fetch security alert and assert related data.

**5 operation(s)**:

- `get_alerts()` — Get Alerts
- `get_assets()` — Get Assets
- `run_query()` — Run Query
- `update_alert_severity()` — Update Alert Severity
- `update_alert_status()` — Update Alert Status


### `paloalto-enterprise-dlp` v1.0.1 _(installed)_
_Palo Alto Enterprise DLP_

Palo Alto Enterprise DLP discovers and protects company data across every data channel and repository.

**1 operation(s)**:

- `get_report_details()` — Get Report Details


### `paloalto-prisma-cloud` v1.0.1 _(installed)_
_Palo Alto Prisma Cloud_

Prisma Cloud is a cloud security posture management (CSPM) and cloud workload protection platform (CWPP) that provides comprehensive visibility and threat detection across an organization’s hybrid, multi-cloud infrastructure. This connector provides Get Alerts, Get Alert Details, Dismiss Alerts, Reopen Alert, Get Alert Remediation Commands, Get Policy Information, etc actions

**7 operation(s)**:

- `dismiss_alerts()` — Dismiss Alerts
- `get_alert_details()` — Get Alert Details
- `get_alert_filters()` — Get Alert Filters
- `get_alert_remediation_commands()` — Get Alert Remediation Commands
- `get_alerts()` — Get Alerts
- `get_policy_info()` — Get Policy Information
- `reopen_alerts()` — Reopen Alerts


### `pensando-policy-servicemanager` v1.0.1 _(installed)_
_Pensando Policy Service Manager_

Pensando's Policy and Services Manager (PSM) is a distributed system that leverages an intent-based model to deliver network and security policy to Pensando Distributed Services Cards for services implementation at the edge.

**17 operation(s)** (+3 hidden):

- `delete_ipfix_export()` — Delete existing IPFIX Export for Host
- `delete_mirror_export()` — Delete Existing Mirror Traffic Export for Host
- `enable_ipfix_export()` — Enable IPFIX Export for Host
- `enable_mirror_export()` — Enable Mirror Traffic Export for Host
- `get_alerts()` — Get Alerts
- `get_distributedservicecards()` — Get Distributed Service Cards
- `get_network_security_policies()` — Get Network Security Policies
- `get_networks()` — Get Networks
- `get_workloads()` — Get Workloads
- `ioc_block_add_ip()` — Add IOC IPs to Blocklist
- `ioc_block_remove_ip()` — Remove IOC IPs from Blocklist
- `ioc_delete_list()` — Remove IOC Blocklist
- `isolate_host()` — Isolate Host
- `unisolate_host()` — Unisolate Host


### `polar-security` v1.0.0 _(installed)_
_Polar Security_

An agentless platform that connects within minutes, Polar Security can automatically find unknown and sensitive data across the cloud.

**7 operation(s)**:

- `apply_label()` — Apply Label
- `get_data_store()` — Get Data Store
- `get_data_stores()` — Get Data Stores
- `get_data_stores_summary()` — Get Data Stores Summary
- `get_linked_vendors()` — Get Linked Vendors
- `get_vendor_accessible_data_store()` — Get Vendor Accessible Data Store
- `get_vendors_data_stores()` — Get Vendors Data Stores


### `progress-whatsup-gold` v1.0.0 _(installed)_
_Progress WhatsUp Gold_

WhatsUp Gold provides complete visibility into the status and performance of applications, network devices and servers in the cloud or on-premises.

**7 operation(s)**:

- `get_device_attributes()` — Get Device Attributes
- `get_device_groups()` — Get Device Groups
- `get_device_monitors()` — Get Device Monitors
- `get_device_overview()` — Get Device Overview
- `get_device_polling_configuration()` — Get Device Polling Configuration
- `get_device_report()` — Get Device Report
- `get_device_summary()` — Get Device Summary


### `protectwise` v1.0.0 _(installed)_
_ProtectWise_

This connector integrate with ProtectWise and perform investigative actions

**4 operation(s)**:

- `domain_reputation()` — Domain Reputation
- `file_reputation()` — File Reputation
- `get_pcap()` — Get PCAP
- `ip_reputation()` — IP Reputation


### `rsa-netwitness-logs-and-packets` v1.0.2 _(installed)_
_RSA Netwitness Logs and Packets_

RSA Netwitness Logs and Packets collects real-time network data from sessions. This connector facilitates the automated operations like get PCAP data and metadata from IP Address, Domain and Username, query Netwitness

**5 operation(s)**:

- `get_meta_from_type()` — Get Metadata
- `get_pcap()` — Get PCAP Data for Session IDs
- `get_pcap_from_type()` — Get PCAP Data
- `get_raw_query()` — Netwitness Search
- `get_session_ids_from_where_stmnt()` — Get Session IDs


### `shieldx` v1.0.0 _(installed)_
_ShieldX_

ShieldX connector automates to pull security threat events and actions to isolate workloads, assign tags etc.

**12 operation(s)** (+2 hidden):

- `assign_tag()` — Assign Tag
- `create_tag()` — Create Tag
- `get_tag()` — Get Tags
- `list_infrastructure()` — List Infrastructure
- `list_security_policy()` — List Security Policies
- `list_workloads()` — List Workloads
- `search_events_by_index()` — Fetch Threat Events
- `unassign_tag()` — Unassign Tag
- `update_security_policy()` — Update Security Policy
- `workloads_details()` — Get Workload Details


### `solarwinds` v1.0.0 _(installed)_
_SolarWinds_

The SolarWinds Orion Platform is a unified suite of network and system management products. This connector facilitates the automated operations to get the alert list, get the event list and to execute SWIS query.

**3 operation(s)**:

- `execute_swis_query()` — Execute SWIS Query
- `get_alert_list()` — Get Alert List
- `get_event_list()` — Get Event List


### `sonicwall-nsm` v1.0.0 _(installed)_
_SonicWall NSM_

SonicWall Network Security Manager (NSM) is a cloud-based (or on-prem) platform designed to centrally manage, monitor, and report on SonicWall firewalls and security policies across distributed environments.

**5 operation(s)**:

- `create_address_object()` — Create Address Object
- `execute_an_api_call()` — Execute an API Request
- `get_access_rules()` — Get Access Rules
- `get_address_objects()` — Get Address Object
- `update_address_object()` — Update Address Object


### `sophos-utm-9` v1.0.0 _(installed)_
_Sophos UTM_

Sophos UTM - 9 Firewall

**10 operation(s)**:

- `block_applications()` — Block Applications
- `block_ips()` — Block IP Addresses
- `block_urls()` — Block URLs
- `check_policies()` — Check Policies
- `get_blocked_application_names()` — Get Blocked Application Names
- `get_blocked_ips()` — Get Blocked IPs
- `get_blocked_urls()` — Get Blocked URLs
- `unblock_applications()` — Unblock Applications
- `unblock_ips()` — Unblock IP Addresses
- `unblock_urls()` — Unblock URLs


### `stealthwatch` v2.1.0 _(installed)_
_Cisco Stealthwatch_

Stealthwatch is the solution that detects threats across your private network, public clouds, and even in encrypted traffic.

**14 operation(s)**:

- `application_traffic_domainid()` — Get Application Traffic by Domain ID
- `application_traffic_hostgroupid()` — Get Application Traffic by Host Group ID
- `application_traffic_ip()` — Get Application Traffic by Exporter IP
- `get_domain_details()` — Get Domain Details
- `get_flow_search_results()` — Get Flow Search Results
- `get_flow_search_status()` — Get Flow Search Status
- `get_host_details()` — Get Host Group Details
- `get_top_conversation_result()` — Get Top Conversation Flow Search Result
- `get_top_conversation_status()` — Get Top Conversation Flow Search Status
- `initiate_flow_analysis()` — Initiate Flow Analysis
- `initiate_flow_search()` — Initiate Flow Search
- `list_host_groups()` — Get Host Groups List
- `threats_top_alarms()` — Get External Threats Top Alarm Host
- `top_conversation_flow()` — Initiate Top Conversation Flow Search


### `symantec-management-center` v1.0.0 _(installed)_
_Symantec Management Center_

Symantec Management Center provides a unified management environment for the Symantec Security Platform portfolio of products. Management Center brings Symantec’s network, security, and cloud technologies to you under a single umbrella making it easier to deploy, manage, and monitor your security environment.

**8 operation(s)**:

- `add_policy_content()` — Add or Update Policy Content
- `create_policy()` — Create Policy
- `delete_policy()` — Delete Policy
- `get_policies()` — Get Policies
- `get_policy_content()` — Get Policy Content
- `get_policy_content_by_version()` — Get Policy Content By Version
- `get_policy_details()` — Get Policy Details
- `update_policy()` — Update Policy


### `threatstop` v1.0.0 _(installed)_
_ThreatSTOP_

ThreatSTOP is a cloud-based automated threat intelligence platform that converts the latest threat data into enforcement policies, and automatically updates your firewalls, routers, DNS servers and endpoints to stop attacks before they become breaches.

**14 operation(s)**:

- `add_domain_to_domain_udl()` — Add Domain to Domain UDL
- `add_ip_to_ip_udl()` — Add IP to IP UDL
- `check_ioc()` — Check IOC
- `create_domain_udl()` — Create Domain UDL
- `create_ioc()` — Create IOC
- `create_ip_udl()` — Create IP UDL
- `delete_domain_from_domain_udl()` — Delete Domain from Domain UDL
- `delete_ip_from_ip_udl()` — Delete IP from IP UDL
- `get_devices()` — Get Devices Details
- `get_domain_policies()` — Get Domain Policies
- `get_domain_udls()` — Get Domain UDLs
- `get_ip_policies()` — Get IP Policies 
- `get_ip_udls()` — Get IP UDLs
- `get_log_details()` — Get Log Details


### `threatx` v1.0.0 _(installed)_
_ThreatX_

Use the ThreatX integration to enrich intel and automate enforcement actions on the ThreatX Next Gen WAF.

**9 operation(s)**:

- `add_entity_note()` — Add Entity Notes
- `blacklist_ip()` — Blacklist IP Address
- `block_ip()` — Block IP Address
- `get_entities()` — Get Entities
- `get_entity_notes()` — Get Entity Notes
- `unblacklist_ip()` — Unblacklist IP Address
- `unblock_ip()` — Unblock IP Address
- `unwhitelist_ip()` — Unwhitelist IP Address
- `whitelist_ip()` — Whitelist IP Address


### `vmware-nsx-t` v1.2.0 _(installed)_
_VMware NSX-T_

VMware NSX-T Data Center focuses on providing networking, security, automation, and operational simplicity for emerging application frameworks and architectures that have heterogeneous endpoint environments and technology stacks. This Connector automated operations such as create, update and delete operation related to policy, rule, group etc.

**16 operation(s)**:

- `add_remove_ip_addresses()` — Add/Remove IP Addresses
- `add_remove_mac_addresses()` — Add/Remove MAC Addresses
- `delete_group()` — Delete Group
- `delete_rule()` — Delete Rule
- `delete_security_policy()` — Delete Security Policy
- `get_group_details()` — Get Group Details
- `get_groups_list()` — Get Groups List
- `get_rule_details()` — Get Rule Details
- `get_rules_list()` — Get Rules List
- `get_security_policies_list()` — Get Security Policies List
- `get_security_policy_details()` — Get Security Policy Details
- `get_vm_externalID()` — Get VM External ID
- `manage_vm_tag()` — Manage VM TAG
- `upsert_group()` — Upsert Group
- `upsert_rule()` — Upsert Rule
- `upsert_security_policy()` — Upsert Security Policy


### `wigle` v1.0.0 _(installed)_
_WiGLE_

Wireless Geographic Logging Engine for collecting information about the different wireless hotspots around the world. WiGLE connector for network lookup, network details, cell search and getting statistics

**9 operation(s)**:

- `cell_search()` — Cell Search
- `get_network_details()` — Get Network Details
- `get_statistics_by_countries()` — Get Country Statistics
- `get_statistics_by_general()` — Get General Statistics
- `get_statistics_by_group()` — Get Group Statistics
- `get_statistics_by_regions()` — Get Region Statistics
- `get_statistics_by_site()` — Get Site Statistics
- `get_statistics_by_user()` — Get User Statistics
- `lookup_network()` — Lookup Network


### `zscaler` v2.1.0 _(installed)_
_Zscaler_

Zscaler is revolutionizing cloud security by empowering organizations to embrace cloud efficiency, intelligence, and agility—securely. This connector integrate with Zscaler and Perform containment, investigation and remediation action.

**17 operation(s)**:

- `add_new_category()` — Add URL Category
- `block_url()` — Block URLs
- `delete_url_category()` — Delete URL Category
- `get_blacklist_urls()` — Get Blacklist URLs
- `get_exempted_urls()` — Get Exempted URLs
- `get_lightweight_url_categories()` — Get Lightweight URL Categories
- `get_sandbox_report_md5_hash()` — Get MD5 Cloud Sandbox Report
- `get_sandbox_report_quota()` — Get Cloud Sandbox Report Quota
- `get_url_categories()` — Get URL Categories
- `get_url_categories_quota()` — Get URL Categories Quota
- `get_url_category_info()` — Get URL Category Details
- `get_whitelist_urls()` — Get Whitelist URLs
- `unblock_url()` — Unblock URLs
- `update_exempted_urls()` — Update exempted URLs
- `update_url_category()` — Update URL Category
- `update_whitelist_urls()` — Update Whitelist URLs
- `url_lookup()` — URL Lookup


### `zscaler-client-connector` v1.0.0 _(installed)_
_Zscaler Client Connector_

Zscaler Client Connector™ is a lightweight agent for user endpoints, enabling hybrid work through secure, fast, reliable access to any app over any network.

**7 operation(s)**:

- `download_device_details()` — Download Device Details
- `download_service_status_of_devices()` — Download Service Status of Devices
- `execute_an_api_call()` — Execute an API Request
- `get_device_app_profile_password()` — Get Device App Profile Password
- `get_device_otp()` — Get Device OTP
- `get_enrolled_device_details()` — Get Enrolled Device Details
- `get_enrolled_device_list()` — Get Enrolled Device List


### `zscaler-private-access` v1.0.0 _(installed)_
_Zscaler Private Access (ZPA)_

Zscaler Private Access (ZPA) is a cloud-delivered Zero Trust Network Access (ZTNA) solution that provides secure, identity-based access to internal applications without placing users on the network. It enables seamless integration with FortiSOAR for automated access control, threat response, and policy enforcement based on real-time user and application context. This connector enables automated operations such as Get All Configured Applications Segments, Get Specific Application Segment Details, Get Customer Certificates, Get All Issued Certificates, and Get Certificate Details.

**6 operation(s)**:

- `execute_api_request()` — Execute an API Request
- `get_all_configured_applications_segments()` — Get All Configured Applications Segments
- `get_all_issued_certificates()` — Get All Issued Certificates
- `get_certificate_details()` — Get Certificate Details
- `get_customer_certificates()` — Get Customer Certificates
- `get_specific_application_segment_details()` — Get Specific Application Segment Details


---

## Network Security,Cloud Security,Endpoint Security

### `illumio-core` v1.0.0 _(installed)_
_Illumio Core_

Illumio that provides a platform designed to help organizations protect their critical applications and data by creating secure zones and controlling access between workloads, regardless of whether those workloads are on-premises or in the cloud. This connector facilitates automated operations related to workloads, IP list and labels.

**20 operation(s)**:

- `create_ip_list()` — Create IP List
- `create_label()` — Create Label
- `create_workload()` — Create Workload
- `delete_ip_list()` — Delete IP List
- `delete_label()` — Delete Label
- `delete_workload()` — Delete Workload
- `get_ip_list()` — Get IP List
- `get_ip_list_by_id()` — Get IP List by ID
- `get_label_by_id()` — Get Label by ID
- `get_labels()` — Get Labels
- `get_pending_security_policy()` — Get Pending Security Policy
- `get_ransomware_details()` — Get Ransomware Details
- `get_workload_by_id()` — Get Workload by ID
- `get_workloads()` — Get Workloads
- `restore_previous_security_policy()` — Restore Previous Security Policy
- `revert_pending_uncommitted_security_policy_list()` — Revert Pending Uncommitted Security Policy List
- `send_custom_request()` — Execute an API Call
- `update_ip_list()` — Update IP List
- `update_label()` — Update Label
- `update_workload()` — Update Workload


---

## Network Visibility

### `symantec-dlp` v2.2.0 _(installed)_
_Symantec DLP_

Symantec DLP provide actions like get incident attachments, get incident details, get incident status, update incident etc.

**10 operation(s)**:

_investigation_
- `download_eml(incident_long_id: text, [save_as_attachment: checkbox])` — Download EML File
- `get_custom_attributes()` — Get Custom Attributes
- `get_incident_attachment(incident_long_id: text, [includeAllComponents: checkbox], [includeOriginalMessage: checkbox])` — Get Incident Attachments
- `get_incident_details(incident_long_id: text, [include_violations: checkbox], [include_history: checkbox])` — Get Incident Details
- `get_incident_status()` — Get Incident Status
- `get_incident_violations(incident_long_id: text, [include_image_violations: checkbox])` — Get Incident Violations
- `get_incidents_ids(report_id: text, creation_date_greater_then: datetime)` — Get Incidents IDs
- `get_sender_recipient_pattern(rule_type: select, pattern_name: text)` — Get Sender/Recipient Pattern
- `update_incident(incident_long_id: text, [severity: select], [status: text], [add_notes: checkbox], [remediation_status: select], [remediation_location: text], [custom_attrib_value: json])` — Update Incident
- `update_sender_recipient_pattern(rule_type: select, [add_items: checkbox])` — Update Sender/Recipient Pattern


---

## OT & IoT Security

### `armis` v1.1.0 _(installed, ingestion)_
_Armis_

Armis connector protects from cyber threats created by the onslaught of unmanaged IoT devices. This connector facilitates operations to get alerts and devices list, update the status of alerts, tag, and untag devices.

**12 operation(s)**:

_investigation_
- `add_device_tags(device_id: text, tags: text)` — Add Device Tag
- `get_alerts([alert_id: text], [start_time: datetime], [risk_level: multiselect], [status: multiselect], [alert_type: multiselect], [site: text], records: select)` — Get Alerts List
- `get_alerts_by_asq([query_string: text], records: select)` — Get Alerts By Armis Standard Query
- `get_devices([device_name: text], [device_id: text], [mac_address: text], [ip_address: text], [device_type: text], [risk_level: multiselect], [site: text], [time_frame: text], records: select)` — Get Devices List
- `get_devices_by_asq([query_string: text], records: select)` — Get Devices By Armis Standard Query
- `get_policies(records: select)` — Get Policies List
- `get_reports()` — Get Reports List
- `get_vulnerability_matches(input_type: select, ids: text, records: select)` — Get Vulnerability Matches
- `remove_device_tags(device_id: text, tags: text)` — Remove Device Tag
- `update_alert_status(alert_id: text, status: select)` — Update Alert Status
- `update_device(device_id: text, attributes: json)` — Update Device
- `update_policy(policy_id: text, attributes: json)` — Update Policy


### `armis_dev` v1.1.0 _(installed)_
_Armis CUSTOM_

Armis connector protects from cyber threats created by the onslaught of unmanaged IoT devices. This connector facilitates operations to get alerts and devices list, update the status of alerts, tag, and untag devices.

**13 operation(s)**:

_investigation_
- `add_device_tags(device_id: text, tags: text)` — Add Device Tag
- `generic_api_call(method: select, endpoint: text, [query_params: json], [data: json], [headers: json])` — Generic API Call
- `get_alerts([alert_id: text], [start_time: datetime], [risk_level: multiselect], [status: multiselect], [alert_type: multiselect], [site: text], records: select)` — Get Alerts List
- `get_alerts_by_asq([query_string: text], records: select)` — Get Alerts By Armis Standard Query
- `get_devices([device_name: text], [device_id: text], [mac_address: text], [ip_address: text], [device_type: text], [risk_level: multiselect], [site: text], [time_frame: text], records: select)` — Get Devices List
- `get_devices_by_asq([query_string: text], records: select)` — Get Devices By Armis Standard Query
- `get_policies(records: select)` — Get Policies List
- `get_reports()` — Get Reports List
- `get_vulnerability_matches(input_type: select, ids: text, records: select)` — Get Vulnerability Matches
- `remove_device_tags(device_id: text, tags: text)` — Remove Device Tag
- `update_alert_status(alert_id: text, status: select)` — Update Alert Status
- `update_device(device_id: text, attributes: json)` — Update Device
- `update_policy(policy_id: text, attributes: json)` — Update Policy


### `everbridge` v1.0.0 _(installed)_
_Everbridge_

Everbridge that provides enterprise software applications that automate and accelerate organizations operational response to critical events. This connector facilitates the automated operations related to incidents, assets, and organizations.

**7 operation(s)**:

- `get_asset_details()` — Get Asset Details
- `get_assets_list()` — Get Assets List
- `get_incident_details()` — Get Incident Details
- `get_incident_list()` — Get Incident List
- `get_organizations_list()` — Get Organizations List
- `update_asset()` — Update Asset
- `update_incident()` — Update Incident


### `scadafence` v1.0.0 _(installed)_
_SCADAfence_

SCADAfence that provides full coverage of large-scale networks, offering best-in-class network monitoring, asset discovery, governance, remote access, and IoT device security. This connector facilitates the automated operations related to alerts, assets, and sites.

**6 operation(s)**:

- `create_alert()` — Create Alert
- `get_alerts()` — Get Alert List
- `get_assets()` — Get Asset List
- `get_sites_status()` — Get Sites Status
- `update_alert_status()` — Update Alert Status
- `update_asset()` — Update Asset


---

## OT & IoT Security 

### `berryio` v1.0.1 _(installed)_
_BerryIO_

This Connector allows for GPIO status commands to be sent to BerryIO, a controller for Raspberry Pi

**3 operation(s)**:

- `get_gpio()` — Get GPIO Pin Status
- `set_gpio_mode()` — Set GPIO Pin Mode
- `set_gpio_value()` — Set GPIO Pin Value


### `microsoft-defender-for-iot` v1.0.0 _(installed)_
_Microsoft Defender for IoT_

Microsoft Defender for IoT consolidates real-time asset discovery, vulnerability management, and cyberthreat protection for your Internet of Things (IoT) and industrial infrastructure, such as industrial control systems (ICS) and operational technology (OT). This connector facilitates automated interactions, with a Microsoft Defender for IoT server using FortiSOAR™ playbooks to effectively view, analyze, and respond to alerts generated by Defender for IoT

**8 operation(s)**:

- `get_device_vulnerability_report()` — Get Device Vulnerability Information
- `get_mitigation_assessment()` — Get Mitigation Steps
- `get_operational_assessment_report()` — Get Operational Vulnerabilities
- `get_vulnerability_assessment_report()` — Get Security Vulnerabilities
- `list_alerts()` — Get Alert List
- `list_device_cves()` — Get Device CVEs List
- `list_devices()` — Get Device List
- `list_timeline_events()` — Get Timeline Events


---

## Query Service

### `aws-athena` v1.1.0 _(installed)_
_AWS Athena_

This connector allows for the automation of AWS Athena queries

**1 operation(s)**:

- `run_athena_query()` — Run Athena Query


### `microsoft-graph` v2.2.0 _(installed)_
_Microsoft Graph API_

Microsoft Graph API is a powerful and unified programming interface provided by Microsoft that allows developers to access a wide range of data and services from Microsoft 365 and Azure Active Directory (Azure AD). It provides a single endpoint and a consistent set of RESTful web APIs, making it easier for developers to integrate and interact with Microsoft's cloud services and applications.

**16 operation(s)**:

- `add_comment_on_security_alert()` — Add Comment on Security Alert
- `block_new_ips()` — Block New IP Ranges
- `create_ip_range_location()` — Create IP Named Location
- `del_message()` — Delete Message
- `del_message_bulk()` — Delete Message Bulk
- `get_all_named_locations()` — Get All Named Locations
- `get_all_security_alerts()` — Get All Security Alerts
- `get_group_users()` — Get Users Within A Group
- `get_groups()` — Get Groups
- `get_risky_user_details()` — Get Risky User Details
- `get_risky_users_list()` — Get Risky Users List
- `get_security_alert()` — Get Security Alert
- `revoke_user_sessions()` — Revoke User Session
- `search_message()` — Search Message in Users Mailbox
- `unblock_new_ips()` — Unblock IP Ranges
- `update_security_alert()` — Update Security Alert


---

## Security Posture Management

### `aws-security-hub` v1.1.0 _(installed)_
_AWS Security Hub_

AWS Security Hub provides you with a comprehensive view of your security state in AWS and helps you check your environment against security industry standards.

**7 operation(s)**:

- `batch_import_findings()` — Import Findings
- `batch_update_findings()` — Batch Update Findings
- `disable_security_hub()` — Disable Security Hub
- `enable_security_hub()` — Enable Security Hub
- `get_findings()` — Get Findings
- `get_insights()` — Get Insights
- `list_members()` — List Members


### `cisco-sma` v1.1.1 _(installed)_
_Cisco SMA_

The Cisco Content Security Management Appliance (SMA) centralizes management and reporting functions across multiple Cisco email and web security appliances. It simplifies administration and planning, improves compliance monitoring, helps to enable consistent enforcement of policy, and enhances threat protection.

**8 operation(s)**:

- `delete_message()` — Delete Message
- `download_attachment()` — Download Attachment
- `fetch_from_other_quarantine()` — Fetch Emails From Other Quarantine
- `fetch_from_spam_quarantine()` — Fetch Emails From SPAM Quarantine
- `get_message_details()` — Get Tracking Message Details
- `get_quarantine_message_details()` — Get Quarantine Message Details
- `release_emails_from_quarantine()` — Release Emails From Quarantine
- `track_emails()` — Track Emails


### `cymulate-phishing-awareness` v1.0.0 _(installed)_
_Cymulate Phishing Awareness - BAS_

Cymulate's Phishing Awareness campaigns evaluate employees' security awareness levels by simulating phishing attacks.

**8 operation(s)**:

- `create_phishing_awareness_contact_group()` — Create Phishing Awareness Contact Group
- `get_phishing_awareness_assessment_history()` — Get Phishing Awareness Assessment History
- `get_phishing_awareness_assessment_id()` — Get Phishing Awareness assessment IDs
- `get_phishing_awareness_campaign_report_for_specific_assessment()` — Get Phishing Awareness Campaign Report for Specific Assessment
- `get_phishing_awareness_contact_groups()` — Get Phishing Awareness Contact Groups
- `get_phishing_awareness_contacts()` — Get Phishing Awareness Contacts
- `get_phishing_awareness_report()` — Get Phishing Awareness Report
- `get_phishing_awareness_report_for_specific_assessment()` — Get Phishing Awareness Report for Specific Assessment


### `fireeye-cms` v1.0.1 _(installed)_
_FireEye CMS_

FireEye CMS connector perform automated operations such as retrieving a list of all guest image profiles and applications details, add/delete custom IOC feed and retrieving data for alerts,events.

**6 operation(s)**:

- `add_custom_feed()` — Add Custom Feed
- `delete_custom_feeds()` — Delete Custom Feeds
- `get_configurations()` — Get Configurations
- `get_custom_feeds()` — Get Custom Feeds
- `get_events()` — Get Events
- `get_open_alerts()` — Get Open Alerts


### `skybox-security` v1.0.0 _(installed)_
_Skybox Security_

Skybox Security arms security professionals with the broadest platform of solutions for security operations, analytics, and reporting. This connector facilitates automated operations like Lookup IP, get assets

**2 operation(s)**:

- `get_assets_by_names()` — Get Assets
- `lookup_ip_address()` — Lookup IP


### `sophos-central` v4.2.0 _(installed)_
_Sophos Central_

Sophos Central is a unified console for managing your Sophos products Sophos Central lets you administer protection for endpoints, mobile devices, encryption, web, email, servers, etc. This connector facilitates automated operations related to endpoints, email, etc.

**34 operation(s)**:

- `alerts_action()` — Perform Alert Action
- `create_allowed_items()` — Create Allowed Item
- `create_blocked_items()` — Create Blocked Item
- `create_exclusion_scanning()` — Create Exclusion Scanning
- `create_exploit_mitigation_application()` — Create Exploit Mitigation Application
- `delete_allowed_items()` — Delete Allowed Item
- `delete_blocked_items()` — Delete Blocked Item
- `delete_endpoints()` — Delete Endpoint
- `delete_exclusion_scanning()` — Delete Exclusion Scanning
- `delete_exploit_mitigation_application()` — Delete Exploit Mitigation
- `get_alerts()` — Get Alert by ID
- `get_allowed_items()` — Get Allowed Item by ID
- `get_blocked_items()` — Get Blocked Item by ID
- `get_detected_exploits()` — Get Specific Detected Exploit
- `get_endpoint_tamper_protection()` — Get Endpoint Tamper Protection
- `get_endpoints()` — Get Endpoint by ID
- `get_endpoints_isolation()` — Get Endpoint Isolations
- `get_exclusion_scanning()` — Get Exclusion Scanning by ID
- `get_exploit_mitigation_application()` — Get Exploit Mitigation by ID
- `isolate_endpoints()` — Isolate Endpoint
- `list_alerts()` — Get Alert List
- `list_allowed_items()` — Get Allowed Items
- `list_blocked_items()` — Get Blocked Items
- `list_detected_exploits()` — Get Detected Exploits
- `list_endpoints()` — Get Endpoints
- `list_exclusion_scanning()` — Get Exclusion Scanning
- `list_exploit_mitigation_application()` — Get Exploit Mitigation Application
- `scan_endpoints()` — Scan Endpoint
- `search_alerts()` — Search Alerts
- `unisolate_endpoints()` — Unisolate Endpoint
- `update_allowed_items()` — Update Allowed Item
- `update_endpoint_tamper_protection()` — Update Endpoint Tamper Protection
- `update_exclusion_scanning()` — Update Exclusion Scanning
- `update_exploit_mitigation_application()` — Update Exploit Mitigation Application


### `symantec-icdx` v1.0.0 _(installed)_
_Symantec ICDX_

Unifying cloud and on-premises security to provide advanced threat protection and information protection across all endpoints, networks, email, and cloud applications.

**1 operation(s)**:

- `search()` — Search Events


### `symantec-mss` v1.0.0 _(installed)_
_Symantec MSS_

Symantec MSS connector provides actions like, list of incident/tickets, create request, query incident/tickets etc.

**20 operation(s)** (+8 hidden):

- `get_incident_organization()` — Get Organizations and Person List
- `incident_add_attachment()` — Incident Add Attachment
- `incident_get_attachment()` — Get Incident Attachment
- `incident_get_list()` — Get List of Incident
- `incident_query()` — Query Incident
- `ticket_delete_attachments()` — Delete Ticket Attachments
- `ticket_get_attachment_contents()` — Get Ticket Attachment
- `ticket_get_attachment_list()` — Get List of Ticket Attachment
- `ticket_get_list()` — Get Ticket List
- `ticket_query()` — Query Ticket
- `update_incident_workflow()` — Update Incident Workflow
- `user_get_devices()` — Get User Devices


### `trendmicro-apex-central` v1.1.0 _(installed)_
_Trend Micro Apex Central_

Trend Micro Apex Central connector automates to list servers, perform action on agent such as isolate,restore, relocate and uninstall etc.

**13 operation(s)**:

- `add_udso_entries()` — Add UDSO to List
- `create_assessment()` — Create Assessment
- `create_live_investigation()` — Create Live Investigation
- `download_rca_file()` — Download RCA CSV File
- `get_rca_response()` — Get RCA Response
- `get_syslog_data()` — Get Syslog Data
- `get_task_id_analysis_chain()` — Get Task ID of RCA in Analysis Chain
- `get_task_id_table_format()` — Get Task ID of RCA in Table Format
- `list_agent()` — List Security Agents
- `list_investigation_result()` — Get All Investigation Results
- `list_server()` — List Product Server
- `list_udso_entries()` — List UDSO Entries
- `perform_action()` — Perform Action on Security Agent


### `trendmicro-control-manager` v1.0.0 _(installed)_
_Trend Micro Control Manager_

Connector for Trend Micro Control Manager which utilizes isolating and restoring an isolated endpoint.

**2 operation(s)**:

- `isolate_endpoint()` — Isolate Endpoint
- `restore_isolated_endpoint()` — Restore Isolated Endpoint


---

## Source Code Management

### `azure-devops` v2.0.0 _(installed)_
_Azure DevOps_

Azure DevOps is a cloud-based service for managing software development projects. The Azure DevOps FortiSOAR connector integrates with Azure DevOps to automate the management of repositories, pipelines, work items, and more within FortiSOAR, enabling streamlined DevOps workflows and incident response.

**30 operation(s)**:

- `add_pull_request_reviewer()` — Add Pull Request Reviewer
- `create_branch()` — Create Branch
- `create_merge_request()` — Create Merge Request
- `create_new_file_in_repository()` — Create File
- `create_pull_request()` — Create Pull Request
- `create_pull_request_comment()` — Create Pull Request Comment
- `create_repository()` — Create Repository
- `delete_branch()` — Delete Branch
- `delete_existing_file_in_repository()` — Delete File
- `execute_an_api_request()` — Execute an API Request
- `get_commit()` — Get Commit Details
- `get_file_from_repository()` — Get File
- `get_pipeline_run()` — Get Pipeline Run Details
- `get_pull_requests_by_id()` — Get Pull Request Details
- `list_branches()` — Get Branch List
- `list_commits()` — Get Commit List
- `list_pipeline_runs()` — Get Pipeline Run List
- `list_pipelines()` — Get Pipeline List
- `list_projects()` — Get Project List
- `list_pull_request_comment()` — Get Pull Request Comment List
- `list_pull_request_commits()` — Get Pull Request Commit List
- `list_pull_request_reviewers()` — Get Pull Request Reviewer List
- `list_pull_requests()` — Get Pull Request List
- `list_repositories()` — Get Repository List
- `list_users()` — Get User List
- `push_repository()` — Push Changes
- `run_pipeline()` — Run Pipeline
- `update_file_in_repository()` — Update File
- `update_pull_request()` — Update Pull Request
- `update_repository()` — Update Repository


### `bitbucket` v1.0.0 _(installed)_
_Bitbucket_

Bitbucket is a comprehensive platform designed to streamline the software development process. It encompasses all aspects of the development lifecycle, offering seamless integration and efficiency throughout the journey from initial project planning to deployment and beyond. With Bitbucket, teams can seamlessly manage their source code, facilitate collaboration, and ensure the quality and security of their software.

**19 operation(s)**:

- `clone_repository()` — Clone Repository
- `create_pull_request()` — Create Pull Request
- `create_pull_request_comment()` — Create Pull Request Comment
- `create_repository()` — Create Repository
- `create_repository_branch()` — Create Repository Branch
- `create_tag()` — Create Tag
- `create_update_file_contents()` — Create or Update File Contents
- `delete_repository()` — Delete Repository
- `delete_repository_branch()` — Delete Repository Branch
- `find_repository_branches()` — Get Repository Branch List
- `get_file_from_repository()` — Get File Details
- `get_users_with_repository_permission()` — Get Member List of Repository
- `get_web_url()` — Get Server URL
- `list_pull_request()` — Get Pull Request List
- `list_pull_requests_comments()` — Get Pull Request Comments
- `list_tags()` — Get Tag List
- `merge_pull_request()` — Merge Pull Request
- `update_clone_repository()` — Update Remote Repository
- `update_user_repository_permission()` — Update User Repository Permission


### `github` v2.0.0 _(installed)_
_GitHub_

GitHub is a code hosting platform for collaboration and version control. This connector facilitates automated interactions with Github, such as to create and manage repositories, branches, issues, pull requests, and many more.

**42 operation(s)**:

_investigation_
- `add_pr_review(repo_type: select, repo: text, pull_number: integer, [commit_id: text], [body: text], [event: select])` — Add Pull Request Review
- `add_repository_collaborator(repo_type: select, repo: text, username: text, [permission: select])` — Add Repository Collaborator
- `add_reviewers(repo_type: select, repo: text, pull_number: integer, [reviewers: text], [team_reviewers: text])` — Add Reviewers for a Pull Request
- `clone_repository(repo_type: select, name: text, [branch: text], clone_zip: checkbox)` — Clone Repository
- `create_branch(repo_type: select, repo: text, new_branch_name: text, checkout_branch: select)` — Create Branch
- `create_issue(repo_type: select, repo: text, title: text, [body: textarea], [assignees: text], [milestone: text], [labels: text])` — Create Issue
- `create_issue_comment(repo_type: select, repo: text, issue_number: integer, body: richtext)` — Create Issue Comment
- `create_pull_request(repo_type: select, repo: text, head: text, base: text, [title: text], [body: text], [maintainer_can_modify: checkbox], [draft: checkbox])` — Create Pull Request
- `create_release(repo_type: select, repo: text, tag_name: text, [target_commitish: text], [name: text], [body: text], [generate_release_notes: checkbox])` — Create Release
- `create_repository(repo_type: select, name: text, [description: text], [homepage: text], [private: checkbox], [has_issues: checkbox], [has_projects: checkbox], [has_wiki: checkbox], [is_template: checkbox], [other_fields: json])` — Create Repository
- `create_repository_using_template(template_owner: text, template_repo: text, name: text, [owner: text], [description: text], [include_all_branches: checkbox], [private: checkbox])` — Create Repository Using Template
- `create_update_file_contents(repo_type: select, name: text, path: text, message: text, content: text, [branch: text], [sha: text])` — Create or Update File Contents
- `delete_branch(repo_type: select, repo: text, branch_name: text)` — Delete Branch
- `delete_file_from_repository(repo_type: select, name: text, path: text, message: text, sha: text, [branch: text])` — Delete File
- `delete_repository(repo_type: select, repo: text)` — Delete Repository
- `fetch_upstream(repo_type: select, repo: text, branch: text)` — Fetch Upstream
- `fork_organization_repository(repo_type: select, repo: text, [organization: text], [name: text], [default_branch_only: checkbox])` — Fork Organization Repository
- `get_branch_revision(repo_type: select, repo: text, base: text)` — Get Branch Revision
- `get_file_from_repository(repo_type: select, name: text, path: text, [branch: text], [decode_content: checkbox])` — Get File
- `get_web_url()` — Get Server URL
- `list_authenticated_user_repositories([affiliation: text], [visibility: select], [type: select], [sort: select], [direction: select], [since: datetime], [before: datetime], [per_page: integer], [page: integer])` — List Authenticated User Repositories
- `list_branches(repo_type: select, repo: text, [protected: checkbox], [per_page: integer], [page: integer])` — List Branches
- `list_fork_repositories(repo_type: select, repo: text, sort: select, [per_page: integer], [page: integer])` — List Fork Repositories
- `list_organization_repositories(org: text, type: select, sort: select, direction: select, [per_page: integer], [page: integer])` — List Organization Repositories
- `list_pr_reviews(repo_type: select, repo: text, pull_number: integer, [per_page: integer], [page: integer])` — List Pull Request Reviews
- `list_pull_request(repo_type: select, repo: text, [pull_number: text], [state: select], [head: text], [base: text], [sort: select], [direction: select], [per_page: integer], [page: integer])` — List Pull Request
- `list_releases(repo_type: select, repo: text, [per_page: integer], [page: integer])` — List Releases
- `list_repository_collaborator(repo_type: select, repo: text, [affiliation: select], [permission: select], [per_page: integer], [page: integer])` — List Repository Collaborator
- `list_repository_issue(repo_type: select, repo: text, [milestone: text], [state: select], [assignee: text], [creator: text], [mentioned: text], [labels: text], [sort: select], [direction: select], [since: datetime], [per_page: integer], [page: integer])` — List Repository Issue
- `list_review_comments(repo_type: select, repo: text, pull_number: integer, [sort: select], [direction: select])` — List Review Comments on a Pull Request
- `list_stargazers(repo_type: select, repo: text, [per_page: integer], [page: integer])` — List Stargazers
- `list_user_repositories(username: text, type: select, sort: select, direction: select, [per_page: integer], [page: integer])` — List User Repositories
- `list_watchers(repo_type: select, repo: text, [per_page: integer], [page: integer])` — List Watchers
- `merge_branch(repo_type: select, repo: text, base: text, head: text, [commit_message: text])` — Merge Branch
- `merge_pull_request(repo_type: select, repo: text, pull_number: integer, [commit_title: text], [commit_message: text], [sha: text], [merge_method: select])` — Merge Pull Request
- `push_repository(repo_type: select, name: text, clone_path: text, branch: text, commit_message: text, [commit_description: textarea])` — Push Changes
- `search_code(query: text, [per_page: integer], [page: integer])` — Search Code
- `set_repo_subscription(repo_type: select, repo: text, [subscribed: checkbox], [ignored: checkbox])` — Set Repository Subscription
- `star_repository(repo_type: select, repo: text)` — Star Repository
- `update_clone_repository(file_iri: text, clone_path: text)` — Update Remote Repository
- `update_issue(repo_type: select, repo: text, issue_number: integer, [title: text], [body: textarea], [state: select], [state_reason: select], [milestone: text], [labels: text], [assignees: text])` — Update Issue
- `update_repository(repo_type: select, repo: text, name: text, [description: text], [homepage: text], [private: checkbox], [has_issues: checkbox], [has_projects: checkbox], [has_wiki: checkbox], [other_fields: json])` — Update Repository


---

## Storage

### `awss3` v3.0.2 _(installed)_
_AWS S3_

To provide automation for AWS S3 operations, like creation and modification of S3 buckets and related contents.

**14 operation(s)**:

- `delete_bucket()` — Delete Bucket
- `delete_object()` — Delete Bucket Object
- `delete_tag()` — Delete Tag
- `download_file()` — Download File
- `get_bucket_policy()` — Get Bucket Policy
- `get_object_details()` — Get Object
- `list_buckets()` — List Buckets
- `list_objects()` — List Objects
- `modify_bucket()` — Modify Bucket
- `modify_object()` — Modify Object
- `new_bucket()` — Create New Bucket
- `put_bucket_policy()` — Create Bucket Policy
- `replace_bucket_policy()` — Replace Bucket Policy
- `upload_file()` — Upload File into Bucket


### `google-cloud-storage` v1.0.0 _(installed)_
_Google Cloud Storage_

Google Cloud Storage is a RESTful online file storage web service for storing and accessing data on Google Cloud Platform infrastructure. This connector facilitates the automated operations related to bucket, bucket objects and bucket policies.

**14 operation(s)**:

- `create_bucket()` — Create Bucket
- `create_bucket_object_policy()` — Create Bucket Object Policy
- `create_bucket_policy()` — Create Bucket Policy
- `delete_bucket()` — Delete Bucket
- `delete_bucket_object_policy()` — Delete Bucket Object Policy
- `delete_bucket_policy()` — Delete Bucket Policy
- `get_bucket_details()` — Get Bucket Details
- `get_bucket_object_policy_details()` — Get Bucket Policy Object Details
- `get_bucket_policy_details()` — Get Bucket Policy Details
- `get_buckets_list()` — Get Buckets List
- `get_buckets_list_object_policy()` — Get Bucket's List Object Policy
- `get_buckets_list_policy()` — Get Bucket's List Policy
- `update_bucket_object_policy()` — Update Bucket Object Policy
- `update_bucket_policy()` — Update Bucket Policy


### `pure-storage-flasharray` v1.0.0 _(installed)_
_Pure Storage FlashArray_

Pure Storage is a leading provider of enterprise data storage solutions. It is specialize in all-flash storage arrays, delivering high-performance, reliable, and scalable storage solutions for businesses. With Pure Storage FlashArray, organizations can accelerate applications, improve productivity, and make data-driven decisions. Experience the power of next-generation storage technology with Pure Storage FlashArray.

**9 operation(s)**:

- `get_alerts()` — Get Alert List
- `get_arrays()` — Get Array List
- `get_audits()` — Get Audit List
- `get_controllers()` — Get Controller List
- `get_directories()` — Get Directory List
- `get_drives()` — Get Drive List
- `get_protection_groups()` — Get Protection Group List
- `get_sessions()` — Get Session List
- `get_volumes()` — Get Volume List


### `veeam-backup-replication` v1.0.0 _(installed)_
_Veeam Backup & Replication_

Veeam Backup & Replication is a data protection and disaster recovery solution that enables backup, recovery, and replication for virtual, physical, and cloud-based workloads.

**16 operation(s)**:

- `create_malware_event()` — Create Malware Event
- `execute_an_api_request()` — Execute an API Request
- `get_backup_list()` — Get Backup List
- `get_malware_event_list()` — Get Malware Event List
- `get_managed_server_list()` — Get Managed Server List
- `get_microsoft_entra_id_tenant_list()` — Get Microsoft Entra ID Tenant List
- `get_repository_state_list()` — Get Repository State List
- `get_restore_point_list()` — Get Restore Point List
- `get_security_compliance_analyzer_results()` — Get Security & Compliance Analyzer Results
- `get_server_list()` — Get Server List
- `get_unstructured_data_server_list()` — Get Unstructured Data Server List
- `scan_backup()` — Scan Backups with Antivirus or YARA Rules
- `start_configuration_backup()` — Start Configuration Backup
- `start_instant_recovery()` — Start Instant Recovery
- `start_quick_backup()` — Start Quick Backup
- `start_security_compliance_analyzer()` — Start Security & Compliance Analyzer


---

## System Monitoring

### `cyops-system-monitoring` v1.6.0 _(installed, system)_
_System Monitoring_

CPU, Memory and Disk Utilization Monitoring for FortiSOAR

**4 operation(s)**:

_investigation_
- `cpu_percent()` — CPU Utilization
- `disk_utilization()` — Disk Utilization
- `service_status()` — Service Status
- `virtual_memory()` — Virtual Memory Utilization


---

## Task Management

### `trello` v1.0.0 _(installed)_
_Trello_

Trello is a collaboration tool that organizes your projects into boards. Trello tells you what's being worked on, who's working on what, and where something is in a process.

**8 operation(s)**:

- `create_card()` — Create a new Card
- `create_label()` — Create a Label
- `delete_card()` — Delete a Card
- `get_board()` — Get a Board
- `get_card()` — Get a Card
- `get_label()` — Get a Label
- `get_list()` — Get a List
- `update_card()` — Update a Card


---

## Threat Detection

### `alphamountain` v1.0.0 _(installed)_
_alphaMountain_

alphaMountain Threat Response integrates investigations informed by reputation scores of target hosts, domains, and IP addresses. It fetches indicators with risk scores and relevant content categorization.

**4 operation(s)**:

- `get_domain_popularity()` — Get Popularity of Domain
- `get_threat_score()` — Get Threat Score
- `get_url_categories()` — Get URL Categories
- `identify_impersonation_detection()` — Get Likely Impersonated Domain for a URL


### `aws-guardduty` v1.0.1 _(installed)_
_AWS GuardDuty_

Amazon GuardDuty is a threat detection service that continuously monitors for malicious activity and unauthorized behavior to protect your AWS accounts, workloads, and data stored in Amazon S3

**18 operation(s)**:

- `create_detector()` — Create Detector
- `create_ip_set()` — Create IP Set
- `create_threat_intel_set()` — Create Threat Intel Set
- `delete_detector()` — Delete Detector
- `delete_ip_set()` — Delete IP Set
- `delete_threat_intel_set()` — Delete Threat Intel Set
- `get_all_detectors()` — Get Detector ID
- `get_all_findings()` — Get All Findings
- `get_all_ip_sets()` — Get All IP Sets
- `get_all_threat_intel_sets()` — Get All Threat Intel Sets
- `get_detector()` — Get Detector Details
- `get_findings()` — Get Findings
- `get_findings_statistics()` — Get Findings Statistics
- `get_ip_set_details()` — Get IP Set
- `get_threat_intel_set_details()` — Get Threat Intel Set Details
- `update_detector()` — Update Detector
- `update_ip_set()` — Update IP Set
- `update_threat_intel_set()` — Update Threat Intel Set


### `lumu` v1.0.0 _(installed)_
_LUMU_

LUMU provides Real-time detection, analysis, and response to network threats.

**5 operation(s)**:

- `close_incident()` — Close Incident
- `get_incident_by_uuid()` — Get Incident by UUID
- `get_incident_context()` — Get Incident Context
- `get_incident_endpoints()` — Get Incident Endpoints
- `get_incidents()` — Get Incidents


### `microsoft-advanced-threat-analytics` v1.0.0 _(installed)_
_Microsoft Advanced Threat Analytics_

Microsoft Advanced Threat Analytics (ATA) is an on-premises platform that helps protect your enterprise from multiple types of advanced targeted cyber attacks and insider threats.

**4 operation(s)**:

- `get_entity()` — Get Entity
- `get_monitoring_alerts_list()` — Get Monitoring Alerts List
- `get_suspicious_activities_list()` — Get Suspicious Activities List
- `set_suspicious_activity_status()` — Set Suspicious Activity Status


### `robtex` v1.0.0 _(installed)_
_Robtex_

Robtex uses various sources to gather public information about IP numbers, domain names, host names, autonomous systems, routes, etc., doing data forensics, investigating competitors, tracking spammers, hackers, or hackers or a virus.This connector facilitates automated operations to pull forward and reverse of an IP number and an AS number together with GEO-location data and network data.

**2 operation(s)**:

- `get_autonomous_system_query_details()` — Get Autonomous System Query Details
- `get_ip_query_details()` — Get IP Query Details


### `sap-etd-cloud` v1.0.0 _(installed)_
_SAP Enterprise Threat Detection Cloud_

SAP Enterprise Threat Detection (ETD), Cloud Edition helps you to identify the real attacks as they are happening and analyze the threats quickly enough to neutralize them before serious damage occurs. SAP Enterprise Threat Detection Cloud Edition connector performs action like get and ingest Events, Alerts and Investigations.

**3 operation(s)**:

- `get_alert_by_id()` — Get Alert Details
- `get_alerts()` — Get Alerts
- `get_investigations()` — Get Investigations


### `taegis-xdr` v1.2.0 _(installed)_
_Taegis XDR_

SecureWorks Taegis™ XDR offers superior detection, unmatched response and an open platform built from the ground up to integrate market-leading technologies and deliver the highest ROI.

**16 operation(s)**:

- `add_alerts_to_investigation()` — Add Alerts to Investigation
- `add_events_to_investigation()` — Add Events to Investigation
- `create_comment()` — Create Comment
- `create_investigation()` — Create Investigation
- `execute_playbook()` — Execute Playbook
- `get_alerts()` — Get Alerts
- `get_assets()` — Get Assets
- `get_endpoint()` — Get Endpoint
- `get_investigations()` — Get Investigations
- `get_investigations_alerts()` — Get Investigations Alerts
- `get_playbook_execution()` — Get Playbook Execution
- `get_user_by_id()` — Get User by ID
- `isolate_assets()` — Isolate Assets
- `unarchive_investigation()` — Unarchive Investigation
- `update_alert_status()` — Update Alert Status
- `update_investigation()` — Update Investigation


---

## Threat Hunting and Search

### `infocyte` v1.1.0 _(installed)_
_Infocyte_

Infocyte connector provides automated actions to get hosts details, run a scan on hosts and get a scan result

**16 operation(s)**:

- `get_accounts()` — Get Accounts
- `get_address()` — Get Host Addresses
- `get_artifacts()` — Get Artifacts
- `get_artifacts_details()` — Get Artifact Details
- `get_artifacts_for_hosts()` — Get Hosts Artifacts
- `get_drivers()` — Get Drivers
- `get_drivers_details()` — Get Driver Details
- `get_modules()` — Get Modules
- `get_modules_details()` — Get Module Details
- `get_processes()` — Get Processes
- `get_processes_details()` — Get Process Details
- `get_scan()` — Get Scans
- `get_scan_status()` — Get Scan Status By User Task ID
- `get_scans_with_target()` — Get Scans Of Target
- `get_target_group()` — Get Target Group Details
- `run_scan()` — Run Scan


### `mobile-security-framework` v1.0.0 _(installed)_
_Mobile Security Framework_

Mobile Security Framework (MobSF) is an automated, all-in-one mobile application (Android/iOS/Windows) pen-testing, malware analysis and security assessment framework capable of performing static and dynamic analysis. MobSF support mobile app binaries (APK, XAPK, IPA & APPX) along with zipped source code and provides REST APIs for seamless integration with your CI/CD or DevSecOps pipeline.

**13 operation(s)** (+1 hidden):

- `compare_scan_results()` — Compare Scan Results
- `delete_scan()` — Delete Scan Result
- `delete_suppressions()` — Delete Suppressions
- `display_recent_scans()` — List Recent Scans
- `generate_json_report()` — Generate JSON Report
- `generate_pdf_report()` — Generate PDF Report
- `get_app_scorecard()` — Get App Scorecard
- `scan_file()` — Scan File
- `suppress_by_rule()` — Suppress by Rule
- `upload_file()` — Upload File
- `view_source_files()` — View Source Files
- `view_suppressions()` — List Suppressions


---

## Threat Intelligence

### `abuseipdb` v2.0.0 _(installed)_
_AbuseIPDB_

AbuseIPDB Connector helps to report and identify IP addresses that have been associated with malicious activity online

**3 operation(s)**:

- `get_ip_blacklist()` — Get IP Blacklist
- `ip_lookup()` — IP Lookup
- `report_ip()` — Report IP


### `alienvault-otx` v1.0.3 _(installed)_
_AlienVault-OTX_

AlienVault-OTX is an open source of Indicators of Compromise (IOCs) supported by the community.This connector provides actions Get IP Reputation, Create Pulse, Get Domain Reputation, etc

**16 operation(s)**:

_investigation_
- `create_pulse(pulse_name: text, indicator_list: json, [pulse_des: text], [tag: text], [references: text], [public: checkbox])` — Create Pulse
- `get_all_indicators([indicator_type: multiselect], [limit: integer], [page: integer], [from_time: datetime], [export_json: checkbox])` — Get All Indicators
- `get_domain_reputation(domain: text, [section: select])` — Get Domain Reputation
- `get_file_reputation(file_hash: text)` — Get File Reputation
- `get_hostname_reputation(hostname: text, [section: select])` — Get Hostname Reputation
- `get_ip_reputation(indicator_type: select, ip_address: text)` — Get IP Reputation
- `get_pulse_details(pulse_id: text)` — Get Pulse Details
- `get_pulse_indicators(pulse_id: text, [include_inactive: checkbox], [limit: integer], [page: integer])` — Get Pulse Indicators
- `get_shared_indicator_pulses(pulse_id: text, [page_number: integer])` — Get Related Pulses
- `get_subscribed_pulses([limit: integer], [page: integer], [from_time: datetime])` — Get Subscribed Pulses
- `get_url_reputation(url: text)` — Get URL Reputation
- `run_query(query_url: text)` — Run Query
- `search_pulses(user_text: text, [limit: integer], [page: integer])` — Search Pulses
- `subscribe_pulse(pulse_id: text)` — Subscribe to Pulse
- `unsubscribe_pulse(pulse_id: text)` — Unsubscribe from Pulse
- `user_action(username: text, user_action: select)` — User Actions


### `alienvault-usm-central` v1.1.0 _(installed)_
_Alienvault USM Central_

Alienvault USM Central Connector can be used to automate actions like search alarms, get alarm details, search assets and get deployments

**4 operation(s)**:

- `get_alarm_details()` — Get Alarm Details
- `get_deployments()` — Get Deployments
- `search_alarms()` — Search Alarms
- `search_assets()` — Search Assets


### `alphamountain-feed` v1.0.0 _(installed)_
_alphaMountain Feed_

The AlphaMountain feed connector facilitates seamless integration with AlphaMountain's data sources, providing access to real-time and historical data on domain popularity, cybersecurity insights, risk scores and relevant content categorization and more.

**2 operation(s)** (+1 hidden):

- `get_indicators()` — Get Indicators


### `anomali-enterprise` v1.0.0 _(installed)_
_Anomali Enterprise_

Anomali Enterprise is a threat and breach analytics platform that applies correlation rules and advanced security analysis to cross-correlate data from SIEMs (ArcSight ESM and Splunk) and other event sources deployed in your network to threat intelligence available from ThreatStream. This connector facilitates automated operations to search all Anomali data, Run retrospective search, Download search result etc.

**6 operation(s)**:

- `download_search_results()` — Download the Search Results
- `get_search_status()` — Get Retrospective Search Status
- `identify_dga_domain()` — Identify DGA Domains
- `run_retrospective_search()` —  Run a Retrospective/Forensic Search
- `search_in_anomali()` — Search in Anomali Enterprise Data
- `upload_asset_information()` — Upload Asset Information


### `anomali-limo-threat-intel-feed` v2.0.0 _(installed)_
_Anomali Limo Threat Intel Feed_

Anomali Limo is a preconfigured set of intelligence feeds that STAXX users can access immediately upon download, and which offers indicators and insights spanning threat categories you need to secure your business. This connector facilitates automated interactions, such as returning the list of public, private, and shared collection resources to which the user has access, returning general information for a specific object of a specific collection, etc. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**6 operation(s)** (+1 hidden):

- `get_api_root_information()` — Get API Root Information
- `get_collections()` — Get Collections
- `get_manifest_by_collection_id()` — Get Manifest By Collection ID
- `get_objects_by_collection_id()` — Get Objects By Collection ID
- `get_objects_by_object_id()` — Get Object By Object ID


### `anomali-staxx` v1.0.0 _(installed)_
_Anomali STAXX_

Anomali STAXX gives you an easy way to access any STIX/TAXII feed. This connector facilitates automated operations like import indicators and get indicators.

**2 operation(s)**:

- `get_indicators()` — Get Indicators
- `import_indicators()` — Import Indicators


### `apivoid` v2.0.0 _(installed)_
_APIVoid_

Apivoid connector provides several threat intelligence services ranging from IP/URL/Domain reputation to domain age and website screenshots

**12 operation(s)**:

- `dnspropagation()` — Get DNS Propagation
- `domainage()` — Get Domain Age
- `domainbl()` — Get Domain Reputation
- `emailverify()` — Get Email Reputation
- `execute_an_api_call()` — Execute an API Request
- `iprep()` — Get IP Reputation
- `parkeddomain()` — Get Domain Parked Status
- `screenshot()` — Get URL Screenshot
- `sitetrust()` — Get Domain Trustworthiness
- `sslinfo()` — Get SSL Info
- `urlrep()` — Get URL Reputation
- `urlstatus()` — Get URL Status


### `arcanna-ai` v1.2.0 _(installed)_
_Arcanna.ai_

Arcanna.ai is a platform for delivering decision intelligence. It augments Security Operation Center analysts in dealing with incoming threats by increasing analyst efficiency in decision-making. More information is available at https://arcanna.ai

**10 operation(s)**:

- `export_event()` — Get Event
- `get_arcanna_response()` — Get Decision on Event
- `get_decision_set()` — Get Job Decision Set
- `get_job_by_name()` — Get Job By Name
- `get_jobs()` — Get Jobs
- `send_feedback()` — Send Feedback
- `send_to_arcanna()` — Send Event
- `start_job()` — Start Job
- `stop_job()` — Stop Job
- `trigger_training()` — Trigger Job Training


### `aws-feed` v1.0.0 _(installed)_
_AWS Feed_

Amazon Web Services (AWS) publishes its current IP address ranges in JSON format. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `bambenek-feed` v1.0.0 _(installed)_
_Bambenek Feed_

Bambenek Consulting is an IT consulting firm focused on cybersecurity and cybercrime. This connector facilitates automated operations related to fetching the list of IP addresses/domains of feed families and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `fetch_indicators()` — Fetch Indicators


### `barracuda-reputation-block-list` v1.0.0 _(installed)_
_Barracuda Reputation Block List_

Barracuda Reputation System is a real-time database of IP addresses that have a poor reputation for sending valid emails. Barracuda Central maintains and manually verifies all IP addresses marked as "poor" on the Barracuda Reputation System.

**1 operation(s)**:

- `get_ip_reputation()` — Get IP Reputation


### `binaryedge` v1.0.0 _(installed)_
_BinaryEdge_

Binaryedge helps to automatically scan the entire public internet, create real-time threat intelligence feeds or security reports that show the exposure of what is connected to the internet.

**5 operation(s)**:

- `get_dns_details()` — Get DNS Details
- `get_host_details()` — Get Host Details
- `get_ip_risk_score_details()` — Get IP Risk Score Details
- `get_list_of_affect_cve_details()` — Get CVEs List
- `get_subdomain_details()` — Get Subdomain Details


### `blockade-io` v1.0.0 _(installed)_
_Blockade.io_

Blockade brings antivirus-like capabilities to users who run the Chrome browser. This connector facilitates automated actions like Get Indicators and Add Indicators

**2 operation(s)**:

- `add_indicators()` — Add MD5 Hashed Indicators
- `get_indicators()` — Get Indicators


### `blocklist_de-feed` v1.0.0 _(installed)_
_Blocklist.de Feed_

Blocklist.de is a free and voluntary service provided by a Fraud/Abuse-specialist, whose servers are often attacked via SSH-, Mail-Login-, FTP-, Webserver- and other services. This connector facilitates automated operations related to fetching the list of blocklisted IP addresses of services and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

- `fetch_indicators()` — Fetch Indicators
- `get_ips_by_service()` — Fetch All Blocklist IPs


### `bluvector` v1.0.0 _(installed)_
_BluVector_

BluVector Connector is network security tool responding to the world's most sophisticated threats in real time

**2 operation(s)**:

- `get_all_events()` — Get All Events
- `get_event_information()` — Get Complete Event Information


### `botvrij-misp-osint-feed` v1.0.0 _(installed)_
_Botvrij.eu MISP OSINT Feed_

Botvrij.eu MISP OSINT Feed Integration.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

- `get_collections()` — Get Collections
- `get_objects_by_collection_id()` — Get Objects By Collection ID


### `brute-force-blocker-feed` v1.0.0 _(installed)_
_BruteForceBlocker Feed_

BruteForceBlocker Feed it's main purpose is to block SSH bruteforce attacks via firewall.This connector facilitates automated operations related to fetching the list of IPs blocklist.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `fetch_indicators()` — Fetch Indicators


### `check-phish` v1.0.0 _(installed)_
_Check Phish_

Check Phish is free scanner to detect phishing & fraudulent sites in real-time. This connector facilitates automated interactions, such as retrieving information for the specific URL from Check Phish.

**1 operation(s)**:

- `get_url_info()` — Get URL Information


### `cins-army-feed` v1.0.0 _(installed)_
_CINS Army Feed_

CINS Army List is a subset of the CINS Active Threat Intelligence ruleset provided to our Sentinel IPS customers, and consists of IP addresses. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `cisco-talos-feed` v1.0.0 _(installed)_
_Cisco Talos Feed_

Cisco Talos Reputation Center provides access to expansive threat data and related information. This connector facilitates automated operations related to fetching the list of blacklisted IP addresses and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `fetch_indicators()` — Fetch Indicators


### `cisco-talos-threat-intelligence` v1.0.0 _(installed)_
_Cisco Talos Threat Intelligence_

Talos Threat Intelligence connector enables seamless integration with Cisco Talos Threat Intelligence using CIsco SecureX APIs to retrieve reputation data for IPs, domains, URLs, and file hashes. This helps security teams automate threat intelligence gathering and enhance incident response workflows.

**4 operation(s)**:

- `get_domain_reputation()` — Get Domain Reputation
- `get_file_hash_reputation()` — Get File Hash Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputation()` — Get URL Reputation


### `cloudflare` v1.0.0 _(installed)_
_Cloudflare_

Cloudflare helps to automatically scan the entire public internet,  including DDoS protection, web application firewall, bot management, encryption, DNS security, access control, and rate limiting, to safeguard websites and online applications from various cyber threats.

**5 operation(s)**:

- `block_ip()` — Block IP
- `get_firewall_rule_set()` — Get Firewall Rule Sets
- `get_firewall_rules()` — Get Firewall Rules
- `get_rule_id_by_rule_name()` — Get Rule ID By Rule Name
- `unblock_ip()` — Unblock IP


### `code42` v1.0.0 _(installed)_
_Code42_

Code42 use to identify potential data exfiltration from insider threats while speeding investigation and response by providing fast access to file events and metadata across physical and cloud environments. This connector facilitates the automated operations related to alerts, high risk employee, departing employee, or legal hold matter.

**11 operation(s)**:

- `add_user_to_high_risk_employee()` — Add User to High Risk Employee
- `add_user_to_legal_hold_matter()` — Add User to Legal Hold Matter
- `download_file_from_code42()` — Download File from Code42
- `get_alert_details()` — Get Alert Details
- `get_alerts()` — Get Alerts
- `get_all_departing_employees()` — Get All Departing Employees
- `get_all_high_risk_employees()` — Get All High Risk Employees
- `get_users()` — Get All Users
- `remove_user_from_high_risk_employee()` — Remove User from High Risk Employee
- `remove_user_from_legal_hold_matter()` — Remove User from Legal Hold Matter
- `resolve_alerts()` — Resolve Alerts


### `cofense-triage` v2.0.0 _(installed)_
_Cofense Triage_

Cofense Triage is a phishing response workbench that allows analysts to automate and respond to phishing threats.

**13 operation(s)**:

- `download_attachment()` — Download Attachment
- `download_report()` — Download Report
- `get_attachment_details()` — Get Attachment Details
- `get_cluster_details()` — Get Cluster Details
- `get_clusters()` — Get Clusters
- `get_domain_details()` — Get Domain Details
- `get_hostname_details()` — Get Hostname Details
- `get_inbox_reports()` — Get Inbox Reports
- `get_report_details()` — Get Report Details
- `get_report_reporters_details()` — Get Report Reporters Details
- `get_reports()` — Get Reports
- `get_triage_threat_indicators()` — Get Triage Threat Indicators
- `get_url_details()` — Get URL Details


### `criminal-ip` v1.0.0 _(installed)_
_Criminal IP_

Criminal IP provides cyber threat intelligence search engine through which you can scan IP, domain, urls.

**3 operation(s)**:

- `get_domain_reputation()` — Get Domain Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputation()` — Get URL Reputation


### `crits` v1.0.0 _(installed)_
_CRITs_

Collaborative Research Into Threats (CRITs) is an open source malware and threat repository

**4 operation(s)**:

- `create_resource()` — Create Resource
- `get_resource()` — Get Resource Details
- `run_query()` — Run Query
- `update_resource()` — Update Resource


### `crowdsec-cyber-threat-intelligence` v1.0.0 _(installed)_
_CrowdSec Cyber Threat Intelligence_

CrowdSec Cyber Threat Intelligence & Service APIs provide a unified, real-time threat intelligence and automation platform that enables organizations to detect, enrich, and respond to cyber threats at scale.

**26 operation(s)**:

- `add_ips_to_blocklist()` — Add IPs to Blocklist
- `add_items_to_allowlist()` — Add IPs to Allowlist
- `batch_get_ip_reputation()` — Batch Get IP Reputation
- `bulk_overwrite_blocklist_ips()` — Bulk Overwrite Blocklist IPs
- `create_allowlist()` — Create New Allowlist
- `create_blocklist()` — Create New Blocklist
- `create_integration()` — Create Integration
- `delete_allowlist()` — Delete Allowlist
- `delete_allowlist_item()` — Delete Item from Allowlist
- `delete_blocklist()` — Delete Blocklist
- `delete_integration()` — Delete Integration
- `delete_ips_from_blocklist()` — Delete IPs from Blocklist
- `get_allowlist_items()` — Get Items in Allowlist
- `get_blocklist()` — Get Specific Blocklist
- `get_blocklist_ips()` — Get Blocklist IPs
- `get_integration()` — Get Integration
- `get_ip_reputation()` — Get IP Reputation
- `get_malevolent_ips()` — Get Fire IPs
- `get_specific_allowlist_item()` — Get Specific Allowlist Item
- `list_allowlists()` — List All Allowlists
- `list_blocklists()` — List All Blocklists
- `list_integrations()` — List Integrations
- `search_ip_reputation()` — Search IP Reputation
- `update_allowlist()` — Update Allowlist
- `update_blocklist()` — Update Blocklist
- `update_integration()` — Update Integration


### `crowdstrike-falcon-intelligence` v1.1.0 _(installed)_
_CrowdStrike Falcon Intelligence_

CrowdStrike Falcon Intelligence service helps organizations by delivering relevant, timely and actionable threat intelligence to defend from bad actors. This connector which facilitates automated way to fetch IP reputation, domain reputation, file reputation, CrowdStrike actors, CrowdStrike indicators and CrowdStrike reports.

**7 operation(s)**:

- `get_cs_actors()` — Get CS Actors
- `get_cs_indicators()` — Get CS Indicators
- `get_cs_reports()` — Get CS Reports
- `get_domain_reputation()` — Get Domain Reputation
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputation()` — Get URL Reputation


### `crowdstrike-intel-indicators` v1.0.1 _(installed)_
_CrowdStrike Intel Indicators_

CrowdStrike Intel Indicator retrieve Indicators data. This connector facilitates automated operations related to fetching the list indicators and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

- `download_indicators()` — Download Indicators
- `fetch_indicators()` — Fetch Indicators


### `ctm360-cyberblindspot` v1.0.0 _(installed)_
_CTM360 CyberBlindspot_

CyberBlindspot is CTM360's Digital Risk Protection platform which combines surface, deep, and dark web monitoring, including brand protection, anti-phishing, and takedowns. This connector allows you to ingest the details from the platform and take response actions.

**8 operation(s)**:

- `add_comment()` — Add Comment
- `close_incident()` — Close Incident
- `get_breached_credentials()` — Get Breached Credentials
- `get_card_leaks()` — Get Card Leaks
- `get_domain_protection()` — Get Domain Protection
- `get_incidents()` — Get Incidents
- `get_malware_logs()` — Get Malware Logs
- `request_takedown()` — Request Takedown


### `ctm360-cyna` v1.0.0 _(installed)_
_CTM360 CYNA_

This connector allows FortiSOAR to pull cyber news from the CTM360 platform to keep security teams informed of the latest threat intelligence.

**1 operation(s)**:

- `get_cyber_news()` — Get Cyber News


### `ctm360-hackerview` v1.0.0 _(installed)_
_CTM360 HackerView_

HackerView is CTM360’s External Attack Surface Management platform, offering automated asset discovery, issue identification, security ratings, and third-party risk management. This collector lets you pull the issues and assets found on attack surface.

**5 operation(s)**:

- `get_domains()` — Get Domains
- `get_hosts()` — Get Hosts
- `get_ip_addresses()` — Get IP Addresses
- `get_issues()` — Get Issues
- `get_resolved_issues()` — Get Resolved Issues


### `cyber-triage` v1.0.0 _(installed)_
_Cyber Triage_

Provide investigative action to scan an endpoint using Cyber Triage

**1 operation(s)**:

- `scan_endpoint()` — Scan Endpoint


### `cybereason-threat-intel` v1.0.0 _(installed)_
_Cybereason Threat Intel_

Access the Cybereason global threat intelligence database on file hashes, IP addresses, and domains.

**3 operation(s)**:

- `domain_batch()` — Get Domain Reputation
- `file_batch()` — Get File Reputation
- `ip_batch()` — Get IP Reputation


### `cyberint` v1.1.0 _(installed)_
_Cyberint_

Cyberint provides Intelligence-Driven Digital Risk Protection.

**11 operation(s)**:

- `execute_an_api_call()` — Execute an API Request
- `fetch_vulnerabilities()` — Fetch Vulnerabilities
- `get_alert_analysis_report()` — Get Alert Analysis Report
- `get_alert_attachment()` — Get Alert Attachment
- `get_alerts()` — Get Alerts
- `get_domain_reputation()` — Get Domain Reputation
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputation()` — Get URL Reputation
- `get_vulnerability_details_by_cve_id()` — Get Vulnerability Details by CVE ID
- `update_alerts_status()` — Update Alerts Status


### `cybersixgill` v1.0.0 _(installed)_
_Cybersixgill_

Cybersixgill captures, processes and alerts teams to emerging threats, TTPs, IOCs and their exposure to risk as it surfaces on the clear, deep and dark web. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

- `get_dark_feed()` — Get Dark Feed
- `get_ioc_dark_feed()` — Get IOC Dark Feed


### `cyble-vision` v2.0.0 _(installed)_
_Cyble Vision_

Cyble Threat Intel that enables users to access and enrich Indicators of Compromise (IOCs) from Cyble's TAXII Feed service within their environment.

**8 operation(s)**:

- `add_comment_to_alert()` — Add Comment to Alert
- `fetch_alerts()` — Fetch Alerts
- `fetch_companies()` — Fetch All Users for a Company
- `fetch_cve_details()` — Fetch CVE Details
- `fetch_indicators()` — Fetch Indicators
- `fetch_ip_details()` — Fetch IP Details
- `get_advisory_details()` — Get Advisory Details
- `list_advisories()` — List Advisories


### `cymon` v1.0.0 _(installed)_
_Cymon_

Cymon is the largest open tracker of malware, phishing, botnets, spam, and more. This connector pulls information about Domains, IP addresses, or file hashes from the Cymon v1 API

**3 operation(s)**:

- `lookup_domain()` — Look Up Domain
- `lookup_hash()` — Lookup File Hash
- `lookup_ip()` — IP Address Lookup


### `cyren` v1.0.0 _(installed)_
_Cyren_

Cyren is leading a revolution in internet security by utilizing extensive cloud intelligence to provide the fastest protection available. This connector sends the URL Submitted by the End User to Cyren for web threats like phishing and malware.

**1 operation(s)**:

- `get_url_lookup()` — Get URL Lookup


### `cyware` v1.0.0 _(installed)_
_Cyware_

Perform actions like list reported incidents, get incident details from Cyware

**15 operation(s)**:

- `get_alert_categories()` — Get Alert Categories
- `get_executive_protection()` — Get Executive Protection Details
- `get_incident_detail()` — Get Incident Details
- `get_recipient_groups()` — Get Recipient Groups
- `get_user_by_email()` — Get User by Email
- `get_user_cyware_index()` — Get User Cyware Index
- `get_user_keywords()` — Get User Personalized Keywords
- `list_incident_reported()` — List Reported Incidents
- `list_incident_type()` — List Incident Types
- `list_info_source()` — Get Info Source
- `list_intel_reported()` — List Reported Intel
- `list_severity()` — List Severity
- `list_threat_method()` — List Threat Methods
- `list_users()` — List Users
- `report_incident()` — Report an Incident


### `cyware-ctix` v2.0.0 _(installed)_
_Cyware CTIX_

Allows user to search for URL, Domain and IP,Hash and CVE ID, chooses the matching element, and displays relevant details.

**33 operation(s)**:

- `add_note_to_threat_data_object()` — Add Note to Threat Data Object
- `bulk_add_relation()` — Bulk Add Relation
- `bulk_deprecate_undeprecate_objects()` — Bulk Deprecate/Undeprecate Objects
- `bulk_ioc_lookup_advanced()` — Bulk IOC Lookup (Advanced)
- `bulk_ioc_lookup_and_create_intel()` — Bulk IOC Lookup and Create Intel
- `bulk_lookup_and_create()` — Bulk Lookup and Create (Deprecated)
- `bulk_mark_unmark_false_positive()` — Bulk Mark/Unmark False Positive
- `create_custom_attribute()` — Create Custom Attribute
- `create_intel_via_open_api()` — Create Intel via Open API
- `create_report()` — Create Report
- `create_tag()` — Create Tag
- `create_threat_bulletin()` — Create Threat Bulletin
- `delete_allowed_indicator()` — Delete Allowed Indicator
- `delete_tag()` — Delete Tag
- `enrichment_tools()` — Get Enrichment Tool List
- `get_enriched_threat_data()` — Get Enriched Threat Data
- `get_enrichment_object_details()` — Get Enrichment Object Details
- `get_supported_allowed_indicator_types_list()` — Get Supported Allowed Indicator Types List
- `list_allowed_indicators()` — List Allowed Indicators
- `list_relations_of_threat_data_object()` — Get Relations List of Threat Data Object
- `list_reports()` — List Reports
- `list_rules()` — List Rules
- `list_threat_data()` — Get Threat Data
- `list_threat_data_object_details()` — Get Threat Data Object Details List
- `run_report()` — Run Report
- `run_rule()` — Run Rule
- `search_cve_id()` — Search CVE ID
- `search_domain()` — Search Domain
- `search_hash()` — Search Hash
- `search_ip()` — Search IP
- `search_url()` — Search URL
- `threat_data_object_advanced_details()` — Get Threat Data Object Additional Details
- `update_threat_bulletin()` — Update Threat Bulletin


### `cyware-ctix-feed` v1.0.0 _(installed)_
_Cyware CTIX Feed_

An automated Threat Intelligence Platform (TIP) for ingestion, enrichment, analysis, prioritization, actioning, and bidirectional sharing of threat data.

**2 operation(s)**:

- `get_save_result_set_data()` — Get Save Result Set Data
- `get_save_result_set_indicators()` — Get Save Result Set Indicators


### `darkowl` v1.0.0 _(installed)_
_DarkOwl_

DarkOwl allows you to access the world's largest database of darknet content to monitor for the presence of your data on the darknet and shorten the timeframe to its detection. DarkOwl Connector provides automated actions to get documents, Scores and perform search.

**6 operation(s)**:

- `get_document()` — Get Document
- `get_score_request_result()` — Get Score Request Result
- `get_score_request_status()` — Get Score Request Status
- `get_usage_status()` — Get Usage Status
- `search_resource()` — Search Resource
- `submit_score_request()` — Submit Score Request


### `digital-shadows` v1.0.0 _(installed)_
_Digital Shadows_

Digital Shadows monitors and manages an organization's digital risk across the widest range of data sources within the open, deep, and dark web.

**12 operation(s)**:

- `find_breach_records()` — Find Breach Records
- `find_incidents()` — Find Incidents
- `find_intelligence_incidents()` — Find Intelligence Incidents
- `find_intelligence_threats()` — Find Intelligence Threats
- `get_breach()` — Get Data Breach
- `get_breach_records()` — Get Data Breach Records
- `get_incident()` — Get Incident
- `get_intelligence_incident()` — Get Intelligence Incident
- `get_intelligence_incident_iocs()` — Get Intelligence Incident IOCs
- `get_intelligence_threat()` — Get Intelligence Threat
- `get_intelligence_threat_iocs()` — Get Intelligence Threat IOCs
- `search_records()` — Search Records


### `digital-shadows-searchlight` v1.0.0 _(installed)_
_Digital Shadows SearchLight_

Digital Shadows SearchLight monitors and manages an organization's digital risk across the widest range of data sources within the open, deep, and dark web.

**14 operation(s)**:

- `add_asset_labels()` — Add Asset Labels
- `get_alert()` — Get Alert Details
- `get_asset()` — Get Asset Details
- `get_exposed_credential_alert()` — Get Exposed Credential Alert Details
- `get_incident()` — Get Incident Details
- `get_triage_item()` — Get Triage Item Details
- `list_alerts()` — Get Alert List
- `list_assets()` — Get Asset List
- `list_exposed_credential_alerts()` — Get Exposed Credential Alert List
- `list_incidents()` — Get Incident List
- `list_triage_item_events()` — Get Triage Item Event List
- `list_triage_items()` — Get Triage Item List
- `remove_asset_labels()` — Remove Asset Labels
- `replace_asset_labels()` — Replace Asset Labels


### `dns` v1.0.0 _(installed)_
_DNS_

This connector allows for DNS lookups of both FQDN/Domain and IP address

**2 operation(s)**:

- `lookup_domain()` — Lookup FQDN/Domain
- `lookup_ip()` — Lookup IP


### `dnstwist` v1.0.0 _(installed)_
_DNSTwist_

DNSTwist is a python script used for detecting phishing attacks, typo squatters, and attack domains.

**1 operation(s)**:

- `search()` — Search Registered Domains


### `domaintools` v1.0.1 _(installed)_
_DomainTools_

DomainTools provide details around the Domain and IP. DomainTools connector facilitates automated operations to get details of domain names and IP addresses.

**9 operation(s)**:

- `get_domain_reputation_info()` — Get Domain Reputation
- `get_domain_search_info()` — Get Recent Domains
- `get_hosting_history_info()` — Get Hosting History Details
- `get_revers_domain_info()` — Get Reverse Domain Details
- `get_revers_ip_info()` — Get Reverse IP Details
- `get_reverse_email_info()` — Get Reverse Email Details
- `get_whois_domain_info()` — Get Whois Domain Details
- `get_whois_history_info()` — Get Whois History Details
- `get_whois_ip_info()` — Get Whois IP Details


### `doppel` v1.1.0 _(installed)_
_Doppel_

Doppel is a next-generation AI security company that specializes in protecting organizations from social engineering attacks, impersonation, malicious ads, fake domains, and phishing campaigns.

**4 operation(s)**:

- `execute_an_api_call()` — Execute an API Request
- `get_alert_details()` — Get Alert Details
- `get_all_alerts()` — Get All Alerts
- `update_alert()` — Update Alert


### `dragos-worldview-threat-intelligence` v1.1.0 _(installed)_
_Dragos WorldView Threat Intelligence_

Dragos WorldView industrial threat intelligence provides actionable information and recommendations on threats to operations technology (OT) environments. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**6 operation(s)**:

- `get_all_indicators()` — Get All Indicators
- `get_all_indicators_in_stix2()` — Get All Indicators In Stix2
- `get_all_reports()` — Get All Reports
- `get_all_tags()` — Get All Tags
- `get_indicators_of_report()` — Get Indicators Of Report
- `get_report_metadata()` — Get Report Metadata


### `dshield` v1.0.0 _(installed)_
_DShield_

Provide investigative actions like lookup ip and get threat feeds details from DShield

**2 operation(s)**:

- `get_threat_feeds()` — Get Threat Feeds
- `lookup_ip()` — Lookup IP


### `eclecticiq` v1.2.0 _(installed)_
_EclecticIQ_

EclecticIQ is a global threat intelligence, hunting and response technology provider. This connector facilitates the automated operations like get IP reputation, get domain reputation, get file reputation etc.

**7 operation(s)**:

- `create_sighting()` — Create Sighting
- `get_domain_reputation()` — Get Domain Reputation
- `get_email_reputation()` — Get Email Reputation
- `get_file_reputation()` — Get Filename or Hash Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_uri_reputation()` — Get URL Reputation
- `query_entities()` — Query Entities


### `emailrep` v1.0.0 _(installed)_
_EmailRep_

EmailRep is an API service provided by Sublime Security. EmailRep uses hundreds of data points from social media profiles, professional networking sites, dark web credential leaks, data breaches, phishing kits, phishing emails, spam lists, open mail relays, domain age and reputation, deliverability, and more to predict the risk of an email address.

**1 operation(s)**:

- `email_reputation()` — Get Email Address Reputation


### `facebook-threat-exchange` v1.0.0 _(installed)_
_Facebook ThreatExchange_

Provide CTI actions like search malware data, get threat indicators for IP, Domain etc from ThreatExchange

**4 operation(s)**:

- `get_malware_families()` — Get Malware Families
- `get_threat_descriptors()` — Get Threat Descriptor
- `get_threat_indicators()` — Get Threat Indicators
- `search_malware_data()` — Search Malware Data


### `farsight-dnsdb` v1.0.0 _(installed)_
_Farsight Security DNSDB_

Perform actions like search ip, search domain and search name server to get information from the Farsight Security DNSDB.

**3 operation(s)**:

- `search_domain()` — Search Domain
- `search_ip()` — Search IP
- `search_name_server()` — Search Name Server


### `feodotracker` v1.0.0 _(installed)_
_FeodoTracker_

Feodo Tracker is a project of abuse.ch with the goal of sharing botnet C&C servers associated with the Feodo malware family (Dridex, Emotet/Heodo). It offers various blocklists, helping network owners to protect their users from Dridex and Emotet/Heodo.

**1 operation(s)**:

- `get_blocklist_feed()` — Get IPv4 Feeds


### `fireeye-isight` v1.0.0 _(installed)_
_FireEye iSIGHT_

iSIGHT API extends FireEye cyber threat intelligence. This connector facilitates operations like Basic Search, Get Indicators and Get IOCs etc.

**7 operation(s)**:

- `basic_search()` — Basic Search
- `get_indicators()` — Get Indicators Data
- `get_iocs()` — Get IOCs
- `get_report()` — Get Report
- `get_threat()` — Get Threat
- `list_report()` — List Reports
- `list_vulnerability()` — List Vulnerabilities


### `focsec` v1.0.0 _(installed)_
_Focsec_

Focsec help to real-time threat intelligence API, powered by proprietary Artificial Intelligence algorithms,for detecting VPNs,Proxys,Bots, and TOR requests,enabling prompt identification of suspicious logins,fraud, and abuse.

**1 operation(s)**:

- `get_ip_details()` — Get IP Details


### `fortinet-fortiguard-ioc` v1.0.1 _(installed)_
_Fortinet FortiGuard IOC_

IOC (Indicators of Compromise) search facilitates finding details about Indicators from the FortiGuard Threat Intelligence server.

**5 operation(s)** (+1 hidden):

_investigation_
- `execute_an_api_request(method: select, endpoint: text, [q_params: json], [body_data: json])` — Execute an API Request
- `get_risk_distribution(indicator: text)` — Get Risk Distribution
- `get_selected_ioc_fields([indicator: text], [fields: text])` — Get Selected IOC Fields
- `get_visiting_countries(indicator: text)` — Get Visiting Countries


### `fortinet-fortiguard-outbreak` v2.2.0 _(installed)_
_Fortinet FortiGuard Outbreak_

Fortinet FortiGuard Outbreak provides key information about on-going cybersecurity attack with significant ramifications affecting numerous companies, organizations and industries. This connector facilitates automated operations to fetch the iocs of outbreak alert

**6 operation(s)**:

_investigation_
- `bulk_ingest_outbreak_alert_iocs(tag_name: text, create_pb_id: text, [pb_env_params: json], [dedup_field: text], [demo_mode: checkbox])` — Bulk Ingest Outbreak Alert IOCs
- `get_outbreak_alert_details_by_slug_name(slug_name: text)` — Get Outbreak Alert Details by Slug Name
- `get_outbreak_alert_iocs(tag_name: text)` — Get Outbreak Alert IOCs
- `get_outbreak_alert_threat_actor_details_by_id(document_id: text)` — Get Outbreak Alert Threat Actor Details by ID
- `list_outbreak_alert_tags()` — List Outbreak Alert Tags
- `list_threat_actors([limit: text])` — List Threat Actors


### `fortinet-fortiguard-threat-intelligence` v3.4.1 _(installed, ingestion)_
_Fortinet FortiGuard Threat Intelligence_

FortiGuard Threat Intelligence is the global threat intelligence and research organization at Fortinet. This connector facilitates automated operations to check IP, URL, Domain and File Hash Lookup’s and ingestion of daily threat feeds.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**7 operation(s)**:

_investigation_
- `fetch_fortiguard_reports(type: multiselect, [start_datetime: datetime], [end_datetime: datetime], [limit: integer], [offset: integer])` — Fetch FortiGuard Reports
- `get_encyclopedia_lookup(source: select, id: text)` — Get Encyclopedia Lookup
- `get_feeds([modified_after: datetime])` — Download Indicators
- `get_threat_categories([title: text])` — Get Threat Categories
- `get_threat_signal_report(slug: text)` — Get Threat Signal Report by Slug Name
- `ingest_feeds([modified_after: datetime], [output_mode: select])` — Fetch Threat Intel Feeds
- `threat_intel_search(indicator: text)` — Threat Intel Search


### `fortinet-web-filter-lookup` v2.0.0 _(installed)_
_Fortinet Web Filter Lookup_

Fortinet Web Filter Lookup allows users to check category and classification for any Domain

**1 operation(s)**:

- `url_review()` — Check Category of Domain or URL


### `google-cloud-platform-whitelist-feed` v1.0.0 _(installed)_
_Google Cloud Platform Whitelist Feed_

Google Cloud Platform publishes its current IP address ranges in JSON format. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `ip_ranges()` — Get IP Ranges


### `google-dorking` v1.0.0 _(installed)_
_Google Dorking_

Google Dorking refers to the practice of using advanced search operators in Google's search engine to discover information that may not be readily accessible through conventional search queries.

**1 operation(s)**:

- `custom_search()` — Custom Search


### `google-maps` v1.0.0 _(installed)_
_Google Maps_

Google Maps is use for the process of converting addresses into geographic coordinates, which you can use to place markers on a map, or position the map.

**1 operation(s)**:

- `get_maps_geocode()` — Get Maps Geocode


### `google-threat-intelligence` v1.0.0 _(installed)_
_Google Threat Intelligence_

Google Threat Intelligence is a cloud-based threat intelligence service provided by Google (via Google Cloud) that helps organizations gain visibility into threat actors, attacks, and indicators of compromise (IOCs). This connector facilitates the automated operations related to analyze retro hunts, search intelligence, livehunt notifications, livehunt rulesets, and download files from Google Threat Intelligence.

**34 operation(s)** (+4 hidden):

- `abort_retrohunt_job()` — Abort Retrohunt Job
- `analysis_file()` — Get File Or URL Analysis Report
- `create_livehunt_ruleset()` — Create Livehunt Ruleset
- `create_retrohunt_job()` — Create Retrohunt Job
- `create_zip_file()` — Create ZIP File
- `delete_livehunt_ruleset()` — Delete Livehunt Ruleset
- `delete_retrohunt_job()` — Delete Retrohunt Job
- `download_file()` — Download File
- `download_zip_file()` — Download ZIP File
- `execute_an_api_call()` — Execute an API Request
- `get_domain_reputation()` — Get Domain Reputation
- `get_entities_details()` — Get Entities Details
- `get_entities_list()` — Get Entities List
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_livehunt_ruleset_details()` — Get Livehunt Ruleset Details
- `get_livehunt_rulesets_list()` — Get Livehunt Rulesets List
- `get_mitre_tactics_and_techniques()` — Get Mitre Tactics and Techniques
- `get_pcap_file_behaviour()` — Get PCAP File Behaviour
- `get_retrohunt_job_details()` — Get Retrohunt Job Details
- `get_retrohunt_job_matching_files()` — Get Retrohunt Job Matching Files
- `get_retrohunt_jobs_list()` — Get Retrohunt Jobs List
- `get_url_reputation()` — Get URL Reputation
- `get_widget_rendering_url()` — Get Widget Rendering URL
- `get_zip_file_status()` — Get ZIP File Status
- `get_zip_file_url()` — Get ZIP File URL
- `scan_url()` — Submit URL for Scanning
- `search_intelligence()` — Search Intelligence
- `submit_sample()` — Submit File
- `update_livehunt_ruleset()` — Update Livehunt Ruleset


### `google-vision-ai` v1.0.0 _(installed)_
_Google Vision AI_

Google Vision AI allows you to Integrates Google Vision features, including image labeling, face, logo, and landmark detection, optical character recognition (OCR), and detection of explicit content, into applications. This connector facilitates the automated operations related to detect images, and operations.

**3 operation(s)**:

- `get_locations_operations()` — Get Locations Operations
- `get_operations()` — Get Operations
- `submit_images()` — Submit Images


### `greensnow-feed` v1.0.0 _(installed)_
_GreenSnow Feed_

GreenSnow is a team consisting of the best specialists in computer security, we harvest a large number of IPs from different computers located around the world. This connector facilitates automated operations such as indicators.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `greynoise` v2.0.0 _(installed)_
_GreyNoise_

GreyNoise provides information on devices observed mass-scanning the internet. This integration provides a set of actions to lookup IPs or query the GreyNoise API. For support or to report issues or enhancements, please contact support@greynoise.io.

**9 operation(s)**:

- `get_all_tag_metadata()` — Get All GreyNoise Tag Metadata
- `get_tag_details()` — Get GreyNoise Tag Details
- `gnql_query()` — GreyNoise GNQL Query
- `lookup_ip_community()` — Lookup GreyNoise IP Community Information
- `lookup_ip_complete()` — Lookup GreyNoise IP Information (Noise, RIOT, Tags)
- `lookup_ip_context()` — Lookup GreyNoise IP Context Information
- `lookup_ip_quick()` — Lookup GreyNoise IP Quick Information
- `lookup_ip_riot()` — Lookup GreyNoise IP RIOT Information
- `stats_query()` — Stats Query


### `group-ib-threat-intelligence-attribution-feed` v1.2.0 _(installed)_
_Group IB Threat Intelligence & Attribution Feed_

Use Group-IB Threat Intelligence & Attribution Feed integration to fetch IOCs from various Group-IB collections.

**2 operation(s)**:

- `get_indicators()` — Get Indicators
- `search_indicator()` — Search Indicator


### `have-i-been-pwned` v2.1.0 _(installed)_
_Have I Been Pwned_

Have I Been Pwned connector to get data breaches information,get data classes,lookup email, lookup domain, lookup for pwned password an dsearch for passwords

**13 operation(s)**:

- `check_pwned_password()` — Lookup for Pwned Password
- `check_pwned_passwords_by_range()` — Search for Passwords
- `execute_api_request()` — Execute an API Request
- `get_a_single_breached_site_by_name()` — Get Breached Site by Name
- `get_all_breached_email_addresses_for_a_domain()` — Get Breached Email Address List
- `get_all_breached_sites()` — Get Breached Sites List
- `get_all_breaches_for_an_account()` — Get Breaches List
- `get_all_subscribed_domains()` — Get Subscribed Domains List
- `get_data_classes()` — Get Data Classes
- `get_pastes()` — Get Pastes
- `get_the_most_recently_added_breach()` — Get Most Recent Breach
- `lookup_domain()` — Lookup Domain
- `lookup_email()` — Lookup Email


### `host_io` v1.0.0 _(installed)_
_host.io_

host.io helps to get comprehensive domain name data, uncover new domains and the relationships between them, get DNS details, scraped website content, outbound links, backlinks, and other hosting details for any domain. This connector facilitates automated operation related to various domains.

**5 operation(s)**:

- `get_all_domains()` — Get All Domains
- `get_dns_domain_details()` — Get DNS Domain Details
- `get_full_domains_data()` — Get Full Domains Data
- `get_related_domains()` — Get Related Domains
- `get_web_domain_details()` — Get Web Domain Details


### `ibm-xforce-threat-intel-feed` v2.1.0 _(installed)_
_IBM X-Force Threat Intelligence Feed_

IBM X-Force Threat Intelligence Feed is a preconfigured set of intelligence feeds that STAXX users can access immediately upon download, and which offers indicators and insights spanning threat categories you need to secure your business. This connector facilitates automated interactions, such as returning the list of public, private, and shared collection resources to which the user has access, returning general information for a specific object of a specific collection, etc. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**7 operation(s)** (+1 hidden):

- `download_indicators()` — Download Indicators
- `get_api_root_information()` — Get API Root Information
- `get_collections()` — Get Collections
- `get_manifest_by_collection_id()` — Get Manifest By Collection ID
- `get_objects_by_collection_id()` — Get Objects By Collection ID
- `get_objects_by_object_id()` — Get Object By Object ID


### `illuminate` v1.0.0 _(installed)_
_Illuminate_

Illuminate Connector

**8 operation(s)**:

- `query_domain_indicator()` — Query Domain Indicator
- `query_email_indicator()` — Query Email Address Indicator
- `query_hash_indicator()` — Query Hash Indicator
- `query_http_request_indicator()` — Query HTTP Request Indicator
- `query_ipv4_indicator()` — Query IPv4 Indicator
- `query_ipv6_indicator()` — Query IPv6 Indicator
- `query_mutex_indicator()` — Query Mutex Indicator
- `query_string_indicator()` — Query String Indicator


### `intel471` v1.0.0 _(installed)_
_Intel471_

Connector to perform various Intel471 CTI operations.

**10 operation(s)**:

- `fetch_iocs()` — Get IOCs
- `global_search()` — Global Search
- `search_actor()` — Search for Actor
- `search_actors_on_forum()` — Search for Actor with Forum
- `search_email()` — Get Email Reputation
- `search_ip_address()` — Get IP Reputation
- `search_report()` — Get Reports
- `search_report_by_tag()` — Search Report by Tag
- `search_report_by_uid()` — Get Report using UID
- `search_url()` — Get URL Reputation


### `ip-api` v1.0.0 _(installed)_
_IP-API_

IP-API helps to get the following information for any IP address: city, region (name & code), country (name & code), continent, postal code / zip code, latitude, longitude, time zone,  utc offset, european union (EU) membership, country calling code, country capital, country tld (top-level domain), currency (name & code), area & population of the country, languages spoken, asn, organization and hostname. This connector facilitates automated operation related to ip-api.

**2 operation(s)**:

- `execute_batch_api()` — Get IP Geolocation
- `execute_dns_api()` — Get DNS Geolocation


### `ip-quality-score` v1.0.1 _(installed)_
_IP Quality Score_

The IPQualityScore (IPQS) Threat Intelligence application provides threat intelligence for IP addresses, email addresses, URLs, and domains. This connector facilitates automated interactions with a IP Quality Score server using FortiSOAR™ playbooks.

**3 operation(s)**:

- `get_email_reputation()` — Get Email Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputation()` — Get URL Reputation


### `ipinfo` v1.0.0 _(installed)_
_ipinfo.io_

IpInfo.io is used to search the owner, internet provider and location of any website, domain or IP address

**2 operation(s)**:

- `get_geolocation_information()` — Get Geolocation Information
- `lookup_ip()` — Lookup IP Address


### `ipstack` v1.0.1 _(installed)_
_IPStack_

IPStack provides geolocation facility for IP Address or Domain.

**2 operation(s)**:

_investigation_
- `domain_locate(query: text, [fields: text], [enable_hostname: checkbox], [enable_security: checkbox])` — Geolocate Domain
- `ip_locate(query: text, [fields: text], [enable_hostname: checkbox], [enable_security: checkbox])` — Geolocate IP


### `ipsum-threat-intelligence-feed` v1.0.0 _(installed)_
_IPsum Threat Intelligence Feed_

IPsum is a threat intelligence feed based on 30+ different publicly available lists of suspicious and/or malicious IP addresses. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `isitphishing` v1.0.0 _(installed)_
_isitPhishing_

Provide investigative action to get url reputation from isitPhishing

**1 operation(s)**:

- `url_reputation()` — Get URL Reputation


### `kaspersky-threat-intel` v1.0.0 _(installed)_
_Kaspersky Threat Intelligence_

Kaspersky Threat Intelligence provides threat intelligence services. This connector facilitates automated operations such as Lookup IP, Lookup URL, Lookup FileHash, and Lookup Domain.

**4 operation(s)**:

- `lookup_Domain()` — Lookup Domain
- `lookup_FileHash()` — Lookup File Hash
- `lookup_IP()` — Lookup IP Address
- `lookup_URL()` — Lookup URL


### `knowthycustomer` v1.0.0 _(installed)_
_Know Thy Customer_

Searches Know Thy Customer for data about people, phone numbers, etc

**4 operation(s)**:

- `lookup_email()` — Lookup Email
- `lookup_person()` — Lookup Person
- `lookup_phone()` — Lookup Phone Number
- `lookup_property()` — Lookup Address


### `majestic-million-feed` v1.0.0 _(installed)_
_Majestic Million Feed_

Majestic crawls the web and analyzes the data to create a huge Link Intelligence dataset describing how the world wide web links together. Use the Majestic Million connector to ingest the top known websites as 'good' indicators. This connector facilitates automated operations related to fetching the list indicators and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_domain_records()` — Get Domain Records


### `malsilo` v2.0.1 _(installed)_
_MalSilo_

Ingest Threat Intel Feeds from MalSilo Gitlab. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**3 operation(s)**:

- `get_domain_feed()` — Get Domain Feeds
- `get_ipv4_feed()` — Get IPv4 Feeds
- `get_url_feed()` — Get URL Feeds


### `maltiverse` v1.0.0 _(installed)_
_Maltiverse_

Maltiverse Threat Intelligence Feeds can be integrated with your security stack to provide improvement in terms of detections and protection capabilities from different points of view. You can also upload an deploy your own Threat Intelligence!

**4 operation(s)**:

- `get_domain_reputation()` — Get Domain Reputation
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputation()` — Get URL Reputation


### `malwarebazaar` v1.0.0 _(installed)_
_MalwareBazaar_

MalwareBazaar is a project from abuse.ch with the goal of sharing malware samples with the InfoSec community, AV vendors and threat intelligence providers.

**3 operation(s)**:

- `add_comment_to_malware_sample()` — Add a Comment to Malware Sample
- `get_filehash_reputation()` — Get File Hash Reputation
- `get_malware_samples()` — Get Malware Samples


### `malwarebazaar-feed` v1.0.0 _(installed)_
_MalwareBazaar Feed_

MalwareBazaar is a project from abuse.ch with the goal of sharing malware samples with the InfoSec community, AV vendors and threat intelligence providers. This connector facilitates automated operations such as indicators.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `malwaredomainlist` v1.0.0 _(installed)_
_Malware Domain List_

Get information for specified ip address or domain from Malware Domain List

**2 operation(s)**:

- `domain_lookup()` — Domain Lookup
- `ip_lookup()` — IP Lookup


### `mandiant-advantage-threat-intelligence` v1.0.0 _(installed)_
_Mandiant Advantage Threat Intelligence_

Mandiant Advantage Threat Intelligence provides automated access to indicators of compromise (IOCs) IP addresses, domain names, URLs threat actors are using, via the indicators, allows access to full length finished intelligence in the reports, allows for notificaiton of threats to brand and keyword monitoring via the alerts, and finally allows searching for intelligence on the adversary with the search. This connector facilitates automated operations such as indicators, actors, malware, reports, campaigns, and vulnerabilities.

**11 operation(s)**:

- `get_actor_details()` — Get Threat Actor Details
- `get_actors()` — Get Threat Actors List
- `get_campaign()` — Get Campaigns List
- `get_campaign_details()` — Get Campaign Details
- `get_indicator_details()` — Get Indicator Details
- `get_indicators()` — Get Indicators List
- `get_malware()` — Get Malware Families List
- `get_malware_details()` — Get Malware Family Details
- `get_report_details()` — Get Report Details
- `get_reports()` — Get Reports List
- `get_vulnerability()` — Get Vulnerabilities List


### `mandiant-feed` v1.0.0 _(installed)_
_Mandiant Feed_

Mandiant Threat Intelligence provides automated access to indicators of compromise (IOCs) — IP addresses, domain names, URLs threat actors are using, via the indicators. <br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `mandiant-threat-intel` v1.2.0 _(installed)_
_Mandiant Threat Intelligence_

Mandiant Threat Intelligence provides automated access to indicators of compromise (IOCs) — IP addresses, domain names, URLs threat actors are using, via the indicators, allows access to full length finished intelligence in the reports, allows for notificaton of threats to brand and keyword monitoring via the alerts, and finally allows searching for intelligence on the adversary with the search. This connector facilitates automated operations such as indicators, reports, alerts, and search collections.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**7 operation(s)**:

- `execute_an_api_call()` — Execute an API Request
- `fetch_indicators()` — Fetch Indicators
- `get_alerts()` — Get Alerts
- `get_indicators()` — Get Indicators
- `get_reports()` — Get Reports
- `get_reputation_of_indicators()` — Get Indicator Reputation
- `search_collections()` — Search Collections


### `maxmind` v1.1.0 _(installed)_
_Maxmind_

Maxmind GeoIP2 offer industry-leading IP intelligence data. Get detailed information about an IP address, such as the geographical location, organization, and other related data, with varying levels of precision.

**5 operation(s)**:

- `execute_an_api_call()` — Execute an API Request
- `ip_all_details()` — Get All Details of IP
- `ip_city_details()` — Get City Details of IP
- `ip_country_details()` — Get Country Details of IP
- `ip_insights_details()` — Get Insights Details of IP


### `maxmind-geoip2` v1.0.0 _(installed)_
_MaxMind GeoIP2_

GeoIP2 IP Intelligence provides an extensive breadth of data on IP addresses for content customization, geofencing, user analysis, research, and more. This connector facilitates automated interactions with a MaxMind GeoIP2 server using FortiSOAR™ playbooks.

**3 operation(s)**:

- `get_city()` — Get City
- `get_country()` — Get Country
- `get_insights()` — Get Insights


### `mcafee-mvision-insights` v1.1.0 _(installed)_
_McAfee Mvision Insights_

MVISION Insights APIs provide intelligence about Campaigns, associated IOCs and Events. They also provide classification information on file-hashes. This connector facilitates the automated operations related to Campaigns, Events, or IOCs.

**16 operation(s)**:

- `get_artefacts()` — Get Artefacts
- `get_campaign_details()` — Get Campaign Details
- `get_campaign_galaxies()` — Get Campaign Galaxies
- `get_campaign_iocs()` — Get Campaign IOCs
- `get_campaigns_detected()` — Get All Campaigns Detected
- `get_campaigns_list()` — Get All Campaigns List
- `get_campaigns_relationship_galaxies()` — Get Campaign Relationship Galaxies
- `get_campaigns_relationship_iocs()` — Get Campaign Relationship IOCs
- `get_events_list()` — Get All Events List
- `get_galaxies_list()` — Get All Galaxies List
- `get_insights_events_list()` — Get Insights Events List
- `get_ioc_campaigns()` — Get IOC Campaigns
- `get_ioc_details()` — Get IOC Details
- `get_ioc_list()` — Get All IOC List
- `get_ioc_relationship_campaigns()` — Get IOC Relationship Campaigns
- `get_related_samples()` — Get Related Samples


### `mcafee-tie` v1.1.0 _(installed)_
_McAfee Threat Intelligence Exchange_

McAfee Threat Intelligence Exchange, Can used to get file reputation,get file references and set file reputation

**3 operation(s)**:

- `get_file_references()` — Get File References
- `get_file_reputation()` — Get File Reputation
- `set_file_reputation()` — Set File Reputation


### `microsoft-defender-threat-intelligence` v1.0.0 _(installed)_
_Microsoft Defender Threat Intelligence_

The Microsoft Defender Threat Intelligence FortiSOAR Connector enables automated threat intelligence gathering, enrichment, and response within FortiSOAR

**11 operation(s)**:

- `get_host_component()` — Get Host Component
- `get_host_details()` — Get Host Details
- `get_host_reputation()` — Get Host Reputation
- `get_host_ssl_certificate()` — Get Host SSL Certificate
- `get_whoisrecord()` — Get Whois Record
- `list_components()` — Get Components List
- `list_hostPorts()` — Get Host Ports List
- `list_host_ssl_certificates()` — Get Host SSL Certificates List
- `list_indicators()` — Get Indicators List
- `list_passiveDns()` — Get Passive DNS List
- `list_passiveDns_reverse()` — Get Passive DNS Reverse List


### `microsoft-office-365-feed` v1.0.0 _(installed)_
_Microsoft Office 365 Feed_

Ingest the IP, URLs used by Office 365 using the web service provided by Microsoft. The fetched indicators can be used to create a whitelist, blacklist etc. for your SIEM or firewall services.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `fetch_indicator()` — Fetch Indicators


### `misp` v2.2.0 _(installed)_
_MISP_

MISP connector allows to create MISP event, delete MISP event, add and delete attributes (IOCs), add and delete tags, into existing MISP event

**15 operation(s)** (+1 hidden):

_investigation_
- `add_attributes_to_event(event_id: text, category: select, type: select, value: text, [distribution: select], [to_ids: checkbox], [comment: text])` — Add Attributes to Event
- `add_tag(name: text, colour: text, [exportable: checkbox], [hide_tag: checkbox], [org_id: integer], [user_id: integer])` — Add Tag
- `add_tag_to_event(event_id: text, tag: text)` — Add Tag to Event
- `create_event(event_info: text, [date: datetime], [distribution: select], [threat_level: select], [analysis: select], [published: checkbox], [extends_uuid: text], [additional_attributes: json])` — Add Event
- `delete_attribute(attribute_id: text)` — Delete Attribute from Event
- `delete_event(event_id: text)` — Delete Event
- `generic_rest_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_event(event_id: text)` — Get Event
- `get_events(searchJSONBody: object)` — Search Events
- `get_organisations()` — Get Organisations
- `get_tags()` — List All Tags
- `get_users()` — Get Users
- `remove_tag_from_event(event_id: text, tag: text)` — Remove Tag from Event
- `run_search(controller: select, search_type: select)` — Run Search


### `mnemonic` v1.0.0 _(installed)_
_Mnemonic_

Provides DNS information from the Mnemonic public DNS API

**1 operation(s)**:

- `lookup_domain()` — Lookup Domain


### `mxtoolbox` v2.0.0 _(installed)_
_MxToolbox_

MxToolbox offers monitoring solutions and lookup tools. Connector supports automated operations for Lookup, Monitor and Usage

**1 operation(s)**:

- `api_call()` — Get MxToolbox Records


### `myipms` v1.0.0 _(installed)_
_MYIP.MS_

Get information about IP address/domain.

**1 operation(s)**:

- `lookup()` — Whois Lookup


### `nsfocus-feed` v1.0.1 _(installed)_
_NSFOCUS Threat Intelligence Feed_

NSFOCUS platform can provide accurate and comprehensive threat intelligence data and services in real-time by incorporating intelligence collection, analysis, sharing, and consumption. <br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `nsfocus-threat-intel` v1.0.0 _(installed)_
_NSFOCUS Threat Intelligence_

NTI is a threat intelligence analysis and sharing platform launched by NSFOCUS after years of security practices and the accumulation of intelligence data. The platform can provide accurate and comprehensive threat intelligence data and services in real-time by incorporating intelligence collection, analysis, sharing, and consumption.

**8 operation(s)**:

- `get_domain_reputation()` — Get Domain or URL Reputation
- `get_domain_security_index()` — Get Domain or URL Security Index
- `get_domains_details()` — Get Domain or URL Details
- `get_file_details()` — Get File Details
- `get_file_reputation()` — Get File Reputation
- `get_ip_address_details()` — Get IP Address Details
- `get_ip_reputation()` — Get IP Reputation
- `get_ip_security_index()` — Get IP Security Index


### `opencti` v1.0.2 _(installed)_
_OpenCTI_

OpenCTI is an open threat intelligence platform where you can store, organize, visualize and share knowledge about cyber threats.

**13 operation(s)**:

- `add_indicator_field()` — Add Indicator Field
- `create_external_reference()` — Create External Reference
- `create_indicator()` — Create Indicator
- `create_label()` — Create Label
- `create_organization()` — Create Organization
- `delete_indicator()` — Delete Indicator
- `get_external_references()` — Get External References
- `get_indicators()` — Get Indicators
- `get_labels()` — Get Labels
- `get_marking_definition()` — Get Marking Definition
- `get_organizations()` — Get Organizations
- `remove_indicator_field()` — Remove Indicator Field
- `update_indicator_field()` — Update Indicator Field


### `openphish` v1.0.0 _(installed)_
_OpenPhish_

OpenPhish helps to automatically identify zero-day phishing sites and provide comprehensive, actionable, real-time threat intelligence by using proprietary Artificial Intelligence algorithms.

**2 operation(s)**:

- `get_indicators_for_24h_feed()` — Get Indicators For 24 Hr Feed 
- `get_indicators_for_latest_feed()` — Get Indicators For Latest Feed 


### `paloalto-autofocus` v2.0.0 _(installed)_
_PaloAlto AutoFocus_

Palo Alto Networks AutoFocus™ is a threat intelligence service that provides an interactive, graphical interface for analyzing and contextualizing the threats your network faces.

**11 operation(s)**:

- `get_domain_reputation()` — Get Domain Reputation
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_sample_details()` — Get Sample Details
- `get_session_details()` — Get Session Details
- `get_tag_details()` — Get Tag Details
- `get_tags_list()` — Get Tags List
- `get_threat_indicator_feed()` — Get Threat Indicator Feed
- `get_url_reputation()` — Get URL Reputation
- `samples_search()` — Samples Searches
- `top_tags_search()` — Top Tags Search


### `passivetotal` v1.0.0 _(installed)_
_PassiveTotal_

Provide investigative action to get reputation of IP and Domain and get WHOIS information of IP and Domain

**9 operation(s)**:

- `domain_reputation()` — Get Domain Reputation
- `get_account_info()` — Get Account Information
- `get_domain_classification()` — Get Domain Classification
- `get_malware_data()` — Get Malware Data
- `get_subdomains()` — Get Sub Domains
- `ip_reputation()` — Get IP Reputation
- `search_whois()` — Search WHOIS
- `whois_domain()` — WHOIS Domain
- `whois_ip()` — WHOIS IP


### `phishing-initiative` v2.0.0 _(installed)_
_Phishing Initiative_

Phishing Initiative connector allows you to get URL reputation

**1 operation(s)**:

- `url_reputation()` — Get URL Reputation


### `phishme-intelligence` v1.0.0 _(installed)_
_Phishme Intelligence_

Provide various hunting operation like hunt file,hunt IP,hunt URL,hunt domain and reporting operation like get report integrate with Phishme Intelligence

**5 operation(s)**:

- `get_report()` — Get Report
- `hunt_domain()` — Hunt Domain
- `hunt_file()` — Hunt File
- `hunt_ip()` — Hunt IP
- `hunt_url()` — Hunt URL


### `phishtank` v1.0.1 _(installed)_
_PhishTank_

PhishTank Connector which utilizes retrieving a URL's reputation from PhishTank

**1 operation(s)**:

- `url_reputation()` — URL Reputation


### `plain-text-feed` v1.0.0 _(installed)_
_Plain Text Feed_

Plain Text Feed can be used to fetch IP addresses from a text file from any publicly hosted url. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `polyswarm` v1.0.0 _(installed)_
_PolySwarm_

PolySwarm is a real-time threat intelligence from a crowdsourced network of security experts and antivirus companies. This connector facilitates the automated operations to get the URL, IP, File, Domain reputation.

**6 operation(s)**:

- `file_rescan()` — File Rescan
- `file_scan()` — File Scan
- `get_domain_reputation()` — Get Domain Reputation
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputation()` — Get URL Reputation


### `pulsedive` v1.0.0 _(installed)_
_Pulsedive_

Pulsedive is a free threat intelligence platform that allows users to search, scan, and enrich IP addresses, URLs, domains, and other Indicators of Compromise (IOCs) using data from open-source intelligence (OSINT) feeds. Users can also submit their own IOCs for analysis and enrichment.

**3 operation(s)**:

- `get_domain_reputation()` — Get Domain Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_links_of_indicator()` — Get Links of Indicator


### `qianxin-threat-intel` v1.1.0 _(installed)_
_QiAnxin Threat Intelligence_

QiAnxin Threat Intelligence Center provides automate processing and the manual operation of top security research teams to provide users with accurate threat intelligence based on multi-dimensional and global data collection capabilities. QiAnxin Threat Intelligence connector performs actions like IP reputation, file reputation etc.

**3 operation(s)**:

- `file_reputation()` — Get File Reputation
- `get_loss_detection_data()` — Get Loss Detection Data
- `ip_reputation()` — Get IP Reputation


### `quttera` v1.0.0 _(installed)_
_Quttera_

Quttera helps to scan website/domain for malware, ssl and open ports. This connector facilitates automated operations like scan website, get status of scan and get reports of scan etc.

**14 operation(s)**:

- `get_blacklist_report()` — Get Blacklist Report
- `get_blacklist_status()` — Get Blacklist Status
- `get_report_of_integrity_scan()` — Get Report of Integrity Scan
- `get_report_of_port_scan()` — Get Report of Port Scan
- `get_report_of_ssl_scan()` — Get Report of SSL Scan
- `get_report_of_url_scan()` — Get Report of URL Scan
- `get_status_of_integrity_scan()` — Get Status of Integrity Scan
- `get_status_of_port_scan()` — Get Status of Port Scan
- `get_status_of_ssl_scan()` — Get Status of SSL Scan
- `get_status_of_url_scan()` — Get Status of URL Scan
- `start_integrity_scan()` — Start Integrity Scan
- `start_port_scan()` — Start Port Scan
- `start_ssl_scan()` — Start SSL Scan
- `start_url_scan()` — Start URL Scan


### `rapid7-threat-command-cloud` v1.1.1 _(installed)_
_Rapid7 Threat Command Cloud_

Rapid7 Threat Command Cloud is a digital risk protection and external threat intelligence platform that helps organizations monitor, detect, and mitigate threats originating outside their perimeters (web, deep web, dark web).

**10 operation(s)**:

- `add_iocs_to_source()` — Add IOCs to Source
- `change_ioc_severity()` — Change IOC Severity
- `generic_api_call()` — Execute an API Request
- `get_alert_by_id()` — Get Alert Details
- `get_alerts_list()` — Get Alerts List
- `get_cves_by_ids()` — Get CVEs by IDs
- `get_cves_list_from_account()` — Get CVEs List from Account
- `get_ioc_by_value()` — Get IOC by Value
- `get_ioc_sources()` — Get IOC Sources
- `get_iocs_by_filter()` — Get IOCs by Filter


### `recorded-future` v2.0.0 _(installed)_
_Recorded Future_

Recorded Future is a threat intelligence product that automatically collects and analyzes threat intelligence from technical, open, and dark web sources to provide invaluable context for faster human analysis and real-time integration with your existing security systems.

**41 operation(s)**:

- `add_entity_to_user_list()` — Add Entity To User List
- `add_ioc_to_recorded_future_intelligence_cloud()` — Add IOC To Recorded Future Intelligence Cloud
- `create_user_list()` — Create User List
- `domain_reputation()` — Get Domain Reputation
- `domain_risklist()` — Get Domain Risk List
- `file_reputation()` — Get File Reputation
- `file_risklist()` — Get File Risk List
- `get_alert()` — Get Alert
- `get_bulk_identity_novel_exposures_alerts()` — Get Bulk Identity Novel Exposures Alerts
- `get_bulk_third_party_risk_alerts()` — Get Bulk Third Party Risk Alerts
- `get_entities_by_list_id()` — Get Entities By List ID
- `get_identity_novel_exposures_alert_by_alert_id()` — Get Identity Novel Exposures Alert By Alert ID
- `get_malware_categories()` — Get Malware Categories
- `get_malware_threat_map()` — Get Malware Threat Map
- `get_malware_threat_map_by_org_id()` — Get Malware Threat Map By Org ID
- `get_maps_list()` — Get Maps List
- `get_riskrules()` — Get Risk Rules
- `get_third_party_risk_alert_by_alert_id()` — Get Third Party Risk Alert By Alert ID
- `get_threat_actors_categories()` — Get Threat Actors Categories
- `get_threat_actors_list()` — Get Threat Actors List
- `get_threat_map()` — Get Threat Map
- `get_threat_map_by_org_id()` — Get Threat Map By Org ID
- `get_user_list_by_list_id()` — Get User List By List ID
- `get_user_list_status_by_list_id()` — Get User List Status By List ID
- `get_user_lists()` — Get User Lists
- `ip_reputation()` — Get IP Reputation
- `ip_risklist()` — Get IP Risk List
- `lookup_malware()` — Lookup Malware
- `lookup_url()` — Lookup URL
- `lookup_vulnerability()` — Lookup Vulnerability
- `remove_entity_from_user_list()` — Remove Entity From User List
- `search_alert_rule()` — Search Alert Rules
- `search_alerts()` — Search Alerts
- `search_domain()` — Search Domain
- `search_file()` — Search Filehash
- `search_ip()` — Search IP
- `search_malware()` — Search Malware
- `search_url()` — Search URL
- `search_vulnerability()` — Search Vulnerabilities
- `url_risklist()` — Get URL Risk List
- `vulnerability_risklist()` — Get vulnerability Risk List


### `ripestat` v1.0.0 _(installed)_
_RIPEstat_

Pulls information about an IP address from multiple endpoints provided by RIPEstat

**1 operation(s)**:

- `lookup_ip()` — Lookup IP


### `riskiq-digital-footprint` v1.0.0 _(installed)_
_RiskIQ Digital Footprint_

RiskIQ Digital Footprint gives complete visibility beyond the firewall. Unlike scanners and IP-dependent data vendors, RiskIQ Digital Footprint is the only solution with composite intelligence, code-level discovery and automated threat detection and exposure monitoring—security intelligence mapped to your attack surface. This connector facilitates automated interactions, with a RiskIQ Digital Footprint server using FortiSOAR™ playbooks.

**8 operation(s)**:

- `add_assets()` — Add Assets
- `get_assets_by_type()` — Get Assets By Type
- `get_assets_by_uuid()` — Get Assets By UUID
- `get_changed_asset()` — Get Changed Asset
- `get_changed_asset_summary()` — Get Changed Asset Summary
- `get_connected_asset()` — Get Connected Assets
- `get_task_status()` — Get Task Status
- `update_assets()` — Update Assets


### `riskiq-passivetotal` v1.0.0 _(installed)_
_RiskIQ PassiveTotal_

RiskIQ PassiveTotal used to map threat actor infrastructure, profile hostnames & IP addresses, discover web technologies on Internet hosts. This connector provides actions for Get Reputation, Get Components, Get Trackers, Get Alerts, Get Enrichment Data, etc

**10 operation(s)**:

- `get_alerts()` — Get Alerts
- `get_components()` — Get Components
- `get_cookies()` — Get Cookies
- `get_enrichment_data()` — Get Enrichment Data
- `get_passive_dns()` — Get Passive DNS
- `get_reputation()` — Get Reputation
- `get_services()` — Get Services
- `get_trackers()` — Get Trackers
- `get_whois_data()` — Get Whois Data
- `search_whois_data()` — Search Whois Data


### `riskiq-whoisiq` v1.0.0 _(installed)_
_RiskIQ WHOISIQ_

The WHOISIQ™ allow you to search for WHOISIQ™ records by the various attributes on those records. Currently, the API supports searching by (physical) address, domain, IP Address, email, (registrant) name, nameserver, (registrant) organization, and (registrant) phone number. This connector facilitates automated interactions, with a RiskIQ WHOISIQ server using FortiSOAR™ playbooks.

**7 operation(s)**:

- `get_address()` — Get Address
- `get_domain()` — Get Domain
- `get_email()` — Get Email Address
- `get_name()` — Get Name
- `get_name_server()` — Get Name Server
- `get_org()` — Get Organization
- `get_phone()` — Get Phone Number


### `rss-feed` v1.0.0 _(installed, ingestion)_
_RSS Feed_

An RSS feed, short for Really Simple Syndication, is a standardized format used to publish frequently updated content such as blog posts, news headlines, audio, and video. It allows users to subscribe to their favorite websites and receive updates automatically without having to visit each site individually. RSS feeds contain headlines, summaries, and links to full articles, enabling users to stay informed about new content from multiple sources in one place.

**1 operation(s)**:

_investigation_
- `get_indicators(url: text)` — Get Indicators


### `safe-browsing` v1.0.0 _(installed)_
_Safe Browsing_

Safe Browsing connector used to get url reputation

**1 operation(s)**:

- `get_url_reputation()` — Get URL Reputation


### `screenshot-machine` v1.0.0 _(installed)_
_ScreenShot Machine_

ScreenShot Machine Connector

**1 operation(s)**:

- `get_screenshot()` — Get Screenshot


### `security-scorecard` v1.0.0 _(installed)_
_SecurityScorecard_

Security Scorecard Platform combines several threat intelligence sources to provide in-depth insights on threat hosts and attack infrastructure.This connector facilitates automated operations to pull off real-time host configuration analysis to come up with actionable threat intelligence that is vital in detection, mitigation, and remediation.

**8 operation(s)**:

- `get_alert_list()` — Get Alert List
- `get_all_companies_portfolio()` — Get All Companies Portfolio
- `get_company_factor_score()` — Get Company Factor Score
- `get_company_history_factor_score()` — Get Company History Factor Score
- `get_company_history_score()` — Get Company History Score
- `get_company_score()` — Get Company Score
- `get_list_of_portfolio()` — Get List of Portfolio
- `get_ransomware_details()` — Get Ransomware Details  


### `security-trails` v1.0.0 _(installed)_
_SecurityTrails_

SecurityTrails is a cybersecurity platform that provides domain and IP intelligence services. It offers tools for reconnaissance, asset discovery, and monitoring of digital footprints to enhance security assessments and investigations. Users can access information such as historical DNS records, WHOIS details, and other data related to domains and IP addresses.

**9 operation(s)**:

- `get_associated_domains()` — Get Associated Domains
- `get_associated_ips()` — Get Associated IPs
- `get_domain_details()` — Get Domain Details
- `get_domain_tags_details()` — Get Domain Tags Details
- `get_domain_whois_details()` — Get Domain WHOIS Details
- `get_ips_neighbors()` — Get IPs Neighbors
- `get_subdomain_details()` — Get Subdomain Details
- `get_whois_history()` — Get WHOIS History
- `get_whois_ips()` — Get Whois IPs


### `securitybridge` v1.0.0 _(installed)_
_SecurityBridge_

SecurityBridge is an SAP native solution for Security and Event monitoring for SAP.

**1 operation(s)**:

- `fetch_events()` — Fetch Events


### `snort-ip-blocklist-feed` v2.0.0 _(installed)_
_Snort IP Blocklist Feed_

Snort is an open-source, free and lightweight network intrusion detection system (NIDS) software for Linux and Windows to detect emerging threats. This connector facilitates automated operations related to fetching the list indicators and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `soltra-edge` v1.0.0 _(installed)_
_Soltra Edge_

Soltra Edge leverages the open industry standards of STIX and TAXII to collect threat intelligence from various sources and convert it into the industry-standard language. This connector facilitates automated operations like get STIX object, upload STIX etc.

**3 operation(s)**:

- `get_stix_object()` — Get STIX object
- `search_stix()` — Search STIX objects
- `upload_stix()` — Upload STIX Package


### `spamhaus` v1.0.1 _(installed)_
_Spamhaus_

The Spamhaus Project is responsible for compiling several widely used anti-spam lists. This connector helps to check IP/Domain/URL is present in Spamhaus blocklists or not.

**3 operation(s)**:

- `check_domain()` — Lookup Domain
- `check_ip()` — Lookup IP
- `check_url()` — Lookup URL


### `spamhaus-feed` v1.0.0 _(installed)_
_Spamhaus Feed_

Spamhaus Feed provides access to expansive threat data and related information. This connector facilitates automated operations related to fetching the list of IPs blocklist.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `fetch_indicators()` — Fetch Indicators


### `ssl-blacklist-feed` v1.0.0 _(installed)_
_SSL Blacklist Feed_

The SSL Blacklist (SSLBL) is a project of abuse.ch with the goal of detecting malicious SSL connections, by identifying and blacklisting SSL certificates used by botnet C&C servers. In addition, SSLBL identifies JA3 fingerprints that helps you to detect & block malware botnet C&C communication on the TCP layer. This connector facilitates automated operations related to fetching the list of IPs blacklist.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `fetch_indicators()` — Fetch Indicators


### `stix` v1.0.0 _(installed)_
_STIX_

Structured Threat Information Expression, is a language and serialization format for exchanging threat information in cyberspace. Using this connector we can be used to extract indicators from the submitted STIX file and also export selected indicators from FortiSOAR in a valid STIX specification.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>.

**4 operation(s)** (+2 hidden):

- `create_indicators()` — Export Indicators In STIX Spec Format
- `extract_indicators()` — Extract Indicators From STIX File


### `symantec-deepsight-intelligence` v1.0.2 _(installed)_
_Symantec DeepSight Intelligence_

Symantec DeepSight™ Intelligence is a cloud-hosted cyber threat intelligence platform that provides an edge against cyber threats. This connector facilitates automated operations like get Filehash , URL, Domain , IP reputation

**4 operation(s)**:

- `domain_reputation()` — Get Domain Reputation
- `filehash_reputation()` — Get File Reputation
- `ip_reputation()` — Get IP Reputation
- `url_reputation()` — Get URL Reputation


### `symantec-webpulse-site-review` v1.0.0 _(installed)_
_Symantec WebPulse Site Review_

Site Review allows users to check and dispute the current WebPulse categorization for any URL

**1 operation(s)**:

- `url_review()` — Check Category of Domain or URL


### `taxii2-threat-intel-feed` v1.2.1 _(installed, ingestion)_
_TAXII Threat Intel Feed_

TAXII Threat Intel Feed connector acts as a STIX-compliant TAXII client. It connects to user-specified TAXII servers (TAXII v2.1), discovers and enumerates collections via API Root, and retrieves STIX-formatted threat intelligence objects—such as Indicators, Malware, Campaigns—on schedule using Data Ingestion or on demand. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**5 operation(s)** (+1 hidden):

_investigation_
- `download_indicators([added_after: datetime], [fetch_all_records: checkbox], [headers: json])` — Download Indicators
- `get_collections([collectionID: text], [headers: json])` — Get Collections
- `get_objects(collectionID: text, [added_after: datetime], [fetch_all_records: checkbox], [headers: json])` — Get Objects
- `get_objects_by_collection_id(collectionID: text, [added_after: datetime], [output_mode: select], [fetch_all_records: checkbox], [headers: json])` — Fetch Indicators


### `threat-intelligence-platform` v1.0.0 _(installed)_
_Threat Intelligence Platform_

Threat Intelligence Platform combines several threat intelligence sources to provide in-depth insights on threat hosts and attack infrastructure.This connector facilitates automated operations to pull off real-time host configuration analysis to come up with actionable threat intelligence that is vital in detection, mitigation, and remediation.

**6 operation(s)**:

- `get_connected_domains_details()` — Get Connected Domains Details
- `get_domain_infrastructure_analysis_details()` — Get Domain Infrastructure Analysis Details
- `get_domain_malware_check_details()` — Get Domain Malware Check Details
- `get_domain_reputation_details()` — Get Domain Reputation  Details
- `get_ssl_certificate_chain_details()` — Get SSL Certificate Chain Details
- `get_ssl_configuration_analysis_details()` — Get SSL Configuration Analysis Details


### `threat-miner` v1.0.0 _(installed)_
_ThreatMiner_

ThreatMiner is a threat intelligence portale that aggregates data from multiple open-source platforms like: VirusTotal, CIRCL etc... and enable analysts to research under a single interface. This connector enables users to create automated solutions to query against ThreatMiner's database.

**6 operation(s)**:

- `get_domain_details()` — Get Domain Details
- `get_email_details()` — Get Email Details
- `get_file_hash_details()` — Get File Hash Details
- `get_import_hash_details()` — Get Import Hash Details
- `get_ip_details()` — Get IP Details
- `get_ssdeep_details()` — Get SSDeep Details


### `threatbook` v1.0.0 _(installed)_
_ThreatBook_

ThreatBook is China’s first security threat intelligence company, dedicated to providing real-time, accurate and actionable threat intelligence to block, detect and prevent attacks.

**13 operation(s)**:

- `domain_analysis()` — Submit Domain for Analysis
- `file_detection_report()` — Get File Detection Report
- `get_domain_name_context()` — Get Domain Name Context
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_url_reputations()` — Get URL Reputations
- `loss_detection()` — Get Loss Detection Data
- `run_domain_advance_query()` — Run Domain Advanced Query
- `run_ip_advance_query()` — Run IP Advance Query
- `run_sub_domain_query()` — Run Sub Domain Query
- `scan_url()` — Submit URL for Scanning
- `submit_file()` — Submit File
- `submit_ip()` — Submit IP for Analysis


### `threatconnect` v2.0.0 _(installed)_
_ThreatConnect_

ThreatConnect connector which utilizes the ThreatConnect API and allows threat intelligence actions such as get reputation of IP address, URL, File Hash or Email address etc.

**7 operation(s)**:

- `hunt_email()` — Get Email Reputation
- `hunt_file()` — Get File Reputation
- `hunt_host()` — Get Host Reputation
- `hunt_ip()` — Get IP Reputation
- `hunt_url()` — Get URL Reputation
- `invoke_api()` — Invoke ThreatConnect REST API
- `list_indicator()` — List Indicator


### `threatcrowd` v1.0.0 _(installed)_
_ThreatCrowd_

ThreatCrowd is a system for finding and researching artifacts relating to Cyber Threats. Provide actions like hunt IP, Email, MD5 and Hostname in ThreatCrowd system.

**4 operation(s)**:

- `hunt_domain()` — Hunt Domain
- `hunt_email()` — Hunt Email Address
- `hunt_file()` — Hunt MD5
- `hunt_ip()` — Hunt IP


### `threatq` v2.1.0 _(installed)_
_ThreatQ_

ThreatQuotient is a threat intelligence platform that centrally manages and correlates unlimited external sources. This connector facilitates automated operation such as collects and interprets intelligence data from open sources and manages indicators.

**28 operation(s)**:

- `add_attribute()` — Add Attribute
- `add_source()` — Add Source
- `create_adversary()` — Create Adversary
- `create_event()` — Create Event
- `create_ioc()` — Create IOC
- `get_domain_reputation()` — Get Domain Reputation
- `get_event_types()` — Get Event Types
- `get_file_reputation()` — Get File Reputation
- `get_indicator_reputation()` — Get Reputation
- `get_indicator_statuses()` — Get Indicator Statuses
- `get_indicator_types()` — Get Indicator Types
- `get_ip_reputation()` — Get IP Reputation
- `get_list_of_adversaries()` — Get List of Adversaries
- `get_list_of_events()` — Get List of Events
- `get_list_of_indicators()` — Get List of Indicators
- `get_related_ioc()` — Get Related IOCs
- `get_related_objects()` — Get Related Objects
- `get_saved_searches()` — Get Saved Searches
- `get_url_reputation()` — Get URL Reputation
- `link_ioc()` — Link IOCs
- `link_two_objects()` — Link Two Objects
- `remove_attribute()` — Remove Attribute
- `remove_source()` — Remove Source
- `run_search_query()` — Run Search Query
- `search_event()` — Search Event
- `search_indicator()` — Search Indicator
- `unlink_two_objects()` — Unlink Two Objects
- `update_indicator()` — Update Indicator


### `threatstream` v2.5.1 _(installed)_
_Anomali ThreatStream_

Anomali ThreatStream offers the most comprehensive Threat Intelligence Platform, allowing organizations to access all intelligence feeds and integrate it seamlessly with internal security and IT systems. This connector facilitates automated operations to to pull threat intelligence from the ThreatStream platform, import observables into ThreatStream from any source, manage threat model entities and investigations, and so on.

**35 operation(s)** (+2 hidden):

- `advance_query()` — Run Advanced Search
- `approve_import_job()` — Approve IOC By Import ID
- `create_incident()` — Create Incident
- `create_investigation()` — Create Investigation
- `create_threat_bulletin()` — Create Threat Bulletin
- `delete_incident()` — Delete Incident
- `domain_reputation()` — Get Domain Reputation
- `email_reputation()` — Get Email ID Reputation
- `fetch_incidents()` — Get Incident List
- `file_reputation()` — Get File Reputation
- `filter_language_query()` — Run Filter Language Query
- `get_import_job_status()` — Get Import Job Status
- `get_import_jobs()` — Get Import Job Details
- `get_incident()` — Get Incident
- `get_submit_url_status()` — Get Sandbox Status of Submitted URL/File
- `get_submitted_url_report()` — Get Sandbox Report of Submitted URL/File
- `intelligence_enrichments()` — Get Intelligence Enrichments
- `ip_reputation()` — Get IP Reputation
- `list_incidents_by_indicator()` — Get Incident List By Indicator
- `list_investigation_elements()` — List Investigation Elements
- `list_investigations()` — List Investigations
- `list_observables_associated_threat_bulletin()` — Get Threat Bulletin Observables
- `list_threat_bulletins()` — Get Threat Bulletin List
- `list_threat_model_entity()` — Get Threat Bulletin Entities
- `reject_import_job()` — Reject IOC By Import ID
- `submit_observables()` — Submit Observables
- `submit_urls_files()` — Submit URLs or Files to Sandbox
- `update_incident()` — Update Incident
- `update_investigation()` — Update Investigation
- `update_threat_bulletin()` — Update Threat Bulletin
- `url_reputation()` — Get URL Reputation
- `whois_domain()` — Get Whois Domain Information
- `whois_ip()` — Get Whois IP Information


### `tor-exit-address-feed` v1.0.0 _(installed)_
_Tor Exit Address Feed_

The Tor Exit List service maintains lists of IP addresses used by all exit relays in the Tor network. Service providers may find it useful to know if users are coming from the Tor network, as they may wish to provide their users with an onion service.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `trend-micro-sms` v1.1.0 _(installed)_
_Trend Micro SMS_

Trend Micro SMS(Security Management System) Provides global vision and security policy control for threat intelligence and enables comprehensive analysis and corrections. You can configure it to automatically check for, download, and distribute filter updates to TrendMicro SMS system as well as to take immediate action on events based on yer security policy.

**7 operation(s)**:

- `add_reputation_entry()` — Add Reputation Entry
- `delete_reputation_bulk()` — Delete Reputation
- `delete_reputation_entry()` — Delete Reputation Entries
- `import_reputation_bulk()` — Import Reputation
- `quarantine_ip()` — Quarantine IP Address
- `query_reputation_entry()` — Query Reputation Entries
- `unquarantine_ip()` — Unquarantine IP Address


### `trend-micro-vision-one` v1.0.0 _(installed)_
_Trend Micro Vision One_

Trend Micro Vision One providing deep and broad extended detection and response (XDR) capabilities that collect and automatically correlate data across multiple security layers—email, endpoints, servers, cloud workloads, and networks—Trend Micro Vision One prevents the majority of attacks with automated protection. This connector facilitates automated operation such as retrieving information about workbench alerts in Trend Micro Vision One, adding indicators such as email addresses, domains, etc. to the 'Suspicious Object List' in Trend Micro Vision One, terminates a process that is running on one or more endpoints, etc.

**17 operation(s)**:

- `add_to_block_list()` — Add to Block List
- `add_to_exception_list()` — Add to Exception List
- `add_to_suspicious_object_list()` — Add to Suspicious Object List
- `collect_file()` — Collect File
- `delete_email_message()` — Delete Email Message
- `get_alert_details()` — Get Alert Details
- `get_detection_data()` — Get Detection Data
- `get_endpoint_details()` — Get Endpoint Details
- `get_list_alerts()` — Search Alerts
- `get_task_details()` — Get Task Details
- `isolate_endpoint()` — Isolate Endpoints
- `quarantine_email_message()` — Quarantine Email Message
- `remove_from_block_list()` — Remove from Block List
- `remove_from_exception_list()` — Remove from Exception List
- `remove_from_suspicious_object_list()` — Remove from Suspicious Object List
- `restore_endpoint()` — Restore Endpoints
- `terminates_process()` — Terminates Process


### `trustar` v1.0.0 _(installed)_
_TruSTAR_

TruSTAR synchronizes the incident report information available in the TruSTAR platform to the monitoring tools and analysis workflows.

**6 operation(s)**:

- `delete_report()` — Delete Report
- `get_indicator()` — Get Indicator
- `get_report()` — Get Report
- `get_report_details()` — Get Report Details
- `submit_report()` — Submit Report
- `update_report()` — Update Report


### `twitter-feed` v1.0.0 _(installed)_
_Twitter Feed_

Twitter feed connector fetches threat intelligence from tweettioc.com.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `unit-42-intel-objects-feed` v1.0.0 _(installed)_
_Unit 42 Intel Objects Feed_

Unit 42 Intel provides threat intelligence from multiple Palo Alto Networks services. Using Unit 42 Intel data, you can investigate indicators and their behaviors, and use that knowledge to better safeguard your network from malicious activity.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `fetch_indicators()` — Fetch Indicators


### `urlhaus` v1.1.0 _(installed)_
_URLhaus_

URLhaus is a project operated by abuse.ch. The purpose of the project is to collect, track and share malware URLs, helping network administrators and security analysts to protect their network and customers from cyber threats.

**8 operation(s)**:

- `get_hash_details()` — Get Hash Details 
- `get_host_details()` — Get Host Details
- `get_recent_payload()` — Get Recent Payloads
- `get_recent_urls()` — Get Recent URLs
- `get_signature()` — Query Signature Information
- `get_tag()` — Query Tag Information
- `get_url_details()` — Get URL Details
- `get_url_details_by_id()` — Get URLs Details by ID


### `urlscan-io` v1.1.2 _(installed)_
_URLScan.io_

URLScan.io provides a service that analyzes websites and the resources they request. URLScan.io provides actions like search domain, ip, hash scan URL and retrieve report of scanned url.

**6 operation(s)**:

- `custom_search()` — Custom Search
- `get_report()` — Get Report
- `search_domain()` — Search Domain
- `search_hash()` — Search Hash
- `search_ip()` — Search IP
- `submit_url()` — Submit URL


### `urlvoid` v1.1.0 _(installed)_
_URLVoid_

URLVoid Connector

**1 operation(s)**:

- `domain_reputation()` — Get Website Reputation 


### `usom` v1.0.0 _(installed)_
_USOM Feed_

USOM has URL's and it is lookup connector. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_feed()` — Fetch Indicators


### `vectra` v4.0.0 _(installed)_
_Vectra_

Vectra provides automated threat detection, empowers threat hunting and exposes hidden attackers

**15 operation(s)**:

- `get_accounts_list()` — Get Accounts List
- `get_assignments_by_id()` — Get Assignments By ID
- `get_assignments_list()` — Get Assignments List
- `get_audit_log_events_associated_with_a_user_id()` — Get Audit Log Events Associated with a User ID
- `get_detection_by_id()` — Get Detection By ID
- `get_detections_list()` — Get Detections
- `get_groups_list()` — Get Groups List
- `get_host_by_id()` — Get Host By ID
- `get_hosts_list()` — Get Hosts
- `get_outcome_by_id()` — Get Outcome By ID
- `get_outcomes_list()` — Get Outcomes List
- `get_threat_feeds()` — Get Threat Feeds
- `get_users_list()` — Get Users List
- `get_vectra_match_rules()` — Get Vectra Match Rules
- `send_custom_request()` — Execute an API Request


### `viriback-c2-tracker-feed` v1.0.0 _(installed)_
_ViriBack C2 Tracker Feed_

ViriBack C2 Tracker is a C2 Tracker platform that instantly monitors current cyber threats. ViriBack C2 Tracker tracks malware activity and provides the URLs of the most recently detected Command and Control (C2) panels and the malware used on these panels. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `virustotal` v3.2.1 _(installed)_
_VirusTotal_

VirusTotal provides a service that analyzes suspicious files and URLs and facilitates the quick detection of viruses, worms, trojans, and all kinds of malware. This connector facilitates automated operations such as scanning and analyzing suspicious files and URLs and retrieving reports from VirusTotal for files, IP addresses, and domains.

**18 operation(s)** (+4 hidden):

_investigation_
- `analysis_file([type: select], analysis_id: text)` — Get Analysis Details
- `domain_re_analyze(id: text)` — Reanalyze Domain
- `file_re_analyze(id: text)` — Reanalyze File
- `file_reputation(file_hash: text, [relationships: multiselect])` — Get File Reputation
- `get_widget_html_content(token: text)` — Get Widget HTML Content
- `get_widget_rendering_url(query: text, [fg1: text], [bg1: text], [bg2: text], [bd1: text])` — Get Widget Rendering URL
- `ip_re_analyze(id: text)` — Reanalyze IP
- `query_domain(domain: text, [relationships: multiselect])` — Get Domain Reputation
- `query_ip(ip: text, [relationships: multiselect])` — Get IP Reputation
- `query_url(url: text, [relationships: multiselect])` — Get URL Reputation
- `scan_url(url: text)` — Submit URL for scanning
- `upload_sample(input: select, value: text)` — Submit File
- `url_re_analyze(id: text)` — Reanalyze URL

_query_
- `custom_endpoint(endpoint: text, [method: select], [body: json])` — Custom API Endpoint


### `virustotal-premium` v1.1.2 _(installed)_
_VirusTotal Premium_

VirusTotal Premium Services are used to get more threat context and exposes advanced threat hunting and malware discovery endpoints and functionality. This connector facilitates the automated operations related to analyze retro hunts, search intelligence, livehunt notifications, livehunt rulesets, and download files from VirusTotal.

**35 operation(s)** (+4 hidden):

- `abort_retrohunt_job()` — Abort Retrohunt Job
- `analysis_file()` — Get File Or URL Analysis Report
- `create_livehunt_ruleset()` — Create Livehunt Ruleset
- `create_retrohunt_job()` — Create Retrohunt Job
- `create_zip_file()` — Create ZIP File
- `delete_livehunt_ruleset()` — Delete Livehunt Ruleset
- `delete_retrohunt_job()` — Delete Retrohunt Job
- `download_file()` — Download File
- `download_zip_file()` — Download ZIP File
- `get_domain_reputation()` — Get Domain Reputation
- `get_file_reputation()` — Get File Reputation
- `get_ip_reputation()` — Get IP Reputation
- `get_livehunt_notifications_details()` — Get Livehunt Notifications Details
- `get_livehunt_notifications_files_list()` — Get Livehunt Notifications Files List
- `get_livehunt_notifications_list()` — Get Livehunt Notifications List
- `get_livehunt_rule_files_list()` — Get Livehunt Rule Files List
- `get_livehunt_ruleset_details()` — Get Livehunt Ruleset Details
- `get_livehunt_rulesets_list()` — Get Livehunt Rulesets List
- `get_pcap_file_behaviour()` — Get PCAP File Behaviour
- `get_retrohunt_job_details()` — Get Retrohunt Job Details
- `get_retrohunt_job_matching_files()` — Get Retrohunt Job Matching Files
- `get_retrohunt_jobs_list()` — Get Retrohunt Jobs List
- `get_url_reputation()` — Get URL Reputation
- `get_widget_html_content()` — Get Widget HTML Content
- `get_widget_rendering_url()` — Get Widget Rendering URL
- `get_zip_file_status()` — Get ZIP File Status
- `get_zip_file_url()` — Get ZIP File URL
- `scan_url()` — Submit URL for Scanning
- `search_intelligence()` — Search Intelligence
- `submit_sample()` — Submit File
- `update_livehunt_ruleset()` — Update Livehunt Ruleset


### `vx-vault-feed` v1.0.0 _(installed)_
_VX Vault Feed_

VX Vault is a platform that serves as a repository for malware samples and related research. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


### `webroot-brightcloud-threat-intelligence` v1.1.0 _(installed)_
_Webroot BrightCloud Threat Intelligence_

BrightCloud Threat Intelligence Connector for collecting reputation details of IP and URL addresses, and files via BrightCloud API

**3 operation(s)**:

- `file_reputation()` — Check File Reputation
- `ip_reputation()` — Check IP Address Reputation
- `url_reputation()` — Check URL Reputation


### `whats-my-browser` v1.0.0 _(installed)_
_WhatIsMyBrowser_

WhatIsMyBrowser parses user agent strings and gives insight into known user agents. This Connector supports executing investigative action like parse user agent on the WhatIsMyBrowser.

**1 operation(s)**:

- `user_agent_parse()` — Parse User Agent


### `whois-freaks` v1.0.0 _(installed)_
_WhoisFreaks_

WhoisFreaks provide well-parsed and structured domain WHOIS data for all domain names, registrars, countries and TLDs since the birth of internet. The carefully crawled current and historical domain data is available in the form of REST APIs, lookup tools, and downloadable database

**3 operation(s)**:

- `dns_lookup()` — Get DNS Lookup
- `ssl_certificates()` — Get SSL Certificates
- `whois_lookup()` — Get Whois Lookup


### `whois-rdap` v1.0.2 _(installed)_
_Whois RDAP_

Whois RDAP is a service that enables you to retrieve information about the location of IP addresses, servers, or websites. You can find out the owner of the Internet resource and their contact details. using this connector we can retrieving whois information for given IP Address.

**1 operation(s)**:

_investigation_
- `whois_ip(ip: text)` — Whois IP


### `whois-xml-api` v1.0.0 _(installed)_
_WhoisXMLAPI_

WhoisXMLAPI Provides comprehensive set of real-time and historic Whois, Domain name and DNS Data

**8 operation(s)**:

- `brand_monitor()` — Brand Monitor
- `dns_lookup()` — Get DNS Lookup
- `domain_subdomain_discovery()` — Domain or Subdomain Discovery
- `reverse_dns_search()` — Get Reverse DNS Search
- `reverse_whois_search()` — Get Reverse WHOIS Search
- `ssl_certificates()` — Get SSL Certificates
- `whois_history_search()` — Get WHOIS History Search
- `whois_search()` — Get WHOIS Search


### `wildfire` v1.1.1 _(installed)_
_PaloAlto WildFire_

This Connector supports executing investigative actions like verdict, detonate file and detonate url to analyze executables and URLs on the PaloAlto Wildfire sandbox.

**6 operation(s)**:

- `get_file_hash_report()` — Get File Hash Report
- `get_file_hash_verdict()` — Get File Hash Verdict
- `get_url_report()` — Get URL Report
- `get_url_verdict()` — Get URL Verdict
- `submit_file()` — Submit File
- `submit_url()` — Submit URL


### `xforce` v1.0.2 _(installed)_
_IBM XForce_

IBM XForce connector

**15 operation(s)**:

- `get_dns_record()` — Get DNS Record
- `get_file_reputation_using_filehash()` — Get File Reputation
- `get_ip_behaviour()` — Get IP Behaviour
- `get_ip_registrant()` — Get IP Registrant
- `get_ip_report()` — Get IP Report
- `get_ip_reputation()` — Get IP Reputation
- `get_relative_malware()` — Get Relative Malware
- `get_url_behaviour()` — Get URL Behaviour
- `get_url_report()` — Get URL Report
- `get_vulnerability()` — Get Vulnerability
- `get_vulnerability_from_stdcode()` — Get Vulnerability from STDCODE
- `get_vulnerability_from_xfid()` — Get Vulnerability from XFID
- `search_signature()` — Search Signature
- `search_signature_by_pamid()` — Search Signature by PAMID
- `search_signature_by_xpu()` — Search Signature by XPU


### `zerofox` v1.0.1 _(installed)_
_ZeroFox_

ZeroFox Platform combines advanced AI-driven analysis to detect complex threats on the surface, deep and dark web, fully managed services with threat analysts that become an extension of your team, and automated remediation to effectively disrupt threats.

**19 operation(s)**:

- `alert_cancel_takedown()` — Cancel Alert Takedown
- `alert_request_takedown()` — Request Alert Takedown
- `assign_alert_to_user()` — Assign Alert to User
- `close_alert()` — Close Alert
- `create_entity()` — Create Entity
- `get_alert_details()` — Get Alert Details
- `get_alerts_list()` — Get Alerts List
- `get_domain_lookup()` — Get Domain Lookup
- `get_email_lookup()` — Get Email Lookup
- `get_entity_list()` — Get Entity List
- `get_entity_types()` — Get Entity Types List
- `get_exploits_lookup()` — Get Exploits Lookup
- `get_filehash_lookup()` — Get FileHash Lookup
- `get_ip_lookup()` — Get IP Lookup
- `get_policy_types()` — Get Policy Types List
- `modify_alert_notes()` — Modify Alert Notes
- `modify_alert_tags()` — Modify Alert Tags
- `open_alert()` — Open Alert
- `submit_threat()` — Submit Threat


### `zoom-feed` v1.0.0 _(installed)_
_Zoom Feed_

Zoom publishes its current IP address ranges in txt files. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

- `get_indicators()` — Get Indicators


---

## Ticket Creation

### `jira` v2.0.0 _(installed)_
_Jira_

The Jira allows users to seamlessly interact with Jira Cloud by creating, updating, and deleting issues. It simplifies task management and integrates Jira actions directly into your applications or workflows.

**16 operation(s)**:

_investigation_
- `add_comment(issue_key: text, comment: text)` — Add Comment
- `add_remote_link(issue_key: text, url: text, title: text)` — Add Remote Link
- `assign_issue(accountId: text, issue_key: text)` — Assign Issue to User
- `create_ticket(project_key: text, ticket_summary: text, ticket_description: text, issue_type: text, [parent: text], [priority: text], [other_fields: json])` — Create Ticket
- `delete_ticket(issue_key: text, delete_subtask: checkbox)` — Delete Ticket
- `get_comments(issue_key: text, [startAt: integer], [maxResults: integer], [orderBy: select])` — Get Comments
- `get_ticket_details(issue_key: text)` — Get Ticket Details
- `get_user_details(accountId: text)` — Get User Details
- `list_projects()` — List Projects
- `list_tickets(jql_query: text, [start_time: datetime], [maxResults: integer], [nextPageToken: text], [fields: text])` — List Tickets
- `search_users([startAt: integer], [maxResults: integer])` — Search Users
- `set_status(issue_key: text, status: text)` — Set Ticket Status
- `submit_file(issue_key: text, path: select)` — Add Attachment
- `update_fortisoar(jira_key: text, cyops_username: text, cyops_password: text)` — Update FortiSOAR Record
- `update_ticket(issue_key: text, project_key: text, summary: text, comment: text, priority: text, [description: text], [status: text], [other_fields: json])` — Update Ticket

_utilities_
- `validate_jql_query(jql_query: text)` — Validate JQL query


---

## Ticket Management

### `alloy-itsm` v1.0.0 _(installed)_
_Alloy ITSM_

Alloy ITSM is an IT Service Management (ITSM) solution designed to help organizations manage and streamline their IT services and operations. This connector is designed to manage and automate ticket-based operations.

**17 operation(s)**:

- `add_attachments()` — Add Attachments
- `check_step_action_availability()` — Check Step Action Availability
- `create_object()` — Create Object
- `download_attachment()` — Download Attachment
- `get_attachment_content()` — Get Attachment Content
- `get_classification_values()` — Get Classification Values
- `get_classification_values_advanced()` — Advanced Search for Classification Values
- `get_current_user_profile()` — Get Current User Profile
- `get_object_activities()` — Get Object Activities
- `get_object_activities_advanced()` — Advanced Search for Object Activities
- `get_object_by_id()` — Get Object By ID
- `get_objects()` — Get Objects
- `get_objects_advanced()` — Get Objects Advanced Search
- `list_object_attachments()` — List Object Attachments
- `remove_attachment()` — Remove Attachment
- `run_step_action()` — Update Object
- `update_attachment_description()` — Update Attachment Description


### `fresh-service-desk-msp` v1.1.0 _(installed)_
_Fresh Service Desk MSP_

Fresh Service Desk MSP is a cloud-based service desk and IT service management (ITSM) platform designed to streamline service management for businesses. It offers a range of features including incident management, problem management, change management, asset management, and more. Freshservice provides a user-friendly interface for managing service requests, automating workflows, tracking assets, and generating reports. Its multi-tenant architecture ensures data segregation and security for different clients. The connector for Freshservice enables automated actions such as creating, updating, deleting, and closing tickets, enhancing the efficiency of service delivery for managed service providers.

**6 operation(s)**:

- `create_ticket()` — Create Ticket
- `delete_ticket_by_id()` — Delete Ticket By ID
- `execute_an_api_call()` — Execute an API Request
- `filter_tickets_by_query()` — Filter Tickets By Query
- `get_ticket_by_id()` — Get Ticket By ID
- `update_ticket()` — Update Ticket


### `hubspot` v1.0.0 _(installed)_
_HubSpot_

HubSpot is a CRM platform with all the software, integrations, and resources you need to connect marketing, sales, content management, and customer service. This integration is used to get, create, update or delete a ticket.

**8 operation(s)**:

- `create_tickets()` — Create Tickets
- `delete_tickets()` — Delete Tickets
- `get_all_tickets()` — Get All Tickets
- `get_owners_list()` — Get Owners List
- `get_ticket_pipelines()` — Get Ticket Pipelines
- `get_tickets_by_id()` — Get Tickets By ID
- `get_tickets_changes_log()` — Get Tickets Changes Log
- `update_tickets()` — Update Tickets


### `jira-insight-db` v1.1.0 _(installed)_
_Jira Insight DB_

Jira Insight gives teams a simple and quick way to tie assets and configuration items to service requests, incidents, problems, changes, and other issues to gain valuable context.

**8 operation(s)**:

- `create_object()` — Create Object
- `get_asset_attributes()` — Get Asset Attributes
- `get_asset_connected_tickets()` — Get Asset Connected Tickets
- `get_asset_details()` — Get Asset Details
- `get_asset_history()` — Get Asset History
- `get_asset_reference_info()` — Get Asset Reference Information
- `get_assets()` — Get Assets List
- `update_object()` — Update Object


### `manage-engine-service-desk-plus-msp` v1.0.0 _(installed)_
_ManageEngine ServiceDesk Plus MSP_

ServiceDesk Plus MSP is a web based, full-fledged ITSM suite designed specifically for managed service providers. This all-in-one ITSM solution delivers comprehensive help desk, service desk, account management, asset management, remote controls and advanced reporting in a multi-tenant architecture with robust data segregation. It empowers service providers to offer services and support to multiple clients with centralized controls.This connector provides automated actions to create, update, delete and close tickets

**16 operation(s)** (+4 hidden):

- `add_note()` — Add Note
- `add_request()` — Create Ticket
- `add_resolution()` — Add Resolution
- `close_request()` — Close Ticket
- `delete_request()` — Delete Ticket
- `delete_request_from_trash()` — Delete Ticket From Trash
- `get_all_accounts()` — Get All Accounts
- `get_all_requests()` — Get All Tickets
- `get_all_sites()` — Get All Sites
- `get_all_user()` — Get All Users
- `get_request()` — Get Ticket Details
- `update_request()` — Update Ticket


### `microfocus_smax` v1.0.0 _(installed)_
_Micro Focus SMAX_

Micro Focus SMAX connector is used for fetch SMAX incidents, requests and automate different SMAX case management actions.

**8 operation(s)**:

- `create_entities()` — Create Entities
- `create_incident()` — Create Incident
- `create_request()` — Create Request
- `get_entity_details()` — Get Entity Details
- `query_entities()` — Query Entities
- `update_entities()` — Update Entities
- `update_incident()` — Update Incident
- `update_request()` — Update Request


### `request-tracker` v2.1.0 _(installed)_
_Request Tracker_

Provide ticket management on Request Tracker by implementing actions such as create ticket, search ticket and update ticket

**15 operation(s)**:

- `comment_ticket()` — Comment Ticket
- `create_queue()` — Create Queue
- `create_ticket()` — Create Ticket
- `delete_queue()` — Delete Queue
- `delete_ticket()` — Delete Ticket
- `get_attachment_details()` — Get Attachment Details
- `get_queue_info()` — Get Queue Properties
- `get_record_history()` — Get Ticket/Queue History
- `get_ticket_info()` — Get Ticket Properties
- `get_transaction_attachments()` — Get Transaction Attachments
- `get_transaction_details()` — Get Transaction Details
- `list_queue()` — List Queue
- `search_ticket()` — Search Ticket
- `update_queue()` — Update Queue
- `update_ticket()` — Update Ticket


### `salesforce` v1.0.1 _(installed)_
_Salesforce_

Salesforce connector provides actions like, create record, update record, get details of salesforce objects/records, run SOQL query etc.

**8 operation(s)** (+1 hidden):

- `create_record()` — Create Record
- `delete_record()` — Delete Record
- `get_object_fields()` — Get Salesforce Object Fields
- `get_record_details()` — Get Salesforce Object Record Details
- `list_objects()` — List Objects
- `run_query()` — Run Query
- `update_record()` — Update Record


### `serviceaide` v1.0.0 _(installed)_
_ServiceAide_

Searches and submits tickets to the ServiceAide Service Desk

**3 operation(s)**:

- `get_ticket()` — Get Ticket
- `list_tickets()` — List Tickets
- `report_incident()` — Report an Incident Ticket


### `zendesk` v2.0.0 _(installed)_
_Zendesk_

This connector provides an automated way to create, read, update, mark spam, restore and delete tickets in Zendesk.

**12 operation(s)**:

- `delete_bulk_tickets()` — Delete Bulk Tickets
- `delete_bulk_tickets_permanently()` — Delete Bulk Of Tickets Permanently
- `ticket_create()` — Create Ticket
- `ticket_delete()` — Delete Ticket
- `ticket_deleted_list()` — Get Deleted Ticket List
- `ticket_deleted_permanently()` — Delete Ticket Permanently
- `ticket_deleted_restore()` — Restore Ticket
- `ticket_details()` — Get Ticket Details
- `ticket_list()` — Get Ticket List
- `ticket_mark_spam()` — Mark Ticket as Spam
- `ticket_related_details()` — Get Ticket Related Details
- `ticket_update()` — Update Ticket


---

## Translator

### `ibm-watson` v1.0.0 _(installed)_
_IBM Watson_

IBM Watson - language translator

**4 operation(s)**:

- `get_language()` — Get Language
- `list_languages()` — List Languages
- `list_translations()` — List Translations
- `translate_text()` — Translate Text


---

## Uncategorized

### `aiassistant-utils` v4.0.1 _(installed)_

_(no operations cataloged)_

### `aws-waf` v1.0.0 _(installed)_
_AWS WAF_

AWS WAF is a web application firewall that lets you monitor and manage web requests that are forwarded to protected AWS resources.

**5 operation(s)**:

- `create_ip_set()` — Create IP Set
- `delete_ip_set()` — Delete IP Set
- `get_ip_set()` — Get IP Set
- `list_ip_set()` — List IP Set
- `update_ip_set()` — Update IP Set


### `aws-waf-classic` v1.0.0 _(installed)_
_AWS WAF Classic_

AWS WAF Classic is a web application firewall that lets you monitor and manage web requests that are forwarded to protected AWS resources.

**6 operation(s)**:

- `create_ip_set()` — Create IP Set
- `delete_ip_set()` — Delete IP Set
- `get_change_token()` — Get Change Token
- `get_ip_set()` — Get IP Set
- `list_ip_set()` — List IP Sets
- `update_ip_set()` — Update IP Set


### `bitsight` v1.0.0 _(installed)_
_Bitsight_

Bitsight is a global cyber risk management leader transforming how companies manage exposure, performance, and risk for themselves and their third parties.

**10 operation(s)**:

- `get_alerts()` — Get Alerts
- `get_assets()` — Get Assets
- `get_assets_risk_matrix()` — Get Asset Risk Matrix
- `get_cataloged_threats()` — Get Cataloged Threats
- `get_companies_with_exposed_credentials()` — Get Companies With Exposed Credentials
- `get_credentials_leaks()` — Get Credentials Leaks Affecting Your Portfolio
- `get_portfolio_threats()` — Get Portfolio Threats
- `get_threat_evidence()` — Get Threat Evidence
- `get_threat_impact()` — Get Threat Impact
- `get_threat_statistics()` — Get Threat Statistics


### `chatsonic` v1.0.0 _(installed)_
_Writesonic Chatsonic_

This integration supports Writesonic's Chatsonic generative AI. A powerful language model with real time data

**2 operation(s)**:

- `chat_completions()` — Ask a Question
- `chat_conversation()` — Converse With Chatsonic


### `check-host` v1.0.0 _(installed)_
_Check Host_

Check host offers various network-related tools and services. It also provides tools for checking the availability and response time of a website or server from different locations around the world.

**5 operation(s)**:

- `check_result_by_request_id()` — Check Result By Request ID
- `dns_address_check()` — DNS Address Check
- `http_check()` — HTTP Check
- `ping_check()` — Ping Check
- `tcp_connection_check()` — TCP Connection Check


### `claroty` v1.1.0 _(installed)_
_Claroty_

Claroty CTD is a robust solution that delivers comprehensive cybersecurity controls for industrial environments. This connector provides automated actions like Get Assets, Get Alert, Get Alert Details, etc

**10 operation(s)**:

- `get_alert_details()` — Get Alert Details
- `get_alerts()` — Get Alerts
- `get_asset_details()` — Get Asset Details
- `get_asset_risks_and_vulnerabilities()` — Get Asset Risks And Vulnerabilities
- `get_assets()` — Get Assets
- `get_events()` — Get Events
- `get_insight_details()` — Get Insight Details
- `get_insights()` — Get Insights
- `get_queries()` — Get Queries
- `get_tasks()` — Get Tasks


### `claroty-xdome` v1.0.0 _(installed)_
_Claroty XDOME_

Claroty xDome is a modular, SaaS-powered industrial cybersecurity platform that scales to protect your environment and fulfill your goals as they evolve

**5 operation(s)**:

- `execute_generic_claroty_api()` — Execute Generic Claroty API
- `get_alerts()` — Get Alerts
- `get_devices()` — Get Devices
- `get_ot_events()` — Get OT Activity Events
- `get_vulnerabilities()` — Get Vulnerabilities


### `csv-data-management` v1.2.0 _(installed)_
_CSV Data Management_

CSV Data management can perform different operations on CSV files like read file, perform deduplication, merge two CSV files, join two CSV files, concat two CSV files and return well formatted dataset

**5 operation(s)**:

- `concat_two_csv_and_extract_data()` — Concat and Extract Data from two CSV
- `convert_json_to_csv_file()` — Convert JSON to CSV File
- `extract_data_from_csv()` — Extract Data from Single CSV
- `join_two_csv_and_extract_data()` — Join and Extract Data from two CSV
- `merge_two_csv_and_extract_data()` — Merge and Extract Data from two CSV


### `cyberark-aim` v1.1.0 _(installed)_
_CyberArk AIM_

CyberArk Application Identity Manager (AIM) is a key component in CyberArk's Privileged Access Security suite. It helps manage and secure credentials used by applications and services by providing secure retrieval of passwords and other sensitive data.

**4 operation(s)** (+3 hidden):

- `get_password()` — Get Password


### `cymulate-asm` v1.0.0 _(installed)_
_Cymulate ASM_

The Cymulate Exposure Management and Security Validation Platform provides the technology for exposure
discovery, validation, and prioritization with business insights and intelligence. This simplifies security leaders’ risk
and resilience to emergent threats and a rapidly changing attack surface. With a complete view of the security
posture and business risks, the Cymulate platform gives security leaders the data they need to define the scope for cyber initiatives, successfully mobilize mitigations, and continuously assess security operations performance.

**9 operation(s)**:

- `create_internal_assessment()` — Create Internal Assessment
- `delete_internal_assessment_by_id()` — Delete Internal Assessment By ID
- `get_assessment_list()` — Get Assessment List
- `get_assets_list_by_assessment_id()` — Get Assets List By Assessment ID
- `get_assets_list_for_latest_assessment()` — Get Assets List For Latest Assessment
- `get_findings_list_by_assessment_id()` — Get Findings List By Assessment ID
- `get_findings_list_for_latest_assessment()` — Get Findings List For Latest Assessment
- `get_internal_assessment_by_id()` — Get Internal Assessment By ID
- `get_internal_assessment_list()` — Get Internal Assessment List


### `cymulate-full-kill-chain-campaign` v1.0.0 _(installed)_
_Cymulate Full Kill Chain Campaign - CART_

Cymulate Continuous Automated Red Teaming (CART) validates security controls and responses against real-world cyber attacks to stress-test defenses and identify gaps and does network pen testing, phishing awareness, real world cyber attacks. Users can use this connector to perform automated operations for managing Full Kill-Chain Campaign module data in your Cymulate account

**9 operation(s)**:

- `get_campaign_assessment_history()` — Get Campaign Assessment History
- `get_campaign_assessment_status()` — Get Campaign Assessment Status
- `get_campaign_assessments_ids()` — Get Campaign Assessments IDs
- `get_campaign_report()` — Get Campaign Report
- `get_campaign_templates()` — Get Campaign Templates
- `get_specific_campaign_assessment_report()` — Get Specific Campaign Assessment Report
- `get_technical_report_for_specific_assessment()` — Get Technical Report for Specific Assessment
- `launch_campaign_assessment()` — Launch Campaign Assessment
- `stop_campaign_assessment()` — Stop Campaign Assessment


### `domain-analysis` v1.0.0 _(installed)_
_Domain Analysis_

Whois for IPs, Domains and ASNs in addition to DGA detection and domain popularity lookup

**4 operation(s)**:

- `analyze_domain()` — Analyze Domain
- `get_domain_popularity()` — Get Domain Popularity
- `get_domain_report()` — Get Domain Report
- `whois()` — Whois


### `extrahop` v2.1.0 _(installed)_
_ExtraHop_

ExtraHop Reveal(x) network detection and response automatically discovers and classifies every transaction, session, device, and asset in your enterprise. ExtraHop helps organizations understand and secure their environments by analyzing all network interactions in real-time and leveraging machine learning to identify threats, deliver critical applications, and secure investments in the hybrid cloud. This Connector automate operations such as retrieving alerts from ExtraHop, querying log records in ExtraHop, updating watchlists in ExtraHop, etc.

**23 operation(s)**:

- `create_alert()` — Create Alert
- `create_new_detection_format()` — Create New Detection Format
- `create_tag()` — Create Tag
- `delete_detection_format()` — Delete Detection Format
- `get_alert_details()` — Get Alert Details
- `get_alerts()` — Get Alerts
- `get_detection_by_id()` — Get Detection By ID
- `get_detection_format()` — Get Detection Formats
- `get_detection_rules_hiding()` — Get Detection Hiding Rules
- `get_detections()` — Get Detections
- `get_peers_devices()` — Get Peers Devices
- `get_protocols()` — Get Protocols
- `get_watchlist()` — Get Watchlist
- `query_records()` — Query Records
- `search_detections()` — Search Detections
- `search_devices()` — Search Devices
- `search_packet()` — Search Packet
- `tag_devices()` — Tag Devices
- `update_alert()` — Update Alert
- `update_associated_ticket()` — Update Associated Ticket
- `update_detection()` — Update Detection
- `update_detection_format()` — Update Detection Format
- `update_watchlist()` — Update Watchlist


### `fortinet-fortirecon-brand-protection` v2.1.0 _(installed)_
_Fortinet FortiRecon Brand Protection_

FortiRecon is a Digital Risk Protection Service (DRPS) product that provides an outside-the-network view to the risks posed to your enterprise.

**23 operation(s)**:

- `get_code_repo_exposures()` — Get Code Repo Exposures
- `get_code_repo_matched_domains_stats()` — Get Code Repo Matched Domains Statistics
- `get_code_repos()` — Get Code Repositories
- `get_code_repos_stats()` — Get Code Repos Statistics
- `get_domain_threats()` — Get Domain Threats
- `get_domain_threats_by_id()` — Get Domain Threats By ID
- `get_domain_threats_stats()` — Get Domain Threats Statistics
- `get_executive_exposures()` — Get Executive Exposures
- `get_executive_profiles()` — Get Executive Profiles
- `get_open_bucket_exposures()` — Get Open Bucket Exposures
- `get_open_bucket_exposures_stats()` — Get Open Bucket Exposures Statistics
- `get_original_domains_stats()` — Get Original Domains Statistics
- `get_rogue_app_by_id()` — Get Rogue App By ID
- `get_rogue_apps()` — Get Rogue Apps
- `get_social_media_threats()` — Get Social Media Threats
- `get_social_media_threats_stats()` — Get Social Media Threats Statistics
- `get_tags()` — Get Tags
- `get_takedown_requests()` — Get Takedown Requests
- `update_code_repo_status()` — Update Code Repo Status
- `update_domain_threat_status()` — Update Domain Threat Status
- `update_open_bucket_exposure_status()` — Update Open Bucket Exposure Status
- `update_rogue_app_exposure_status()` — Update Rogue App Status
- `update_social_media_threat_status()` — Update Social Media Threat Status


### `google-bard` v2.0.0 _(installed)_
_Google Gemini_

Google Gemini is a conversational AI chatbot, based initially on the LaMDA family of large language models and later the PaLM LLM.

**6 operation(s)**:

- `count_message_token()` — Count Message Token
- `generate_embeddings()` — Generate Embedding
- `generate_message()` — Generate Message
- `generate_text()` — Generate Text
- `get_model_details()` — Get Model Details
- `list_models()` — Get All Model List


### `google-secops-soar` v1.0.0 _(installed)_
_Google SecOps SOAR_

Google Security Operations SOAR (Security Orchestration, Automation, and Response) is a cloud-native platform designed to help security teams detect, investigate, and respond to threats in real time.

**1 operation(s)**:

- `generic_api_call()` — Execute an API Request


### `hashicorp-vault` v2.0.0 _(installed)_
_HashiCorp Vault_

HashiCorp Vault is an identity-based secret and encryption management system. A secret is anything over which you want to control access, such as API encryption keys, passwords, and certificates.

**3 operation(s)** (+3 hidden):

- `get_credential()` — Get Credential
- `get_credentials()` — Get Credentials
- `get_credentials_details()` — Get Credentials Details


### `hikvision-nvr` v1.0.0 _(installed)_
_Hikvision NVR_

Hikvision's Network Video Recorders (NVRs) provide advanced artificial intelligence capabilities for any connected data stream, even those from conventional security cameras

**8 operation(s)**:

- `download_video()` — Download Videos Recording
- `get_channel()` — Get Channels
- `get_device_info()` — Get NVR Device Details
- `get_http_listening_servers()` — Get HTTP Listening Servers
- `get_interface()` — Get Management Interface
- `get_ntp_details()` — Get NVR Time
- `get_video_recording_details()` — Get Videos Recording Details
- `search_log()` — Search Log


### `ibm-security-qradar-soar` v1.1.0 _(installed)_
_IBM Security QRadar SOAR_

IBM Security QRadar SOAR is a software platform designed to help organizations manage and respond to security incidents effectively. It provides a comprehensive approach to incident response by integrating with various security tools and automating processes to streamline incident handling.

**12 operation(s)**:

- `close_incident()` — Close Incident
- `create_incident()` — Create Incident
- `get_all_incident_details()` — Get All Incident Details
- `get_incident_artifacts()` — Get Incident Artifacts
- `get_incident_attachment_details()` — Get Incident Attachment Details
- `get_incident_attachments()` — Get Incident Attachments
- `get_incident_details()` — Get Incident Details
- `get_incident_notes()` — Get Incident Notes
- `get_incident_simulations()` — Get Incidents Simulations
- `get_incident_tasks()` — Get Incident Tasks
- `search_incidents()` — Search Incidents
- `update_incident()` — Update Incident


### `keeper-secrets-manager` v1.0.0 _(installed)_
_Keeper Secrets Manager_

Keeper Secrets Manager is a tool designed to securely manage sensitive information, such as passwords, API keys, and other credentials, within an organization. It provides a centralized platform for storing, accessing, and sharing these secrets while maintaining strong encryption and access controls to protect sensitive data.

**3 operation(s)** (+3 hidden):

- `get_credential()` — Get Credential
- `get_credentials()` — Get Credentials
- `get_credentials_details()` — Get Credentials Details


### `microsoft-bing` v1.0.0 _(installed)_
_Microsoft Bing_

Microsoft Bing is a web search engine it provides a standard web search, as well as specialized searches for images, videos, shopping, news, maps, and other categories.

**1 operation(s)**:

- `web_search()` — Web Search


### `microsoft-winrm` v2.1.0 _(installed)_
_Microsoft WinRM_

Microsoft WinRM Connector help to connect windows endpoint and execute commands on it.

**6 operation(s)**:

- `execute_command()` — Run Command
- `execute_ps_command()` — Run Powershell Command
- `execute_ps_script()` — Run Inline Powershell Script
- `execute_script()` — Run Script
- `get_file()` — Get File
- `upload_file()` — Upload File To Endpoint


### `nozomi-networks-central-management-console` v1.1.0 _(installed)_
_Nozomi Networks Central Management Console_

The Nozomi Networks Central Management Console (CMC) consolidates OT and IoT risk monitoring and visibility from Guardian physical or virtual appliances across all of your distributed sites. It integrates with your IT security infrastructure for streamlined workflows and faster response to threats and anomalies.

**19 operation(s)**:

- `create_threat_intelligence_indicator()` — Create Indicator
- `delete_threat_intelligence_indicator()` — Delete Indicator
- `get_alert_ack_status()` — Get Alert Acknowledgement Status
- `get_alerts()` — Get Alerts List
- `get_all_threat_intelligence_indicators()` — Get All Indicators
- `get_appliances()` — Get Appliances
- `get_assertions()` — Get Assertions
- `get_assets()` — Get Assets List
- `get_captured_logs()` — Get Captured Logs
- `get_function_codes()` — Get Function Codes
- `get_health_log()` — Get Health Log
- `get_links()` — Get Links
- `get_node_cpe_changes()` — Get Node CPE Changes
- `get_node_cpes()` — Get Node CPEs
- `get_node_cves()` — Get Node CVEs
- `get_nodes()` — Get Nodes
- `import_asset()` — Import Asset
- `run_cli()` — Run CLI
- `set_alert_ack()` — Set Acknowledgment Status


### `nozomi-networks-guardian` v1.2.0 _(installed)_
_Nozomi Networks Guardian_

The Nozomi Networks Guardian platform used to monitor OT/IoT/IT networks. It combines asset discovery, network visualization, vulnerability assessment, risk monitoring and threat detection in a single solution. This integration is used to gather alerts and assets information from Nozomi.

**26 operation(s)**:

- `create_threat_intelligence_indicator()` — Create Indicator
- `delete_threat_intelligence_indicator()` — Delete Indicator
- `get_alert_ack_status()` — Get Alert Acknowledgement Status
- `get_alert_details()` — Get Alert Trace
- `get_alerts()` — Get Alerts List
- `get_all_threat_intelligence_indicators()` — Get All Indicators
- `get_appliances()` — Get Appliances
- `get_assertions()` — Get Assertions
- `get_assets()` — Get Assets
- `get_captured_logs()` — Get Captured Logs
- `get_captured_urls()` — Get Captured URLs
- `get_function_codes()` — Get Function Codes
- `get_health_log()` — Get Health Log
- `get_link_events()` — Get Link Events
- `get_links()` — Get Links
- `get_node_cpe_changes()` — Get Node CPE Changes
- `get_node_cpes()` — Get Node CPEs
- `get_node_cves()` — Get Node CVEs
- `get_nodes()` — Get Nodes
- `get_sessions()` — Get Sessions
- `get_sessions_history()` — Get Sessions History
- `get_variable_history()` — Get Variable History
- `get_variables()` — Get Variables
- `import_asset()` — Import Asset
- `run_cli()` — Run CLI
- `set_alert_ack()` — Set Acknowledgment Status


### `oletools` v1.0.0 _(installed)_
_OLETools_

OLEtools is a suite of Python tools used for analyzing Microsoft OLE2 files (also known as Structured Storage, Compound File Binary Format, or Microsoft Office documents such as .doc, .xls, .ppt, and .msg). It is particularly popular in digital forensics, malware analysis, and incident response for examining potentially malicious Office documents.

**3 operation(s)**:

- `oleid()` — Oleid
- `oleobj()` — Oleobj
- `olevba()` — Olevba


### `openbao-vault` v1.0.0 _(installed)_
_OpenBao Vault_

OpenBao Vault is an identity-based system for securely managing and distributing secrets such as API keys, passwords, and certificates.

**3 operation(s)** (+3 hidden):

- `get_credential()` — Get Credential
- `get_credentials()` — Get Credentials
- `get_credentials_details()` — Get Credentials Details


### `otbase-inventory` v1.1.0 _(installed)_
_OTbase Inventory_

Enterprise-grade OT asset management software. OTbase is the gold standard for large scale OT asset inventories. It inventories OT devices from PLCs over network switches to sensors and actuators and integrates nicely with your existing tools and platforms.

**8 operation(s)**:

- `delete_device_details()` — Delete Device Details
- `get_data_flow()` — Get Data Flow
- `get_device_details()` — Get Device Details
- `get_devices_list()` — Get Devices List
- `get_network_details()` — Get Network Details
- `get_network_list()` — Get Network List
- `get_vulnerabilities_list()` — Get Vulnerabilities List
- `get_vulnerability_details()` — Get Vulnerability Details


### `pcap-tools` v1.0.0 _(installed)_
_PCAP Tools_

PCAP Tools decodes a pcap file and converts it to human readable format

**1 operation(s)**:

- `pcap_to_json()` — PCAP To JSON


### `pdf-reader` v1.0.2 _(installed)_
_PDF Reader_

PDF Reader connector reads PDF documents and extract text.

**2 operation(s)**:

- `read_all_pages()` — Read all Pages
- `read_page()` — Read a Page


### `proofpoint-threat-response` v1.0.0 _(installed)_
_Proofpoint Threat Response_

Proofpoint Threat Response is a solution designed to help organizations manage and respond to cybersecurity threats. It provides tools and features to identify, investigate, and remediate security incidents.

**16 operation(s)**:

- `add_comment_to_incident()` — Add Comment To Incident
- `add_to_list()` — Add Indicators
- `add_user_to_incident()` — Add User To Incident
- `block_domain()` — Block Domain
- `block_hash()` — Block File Hash
- `block_ip()` — Block IP Addresses
- `block_url()` — Block URL
- `close_incident()` — Close Incident
- `delete_indicator()` — Delete Indicator
- `get_incident()` — Get Incident By ID
- `get_incidents()` — Get Incidents List
- `get_list()` — Get Indicators List
- `ingest_alert()` — Ingest Alert
- `search_indicator()` — Search Indicator
- `update_comment_to_incident()` — Update Comment To Incident
- `verify_quarantine()` — Verify Quarantine


### `soc-radar` v1.0.0 _(installed)_
_SOCRadar_

Threat Intelligence enriched with External Attack Surface Management and Digital Risk Protection Services

**4 operation(s)**:

- `change_status()` — Change Status
- `get_incident()` — Get Incident
- `get_incidents()` — Get Incidents
- `threat_analysis()` — Threat Analysis


### `text-utility` v1.1.0 _(installed)_
_Text Utility_

Utilities to process text with features like sentences similarity, OCR and macro extractions from MS Office documents

**3 operation(s)**:

- `extract_macros()` — Extract Macros
- `image_to_text()` — Image to Text OCR
- `sentence_similarity()` — Get Sentences Similarity


---

## Utilities

### `atlassian-confluence-cloud` v1.0.0 _(installed)_
_Atlassian Confluence Cloud_

Atlassian Confluence is a collaborative workspace where teams create, organize, and share project documents, ideas, and knowledge in one central place.

**13 operation(s)**:

- `create_custom_content()` — Create Custom Content
- `create_footer_comment()` — Create Footer Comment
- `create_space()` — Create Space
- `delete_custom_content()` — Delete Custom Content
- `get_attachments()` — Get Attachments
- `get_audit_records()` — Get Audit Records
- `get_custom_contents()` — Get Custom Contents
- `get_groups()` — Get Groups
- `get_spaces()` — Get Spaces
- `get_specific_custom_content()` — Get Specific Custom Content
- `get_specific_space_details()` — Get Specific Spaces Details
- `get_users()` — Get Users
- `update_custom_content()` — Update Custom Content


### `bpmn-to-playbooks` v1.0.3 _(installed)_
_BPMN_

Convert BPMN XML to FortiSoar Playbooks

**1 operation(s)**:

- `bpmntoplaybooks()` — Import BPMN Playbook


### `cicd-utils` v1.2.0 _(installed)_
_CICD Utils_

CICD Utils provides out of the box actions for CICD solution pack

**5 operation(s)**:

- `export_fortisoar_template()` — Export FortiSOAR Template
- `import_fortisoar_template()` — Import FortiSOAR Template
- `review_import_fortisoar_template()` — Review & Import FortiSOAR Template
- `split_export_templates()` — Split Export Template
- `unzip_export_template()` — Unzip Export Template


### `cisa-advisory` v1.1.0 _(installed)_
_CISA Advisory_

CISA Advisory connector fetches the Advisory and Known Exploited Vulnerability (KEV) CVE published by CISA.

**5 operation(s)**:

_investigation_
- `get_advisory(advisory_type: select, [date_filter: select])` — Get Advisory
- `get_advisory_by_product(advisory_type: select, vendor: text, product: text, [version: text], vendorSimilarityThreshold: integer, productSimilarityThreshold: integer)` — Get Advisory By Product
- `get_advisory_by_vendor(advisory_type: select, vendor: text, similarityThreshold: integer)` — Get Advisory By Vendor
- `get_advisory_by_year(advisory_type: select)` — Get Advisory By Year
- `get_known_exploited_vulnerability_cves()` — Get Known Exploited Vulnerability CVEs


### `cyops_utilities` v3.7.0 _(installed, system)_
_Utilities_

Includes functions to Fetch, Create or Update records and multiple other utility functions for facilitating automation

**55 operation(s)** (+8 hidden):

_investigation_
- `create_store_key(name: text, type: text, [value: text], [notes: text])` — Create Store Key
- `delete_store_key(name: text)` — Delete Store Key
- `get_ioc_parsing_regex()` — Get IOC Parsing Regex
- `get_store_keys([key_name: text])` — Get Store Keys
- `make_fcp_request(url: text, [method: select], [body: json])` — Make API Call
- `read_pem_certificate(file_iri_or_path: text)` — File: Read PEM Certificate
- `reverse_dns_lookup(ip_address: text)` — Reverse DNS Lookup
- `update_store_key(key_name: text, [name: text], [value: text], [type: text], [notes: text])` — Update Store Key
- `xor_byte_file_decryption(input_file: select, output_file: text, key_to_decrypt: text)` — File: XOR Decryption

- `api_call(url: text, [method: select], [params: textarea], [body: textarea], [headers: textarea], [is_upload_file: checkbox], [verify: checkbox], [username: text], [password: password], [auth_config: textarea])` — Utils: Make REST API Call
- `arrow_timestamp_diff(time_stamp_1: text, time_stamp_2: text)` — Utils: Compute Time Difference
- `attach_indicators(iri: text, indicators: textarea, [source: text], [related_field: text])` — FSR: Attach Indicators to Record
- `convert_from_json(data: text, [save_to_file: checkbox])` — Utils: Convert JSON to CSV
- `convert_periodic_time_to_minutes(periodic_time: text)` — Utils: Convert String Time to Minutes
- `convert_to_json(type: select, file_type: select)` — Utils: Convert XML, CSV, XLS or XLSX Files to Dictionary
- `create_cyops_attachment(filename: text, name: text, [description: text], [request_headers: text], [multipart_headers: text], [extra_multipart_fields: text])` — File: Create Attachment from File
- `create_file_from_string(contents: textarea, [filename: text], [mimetype: text])` — File: Create File from String
- `createmacro_xf(macro: text, value: textarea)` — Create Global Variable
- `download_file_from_cyops(iri: text)` — File: Compute Hash
- `download_file_from_cyops_alias(iri: text)` — File: Download File From FortiSOAR
- `download_file_from_url(url: text, [username: text], [password: password], [request_headers: textarea])` — File: Download File from URL
- `evaluate_email_template(email_template: select)` — FSR: Evaluate Email Template Expressions
- `extract_artifacts(data: textarea, [whitelist: textarea], [case_sensitive: checkbox], [private_whitelist: checkbox], [override_regex: checkbox])` — FSR: Extract Artifacts from String (Deprecated)
- `extract_artifacts_new(data: textarea, [whitelist: textarea], [case_sensitive: checkbox], [private_whitelist: checkbox], [extract_defang_indicators: checkbox])` — FSR: Extract Artifacts from String
- `extract_email_metadata_new(filepath: text, filetype: select, [parse_inline_image: checkbox])` — Email: Extracts email's metadata from email file
- `format_richtext(value: richtext)` — Utils: Format as RichText (Markdown)
- `format_richtext_html(value: html)` — Utils: Format as RichText (HTML)
- `html_table_to_dictionary(html: textarea)` — Utils: Convert HTML Table to Dictionary
- `insert_cyops_resource(iri: text, body: textarea)` — FSR: Create Record
- `ip_cidr_check(ip_address: text, cidr: text)` — Utils: Is IP in CIDR
- `json_to_html(data: textarea, [display: select], [show_button: checkbox], [styling: checkbox])` — Utils: Convert JSON into a HTML Table
- `make_cyops_request(iri: text, method: select, [body: textarea])` — FSR: Make FortiSOAR API Call
- `map_json(json_data: textarea, patch: textarea)` — Utils: Patch JSON
- `markdown_to_html(markdown_string: textarea)` — Utils: Convert Markdown string to HTML
- `no_op()` — Utils: No Operation
- `parse_cef(cef_input: textarea)` — FSR: Parse CEF String to JSON.
- `query_cyops_resource(resource: text, query: textarea)` — FSR: Find Record
- `raise_exception(msg: text)` — Utils: Raise Exception
- `unzip_protected_file(type: select, [password: password])` — File: Unzip
- `update_cyops_resource(iri: text, body: textarea)` — FSR: Update Record
- `updatemacro(macro: select, value: textarea)` — FSR: Create/Update Global Variables
- `updatemacro_xf(uuid: text, macro: text, value: textarea)` — Update Global Variable
- `upload_file_to_cyops(file_path: text, filename: text, [create_attachment: checkbox])` — File: Upload a file in the system and Create an Attachment
- `upload_file_to_url(type: select, url: text, [username: text], [password: password], [request_headers: textarea], [multipart_headers: textarea], [extra_multipart_fields: textarea], [download_auth: text], [download_url: text])` — File: Upload File to URL
- `upsert_cyops_resource(iri: text, resource: textarea, fields: text, [Ignore_missing_fields: text])` — FSR: Upsert Record
- `xml_to_dictionary(xml: textarea)` — Utils: Convert XML to Dictionary
- `zip_and_protect_file(filename: text, target_filename: text, [password: password], [compress_level: select])` — File: Zip


### `database` v2.2.1 _(installed)_
_Database_

Database connector can be used to connect to a database and then query the database and retrieve data. You can connect to multiple databases by setting up multiple configurations.

**1 operation(s)**:

- `db_query()` — Query DB


### `debug_utils` v1.1.0 _(installed)_
_Debug Utils_

Debug Utils connector can be used to debug connector issues. In production environment is difficult to find the reason for the issue, whether it is with the connector setup or the connector code. To enable faster resolution of issues, the user can use this connector to generate the curl for an API request that can then be shared with the development team.

_(no operations cataloged)_

### `excel-tools` v1.0.0 _(installed)_
_Excel Tools_

Utility to manage excel files

**5 operation(s)**:

- `list_sheets()` — List Sheets
- `read_column_by_name()` — Read Column By Name
- `read_sheet()` — Read Sheet
- `update_cell()` — Update Cell
- `update_column()` — Update Column


### `exploit-prediction-scoring-system` v1.0.0 _(installed)_
_Exploit Prediction Scoring System (EPSS)_

The Exploit Prediction Scoring System (EPSS) is a framework used in cybersecurity to assess the likelihood of a vulnerability being exploited by adversaries. It leverages various factors, such as the characteristics of the vulnerability, its accessibility, and historical data on similar vulnerabilities, to generate a prediction score. The EPSS aids security analysts and organizations in prioritizing their vulnerability management efforts, allowing them to focus on high-risk vulnerabilities that are more likely to be exploited. By using EPSS, organizations can effectively allocate their resources, mitigate potential threats, and enhance their overall security posture.

**2 operation(s)**:

_investigation_
- `get_epss_score(scope: select, [byDate: datetime], [fields: text], [limit: integer], [offset: integer], [sort: text], [envelope: checkbox], [pretty: checkbox], [orderResult: checkbox])` — Get EPSS Score
- `get_epss_score_by_cve_id([scope: select], cve: text, [byDate: datetime], [fields: text], [sort: text], [envelope: checkbox], [pretty: checkbox], [orderResult: checkbox])` — Get EPSS Score By CVE ID


### `file-content-extraction` v1.3.1 _(installed)_
_File Content Extraction_

Utility to Extract Text, Artifacts and Metadata from almost any file. Internet connectivity is required for the connector to download dependent packages

**5 operation(s)**:

_investigation_
- `create_xslx_file_from_json_data(fileName: text, jsonData: object, [xLSXFields: text])` — Create XLSX File as Attachment From JSON Data
- `extract_indicators(file_iri: text)` — Extract Artifacts
- `extract_indicators_from_file(file_iri: text)` — Extract Artifacts Extended
- `extract_text(file_iri: text, [html_output_format: checkbox])` — Extract Text
- `get_backend_config([verbose_config: checkbox])` — Get Backend Config


### `floodlight` v1.0.0 _(installed)_
_Floodlight_

Floodlight Connector which utilizes Java OpenFlow controller

**4 operation(s)**:

- `block_ip()` — Block IP
- `block_mac()` — Block MAC Address
- `unblock_ip()` — Unblock IP
- `unblock_mac()` — Unblock MAC Address


### `fsr-agent-communication-bridge` v1.2.0 _(installed, system)_
_FSR Agent Communication Bridge_

Establishes and enables a network communication bridge (web server on agent) that allows users to provide manual inputs from an unauthenticated page spun and hosted within the agent's network premises.

**2 operation(s)** (+2 hidden):

_investigation_
- `resume_playbook(web_data: json, token: text)` — Resume Playbook

_miscellaneous_
- `fetch_maunal_input_details(manual_input_id: integer, token: text)` — Fetch Manual Input Details


### `fuzzy-search` v1.0.0 _(installed)_
_Fuzzy Search_

Connector provides actions to find relevant results even when they do not know the exact term by filtering the provided JSON data and also searches for keywords within the provided text using fuzzy logic.

**2 operation(s)**:

- `filter_json_by_key_value()` — Filter JSON by Key Value
- `search_keyword_in_text()` — Search Keyword In Text


### `gcp-ca-service` v1.0.1 _(installed)_
_GCP Certificate Authority Service_

Certificate Authority Service is a highly available and scalable Google Cloud service that enables you to simplify, automate, and customize the deployment, management, and security of private certificate authorities (CA)

**4 operation(s)**:

- `csr()` — Submit CSR
- `get_ca_crl()` — Get CA and CRL
- `list_certificate_authorities()` — Get Certificate Authorities
- `revoke_certificate()` — Revoke Certificate


### `google-calendar` v1.0.0 _(installed)_
_Google Calendar_

Google Calendar is a web-based calendar service developed by Google, allowing users to organize their schedules, appointments, and events seamlessly. It offers a range of features designed to help users manage their time effectively, collaborate with others, and stay organized across various devices.

**8 operation(s)**:

- `delete_access_control_rule()` — Delete Access Control Rule
- `delete_calendar_list()` — Delete Calendar List
- `get_access_control_rule_details()` — Get Access Control Rule Details
- `get_calendar_access_control_list()` — Get Calendar Access Control List
- `get_calendar_list()` — Get All Calendar List
- `get_calendar_list_details()` — Get Calendar List Details
- `get_event_details()` — Get Event Details
- `get_events_list()` — Get Events List


### `google-cloud-functions` v1.0.0 _(installed)_
_Google Cloud Functions_

Google Cloud Functions is a serverless execution environment for building and connecting cloud services.

**5 operation(s)**:

- `get_access_control_policy()` — Get Access Control Policy
- `get_function_details()` — Get Function Details
- `get_functions_list()` — Get Functions List
- `get_locations_list()` — Get Locations List
- `set_access_control_policy()` — Set Access Control Policy


### `google-docs` v1.0.0 _(installed)_
_Google Docs_

Google Docs is a cloud-based word processing application developed by Google. It allows users to create, edit, and collaborate on documents in real-time over the internet.

**3 operation(s)**:

- `create_document()` — Create Document
- `get_document_details()` — Get Document Details
- `update_documents()` — Update Documents


### `google-sheets` v1.0.0 _(installed)_
_Google Sheets_

Google Sheets is a web-based application that enables users to create, update and modify spreadsheets and share the data online in real time.

**10 operation(s)**:

- `add_row_to_spreadsheet()` — Add Row to a Spreadsheet
- `clear_rows_from_spreadsheet()` — Clear Rows from a Spreadsheet
- `clear_rows_of_spreadsheet_by_filter()` — Clear Rows of Spreadsheet by Filter
- `create_spreadsheet()` — Create Spreadsheet
- `filter_spreadsheet()` — Filter Spreadsheet
- `get_spreadsheet_details()` — Get Spreadsheet Details
- `get_spreadsheet_rows()` — Get Spreadsheet Rows
- `move_sheet()` — Move Sheet
- `update_rows_in_spreadsheet()` — Updates Rows in a Spreadsheet
- `update_rows_of_spreadsheet_by_filter()` — Update Rows of Spreadsheet by Filter


### `hello-world` v1.1.1 _(installed)_
_Hello World_

A minimal example connector for learning FortiSOAR connector structure. Returns simple greetings and messages.

**3 operation(s)**:

_investigation_
- `reverse_text(input_text: text)` — Reverse Text
- `say_hello(name: text)` — Say Hello

- `add_numbers(number_a: integer, number_b: integer)` — Add Numbers


### `jscode-snippet` v1.0.0 _(installed)_
_JS Code Snippet_

JS code snippet integration for FortiSOAR allows you to seamlessly incorporate JavaScript code snippets into your playbooks. With this integration, you can harness the power of JavaScript to enhance your automation and response workflows, enabling greater flexibility and customization.

**1 operation(s)**:

- `run_js_code()` — Execute JavaScript Code


### `json-convert` v1.0.0 _(installed)_
_JC - Parse Command Output_

Convert the output of many commands and file-types to structured objects using the open-source JSON Convert (JC) library. The JC project details can be found at https://github.com/kellyjonbrazil/jc

**2 operation(s)** (+1 hidden):

- `convert()` — Convert


### `macvendors` v1.0.0 _(installed)_
_MACVendors_

MACVendors Connector provides vendor name given MAC Address

**1 operation(s)**:

- `mac_lookup()` — MAC Address Lookup


### `neutrinoapi` v1.0.0 _(installed)_
_NeutrinoAPI_

NeutrinoAPI connector to pull information about potentially malicious or dangerous IP addresses. Connector supports the automated operations like Analyze IP Address, Get IP Information and Get IP Address Blocklist Status

**3 operation(s)**:

- `ip_blocklist()` — Get IP Address Blocklist Status
- `ip_info()` — Get IP Address Information
- `ip_probe()` — Analyze IP Address


### `ocr-space` v1.0.0 _(installed)_
_OCRSpace_

The OCR API provides a simple way of parsing images and multi-page PDF documents (PDF OCR) and extract text results. This connector facilitates automated operations related to extracting data from image or document.

**1 operation(s)**:

- `parse_image()` — Parse Image


### `qrcode-tools` v1.0.2 _(installed)_
_QR Code Tools_

QR Code Tools helps users working with QR and Bar codes

**1 operation(s)**:

- `read_qr_code()` — Read QR Code


### `remote-fortisoar` v2.0.0 _(installed)_
_Remote FortiSOAR_

This connector facilitates automated interactions, with a FortiSOAR endpoint using FortiSOAR playbooks. Add the Remote FortiSOAR connector as a step in FortiSOAR playbooks and run REST API operations on FortiSOAR environments other than your own FortiSOAR environment

**2 operation(s)**:

- `make_api_call()` — Make an API call
- `upload_file()` — Upload file to FortiSOAR


### `screenshot` v1.0.1 _(installed)_
_Remote Screenshot_

Screenshot connector provide you functionality to take screenshot of URLs, Emails, MSG Files, and EML Files.

**3 operation(s)**:

_investigation_
- `screenshot_eml_or_msg_file(file_type: select, [screenshot_name: text], screenshot_size: select, [create_attachment: checkbox])` — Screenshot EML OR MSG File Content
- `screenshot_mail(mail_html_body: text, [screenshot_name: text], screenshot_size: select, [create_attachment: checkbox])` — Screenshot Email Content
- `screenshot_url(url: text, [screenshot_name: text], screenshot_size: select, [create_attachment: checkbox])` — Screenshot URL


### `soap` v2.4.1 _(installed)_
_SOAP_

Steps related to making SOAP requests

**4 operation(s)** (+2 hidden):

- `soap_call()` — SOAP Call (Generic)
- `soap_client()` — SOAP Call


### `time-series-chart-utilities` v1.0.0 _(installed)_
_Time Series Chart Utilities_

When using the Time Series Chart Solution Pack, this connector is used by the included playbooks to facilitate the creation of data-over-time or time series charts. The included functions include building a list of datetime-buckets, as well as various utilities to process the output of dataset queries for use by the Time Series Widget.

**4 operation(s)**:

- `assemble_query_time_windows()` — Assemble Query Time Windows
- `combine_query_results_into_data_columns()` — Combine Query Results into Data Columns
- `flatten_data_sets_and_groups()` — Flatten Data Sets and Groups
- `format_data_set_output_with_fieldgrouped()` — Format Data Set Output with Field-Grouped


### `ultipro` v1.0.0 _(installed)_
_Ultipro_

This connector is capable of querying Ultipro for Employee, Job, and Phone details.

**5 operation(s)**:

- `findEmployeePhone()` — Find Employee Phones
- `getAllCompanyEmployees()` — Get All Employees
- `getEmploymentDetails()` — Get Employment Details
- `getPersonDetails()` — Get Person Details
- `getPhoneInformationByEmployeeIdentifier()` — Get Employee Phone Information


### `unshortenme` v1.0.0 _(installed)_
_Unshorten.me_

Unshorten.me connector can un-shorten URLs created by different services

**1 operation(s)**:

- `unshorten_url()` — Unshorten URL


### `url-expander` v1.0.0 _(installed)_
_URL Expander_

URL Expander allows to retrieve original URL from shortened provided by various shortening services

**1 operation(s)**:

- `expand_url()` — Expand URL


### `web-scraper` v1.0.0 _(installed)_
_Web Scraper_

Web scraping is data scraping used for extracting data from websites. This connector facilitates automated operations related to extracting data from websites.

**2 operation(s)**:

- `get_screenshot()` — Get Web Page Screenshot
- `get_web_page_source()` — Get Web Page Source


### `web-screenshot` v1.0.0 _(installed)_
_Web Screenshot_

Web Screenshot provides a service to take screenshot or thumbnail of any online web page in a couple of second.

**1 operation(s)**:

- `take_screenshot()` — Take Screenshot


---

## Vulnerability Management

### `nist-nvd` v1.0.2 _(installed)_
_NIST National Vulnerability Database_

The NIST National Vulnerability Database (NVD) is the U.S. government repository of standards based vulnerability management data represented using the Security Content Automation Protocol (SCAP). This data enables automation of vulnerability management, security measurement, and compliance. The NVD includes databases of security checklist references, security related software flaws, misconfigurations, product names, and impact metrics.

**5 operation(s)**:

_investigation_
- `cpe_search([filterBy: select], [useLastModDate: checkbox], [startIndex: integer], [resultsPerPage: integer])` — CPE Search
- `cve_search([useCveId: checkbox], [useCpeName: checkbox], [useCweId: checkbox], [useCVSSv2: checkbox], [useCVSSv3: checkbox], [useSearchFlags: multiselect], [usePublishDate: checkbox], [useLastModDate: checkbox], [startIndex: integer], [resultsPerPage: integer])` — Advance CVE Search
- `cve_search_by_keywords(keywordSearch: text, [startIndex: integer], [resultsPerPage: integer])` — CVE Search by Keywords
- `get_cve_change_history([cveId: text], [eventName: select], [useChangeDate: checkbox], [startIndex: integer], [resultsPerPage: integer])` — Get CVE Change History
- `get_specific_cve_details(cveId: text)` — Get Specific CVE ID Details


### `tenable-io` v1.4.0 _(installed, ingestion)_
_Tenable.io_

Tenable.io provide actions like get all scans, trigger scan, scan specific assets, asset specific vulnerabilities, export assets and export vulnerabilities from Tenable.io

**18 operation(s)**:

_investigation_
- `cancel_asset_export_job(export_uuid: text)` — Cancel Asset Export Job
- `cancel_vuln_export_job(export_uuid: text)` — Cancel Vulnerability Export Job
- `download_asset_export_chunk(export_uuid: text, chunk_id: integer)` — Download Asset Export Chunk
- `download_vuln_export_chunk(export_uuid: text, chunk_id: integer)` — Download Vulnerability Export Chunk
- `get_asset_export_status(export_uuid: text)` — Get Asset Export Status
- `get_asset_vulnerabilities(asset_id: text)` — List Asset's Vulnerabilities
- `get_host_details(scan_uuid: text, host_id: integer, [history_id: integer], [history_uuid: text])` — Get Host Details
- `get_plugin_details(plugin_id: integer)` — Get Plugin Information
- `get_scan_assets(scan_id: integer)` — List Scan's Assets
- `get_scan_history(scan_id: text, [limit: integer], [offset: integer], [exclude_rollover: checkbox])` — Get Scan History
- `get_scans(days: select)` — List Scans
- `get_vuln_details(plugin_id: integer)` — Get Vulnerability Information
- `get_vuln_export_status(export_uuid: text)` — Get Vulnerability Export Status
- `list_asset_export_jobs()` — List Asset Export Jobs
- `list_vuln_export_jobs()` — List Vulnerability Export Jobs
- `submit_asset_export_job(chunk_size: integer, [last_assessed: datetime])` — Submit Asset Export Job
- `submit_vuln_export_job(num_assets: integer, [cidr_range: text], [severity: multiselect], [since: datetime], [state: multiselect])` — Submit Vulnerability Export Job
- `trigger_scan(scan_id: text, [alt_targets: text])` — Trigger Scan


---

## Vulnerability and Risk Management

### `bitcoin-abuse-db` v1.0.0 _(installed)_
_Bitcoin Abuse DB_

BitcoinAbuse.com is a public database of bitcoin addresses used by scammers, hackers, and criminals. This connector lets you tracking bitcoin addresses used by ransomware, blackmailers, fraudsters, etc.

**4 operation(s)**:

- `check_given_address()` — Check Address
- `get_all_reports()` — Get Complete Download
- `get_lookup_abuse_types()` — Get Lookup Abuse Types
- `get_lookup_distinct_reports()` — Get Lookup Distinct Reports


### `blueliv-threatcompass` v1.0.0 _(installed)_
_Blueliv ThreatCompass_

Blueliv ThreatCompass systematically looks for information about companies,products, people, brands, logos, assets, technology and other information, depending on your needs. Blueliv ThreatCompass allows you to monitor and track all this information to keep your data, your organization and its employees safe

**9 operation(s)**:

- `get_module_labels()` — Get Module Labels
- `get_resource_by_id()` — Get Resource by ID
- `get_resource_list()` — Get Resource List
- `update_resource_fav()` — Update Resource FAV
- `update_resource_label()` — Update Resource Label
- `update_resource_rating()` — Update Resource Rating
- `update_resource_read_status()` — Update Resource Read Status
- `update_resource_status()` — Update Resource Status
- `update_resource_tlp()` — Update Resource TLP


### `circl-cve-search` v1.0.0 _(installed)_
_Circl CVE Search_

This app searches publicly known information from security vulnerabilities in software and hardware along with their corresponding exposures on CIRCL CVE database and returns the findings.

**6 operation(s)**:

- `browse_products()` — Get Products
- `browse_vendors()` — Get Vendors
- `current_cve_dbinfo()` — Get CVE DB Info
- `last_updated_cves()` — Get Last Updated CVEs
- `search_per_id()` — Get CVE Details
- `search_per_product()` — Search Specific Product


### `fullhunt` v1.0.0 _(installed)_
_FullHunt_

FullHunt enables companies to discover all of their attack surfaces, monitor them for exposure and continuously scan them for the latest security vulnerabilities.

**3 operation(s)**:

- `get_domain_details()` — Get Domain Details
- `get_specific_host_details()` — Get Details of a Specific Host
- `get_subdomain_of_domain()` — Get Subdomains of a Domain


### `git-guardian` v1.0.0 _(installed)_
_GitGuardian_

GitGuardian is a cybersecurity platform that specializes in detecting and preventing the exposure of sensitive information in source code repositories, specifically Git repositories. It is designed to help organizations and developers protect their code and prevent the accidental or unauthorized exposure of credentials, API keys, tokens, and other sensitive data that may be present in code repositories.

**10 operation(s)**:

- `assign_a_secret_incident()` — Assign Secret Incident 
- `content_scan()` — Scan Documents Content
- `get_members_list()` — Get Members List
- `list_secret_incidents()` — Get Secret Incidents List
- `list_secret_occurrences()` — Get Secret Occurrences List
- `list_sources()` — Get Sources List
- `resolve_a_secret_incident()` — Resolve Secret Incident 
- `retrieve_a_secret_incident()` — Get Secret Incident Details
- `unassign_a_secret_incident()` — Unassign Secret Incident 
- `update_a_secret_incident()` — Update Secret Incident


### `git-guardian-enterprise` v1.0.0 _(installed)_
_GitGuardian Enterprise_

GitGuardian Enterprise is a security platform designed to detect, monitor, and remediate secrets (like API keys, passwords, and tokens) and sensitive data exposed in source code, CI/CD pipelines, containers, and developer environments.

**23 operation(s)**:

- `create_incident_secret_shared_link()` — Create Incident Secret Shared Link
- `create_keyword()` — Create Keyword
- `delete_incident_secret_shared_link()` — Delete Incident Secret Shared Link
- `delete_keyword()` — Delete Keyword
- `execute_an_api_call()` — Execute an API Request
- `export_keywords()` — Export Keywords
- `get_all_audit_logs()` — Get All Audit Logs
- `get_all_git_users()` — Get All Git Users
- `get_all_incident_keywords()` — Get All Incident Keywords
- `get_all_incident_secrets()` — Get All Incident Secrets
- `get_all_keywords()` — Get All Keywords
- `get_audit_log_actors_types()` — Get Audit Log Actors/Types
- `get_audit_log_details()` — Get Audit Log Details
- `get_git_user_details()` — Get Git User Details
- `get_incident_keyword_details()` — Get Incident Keyword Details
- `get_incident_keyword_note()` — Get Incident Keyword Note
- `get_incident_secret_details()` — Get Incident Secret Details
- `get_incident_secret_note()` — Get Incident Secret Note
- `get_keyword_details()` — Get Keyword Details
- `rotate_incident_secret_shared_link()` — Rotate Incident Secret Shared Link
- `update_incident_keyword_status()` — Update Incident Keyword Status
- `update_incident_secret_status()` — Update Incident Secret Status
- `update_keyword_details()` — Update Keyword Details


### `hacker-target` v1.0.0 _(installed)_
_Hacker Target_

Hacker Target provide online IP Tools that can be used to quickly get information about IP Addresses, Web Pages and DNS records.

**9 operation(s)**:

- `dns_lookup()` — DNS Lookup
- `geoip_lookup()` — GeoIP Lookup
- `get_all_links_from_page()` — Get All Links from Page
- `get_http_header()` — Get HTTP Header
- `mtr_traceroute()` — MTR Traceroute
- `reverse_dns_lookup()` — Reverse DNS Lookup
- `reverse_ip_lookup()` — Reverse IP Lookup
- `test_ping()` — Test Ping
- `whois_lookup()` — Whois Lookup


### `kenna` v1.0.0 _(installed)_
_Kenna_

Kenna is risk-based intelligent vulnerability management platform that enables InfoSec teams to prioritize and remediate vulnerabilities faster. This connector facilitates the automated operations around vulnerabilities, connectors, assets and users

**17 operation(s)**:

- `create_asset()` — Create Asset
- `create_user()` — Create User
- `create_vulnerability()` — Create Vulnerability
- `delete_user()` — Delete User
- `delete_vulnerability()` — Delete Vulnerability
- `get_connectors()` — Get Connectors
- `list_assets()` — List Assets
- `list_fixes()` — List Fixes
- `list_users()` — List Users
- `list_vulnerabilities()` — List Vulnerabilities
- `run_connector()` — Run Connector
- `search_asset()` — Search Asset
- `search_fixes()` — Search Fixes
- `search_vulnerabilities()` — Search Vulnerabilities
- `update_asset()` — Update Asset
- `update_user()` — Update User
- `update_vulnerability()` — Update Vulnerability


### `microsoft-defender-vulnerability-management` v1.0.0 _(installed)_
_Microsoft Defender Vulnerability Management_

Microsoft's Defender Vulnerability Management is a built-in module in Microsoft Defender for Endpoint that can discover vulnerabilities and misconfigurations in near real time, prioritize vulnerabilities based on the threat landscape and detections in your organization.

**5 operation(s)**:

- `get_specific_cve_details()` — Get Specific CVE ID Details
- `get_vulnerability_by_id()` — Get Vulnerability By CVE ID
- `list_devices_by_vulnerability()` — Get Devices By Vulnerability
- `list_vulnerabilities()` — Get All Vulnerabilities
- `list_vulnerabilities_by_machine_and_software()` — Get Vulnerabilities By Machine And Software


### `nessus` v1.0.0 _(installed)_
_Nessus_

Nessus provide actions like get all scans, trigger scan, scan specific assets and asset specific vulnerabilities

**6 operation(s)**:

- `get_asset_vulnerabilities()` — List Asset's Vulnerabilities
- `get_plugin_details()` — Get Plugin Information
- `get_scan_assets()` — List Scan's Assets
- `get_scans()` — List Scans
- `get_vuln_details()` — Get Vulnerability Information
- `trigger_scan()` — Trigger Scan


### `qualys` v1.1.0 _(installed)_
_Qualys_

Qualys provides cloud security, compliance and protection of IT assets and web applications. This connector facilitates the automated operations for vulnerability management, policy compliance, asset management

**47 operation(s)**:

- `add_ip()` — Add Assets
- `create_asset_group()` — Create Asset Group
- `create_static_search_list()` — Create Static Search List
- `create_vm_option_profile()` — Create VM Option Profile
- `delete_asset_group()` — Delete Asset Group
- `delete_report()` — Delete Report
- `delete_static_search_list()` — Delete Static Search List
- `delete_vm_option_profile()` — Delete VM Option Profile
- `edit_asset_group()` — Edit Asset Group
- `fetch_pc_scan()` — PC - Fetch Scan
- `fetch_report()` — Download Saved Report
- `fetch_vm_scan()` — VM - Fetch Scan
- `get_asset_search_report()` — Get Asset Search Report
- `launch_compliance_policy_report()` — Launch Compliance Policy Report
- `launch_compliance_report()` — Launch Compliance Report
- `launch_host_based_findings_report()` — Launch Host Based Findings Report
- `launch_patch_report()` — Launch Patch Report
- `launch_pc_scan()` — PC - Launch Scan
- `launch_remediation_report()` — Launch Remediation Report
- `launch_scan_based_findings_report()` — Launch Scan Based Findings Report
- `launch_scheduled_report()` — Launch Scheduled Report
- `launch_score_card()` — Launch Scorecard Report
- `launch_vm_scan()` — VM - Launch Scan
- `list_excluded_host()` — Get Excluded Host List
- `list_group()` — Get Asset Group List
- `list_host()` — Get Scanned Host List
- `list_host_detection()` — Get Host Detection List
- `list_ip()` — Get Asset List
- `list_option_profile()` — Get Option Profiles
- `list_pc_scan()` — PC - Get Scan List
- `list_report()` — Get Report List
- `list_report_template()` — Get Report Template List
- `list_scanner_appliance()` — Get Scanner Appliance
- `list_schedule_scan()` — Get Schedule Scan List
- `list_scheduled_report()` — Get Scheduled Report List
- `list_static_search()` — Get Static Search List
- `list_virtual_host()` — Get Virtual Host List
- `list_vm_option_profile()` — Get VM Option Profile List
- `list_vm_scan()` — VM - Get Scan List
- `list_vulnerability()` — Get Vulnerability List
- `manage_excluded_host()` — Manage Excluded Host
- `manage_pc_scan()` — PC - Manage Scan
- `manage_virtual_host()` — Manage Virtual Host
- `update_ip()` — Update Asset
- `update_static_search_list()` — Update Static Search List
- `update_vm_option_profile()` — Update VM Option Profile
- `vm_scan_action()` — VM - Manage Scan


### `qualys-web-application-scanner` v2.0.0 _(installed)_
_Qualys Web Application Scanning(WAS)_

Qualys Web Application Scanning (WAS) is a robust cloud-based application security product that continuously discovers, detects, and catalogs web applications and APIs.

**22 operation(s)**:

- `count_webapp()` — Get Web Applications Count
- `create_tag()` — Create Tag
- `create_web_app()` — Create Web Application
- `delete_scan()` — Delete Scan
- `delete_tag()` — Delete Tag
- `delete_webapp()` — Delete Web Applications
- `download_report()` — Download Report
- `get_scan_details()` — Get Scan Details
- `get_schedule_details()` — Get Schedule Details
- `get_webapp_details()` — Get Web Application Details
- `launch_scans()` — Launch Scans
- `retrieve_scan_results()` — Get Scan Results
- `retrieve_scan_status()` — Get Scan Status
- `scan_count()` — Get Scan Count
- `search_option_profiles()` — Search Option Profiles
- `search_reports()` — Search Reports
- `search_scans()` — Search Scans
- `search_schedule()` — Search Schedule
- `search_tags()` — Search Tags
- `search_users()` — Search Users
- `search_webapp()` — Search Web Applications
- `update_tag()` — Update Tag


### `rapid7-insightvm` v1.2.0 _(installed)_
_Rapid7 InsightVM_

The Rapid7 InsightVM platform integrates Rapid7’s library of Nexpose vulnerability research, Metasploit exploit knowledge, global attacker behavior, internet-wide scanning data, and threat exposure analytics. InsightVM takes advantage of this powerful analytics platform to automatically collect, monitor, and analyze your network for new and existing risks. This connector facilitates automated operations to fetch information about Asset, Site, Scan, Exploits and Vulnerability

**19 operation(s)**:

- `create_site_scan_schedules()` — Create Site Scan Schedules
- `delete_site_scan_schedule()` — Delete Site Scan Schedule
- `get_asset()` — Get Asset(s)
- `get_asset_groups()` — Get Asset Groups
- `get_asset_vuln()` — Get Asset Vulnerability
- `get_exploit_details()` — Get Exploit Details
- `get_exploitable_vuln()` — Get Exploitable Vulnerabilities
- `get_exploits()` — Get Exploits
- `get_scan()` — Get Scan
- `get_scan_engines()` — Get Scan Engines
- `get_scan_templates()` — Get Scan Templates
- `get_site()` — Get Site
- `get_site_scan_engines()` — Get Site Scan Engines
- `get_site_scan_schedule()` — Get Specified Scan Schedule
- `get_site_scan_schedules()` — Get Scan Schedules
- `get_site_scan_templates()` — Get Site Scan Templates
- `get_software()` — Get Softwares on Asset
- `get_vulns()` — Get Vulnerability
- `launch_site_scan()` — Launch Site Scan


### `rapid7-nexpose` v1.3.0 _(installed)_
_Rapid7 Nexpose_

Rapid7 Nexpose is a vulnerability assessment tool which aims to support the entire vulnerability management lifecycle, including discovery, detection, verification, risk classification, impact analysis, reporting, and mitigation. It integrates with Rapid7's Metasploit for vulnerability exploitation.

**20 operation(s)**:

- `create_tags()` — Create Tag
- `get_asset()` — Get Asset(s)
- `get_asset_groups()` — Get Asset Groups
- `get_asset_tags()` — Get Asset Tags
- `get_asset_vuln()` — Get Asset Vulnerability
- `get_exploit_details()` — Get Exploit Details
- `get_exploitable_vuln()` — Get Exploitable Vulnerabilities
- `get_exploits()` — Get Exploits
- `get_reference_link()` — Execute Reference link
- `get_scan()` — Get Scan
- `get_scan_engines()` — Get Scan Engines
- `get_scan_templates()` — Get Scan Templates
- `get_site()` — Get Site
- `get_site_scan_schedule()` — Get Site Scan Schedule(s)
- `get_software()` — Get Softwares on Asset
- `get_tag_assets()` — Get Assets Associated with Tag
- `get_tags()` — Get Tags
- `get_vulns()` — Get Vulnerability
- `launch_site_scan()` — Launch Site Scan
- `tag_asset()` — Tag Asset


### `security-center` v1.1.0 _(installed)_
_Tenable Security Center_

Tenable Security Center provide actions like get all completed scans, scan specific assets and asset specific vulnerabilities

**3 operation(s)**:

- `get_all_assets()` — List Assets
- `get_all_scans()` — List Completed Scans
- `get_asset_vulns()` — List Asset Vulnerabilities


### `shadowserver` v1.0.0 _(installed)_
_Shadow Server_

Shadow server provides you with access to the most timely, critical Internet security like data collection,network reporting,investigation support ,reveal security vulnerabilities, expose malicious activity and help remediate victims.

**6 operation(s)**:

- `get_asn_query()` — Get ASN Query
- `get_malware_query()` — Get Malware Query
- `get_origin_query()` — Get Origin Query
- `get_peer_query()` — Get Peer Query
- `get_prefix_query()` — Get Prefix Query
- `get_programs_query()` — Get Programs Query


### `symantec-ccsvm` v1.0.0 _(installed)_
_Symantec CCSVM_

Symantec Control Compliance Suite Vulnerability Manager (CCS-VM) is the vulnerability management software solution designed from the ground up to provide organizations with context-aware vulnerability assessment and risk analysis.

**13 operation(s)**:

- `add_group()` — Create Group
- `delete_asset()` — Delete Asset
- `execute_command()` — Execute Command on PowerShell
- `get_asset_by_id()` — Get Asset By ID
- `get_assets_by_workgroup()` — Get Assets by Workgroup
- `get_retina_scan_result()` — Get Scan Result
- `get_retina_scan_status()` — Get Scan Status
- `get_vulnerabilities_by_asset_id()` — Get Vulnerabilities by Asset ID
- `get_vulnerabilities_by_vulnerability_ids()` — Get Vulnerabilities by Vulnerability IDs
- `remove_group()` — Remove Group
- `search_assets()` — Search Assets
- `start_new_retina_scan()` — Configure and Run Scan
- `start_retina_scan()` — Run Scan


### `threadfix` v1.1.0 _(installed)_
_ThreadFix_

ThreadFix is a software vulnerability aggregation and management system. Threadfix connector facilitates automated operation related to policies, vulnearabilities, scans with threadfix server.

**21 operation(s)**:

- `add_application_to_policy()` — Add Application To a Policy
- `add_comment_vulns()` — Add Comment To Vulnerability
- `check_pending_scan_status()` — Check Pending Scan Status
- `close_vulns()` — Close Vulnerabilities
- `create_application()` — Create Application
- `create_dynamic_finding()` — Create Dynamic Finding
- `create_static_finding()` — Create Static Finding
- `create_team()` — Create Team
- `get_all_policies()` — Get All Policy
- `get_all_tags()` — Get All Tags
- `get_all_teams()` — Get All Teams
- `get_application_by_id()` — Get Application By ID
- `get_application_by_name()` — Get Application By Name
- `get_application_policy_status()` — Get Application Policy Status
- `get_policy()` — Get Policy Details
- `get_scan_details()` — Get Scan Details
- `get_team()` — Get Team Details
- `list_scan()` — Get Scan List
- `list_severities()` — Get Severity List
- `update_vuln_severity()` — Update Vulnerability Severity
- `vulnerability_search()` — Search Vulnerabilities


### `tripwire-ip360` v1.0.0 _(installed)_
_Tripwire IP360_

Tripwire IP360 Connector provides an enterprise-class vulnerability management solution, this connector used to do actions related to scanning

**25 operation(s)** (+4 hidden):

- `add_new_scan_config()` — Configure New Scan
- `cancel_scan()` — Cancel Scan
- `create_network()` — Create Network
- `create_scan_profile()` — Create Scan Profile
- `delete_network()` — Delete Network
- `delete_scan_config()` — Delete Scan Configuration
- `delete_scan_profile()` — Delete Scan Profile
- `get_agents()` — Get Agents
- `get_assets()` — Get Assets
- `get_audits()` — Get Audits
- `get_networks()` — Get Networks
- `get_scan_configs()` — Get Scan Configurations
- `get_scan_profiles()` — Get Scan Profiles
- `get_vulnerabilities()` — Get Vulnerabilities
- `pause_scan()` — Pause Scan
- `resume_scan()` — Resume Scan
- `run_agent()` — Run Agent
- `start_scan()` — Start Scan
- `update_network()` — Update Network
- `update_scan_config()` — Update Scan Configuration
- `update_scan_profile()` — Update Scan Profile


### `vuln-db` v1.0.0 _(installed)_
_VulnDB_

VulnDB is the most comprehensive and timely vulnerability intelligence available and provides actionable information about the latest in security vulnerabilities. This connector facilitates the automated operations related to vulnerabilities, products, and vendors.

**6 operation(s)**:

- `get_product_details()` — Get Product Details
- `get_product_version()` — Get Product Version
- `get_vendor_details()` — Get Vendor Details
- `get_vuln_by_vendor_and_product()` — Get Vulnerability By Vendor and Product
- `get_vuln_details()` — Get Vulnerability Details
- `get_vuln_list()` — Get Vulnerability List


---

## Web Application

### `aws-route53` v1.1.0 _(installed)_
_AWS Route 53_

Amazon Route 53 is managed,highly available, and scalable Domain Name System (DNS) web service. This connector facilitates automated operations related to create, upsert,delete record etc.

**7 operation(s)**:

- ` waiter_resource_record_sets_changed()` — Waiter Resource Record Sets Changed
- `create_record()` — Create Record
- `delete_record()` — Delete Record
- `get_hosted_zones()` — Get Hosted Zones
- `get_resource_record_sets()` — Get Resource Record Sets
- `test_dns_answer()` — Test DNS Answer
- `upsert_record()` — Upsert Record


### `f5-big-ip-waf` v1.0.0 _(installed)_
_F5 BIG-IP WAF_

F5 BIG-IP WAF connector block/unblock IP address or range, create network firewall policy and associated rules, list out network policies and corresponding rules etc.

**14 operation(s)** (+5 hidden):

- `apply_policy()` — Apply Network Firewall Policy to Virtual Server
- `create_policy()` — Create Network Firewall Policy
- `create_policy_rule()` — Create Network Firewall Policy Rule
- `delete_policy()` — Delete Network Firewall Policy
- `delete_policy_rule()` — Delete Network Firewall Policy Rule
- `list_policies()` — Get List of Network Firewall Policies
- `list_policy_rules()` — Get List of Policy Rules
- `list_virtual_servers()` — Get List of Virtual Servers
- `update_policy_rule()` — Update Network Firewall Policy Rule


### `fortinet-fortiproxy` v1.0.1 _(installed)_
_Fortinet FortiProxy_

FortiProxy provides a secure web gateway, which protects against web attacks with URL filtering, visibility and control of encrypted web traffic through SSL and SSH inspection, and application of granular web application policies. This connector facilitates automated operation related to firwall policy, firewall address, firewall address group, firewall service group, and banned users.

**26 operation(s)**:

- `add_users_to_banned_list()` — Add Users to Banned List
- `clear_all_banned_users_list()` — Clear All Banned Users List
- `clear_banned_users_list_by_ip()` — Clear Banned Users List by IP
- `create_firewall_address()` — Create Firewall Address
- `create_firewall_address_group()` — Create Firewall Address Group
- `create_firewall_policy()` — Create Firewall Policy
- `create_firewall_service_group()` — Create Firewall Service Group
- `deauthenticate_firewall_users()` — DeAuthenticate Firewall Users
- `delete_firewall_address()` — Delete Firewall Address
- `delete_firewall_address_group()` — Delete Firewall Address Group
- `delete_firewall_policy()` — Delete Firewall Policy
- `delete_firewall_service_group()` — Delete Firewall Service Group
- `get_all_banned_users_list()` — Get All Banned Users List
- `get_authenticated_firewall_users_list()` — Get Authenticated Firewall Users List
- `get_firewall_address()` — Get Firewall Address
- `get_firewall_address_details()` — Get Firewall Address Details
- `get_firewall_address_group()` — Get Firewall Address Group
- `get_firewall_address_group_details()` — Get Firewall Address Group Details
- `get_firewall_policy()` — Get Firewall Policy
- `get_firewall_policy_details()` — Get Firewall Policy Details
- `get_firewall_service_group()` — Get Firewall Service Group
- `get_firewall_service_group_details()` — Get Firewall Service Group Details
- `update_firewall_address()` — Update Firewall Address
- `update_firewall_address_group()` — Update Firewall Address Group
- `update_firewall_policy()` — Update Firewall Policy
- `update_firewall_service_group()` — Update Firewall Service Group


### `fortinet-fortiweb` v1.0.0 _(installed)_
_Fortinet FortiWeb_

Fortinet’s Web Application Firewall, protects your business-critical web applications from attacks that target known and unknown vulnerabilities

**14 operation(s)**:

- `delete_active_users()` — Delete Active Users
- `delete_client_info()` — Delete Client Information
- `get_active_users()` — Get Active Users
- `get_all_physical_servers()` — Get All Physical Servers
- `get_all_virtual_servers()` — Get All Virtual Servers
- `get_anomaly_policy_info()` — Get Anomaly Policy Information
- `get_blocked_ips()` — Get Blocked IPs
- `get_blocked_users()` — Get Blocked Users
- `get_client_info()` — Get Client Information
- `get_server_policy_status()` — Get Server Policy Status
- `get_server_policy_traffic()` — Get Server Policy Traffic
- `restore_threat_score()` — Restore Client Threat Score
- `unblock_ips()` — Unblock IPs
- `unblock_users()` — Unblock Users


### `imperva-incapsula` v1.0.0 _(installed)_
_Imperva Incapsula_

Imperva Incapsula provide web application security, DDoS mitigation. This connector facilitates automated operations like get site status, get site report, list site, modify site (security & ACL) config, delete site and etc.

**19 operation(s)**:

- `add_site()` — Add Site
- `delete_site()` — Delete Site
- `get_client_app_info()` — Get Client Applications Info
- `get_domain_approver_email()` — Get Domain Approver E-mail IDs
- `get_incapsula_ip_ranges()` — Get IP Ranges
- `get_login_protect_users()` — Get Login Protect Users
- `get_site_report()` — Get Site Report
- `get_site_status()` — Get Site Status
- `get_stats()` — Get Statistics
- `get_visits()` — Get Visits
- `list_sites()` — List Sites
- `modify_site_acl_config()` — Modify Site ACL Configuration
- `modify_site_config()` — Modify Site Configuration
- `modify_site_logs_level()` — Modify Site Logs Level
- `modify_site_security_config()` — Modify Site Security Configuration
- `modify_whitelist_config()` — Modify or Create Whitelists Configuration
- `purge_hostname()` — Purge Hostname
- `purge_resource()` — Purge Resource
- `purge_site_cache()` — Purge Site Cache


### `imperva-securesphere-waf` v1.0.0 _(installed)_
_Imperva SecureSphere WAF_

Imperva SecureSphere WAF connector block/unblock IP address and network

**6 operation(s)**:

- `get_all_custom_policies()` — Get All Web Service Custom Policies
- `get_custom_policy()` — Get Web Service Custom Policy Details
- `get_ip_group()` — Get IP Group
- `policy_block_ip()` — Policy to Block IP
- `policy_unblock_ip()` — Update Policy to Unblock IP
- `update_ip_group()` — Update IP Group


### `tcell` v1.0.0 _(installed)_
_TCell_

TCell is a web application security platform which protects web apps deployed in the cloud using web server and app server agents that integrate easily with your deployment process. This connector facilitates the automated operations like get applications,agents,routes,inline scripts,packages,events and configs

**7 operation(s)**:

- `get_agents()` — Get Agents
- `get_apps()` — Get Applications
- `get_configs()` — Get Configurations
- `get_events()` — Get Events
- `get_inline_scripts()` — Get Inline Scripts
- `get_packages()` — Get Packages
- `get_routes()` — Get Routes


---

## information

### `fortisoar-soc-simulator` v2.0.0 _(installed)_
_FortiSOAR SOC Simulator_

The FortiSOAR SOC Simulator connector is a special type of connector that is used to simulate a SOC environment. It creates various scenarios-based artifacts such as alerts, incidents, etc. in FortiSOAR™

**7 operation(s)**:

_investigation_
- `bad_domain([random: checkbox])` — Fetch Malicious Domain
- `bad_filehash([random: checkbox])` — Fetch Malicious Filehash
- `bad_ip([random: checkbox])` — Fetch Malicious IP
- `bad_url([random: checkbox])` — Fetch Malicious URL

- `create_simulated_alert(alert_json: textarea, [fields_to_ignore: text])` — Create Simulated Alert
- `malicious_file_indicator([file_name: text], [malicious_url: text], [malicious_email: text], [custom_parameters: json], [attachment_also: checkbox])` — Create Malicious File Indicator
- `replace_variables(variables: textarea)` — Replace Variables


---

## investigation

### `fortinet-fortimail` v1.2.1 _(installed)_
_Fortinet FortiMail_

Fortinet-FortiMail Connector facilitates automated operation FortiMail email security gateway that monitors email messages on behalf of an organization to identify messages that contain malicious content, including spam, malware and phishing attempts.

**26 operation(s)**:

_containment_
- `block_recipient_address(profile_name: text, email_address: text)` — Block Recipient Address
- `block_sender_address(profile_name: text, email_address: text)` — Block Sender Address

_investigation_
- `create_antispam_profile(profile_name: text, [scanner_default: select], [scan_config: checkbox])` — Create AntiSpam Profile
- `create_session_profile(profile_name: text, [connection_settings: checkbox], [sender_reputations: checkbox], [endpoint_reputation: checkbox], [sender_validation: checkbox], [session_settings: checkbox], [lists: checkbox])` — Create Session Profile
- `delete_antispam_profile(profile_name: text)` — Delete AntiSpam Profile
- `delete_session_profile(profile_name: text)` — Delete Session Profile
- `display_quarantine_mail_list(type: select, start: integer, size: integer)` — Display Quarantine Mail List
- `get_antispam_domains(domain: text)` — Get AntiSpam Profiles for Domain
- `get_antispam_profile(profile_name: text)` — Get AntiSpam Profile Details
- `get_domains()` — Get Configured Domains
- `get_profile_name(profile_type: select)` — Get Profile Names Based on Profile Type
- `get_recipient_policies(domain: text)` — Get Recipient Policies for Domain
- `get_session_block_list(profile_name: text)` — Get Sender Blacklist for Session Profile
- `get_session_profile(profile_name: text)` — Get Session Profile Details
- `get_session_safe_list(profile_name: text)` — Get Sender Whitelist For Session Profile
- `grey_list()` — Get GreyList
- `grey_list_auto_exempt()` — Get Auto Exempt GreyList
- `quarantine_release(account_type: select, message_ids: text, [release_to_others: checkbox])` — Release Quarantine Emails
- `system_quarantine_batch_release(folder: text, start: date, end: date, [message_type: select], [release_to_original: checkbox], [release_to_others: checkbox])` — Batch Release System Quarantine Emails
- `update_antispam_profile(profile_name: text, [scanner_default: select], [scan_config: checkbox])` — Update AntiSpam Profile
- `update_session_profile(profile_name: text, [connection_settings: checkbox], [sender_reputations: checkbox], [endpoint_reputation: checkbox], [sender_validation: checkbox], [session_settings: checkbox], [lists: checkbox])` — Update Session Profile
- `view_mail_in_quarantine(account_type: select, [uid_scope: integer])` — View All Emails in Quarantine

_remediation_
- `unblock_recipient_address(profile_name: text, email_address: text)` — Unblock Recipient Address
- `unblock_sender_address(profile_name: text, email_address: text)` — Unblock Sender Address
- `update_block_list(reqAction: select, resource: select, level_type: select, items: text)` — Update Block List
- `update_safe_list(reqAction: select, resource: select, level_type: select, items: text)` — Update Safe List


### `nmap-scanner` v1.0.1 _(installed)_
_NMAP Scanner_

Nmap is a security scanner provide detailed network information

**1 operation(s)**:

_investigation_
- `scan_network(hostname: text, port: text, [args: text])` — Scan Network


---

## network_security

### `infoblox-ddi` v2.1.1 _(installed)_
_Infoblox DDI_

Infoblox DDI is an integrated, and centrally managed approach to delivering enterprise-grade DDI. Infoblox DDI makes it easier for you to support your current and evolving needs, while achieving the highest standards for security, service uptime, and operational efficiencies. Infoblox DDI Connector which consolidates network services such as domain and IP address management from a single platform

**29 operation(s)**:

_containment_
- `add_block_client_ip_no_data(name: text, rp_zone: text)` — Add Block Client IP (No Data) Rule
- `add_block_client_ip_no_domain(name: text, rp_zone: text)` — Add Block Client IP (No Domain) Rule
- `add_block_domain_name_no_data(name: text, rp_zone: text)` — Add Block Domain Name (No Data) Rule
- `add_block_domain_name_no_domain(name: text, rp_zone: text)` — Add Block Domain Name (No Domain) Rule
- `add_block_ip_address_no_data(name: text, rp_zone: text)` — Add Block IP Address (No Data) Rule
- `add_block_ip_address_no_domain(name: text, rp_zone: text)` — Add Block IP Address (No Domain) Rule
- `add_host_with_aliases(hostname: text, ip_address: text, aliases: text, [configure_for_dns: checkbox])` — Add Host with Aliases
- `add_passthru_domain_name(name: text, canonical: text, rp_zone: text)` — Add Passthru Domain Name
- `add_passthru_ip_address(name: text, canonical: text, rp_zone: text)` — Add Passthru IP Address
- `create_rpz(fqdn: text, rpz_policy: select, rpz_severity: select)` — Create RPZ
- `delete_rpz(ref_no: text)` — Delete RPZ
- `retrieve_rpz_details(zone_name: text)` — Retrieve RPZ Details
- `update_rpz(ref_no: text, rpz_policy: select, rpz_severity: select)` — Update RPZ

_investigation_
- `fetch_rpzs()` — Fetch RPZs
- `get_host_aliases(hostname: text)` — Get Host Aliases
- `get_ip_address_info(ip_address: text)` — Get Information About IP Address
- `get_subnet_addresses(subnet: text)` — Get Subnet Addresses
- `search_ip_address(ip_address: text)` — Search IP Address
- `search_network(ip_address: text)` — Search Network
- `search_network_by_ea([country: text], [state: text], [region: text], [site: text], [building: text], [vlan: text])` — Search Network by EA
- `search_objects_with_ip(ip_address: text)` — Search Objects with IP

_miscellaneous_
- `add_host_ip(ref_host_id: text, ip_address: text)` — Add IP Address to Host
- `change_host_ip(ref_host_id: text, ip_address: text)` — Change Host IP
- `delete_ip_address(ref_ip_id: text)` — Delete IP Address
- `delete_rpz_rule(reference_id: text)` — Delete Rule from RPZ
- `get_cname(name: text, [page_no: integer], [limit: integer])` — Get CName from RPZ
- `modify_or_remove_host_aliases(ref_host_id: text, [aliases: text])` — Modify or Remove Host Aliases
- `remove_host_ip(ref_host_id: text, ip_address: text)` — Remove Host IP

_utilities_
- `get_details_of_block_domain_name_no_domain_rule(rp_zone: text, [view: text])` — Get Block Domain Name (No Domain) Rule Details


---

## utilities

### `code-snippet` v2.1.4 _(installed, system)_
_Code Snippet_

Execute code snippets as part of your Playbooks.

**2 operation(s)**:

- `python_inline(python_function: textarea)` — Execute Python Code (Deprecated)
- `python_inline_code_editor(python_function: codeEditor)` — Execute Python Code


### `imap` v3.5.8 _(installed, system, ingestion)_
_IMAP_

Steps related to fetching and parsing email

**2 operation(s)** (+1 hidden):

- `fetch_email_new([limit_count: integer], [parse_inline_image: checkbox])` — Fetch Email(s)


### `smtp` v2.6.0 _(installed, system)_
_SMTP_

Steps related to sending email

**6 operation(s)** (+4 hidden):

- `send_email([to_recipients: text], [cc_recipients: text], [bcc_recipients: text], [body: richtext], [subject: text], [iri_list: text], [to: text], [cc: text], [bcc: text], [from: text], [content: text], [content_type: text], [file_path: text], [file_name: text])` — Send Email
- `send_email_new(type: select, [from: text], body_type: select, [file_path: text], [file_name: text], [iri_list: text])` — Send Email (Advanced)


### `ssh` v2.1.2 _(installed)_
_SSH_

Steps that use an ssh connection. Including sftp and remote code execution

**2 operation(s)**:

- `run_remote_command(cmd: text, [allowed_exit: text], [is_super_user: checkbox])` — Execute remote command
- `run_remote_python(script: text, [version: text])` — Execute a python script


---

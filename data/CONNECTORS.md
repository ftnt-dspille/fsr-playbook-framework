---
title: FortiSOAR Connectors Cheatsheet
category: connectors
status: reference
source: live-verified
topics:
- connectors
- operations
- parameters
- categories
- 714-connectors
canonical: true
summary: '714 connectors · 6773 operations · 26093 parameters across 157 categories.
  Per-op signature format: op_name(req: type, [opt: type]).'
---

# FortiSOAR connectors cheatsheet

Generated from `store/fsr_reference.db` by `python/store/export_connectors.py`. Source-of-truth is the live FSR appliance's `/api/integration/connectors/` endpoint plus the catalog via `/api/query/solutionpacks`.

**714** connectors · **6773** operations · **26093** parameters across **157** categories.

Format per operation: `op_name(req: type, [opt: type])`. Square brackets denote optional parameters. Conditional / nested params (rendered when a parent value is set) are omitted from the inline signature — use `fsrpb explain connector <name>` to see them.

---

## Categories

- [ Network Security](#-network-security) — 1
- [AWS Service](#aws-service) — 9
- [Alert Management](#alert-management) — 1
- [Analytics](#analytics) — 1
- [Analytics & SIEM](#analytics-&-siem) — 6
- [Analytics and SIEM](#analytics-and-siem) — 16
- [Analytics and SOAR](#analytics-and-soar) — 1
- [Asset Management](#asset-management) — 7
- [Asset Management,Attack surface management,Cloud Security](#asset-management,attack-surface-management,cloud-security) — 1
- [Attack Surface Management](#attack-surface-management) — 5
- [Attack surface management](#attack-surface-management) — 4
- [Authentication](#authentication) — 2
- [Automation controller](#automation-controller) — 1
- [Breach and Attack Simulation](#breach-and-attack-simulation) — 1
- [Breach and Attack Simulation (BAS)](#breach-and-attack-simulation-(bas)) — 1
- [CMDB](#cmdb) — 4
- [CTI](#cti) — 4
- [Case Management](#case-management) — 2
- [Case Management,Threat Intelligence](#case-management,threat-intelligence) — 1
- [Central Management System](#central-management-system) — 1
- [Centralized Security Management](#centralized-security-management) — 4
- [Cloud Security](#cloud-security) — 10
- [Cloud Security Log](#cloud-security-log) — 1
- [Cloud access security broker (CASB)](#cloud-access-security-broker-(casb)) — 1
- [Communication](#communication) — 6
- [Communication and Coordination](#communication-and-coordination) — 8
- [Compliance and Reporting](#compliance-and-reporting) — 1
- [Compute Platform](#compute-platform) — 3
- [Contact Dictionary](#contact-dictionary) — 1
- [Container Services](#container-services) — 1
- [Content Management](#content-management) — 1
- [Content Security Management](#content-security-management) — 1
- [Cyber Threat Intelligence](#cyber-threat-intelligence) — 1
- [DDoS Prevention and Protection](#ddos-prevention-and-protection) — 1
- [Data Enrichment & Threat Intelligence](#data-enrichment-&-threat-intelligence) — 2
- [Data Enrichment and Threat Intelligence](#data-enrichment-and-threat-intelligence) — 2
- [Data Security](#data-security) — 1
- [Database](#database) — 14
- [DevOps](#devops) — 3
- [DevOps and Digital Operations](#devops-and-digital-operations) — 5
- [Device Security](#device-security) — 1
- [Digital Forensics & Incident Response](#digital-forensics-&-incident-response) — 1
- [Directory Service](#directory-service) — 1
- [Document Reader](#document-reader) — 1
- [Domain Information Provider](#domain-information-provider) — 1
- [Email Gateway](#email-gateway) — 3
- [Email Security](#email-security) — 11
- [Email Server](#email-server) — 6
- [Endpoint](#endpoint) — 3
- [Endpoint Management](#endpoint-management) — 2
- [Endpoint Manager](#endpoint-manager) — 1
- [Endpoint Protection](#endpoint-protection) — 10
- [Endpoint Security](#endpoint-security) — 23
- [Enrichment](#enrichment) — 2
- [Exploitation](#exploitation) — 1
- [Firewall](#firewall) — 11
- [Firewall and Network Protection](#firewall-and-network-protection) — 13
- [Forensics and Malware Analysis](#forensics-and-malware-analysis) — 1
- [FortiSOAR Essentials](#fortisoar-essentials) — 1
- [Google service](#google-service) — 1
- [HTTP Requests](#http-requests) — 1
- [IOT](#iot) — 1
- [IP Information](#ip-information) — 1
- [IT Service](#it-service) — 1
- [IT Service Management](#it-service-management) — 7
- [IT Service Management,Network Security,Compliance and Reporting](#it-service-management,network-security,compliance-and-reporting) — 1
- [IT Services](#it-services) — 16
- [Identity Management](#identity-management) — 2
- [Identity and Access Management](#identity-and-access-management) — 13
- [Information](#information) — 26
- [Insider Threat](#insider-threat) — 1
- [Investigation](#investigation) — 6
- [Logging](#logging) — 2
- [ML Service](#ml-service) — 1
- [Machine Learning](#machine-learning) — 2
- [Malware Analysis](#malware-analysis) — 9
- [Managed Security Services](#managed-security-services) — 1
- [Messaging](#messaging) — 2
- [Miscellaneous](#miscellaneous) — 4
- [Monitoring](#monitoring) — 7
- [Network Access Control](#network-access-control) — 2
- [Network Analysis and Monitoring](#network-analysis-and-monitoring) — 1
- [Network Monitoring](#network-monitoring) — 2
- [Network Protection](#network-protection) — 1
- [Network Security](#network-security) — 33
- [Network Security,Cloud Security,Endpoint Security](#network-security,cloud-security,endpoint-security) — 1
- [Network Tool](#network-tool) — 2
- [Network Visibility](#network-visibility) — 1
- [Networking](#networking) — 1
- [OT & IoT Security](#ot-&-iot-security) — 10
- [OT & IoT Security ](#ot-&-iot-security-) — 1
- [Other](#other) — 1
- [Reputation](#reputation) — 1
- [Risk Scoring](#risk-scoring) — 1
- [SCIM](#scim) — 1
- [SIEM](#siem) — 13
- [SOAR](#soar) — 1
- [SandBox](#sandbox) — 3
- [Sandbox](#sandbox) — 14
- [Security Policy Automation](#security-policy-automation) — 1
- [Security Posture Management](#security-posture-management) — 1
- [Server Virtualization](#server-virtualization) — 1
- [Service Management/Ticketing System](#service-management-ticketing-system) — 1
- [Service Manager](#service-manager) — 1
- [Software Based ADC](#software-based-adc) — 1
- [Source Code Management](#source-code-management) — 4
- [Storage](#storage) — 2
- [System Management](#system-management) — 1
- [System Monitoring](#system-monitoring) — 1
- [TIP](#tip) — 1
- [Threat Awareness & Response](#threat-awareness-&-response) — 1
- [Threat Detection](#threat-detection) — 9
- [Threat Detector](#threat-detector) — 1
- [Threat Hunting](#threat-hunting) — 1
- [Threat Hunting and Intelligence](#threat-hunting-and-intelligence) — 1
- [Threat Hunting and Search](#threat-hunting-and-search) — 1
- [Threat Intel](#threat-intel) — 1
- [Threat Intelligence](#threat-intelligence) — 128
- [Threat Intelligence Exchange](#threat-intelligence-exchange) — 2
- [Threat Protection](#threat-protection) — 2
- [Threat Response](#threat-response) — 1
- [ThreatHunt](#threathunt) — 1
- [ThreatIntel](#threatintel) — 3
- [Ticket Creation](#ticket-creation) — 3
- [Ticket Management](#ticket-management) — 6
- [Ticketing](#ticketing) — 4
- [Ticketing System](#ticketing-system) — 1
- [Translator](#translator) — 1
- [UEBA](#ueba) — 1
- [Uncategorized](#uncategorized) — 6
- [Utilities](#utilities) — 26
- [Utility](#utility) — 1
- [Vault](#vault) — 6
- [Vulnerability Control](#vulnerability-control) — 1
- [Vulnerability Management](#vulnerability-management) — 11
- [Vulnerability Manager](#vulnerability-manager) — 1
- [Vulnerability and Risk Management](#vulnerability-and-risk-management) — 9
- [WAF](#waf) — 2
- [Web Application](#web-application) — 1
- [Web Application Security](#web-application-security) — 1
- [Web Gateway](#web-gateway) — 1
- [Web Security](#web-security) — 1
- [Windows Endpoint Management](#windows-endpoint-management) — 2
- [Wireless Network Mapping](#wireless-network-mapping) — 1
- [breach_analysis](#breach_analysis) — 1
- [darkweb](#darkweb) — 1
- [firewall](#firewall) — 3
- [information](#information) — 2
- [investigation](#investigation) — 5
- [netbios](#netbios) — 1
- [network_security](#network_security) — 2
- [networking](#networking) — 2
- [protection](#protection) — 1
- [sandbox](#sandbox) — 1
- [threat_intel](#threat_intel) — 2
- [ticketing](#ticketing) — 1
- [utilities](#utilities) — 15

---

##  Network Security

### `extrahop` v2.1.0 _(installed)_
_ExtraHop_

ExtraHop Reveal(x) network detection and response automatically discovers and classifies every transaction, session, device, and asset in your enterprise. ExtraHop helps organizations understand and secure their environments by analyzing all network interactions in real-time and leveraging machine learning to identify threats, deliver critical applications, and secure investments in the hybrid cloud. This Connector automate operations such as retrieving alerts from ExtraHop, querying log records in ExtraHop, updating watchlists in ExtraHop, etc.

**23 operation(s)**:

_investigation_
- `create_alert(name: text, disabled: checkbox, severity: select, author: text, apply_all: checkbox, notify_snmp: checkbox, type: select, cc: text, [description: text], [refire_interval: text])` — Create Alert
- `create_new_detection_format(type: text, display_name: text, [author: text], [categories: text], [mitre_categories: text])` — Create New Detection Format
- `create_tag(tag_name: text)` — Create Tag
- `delete_detection_format(detection_id: text)` — Delete Detection Format
- `get_alert_details(alert_id: text)` — Get Alert Details
- `get_alerts()` — Get Alerts
- `get_detection_by_id(detection_id: text)` — Get Detection By ID
- `get_detection_format()` — Get Detection Formats
- `get_detection_rules_hiding()` — Get Detection Hiding Rules
- `get_detections()` — Get Detections
- `get_peers_devices(based_on: select, from: text, [until: text], [role: select], [protocol: text])` — Get Peers Devices
- `get_protocols(based_on: select, from: text, [until: text])` — Get Protocols
- `get_watchlist()` — Get Watchlist
- `query_records(from: text, until: text, [type: text], [filters: select], [limit: integer], [offset: integer], [sort: checkbox])` — Query Records
- `search_detections([categories: text], [assignee: text], [ticket_id: text], [status: multiselect], [resolution: multiselect], [types: text], [risk_score_min: integer], [from: text], [limit: integer], [offset: integer], [sort: checkbox], [until: text], [update_time: text], [mod_time: text], [id_only: checkbox])` — Search Detections
- `search_devices([active_from: text], [active_until: text], [filters: select], [limit: integer], [offset: integer])` — Search Devices
- `search_packet(from: text, [until: text], [output: select], [limit_bytes: text], [limit_search_duration: text], [bpf: text], [ip1: text], [port1: text], [ip2: text], [port2: text])` — Search Packet
- `tag_devices(tag_name: text, action: select, based_on: select)` — Tag Devices
- `update_alert(alert_id: text, name: text, severity: select, author: text, apply_all: checkbox, notify_snmp: checkbox, type: select, [cc: text], [description: text], [refire_interval: text])` — Update Alert
- `update_associated_ticket(ticket_id: text, assignee: text, status: select, resolution: select)` — Update Associated Ticket

_miscellaneous_
- `update_detection(detection_id: text, ticket_id: text, assignee: text, status: select, resolution: select)` — Update Detection
- `update_detection_format(detection_id: text, [display_name: text], [author: text], [categories: text], [mitre_categories: text], [type: text])` — Update Detection Format
- `update_watchlist(action: select, based_on: select)` — Update Watchlist


---

## AWS Service

### `aws` v3.1.2 _(installed)_
_AWS EC2_

Amazon Elastic Compute Cloud (Amazon EC2) provides scalable computing capacity in the Amazon Web Services (AWS) cloud. You can use Amazon EC2 to launch as many or as few virtual servers as you need, configure security and networking, and manage storage.

**32 operation(s)**:

_containment_
- `add_network_acl_rule([assume_role: checkbox], network_acl_id: text, egress_rule: select, ip_address: text, rule_action: select, rule_number: text)` — Add Network ACL Rule
- `add_security_group_to_instance([assume_role: checkbox], instance_id: text, group_list: text)` — Add Security Group To Instance
- `authorize_egress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Authorize Egress
- `authorize_ingress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Authorize Ingress
- `create_network_acl([assume_role: checkbox], vpc_id: text)` — Create Network ACL
- `create_security_group([assume_role: checkbox], group_name: text, description: text)` — Create Security Groups
- `delete_network_acl([assume_role: checkbox], network_acl_id: text)` — Delete Network ACL
- `delete_network_acl_rule([assume_role: checkbox], network_acl_id: text, egress_rule: select, rule_number: text)` — Delete Network ACL Rule
- `revoke_egress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Revoke Egress
- `revoke_ingress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Revoke Ingress

_investigation_
- `describe_instance([assume_role: checkbox], instance_id: text)` — Get Instance Details
- `describe_network_acls([assume_role: checkbox], [network_acl_ids: text], [filters: text])` — Get Details of Network ACLs
- `describe_user([assume_role: checkbox], username: text)` — Get User Details
- `get_details_for_all_images([assume_role: checkbox], [image_ids: text], [executable_users: text], [owners: text], [filters: text])` — Get AMIs Detail
- `get_details_of_security_group([assume_role: checkbox], security_group_id: text)` — Get Details of Security Group
- `get_security_groups([assume_role: checkbox])` — Get Security Groups

_miscellaneous_
- `add_tag_to_instance([assume_role: checkbox], instance_id: text, tag_key: text, tag_value: text)` — Add Instance Tag
- `attach_instance_to_auto_scaling_group([assume_role: checkbox], autoscaling_group_name: text, instance_id: text)` — Attach Instance To Auto Scaling Group
- `attach_volume([assume_role: checkbox], volume_id: text, device_name: text, instance_id: text)` — Attach Volume
- `deregister_instance_from_elb([assume_role: checkbox], elb_name: text, instance_id: text)` — Deregister Instance from ELB
- `detach_instance_from_autoscaling_group([assume_role: checkbox], autoscaling_group_name: text, instance_id: text)` — Detach Instance From Auto Scaling Group
- `launch_instance([assume_role: checkbox], image_id: text, instance_type: select, maxcount: integer, mincount: integer, [subnetid: text], device_name: text, delete_on_termination: checkbox, [security_groups_list: text], [purpose: text], [customer_name: text], [terminate_by_date: text])` — Launch Instance
- `reboot_instance([assume_role: checkbox], instance_id: text)` — Reboot Instance
- `register_instance_to_elb([assume_role: checkbox], elb_name: text, instance_id: text)` — Register Instance To ELB
- `snapshot_volume([assume_role: checkbox], volume_id: text, description: text)` — Capture Volume Snapshot
- `start_instance([assume_role: checkbox], instance_id: text, [description: text])` — Start Instance
- `stop_instance([assume_role: checkbox], instance_id: text)` — Stop Instance
- `terminate_instance([assume_role: checkbox], instance_id: text)` — Terminate Instance

_remediation_
- `delete_security_group([assume_role: checkbox], security_group_id: text)` — Delete Security Groups
- `delete_volume([assume_role: checkbox], volume_id: text)` — Delete Volume
- `detach_volume([assume_role: checkbox], volume_id: text, device_name: text, instance_id: text, force: checkbox)` — Detach Volume

- `instance_api_termination([assume_role: checkbox], instance_id: text, operation: select)` — Instance API Termination 


### `aws-athena` v1.1.0 _(installed)_
_AWS Athena_

This connector allows for the automation of AWS Athena queries

**1 operation(s)**:

_investigation_
- `run_athena_query([assume_role: checkbox], query: text, location: text, encryption: select, [db: text], [maxtries: integer])` — Run Athena Query


### `aws-cloudtrail` v1.1.0 _(installed)_
_AWS CloudTrail_

AWS CloudTrail enables auditing, security monitoring, and operational monitoring by logging your AWS account activity

**9 operation(s)**:

_investigation_
- `add_tags([assume_role: checkbox], ResourceId: text, [TagsList: json])` — Add Tags
- `create_trail([assume_role: checkbox], Name: text, S3BucketName: text, [S3KeyPrefix: text], [SnsTopicName: text], [IncludeGlobalServiceEvents: checkbox], [IsMultiRegionTrail: checkbox], [EnableLogFileValidation: checkbox], [CloudWatchLogsLogGroupArn: text], [CloudWatchLogsRoleArn: text], [KmsKeyId: text], [IsOrganizationTrail: checkbox], [TagsList: json])` — Create Trail
- `delete_trail([assume_role: checkbox], Name: text)` — Delete Trail
- `get_trail_status([assume_role: checkbox], Name: text)` — Get Trail Status
- `list_trails([assume_role: checkbox], [NextToken: text])` — List Trails
- `lookup_events([assume_role: checkbox], [LookupAttributes: json], [StartTime: datetime], [EndTime: datetime], [EventCategory: text], [MaxResults: integer], [NextToken: text])` — Lookup Events
- `start_logging([assume_role: checkbox], Name: text)` — Start Logging
- `stop_logging([assume_role: checkbox], Name: text)` — Stop Logging
- `update_trail([assume_role: checkbox], Name: text, [S3BucketName: text], [S3KeyPrefix: text], [SnsTopicName: text], [IncludeGlobalServiceEvents: checkbox], [IsMultiRegionTrail: checkbox], [EnableLogFileValidation: checkbox], [CloudWatchLogsLogGroupArn: text], [CloudWatchLogsRoleArn: text], [KmsKeyId: text], [IsOrganizationTrail: checkbox])` — Update Trail


### `aws-guardduty` v1.0.1 _(installed)_
_AWS GuardDuty_

Amazon GuardDuty is a threat detection service that continuously monitors for malicious activity and unauthorized behavior to protect your AWS accounts, workloads, and data stored in Amazon S3

**18 operation(s)**:

_investigation_
- `create_detector([assume_role: checkbox], [enable: checkbox])` — Create Detector
- `create_ip_set([assume_role: checkbox], detectorId: text, format: select, location: text, name: text, [activate: checkbox])` — Create IP Set
- `create_threat_intel_set([assume_role: checkbox], detectorId: text, format: select, location: text, name: text, [activate: checkbox])` — Create Threat Intel Set
- `delete_detector([assume_role: checkbox], detectorId: text)` — Delete Detector
- `delete_ip_set([assume_role: checkbox], detectorId: text, ipSetId: text)` — Delete IP Set
- `delete_threat_intel_set([assume_role: checkbox], detectorId: text, threatIntelSetId: text)` — Delete Threat Intel Set
- `get_all_detectors([assume_role: checkbox])` — Get Detector ID
- `get_all_findings([assume_role: checkbox], detectorId: text, [findingCriteria: json], [MaxResults: integer], [NextToken: text])` — Get All Findings
- `get_all_ip_sets([assume_role: checkbox], detectorId: text)` — Get All IP Sets
- `get_all_threat_intel_sets([assume_role: checkbox], detectorId: text, [MaxResults: integer], [NextToken: text])` — Get All Threat Intel Sets
- `get_detector([assume_role: checkbox], detectorId: text)` — Get Detector Details
- `get_findings([assume_role: checkbox], detectorId: text, findingIds: text, [sortCriteria: json])` — Get Findings
- `get_findings_statistics([assume_role: checkbox], detectorId: text)` — Get Findings Statistics
- `get_ip_set_details([assume_role: checkbox], detectorId: text, ipSetId: text)` — Get IP Set
- `get_threat_intel_set_details([assume_role: checkbox], detectorId: text, threatIntelSetId: text)` — Get Threat Intel Set Details
- `update_detector([assume_role: checkbox], detectorId: text, [enable: checkbox])` — Update Detector
- `update_ip_set([assume_role: checkbox], detectorId: text, ipSetId: text, [activate: checkbox], [location: text], [name: text])` — Update IP Set
- `update_threat_intel_set([assume_role: checkbox], detectorId: text, threatIntelSetId: text, [activate: checkbox], [location: text], [name: text])` — Update Threat Intel Set


### `aws-network-firewall` v1.0.0 _(installed)_
_AWS Network Firewall_

AWS Network Firewall is a managed service that makes it easy to deploy essential network protections for all of your Amazon Virtual Private Clouds (VPCs). Network Firewall is a stateful, managed, network firewall and intrusion detection and prevention service. This Connector automated operations such as retrieving create, update and delete operation in AWS Network firewall.

**20 operation(s)**:

_investigation_
- `create_firewall([assume_role: checkbox], FirewallName: text, FirewallPolicyArn: text, [Description: text], [DeleteProtection: checkbox], [FirewallPolicyChangeProtection: checkbox], [SubnetChangeProtection: checkbox], SubnetMappings: text, VpcId: text, [Tags: json])` — Create Firewall
- `describe_firewall([assume_role: checkbox], [FirewallArn: text], [FirewallName: text])` — Describe Firewall
- `describe_firewall_policy([assume_role: checkbox], [FirewallPolicyArn: text], [FirewallPolicyName: text])` — Describe Firewall Policy
- `describe_logging_configuration([assume_role: checkbox], [FirewallArn: text], [FirewallName: text])` — Describe Logging Configuration
- `describe_resource_policy([assume_role: checkbox], ResourceArn: text)` — Describe Resource Policy
- `describe_rule_group([assume_role: checkbox], [RuleGroupName: text], [RuleGroupArn: text], [Type: select])` — Describe Rule Group
- `disassociate_subnets([assume_role: checkbox], SubnetIds: text, [FirewallArn: text], [FirewallName: text], [UpdateToken: text])` — Disassociate Subnets
- `get_associate_firewall_policy([assume_role: checkbox], FirewallPolicyArn: text, [FirewallArn: text], [FirewallName: text], [UpdateToken: text])` — Get Associate Firewall Policy
- `get_associate_subnets([assume_role: checkbox], subnet_ids: text, [FirewallArn: text], [FirewallName: text], [UpdateToken: text])` — Get Associate Subnets
- `get_list_firewall_policies([assume_role: checkbox], [MaxResults: integer], [NextToken: text])` — Get List Firewall Policies
- `get_list_firewalls([assume_role: checkbox], [MaxResults: integer], [NextToken: text], [VpcIds: text])` — Get List Firewalls
- `get_list_rule_groups([assume_role: checkbox], [MaxResults: integer], [NextToken: text], [Scope: select])` — Get List Rule Groups
- `get_list_tag_for_resource([assume_role: checkbox], ResourceArn: text, [MaxResults: integer], [NextToken: text])` — Get List Tag For Resource
- `tag_resource([assume_role: checkbox], ResourceArn: text, Tags: json, [NextToken: text])` — Tag Resource

_miscellaneous_
- `create_firewall_policy([assume_role: checkbox], FirewallPolicyName: text, firewall_policy_json: json, [Description: text], [Tags: json])` — Create Firewall Policy
- `create_rule_group([assume_role: checkbox], rule_group_name: text, setting_type: select, type: select, capacity: integer, [description: text], [tags: json])` — Create Rule Group
- `delete_firewall([assume_role: checkbox], [FirewallArn: text], [FirewallName: text])` — Delete Firewall
- `delete_firewall_policy([assume_role: checkbox], [FirewallPolicyArn: text], [FirewallPolicyName: text])` — Delete Firewall Policy
- `delete_resource_policy([assume_role: checkbox], ResourceArn: text)` — Delete Resource Policy
- `delete_rule_group([assume_role: checkbox], [RuleGroupArn: text], [RuleGroupName: text], [Type: select])` — Delete Rule Group


### `aws-route53` v1.1.0 _(installed)_
_AWS Route 53_

Amazon Route 53 is managed,highly available, and scalable Domain Name System (DNS) web service. This connector facilitates automated operations related to create, upsert,delete record etc.

**7 operation(s)**:

_investigation_
- ` waiter_resource_record_sets_changed([assume_role: checkbox], Id: text, [Delay: integer], [MaxAttempts: integer])` — Waiter Resource Record Sets Changed
- `create_record([assume_role: checkbox], source: text, target: text, ttl: text, hostedZoneId: text, type: select, [comment: text])` — Create Record
- `delete_record([assume_role: checkbox], source: text, target: text, ttl: text, hostedZoneId: text, type: select)` — Delete Record
- `get_hosted_zones([assume_role: checkbox])` — Get Hosted Zones
- `get_resource_record_sets([assume_role: checkbox], HostedZoneId: text, [StartRecordName: text], [StartRecordType: select], [StartRecordIdentifier: text])` — Get Resource Record Sets
- `test_dns_answer([assume_role: checkbox], HostedZoneId: text, RecordName: text, RecordType: select, [ResolverIP: text])` — Test DNS Answer
- `upsert_record([assume_role: checkbox], source: text, target: text, ttl: text, hostedZoneId: text, type: select, [comment: text])` — Upsert Record


### `aws-sagemaker` v1.1.0 _(installed)_
_AWS SageMaker_

AWS SageMaker helps data scientists and developers to prepare, build, train, and deploy high-quality machine learning (ML) models quickly by bringing together a broad set of capabilities purpose-built for ML.

**4 operation(s)**:

_investigation_
- `get_actions([assume_role: checkbox], [SourceUri: text], [ActionType: text], [CreatedAfter: datetime], [CreatedBefore: datetime], [SortBy: text], [SortOrder: select], [NextToken: text], [MaxResults: integer])` — Get Actions
- `get_algorithms([assume_role: checkbox], [CreationTimeAfter: datetime], [CreationTimeBefore: datetime], [NameContains: text], [SortBy: text], [SortOrder: select], [MaxResults: integer], [NextToken: text])` — Get Algorithms
- `get_apps([assume_role: checkbox], [MaxResults: integer], [SortOrder: select], [SortBy: text], [DomainIdEquals: text], [UserProfileNameEquals: text], [NextToken: text])` — Get Applications
- `get_artifacts([assume_role: checkbox], [SourceUri: text], [ArtifactType: text], [CreatedAfter: datetime], [CreatedBefore: datetime], [SortBy: text], [SortOrder: select], [NextToken: text], [MaxResults: integer])` — Get Artifacts


### `aws-security-hub` v1.1.0 _(installed)_
_AWS Security Hub_

AWS Security Hub provides you with a comprehensive view of your security state in AWS and helps you check your environment against security industry standards.

**7 operation(s)**:

_investigation_
- `batch_import_findings([assume_role: checkbox], Findings: json)` — Import Findings
- `batch_update_findings([assume_role: checkbox], FindingIdentifiers: json, [Confidence: integer], [Criticality: integer], [Note: json], [RelatedFindings: json], [Severity: json], [Types: multiselect], [VerificationState: select], [Workflow: select])` — Batch Update Findings
- `disable_security_hub([assume_role: checkbox])` — Disable Security Hub
- `enable_security_hub([assume_role: checkbox], [tags: json], [enableDefaultStandards: checkbox])` — Enable Security Hub
- `get_findings([assume_role: checkbox], [Filters: json], [MaxResults: integer], [NextToken: text])` — Get Findings
- `get_insights([assume_role: checkbox], [InsightArns: text], [MaxResults: integer], [NextToken: text])` — Get Insights
- `list_members([assume_role: checkbox], [MaxResults: integer], [NextToken: text], [OnlyAssociated: checkbox])` — List Members


### `aws-sqs` v1.0.1 _(installed)_
_AWS SQS_

Amazon Simple Queue Service (SQS) is a fully managed message queuing service. Connector actions allows to scale and decouple microservices for distributed systems and serverless applications.

**16 operation(s)**:

_containment_
- `add_permission(queue_url: text, label: text, aws_account_ids: text, actions: multiselect)` — Add Permission to Queue
- `remove_permission(queue_url: text, label: text)` — Remove Permission
- `send_message(queue_url: text, message_body: text, [MessageGroupId: text], [MessageDeduplicationId: text])` — Send Message
- `update_queue(queue_url: text, [DelaySeconds: integer], [MaximumMessageSize: integer], [MessageRetentionPeriod: integer], [Policy: text], [ReceiveMessageWaitTimeSeconds: integer], [VisibilityTimeout: integer], [KmsMasterKeyId: text], [KmsDataKeyReusePeriodSeconds: integer])` — Update Queue

_investigation_
- `add_tag_queue(queue_url: text, key: text, value: text)` — Add Tag to Queue
- `create_queue(queue_name: text, [DelaySeconds: integer], [MaximumMessageSize: integer], [MessageRetentionPeriod: integer], [Policy: text], [ReceiveMessageWaitTimeSeconds: integer], [VisibilityTimeout: integer], [KmsMasterKeyId: text], [KmsDataKeyReusePeriodSeconds: integer], [FifoQueue: checkbox], [ContentBasedDeduplication: checkbox])` — Create Queue
- `delete_message(queue_url: text, receipt_handle: text)` — Delete Message
- `delete_queue(queue_url: text)` — Delete Queue
- `get_queue_attributes(queue_url: text)` — Get Queue Attributes
- `get_queue_url(queue_name: text, [queue_owner_aws_account_id: text])` — Get Queue URL
- `list_dead_letter_source_queues(queue_url: text)` — Get Dead-Letter Queues
- `list_queue_tags(queue_url: text)` — Get Queue Tags
- `list_queues([queue_name_prefix: text])` — Get List of Queues
- `purge_queue(queue_url: text)` — Purge Queue
- `receive_message(queue_url: text)` — Receive Message
- `untag_queue(queue_url: text, key: text)` — Remove Tag from Queue


---

## Alert Management

### `ops-genie` v1.1.0 _(installed)_
_OpsGenie_

OpsGenie connector provides alert management service

**16 operation(s)**:

_containment_
- `add_responder_to_alert(identifier_type: select, identifier: text, responder: json, [note: text])` — Add Responder to Alert
- `add_team_to_alert(identifier_type: select, identifier: text, team: json, [note: text])` — Add Team to Alert
- `assign_alert(identifier_type: select, identifier: text, owner: json, [note: text])` — Assign Alert

_investigation_
- `add_note_to_alert(identifier_type: select, identifier: text, note: text, [user: text], [source: text])` — Add Note to Alert
- `create_alert(message: text, [user: text], [alias: text], [description: text], [responders: json], [visible_to: json], [actions: text], [tags: text], [details: json], [entity: text], [source: text], [priority: select], [note: text])` — Create Alert
- `get_alert(identifier_type: select, identifier: text)` — Get Alert
- `get_attachment(identifier_type: select, alert_identifier: text, attachment_identifier: text)` — Get Attachment
- `get_list_of_alerts([sort: select], [order: select], [offset: integer], [limit: integer])` — Get List of Alerts
- `get_list_of_attachments(identifier_type: select, identifier: text)` — Get Alert Attachments
- `get_request_status(request_id: text)` — Get Request Status
- `update_alert_description(identifier_type: select, identifier: text, description: text)` — Update Alert Description
- `update_alert_message(identifier_type: select, identifier: text, message: text)` — Update Alert Message
- `update_alert_priority(identifier_type: select, identifier: text, priority: select)` — Update Alert Priority

_miscellaneous_
- `close_alert(identifier_type: select, identifier: text, [note: text])` — Close Alert
- `delete_alert(identifier_type: select, identifier: text)` — Delete Alert
- `get_alert_status(requestid: text)` — Get Alert Action Status


---

## Analytics

### `safebreach` v1.0.0 _(installed)_
_SafeBreach_

SafeBreach simulates attacks across the kill chain, to validate security policy, configuration, and effectiveness. Use this connector to get a simulation from SafeBreach and rerun the simulation on your system

**2 operation(s)**:

_investigation_
- `get_simulation(simulation_id: text)` — Get Simulation
- `rerun_simulation(rerun_data: text)` — Rerun Simulation


---

## Analytics & SIEM

### `alphasoc` v1.0.0 _(installed, ingestion)_
_AlphaSOC Network Behavior Analytics_

AlphaSOC Network Behavior Analytics connector provide action fetch alert to retrieve alerts from AplhaSOC.

**1 operation(s)**:

_investigation_
- `get_alerts([minSeverity: select], [follow: text])` — Fetch Alerts


### `exabeam-data-lake` v1.0.0 _(installed)_
_Exabeam Data Lake_

Exabeam Data Lake provides centralized logging, advanced search, cloud storage and reporting.

**1 operation(s)**:

_investigation_
- `run_query(clusterName: text, indices: text, query: text, [startTime: datetime], [endTime: datetime], [size: integer], [field: text], [order: select])` — Run Query


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


### `grafana` v1.1.0 _(installed, ingestion)_
_Grafana_

Grafana Alerting Service provides a unified, powerful system for monitoring and notifying users, allowing them to fetch alert data, including the status and details of active or past alerts.

**4 operation(s)**:

_investigation_
- `generic_rest_api_call(endpoint: text, method: select, [query_params: json], [payload: json])` — Execute an API Request
- `get_alerts([start_date: datetime], [state: select])` — Get Alerts
- `get_data_sources()` — Get Data Sources
- `run_datasource_query(query_input_method: select)` — Run Data Source Query


### `micro-focus-arcsight-logger` v1.1.0 _(installed)_
_Micro Focus ArcSight Logger_

ArcSight Logger delivers a cost-effective universal log management solution that unifies searching, reporting, alerting, and analysis across any type of enterprise machine data. This unified machine data can be used for compliance, regulations, security, IT operations, and log analytics.

**9 operation(s)**:

_investigation_
- `close(search_session_id: text, user_session_id: text)` — Release Search Session
- `drilldown(search_session_id: text, user_session_id: text, start_time: datetime, end_time: datetime)` — Get Events from Time Range
- `get_events(search_session_id: text, user_session_id: text, [dir: select], [fields: text], [length: integer], [offset: integer])` — Get Search Result
- `histogram(search_session_id: text, user_session_id: text)` — Get Histogram
- `raw_events(search_session_id: text, user_session_id: text, row_ids: text)` — Get Raw Events
- `search([query: text], [start_time: datetime], [end_time: datetime], [field_summary: select], [local_search: checkbox], [timeout: integer])` — Start Search
- `search_events([query: text], [start_time: datetime], [end_time: datetime], [field_summary: select], [local_search: checkbox], [timeout: integer], [dir: select], [fields: text], [length: integer], [offset: integer])` — Search Events
- `status(search_session_id: text, user_session_id: text)` — Get Search Status
- `stop(search_session_id: text, user_session_id: text)` — Stop Search


### `sekoia-io-xdr` v1.1.0 _(installed, ingestion)_
_SEKOIA.IO XDR_

SEKOIA.IO eXtended Detection and Response SaaS platform leverages Cyber Threat Intelligence to combine anticipation with automated incident response. SEKOIA.IO XDR offers open, transparent and flexible security oversight to break down silos and neutralise threats before impact, using intelligence. This connector facilitates automated operations related to alerts, assets and events.

**10 operation(s)**:

_investigation_
- `activate_countermeasure(countermeasure_uuid: text, content: text, [author: text])` — Activate a Countermeasure
- `add_comment_to_alert(alert_uuid: text, comment: text, [author: text])` — Add Comment to Alert
- `delete_asset(asset_uuid: text)` — Delete Asset
- `deny_countermeasure(countermeasure_uuid: text, content: text, [author: text])` — Deny a Countermeasure
- `get_alert(alert_uuid: text, [include_comments: checkbox], [include_stix: checkbox], [include_history: checkbox], [include_countermeasures: checkbox])` — Get Alert
- `get_asset(asset_uuid: text)` — Get Asset
- `get_events(query: text, earliest_time: datetime, latest_time: datetime)` — Get Events
- `list_alerts([status_uuid: text], [status_name: text], [short_id: text], [rule_uuid: text], [rule_name: text], [creation_start_date: text], [creation_end_date: text], [updated_start_date: datetime], [updated_end_date: datetime], [offset: integer], [limit: integer])` — List Alerts
- `update_alert_status(alert_uuid: text, action_uuid: text, [comment: text])` — Update Alert Status
- `update_asset(asset_uuid: text, asset_name: text, asset_type_uuid: text, asset_type_name: text, asset_criticity: text, [asset_description: text], [asset_attributes: text], [asset_keys: text], [asset_owners: text])` — Update Asset


---

## Analytics and SIEM

### `azure-log-analytics` v2.0.1 _(installed)_
_Azure Log Analytics_

Log Analytics is a tool in the Azure portal that's used to edit and run log queries against data in the Azure Monitor Logs store. This connector facilitates the automated operations related to query and saved searches.

**6 operation(s)**:

_investigation_
- `create_saved_searches(savedSearchId: text, workspace_name: text, category: text, displayName: text, query: text, [etag: text], [additional_fields: json])` — Create Saved Searches
- `delete_saved_search(savedSearchId: text, workspace_name: text)` — Delete Saved Search
- `get_saved_searches(savedSearchId: text, workspace_name: text)` — Get Saved Searches
- `update_saved_searches(savedSearchId: text, workspace_name: text, category: text, displayName: text, query: text, [additional_fields: json])` — Update Saved Searches

_investigation _
- `execute_query(workspace_id: text, query: text, [timespan: text], [workspace_name: text])` — Execute Query
- `list_saved_searches(workspace_name: text)` — List Saved Searches


### `crowdstrike-falcon-logscale` v1.0.0 _(installed)_
_CrowdStrike Falcon LogScale_

CrowdStrike Falcon® LogScale™ is a next-generation Security Information and Event Management (SIEM) platform designed to provide real-time log management, threat detection, and observability at scale.

**6 operation(s)**:

_investigation_
- `cancel_query_job(id: text, repository: select)` — Cancel Query Job
- `get_custom_lookup_file(repository: select, filename: text)` — Get Custom Lookup File
- `get_managed_lookup_file(repository: select, namespace: text, package: text, filename: text)` — Get Managed Lookup File
- `get_search_results(id: text, repository: select)` — Get Search Results
- `initiate_search(repository: select, queryString: text, [start: datetime], [end: datetime], [ingestStart: datetime], [ingestEnd: datetime], [useIngestTime: checkbox], [additional_fields: json])` — Initiate Search
- `upload_file(repository: select, input: select, value: text)` — Upload File


### `datadog-siem-cloud` v1.0.0 _(installed, ingestion)_
_Datadog Cloud SIEM_

Datadog Cloud SIEM is a real time threat detection platform paired with rich observability context to achieve faster security outcomes.

**8 operation(s)**:

_investigation_
- `get_attachments(incident_id: text)` — Get Attachments
- `get_event_details(event_id: text)` — Get Event Details
- `get_hosts([filter: text], [sort_field: text], [sort_dir: select], [start: integer], [count: integer], [_from: datetime], [include_muted_hosts_data: checkbox], [include_hosts_metadata: checkbox])` — Get Hosts
- `get_incident_details(incident_id: text)` — Get Incident Details
- `get_incidents([include: multiselect], [page_offset: integer], [page_size: integer])` — Get Incidents
- `search_events([from: datetime], [to: datetime], [query: text], [time_difference: select], [sort: select], [cursor: text], [limit: integer])` — Search Events
- `search_incidents([created_after: datetime], [created_before: datetime], [state: select], [severity: select], [customer_impacted: checkbox], [detection_method: select], [sort: select], [include: select], [offset: integer], [limit: integer], [fetch_all_incidents: checkbox])` — Search Incidents
- `update_incident(incident_id: text, [customer_impact_end: datetime], [customer_impact_scope: text], [customer_impact_start: datetime], [customer_impacted: select], [detected: datetime], [state: select], [severity: select], [detection_method: select], [root_cause: text], [title: text], [summary: text])` — Update Incident


### `elastic-kibana` v1.0.0 _(installed)_
_Elastic Kibana_

Elastic Kibana provides a powerful UI for interacting with the Elastic Stack. It enables users to search, visualize, and manage data from Elasticsearch, build dashboards, monitor systems, and secure their environment.

**9 operation(s)**:

_investigation_
- `add_and_remove_detection_alert_tags(ids: json, tags: json)` — Add and Remove Detection Alert Tags
- `create_a_live_query(query: textarea, agent_ids: json, agent_platforms: json, [agent_policy_ids: json], [alert_ids: json], [case_ids: json], [ecs_mapping: json], [event_ids: json], [metadata: json], [pack_id: text])` — Create Live Query
- `generic_action(method: select, apiendpoint: text, [data: object], [params: object])` — (Deprecation Warning) Generic Action
- `generic_api_call(method: select, api_endpoint: text, [params: object], [json_data: object])` — Execute an API Request
- `get_all_data_views()` — Get All Data Views
- `get_case_information(caseId: text)` — Get Case Information
- `get_live_query_results(id: text, actionId: text)` — Get Live Query Results
- `get_saved_queries()` — Get Saved Queries
- `search_cases([assignees: text], [category: text], [defaultSearchOperator: text], [from_: text], [to: text], [owner: select], [reporters: text], [search: text], [searchFields: select], [severity: select], [status: select], [tags: text], [sortField: select], [sortOrder: select], [page: integer], [perPage: integer])` — Search cases


### `elastic-security` v1.0.0 _(installed)_
_Elastic Security_

Elastic Security provides threat prevention, detection, and response capabilities built on the Elastic Stack. It unifies SIEM, endpoint security, and cloud security in a single solution.

**8 operation(s)**:

_investigation_
- `eql_search_api(target: text, data: object)` — (Deprecation Warning) EQL Search API
- `esql_search_api(data: object)` — (Deprecation Warning) ESQL Search API
- `generic_action(method: select, apiendpoint: text, [data: object], [params: object])` — (Deprecation Warning) Generic Action
- `generic_api_call(method: select, api_endpoint: text, [params: object], [json_data: object])` — Execute an API Request
- `get_eql_search_results(index: text, query: object)` — Get EQL Search Results
- `get_status()` — (Deprecation Warning) Get Status
- `get_the_cluster_health_status(index: text)` — Get Cluster Health Status
- `run_an_esql_query(query: object, [format: select], [delimiter: text], [drop_null_columns: checkbox], [allow_partial_results: checkbox])` — Run an ES|QL Query


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


### `google-secops-siem` v1.0.0 _(installed, ingestion)_
_Google SecOps SIEM_

Google Security Operations (SecOps) is a cloud-native security information and event management (SIEM) platform built on Google Cloud's infrastructure. It is designed to help enterprises detect, investigate, and respond to cybersecurity threats at scale and speed. By normalizing, indexing, and analyzing vast amounts of security telemetry, Google SecOps provides real-time insights into potential risks, enabling security teams to act swiftly and effectively.

**5 operation(s)**:

_investigation_
- `legacyfetchalertsview([baselineQuery: text], timeRangeStartTime: datetime, timeRangeEndTime: datetime, alertListOptionsMaxReturnedAlerts: integer)` — Fetch Legacy Alerts View
- `legacygetalert(alertId: text, includeDetections: checkbox)` — Get Legacy Alert
- `udm_search(udm_type: select, query: text, time_range.start_time: datetime, time_range.end_time: datetime, [limit: integer])` — UDM Search

- `check_health()` — Check Health
- `execute_api_endpoint(apidomain: select, method: select, api_endpoint: text, [headers: object], [data: object], [params: object])` — Execute API Endpoint


### `graylog` v1.0.0 _(installed, ingestion)_
_Graylog_

Graylog is a leading centralized log management solution for capturing, storing, and enabling real-time analysis of terabytes of machine data. This connector facilitates automated operations related to alerts, clusters, events, and search messages.

**15 operation(s)**:

_investigation_
- `get_alerts([limit: integer], [since: integer])` — Get Alerts
- `get_cluster_input_states()` — Get Cluster Input States
- `get_cluster_lookup_tables(id: text, [key: text])` — Get Clusters Lookup Tables
- `get_cluster_metrics([metrics: text])` — Get Cluster Metrics
- `get_cluster_node_jvm(id: text)` — Get Cluster Node JVM
- `get_cluster_node_metrics(id: text, [metrics: text])` — Get Cluster Node Metrics
- `get_cluster_node_metrics_names(id: text)` — Get Cluster Node Metrics Names
- `get_cluster_processing_status()` — Get Cluster Processing Status
- `get_clusters()` — Get Clusters
- `get_indexer_cluster_health()` — Get Indexer Cluster Health
- `get_streams()` — Get Streams
- `get_system_lookup_tables(sort: text, [per_page: integer], [order: checkbox], [query: text], [resolve: checkbox])` — Get System Lookup Tables
- `search_absolute(query: text, start_time: datetime, end_time: datetime, [filter: text], [limit: integer], [offset: integer], [fields: text], [sort: checkbox], [decorate: checkbox])` — Search Absolute
- `search_events(time_range: text, [query: text], [filter: text], [limit: integer], [offset: integer], [sort: checkbox])` — Search Events
- `search_relative(query: text, [time_range: text], [filter: text], [limit: integer], [offset: integer], [fields: text], [sort: checkbox], [decorate: checkbox])` — Search Relative


### `logrhythm` v3.1.0 _(installed, ingestion)_
_LogRhythm_

LogRhythm delivers in-depth endpoint visibility, automated threat hunting and breach response across the entire enterprise. LogRhythm  enhances investigator productivity with extensive rules and user behavior analytics that brings the skills and best practices of the most experienced security analysts to any organization, resulting in significantly lower costs. This connector supports the investigation actions like Get Alarm, Update Alarm etc on LogRhythm SIEM.

**33 operation(s)**:

_investigation_
- `add_alarm_comment(id: text, alarm_comment: text)` — Add Alarm Comment
- `add_alarm_evidence(id: text, alarm_ids: text)` — Add Alarm Evidence
- `add_case_tags(id: text, tag_number: text)` — Add Case Tags
- `add_file_evidence(id: text, input: select, value: text)` — Add File Evidence
- `add_note_evidence(id: text, note: text)` — Add Note Evidence
- `create_case(name: text, priority: select, [externalId: text], [dueDate: datetime], [summary: text])` — Create Case
- `delete_case_evidence(id: text, number: integer)` — Delete Case Evidence
- `download_file_evidence(id: text, number: integer)` — Download File Evidence
- `get_alarm_details(alarm_id: integer)` — DrillDown - Get Alarm Details
- `get_alarm_details_ex(alarm_id: integer)` — Get Alarm Details
- `get_alarm_events(alarm_id: integer, [count: integer], [fields: text], [show_log_messages: checkbox])` — DrillDown - Get Alarm Events
- `get_alarm_events_ex(alarm_id: integer)` — Get Alarm Events
- `get_alarm_history(alarm_id: integer, [person_id: integer], [date_updated: datetime], [type: select], [offset: integer], [count: integer])` — Get Alarm History
- `get_alarm_summary(alarm_id: integer)` — Get Alarm Summary
- `get_associated_cases_list(id: text)` — Get Associated Cases List
- `get_case(id: text)` — Get Case
- `get_case_collaborators(id: text)` — Get Case Collaborators
- `get_case_metrics(id: text)` — Get Case Metrics
- `get_evidence(id: text, number: integer)` — Get Evidence
- `get_evidence_list(id: text, [type: multiselect], [status: multiselect])` — Get Evidence list
- `get_evidence_progress(id: text, number: integer)` — Get Evidence Progress
- `get_host_by_entities(entity_name: text, [count: integer], [update_keys: checkbox])` — Get Hosts by Entities
- `get_hosts([host_id: integer], [count: integer], [update_keys: checkbox])` — Get Hosts
- `get_list_details([list_type: select], [name: text], [can_edit: checkbox], [offset: integer], [count: integer])` — Get List Details
- `get_network_list([name: text], [recordStatus: select], [BIP: text], [EIP: text], [Entity: text], [offset: integer], [count: integer])` — Get Network List
- `get_user_list([id: text], [entityIds: text], [hasLogin: multiselect], [userStatus: multiselect], [offset: integer], [count: integer])` — Get User List
- `list_alarm([status: select], [created_date: datetime], [alarm_rule_name: text], [entity_name: text], [case_association: text], [offset: integer], [count: integer])` — Search Alarm
- `list_case_tags([tag_name: text], [offset: integer], [count: integer])` — List Case Tags
- `list_cases([dueBefore: datetime], [priority: multiselect], [statusNumber: multiselect], [ownerNumber: text], [collaboratorNumber: integer], [tagNumber: text], [text: text], [evidenceType: select], [referenceId: text], [externalId: text], [entityNumber: text], [offset: integer], [count: integer], [orderBy: select], [direction: select], [updatedAfter: datetime], [updatedBefore: datetime], [createdAfter: datetime], [createdBefore: datetime])` — Get Case List
- `list_user_events_evidence(id: text, number: integer)` — Get User Event List
- `remove_case_tags(id: text, tag_number: text)` — Remove Case Tags
- `update_alarm(id: integer, [alarm_status: select], [rbp: integer])` — Update Alarm
- `update_case(id: text, [name: text], [priority: select], [externalId: text], [dueDate: datetime], [summary: text], [resolution: text])` — Update Case


### `logz-io` v1.0.0 _(installed)_
_Logz.io_

Logz.io delivers unified, full stack observability and security as a fully-managed SaaS based on best-of-breed open source. The Open 360 platform brings together logs, metrics, traces, and security data, applying powerful AI/ML features to improve troubleshooting, reduce response times, and help manage costs.

**8 operation(s)**:

_investigation_
- `delete_an_alert(alert_id: integer)` — Delete Alert By ID
- `disable_alert_by_id(alert_id: integer)` — Disable Alert By ID
- `enable_alert_by_id(alert_id: integer)` — Enable Alert By ID
- `fetch_security_events([searchTerm: text], [severities: select], fromDate: integer, toDate: integer, [_source: checkbox], field: select, [descending: checkbox], [pageNumber: integer], [pageSize: integer])` — Get Security Events List
- `get_list_of_insights([startDate: integer], [endDate: integer], [from: integer], [size: integer], [insightTypes: text], [tagNames: text], [logTypes: multiselect], [onlyNew: checkbox], [sortBy: select], [asc: checkbox], [search: text])` — Get Insights List
- `retrieve_alert_by_id(alert_id: integer)` — Get Alert By ID
- `retrieve_all_alerts()` — Get Alerts List
- `search_logs([query: json])` — Search Logs


### `microsoft-sentinel` v1.1.0 _(installed, ingestion)_
_Microsoft Sentinel_

Microsoft Sentinel is Cloud-native SIEM for intelligent security analytics for your entire enterprise. These connector connects to Microsoft sentinel using Sentinel APIs to investigate on alerts, threats intelligence indicator, incidents, incident entities, incident relations, incident comments, and incident bookmarks.

**31 operation(s)**:

_investigation_
- `create_incident_comment(incidentId: text, message: text)` — Create Incident Comment
- `create_incident_relations(incidentId: text, relationName: text, resourceId: text)` — Create Incident Relations
- `create_threat_intelligence_indicator(displayName: text, patternType: select, source: text, [confidence: integer], [description: text], [threatIntelligenceTags: text], [threatTypes: text], [indicatorTypes: text], [labels: text], [additional_fields: json])` — Create Threat Intelligence Indicator
- `create_watchlist(watchlistAlias: text, displayName: text, itemsSearchKey: text, provider: text, source: text, [description: text], [etag: text], [custom_attributes: json])` — Create Watchlist
- `create_watchlist_item(watchlistAlias: text, itemsKeyValue: json, [watchlistItemId: text], [etag: text], [custom_attributes: json])` — Create Watchlist Item
- `delete_incident_comment(incidentcommentId: text, incidentId: text)` — Delete Incident Comment
- `delete_incident_relation(incidentId: text, relationName: text)` — Delete Incident Relation
- `delete_threat_intelligence_indicator(id: text)` — Delete Threat Intelligence Indicator
- `delete_watchlist(watchlistAlias: text)` — Delete Watchlist
- `delete_watchlist_item(watchlistItemId: text, watchlistAlias: text)` — Delete Watchlist Item
- `get_alert_list(incidentId: text)` — Get Incident Alert List
- `get_all_incident_comments(incidentId: text, [$filter: text], [$orderby: text], [$top: integer], [$skipToken: text])` — Get All Incident Comments
- `get_all_incident_relations(incidentId: text, [$filter: text], [$orderby: text], [$top: integer], [$skipToken: text])` — Get All Incident Relations
- `get_all_threat_intelligence_indicators([$filter: text], [$orderby: text], [$top: integer], [$skipToken: text])` — Get All Threat Intelligence Indicators
- `get_all_watchlist([$skipToken: text])` — Get All Watchlist
- `get_all_watchlist_items(watchlistAlias: text, [$skipToken: text])` — Get All Watchlist Items
- `get_bookmarks_list(incidentId: text)` — Get Incident Bookmarks List
- `get_entities_list(incidentId: text)` — Get Incident Entities List
- `get_incident(incidentId: text)` — Get Incident Details
- `get_incident_comment(incidentcommentId: text, incidentId: text)` — Get Incident Comment
- `get_incident_list([created_datetime: datetime], [Severity: select], [Status: select], [$filter: text], [$orderby: text], [$top: integer], [$skipToken: text])` — Get Incident List
- `get_incident_relations(incidentId: text, relationName: text)` — Get Incident Relation
- `get_threat_intelligence_indicator(id: text)` — Get Threat Intelligence Indicator
- `get_watchlist(watchlistAlias: text)` — Get Watchlist
- `get_watchlist_item(watchlistItemId: text, watchlistAlias: text)` — Get Watchlist Item
- `update_incident(incidentId: text, Severity: select, Status: select, Title: text, [labels: text], [etag: text], [Description: text], [custom_attributes: json])` — Update Incident
- `update_incident_comment(incidentcommentId: text, incidentId: text, message: text)` — Update Incident Comment
- `update_incident_relations(incidentId: text, relationName: text, resourceId: text)` — Update Incident Relations
- `update_threat_intelligence_indicator(id: text, displayName: text, patternType: select, source: text, [confidence: integer], [description: text], [threatIntelligenceTags: text], [threatTypes: text], [indicatorTypes: text], [labels: text], [additional_fields: json])` — Update Threat Intelligence Indicator
- `update_watchlist(watchlistAlias: text, displayName: text, itemsSearchKey: text, provider: text, source: text, [description: text], [etag: text], [custom_attributes: json])` — Update Watchlist
- `update_watchlist_item(watchlistItemId: text, watchlistAlias: text, itemsKeyValue: json, [etag: text], [custom_attributes: json])` — Update Watchlist Item


### `qradar` v1.6.2 _(installed, ingestion)_
_IBM QRadar_

IBM QRadar is an enterprise security information and event management (SIEM) product. Fortinet FortiSOAR connector for IBM QRadar allows users to invoke QRadar API, perform Ariel Queries and operations like Get Offense,related events,update and close offenses.

**23 operation(s)**:

_investigation_
- `add_table_element(path.name: text, query.outer_key: text, query.inner_key: text, query.value: text, [query.domain_id: text], [query.source: text], [query.fields: text], [query.namespace: text])` — Add or Update Table Element
- `create_case(body.case: json, [content_type: text])` — Create Case
- `delete_reference_table(path.name: text, [query.purge_only: select], [query.fields: text], [query.namespace: text])` — Delete or Purge Reference Table
- `delete_table_element(path.name: text, path.outer_key: text, path.inner_key: text, query.value: text, [query.domain_id: text], [query.fields: text], [query.namespace: text])` — Delete Table Element
- `fetch_offenses(filter_string: text, start_time: datetime)` — Fetch Offenses from QRadar
- `get_assets([filter_string: text], [max_results: integer], [query.fields: text], [query.sort: text])` — Get Assets
- `get_assets_properties([max_results: integer], [filter_string: text], [query.fields: text])` — Get Assets Properties
- `get_cases([query.fields: text], [filter_string: text], [max_results: integer])` — Get Cases
- `get_destination_ip(destination_address_ids: text)` — Get Destination IP Addresses
- `get_events_related_to_offense(offense_id: text, start_time: datetime, last_updated_time: datetime, [max_results: integer])` — Get Events Related to an Offense
- `get_offense_type()` — Get Offense Types
- `get_offenses(filter_string: text)` — Get Offenses from QRadar
- `get_reference_tables([filter_string: text], [max_results: integer], [query.fields: text])` — Get Reference Tables
- `get_source_ip(source_address_ids: text)` — Get Source IP Addresses
- `get_table_elements(path.name: text, [max_results: integer], [query.fields: text], [query.namespace: text])` — Get Table Elements
- `handle_reference_set_value(method: select)` — Manipulate Reference Set Content
- `invoke_api(endpoint: text, method: select, [headers: json])` — Invoke QRadar REST API
- `query_qradar(search_string: text)` — Make an Ariel Query to QRadar
- `update_asset(path.asset_id: text, body.asset: json, [content_type: text])` — Update Asset

_remediation_
- `add_notes(offense_id: text, closure_note: textarea)` — Create Note
- `close_offense(offense_id: text, offense_close_id: text, [closure_note: textarea])` — Close Offense
- `get_closing_reasons()` — Get Offense Closing Reasons
- `get_notes(offense_id: text)` — Get Offense Notes


### `rapid7-insightidr` v2.1.0 _(installed, ingestion)_
_Rapid7 InsightIDR_

Rapid7 InsightIDR is an intruder analytics solution that gives you the confidence to detect and investigate security incidents faster. This connector facilitates automated operations like get investigations, update status of the investigation, close investigation, add/ update indicators to threat.

**12 operation(s)**:

_investigation_
- `add_indicators_to_threat(key: text, format: select)` — Add Indicators to Threat
- `close_investigations(source: text, from: datetime, to: datetime, [alert_type: text], [disposition: text], [detection_rule_rrn: text], [max_investigations_to_close: integer])` — Close Investigations
- `create_comment(target: text, [body: text], [attachments: json])` — Create Comment
- `create_investigation(title: text, [status: text], [priority: text], [disposition: text], [assignee: text])` — Create Investigation
- `delete_comment(rrn: text)` — Delete Comment
- `get_alerts_associated_with_investigation(id: text, [index: integer], [size: integer], [multi-customer: checkbox], [get_all_records: checkbox])` — Get Alerts Associated With Investigation
- `get_comments(target: text, [index: integer], [size: integer])` — Get Comments
- `get_investigations([statuses: text], [sources: text], [priorities: text], [assignee.email: text], [start_time: datetime], [end_time: datetime], [sort: text], [multi-customer: checkbox], [tags: text], [index: integer], [size: integer], [get_all_records: checkbox])` — Get Investigation List
- `get_investigations_details([id: text], [multi-customer: checkbox])` — Get Investigation Details
- `search_investigations(search: json, [sort: json], [start_time: datetime], [end_time: datetime], [index: integer], [size: integer], [multi-customer: checkbox])` — Search Investigations
- `update_indicators_to_threat(key: text, format: select)` — Replace Indicators for Threat
- `update_investigation(id: text, [multi-customer: checkbox], [title: text], [status: text], [priority: text], [disposition: text], [assignee: text], [threat_command_close_reason: text], [threat_command_free_text: text])` — Update Investigation


### `securonix-snypr` v2.2.0 _(installed, ingestion)_
_Securonix SNYPR_

Connector facilitates automated operations to Analyze and detect the Threats, Violations and Risk associated with users in organisation.

**26 operation(s)**:

_investigation_
- `add_comment(incidentId: text, comment: text)` — Add Comment
- `check_task_on_incident(incidentId: text, actionName: text)` — Check Task on Incident
- `create_incident(violationName: text, datasourceName: text, entityName: text, entityType: text, actionName: select, [resourceName: text], [employeeid: text], [workflow: text], [comment: text], [criticality: text])` — Create Incident
- `custom_query(query: text, [eventtime_from: datetime], [eventtime_to: datetime], [generationtime_from: datetime], [generationtime_to: datetime])` — Custom Query
- `get_available_threat_action()` — Get Available Threat Action
- `get_incident_details(incidentId: text)` — Get Incident Details
- `get_incident_status(incidentId: text)` — Get Incident Status
- `get_incident_workflow(incidentId: text)` — Get Incident Workflow
- `get_possible_action_for_incident(incidentId: text)` — Get Possible Actions for Incident
- `get_risk_history([query: text], [from: datetime], [to: datetime])` — Get Risk History
- `get_risk_score([query: text], [from: datetime], [to: datetime])` — Get Risk Score
- `get_top_threats(dateunit: select)` — Get Top Threats
- `get_top_violations(dateunit: select)` — Get Top Violations
- `get_top_violators(dateunit: select, offset: integer, max: integer)` — Get Top Violators
- `get_workflow_default_assignee(workflow: text)` — Get Workflow Default Assignee
- `get_workflows()` — Get Workflows
- `list_incidents(rangeType: select, from: datetime, to: datetime, [status: text], [offset: integer], [max: integer])` — List Incidents
- `list_peer_groups()` — List All Peer Groups
- `list_policies()` — List All Policies
- `list_resource_groups()` — List All Resource Groups
- `list_users()` — List All Users
- `query_tpi([query: text])` — Query Third Party Intelligence
- `query_users([query: text])` — Query Users
- `query_violations([query: text], generationtime_from: datetime, [generationtime_to: datetime])` — Query Violations
- `query_watchlist([query: text])` — Query Watchlist
- `take_action_on_incident(incidentId: text, actionName: text, [other_fields: json])` — Task Action on Incident


### `sentinelone` v3.5.3 _(installed, ingestion)_
_SentinelOne_

SentinelOne that provides threat detection, hunting, and response features that enable organizations to discover vulnerabilities and protect IT operations. This connector facilitates automated operations related to events, threats, agents, query, and applications.

**45 operation(s)** (+3 hidden):

_containment_
- `agent_action(action: select, ids: text, [groupIds: text], [isDecommissioned: checkbox], [isUninstalled: checkbox])` — Agent Action

_investigation_
- `abort_agent_scan([ids: text], [isActive: checkbox], [infected: checkbox], [isDecommissioned: checkbox], [computerName__like: text], [totalMemory__lte: integer], [totalMemory__gte: integer], [coreCount__lte: integer], [coreCount__gte: integer], [agentVersions: text], [osTypes: multiselect], [networkStatuses: select], [extra_parameters: json])` — Abort Agent Scan
- `add_note_to_a_threat(threatID: text, note: text)` — Add Note to a Threat
- `cancel_running_query(queryId: text)` — Cancel Running Query
- `change_incident_status(threatID: text, incidentStatus: select)` — Change Incident Status
- `create_blacklist_item(osType: select, [hashValue: text], [sha256Value: text], [description: text], [tenant: checkbox], [accountIds: text], [groupIds: text], [siteIds: text])` — Create Blocklist Item
- `create_query(query: text, fromDate: datetime, toDate: datetime, [groupIds: text], [tenant: checkbox], [queryType: text], [accountIds: text], [siteIds: text])` — Create Query And Get Query ID
- `delete_threat_note(id: text, note_id: text)` — Delete Threat Note
- `export_applications_risk([siteIds: text], [groupIds: text], [accountIds: text], [size__between: text], [agentMachineTypes: multiselect], [ids: text], [types: multiselect], [agentIsDecommissioned: checkbox], [riskLevels: multiselect], [osTypes: multiselect], [extra_parameters: json])` — Export Applications Risk
- `export_forensics_threat(threat_id: text, export_format: select)` — Export Threat
- `fetch_agent_logs([ids: text], [isActive: checkbox], [infected: checkbox], [isDecommissioned: checkbox], [computerName__like: text], [totalMemory__lte: integer], [totalMemory__gte: integer], [coreCount__lte: integer], [coreCount__gte: integer], [agentVersions: text], [osTypes: multiselect], [networkStatuses: multiselect])` — Fetch Agents Logs
- `fetch_threat_file(ids: text, password: password, [additional_fields: json])` — Fetch Threat File
- `fetch_threats([createdAt__gt: datetime], [updatedAt__gt: datetime], [query: text], [additional_fields: json])` — Fetch Threats
- `free_text_filters()` — Free Text
- `get_agent_application(ids: text)` — Get Agent Application
- `get_agents([ids: text], [isActive: checkbox], [infected: checkbox], [isDecommissioned: checkbox], [computerName__like: text], [totalMemory__lte: integer], [totalMemory__gte: integer], [coreCount__lte: integer], [coreCount__gte: integer], [agentVersions: text], [networkStatuses: multiselect], [limit: integer], [skip: integer], [cursor: text], [additional_fields: json])` — Get Agents
- `get_alerts([additional_fields: json])` — Get Alerts
- `get_application_count(filterBy: select, [siteIds: text], [groupIds: text], [accountIds: text], [agentMachineTypes: multiselect], [ids: text], [types: select], [agentIsDecommissioned: checkbox], [riskLevels: multiselect], [osTypes: multiselect], [extra_parameters: json])` — Get Application Count
- `get_application_cve(agent_application_id: text)` — Get Application CVEs
- `get_applications([agentMachineTypes: multiselect], [ids: text], [agentIsDecommissioned: checkbox], [types: multiselect], [riskLevels: multiselect], [limit: integer], [skipCount: checkbox], [sortBy: select], [sortOrder: select], [countOnly: checkbox], [osTypes: multiselect], [cursor: text], [extra_parameters: json])` — Get Applications
- `get_cve([ids: text], [cveIds: text], [limit: integer], [skipCount: checkbox], [sortBy: select], [sortOrder: select], [countOnly: checkbox], [cursor: text], [extra_parameters: json])` — Get CVEs
- `get_events(queryId: text, [limit: integer], [skip: text], [cursor: text], [sortBy: text], [sortOrder: select], [subQuery: text])` — Get Events
- `get_events_by_type(queryId: text, event_type: select, [limit: integer], [skip: integer], [cursor: integer], [sortBy: text], [sortOrder: select], [subQuery: text])` — Get Events By Type
- `get_hash_details(hash_id: text)` — Get Hash Details
- `get_query_status(queryId: text)` — Get Query Status
- `get_threat_details(ids: text)` — Get Threat Details
- `get_threat_events(threat_id: text, [eventId: text], [eventTypes: multiselect], [eventSubTypes: text], [limit: integer], [skip: text], [cursor: text], [additional_fields: json])` — Get Threat Events List
- `get_threat_notes(id: text, [creatorId: text], [creator__like: text], [sortBy: text], [sortOrder: select], [skip: text], [limit: integer], [skipCount: checkbox], [countOnly: checkbox], [cursor: text])` — Get Threat Notes
- `get_threat_timeline(id: text, [sortOrder: select], [skip: text], [limit: integer], [cursor: text], [additional_fields: json])` — Get Threat Timeline
- `initiate_agent_scan([ids: text], [isActive: checkbox], [infected: checkbox], [isDecommissioned: checkbox], [computerName__like: text], [totalMemory__lte: integer], [totalMemory__gte: integer], [coreCount__lte: integer], [coreCount__gte: integer], [agentVersions: text], [osTypes: multiselect], [networkStatuses: multiselect], [extra_parameters: json])` — Initiate Agent Scan
- `list_all_threats([agentIds: text], [createdAt__gt: datetime], [updatedAt__gt: datetime], [contentHash: text], [displayName: text], [limit: integer], [skip: text], [cursor: text], [additional_fields: json])` — List All Threats
- `threat_forensic_details(threat_id: text)` — Threat Forensic Details
- `threat_forensics(threat_id: text, [siteIds: text], [groupIds: text], [accountIds: text])` — Get Threat Forensics
- `threat_seen_on_network(threat_id: text, [siteIds: text], [groupIds: text], [accountIds: text])` — Get Threat Seen on Network
- `update_threat_note(id: text, note_id: text, text: text)` — Update Threat Note

_miscellaneous_
- `broadcast_message_to_agent(message: text, [ids: text], [isActive: checkbox], [infected: checkbox], [isDecommissioned: checkbox], [computerName__like: text], [totalMemory__lte: text], [totalMemory__gte: text], [coreCount__lte: text], [coreCount__gte: text], [agentVersions: text], [osTypes: multiselect], [networkStatuses: multiselect])` — Broadcast Message to Agent
- `get_agent_count([ids: text], [isActive: checkbox], [infected: checkbox], [isDecommissioned: checkbox], [computerName__like: text], [totalMemory__lte: integer], [totalMemory__gte: integer], [coreCount__lte: integer], [coreCount__gte: integer], [agentVersions: text], [osTypes: multiselect], [networkStatuses: multiselect])` — Get Agent Count
- `get_agent_passphrase([ids: text], [cursor: text], [additional_fields: json])` — Get Agent Passphrase

_query_
- `custom_endpoint([method: select], endpoint: text, [body: json])` — Execute an API Request

_remediation_
- `mark_threat_as_benign(targetScope: text, ids: text, [agentId: text], [contentHash: text], [displayName: text], [limit: integer])` — Mark Threat as Benign
- `mitigate_threats(action: select, ids: text, [agentId: text], [contentHash: text], [displayName: text], [limit: integer])` — Mitigate Threat
- `reconnect_agent([ids: text], [isActive: checkbox], [infected: checkbox], [isDecommissioned: checkbox], [computerName__like: text], [totalMemory__lte: integer], [totalMemory__gte: integer], [coreCount__lte: integer], [coreCount__gte: integer], [agentVersions: text], [osTypes: multiselect], [networkStatuses: multiselect])` — Reconnect Agent


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


---

## Analytics and SOAR

### `google-secops-soar` v1.0.0 _(installed)_
_Google SecOps SOAR_

Google Security Operations SOAR (Security Orchestration, Automation, and Response) is a cloud-native platform designed to help security teams detect, investigate, and respond to threats in real time.

**1 operation(s)**:

_investigation_
- `generic_api_call(method: select, api_endpoint: text, [headers: object], [params: object], [data: object])` — Execute an API Request


---

## Asset Management

### `axonius` v1.0.0 _(installed)_
_Axonius_

Axonius provides the unified view of all your assets, users, vulnerabilities, and more by aggregating data from business management and security tools. This connector provides action to Get Devices, Get Assets

**2 operation(s)**:

_investigation_
- `get_device_assets(get_devices_by: select)` — Get Device Assets
- `get_user_assets(get_users_by: select)` — Get User Assets


### `azure-commands` v1.0.1 _(installed)_
_Azure Commands_

Azure Commands are used to run Azure native commands for Azure resources configurations directly from FortiSOAR.

**10 operation(s)**:

_investigation_
- `delete_resource(input: select, [optional_parameters: text])` — Delete Resource
- `delete_vm(input: select, [optional_parameters: text])` — Delete Virtual Machine
- `generic_command(command: text, [optional_parameters: text])` — Execute Azure Command
- `get_resource(input: select, [optional_parameters: text])` — Get Resource
- `get_vm(input: select, [optional_parameters: text])` — Get Virtual Machine
- `list_resource([location: text], [optional_parameters: text])` — Get Resources List
- `list_ssh_keys([resource_group: text], [optional_parameters: text])` — Get SSH Keys List
- `list_storage_fs_directory(file_system: text, [optional_parameters: text])` — Get Storage FS Directory List
- `list_vm([resource_group: text], [optional_parameters: text])` — Get Virtual Machines List
- `list_webapp([resource_group: text], [optional_parameters: text])` — Get Webapp List


### `dragos-sitestore` v1.0.0 _(installed)_
_Dragos SiteStore_

Dragos SiteStore is a key component of the Dragos Platform, designed to enhance cybersecurity for industrial control systems (ICS) and operational technology (OT) environments. It serves as the management and reporting console for data collected by Dragos sensors, providing comprehensive visibility and threat detection capabilities.

**8 operation(s)**:

_investigation_
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_assets([createdAtAfter: datetime], [createdAtBefore: datetime], [lastSeenAtAfter: datetime], [lastSeenAtBefore: datetime], [is_deleted: checkbox], [overlaps_starttime: datetime], [overlaps_endtime: datetime], [maskAddress_starttime: datetime], [maskAddress_endtime: datetime], [sort_by: multiselect], [order_by: checkbox], [pageSize: integer], [pageNumber: integer], [limitTotalCount: integer], [additional_fields: json])` — Get All Assets
- `get_detections([includeFields: text], [excludeFields: text], [sort_by: text], [order_by: checkbox], [pageSize: integer], [pageNumber: integer], [limitTotalCount: integer], [additional_fields: json])` — Get All Detections
- `get_notification_details(ids: text, [resolveChildrenDepth: integer], [includeConversations: checkbox])` — Get Notifications Details
- `get_notifications([filter: text], [createdAtAfter: datetime], [state: select], [sorts: text], [sortField: select], [sortDescending: checkbox], [resolveChildrenDepth: integer], [offset: integer], [pageSize: integer], [pageNumber: integer], [limitTotalCount: integer], [additional_fields: json])` — Get All Notifications
- `get_stats_of_notification(groupBy: multiselect, [filter: text])` — Get Statistics of Notification
- `get_vulnerabilities([sort_by: text], [order_by: checkbox], [pageSize: integer], [pageNumber: integer], [limitTotalCount: integer], [additional_fields: json])` — Get All Vulnerabilities
- `get_vulnerability_detections([sort_by: text], [order_by: checkbox], [pageSize: integer], [pageNumber: integer], [limitTotalCount: integer], [additional_fields: json])` — Get All Vulnerability Detections


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

_investigation_
- `create_folder(associated_with: select, folder_structure: json, parent_item_id: text)` — Create Folder
- `download_file(associated_with: select, item_id: text)` — Download File
- `get_document_library(select_option: select)` — Get Document Library
- `get_drive_by_id(drive_id: text)` — Get Drive By ID
- `get_user_onedrive(user_id: text)` —  Get User OneDrive
- `list_drives()` — List Drives
- `upload_file(associated_with: select, input: select, value: text, parent_item_id: text, filename: text)` — Upload File


### `netbox` v1.0.0 _(installed)_
_NetBox_

NetBox is the leading solution for modeling and documenting modern networks. By combining the traditional disciplines of IP address management (IPAM) and datacenter infrastructure management (DCIM) with powerful APIs and extensions, NetBox provides the ideal "source of truth" to power network automation.

**24 operation(s)**:

_investigation_
- `delete_cable(id: integer)` — Delete Cable
- `delete_device(id: integer)` — Delete Device
- `delete_ip_address(id: integer)` — Delete IP Address
- `delete_prefix(id: integer)` — Delete Prefix
- `delete_rack(id: integer)` — Delete Rack
- `delete_vm(id: integer)` — Delete Virtual Machine
- `get_cable(id: integer)` — Get Cable
- `get_cable_list([id: text], [tag: text], [type: text], [q: text], [status: text], [ordering: text], [offset: integer], [limit: integer], [other_fields: json])` — Get Cables List
- `get_device(id: integer)` — Get Device
- `get_device_list([id: text], [name: text], [region_id: text], [site: text], [rack_id: text], [tag: text], [device_type: text], [asset_tag: text], [tenant: text], [q: text], [status: text], [ordering: text], [offset: integer], [limit: integer], [other_fields: json])` — Get Devices List
- `get_ip_address(id: integer)` — Get IP Address
- `get_ip_address_list([id: text], [address: text], [role: text], [tag: text], [q: text], [family: select], [status: text], [ordering: text], [offset: integer], [limit: integer], [other_fields: json])` — Get IP Address List
- `get_prefix(id: integer)` — Get Prefix
- `get_prefix_list([id: text], [prefix: text], [site: text], [role: text], [tag: text], [q: text], [family: select], [status: text], [ordering: text], [offset: integer], [limit: integer], [other_fields: json])` — Get Prefix List
- `get_rack(id: integer)` — Get Rack
- `get_rack_list([id: text], [name: text], [site: text], [role: text], [tag: text], [type: text], [q: text], [status: text], [ordering: text], [offset: integer], [limit: integer], [other_fields: json])` — Get Rack List
- `get_vm(id: integer)` — Get Virtual Machine
- `get_vm_list([id: text], [name: text], [site: text], [role: text], [tag: text], [status: text], [q: text], [ordering: text], [offset: integer], [limit: integer], [other_fields: json])` — Get Virtual Machines List
- `update_cable(id: integer, patch_fields: json)` — Update Cable
- `update_device(id: integer, [device_type: text], [name: text], [description: text], [status: text], [site: text], [comments: text], [rack: text], [tags: json], [other_fields: json])` — Update Device
- `update_ip_address(id: integer, patch_fields: json)` — Update IP Address
- `update_prefix(id: integer, patch_fields: json)` — Update Prefix
- `update_rack(id: integer, patch_fields: json)` — Update Rack
- `update_vm(id: integer, patch_fields: json)` — Update Virtual Machine


---

## Asset Management,Attack surface management,Cloud Security

### `wiz-io` v2.0.0 _(installed)_
_Wiz.io_

Wiz provides a comprehensive analysis engine that integrates: Cloud Security Posture Management (CSPM) Kubernetes Security Posture Management (KSPM) Cloud Workload Protection (CWPP) + vulnerability management. Infrastructure-as-Code (IaC) scanning.

**5 operation(s)**:

_investigation_
- `add_comment_to_issue(issueID: text, comment: textarea)` — Add Comment to Issue
- `get_inventory_assets(projectID: text, type: text, [searchTerm: text], [updatedBefore: datetime], [updatedAfter: datetime], [deletedBefore: datetime], [deletedAfter: datetime], [limit: integer])` — Get Inventory Assets
- `get_issues([issueID: text], [searchQuery: text], [projectID: text], [severity: select], [status: select], [type: select], [relatedEntityID: text], [realtedEntityType: select], [createdBefore: datetime], [createdAfter: datetime], [resolvedBefore: datetime], [resolvedAfter: datetime], [limit: integer], [pagination: text], [relatedCloudPlatform: select])` — Get Issues
- `get_projects([name: text], [businessImpact: select], [includeArchivedProjects: checkbox], [limit: integer])` — Get Projects
- `get_vulnerabilities(status: select, projectID: text, assetType: text, [vulnerabilityID: text], [externalSubscriptionID: text], [severity: select], [firstSeenBefore: datetime], [firstSeenAfter: datetime], [resolvedBefore: datetime], [resolvedAfter: datetime], [assetID: text], [patchAvailable: checkbox], [exploitAvailable: checkbox], [limit: integer], [pagination: text])` — Get Vulnerabilities


---

## Attack Surface Management

### `bitsight` v1.0.0 _(installed)_
_Bitsight_

Bitsight is a global cyber risk management leader transforming how companies manage exposure, performance, and risk for themselves and their third parties.

**10 operation(s)**:

_investigation_
- `get_alerts([alert_date_gte: datetime], [alert_date_lte: datetime], [alert_type: text], [company_guid: text], [expand: text], [folder_guid: text], [severity: text], [limit: integer], [offset: integer])` — Get Alerts
- `get_assets(company_guid: text, [asset: text], [combined_overrides.importance: text], [expand: text], [findings.total_count_gte: integer], [findings.total_count_lte: integer], [hosted_by_isnull: select], [importance_categories: text], [importance_overrides: text], [ip_address: text], [is_ip: select], [origin_subsidiary_isnull: select], [overrides_isnull: select], [tags_contains: text], [limit: integer], [offset: integer], [attack_surface_analytics: select])` — Get Assets
- `get_assets_risk_matrix(company_guid: text)` — Get Asset Risk Matrix
- `get_cataloged_threats([category: text], [support_started_date_gte: datetime], [support_started_date_lte: datetime], [guid: text], [name: text], [severity_level: text], [sort: text], [limit: integer], [offset: integer])` — Get Cataloged Threats
- `get_companies_with_exposed_credentials([date_added_gte: datetime], [date_added_lte: datetime], [limit: integer], [offset: integer])` — Get Companies With Exposed Credentials
- `get_credentials_leaks([limit: integer], [offset: integer])` — Get Credentials Leaks Affecting Your Portfolio
- `get_portfolio_threats([company_guid: text], [category_slug: text], [currently_exposed_count_lte: integer], [currently_exposed_count_gte: integer], [last_seen_date_gte: datetime], [last_seen_date_lte: datetime], [expand: text], [folder: text], [impacts_group: select], [severity_level: text], [sort: text], [threat_guid: text], [tier: text], [limit: integer], [offset: integer])` — Get Portfolio Threats
- `get_threat_evidence(company_guid: text, threat_guid: text, [last_seen_date_gte: datetime], [last_seen_date_lte: datetime], [detection_type: select], [evidence_certainty: select], [exposure_detection: select], [force_masked: checkbox], [limit: integer], [offset: integer])` — Get Threat Evidence
- `get_threat_impact(threat_guid: text, [last_seen_date_gte: datetime], [last_seen_date_lte: datetime], [evidence_certainty: select], [expand: text], [exposure_detection: select], [folder: text], [sort: text], [sub_threats_count_gte: integer], [sub_threats_count_lte: integer], [tier: text], [limit: integer], [offset: integer])` — Get Threat Impact
- `get_threat_statistics([folder: text], [scope: text], [tier: text])` — Get Threat Statistics


### `cymulate-asm` v1.0.0 _(installed)_
_Cymulate ASM_

The Cymulate Exposure Management and Security Validation Platform provides the technology for exposure
discovery, validation, and prioritization with business insights and intelligence. This simplifies security leaders’ risk
and resilience to emergent threats and a rapidly changing attack surface. With a complete view of the security
posture and business risks, the Cymulate platform gives security leaders the data they need to define the scope for cyber initiatives, successfully mobilize mitigations, and continuously assess security operations performance.

**9 operation(s)**:

_investigation_
- `create_internal_assessment(name: text, description: text, address: text, agentUserName: text, selectedPlatforms: text, crownJewels: json, [scheduledFor: datetime], scheduleLoop: text)` — Create Internal Assessment
- `delete_internal_assessment_by_id(id: text)` — Delete Internal Assessment By ID
- `get_assessment_list([fromDate: datetime], [toDate: datetime])` — Get Assessment List
- `get_assets_list_by_assessment_id(id: text)` — Get Assets List By Assessment ID
- `get_assets_list_for_latest_assessment()` — Get Assets List For Latest Assessment
- `get_findings_list_by_assessment_id(id: text)` — Get Findings List By Assessment ID
- `get_findings_list_for_latest_assessment()` — Get Findings List For Latest Assessment
- `get_internal_assessment_by_id(id: text)` — Get Internal Assessment By ID
- `get_internal_assessment_list(skip: integer, limit: integer)` — Get Internal Assessment List


### `fortinet-fortirecon-brand-protection` v2.1.0 _(installed)_
_Fortinet FortiRecon Brand Protection_

FortiRecon is a Digital Risk Protection Service (DRPS) product that provides an outside-the-network view to the risks posed to your enterprise.

**23 operation(s)**:

_investigation_
- `get_code_repo_exposures([q: text], [matched_domain: text], [risk_level: text], [attribute_type: text], [status: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Code Repo Exposures
- `get_code_repo_matched_domains_stats()` — Get Code Repo Matched Domains Statistics
- `get_code_repos([q: text], [matched_domain: text], [risk_level: text], [attribute_type: text], [status: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Code Repositories
- `get_code_repos_stats()` — Get Code Repos Statistics
- `get_domain_threats([q: text], [original_domain: text], [tags: text], [online_status: select], [status: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Domain Threats
- `get_domain_threats_by_id(id: text)` — Get Domain Threats By ID
- `get_domain_threats_stats()` — Get Domain Threats Statistics
- `get_executive_exposures([source_type: text], [executive_id: text], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Executive Exposures
- `get_executive_profiles([name: text], [page: integer], [size: integer])` — Get Executive Profiles
- `get_open_bucket_exposures([q: text], [file_type: text], [bucket_type: text], [status: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Open Bucket Exposures
- `get_open_bucket_exposures_stats()` — Get Open Bucket Exposures Statistics
- `get_original_domains_stats()` — Get Original Domains Statistics
- `get_rogue_app_by_id(id: text)` — Get Rogue App By ID
- `get_rogue_apps([status: multiselect], [q: text], [appstore: text], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Rogue Apps
- `get_social_media_threats([q: text], [media_type: text], [profile_name: text], [handle_name: text], [is_verified: select], [status: select], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Social Media Threats
- `get_social_media_threats_stats()` — Get Social Media Threats Statistics
- `get_tags()` — Get Tags
- `get_takedown_requests([q: text], [status: multiselect], [category: multiselect], [start_date: datetime], [end_date: datetime], [page: integer], [size: integer])` — Get Takedown Requests
- `update_code_repo_status(repo_id: text, status: select)` — Update Code Repo Status
- `update_domain_threat_status(domain_threat_id: text, status: select)` — Update Domain Threat Status
- `update_open_bucket_exposure_status(open_bucket_exposure_id: text, status: select)` — Update Open Bucket Exposure Status
- `update_rogue_app_exposure_status(rogue_app_exposure_id: text, status: select)` — Update Rogue App Status
- `update_social_media_threat_status(social_media_threat_id: text, status: select)` — Update Social Media Threat Status


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


### `soc-radar` v1.0.0 _(installed)_
_SOCRadar_

Threat Intelligence enriched with External Attack Surface Management and Digital Risk Protection Services

**4 operation(s)**:

_investigation_
- `change_status(alarm_id: integer, status: select, comments: text)` — Change Status
- `get_incident(alarm_id: integer)` — Get Incident
- `get_incidents([start_date: datetime], [end_date: datetime], status: select, [limit: integer], [page: integer])` — Get Incidents
- `threat_analysis(entity: text, [advance_investigation: checkbox], [force_new_analysis: checkbox])` — Threat Analysis


---

## Attack surface management

### `acronis` v1.0.0 _(installed)_
_Acronis Cyber Protect Cloud_

Acronis Cyber Protect Connect is a remote access solution to remotely manage workloads - quickly and easily. This connector facilitates automated operations to fetch alerts, target, service etc.

**5 operation(s)**:

_investigation_
- `create_alert([title: text], [type: text], [category: select], [tenant: text], [description: text], [other_fields: json])` — Create an Alert
- `delete_alert(alert_id: text)` — Delete an Alert
- `get_alert_types([os_type: select], [category: select], [order: select])` — Get Alert Types
- `get_alerts([alerts_id: text], [limit: integer])` — Get Alerts
- `get_categories()` — Get Categories


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


### `horizon3-ai` v1.0.0 _(installed, ingestion)_
_Horizon3.ai_

Horizon3.ai is a cybersecurity company specializing in automated security solutions. Their flagship product, NodeZero, is an autonomous penetration testing platform that simulates real-world cyberattacks to identify vulnerabilities and provide actionable remediation insights. Designed for ease of use, NodeZero empowers organizations to continuously assess and improve their security posture without relying heavily on manual intervention. It supports cloud, on-premise, and hybrid environments, making it adaptable to diverse IT setups.

**3 operation(s)**:

_investigation_
- `get_attack_paths(op_id: text, [page_num: integer], [page_size: integer])` — Get Attack Paths
- `get_pentests([text_search: text], [order_by: select], [sort_order: select], [date_field: select], [date_from: datetime], [date_to: datetime], [state: select], [client_name: text], [include_attack_paths: checkbox], [include_weaknesses: checkbox], [page_num: integer], [page_size: integer])` — Get Pentests
- `get_weaknesses(op_id: text, [page_num: integer], [page_size: integer])` — Get Weaknesses


### `ibm-randori` v1.0.0 _(installed)_
_IBM Randori_

IBM Randori is an attack surface management SaaS that monitors internal and external attack surfaces for unexpected changes, blind spots, misconfigurations, and process failures. This connector facilitates automated operations to fetch network, target, service etc.

**13 operation(s)**:

_investigation_
- `get_all_detections_for_target([q: json], [limit: integer], [offset: integer])` — Get All Detections for Target
- `get_artifact(artifact_uuid: text)` — Get Artifact by UUID
- `get_hostnames([q: json], [limit: integer], [offset: integer])` — Get Hostname List
- `get_ips([q: json], [limit: integer], [offset: integer])` — Get IP Objects
- `get_ips_for_hostname([q: json], [limit: integer], [offset: integer])` — Get IPs for Hostname
- `get_ips_for_network([q: json], [limit: integer], [offset: integer])` — Get IPs for Network
- `get_networks([q: json], [limit: integer], [offset: integer])` — Get Network List
- `get_policy([q: json], [limit: integer], [offset: integer])` — Get Policy List
- `get_report([q: json], [limit: integer], [offset: integer])` — Get Report List
- `get_services([q: json], [limit: integer], [offset: integer])` — Get Service List
- `get_single_detection_for_target([q: json], [limit: integer], [offset: integer])` — Get Single Detection for Target
- `get_statistics([q: json], [limit: integer], [offset: integer])` — Get Statistics List
- `get_targets([q: json], [limit: integer], [offset: integer])` — Get Target List


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

_investigation_
- `add_ssl_order(product_id: text, csr: text, server_count: integer, period: integer, webserver_type: text, [additional_field: json])` — Add SSL Order
- `add_ssl_renew_order(product_id: text, csr: text, server_count: integer, period: integer, approver_emails: text, [additional_field: json])` — Add SSL Renew Order
- `add_ssl_san_order(order_id: text, [wildcard_san_count: text], [single_san_count: integer])` — Add SSL SAN Order
- `cancel_order(order_id: text, [reason: text])` — Cancel Order
- `decode_csr(csr: text)` — Decode CSR
- `generate_csr(csr_commonname: text, csr_organization: text, csr_department: text, csr_city: text, csr_state: text, csr_country: text, csr_email: text)` — Generate CSR
- `get_all_orders_status(cids: text)` — Get All Orders Status
- `get_all_products()` — Get All Products
- `get_domain_alternative(csr: textarea)` — Get Domain Alternative
- `get_domain_emails(domain: text)` — Get Domain Emails
- `get_domain_emails_for_geo_trust(domain: text)` — Get Geotrust Approval Emails
- `get_domain_from_whois(domain: text)` — Get Approver Emails
- `get_orders_details(order_id: text)` — Get Orders Details
- `get_orders_metadata()` — Get Orders Metadata
- `get_product_details(product_id: text)` — Get Product Details
- `get_total_order_count()` — Get Total Order Count
- `reissue_ssl_order(order_id: text, csr: text, webserver_type: text, dcv_method: text, dns_names: text, [approver_emails: text], [approver_email: text], [signature_hash: text], [additional_field: json])` — Reissue SSL Order
- `validate_csr(csr: text)` — Validate CSR


---

## Automation controller

### `radware-alteon` v1.0.0 _(installed)_
_Radware Alteon_

Radware Alteon is a robust and feature-rich application delivery controller that helps organizations optimize application performance, enhance security, and ensure high availability, making it a valuable component of modern IT infrastructure

**5 operation(s)**:

_investigation_
- `add_table_element(ip_address: text, mask: text, [index: integer])` — Add Table Element
- `delete_table_element(index: integer)` — Delete Table Element
- `edit_table_element(ip_address: text, [mask: text], [index: integer])` — Edit Table Element
- `view_table()` — View Table
- `view_table_element(index: integer)` — View Table Element


---

## Breach and Attack Simulation

### `cymulate-full-kill-chain-campaign` v1.0.0 _(installed)_
_Cymulate Full Kill Chain Campaign - CART_

Cymulate Continuous Automated Red Teaming (CART) validates security controls and responses against real-world cyber attacks to stress-test defenses and identify gaps and does network pen testing, phishing awareness, real world cyber attacks. Users can use this connector to perform automated operations for managing Full Kill-Chain Campaign module data in your Cymulate account

**9 operation(s)**:

_investigation_
- `get_campaign_assessment_history([env: text], [fromDate: datetime], [toDate: text])` — Get Campaign Assessment History
- `get_campaign_assessment_status([id: text])` — Get Campaign Assessment Status
- `get_campaign_assessments_ids([env: text])` — Get Campaign Assessments IDs
- `get_campaign_report([env: text])` — Get Campaign Report
- `get_campaign_templates()` — Get Campaign Templates
- `get_specific_campaign_assessment_report(id: text, [skip: text], [limit: text])` — Get Specific Campaign Assessment Report
- `get_technical_report_for_specific_assessment(assessment_id: text)` — Get Technical Report for Specific Assessment
- `launch_campaign_assessment(templateID: text, schedule: datetime, scheduleLoop: Select)` — Launch Campaign Assessment
- `stop_campaign_assessment(env: text)` — Stop Campaign Assessment


---

## Breach and Attack Simulation (BAS)

### `ridgebot` v1.0.1 _(installed)_
_Ridge Security RidgeBot_

RidgeBot validates security vulnerabilities in your organization by using real POC codes to exploit the vulnerability. This connector facilitates automated operation such as creating and executing penetration testing tasks.

**5 operation(s)**:

_investigation_
- `create_task(name: text, temp_id: select, targets: text)` — Create Task
- `generate_and_download(task_id: text)` — Generate And Download
- `get_task_info(task_id: text)` — Get Task Info
- `get_task_statistics(task_id: text)` — Get Task Statistics

- `stop_task(task_id: text)` — Stop Task


---

## CMDB

### `cherwell` v1.0.0 _(installed)_
_Cherwell_

Cherwell connector

**6 operation(s)**:

_Miscellaneous_
- `report_template([dummy: text])` — Show Incident Template

_investigation_
- `advance_search(filter_query: text, sort_query: text, [fields: text], [include_all_fields: checkbox], [include_schema: checkbox], [page_number: text], [page_size: text])` — Advance Search
- `create_incident(requester: text, short_description: text, description: text, [source: select], [service: select], priority: select, [additional_input: text])` — Create Incident
- `quick_search(field_name: select, filter_option: select, value: text, sort_direction: select, [fields: text], [include_all_fields: checkbox], [include_schema: checkbox], [page_number: text], [page_size: text])` — Quick Search
- `update_cyops_incident(cyops_record_list: text, csm_cyop_mapping: text, [incident_picklist_mapping: text])` — Update CyOPs Incident
- `update_incident_in_cherwell(incident_id: text, [status: text], priority: text, [additional_input: text])` — Update Cherwell Incident


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


### `tanium` v2.0.1 _(installed)_
_Tanium_

Tanium is an endpoint security and system management solution. This connector facilitates the automated operations like get computer information,installed softwares,running processes,execute package on machine,issue saved question, ask question and reissue action

**7 operation(s)**:

_investigation_
- `ask_question(question_text: text)` — Ask Question
- `get_computer_information(sensors: multiselect, information_by: select, value: text)` — Get Computer Information
- `get_installed_software(information_by: select, value: text)` — Get Installed Softwares
- `get_running_processes(information_by: select, value: text)` — Get Running Processes
- `issue_saved_question(saved_question_id: text)` — Issue a Saved Question

_miscellaneous_
- `execute_package_on_machine(package_name: text, [package_inputs: json], information_by: select, value: text)` — Execute Package on Machine
- `reissue_action(action_id: text)` — Reissue Action


---

## CTI

### `facebook-threat-exchange` v1.0.0 _(installed)_
_Facebook ThreatExchange_

Provide CTI actions like search malware data, get threat indicators for IP, Domain etc from ThreatExchange

**4 operation(s)**:

_investigation_
- `get_malware_families(since: datetime, until: datetime)` — Get Malware Families
- `get_threat_descriptors(type: select, status: select, since: datetime, until: datetime)` — Get Threat Descriptor
- `get_threat_indicators(type: select, since: datetime, until: datetime)` — Get Threat Indicators
- `search_malware_data(sample_type: select, status: select, since: datetime, until: datetime)` — Search Malware Data


### `greynoise` v2.0.0 _(installed)_
_GreyNoise_

GreyNoise provides information on devices observed mass-scanning the internet. This integration provides a set of actions to lookup IPs or query the GreyNoise API. For support or to report issues or enhancements, please contact support@greynoise.io.

**9 operation(s)**:

_investigation_
- `get_all_tag_metadata()` — Get All GreyNoise Tag Metadata
- `get_tag_details(tag_name: text)` — Get GreyNoise Tag Details
- `gnql_query(query: text, max_results: numeric)` — GreyNoise GNQL Query
- `lookup_ip_community(ip_address: text)` — Lookup GreyNoise IP Community Information
- `lookup_ip_complete(ip_address: text)` — Lookup GreyNoise IP Information (Noise, RIOT, Tags)
- `lookup_ip_context(ip_address: text)` — Lookup GreyNoise IP Context Information
- `lookup_ip_quick(ip_address: text)` — Lookup GreyNoise IP Quick Information
- `lookup_ip_riot(ip_address: text)` — Lookup GreyNoise IP RIOT Information
- `stats_query(query: text)` — Stats Query


### `metadefender` v1.2.0 _(installed)_
_Metadefender Cloud_

Metadefender Cloud provides file, sandbox and IP reputation

**7 operation(s)**:

_investigation_
- `get_hash_lookup_with_sandbox(hash: text)` — Get Hash Lookup With Sandbox
- `get_hash_reputation(hash: text)` — Get Filehash Reputation
- `get_ip_reputation(ip_address: text)` — Get IP Reputation
- `get_sandbox_lookup(sandbox_id: text)` — Get Sandbox Lookup
- `get_scan_file_result(data_id: text)` — Get Scan File Result
- `get_scan_with_sandbox(data_id: text, sandbox: select)` — Get Scan With Sandbox
- `submit_file(file_iri: text)` — Submit File


### `trustar` v1.0.0 _(installed)_
_TruSTAR_

TruSTAR synchronizes the incident report information available in the TruSTAR platform to the monitoring tools and analysis workflows.

**6 operation(s)**:

_investigation_
- `get_indicator(report_id: text, id_type: select)` — Get Indicator
- `get_report(report_id: text, id_type: select)` — Get Report
- `get_report_details(indicator: select, [other_indicator: text], value: text)` — Get Report Details
- `submit_report(title: text, externalTrackingId: text, timeBegan: datetime, reportBody: text, distributionType: select, [enclaveIds: text])` — Submit Report
- `update_report(report_id: text, id_type: select, [title: text], [externalTrackingId: text], [timeBegan: datetime], [reportBody: text], [distributionType: select], [enclaveIds: text])` — Update Report

_miscellaneous_
- `delete_report(report_id: text, id_type: select)` — Delete Report


---

## Case Management

### `thehive` v1.0.0 _(installed)_
_TheHive_

TheHive Security Incident Response Platform involves connecting external security tools, systems, or data sources with TheHive's platform. This integration facilitates centralized incident management, response coordination, and automation, enhancing overall security operations by streamlining incident detection, investigation, and resolution processes.

**21 operation(s)**:

_investigation_
- `add_alert_attachment(alertID: text, attachment: file, [canRename: checkbox])` — Add Alert Attachment
- `create_alert(title: text, description: text, type: text, source: text, type: text, [severity: text], [assignee: text], [summary: text], [attachment: file], [observables: json], [additional_field: json])` — Create Alert
- `create_case(title: text, description: text, [summary: text], [assignee: text], [severity: text], [status: text], [additional_field: json])` — Create Case
- `create_observable_in_alert(alertID: text, dataType: select, [message: text], tags: text, [ignoreSimilarity: checkbox], [additional_field: json])` — Create Observable in Alert
- `create_observable_in_case(caseID: text, dataType: select, [message: text], [tags: text], [tlp: text], [ignoreSimilarity: checkbox], [additional_field: json])` — Create Observable in Case
- `create_task(caseId: text, title: text, [description: text], [status: text], [group: text], [assignee: text], [additional_field: json])` — Create Task in Case
- `delete_alert(alertID: text)` — Delete Alert
- `delete_alert_attachment(alertID: text, attachmentId: text)` — Delete Alert Attachment
- `delete_case(caseID: text)` — Delete Case
- `delete_observable(observableId: text)` — Delete Observable
- `delete_task(taskID: text)` — Delete Task
- `download_alert_attachment(alertID: text, attachmentId: text)` — Download Alert Attachment
- `get_alert(alertID: text)` — Get Alert
- `get_alert_attachment(alertID: text, attachmentId: text)` — Get Alert Attachment
- `get_case(caseID: text)` — Get Case
- `get_observable(observableId: text)` — Get Observable
- `get_task(TaskID: text)` — Get Task
- `update_alerts(action_type: select, [title: text], [description: text], [source: text], [type: text], [severity: text], [assignee: text], [summary: text], [additional_field: json])` — Update Alerts
- `update_case(action_type: select, [title: text], [description: text], [summary: text], [assignee: text], [severity: text], [status: text], [additional_field: json])` — Update Case
- `update_observable(action_type: select, dataType: select, [message: text], [addTags: text], [removeTags: text], [ignoreSimilarity: checkbox], [additional_field: json])` — Update Observable
- `update_task(action_type: select, [title: text], [description: text], [status: text], [group: text], [assignee: text], [additional_field: json])` — Update Task


### `trello` v1.0.0 _(installed)_
_Trello_

Trello is a collaboration tool that organizes your projects into boards. Trello tells you what's being worked on, who's working on what, and where something is in a process.

**8 operation(s)**:

_investigation_
- `create_card(idList: text, [name: text], [desc: text], [other_fields: json])` — Create a new Card
- `create_label(name: text, color: text, idBoard: text)` — Create a Label
- `delete_card(card_id: text)` — Delete a Card
- `get_board(board_id: text)` — Get a Board
- `get_card(card_id: text, [other_fields: json])` — Get a Card
- `get_label(label_id: text)` — Get a Label
- `get_list(list_id: text)` — Get a List
- `update_card(card_id: text, [name: text], [desc: text], [other_fields: json])` — Update a Card


---

## Case Management,Threat Intelligence

### `proofpoint-trap` v1.1.0 _(installed)_
_Proofpoint TRAP_

Perform actions like Get incident details, Retrieve incidents, Close Incidents and Create Alert from JSON source using Proofpoint TRAP

**5 operation(s)**:

_investigation_
- `close_incidents(incidentIDs: text, closeSummary: text, closeDetail: textarea)` — Close Incidents
- `create_alert_from_json_source(alertSourceID: text, data: object)` — Create Alert from JSON Source
- `execute_api_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_incident_details(incidentID: text)` — Get Incident Details
- `get_incidents(state: select, [createdAfterDate: datetime], [createdBeforeDate: datetime], [emailMessageID: text])` — Get Incidents


---

## Central Management System

### `fireeye-cms` v1.0.1 _(installed)_
_FireEye CMS_

FireEye CMS connector perform automated operations such as retrieving a list of all guest image profiles and applications details, add/delete custom IOC feed and retrieving data for alerts,events.

**6 operation(s)**:

_containment_
- `add_custom_feed(feedName: text, feedType: select, feedAction: text, feedSource: text, content: textarea, [overwrite: checkbox])` — Add Custom Feed

_investigation_
- `get_configurations()` — Get Configurations
- `get_custom_feeds()` — Get Custom Feeds
- `get_events(duration: select, event_type: select)` — Get Events
- `get_open_alerts([alert_id: integer], [info_level: select], [url: text], [file_name: text], [file_type: text], [malware_name: text], [malware_type: text], [date_filter: select], [date: text])` — Get Open Alerts

_remediation_
- `delete_custom_feeds(feed_name: text)` — Delete Custom Feeds


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


### `trendmicro-apex-central` v1.1.0 _(installed, ingestion)_
_Trend Micro Apex Central_

Trend Micro Apex Central connector automates to list servers, perform action on agent such as isolate,restore, relocate and uninstall etc.

**13 operation(s)**:

_investigation_
- `add_udso_entries(type: select, scan_action: select, [notes: text], [expiration_date: datetime])` — Add UDSO to List
- `create_assessment(TaskType: select, typeId: select, condition: select, value: text, [searchPeriod: select])` — Create Assessment
- `create_live_investigation(name: text, TaskType: select, agentGuid: text, serverGuid: text, typeId: select, condition: select, value: text, rangeType: select)` — Create Live Investigation
- `download_rca_file(TaskType: select, hostIP: text, hostName: text, agentGuid: text, scanSummaryGuid: text, serverGuid: text)` — Download RCA CSV File
- `get_rca_response(TaskType: select, TaskId: text, TopN: text, serverGuid: text, [ContentId: text])` — Get RCA Response
- `get_syslog_data(log_type: select, [page_token: text], [time_range: select], [output_format: text])` — Get Syslog Data
- `get_task_id_analysis_chain(TaskType: select, agentGuid: text, scanSummaryGuid: text, serverGuid: text)` — Get Task ID of RCA in Analysis Chain
- `get_task_id_table_format(TaskType: select, agentGuid: text, scanSummaryGuid: text, serverGuid: text)` — Get Task ID of RCA in Table Format
- `list_agent([entity_id: text], [ip_address: text], [mac_address: text], [host_name: text], [product: text], [managing_server_id: text])` — List Security Agents
- `list_investigation_result(TaskType: select, scanType: multiselect, [limit: text], [offset: text], [type: select])` — Get All Investigation Results
- `list_server([entity_id: text], [ip_address: text], [mac_address: text], [host_name: text], [product: text])` — List Product Server
- `list_udso_entries([type: select], [contentFilter: text])` — List UDSO Entries
- `perform_action(act: select, allow_multiple_match: checkbox, [entity_id: text], [host_name: text], [ip_address: text], [mac_address: text], [product: text])` — Perform Action on Security Agent


---

## Cloud Security

### `azure-network-security-group` v1.2.0 _(installed)_
_Azure Network Security Group_

Azure network security group to filter network traffic to and from Azure resources in an Azure virtual network. This connector facilitates automated operations to get list of network security groups, get details of network security group, create network security group, update network security group and delete network security group etc.

**10 operation(s)** (+5 hidden):

_investigation_
- `create_network_security_group(subs_id: select, resource_group_name: select, nsg_name: text, location: select, rule_type: select)` — Create Network Security Group
- `delete_network_security_group(subs_id: select, resource_group_name: select, nsg_name: select)` — Delete Network Security Group
- `get_network_security_group_info(subs_id: select, resource_group_name: select, nsg_name: select)` — Get Network Security Group Info
- `list_of_network_security_groups(subs_id: select, [resource_group_name: select])` — List Network Security Groups
- `update_network_security_group(subs_id: select, resource_group_name: select, nsg_name: select, operation_to_perform_on_network_security_group: select)` — Update Network Security Group


### `fortinet-forticnapp` v1.1.0 _(installed, ingestion)_
_Lacework FortiCNAPP_

Lacework delivers end-to-end visibility into what’s happening across your cloud environment, including detecting threats, vulnerabilities, misconfigurations, and unusual activity, so you can innovate with speed and safety.

**11 operation(s)**:

_investigation_
- `add_comment_to_alert(alertId: integer, comment: text, [format: select])` — Add Comment to Alert
- `close_alert(alertId: integer, reason: select)` — Close Alert
- `get_alert_details(alertId: integer, scope: select)` — Get Alerts Details
- `get_alert_entities(alertId: integer)` — Get Alert Entities
- `get_alert_entity_details(alertId: integer, contextEntityType: select, entityValue: text)` — Get Alert Entity Details
- `lql_query(query: text, [startTime: datetime], [endTime: datetime], [limit: integer])` — Run LQL Query
- `search_alerts([startTime: datetime], [endTime: datetime], [alertId: integer], [alertType: text], [severity: select], [status: select], [category: select], [subCategory: select], [source: select], [returns: text])` — Search Alerts
- `search_configuration(dataset: select, [startTime: datetime], [endTime: datetime], [account.AccountId: text], [account.tenantId: text], [account.subscriptionId: text], [account.projectId: text], [id: text], [region: text], [resource: text], [severity: select], [status: select], [returns: text])` — Search Configuration
- `search_container_vulnerabilities([startTime: datetime], [endTime: datetime], [packageStatus: select], [imageRiskInfo.factors_breakdown.internet_reachability: select], [imageRiskInfo.factors_breakdown.exploit_summary.exploit_public: select], [imageId: text], [fixInfo.fix_available: select], [severity: select], [returns: text])` — Search Container Vulnerabilities
- `search_host_vulnerabilities([startTime: datetime], [endTime: datetime], [packageStatus: select], [props.kernel_status: select], [riskInfo.host_risk_factors_breakdown.internet_reachability: select], [riskInfo.host_risk_factors_breakdown.exploit_summary.exploit_public: select], [fixInfo.fix_available: select], [machineTags.Account: text], [machineTags.TenantId: text], [machineTags.SubscriptionId: text], [machineTags.ProjectId: text], [machineTags.InstanceId: text], [machineTags.AmiId: text], [machineTags.Hostname: text], [machineTags.Name: text], [severity: select], [returns: text])` — Search Host Vulnerabilities
- `send_custom_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Call


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

**26 operation(s)**:

_investigation_
- `add_annotation(annotations: json, [account_uuid: text])` — Add Annotation
- `add_or_replace_entities_to_annotation(annotation_uuid: text, entities: json, [replace: checkbox])` — Add or Replace Entities to Annotation
- `delete_annotation(annotation_uuid: text)` — Delete Annotation
- `delete_pcap_task(task_uuid: text)` — Delete PCAP Task
- `download_pcap_task_file(task_uuid: text, [file_name: text])` — Download PCAP Task File
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
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
- `modify_annotation(annotation_uuid: text, annotation: json)` — Modify Annotation
- `resolve_detection(detection_uuid: text, resolution: select, [resolution_comment: text])` — Resolve Detection
- `retrieve_annotation_for_entities(entities: json, [account_uuid: text])` — Retrieve Annotation for Entities
- `retrieve_annotations([account_uuid: text], [value: text], [entity: text], [entity_type: text], [limit: integer], [offset: text])` — Retrieve Annotations
- `terminate_pcap_task(task_uuid: text)` — Terminate PCAP Task


### `fortinet-fortiweb-cloud` v2.0.0 _(installed)_
_Fortinet FortiAppSec Cloud_

FortiAppSec Cloud simplifies and strengthens application security and delivery across hybrid and cloud environments. This SaaS platform secures network availability and accelerates application performance while delivering consistent security.

**13 operation(s)**:

_investigation_
- `add_ip_protection(epid: text, iptype: select, ipaddress: text)` — Add IP Protection
- `delete_ip_protection(epid: text, iptype: select, ipaddress: text)` — Delete IP Protection
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_application_list([filter: json], [size: integer], [cursor: text], [forward: checkbox])` — Get Applications List
- `get_incident_aggregated_details(incident_id: text, name: select)` — Get Incident Aggregated Details
- `get_incident_dashboard_details(widget_id: select, [action: select], [host: text], [time_range: text])` — Get Incident Dashboard Details
- `get_incident_details(incident_id: text)` — Get Incident Details
- `get_incident_list(time_range: text, [filter: json], [size: integer], [page: integer])` — Get Incidents List
- `get_incident_timeline_details(incident_id: text)` — Get Incident Timeline Details
- `get_insight_events(type: select, [cursor: text], [size: integer], [forward: checkbox])` — Get Insight Events
- `get_insight_events_summary()` — Get Insight Events Summary
- `get_ip_protection(epid: text)` — Get IP Protection
- `update_geo_ip_block_list(epid: text, operation_to_perform: select, [block_country_list: multiselect])` — Update Geo IP Block List


### `microsoft-defender-for-cloud` v1.2.0 _(installed, ingestion)_
_Microsoft Defender For Cloud_

Microsoft Defender for Cloud is a solution for cloud security posture management (CSPM) and cloud workload protection (CWP) that finds weak spots across your cloud configuration, helps strengthen the overall security posture of your environment, and can protect workloads across multicloud and hybrid environments from evolving threat.This connector facilitates the automated operations related to alerts, managing APS, ATP etc.

**15 operation(s)**:

_investigation_
- `get_alert_list([subscription_id: text], [resource_group_name: text], [asc_location: text])` — Get Alert List
- `get_aps([subscription_id: text], setting_name: text)` — Get APS
- `get_aps_list([subscription_id: text])` — Get APS List
- `get_atp(resource_id: text, [setting_name: text])` — Get ATP
- `get_jit_list([subscription_id: text], [resource_group_name: text], [asc_location: text])` — Get JIT List
- `get_locations_list([subscription_id: text])` — Get Locations List
- `get_secure_score([subscription_id: text], [secure_score_name: text])` — Get Secure Score
- `get_storage_list([subscription_id: text])` — Get Storage List
- `get_subscriptions_list()` — Get Subscriptions List
- `list_management_groups([fetch_all: checkbox])` — Get Management Group List
- `list_subscriptions_by_management_group_id(group_id: text, [fetch_all: checkbox])` — Get Subscription List By Management Group ID
- `search_alerts([subscription_id: text], [resource_group_name: text], [asc_location: text], [reported_severity: select], [state: select], [detected_after: datetime], [limit: integer])` — Search Alerts
- `update_alert([subscription_id: text], alert_name: text, change_state_to: select, asc_location: text, [resource_group_name: text])` — Update Alert
- `update_aps([subscription_id: text], setting_name: text, auto_provision: select)` — Update APS
- `update_atp([subscription_id: text], resource_group_name: text, storage_account: text, is_enabled: select, [setting_name: text])` — Update ATP


### `netapp-ontap` v1.0.0 _(installed)_
_NetApp ONTAP_

ONTAP helps you create a storage infrastructure that reduces costs, accelerates critical workloads, and protects and secures data across your hybrid multicloud.

**4 operation(s)**:

_investigation_
- `get_security_accounts([fields: text], [max_records: integer], [return_records: checkbox], [return_timeout: integer], [order_by: select])` — Get Security Accounts
- `get_security_audit_messages([timestamp: datetime], [state: text], [application: text], [session_id: text], [scope: text], [command_id: text], [index: integer], [location: integer], [fields: text], [max_records: integer], [return_records: checkbox], [return_timeout: integer], [order_by: select])` — Get Security Audit Messages
- `get_security_roles([fields: text], [max_records: integer], [return_records: checkbox], [return_timeout: integer], [order_by: select])` — Get Security Roles
- `update_user_password(name: text, max_records: password, [owner_name: text], [owner_uuid: text])` — Update User Password


### `rapid7-insightcloudsec` v1.0.0 _(installed)_
_Rapid7 InsightCloudSec_

InsightCloudSec secures your public cloud environment from development to production with a modern, integrated, and automated approach. This connector facilitates automated operation such as retrieving resource related information.

**3 operation(s)**:

_investigation_
- `get_list_resource_tags(resource_id: text)` — Get Resource Tags List
- `get_resource_details(resource_id: text)` — Get Resource Details
- `run_resource_query([badges: json], [badge_filter_operator: select], [filters: json], [insight: text], [scopes: text], [selected_resource_type: text], [tags: text], [order_by: text], limit: integer, [offset: integer])` — Run Resource Query


### `trend-micro-cloud-app-security` v1.0.0 _(installed)_
_Trend Micro Cloud App Security_

Trend Micro Cloud App Security provides advanced protection for the following cloud applications and services to enhance security with powerful enterprise-class threat and data protection control: Microsoft Office 365 services (Exchange Online, SharePoint Online, OneDrive, Microsoft Teams), Box, Dropbox, and Google Workspace (Google Drive, Gmail).Cloud App Security provides protection against ransomware, phishing, Business Email Compromise (BEC), zero-day and hidden malware, and unauthorized transmission of sensitive data. It integrates cloud-to-cloud with the protected applications and services to maintain high availability and administrative functionality.

**10 operation(s)**:

_investigation_
- `get_blocked_list()` — Get Blocked List
- `get_email([mailbox: text], [lastndays: text], [start: datetime], [end: datetime], [subject: text], [file_sha1: text], [file_sha256: text], [file_name: text], [file_extension: text], [url: text], [sender: text], [recipient: text], [message_id: text], [source_ip: text], [source_domain: text], [limit: text], [get_all_pages: checkbox])` — Get Email
- `get_email_action_result(batch_id: text, [start: datetime], [end: datetime], [limit: text], [get_all_pages: checkbox])` — Get Email Action Result
- `get_quarantine_events(service: text, [start: datetime], [end: datetime], [limit: text], [get_all_pages: checkbox])` — Get Quarantine Events
- `get_security_logs(service: select, event: select, [start: datetime], [end: datetime], [limit: text], [get_all_pages: checkbox])` — Get Security Logs
- `get_user_action_result(batch_id: text, [start: datetime], [end: datetime], [limit: text], [get_all_pages: checkbox])` — Get User Action Result
- `get_virtual_analyzer_report(report_id: text)` — Get Virtual Analyzer Report
- `take_action_on_email(action_type: select, service: select, account_provider: select, mailbox: text, mail_message_id: text, mail_unique_id: text, mail_message_delivery_time: datetime, detection_time: datetime, mail_log_id: text)` — Take Action On Email
- `take_action_on_user(action_type: select, service: text, account_provider: text, account_user_email: text)` — Take Action On User
- `update_blocked_list(action_type: select, [senders: text], [urls: text], [filehashes: text], [file256hashes: text])` — Update Blocked List


### `zscaler-internet-access` v1.0.0 _(installed)_
_Zscaler Internet Access_

Zscaler Internet Access (ZIA) connector enables automated operations such as Get Firewall Filtering Rules, Get Specific Firewall Filtering Rule, Get Time Windows, Get Network Applications, Get Network Services, Get Network Services Groups, Get Network Applications Groups, and Execute an API Request.

**8 operation(s)**:

_utilities_
- `execute_api_request(endpoint: text, method: select, [Query Parameters: json], [payload: json])` — Execute an API Request
- `get_firewall_filtering_rules()` — Get Firewall Filtering Rules
- `get_network_application_groups()` — Get Network Applications Groups
- `get_network_applications()` — Get Network Applications
- `get_network_service_groups()` — Get Network Services Groups
- `get_network_services([search: text], [protocol: select], [locale: text])` — Get Network Services
- `get_specific_firewall_filtering_rule(id: text)` — Get Specific Firewall Filtering Rule
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

_investigation_
- `get_datapatterns()` — Get Data Patterns
- `get_policies()` — Get Policies
- `search_activity([startTime: datetime], [endTime: datetime], [service: text], [idList: text], [activity: text], [ipList: text])` — Search Activity
- `search_alerts(service: text, [startTime: datetime], [endTime: datetime], [user: text], [policy: text], [severity: text], [status: text], [idList: text], [businessunitname: text])` — Search Alerts

_miscellaneous_
- `get_resource_url_map()` — Get Resource URL Map


---

## Communication

### `hip-chat` v1.0.0 _(installed)_
_HipChat_

HipChat is a web service for internal private online chat and instant messaging.

**3 operation(s)**:

_investigation_
- `get_all_rooms(start_index: integer, max_result: integer, include_guests: checkbox, include_deleted: checkbox)` — Get All Rooms
- `get_all_users(start_index: integer, max_result: integer, include_guests: checkbox, include_deleted: checkbox)` — Get All Users
- `send_massage(room_id: text, message: text)` — Send Message


### `messagebird` v1.0.1 _(installed)_
_MessageBird_

MessageBird is a platform for communications and connecting companies to their customers on billions of devices. sending outbound SMS messages with MessageBird

**4 operation(s)**:

_investigation_
- `delete_message(id: text)` — Delete Message
- `get_messages()` — Get Messages
- `get_specific_message_details(id: text)` — Get Specific Message Details
- `send_message(originator: text, body: text, recipients: text)` — Send Message


### `microsoft-intune` v1.0.0 _(installed)_
_Microsoft Intune_

Microsoft Intune is a cloud-based endpoint management solution. This connector facilitates automated operation related to managed device.

**20 operation(s)**:

_investigation _
- `bypass_activation_lock_of_device(managedDeviceId: text)` — Bypass Activation Lock for Device
- `clean_windows_device(managedDeviceId: text)` — Clean Windows Device
- `delete_user_from_shared_apple_device(managedDeviceId: text)` — Delete User from Apple Device
- `disable_lost_mode_of_device(managedDeviceId: text)` — Disable Lost Mode for Device
- `get_managed_device_details(managedDeviceId: text)` — Get Managed Device Details
- `list_managed_devices()` — Get Managed Devices List
- `locate_device(managedDeviceId: text)` — Locate a Device
- `logout_shared_apple_device_active_user(managedDeviceId: text)` — Logout Apple Device for Active User
- `reboot_device(managedDeviceId: text)` — Reboot Device
- `recover_passcode_of_device(managedDeviceId: text)` — Recover Passcode for Device
- `remote_lock_of_device(managedDeviceId: text)` — Remote Lock Device
- `request_remote_assistance_of_device(managedDeviceId: text)` — Request Remote Assistance for Device
- `reset_passcode_of_device(managedDeviceId: text)` — Reset Passcode Device
- `retire_device(managedDeviceId: text)` — Retire Device
- `shutdown_device(managedDeviceId: text)` — Shutdown Device
- `sync_device(managedDeviceId: text)` — Sync Device
- `update_windows_device_account(managedDeviceId: text)` — Update Account for Windows Device
- `windows_defender_scan(managedDeviceId: text)` — Windows Defender Scan
- `windows_defender_update_signature(managedDeviceId: text)` — Update Signature for Windows Defender
- `wipe_device(managedDeviceId: text)` — Wipe Device


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


### `twitter` v1.0.0 _(installed)_
_Twitter_

Twitter is an online news and social networking service. This Connector facilitates automated interactions, such as posting tweets and searching for tweets, in Twitter accounts using CyOPs™ playbooks

**5 operation(s)**:

_investigation_
- `get_user([user_id: integer], [screen_name: text], [include_entities: checkbox])` — Get User
- `get_user_timeline([user_id: integer], [screen_name: text], [since_id: integer], [max_id: integer], [count: integer], [include_rts: checkbox], [trim_user: checkbox], [exclude_replies: checkbox])` — Get User Timeline
- `search_tweets([term: text], [geocode: text], [since_id: integer], [max_id: integer], [until: datetime], [since: datetime], [count: integer], [lang: text], [result_type: select], [include_entities: checkbox])` — Search Tweets
- `send_direct_message(text: text, [user_id: integer], [screen_name: text])` — Send Direct Message

- `post_tweet(status: text, [media: text], [in_reply_to_status_id: integer], [auto_populate_reply_metadata: checkbox], [exclude_reply_user_ids: text], [latitude: text], [longitude: text], [place_id: text], [display_coordinates: checkbox], [trim_user: checkbox], [verify_status_length: checkbox], [attachment_url: text])` — Post Tweet


### `zoom` v1.0.0 _(installed)_
_Zoom_

Zoom Connector can be used to automate actions like Create New Meeting, Get Meetings, Get Meeting Details, Update Meeting, Delete Meeting and Get Users

**6 operation(s)**:

_investigation_
- `create_new_meeting(type: select, [topic: text], [password: password], [agenda: text])` — Create New Meeting
- `delete_meeting(meetingId: text, [occurrence_id: text], [schedule_for_reminder: checkbox], [cancel_meeting_reminder: checkbox])` — Delete Meeting
- `get_meeting_details(meetingId: text, [occurrence_id: text], [show_previous_occurrences: checkbox])` — Get Meeting Details
- `get_meetings([userId: text], [type: select], [page_size: integer], [page_number: integer], [next_page_token: text])` — Get Meetings
- `get_users([status: select], [page_size: integer], [page_number: integer], [include_fields: text], [next_page_token: text])` — Get Users
- `update_meeting(meetingId: text, [occurrence_id: text], [schedule_for: text], [topic: text], [type: select], [password: password], [agenda: text])` — Update Meeting


---

## Communication and Coordination

### `clicksend` v2.0.0 _(installed)_
_ClickSend_

ClickSend is a cloud-based service that lets you send and receive SMS, Email, Voice, Fax, and Letters worldwide.

**3 operation(s)**:

_investigation_
- `get_contact_list([page: integer], [limit: integer])` — Get Contact List
- `send_message(body: textarea, send_to: select, [from: text], [schedule: datetime], [custom_string: text], [country: text], [from_email: text])` — Send Message
- `send_voice_message(body: textarea, voice: select, send_to: select, [schedule: datetime], [custom_string: text], [country: text], [lang: text], [require_input: checkbox], [machine_detection: checkbox])` — Send Voice Message


### `ducont-sms` v1.0.0 _(installed)_
_Ducont SMS_

The WCF Restful Service - Push SMS supports single and bulk messages request with parameterized or customized message.

**2 operation(s)**:

_investigation_
- `push_sms(recipients: text, body: textarea, sender_id: text, message_id: text, priority: select, [channel_id: text], [template_id: text], [template_variables: json], validity_period: integer, language_id: text, [confirm_delivery: select])` — Push SMS
- `push_sms_sub(recipients: text, body: textarea, [channel_id: text], sender_id: text, message_id: text, priority: select, [template_id: text], [template_variables: textarea], validity_period: text, language_id: text, confirm_delivery: select)` — Push SMS SUB


### `fortinet-fortivoice` v1.0.0 _(installed)_
_Fortinet FortiVoice_

FortiVoice Secure Unified Communications, along with FortiFone IP phones, helps organizations keep up with changing communication needs due to evolving infrastructure, remote/hybrid work, and BYOD.

**1 operation(s)**:

_investigation_
- `get_devices_list([search_mac_address: text], [get_non_assigned_devices: checkbox], [start_index: integer], [size: integer])` — Get Devices List


### `kafka` v1.0.0 _(installed)_
_Kafka_

Kafka is an open-source distributed event streaming platform. This Kafka Connector is use to publish/consume a messages to/from a topic.

**4 operation(s)**:

_investigation_
- `send_b64encoded_message_to_topic([topic: text], [base64msg: text])` — Send b64encoded Message to Topic
- `send_str_message_to_topic(topic: text, message: text)` — Send String Message to Topic
- `topic_details(topics: object, [timeout_ms: integer], max_records: integer, [seek_partition: object])` — Kafka Topic Details
- `topic_list()` — Kafka Topic List


### `mcafee-open-dxl` v1.1.0 _(installed)_
_McAfee OpenDXL_

The McAfee Open Data Exchange Layer (DXL) Connector allow automated way to communicate across multiple mcafee products with optimized security actions.

**1 operation(s)**:

_miscellaneous_
- `publish_message(topic: text, message: text)` — Publish Message to Topic


### `microsoft-teams` v3.1.1 _(installed)_
_Microsoft Teams_

Microsoft Teams is a chat-based workspace in Office 365 that provides global, remote, and dispersed teams with the ability to work together and share information using a common space. This connector facilitates automated operation related to teams.

**36 operation(s)**:

_investigation_
- `add_member(group_id: text, user_id: text)` — Add Group's Member
- `add_owner(group_id: text, user_id: text)` — Add Group's Owner
- `archive_team(id: text)` — Archive Team
- `clone_team(id: text, displayName: text, mailNickname: text, partsToClone: text, [visibility: select])` — Clone Team
- `create_channel(group_id: text, displayName: text, description: text, membershipType: select, [custom_attributes: json])` — Create Channel
- `create_meeting(subject: text, [user_id: text], [startDateTime: datetime], [endDateTime: datetime], [custom_attributes: json])` — Create Meeting
- `create_team(displayName: text, description: text, [user_id: text], [teamsTemplates: text], [visibility: select], [custom_attributes: json])` — Create Team
- `delete_meeting(meeting_id: text, [user_id: text])` — Delete Meeting
- `get_channel(group_id: text, [channel_id: text], [custom_attributes: json])` — Get Channel Details
- `get_channel_messages(group_id: text, channel_id: text, [message_id: text])` — Get Channel's Messages
- `get_chat_messages(chat_id: text)` — Get Chat Messages
- `get_group_owner(group_id: text, [custom_attributes: json])` — Get Group's Owner
- `get_groups([group_id: text], [custom_attributes: json])` — Get Groups
- `get_meeting(meeting_id: text, [user_id: text], [custom_attributes: json])` — Get Meeting Details
- `get_replies_to_channel_message(group_id: text, channel_id: text, message_id: text, [limit: integer])` — Get Replies to Channel Message
- `get_team(group_id: text, [custom_attributes: json])` — Get Team Details
- `get_users_all_messages(based_on: select, [query_string: text], [limit: integer])` — Get User's all Chat Messages
- `list_user_joined_teams([user_id: text])` — Get User's Teams
- `messages_mention(group_id: text, channel_id: text, message: text, user_id: text, displayName: text)` — Tag User in Message
- `reply_messages(group_id: text, channel_id: text, message_id: text, message: text)` — Reply Message
- `send_chat(sender_user_email: text, receiver_user_email: text, message_type: select)` — Send Direct Message
- `send_message(group_id: text, channel_id: text, message_type: select)` — Send Message to Channel
- `send_message_or_approval_form_to_bot(type: select)` — Send Bot Message/Input Form
- `unarchive_team(id: text)` — Unarchive Team
- `update_meeting(meeting_id: text, [user_id: text], [startDateTime: datetime], [endDateTime: datetime], [subject: text], [allowAttendeeToEnableCamera: checkbox], [allowAttendeeToEnableMic: checkbox], [custom_attributes: json])` — Update Meeting Details
- `update_team(id: text, custom_attributes: json)` — Update Team Details

_investigation _
- `create_group(displayName: text, mailNickname: text, [mailEnabled: checkbox], [securityEnabled: checkbox], [groupTypes: text], [description: text], [visibility: select], [custom_attributes: json])` — Create Group
- `create_user(displayName: text, accountEnabled: checkbox, mailNickname: text, userPrincipalName: text, password: password, [forceChangePasswordNextSignIn: checkbox], [custom_attributes: json])` — Create User
- `delete_group(group_id: text)` — Delete Group
- `delete_user(based_on: select)` — Delete User
- `get_group_member(group_id: text, [user_id: text], [custom_attributes: json])` — Get Group's Member
- `get_users(based_on: select)` — Get User Details
- `list_users([$filter: text], [$select: text], [$search: text], [$orderBy: text], [$top: integer], [custom_attributes: json])` — Get All Users
- `remove_group_member(group_id: text, user_id: text)` — Remove Group's Member
- `remove_group_owner(group_id: text, owner_id: text)` — Remove Group's Owner
- `update_user(based_on: select, [displayName: text], [givenName: text], [surname: text], [jobTitle: text], [officeLocation: text], [custom_attributes: json])` — Update User Details


### `sap-rfc` v1.1.0 _(installed)_
_SAP NetWeaver_

SAP NetWeaver Remote Function Call (RFC) is the standard SAP interface for communication between SAP systems. SAP NetWeaver connector performs action like list out session, end user session and, send popup message.

**10 operation(s)** (+1 hidden):

_investigation_
- `assign_user_role(username: text, AGR_NAME: text, [FROM_DAT: datetime], [TO_DAT: datetime], [AGR_TEXT: text])` — Assign User Role
- `end_session(TENANT: text, [USER_NAME: text], [LOGON_ID: text], [LOGON_HDL: text], [CLIENT_IP_ADDR: text])` — End User Session
- `get_session_list(TENANT: text, [USER_NAME: text], [LOGON_ID: text], [LOGON_HDL: text], [CLIENT_IP_ADDR: text])` — Get Session List
- `lock_user(username: text)` — Lock User
- `remove_all_user_profiles(username: text)` — Remove User Profiles
- `remove_all_user_roles(username: text)` — Remove User Roles
- `run_rfc_functions(function_name: text)` — Run RFC Function
- `send_popup(client: text, username: text, message: text)` — Send Popup
- `unlock_user(username: text)` — Unlock User


### `twilio` v2.0.0 _(installed)_
_Twilio_

Twilio provides its users with a platform and a robust API capable of sending messages using the carrier network all over the world, while also exposing a globally available cloud API that developers can interact with to build intelligent and complex communications systems. This connector facilitates operations to Send Message and Make Outbound Call.

**2 operation(s)**:

_miscellaneous_
- `make_outbound_call(from: text, to: text, lang: select, message: textarea)` — Make Outbound Call
- `send_sms(from: text, to: text, message: textarea)` — Send Message


---

## Compliance and Reporting

### `word-templated-report` v1.0.1 _(installed)_
_FortiSOAR MS Word Report Templating_

This connector allows for Microsoft Word documents containing Jinja syntax to be used to generate reports in either .docx or .pdf formats. The 'docxtpl' Python library  is used to do this. For more information on how to format your templates, see the library's official documentation: https://docxtpl.readthedocs.io/en/latest/

**1 operation(s)**:

_investigation_
- `generate_report(templateIRI: text, [context: object], [context_images: object], reportName: text, outputFormat: select)` — Generate Report


---

## Compute Platform

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

_investigation_
- `create_instance(subs_id: select, resource_group_name: select, vm_name: text, location: select, vm_size: select, nic_name: select, username: text, password: password, os_image_type: select)` — Create an Instance
- `create_snapshot(subs_id: select, resource_group_name: select, snapshotName: text, location: select, createOption: select, [diskSizeGB: integer], [logicalSectorSize: integer], [sourceUniqueId: text], [EdgeZone: text], [diskAccessId: text], [incremental: checkbox], [tags: json], [type: select], [networkAccessPolicy: select], [osType: select], [dataAccessAuthMode: select], [hyperVGeneration: select], [sku: select], [tier: text], [custom_attributes: json])` — Create Snapshot
- `delete_instance(subs_id: select, resource_group_name: select, vm_name: select)` — Delete an Instance
- `delete_snapshot(subs_id: select, resource_group_name: select, snapshot_name: text)` — Delete Snapshot
- `get_instance_details(subs_id: select, resource_group_name: select, vm_name: select)` — Get Instance Details
- `get_nic_details(subs_id: select, resource_group_name: select, nic_name: select)` — Get NIC Details
- `get_nsg_details(subs_id: select, resource_group_name: select, nsg_name: select)` — Get NSG Details
- `get_snapshot_details(subs_id: select, resource_group_name: select, snapshotName: text)` — Get Snapshot Details
- `list_of_instances(subs_id: select, [resource_group_name: select])` — List Instances
- `list_snapshot(subs_id: select, [resource_group_name: select])` — List Snapshot
- `restart_instance(subs_id: select, resource_group_name: select, vm_name: select)` — Restart an Instance
- `start_instance(subs_id: select, resource_group_name: select, vm_name: select)` — Start an Instance
- `stop_instance(subs_id: select, resource_group_name: select, vm_name: select)` — Stop an Instance
- `update_snapshot(subs_id: select, resource_group_name: select, snapshotName: text, [dataAccessAuthMode: select], [diskAccessId: text], [diskSizeGB: integer], [type: select], [networkAccessPolicy: select], [osType: select], [tags: json], [sku: select], [tier: text], [custom_attributes: json])` — Update Snapshot


### `google-cloud-compute` v1.2.0 _(installed)_
_Google Cloud Compute_

Google Compute Engine's tooling and workflow supports to create advanced networks on the regional levels and load balancing capabilities in cloud computing. This connector facilitates automated operation related to GCE operations.

**9 operation(s)**:

_investigation_
- `describe_instance(zone: text, resource_id: text)` — Get Instance Details
- `disk_snapshot(zone: text, instance_name: text)` — Disk Snapshot
- `get_aggregated_list_instances([include_all_scopes: checkbox], [filter: text], [order_by: text], [page_token: text], [max_results: integer], [return_partial_success: checkbox])` — Aggregated List Instances
- `list_instances_within_zone(zone: text, [filter: text], [order_by: text], [page_token: text], [max_results: integer])` — List Instances within Zone
- `set_label(instance_name: text, zone: text, new_key: text, new_value: text)` — Set Instance Label

_miscellaneous_
- `delete_instance(zone: text, resource_id: text)` — Delete Instance
- `reset_instance(zone: text, resource_id: text)` — Reset Instance
- `start_instance(zone: text, resource_id: text)` — Start Instance
- `stop_instance(zone: text, resource_id: text)` — Stop Instance


---

## Contact Dictionary

### `pipl` v1.0.0 _(installed)_

PIPL provides a way to get work & social contact information of people.

**1 operation(s)**:

_investigation_
- `get_user_details([username: text], [user_id: text], [first_name: text], [middle_name: text], [last_name: text], [raw_name: text], [email: text], [raw_phone: text], [country: text], [state: text], [city: text], [raw_address: text])` — Get User Details


---

## Container Services

### `kubernetes` v1.0.0 _(installed)_
_Kubernetes_

Kubernetes, also known as K8s, is an open-source system for automating deployment, scaling, and management of containerized applications.

**13 operation(s)**:

_investigation_
- `apply_yml_file(file_name: text)` — Apply YAML File
- `delete_collection_namespace_config_map(namespace: text)` — Delete Collection Namespace ConfigMap
- `delete_collection_namespace_pod(namespace: text)` — Delete Collection Namespace Pods
- `delete_collection_namespace_secret(namespace: text)` — Delete Collection Namespace Secret
- `delete_namespace_config_map(configmap_name: text, namespace: text)` — Delete Namespace ConfigMaps
- `delete_namespace_pod(pod_name: text, namespace: text)` — Delete Namespace Pod
- `delete_namespace_secret(secret_name: text, namespace: text)` — Delete Namespace Secret
- `get_pod_logs(pod_name: text, namespace: text)` — Get Pod logs
- `list_config_map_for_all_namespaces()` — Get ConfigMap For All Namespaces
- `list_event_for_all_namespaces()` — Get Events For All Namespaces
- `list_namespace_pod(namespace: text)` — Get Namespace Pods List
- `list_pod_for_all_namespaces()` — Get Pod For All Namespaces
- `list_secret_for_all_namespaces()` — List Secret For All Namespaces


---

## Content Management

### `microsoft-sharepoint` v1.0.0 _(installed)_
_Microsoft Sharepoint_

Microsoft SharePoint is a collaboration, document management platform and content management system. This connector facilitates automated operations related to lists, files.

**6 operation(s)**:

_investigation_
- `delete_file(file_name: text, folder_url: text)` — Delete File
- `edit_file(file_name: text, folder_url: text, file_content: textarea, comment: text)` — Update File Content
- `get_folder_file_list([folder_url: text])` — Get Folders or File Lists
- `get_list([list_title: text])` — Get Lists
- `read_file_content(file_name: text, folder_url: text)` — Download File
- `upload_file(attachment_id: text, folder_url: text)` — Upload File


---

## Content Security Management

### `cisco-sma` v1.1.1 _(installed)_
_Cisco SMA_

The Cisco Content Security Management Appliance (SMA) centralizes management and reporting functions across multiple Cisco email and web security appliances. It simplifies administration and planning, improves compliance monitoring, helps to enable consistent enforcement of policy, and enhances threat protection.

**8 operation(s)**:

_investigation_
- `delete_message(message_ids: text, quarantineType: text, quarantineName: text)` — Delete Message
- `download_attachment(mid: text, quarantineType: text, attachmentId: text, [save_as_attachment: checkbox])` — Download Attachment
- `fetch_from_other_quarantine(startDate: datetime, endDate: datetime, quarantines: text, quarantineType: text, offset: integer, limit: integer, [subjectFilterBy: select], [originatingEsaIp: text], [attachmentDetails: multiselect], [sorting: multiselect], [envelopeRecipientFilterBy: select], [envelopeSenderFilterBy: select])` — Fetch Emails From Other Quarantine
- `fetch_from_spam_quarantine(startDate: datetime, endDate: datetime, [sorting: multiselect], [lazy_loading: checkbox], [envelopeRecipientFilterOperator: select])` — Fetch Emails From SPAM Quarantine
- `get_message_details(startDate: datetime, endDate: datetime, mid: text, icid: text, serialNumber: text)` — Get Tracking Message Details
- `get_quarantine_message_details(mid: text, quarantineType: text)` — Get Quarantine Message Details
- `release_emails_from_quarantine(message_ids: text, quarantineType: text, quarantineName: text)` — Release Emails From Quarantine
- `track_emails(startDate: datetime, endDate: datetime, searchOption: text, [ciscoHost: text], [ciscoMid: text], [senderIp: text], [fileSha256: text], [subjectfilterOperator: select], [envelopeSenderfilterOperator: select], [envelopeRecipientfilterOperator: select], [messageIdHeader: text], [deliveryStatus: select], [message_delivered: checkbox], [messageDirection: select], [containedMaliciousUrls: checkbox], [attachmentNameOperator: select], [offset: integer], [limit: integer])` — Track Emails


---

## Cyber Threat Intelligence

### `fireeye-isight` v1.0.0 _(installed)_
_FireEye iSIGHT_

iSIGHT API extends FireEye cyber threat intelligence. This connector facilitates operations like Basic Search, Get Indicators and Get IOCs etc.

**7 operation(s)**:

_investigation_
- `basic_search(key: select, value: text, [startDate: datetime], [endDate: datetime], [limit: integer], [offset: integer])` — Basic Search
- `get_indicators(key: select, value: text, [limit: integer], [offset: integer])` — Get Indicators Data
- `get_iocs(startDate: datetime, endDate: datetime)` — Get IOCs
- `get_report(reportID: text, [detail: text], [iocsOnly : checkbox])` — Get Report
- `get_threat([threatType: text])` — Get Threat
- `list_report([startDate: datetime], [endDate: datetime], [reportType: select], [limit: integer], [offset: integer])` — List Reports
- `list_vulnerability([startDate: datetime], [endDate: datetime])` — List Vulnerabilities


---

## DDoS Prevention and Protection

### `arbor-ddos` v1.0.0 _(installed)_
_Arbor DDoS_

Arbor DDoS connector perform automated operations, such as retrieving all DDoS alerts or alerts based on the search criteria you have specified from Arbor DDoS, or retrieving network summary reports using various filters you have specified from Arbor DDoS.

**3 operation(s)**:

_investigation_
- `get_alerts([filter: text], [limit: integer])` — Get Alerts
- `get_network_summery_report(customer_name: text, start_time: text, end_time: text, unit: text, [timeout: integer], [limit: integer])` — Get Network Summary Report
- `get_top_talker_report(id: text, report_type: select, start_time: datetime, end_time: datetime, [unit: text], [limit: integer])` — Get TopTalker Report


---

## Data Enrichment & Threat Intelligence

### `digital-shadows` v1.0.0 _(installed)_
_Digital Shadows_

Digital Shadows monitors and manages an organization's digital risk across the widest range of data sources within the open, deep, and dark web.

**12 operation(s)**:

_investigation_
- `find_breach_records([domainNames: text], [published: text], [reviewStatuses: select], [property: select], [direction: select], [size: text], [offset: text])` — Find Breach Records
- `find_incidents([dateRangeField: select], [domainSelection: select], [direction: select], [property: select], [size: text], [offset: text])` — Find Incidents
- `find_intelligence_incidents([dateRangeField: select], [domainSelection: select], [direction: select], [property: select], [size: text], [offset: text])` — Find Intelligence Incidents
- `find_intelligence_threats([dateRangeField: select], [relevantTo: select], [size: text], [offset: text])` — Find Intelligence Threats
- `get_breach(id: text)` — Get Data Breach
- `get_breach_records(id: text, [domainNames: text], [property: select], [published: text], [reviewStatuses: select], [direction: select], [size: text], [offset: text])` — Get Data Breach Records
- `get_incident(id: text, [fulltext: checkbox])` — Get Incident
- `get_intelligence_incident(id: text)` — Get Intelligence Incident
- `get_intelligence_incident_iocs(id: text, [size: text], [offset: text])` — Get Intelligence Incident IOCs
- `get_intelligence_threat(id: integer)` — Get Intelligence Threat
- `get_intelligence_threat_iocs(id: text, [types: select], [direction: select], [property: select], [size: text], [offset: text])` — Get Intelligence Threat IOCs
- `search_records(query: text, [types: select], [size: text], [offset: text])` — Search Records


### `microsoft-management-activity-api` v1.0.1 _(installed, ingestion)_
_Microsoft Management Activity API_

Office 365 Management Activity API is used to retrieve information about user, admin, system, and policy actions and events from Office 365 and Azure AD activity logs.

**4 operation(s)**:

_investigation_
- `list_content([content_type: select], [start_time: datetime], [end_time: datetime], [record_types_filter: multiselect], [workloads_filter: multiselect], [operations_filter: text])` — MS Management Activity List Content
- `list_subscription()` — MS Management Activity List Subscription
- `start_subscription(content_type: select)` — MS Management Activity Start Subscription
- `stop_subscription(content_type: select)` — MS Management Activity Stop Subscription


---

## Data Enrichment and Threat Intelligence

### `atlassian-iam` v1.0.0 _(installed)_
_Atlassian IAM_

Integrate with Atlassian's services to execute CRUD operations for employee lifecycle processes.

**4 operation(s)**:

_investigation_
- `create_user([userName: text], [emails: text], [title: text], [department: text], [organization: text], [active: checkbox], [custom_filter: json])` — Create User
- `deactivate_user(userId: text)` — Deactivate User
- `get_users()` — Get Users
- `update_user(userId: text, [userName: text], [emails: text], [title: text], [department: text], [organization: text], [custom_filter: json])` — Update User


### `blockade-io` v1.0.0 _(installed)_
_Blockade.io_

Blockade brings antivirus-like capabilities to users who run the Chrome browser. This connector facilitates automated actions like Get Indicators and Add Indicators

**2 operation(s)**:

_investigation_
- `add_indicators(indicators: text, api_key: password, email: text, [dbroute: text])` — Add MD5 Hashed Indicators
- `get_indicators([dbroute: text])` — Get Indicators


---

## Data Security

### `imperva-counterbreach` v1.0.0 _(installed)_
_Imperva CounterBreach_

Imperva CounterBreach protects enterprise data stored in enterprise databases, file shares and SaaS applications from the theft and loss caused by compromised, careless or malicious users. Imperva CounterBreach connector performs action like get security events, get allow list rule, update incident/anomaly etc.

**6 operation(s)**:

_investigation_
- `get_allow_list_rule([limit: integer], [offset: integer])` — Get Allow List Rule
- `get_security_events([search: text], [status: select], [event_category: select], [event_class: select], [logged_before: datetime], [limit: integer], [offset: integer])` — Get Security Events
- `get_specific_allow_list_rule(ignore_rule_id: text)` — Get Specific Allow List Rule
- `update_anomaly(event_id: text, [comment: text], [star: checkbox], [status: select])` — Update Anomaly
- `update_incident(event_id: text, [comment: text], [star: checkbox], [status: select])` — Update Incident
- `update_rule(ignore_rule_id: text, ruleName: text, [ruleComment: text], [incidentType: multiselect], [expirationDate: datetime], [dbName: text], [tableName: text], [destHostname: text], [destIp: text], [dbUser: text], [srcApp: text], [srcHostname: text], [srcIp: text], [srcUser: text], [suspiciousCommand: text], [fileExtension: text], [folder: text], [closeIncidents: checkbox], [comment: text], [overrideComment: checkbox])` — Update Allow List Rule


---

## Database

### `aws-dynamodb` v1.0.0 _(installed)_
_AWS DynamoDB_

AWS DynamoDB is a fully managed NoSQL database service that provides fast and predictable performance with seamless scalability. This connector facilitates the automate operations related to manage database table, data and backup.

**16 operation(s)**:

_utilities_
- `create_backup([assume_role: checkbox], TableName: text, BackupName: text)` — Create Table Backup
- `create_global_table([assume_role: checkbox], globalTableName: text, regionName: text)` — Create Global Table
- `create_or_update_table_item([assume_role: checkbox], TableName: text, partitionKeyName: text, partitionKeyDataType: select, partitionKeyValue: text, [sortKey: checkbox], [additionalAttributes: object])` — Create or Update Table Item
- `create_table([assume_role: checkbox], TableName: text, partitionKeyName: text, partitionKeyDataType: select, [sortKey: checkbox], billingMode: select)` — Create Table
- `delete_item([assume_role: checkbox], TableName: text, partitionKeyName: text, partitionKeyDataType: select, partitionKeyValue: text, [sortKey: checkbox])` — Delete Table Item
- `delete_table([assume_role: checkbox], TableName: text)` — Delete Table
- `delete_table_backup([assume_role: checkbox], BackupArn: text)` — Delete Table Backup
- `get_global_table_details([assume_role: checkbox], globalTableName: text)` — Get Global Table Details
- `get_global_table_list([assume_role: checkbox])` — Get Global Table List
- `get_table_backup_details([assume_role: checkbox], BackupArn: text)` — Get Table Backup Details
- `get_table_backup_list([assume_role: checkbox])` — Get Table Backup List
- `get_table_details([assume_role: checkbox], TableName: text)` — Get Table Details
- `get_table_list([assume_role: checkbox])` — Get Table List
- `list_table_items([assume_role: checkbox], TableName: text, [Select: select], [Limit: integer])` — Get Table Items List
- `search_item([assume_role: checkbox], TableName: text, partitionKeyName: text, partitionKeyDataType: select, partitionKeyValue: text, [sortKey: checkbox])` — Search Table Item
- `update_table([assume_role: checkbox], TableName: text, updateOperation: select)` — Update Table


### `azure-cosmos-db` v1.0.0 _(installed)_
_Azure Cosmos DB_

Azure Cosmos DB is a globally distributed, multi-model database service offered by Microsoft. It is designed to provide high availability, scalability, and low-latency access to data for modern applications.

**6 operation(s)**:

_investigation_
- `delete_document(doc_id: text, partition_key: text, collection_name: text, [database_name: text])` — Delete Document
- `get_collections([database_name: text])` — Get Containers
- `get_database_properties([database_name: text])` — Get Database Properties
- `insert_document(document_details: json, collection_name: text, [database_name: text])` — Insert Document
- `query_document(query: text, collection_name: text, [database_name: text])` — Query Document
- `update_document(doc_id: text, document_details: json, collection_name: text, [database_name: text])` — Update Document


### `cloudera-edh` v1.0.0 _(installed)_
_Cloudera EDH_

Cloudera provides a scalable, flexible, integrated platform that makes it easy to manage rapidly increasing volumes and varieties of data in your enterprise.This connector allows you do operations related to database.

**4 operation(s)**:

_investigation_
- `list_columns(table_name: text)` — Get Columns
- `list_tables()` — Get Table List
- `run_query(query: text)` — Run Query
- `select_query(query: text)` — Execute Select Query


### `databricks` v1.0.1 _(installed)_
_Databricks_

Query an Azure Databricks Cluster table in a catalog's schema (database). Uses Databricks SQL Connector for Python.

**1 operation(s)**:

_investigation_
- `run_query(query_string: text)` — Run Query


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


### `influxdb` v1.0.0 _(installed)_
_InfluxDB_

Runs database queries against an InfluxDB instance

**1 operation(s)**:

_investigation_
- `run_query([dbName: text], query: text)` — Run Query


### `microsoft-sql-server` v2.0.1 _(installed)_
_Microsoft SQL Server_

Microsoft SQL Server Connector which enables to run queries on Microsoft SQL Server database

**4 operation(s)**:

_investigation_
- `list_columns(table_name: text)` — Get Columns
- `list_tables()` — Get Table List
- `run_query(query: text)` — Run Query
- `select_query(sql_query: text)` — Select Query


### `mongodb` v2.0.0 _(installed)_
_MongoDB_

MongoDB is an open-source document database that provides high performance, high availability, and automatic scaling. Use the MongoDB connector to perform automated operations, such as inserting or updating documents, retrieving a list of all available collections from the MongoDB database, and querying the MongoDB database.

**5 operation(s)**:

_investigation_
- `add_data(collection_name: text, json_data: json, [database: text])` — Insert Documents
- `get_data(collection_name: text, [database: text], [doc_filter: json])` — Query Documents
- `list_tables([database: text])` — Get Collections
- `update_data(collection_name: text, filter: json, update: json, [database: text])` — Update Documents

_remediation_
- `delete_data(collection_name: text, doc_filter: json, [database: text])` — Delete Documents


### `mysql` v1.0.1 _(installed)_
_MySQL_

The MySQL database server manages the databases and tables, controls user access, and processes the SQL queries. perform automated operations, such as executing a query on MySQL database and listing table and column names present in the database.

**3 operation(s)**:

_investigation_
- `list_columns(table_name: text)` — List Columns
- `list_tables()` — List Tables
- `run_query(query_string: text)` — Run Query


### `odbc` v1.0.0 _(installed)_
_ODBC_

ODBC (Open Database Connectivity) allows applications to access data from different database systems (e.g., MySQL, SQL Server, Oracle). It enables interoperability between applications and databases through an ODBC driver.

**1 operation(s)**:

_investigation_
- `execute_query(query: text)` — Execute Query


### `oracle-db` v1.0.1 _(installed)_
_Oracle Database_

Use Oracle Database connector to connect to a database and then query the database and retrieve data. supports Oracle v12c onward.

**1 operation(s)**:

- `db_query(query_string: text)` — Query DB


### `postgresql` v1.0.2 _(installed)_
_PostgreSQL_

PostgreSQL Connector provide automated operation to run query on PostgreSQL server

**1 operation(s)**:

_investigation_
- `run_query([dbName: text], query: text)` — Run Query


### `sqlite` v1.0.0 _(installed)_
_SQLite_

SQLite Connector allows querying local SQLite database.

**3 operation(s)**:

_investigation_
- `list_columns(table_name: text)` — Get Columns
- `list_tables()` — Get Table List
- `run_query(query: text, [commit_to_db: checkbox])` — Run Query


### `teradata-db` v1.0.0 _(installed)_
_Teradata DB_

Teradata DB is one of the popular Relational Database Management System. It is mainly suitable for building large scale data warehousing applications. Teradata Query Service is a REST API for Vantage that you can use to run standard SQL statements without managing client-side drivers.

**14 operation(s)**:

_investigation_
- `get_list_of_all_databases(system_name: text)` — Get List Of All Databases
- `get_list_of_all_functions(system_name: text, database_name: text)` — Get List Of All Functions
- `get_list_of_all_macros(system_name: text, database_name: text)` — Get List Of All Macros
- `get_list_of_all_procedures(system_name: text, database_name: text)` — Get List Of All Procedures
- `get_list_of_all_queries(system_name: text, [session: text], [state: select], [clientId: text])` — Get List Of All Queries
- `get_list_of_all_systems()` — Get List Of All Systems
- `get_list_of_all_tables(system_name: text, database_name: text)` — Get List Of All Tables
- `get_list_of_all_views(system_name: text, database_name: text)` — Get List Of All Views
- `get_query_by_id(system_name: text, id: integer)` — Get Query By Id
- `get_query_results_by_id(system_name: text, id: integer, [row_offset: integer], [row_limit: integer])` — Get Query Results By ID
- `get_specific_database_by_name(system_name: text, database_name: text)` — Get Specific Database By Name
- `get_specific_table_by_name(system_name: text, database_name: text, table_name: text)` — Get Specific Table By Name
- `get_specific_view_by_name(system_name: text, database_name: text, view_name: text)` — Get Specific View By Name
- `submit_a_query(system_name: text, query_request: textarea)` — Submit A Query


---

## DevOps

### `aws-waf` v1.0.0 _(installed)_
_AWS WAF_

AWS WAF is a web application firewall that lets you monitor and manage web requests that are forwarded to protected AWS resources.

**5 operation(s)**:

_investigation_
- `create_ip_set(Name: text, IPAddressVersion: select, [Addresses: text], [Description: text], [Tags: json])` — Create IP Set
- `delete_ip_set(Name: text, Id: text, LockToken: text)` — Delete IP Set
- `get_ip_set(Name: text, Id: text)` — Get IP Set
- `list_ip_set([Limit: integer], [NextMarker: text])` — List IP Set
- `update_ip_set(Name: text, Id: text, LockToken: text, [AddressesToAdd: text], [AddressesToRemove: text], [Description: text])` — Update IP Set


### `aws-waf-classic` v1.0.0 _(installed)_
_AWS WAF Classic_

AWS WAF Classic is a web application firewall that lets you monitor and manage web requests that are forwarded to protected AWS resources.

**6 operation(s)**:

_investigation_
- `create_ip_set(Name: text, ChangeToken: text)` — Create IP Set
- `delete_ip_set(ChangeToken: text, IPSetId: text)` — Delete IP Set
- `get_change_token()` — Get Change Token
- `get_ip_set(IPSetId: text)` — Get IP Set
- `list_ip_set([Limit: integer], [NextMarker: text])` — List IP Sets
- `update_ip_set(IPSetId: text, ChangeToken: text, Updates: json)` — Update IP Set


### `awss3` v3.0.2 _(installed)_
_AWS S3_

To provide automation for AWS S3 operations, like creation and modification of S3 buckets and related contents.

**14 operation(s)**:

_investigation_
- `get_bucket_policy(bucketName: text)` — Get Bucket Policy
- `list_objects(bucketName: text, [startKey: text], [pageSize: integer])` — List Objects
- `new_bucket(Bucket: text, [ACL: select])` — Create New Bucket

_miscellaneous_
- `download_file(download_from: select)` — Download File
- `get_object_details(bucketName: text, objectKey: text)` — Get Object
- `list_buckets()` — List Buckets
- `modify_bucket(bucketName: text, [tags: text], [encryption: select], [grants: text])` — Modify Bucket
- `modify_object(bucketName: text, objectKey: text, [tags: text], [grants: text])` — Modify Object
- `put_bucket_policy(bucketName: text, policy_args: json)` — Create Bucket Policy
- `replace_bucket_policy(bucketName: text, policy_args: json)` — Replace Bucket Policy
- `upload_file(bucketName: text, file_id: text, objectKey: text)` — Upload File into Bucket

_remediation_
- `delete_bucket(bucketName: text)` — Delete Bucket
- `delete_object(bucketName: text, key: text)` — Delete Bucket Object
- `delete_tag(object_or_bucket: select)` — Delete Tag


---

## DevOps and Digital Operations

### `ansible-tower` v2.0.0 _(installed)_
_Ansible Tower_

Ansible Tower connector perform automated operations, such as retrieving job status, launching jobs, retrieving job template, list job, list users etc from resources within Tower.

**16 operation(s)**:

_investigation_
- `cancel_job(job_id: text)` — Cancel Job
- `create_host_for_inventory(inventory_id: text, name: text, [description: text], [enabled: checkbox], [instance_id: text], [variables: json], [additional_fields: json])` — Create Host for Inventory
- `delete_host(host_id: text)` — Delete Host
- `get_credentials([search: text], [order_by: text], [page: text], [page_size: text])` — Get Credentials
- `get_hosts_for_inventory(inventory_id: text, [search: text], [order_by: text], [page: text], [page_size: text])` — Get Hosts for Inventory
- `get_inventories([search: text], [order_by: text], [page: text], [page_size: text])` — Get Inventories
- `get_job_status(job_id: text, [search: text])` — Get Job Status
- `get_job_templates()` — Get Job Templates
- `get_jobs([search: text], [order_by: text], [page: text], [page_size: text])` — Get Jobs
- `get_specific_job_events(job_id: text)` — Get Specific Job Event
- `get_specific_job_template_details(job_id: text, [search: text])` — Get Specific Job Template Details
- `get_templates_for_inventory(inventory_id: text, [search: text], [order_by: text], [page: text], [page_size: text])` — Get Templates for Inventory
- `launch_job_template(job_template_id: text, [extra_vars: json])` — Launch Job Template
- `list_job_templates([search: text], [order_by: text], [page: text], [page_size: text])` — List Job Templates
- `list_users([search: text], [order_by: text], [page: text], [page_size: text])` — List Users
- `relaunch_job(job_id: text, [additional_fields: json])` — Relaunch a Job


### `argo-cd` v1.0.1 _(installed)_
_Argo CD_

Argo CD (short for Argo Continuous Delivery) is a declarative, GitOps continuous delivery tool for Kubernetes. It allows you to manage and deploy applications to Kubernetes clusters using Git repositories as the source of truth for both the desired application state and its configuration.

**7 operation(s)**:

_investigation_
- `create_application(name: text, source: json, destination: json, [metadata: json], [spec: json], [operation: json], [additional_properties: json])` — Create Application
- `delete_application(name: text)` — Delete Application
- `get_application_by_name(name: text)` — Get Application by Name
- `get_applications([name: text], [projects: text], [additional_properties: json])` — Get Applications
- `get_clusters([server: text], [name: text])` — Get Clusters
- `send_custom_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Call
- `update_application(name: text, source: json, destination: json, [metadata: json], [spec: json], [operation: json], [additional_properties: json])` — Update Application


### `circleci` v1.0.0 _(installed)_
_CircleCI_

CircleCI is the continuous integration & delivery platform that helps the development teams to release code rapidly and automate the build, test, and deploy. CircleCI can be configured to run very complex pipelines efficiently with caching, docker layer caching, resource classes and many more. After repositories on GitHub or Bitbucket are authorized and added as a project to circleci.com, every code triggers CircleCI runs jobs. CircleCI also sends an email notification of success or failure after the tests complete.

**5 operation(s)**:

_investigation_
- `get_artifacts_list(job-number: text, [vc_type: select], [organization: text], [project: text])` — Get Artifacts List
- `get_workflow_jobs_list(id: text)` — Get Workflow Jobs List
- `get_workflow_last_runs(workflow-name: text, [vc_type: select], [organization: text], [project: text], [page-token: text], branch_name: select, [start-date: datetime], [end-date: datetime])` — Get Workflow Last Runs
- `get_workflows_list([vc_type: select], [organization: text], [project: text], [page-token: text], branch_name: select, [reporting-window: select])` — Get Workflows List
- `trigger_workflow([vc_type: select], [organization: text], [project: text], [parameters: json])` — Trigger Workflow


### `jenkins` v1.0.0 _(installed, ingestion)_
_Jenkins_

Jenkins is an open-source automation server widely used to implement Continuous Integration (CI) and Continuous Delivery (CD) pipelines. It helps automate the parts of software development related to building, testing, and deploying, facilitating faster and more reliable software delivery.

**5 operation(s)**:

_investigation_
- `generic_rest_api_call(endpoint: text, method: select, [query_params: json], [payload: json])` — Execute an API Request
- `get_job_status(job_path: text, build_number: text)` — Get Job Status
- `get_list_jobs([job_path: text])` — Get List Jobs
- `resume_jenkins_job_with_input(job_path: text, build_number: text, input_id: text, input_parameters: json, job_status: select)` — Resume Jenkins Job with Input
- `trigger_job(job_path: text, [build_parameters: json])` — Trigger Job


### `kiuwan` v1.2.0 _(installed)_
_Kiuwan_

Kiuwan is a software as a service (SaaS) static application security testing multi-technology software for software analysis, code quality, software composition and security measurement/management. This connector facilitates automated operations related to Action Plan, Analyses, and Defect.

**25 operation(s)**:

_investigation_
- `create_mutes_for_rule_or_file(app_name: text, [comment: text], [file_name: text], [file_pattern: text], [rule: text], [reason: select])` — Create Mutes for Rule or File
- `create_suppression_rule(defect_id: text, [comment: text], [muteBy: select], [reason: select])` — Create Suppression Rule
- `delete_analysis(analysis_code: text)` — Delete Analysis
- `get_analysis_codes_list(app_name: text, [filterPurgedAnalyses: checkbox], [success: checkbox], [count: integer])` — Get Analysis Codes List
- `get_analysis_defects_list(code: text, [characteristics: text], [fileContains: text], [languages: text], [muted: checkbox], [priorities: text], [count: integer], [page: integer], [orderBy: select], [sort_by: checkbox])` — Get Analysis Defects List
- `get_analysis_list([app_name: text], [audit_status: select], [deliveries: checkbox], [start_date: datetime], [end_date: datetime], [status: select], [count: integer], [page: integer])` — Get Analysis List
- `get_application_analysis(code: text)` — Get Application Analysis
- `get_application_defects_list(app_name: text, [characteristics: text], [fileContains: text], [languages: text], [priorities: text], [count: integer], [page: integer], [orderBy: select], [sort_by: checkbox])` — Get Application Defects List
- `get_application_details(app_name: text)` — Get Application Details
- `get_application_list([app_name: text], [activityInfo: checkbox], [initDateAnalysis: datetime], [endDateAnalysis: datetime], [exactApplicationName: checkbox], [count: integer], [page: integer], [orderBy: select], [sort_by: checkbox])` — Get Application List
- `get_available_action_plans(app_name: text)` — Get Available Action Plans
- `get_comparison_defects(code: text, prev_code: text)` — Get Comparison Defects
- `get_defect_notes(defect_id: integer)` — Get Defect Notes
- `get_defects_list_for_action_plan(app_name: text, action_name: text, [creation_date: datetime])` — Get Defects List for Action Plan
- `get_file_defects(app_name: text, analysisCode: text, file_name: text, ruleCode: text)` — Get File Defects
- `get_files_defects_details(code: text)` — Get Files Defects Details
- `get_last_analysis(app_name: text)` — Get Latest Analysis
- `get_latest_analysis_files_list(app_name: text)` — Get Latest Analysis Files List
- `get_new_removed_defects_list(code: text, prev_code: text, defectstype: select)` — Get New/Removed Defects List
- `get_pending_defects_for_action_plan(app_name: text, action_name: text, [creation_date: datetime], [analysisLabel: text], [characteristics: text], [fileContains: text], [languages: text], [priorities: text], [limit: integer], [orderBy: select], [sort_by: checkbox])` — Get Pending Defects for Action Plan
- `get_progress_summary_for_action_plan(app_name: text, action_name: text, [creation_date: datetime])` — Get Progress Summary for Action Plan
- `get_removed_defects_for_action_plan(app_name: text, action_name: text, [creation_date: datetime], [analysisLabel: text])` — Get Removed Defects for Action Plan
- `get_violated_rule_files(app_name: text, analysisCode: text, ruleCode: text)` — Get Violated Rule Files
- `get_violated_rules(app_name: text, [analysisCode: text], [onlyCodeSecurity: checkbox], [characteristics: multiselect], [languages: text], [priority: select], [tag: text], [vuln_type: select])` — Get Violated Rules
- `update_defect_status(defect_id: integer, status: select, [note: text])` — Update Defect Status


---

## Device Security

### `duo` v1.0.1 _(installed)_
_Duo_

Duo provides secure, rapid transition to the cloud use Duo Beyond to protect their on-premises and hosted applications, while securing their mobile workforce and their chosen devices.

**4 operation(s)** (+1 hidden):

_investigation_
- `authenticate_user(device: text, username: text, factor: select, [ipaddr: text], [async_txn: checkbox])` — Authenticate User
- `get_auth_status(txid: text)` — Get Auth Status
- `get_preauth_details(username: text)` — Get Preauth Details


---

## Digital Forensics & Incident Response

### `oletools` v1.0.0 _(installed)_
_OLETools_

OLEtools is a suite of Python tools used for analyzing Microsoft OLE2 files (also known as Structured Storage, Compound File Binary Format, or Microsoft Office documents such as .doc, .xls, .ppt, and .msg). It is particularly popular in digital forensics, malware analysis, and incident response for examining potentially malicious Office documents.

**3 operation(s)**:

_investigation_
- `oleid(file_iri: text, [file_password: text])` — Oleid
- `oleobj(file_iri: text, [file_password: text])` — Oleobj
- `olevba(file_iri: text, [file_password: text], [show_decoded_strings: checkbox], [deobfuscate: checkbox])` — Olevba


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

## Document Reader

### `pdf-reader` v1.0.2 _(installed)_
_PDF Reader_

PDF Reader connector reads PDF documents and extract text.

**2 operation(s)**:

_investigation_
- `read_all_pages(type: select, [password: password])` — Read all Pages
- `read_page(type: select, page_num: integer, [password: password])` — Read a Page


---

## Domain Information Provider

### `domaintools` v1.0.1 _(installed)_
_DomainTools_

DomainTools provide details around the Domain and IP. DomainTools connector facilitates automated operations to get details of domain names and IP addresses.

**9 operation(s)**:

_investigation_
- `get_domain_reputation_info(domain_name: text)` — Get Domain Reputation
- `get_domain_search_info(query: text, [domain_status: select], [days_back: select])` — Get Recent Domains
- `get_hosting_history_info(domain_name: text)` — Get Hosting History Details
- `get_revers_domain_info(domain_name: text)` — Get Reverse Domain Details
- `get_revers_ip_info(ip_address: text)` — Get Reverse IP Details
- `get_reverse_email_info(email: text)` — Get Reverse Email Details
- `get_whois_domain_info(domain_name: text)` — Get Whois Domain Details
- `get_whois_history_info(domain_name: text)` — Get Whois History Details
- `get_whois_ip_info(ip_address: text)` — Get Whois IP Details


---

## Email Gateway

### `fireeye-etp` v1.0.0 _(installed)_
_FireEye ETP_

FireEye ETP helps you secure and control inbound and outbound email through an easy-to-use cloud-based solution. Perform actions like alerts and messages information using FireEye ETP.

**13 operation(s)**:

_investigation_
- `delete_bulk_quarantined_email(message_ids: text)` — Delete Bulk Emails From Quarantine
- `delete_quarantined_email(message_id: text)` — Delete Quarantined Email
- `get_alert(alert_id: text)` — Get Alert
- `get_alert_artifact(alert_id: text)` — Get Alert Artifact
- `get_alert_list([legacy_id: integer], [email_status: multiselect], [from_last_modified_on: datetime], [etp_message_id: text], [size: integer])` — List All Alerts
- `get_alert_malware_files(alert_id: text)` — Get Alert Malware Files
- `get_alert_pcap_files(alert_id: text)` — Get Alert PCAP Files
- `get_message(message_id: text)` — Get Message
- `get_quarantined_email(message_id: text)` — Get Quarantine Email
- `query_quarantined_email([reason: multiselect], [from: text], [domains: text], [recipients: text], [ip_address: text], [domain: text], [from_date: datetime], [to_date: datetime], [subject: text], [size: integer], [tag: multiselect])` — Query Quarantined Email
- `release_bulk_quarantined_email(message_ids: text, [is_not_spam: checkbox], [headers_only: checkbox])` — Release Bulk Emails From Quarantine
- `release_quarantined_email(message_id: text, [is_not_spam: checkbox], [headers_only: checkbox])` — Release Quarantined Email
- `search_messages([email: select], [email_recipients: select], [message_status: select], [subject: text], [from_accepted_date_time: datetime], [to_accepted_date_time: datetime], [rejection_reason: multiselect], [sender_ip: text], [last_modified_date_time: datetime], [domains: text], [has_attachments: checkbox], [max_message_size: integer])` — Search Messages


### `proofpoint-email-gateway` v2.0.0 _(installed)_
_Proofpoint Email Gateway_

Proofpoint Email Protection helps you secure and control inbound and outbound email through an easy-to-use cloud-based solution. Perform actions like organizational block list and search quarantine message information using Proofpoint Email Gateway.

**4 operation(s)**:

_investigation_
- `add_remove_organizational_block_list(clusterId: text, action: select, attribute: text, operator: text, value: text, [comment: text])` — Add or Remove Organizational Block List
- `get_organizational_block_list(clusterId: text)` — Get Organizational Block List
- `quarantine_message_actions(message: select, folder: text, localguid: text)` — Quarantine Message Actions (Deprecated)
- `search_quarantine_messages([message: multiselect], [queryid: text], [start_date: datetime], [end_date: datetime], [folder: text], [guid: text], [dlpviolation: select], [messagestatus: checkbox])` — Search Quarantine Messages (Deprecated)


### `symantec-messaging-gateway` v1.1.1 _(installed)_
_Symantec Messaging Gateway_

Symantec Messaging Gateway is an email security solution which provides inbound and outbound messaging security. Also it can perform containment and corrective actions like block Domain/Email/IP or unblock Domain/Email/IP

**8 operation(s)**:

_Containment_
- `blacklist_domain(domain: text)` — Block Domain
- `blacklist_email(email_id: email)` — Block Email
- `blacklist_ip(ip: text)` — Block IP

_Remediation_
- `unblacklist_domain(domain: text)` — Unblock Domain
- `unblacklist_email(email_id: email)` — Unblock Email
- `unblacklist_ip(ip: text)` — Unblock IP

_investigation_
- `advanced_audit_logs_search(mandatoryFilterId: select, mandatoryFilterValue: text, start_time: datetime, end_time: datetime, [remove_none_ascii: checkbox])` — Advanced Audit Log Search
- `audit_logs_search(mandatoryFilterId: select, mandatoryFilterValue: text, start_time: datetime, end_time: datetime, [entriesPerPage: integer], [pageNumber: integer])` — Quick Audit Log Search


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


### `cisco-esa` v3.1.0 _(installed)_
_Cisco ESA_

The Cisco Email Security Virtual Appliance significantly lowers the cost of deploying email security, especially in highly distributed networks. Spam and malware are part of a complex email security picture that includes inbound threats and outbound risks. The all-in-one Cisco ESA (Email Security Appliance) offers simple, fast deployment with few maintenance requirements, low latency, and low operating costs.

**29 operation(s)**:

_containment_
- `block_mail(mail_id: text, msg_name: text)` — Block Email
- `block_sender(listener: text, sender_type: select, [domain_value: text], [country_name: select])` — Block Sender

_investigation_
- `add_policy_entries(policy_name: text, policy_type: select, policy_applicable_for_senders: select, [receiver: checkbox])` — Add Entries In Policy
- `add_to_dictionary(dict_name: text, entries: text)` — Add Entries In Dictionary
- `delete_blocklist_entries(viewBy: select)` — Delete Blocklist Entries
- `delete_message(mids: text)` — Delete Message
- `delete_safelist_entries(viewBy: select)` — Delete Safelist Entries
- `download_attachment(mid: text, attachmentId: text)` — Download Attachment
- `get_all_dictionaries()` — Get All Dictionaries
- `get_all_policies(policy_type: select)` — Get All Policies
- `get_blocklist_entries([orderDir: select], [viewBy: select], [offset: integer], [limit: integer])` — Get Blocklist Entries
- `get_dictionary_entries(dict_name: text)` — Get Dictionary Entries
- `get_message_details(mid: text)` — Get Message Details
- `get_safelist_entries([orderDir: select], [viewBy: select], [offset: integer], [limit: integer])` — Get Safelist Entries
- `list_msg_filters()` — Get Message Filters List
- `message_tracking(search_type: select, search_value: text)` — Message Tracking
- `query_report(report_type: select, time_range: select, [from: datetime], [to: datetime], [search_value: text], [starts_with: checkbox], [limit: integer])` — Query-based Report
- `release_emails_from_quarantine(mids: text)` — Release Emails From Quarantine
- `remove_from_dictionary(dict_name: text, entries: text)` — Remove Entries From Dictionary
- `remove_policy_entries(policy_name: text, policy_type: select, row_number: text)` — Remove Entries From Policy
- `run_report(report_type: select, startDate: datetime, endDate: datetime, [sorting: checkbox], [lazy_loading: checkbox], [filtering: checkbox], [device_group_name: text], [device_name: text])` — Run Report
- `search_in_other_quarantine(startDate: datetime, endDate: datetime, quarantines: text, [quarantineType: text], [subjectFilterBy: select], [originatingEsaIp: text], [attachmentDetails: multiselect], [sorting: multiselect], [lazy_loading: checkbox], [envelopeRecipientFilterBy: select], [envelopeSenderFilterBy: select])` — Search Emails From Other Quarantine
- `search_in_spam_quarantine(startDate: datetime, endDate: datetime, [sorting: multiselect], [lazy_loading: checkbox], [envelopeRecipientFilterOperator: select], [filterOperator: select])` — Search Emails From SPAM Quarantine
- `simple_report(report_type: select, time_range: select, [from: datetime], [to: datetime])` — Simple Report
- `topN_report(report_type: select, time_range: select, [from: datetime], [to: datetime], limit: integer)` — Top-N Report
- `update_blocklist_entries(action: select)` — Update Blocklist Entries
- `update_safelist_entries(action: select)` — Update Safelist Entries

_remediation_
- `unblock_mail(mail_id: text)` — Unblock Email
- `unblock_sender(listener: text, sender_type: select, [domain_value: text], [country_name: select])` — Unblock Sender


### `cisco-esa-rest` v1.0.0 _(installed)_
_Cisco ESA(REST)_

The Cisco Email Security Virtual Appliance significantly lowers the cost of deploying email security, especially in highly distributed networks. Spam and malware are part of a complex email security picture that includes inbound threats and outbound risks. The all-in-one Cisco ESA (Email Security Appliance) offers simple, fast deployment with few maintenance requirements, low latency, and low operating costs.

**11 operation(s)**:

_investigation_
- `delete_quarantine_message(mids: text, [quarantineType: text])` — Delete Quarantine Messages
- `delete_safelist_or_blocklist_entries(safelist_or_blocklist: select, [quarantineType: text], [recipientList: text], [senderList: text], [viewBy: select])` — Delete Safelist or Blocklist Entries
- `edit_safelist_or_blocklist_entries(safelist_or_blocklist: select, action: select, [quarantineType: text], [viewBy: select], [recipientAddresses: text], [recipientList: text], [senderAddresses: text], [senderList: text])` — Edit Safelist or Blocklist Entries
- `get_message_amp_details(startDate: datetime, endDate: datetime, [serialNumber: text], [mid: text], [icid: text])` — Get Message AMP Details
- `get_message_dlp_details(startDate: datetime, endDate: datetime, [serialNumber: text], [mid: text], [icid: text])` — Get Message DLP Details
- `get_message_url_details(startDate: datetime, endDate: datetime, [serialNumber: text], [mid: text], [icid: text])` — Get Message URL Details
- `get_quarantine_message(mid: text, [quarantineType: text])` — Get Quarantine Message By ID
- `get_report(reportType: select, startDate: datetime, endDate: datetime, device_type: text, [query_type: text], [orderBy: text], [orderDir: select], [offset: integer], [limit: integer], [top: text], [filterValue: text], [filterBy: text], [filterOperator: select], [device_group_name: text], [device_name: text])` — Get Report
- `release_quarantine_message(mids: text, [action: text], [quarantineType: text])` — Release Quarantine Messages
- `search_quarantine_messages([startDate: datetime], [endDate: datetime], [quarantineType: text], [orderBy: select], [orderDir: select], [offset: integer], [limit: integer], [envelopeRecipientFilterOperator: select], [envelopeRecipientFilterValue: text], [filterOperator: select], [filterValue: text])` — Search Quarantine Messages
- `search_safelist_or_blocklist_entries(safelist_or_blocklist: select, [action: text], [quarantineType: text], [viewBy: select], [orderBy: select], [offset: integer], [limit: integer], [orderDir: select], [search: text])` — Search Safelist or Blocklist Entries


### `cofense-vision` v1.0.0 _(installed)_
_Cofense Vision_

Cofense Vision is a security solution designed to help organizations quickly detect, locate, and quarantine phishing emails across all employee inboxes.

**2 operation(s)**:

_investigation_
- `quarantine_email(recipientAddress: text, internetMessageId: text)` — Quarantine Email
- `search_email(emailSubject: text, senderEmailAddress: text)` — Search Email


### `fireeye-ex` v1.1.0 _(installed)_
_FireEye EX_

FireEye EX connector perform automated operations such as retrieving a list of all guest image profiles and applications details, get alerts details and retrieving data for artifacts etc.

**16 operation(s)**:

_containment_
- `add_custom_feed(feedName: text, feedType: select, feedAction: text, feedSource: text, content: textarea, [overwrite: checkbox])` — Add Custom Feed
- `add_yara_rule(file_iri: text, file_type: text, [target_type: select])` — Add YARA Rule

_investigation_
- `delete_quarantined_emails(queue_ids: text)` — Delete Quarantined Emails
- `download_quarantined_email(queue_id: text, [sensorName: text])` — Download Quarantined Email
- `get_alert_details(alert_id: text)` — Get Alert Details
- `get_alert_ioc(filter_by_id: select, response_format: select)` — Get Alert Related IOC
- `get_alerts([alert_id: text], [info_level: select], [url: text], [file_name: text], [file_type: text], [malware_name: text], [malware_type: text], [start_time: datetime], [end_time: datetime])` — Get Alerts
- `get_artifacts_metadata_by_uuid(alert_uuid: text)` — Get Artifacts Metadata By UUID
- `get_config()` — Get Config
- `get_custom_feeds()` — Get Custom Feeds
- `list_quarantined_emails([filter_by_time: checkbox], [from: text], [subject: text], [appliance_id: text], [limit: text])` — List Quarantined Emails
- `list_yara_rule(yara_type: text, [appliance: text])` — List YARA Rule
- `release_quarantined_emails(queue_ids: text)` — Release Quarantined Emails

_miscellaneous_
- `delete_yara_rule(yara_type: text, yara_file: text, [target_type: select])` — Delete YARA Rule
- `download_yara_rule(yara_type: text, yara_file: text, [appliance: text])` — Download YARA Rule

_remediation_
- `delete_custom_feed(feed_name: text)` — Delete Custom Feed


### `know-b4-phisher` v1.0.1 _(installed)_
_KnowBe4 PhishER_

KnowBe4 PhishER helps your InfoSec and Security Operations team cut through the inbox noise and respond to the most dangerous threats more quickly.

**6 operation(s)**:

_investigation_
- `add_comment(id: text, comment: text)` — Add Comment
- `add_tags(id: text, tags: text)` — Add Tags
- `get_message_by_id(id: text)` — Get Message by ID
- `get_message_list([query: text], [all: checkbox], [page: integer], [per: integer])` — Get Messages
- `remove_tags(id: text, tags: text)` — Remove Tags
- `update_message(id: text, [category: select], [status: select], [severity: select])` — Update Message


### `mailboxlayer` v1.0.0 _(installed)_
_Mailboxlayer_

Mailboxlayer simple and powerful API offering instant email address validation & verification via syntax checks, typo and spelling checks, SMTP checks, free and disposable provider filtering.This connector facilitates the automated operations email verification and check email validation.

**1 operation(s)**:

_investigation_
- `get_email_verification_details(email_address: text)` — Get Email Verification Detail


### `mimecast` v3.0.0 _(installed)_
_Mimecast_

This connector integrate with Mimecast endpoints provide cloud-based email management for Microsoft Exchange and Microsoft Office 365, and offers security, archiving, and continuity services to protect business mail.

**26 operation(s)**:

_containment_
- `blacklist_url(url: text, disableLogClick: checkbox, [matchType: select], [comment: text])` — Add URL to Block List
- `block_sender(sender: text, to: text)` — Block Sender

_investigation_
- `add_group_member(id: text, [domain: text], [emailAddress: text], [notes: text])` — Add Group Member
- `archive_search([mailbox: text], [admin: checkbox], [search_text: text], [show: select], [doc_type: select])` — Archive Search
- `create_group(description: text, [parentId: text])` — Create Group
- `decode_url(url: text)` — Decode URL
- `find_groups([query: text], [source: select])` — Find Groups
- `get_aliases(emailAddress: text)` — Get Aliases
- `get_archive_search_message_details(id: text)` — Get Archive Search Message Details
- `get_attachment_protection_logs([result: select], [from: datetime], [to: datetime], [route: select], [oldestFirst: checkbox])` — Get Attachment Protection Logs
- `get_blocked_sender_policy(policy_id: text)` — Get Blocked Sender Policy
- `get_dlp_logs([searchField: select], [query: text], [actions: multiselect], [from: datetime], [to: datetime], [routes: multiselect], [oldestFirst: checkbox])` — Get DLP Logs
- `get_group_members(id: text)` — Get Group Member
- `get_managed_url([domainOrComment: text], [domainOrUrl: text], [exactMatch: checkbox], [filterBy: json], [sortByUrl: checkbox], [sortOrder: text])` — Get Managed URL
- `get_message_info(id: text)` — Get Message Info
- `get_message_list(view: select, [mailbox: text], [start: datetime], [end: datetime], [includeDelegates: checkbox], [includeAliases: checkbox])` — Get Message List
- `get_search_url_logs([query: text], [start: datetime], [end: datetime])` — Get Search URL Logs
- `get_ttp_impersonation_protect_logs([actions: multiselect], [searchField: select], [query: text], [from: datetime], [to: datetime], [identifiers: multiselect], [oldestFirst: checkbox], [taggedMalicious: checkbox])` — Get TTP Impersonation Protect Logs
- `get_ttp_url_logs([route: select], [from: datetime], [to: datetime], [scan_result: select], [oldest_first: checkbox])` — Get TTP URL Logs
- `message_search([from: text], [to: text], [subject: text], [messageId: text], [senderIP: text], [searchReason: text], [url: text], [start: datetime], [end: datetime], [route: multiselect], [status: multiselect])` — Message Search
- `update_group(id: text, [description: text], [parentId: text])` — Update Group

_miscellaneous_
- `create_blocked_sender_policy(action: select, description: text, from_type: select, to_type: select, [from_part: select], [source_ip: text], [additional_fields: json])` — Create Blocked Sender Policy
- `delete_group(id: text)` — Delete Group

_remediation_
- `remove_group_member(id: text, [emailAddress: text], [domain: text])` — Remove Group Member
- `unblock_sender(sender: text, to: text)` — Unblock Sender
- `whitelist_url(url: text, disableRewrite: checkbox, disableUserAwareness: checkbox, disableLogClick: checkbox, [matchType: select], [comment: text])` — Add URL to Allow List


### `mimecast-s2` v3.0.0 _(installed)_
_Mimecast S2_

This connector integrate with Mimecast S2 endpoints provide cloud-based email management for Microsoft Exchange and Microsoft Office 365, and offers threat monitoring and remediation service for internally generated emails

**5 operation(s)**:

_investigation_
- `archive_search([mailbox: text], [admin: checkbox], [search_text: text], [show: select], [doc_type: select], [more_details: checkbox])` — Archive Search
- `create_incident(reason: text, search_by: select, [start: datetime], [end: datetime])` — Create Incident
- `get_archive_search_message_details(id: text)` — Get Archive Search Message Details
- `get_message_info(id: text)` — Get Message Info
- `message_search(search_by: select, [searchReason: text], [start: datetime], [end: datetime], [route: multiselect], [status: multiselect], [get_message_info: checkbox])` — Message Search


### `smime-messaging` v1.0.0 _(installed)_
_S/MIME Messaging_

Secure/Multipurpose Internet Mail Extensions (S/MIME) is an email security protocol that uses encryption to protect the confidentiality and integrity of email messages. S/MIME can be used to encrypt email messages or digitally sign email messages. 

<b><i> Prerequisites: </i></b> User need to install swig using following command: <b><i> yum install swig </i></b>

**4 operation(s)**:

_investigation_
- `decrypt_email(file_iri: text)` — Decrypt Email
- `encrypt_email(receiver_public_key: file, file_name: text, body: richtext)` — Encrypt Email
- `sign_email(file_name: text, body: richtext)` — Sign Email
- `verify_sign(sender_public_key: file, file_iri: text)` — Verify Sign


### `symantec-cloud` v2.0.1 _(installed)_
_Symantec Email Security.cloud_

Symantec Email Security.cloud stops targeted spear phishing and other email threats by blocking sender IP, Domain and Email address etc.

**12 operation(s)**:

_containment_
- `block_domain(IocType: select, APIRowAction: select, IocValue: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Blacklist Domain
- `block_email(IocType: select, APIRowAction: select, IocValue: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Blacklist Email Address
- `block_ip(APIRowAction: select, IocValue: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Blacklist IP Address
- `block_md5(APIRowAction: select, IocValue: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Blacklist MD5
- `block_sha2(APIRowAction: select, IocValue: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Blacklist SHA-2
- `block_subject(APIRowAction: select, IocValue: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Block Subject Text
- `block_url(APIRowAction: select, IocValue: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Blacklist URL
- `merge_iocs(ioc_type: multiselect, EmailDirection: select, Description: text, [RemediationAction: select])` — Merge IOCs In Blacklist
- `renewall_ioc([domain_name: text])` — Renew All Blacklist IOC
- `replace_iocs(ioc_type: multiselect, EmailDirection: select, Description: text, [RemediationAction: select])` — Replace All IOCs In Blacklist

_investigation_
- `download_iocs(response_format: select, [domain_name: text])` — Download IOCs

_remediation_
- `delete_ioc(IocType: select, IocValue: text, iocBlackListId: text, EmailDirection: select, Description: text, [RemediationAction: select])` — Remove IOC from Blacklist


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


### `gmail` v3.1.0 _(installed, ingestion)_
_GSuite for Gmail_

Allows for searching emails, send emails, import emails,listing users, and deleting emails using the GSuite for Gmail

**8 operation(s)** (+1 hidden):

_investigation_
- `delete_messages(emailAddr: text, messageIds: text)` — Delete Emails
- `get_unread_emails([emailAddr: text], [query: text], [labelIds: text], [mark_read: checkbox], [includeSpamTrash: checkbox], [parse_inline: checkbox], [pageToken: text], [limit: integer])` — Get Unread Emails
- `import_email(emailAddr: text, to: text, subject: text, [cc: text], [bcc: text], [body: text], [id: text], [attachmentId: text], [labelIds: text], [threadId: text], [partId: text], [historyId: text], [internalDate: datetime], [headers: json], [snippet: text], [data: text], [size: integer], [filename: text], [mimeType: text], [sizeEstimate: integer], [parts: json])` — Import Email
- `list_users(emailAddr: text, [pageToken: text])` — List Users (Deprecated)
- `modify_email_label(emailAddr: text, id: text, [removeLabelIds: text], [addLabelIds: text])` — Modify Email Label
- `search_emails(emailAddr: text, [query: text], [labelIds: text], [includeSpamTrash: checkbox], [pageToken: text])` — Search for Emails
- `send_email(emailAddr: text, to: text, [body_type: select], [cc: text], [bcc: text], [id: text], [attachmentId: text], [labelIds: text], [threadId: text], [partId: text], [historyId: text], [internalDate: datetime], [headers: json], [data: text], [size: integer], [filename: text], [snippet: text], [mimeType: text], [sizeEstimate: integer], [parts: json])` — Send Email


### `microsoft-graph-mail` v1.4.0 _(installed, ingestion)_
_Microsoft Graph Mail_

Using Microsoft Graph integrate with Outlook by creating an app and get authorized access to a user's Outlook mail in a personal or organization account.

**16 operation(s)** (+1 hidden):

_investigation_
- `add_email_category(user_id: text, message_id: text, category: text)` — Add Email Category
- `create_email_threat_submission(input: select, [other_params: json])` — Create Email Threat Submission
- `delete_email(user_id: text, [source: select], message_id: text)` — Delete Email
- `execute_api_request(endpoint: text, method: select, [query_params: json], [payload: json])` — Execute an API Request
- `forward_email(to_recipients: text, from_recipients: text, message_id: text, [body: richtext])` — Forward Email
- `get_child_folders(user_id: text, source_folder: select, [limit: integer])` — Get Child Folders
- `get_email_categories(user_id: text, message_id: text)` — Get Email Categories
- `get_folders(user_id: text, [limit: integer])` — Get Folders
- `get_unread_emails(user_id: text, source: select, [mark_as_read: checkbox], [parse_inline: checkbox], [save_email: checkbox], [limit: integer])` — Get Unread Emails
- `search_emails(user_id: text, source: select, [odata_query: text], [search: text], [mark_read: checkbox], [parse_inline: checkbox], [limit: integer])` — Search Emails
- `send_email(from: text, [body_type: select], to_recipients: text, [cc_recipients: text], [bcc_recipients: text], [iri_list: text], [flag: select], [importance: select])` — Send Email
- `send_email_as_reply(message_id: text, from_recipients: text, [to: text], [cc_recipients: text], [bcc_recipients: text], [body: richtext], [iri_list: text])` — Send Mail as Reply

_miscellaneous_
- `copy_email(user_id: text, destination_folder: select, message_id: text)` — Copy Email
- `move_email(user_id: text, destination_folder: select, message_id: text)` — Move Email
- `remove_email_category(user_id: text, message_id: text, category: text)` — Remove Email Category


### `sendgrid` v1.1.0 _(installed)_
_SendGrid_

SendGrid

**10 operation(s)** (+1 hidden):

_investigation_
- `create_batch_id()` — Create Batch ID
- `delete_scheduled_send(batch_id: text)` — Delete Scheduled Send
- `get_alerts()` — Get Alerts
- `get_contact_list()` — Get Contact List
- `get_email_stats(stats_by: select, start_date: datetime, [end_date: datetime], [aggregated_by: select])` — Get Email Statistics
- `get_scheduled_send([batch_id: text])` — Get Scheduled Send
- `search_email(query: text, [limit: integer])` — Search Emails
- `send_email(from_email: email, to_emails: email, [cc_recipients: text], [bcc_recipients: text], [body_type: select], [iri_list: text], [inline_iri_list: text], [batch_id: text], [send_at: integer])` — Send Email
- `update_scheduled_send(batch_id: text, status: select)` — Update Scheduled Send


### `zimbra-administrator` v1.0.0 _(installed)_
_Zimbra Administrator_

Zimbra Collaboration is the world’s leading open source messaging and collaboration solution. Zimbra includes complete email, contacts, calendar, file sharing, tasks and chat and can be accessed from the Zimbra Web client via any device and any other email client. Using Zimbra Administrator integration user can search across mailboxe, delete emails etc.

**3 operation(s)**:

_investigation_
- `get_account_details(account: text)` — Get Account Details
- `search_emails([source: select], email_addresses: text, [subject: text], [query: text])` — Search Email

_remediation_
- `delete_email(mailbox: text, message_id: integer)` — Delete Email


### `zimbra-mailbox` v1.0.0 _(installed)_
_Zimbra Mailbox_

Zimbra Collaboration is the world's leading open source messaging and collaboration solution. Zimbra includes complete email, contacts, calendar, file sharing, tasks, and chat solution. It can be accessed from the Zimbra Web client via any device and any other email client. Using Zimbra integration, users can search emails, retrieve unread emails, import, and export emails.

**5 operation(s)**:

_investigation_
- `export_mailbox([mailbox: text], response_format: select, [query: text])` — Export Mailbox
- `get_contact([mailbox: text], [folder: select], [query: text])` — Get Contacts
- `get_unread_emails([mailbox: text], [source: select], [parse_header: checkbox])` — Get Unread Emails
- `import_email([mailbox: text], [source: select], input: select, value: text)` — Import Email
- `search_emails([mailbox: text], [source: select], [query: text], [parse_header: checkbox])` — Search Emails


---

## Endpoint

### `code42` v1.0.0 _(installed, ingestion)_
_Code42_

Code42 use to identify potential data exfiltration from insider threats while speeding investigation and response by providing fast access to file events and metadata across physical and cloud environments. This connector facilitates the automated operations related to alerts, high risk employee, departing employee, or legal hold matter.

**11 operation(s)**:

_investigation_
- `add_user_to_high_risk_employee(username: text)` — Add User to High Risk Employee
- `add_user_to_legal_hold_matter(username: text, matter_name: text)` — Add User to Legal Hold Matter
- `download_file_from_code42(hash: text)` — Download File from Code42
- `get_alert_details(alert_ids: text)` — Get Alert Details
- `get_alerts(query: text, [page_num: integer], [page_size: integer], [created_at: datetime])` — Get Alerts
- `get_all_departing_employees([filter_type: select], [sort_key: select], [sort_direction: select], [page_size: integer])` — Get All Departing Employees
- `get_all_high_risk_employees([filter_type: select], [page_size: integer])` — Get All High Risk Employees
- `get_users([active: select], [email: text], [org_uid: text], [role_id: integer], [q: text])` — Get All Users
- `remove_user_from_high_risk_employee(username: text)` — Remove User from High Risk Employee
- `remove_user_from_legal_hold_matter(username: text, matter_name: text)` — Remove User from Legal Hold Matter
- `resolve_alerts(alert_ids: text, [reason: text])` — Resolve Alerts


### `deepsecurity` v1.1.0 _(installed)_
_Trend Micro Deep Security_

Trend Micro Deep Security

**7 operation(s)**:

_investigation_
- `get_all_host_info()` — Get All Hosts
- `get_app_control_events([event_time_op: select], [event_time: datetime], [limit: text])` — Get Application Control Events
- `get_events(event_type: select, [host_name: text], [host_group_id: text], [host_type: select], [security_profile_name: text], [range_from: datetime], [range_to: datetime], [time_type: select])` — Get Events
- `get_latest_alerts([alert_id_op: select], [alert_id: text], [limit: text], [dismissed: checkbox])` — Get Alerts
- `get_security_profile(profile_id: text)` — Get Security Profile
- `scan_computer_by_host(scan_type: select, host_names: text)` — Scan Endpoint

- `assign_security_profile_to_host(security_profile_name: text, host_name: text)` — Assign Security Profile


### `tanium-threat-response` v1.0.0 _(installed)_
_Tanium Threat Response_

Tanium Threat Response monitors the entire IT ecosystem for suspicious files, misconfiguration of registry settings, and other security risks while alerting security teams in real-time. This connector facilitates automated operations to manage endpoints processes, evidence, alerts, files, snapshots, and connections.

**12 operation(s)**:

_investigation_
- `create_evidence(connection_name: text, host_name: text, process_id: text)` — Create Evidence
- `create_snapshot(connection_name: text)` — Create Snapshot
- `get_connections([limit: integer], [offset: integer])` — Get Connections
- `get_downloaded_file(file_id: text)` — Get Downloaded File
- `get_events_by_process(connection_name: text, process_id: text, [limit: integer], [offset: integer])` — Get Events By Process
- `get_file_download_info(file_id: text)` — Get File Download Info
- `get_file_info(connection_name: text, path: text)` — Get File Info
- `get_parent_process(connection_name: text, process_id: text)` — Get Parent Process
- `get_parent_process_tree(connection_name: text, process_id: text)` — Get Parent Process Tree
- `get_process_children(connection_name: text, process_id: text, [limit: integer], [offset: integer])` — Get Process Children
- `get_process_tree(connection_name: text, process_id: text)` — Get Process Tree
- `update_alert_state(alert_ids: integer, state: select)` — Update Alert State


---

## Endpoint Management

### `microsoft-scom` v1.0.0 _(installed)_
_Microsoft SCOM_

Microsoft SCOM Connector

**6 operation(s)**:

_Containment_
- `set_resolution_state(alert_id: text, state: select, [id: integer])` — Set Resolution State
- `update_alert(alert_id: text, [owner: text], [ticket_id: text], [custom_fields: json], [state: select], [state_id: integer])` — Update Alert

_Remediation_
- `close_alert(alert_id: text, [comment: text])` — Close Alert

_investigation_
- `get_device_info([ip_address: text], [computer_name: text])` — Get Device Information
- `list_alerts([computer_name: text])` — Get Alerts
- `list_endpoints([domain: text])` — List Endpoints


### `microsoft-winrm` v2.1.0 _(installed)_
_Microsoft WinRM_

Microsoft WinRM Connector help to connect windows endpoint and execute commands on it.

**6 operation(s)**:

_miscellaneous_
- `execute_command(command: text)` — Run Command
- `execute_ps_command(command: text, [convert_to_json: checkbox])` — Run Powershell Command
- `execute_ps_script(command: textarea)` — Run Inline Powershell Script
- `execute_script(attachment_iri: text)` — Run Script
- `get_file(location: text, [create_attachment: checkbox])` — Get File
- `upload_file(location: text, attachment_iri: text)` — Upload File To Endpoint


---

## Endpoint Manager

### `ibm-bigfix` v1.0.0 _(installed)_
_IBM BigFix_

IBM BigFix connector handle actions like, get endpoints, get patches list etc.

**6 operation(s)**:

- `deploy_patch(fixlet_id: text, action_id: text, [site_name: text], [computer_id: text])` — Create Action
- `get_host(hostname: text)` — Get Bigfix ID
- `list_computer_group(site_type: select)` — Get Computer Groups List 
- `list_endpoints()` — Get Endpoints
- `list_fixlets(site_type: select, [site_name: text])` — Get Patches List
- `list_sites()` —  Get Sites List


---

## Endpoint Protection

### `carbonblack-defense` v3.0.0 _(installed, ingestion)_
_CarbonBlack Defense_

CarbonBlack Defense is the most powerful Next-Generation Anti Virus platform. This connector facilitates automated operations related to devices, policies, alerts, notifications etc.

**21 operation(s)**:

_investigation_
- `add_rule_to_policy(policy_id: integer, ruleInfo: json)` — Add Rule To Policy
- `change_device_status(device_id: integer, update_option: select)` — Change Device Status
- `create_policy(policy_using: select)` — Create Policy
- `delete_rule_from_policy(policy_id: integer, rule_id: integer)` — Delete Rule from Policy
- `execute_file_commands(device_id: integer, name: select)` — Execute Live Commands - File
- `execute_process_commands(device_id: integer, name: select)` — Execute Live Commands - Process
- `execute_registry_commands(device_id: integer, name: select)` — Execute Live Commands - Registry
- `find_event_by_id(event_id: text)` — Find Event By ID
- `find_events([hostName: text], [hostNameExact: text], [ownerName: text], [ownerNameExact: text], [ipAddress: text], [sha256hash: text], [applicationName: text], [eventType: select], [searchWindow: select], [start: integer], [rows: integer])` — Find Events
- `find_processes([hostNameExact: text], [ownerName: text], [ownerNameExact: text], [ipAddress: text], [searchWindow: text], [start: integer], [rows: integer])` — Find Processes
- `get_alert_by_id(alert_id: text)` — Get Alert by ID
- `get_alert_details(alert_id: text)` — Get Alert Details
- `get_all_policies()` — Get All Policies
- `get_device_status(device_id: integer)` — Get Device Status
- `get_devices_status([hostName: text], [hostNameExact: text], [ownerName: text], [ownerNameExact: text], [ipAddress: text], [start: integer], [rows: integer])` — Get Devices Status
- `get_notifications()` — Get Notifications
- `get_policy_by_id(policy_id: integer)` — Get Policy By ID
- `search_alerts([device_name: text], [device_id: text], [device_username: text], [device_os: select], [group_results: checkbox], [id: text], [target_value: select], [minimum_severity: select], [policy_name: text], [process_name: text], [workflow: multiselect], [tag: text], [created_start: datetime], [created_end: datetime], [last_updated_start: datetime], [last_updated_end: datetime], [start: integer], [rows: integer])` — Search Alerts
- `update_policy(policy_id: text, policy_using: select)` — Update Policy
- `update_rule_in_policy(policy_id: integer, rule_id: integer, [ruleInfo: json])` — Update Rule in Policy

_miscellaneous_
- `delete_policy(policy_id: integer)` — Delete Policy


### `carbonblack-protect-bit9` v1.0.2 _(installed)_
_CarbonBlack Protection Bit9_

CarbonBlack Protection is a comprehensive endpoint threat protection solution. This connector facilitates automated operation related to file white listing operations.

**8 operation(s)**:

_containment_
- `block_file(input_type: select, value: text, [name: text], [policyIds: text], [description: text])` — Block File

_investigation_
- `get_approval_request([status: multiselect], [computerName: text], [computerId: integer], [id: integer], [fileCatalogId: integer], [policyId: integer], [createdBy: text], [requestType: multiselect], [priority: select], [fileName: text], [pathName: text], [process: text], [dateCreated: datetime], [dateModified: datetime], [sort: select], [offset: integer], [limit: integer], [expand: text])` — Get Approval Requests
- `get_policies([id: integer], [name: text], [description: text], [packageName: text], [enforcementLevel: select], [disconnectedEnforcementLevel: select], [helpDeskUrl: text], [imageUrl: text], [dateModified: datetime], [dateCreated: datetime], [readOnly: select], [hidden: select], [automatic: select], [loadAgentInSafeMode: select], [reputationEnabled: select], [fileTrackingEnabled: select], [customLogo: select], [automaticApprovalsOnTransition: select], [allowAgentUpgrades: select], [clVersionMax: integer], [offset: integer], [limit: integer])` — Get Policies
- `get_system_info(input_type: select, value: text)` — Get System Information
- `hunt_file(file_hash: text)` — Hunt File
- `update_approval_request(id: integer, status: select, resolution: select, [resolutionComments: text], [requestorEmail: text])` — Update Approval Request

_remediation_
- `remove_filerule(hash: text)` — Remove File Rule
- `unblock_file(input_type: select, value: text, [name: text], [policyIds: text], [description: text])` — Unblock File


### `carbonblack-response` v2.0.2 _(installed)_
_VMware Carbon Black EDR_

VMware Carbon Black EDR is purpose-built for enterprise SOC and IR teams.This connector facilitates automated operation related to endpoint protection like isolate endpoint, unisolate endpoint, hunt file, terminate process etc. with VMware Carbon Black EDR server.

**17 operation(s)**:

_containment_
- `block_hash(md5: text)` — Block Hash
- `delete_file(input_type: select, value: text, file_name: text)` — Delete file
- `isolate_sensor(input_type: select, value: text)` — Isolate Sensor
- `terminate_process(input_type: select, value: text, select_type: select, process_value: text)` — Terminate Process

_investigation_
- `bulk_update_alert(alert_id: text, status: select)` — Bulk Update Alerts
- `get_blacklisted_hash()` — Get All Block Hashes
- `get_file_info_md5(md5: text)` — Get File Information
- `get_host_details(input_type: select, [value: text])` — Get Sensor(s) Information
- `get_process_list(input_type: select, value: text)` — Get All Processes
- `get_watchlist([watchlist_id: text])` — Get Watchlist
- `hunt_file(query_type: select, md5: text, [start: integer], [rows: integer])` — Hunt file
- `list_connections(input_type: select, value: text, pname_pid: select, proc_pid: text)` — Get Process Connections
- `run_query(query_type: select, query: text, [start: integer], [rows: integer])` — Run Query
- `search_alert([query: text], [status: multiselect], [sort_by: select], [start: integer], [rows: integer])` — Search Alerts
- `update_alert(unique_id: text, status: select)` — Update Alert

_remediation_
- `unblock_hash(md5: text)` — Unblock Hash
- `unisolate_sensor(input_type: select, value: text)` — Remove Isolation


### `fidelis-edr` v1.1.0 _(installed)_
_Fidelis EDR_

Fidelis Endpoint EDR detects endpoint activity in real time and retrospectively so you can accelerate your response and stop adversaries at the point of entry. This connector supports following actions Get Alerts, Get Endpoints, Detete Endpoints, etc

**21 operation(s)**:

_investigation_
- `create_custom_task(packageId: text, isplaybook: select, endpoints: text, integration_output_format: text, script_id: text, questions: textarea, [json_questions: text], timeout_in_Seconds: integer, [queue_expiration_in_hours: text])` — Create Custom Task
- `create_task(packageId: text, isplaybook: select, endpoints: text)` — Execute Task
- `delete_endpoint(endpointID: text)` — Delete Endpoint
- `execute_script_package(scriptPackageId: text, timeoutInSeconds: integer, hosts: text, [integrationOutputs: text], [questions: json])` — Execute Script Package
- `get_alert_responses([search: text], [offset: integer], [columns: text], [limit: integer], [sort: text])` — Get Alert Responses
- `get_alerts([facetSearch: text], [startDate: datetime], [endDate: datetime], [skip: integer], [take: integer], [sort: text])` — Get Alerts
- `get_api_info()` — Get API version Information
- `get_endpoints(startIndex: integer, count: integer, sort: text)` — Get Endpoints
- `get_endpoints_by_name(nameArray: text)` — Get Endpoint By Name
- `get_endpoints_by_search_query(startRange: integer, count: integer, search: text, sort: text, [accessType: select])` — Get Endpoints By Search Query
- `get_installed_software(endpointID: text, [facetSearch: text], [skip: integer], [take: integer], [sort: text])` — Get Installed Software
- `get_job_status_by_job_id(jobResultID: text)` — Get Job Status By Job ID
- `get_playbooks(take: text)` — Get Playbooks
- `get_playbooks_detail(id: text)` — Get Playbooks Details
- `get_playbooks_scripts([filterType: select], [platformFilter: select], [sort: text], [take: integer], [skip: integer])` — Get Playbooks And Scripts
- `get_script_packages()` — Get Script Packages
- `get_script_packages_file(scriptID: text)` — Get Script Packages File
- `get_script_packages_manifest(scriptID: text)` — Get Script Packages Manifest
- `get_script_packages_metadata(scriptID: text)` — Get Script Packages Metadata
- `get_script_packages_template(scriptID: text)` — Get Script Packages Template
- `script_job_results(jobResultID: text)` — Get Script Job Results


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


### `microsoft-365-defender` v1.2.0 _(installed, ingestion)_
_Microsoft 365 Defender_

Microsoft 365 Defender For Endpoints is a unified platform for preventative protection, post-breach detection, automated investigation, and response. This connector facilitates the automated operations related to files, machines, IP, Domain, actor etc.

**4 operation(s)**:

_investigation_
- `advanced_hunting(Query: text)` — Advanced Hunting
- `get_incident(id: text)` — Get Incident Details
- `list_incidents([lastUpdateTime: datetime], [createdTime: datetime], [status: multiselect], [assignedTo: text], [query: text], [skip: text], [top: integer], [get_all_records: checkbox])` — Get Incidents List
- `update_incident(id: text, [status: select], [assignedTo: text], [classification: select], [tags: text], [comment: text])` — Update Incident


### `red-canary` v1.0.0 _(installed)_
_Red Canary_

Red Canary collects endpoint data using Carbon Black Response and CrowdStrike Falcon. The collected data is standardized into a common schema, which allows teams to detect, analyze and respond to security incidents.

**9 operation(s)**:

_investigation_
- `acknowledge_detection(detection_id: integer)` — Acknowledge Detection
- `deisolate_endpoint(ids: text)` — Deisolate Endpoint
- `get_detection(detection_id: integer)` — Get Detection Details
- `get_endpoint(endpoint_id: integer)` — Get Endpoint Details
- `isolate_endpoint(ids: text)` — Isolate Endpoint
- `list_detection_marked_indicators_of_compromise(detection_id: integer, [page: integer], [per_page: integer])` — List Detection Marked Indicators of Compromise
- `list_detections([page: integer], [per_page: integer], [since: datetime])` — Get Detections List
- `list_endpoints([page: integer], [per_page: integer], [order_by: select], [filter_query: json])` — Get Endpoints List
- `update_remediation_state(detection_id: integer, remediation_state: select, [comment: text])` — Update Remediation State


### `symantec-sepm` v1.1.1 _(installed)_
_Symantec EPM (SEPM)_

Integrate with Symantec Endpoint Protection to execute investigative actions like list endpoints, and scan endpoint, in addition to actions like add blacklist and delete blacklist.

**26 operation(s)**:

_containment_
- `add_blacklist(name: text, hashType: select, data: text, domainId: text, description: text)` — Add Blacklist
- `assign_fingerprint_to_group(fingerprint_id: text, group_id: text)` — Assign Fingerprint List To Group
- `delete_blacklist(fid: text)` — Delete Blacklist
- `quarantine_endpoints(apply_quarantine: select, ids: text)` — Quarantine Endpoints/Groups
- `update_blacklist(fid: text, name: text, hashType: select, data: text, domainId: text, description: text)` — Update Blacklist

_investigation_
- `active_scan_endpoint(type: select)` — Active Scan Endpoint
- `client_list_group_by_content_version()` — List Client For Group By Content Version
- `client_list_reporting_malware_events(reportType: select, startTime: datetime, endTime: datetime)` — Get Malware Reporting Clients
- `create_domain(domainName: text, maxClientIdleTimeInDays: integer, maxNpvdiClientIdleTimeInDays: integer, [deleteIdleClients: checkbox], [deleteIdleNpvdiClients: checkbox], [allowSavingCredentials: checkbox], [allowNeverExpiringPasswords: checkbox], [displayLogonBanner: checkbox])` — Create Domain
- `critical_events_info()` — Get Critical Events Information
- `delete_domain(domain_id: text)` — Delete Domain
- `full_scan_endpoint(type: select)` — Full Scan Endpoint
- `get_command_status(command_id: text)` — Get Command Status
- `get_computers([domain: text], [computerName: text], [pageSize: integer], [pageIndex: integer], [custom_filter: json])` — List Endpoints
- `get_domain_info(domain_id: text)` — Get Domain Information
- `get_domain_name(domain_id: text)` — Get Domain Name
- `get_domains()` — List Domains
- `get_fingerprint_list_info(fid: text)` — Get Fingerprint List Information
- `get_group_info(group_id: text)` — Get Group Information
- `get_threat_stats()` — Get Threat Status
- `list_client_groups_by_content_source()` — Get Client Groups By Content Source
- `list_groups()` — List Groups
- `list_infected_clients(reportType: select, startTime: datetime, endTime: datetime)` — List Infected Client
- `scan_endpoint(scan_run: select, ids: text, body: text)` — Scan Endpoint
- `updates_domain_info(domain_id: text, domainName: text, maxClientIdleTimeInDays: integer, maxNpvdiClientIdleTimeInDays: integer, [deleteIdleClients: checkbox], [deleteIdleNpvdiClients: checkbox], [allowSavingCredentials: checkbox], [allowNeverExpiringPasswords: checkbox], [displayLogonBanner: checkbox])` — Update Domain

_remediation_
- `unquarantine_endpoints(apply_quarantine: select, ids: text)` — Unquarantine Endpoints/Groups


### `trendmicro-control-manager` v1.0.0 _(installed)_
_Trend Micro Control Manager_

Connector for Trend Micro Control Manager which utilizes isolating and restoring an isolated endpoint.

**2 operation(s)**:

_containment_
- `isolate_endpoint(ip_address: text)` — Isolate Endpoint

_remediation_
- `restore_isolated_endpoint(ip_address: text)` — Restore Isolated Endpoint


### `vmware-carbon-black-enterprise-edr` v1.0.0 _(installed, ingestion)_
_VMware Carbon Black Enterprise EDR_

VMware Carbon Black Enterprise EDR is an advanced threat hunting and incident response solution delivering unfiltered visibility for top security operations centers (SOCs) and incident response (IR) teams. This connector facilitates automated operations related to devices, watchlists, reports etc.

**22 operation(s)**:

_investigation_
- `create_report(title: text, description: text, severity: select, timestamp: datetime, [md5: text], [ipv4: text], [ipv6: text], [dns: text], [query_ioc: text], [tags: text])` — Create Report
- `create_watchlist(watchlist_type: select)` — Create Watchlist
- `delete_watchlist(watchlist_id: text)` — Delete Watchlist
- `disable_watchlist_alerts(watchlist_id: text)` — Disable Watchlist Alerts
- `enable_watchlist_alerts(watchlist_id: text)` — Enable Watchlist Alerts
- `get_all_watchlist()` — Get All Watchlists
- `get_device_details(device_id: text)` — Get Device Details
- `get_ioc_ignore_status(report_id: text, ioc_id: text)` — Get IOC Ignore Status
- `get_report(report_id: text)` — Get Report
- `get_report_ignore_status(report_id: text)` — Get Report Ignore Status 
- `get_watchlist(watchlist_id: text)` — Get Watchlist
- `get_watchlist_alert_status(watchlist_id: text)` — Get Watchlist Alert Status
- `get_watchlist_telemetry(watchlist_id: text)` — Get Watchlist Telemetry
- `ignore_ioc(report_id: text, ioc_id: text)` — Ignore IOC
- `ignore_report(report_id: text)` — Ignore Report
- `reactive_ioc(report_id: text, ioc_id: text)` — Re-activate IOC
- `reactive_report(report_id: text)` — Re-activate Report
- `search_devices([id: text], [device_os: select], [status: multiselect], [policy_id: text], [target_priority: select], [ad_group_id: text], [last_contact_start: datetime], [last_contact_end: datetime], [start: integer], [rows: integer], [sort_by: select], [order_by: select])` — Search Devices
- `search_watchlist_alerts([device_name: text], [device_id: text], [device_username: text], [device_os: select], [group_results: checkbox], [id: text], [target_value: select], [minimum_severity: select], [policy_name: text], [process_name: text], [workflow: multiselect], [tag: text], [created_start: datetime], [created_end: datetime], [last_updated_start: datetime], [last_updated_end: datetime], [report_id: text], [report_name: text], [watchlist_id: text], [watchlist_name: text], [start: integer], [rows: integer])` — Search Watchlist Alerts
- `unquarantine_device(device_id: text)` — Unquarantine Device
- `update_watchlist(watchlist_id: text, watchlist_type: select)` — Update Watchlist

_remediation_
- `quarantine_device(device_id: text)` — Quarantine Device


---

## Endpoint Security

### `bitdefender` v1.0.0 _(installed)_
_Bitdefender_

Bitdefender Endpoint Detection and Response (EDR) is a security solution designed to detect, investigate, and respond to advanced cyber threats on endpoints. This connector enables automated operations such as Get Computers Quarantine List, Get Exchange Quarantine List, and others.

**22 operation(s)**:

_Security_
- `add_to_blocklist(type: select, hash: text, [sourceinfo: text])` — Add to Blocklist
- `change_incident_status(incident_id: text, type: select, status: select)` — Change Incident Status
- `createRestoreEndpointFromIsolationTask(endpointId: text)` — Create Restore Endpoint from Isolation
- `create_add_file_to_quarantine_task([endpointIds: text], [filePath: text])` — Create Add File To Quarantine Task
- `create_isolate_endpointtask(endpointId: text)` — Create Isolate Endpoint Task
- `create_scan_task(targetIds: text, type: select, [name: text], [returnAllTaskIds: select])` — Create Scan Task
- `create_scan_task_by_mac(macAddresses: text, type: select, [name: text], [returnAllTaskIds: select])` — Create Scan Task By Mac Address
- `delete_custom_rule(ruleId: text, type: select)` — Delete Custom Rule
- `get_block_list_items(page: integer, perPage: integer)` — Get Block List Items
- `get_custom_rule_list(page: integer, perPage: integer, companyId: text, type: select)` — Get Custom Rules List
- `get_endpoints_list([isManaged: select], [page: integer], [perPage: integer])` — Get Endpoints List
- `get_managed_endpoints_details(endpointId: text)` — Get Managed Endpoints Details
- `get_scan_tasks_list([status: select], [page: integer], [perPage: integer])` — Get Scan Task List
- `get_scan_tasks_status([taskId: text])` — Get Scan Task Status
- `move_endpoints(endpointId: text, groupId: text)` — Move Endpoints
- `remove_from_blocklist(hashItemId: text)` — Remove from BlockList
- `set_endpoint_label(endpointId: text, label: text)` — Set Endpoint Label
- `update_incident_note(incident_id: text, type: select, note: text)` — Update Incident Note

_investigation_
- `get_accounts_list([page: integer], [perPage: integer])` — Get Accounts List
- `get_computers_quarantine_items_list([endpointId: text], [page: integer], [perPage: integer], [filters: json])` — Get Computers Quarantine List
- `get_exchange_quarantine_items_list([endpointId: text], [page: integer], [perPage: integer], [filters: json])` — Get Exchange Quarantine List
- `get_policies_list([page: integer], [perPage: integer])` — Get Policies List


### `bmc-discovery` v1.0.0 _(installed)_
_BMC Discovery_

BMC Discovery is a data center discovery solution that automatically discovers data center inventory, configuration and relationship data, and maps applications to the IT infrastructure. This connector facilitates automated operation related to run search.

**1 operation(s)**:

_investigation_
- `search_query(query: text, [delete: checkbox], [offset: integer], [results_id: text], [limit: integer])` — Run Search


### `cisco-amp-endpoints` v1.0.1 _(installed)_
_Cisco AMP For Endpoints_

Cisco AMP for Endpoints provides complete protection against the most advanced attacks. Cisco AMP Connector facilitates automated operation related to endpoints,hunt indicator, blacklist hash, policies etc.

**22 operation(s)**:

_investigation_
- `application_blocking_list([name: text], [limit: integer], [offset: integer])` — Get Application Blocking Filelist
- `create_file_list_item(list_guid: text, filehash: text, description: text)` — Add Hash to Blacklist
- `create_group(name: text, description: text)` — Create Group
- `delete_file_list_item(list_guid: text, filehash: text)` — Delete Filelist Item
- `get_all_policies()` — Get All Policies
- `get_device_trajectory(connector_guid: text, [filter_opt: select], [value: text], [limit: integer])` — Get Device Trajectory
- `get_device_trajectory_by_user(connector_guid: text, user: text, [limit: integer])` — Get Device Trajectory By User
- `get_endpoint_by_guid(connector_guid: text)` — Get Computer Information
- `get_endpoints_by_activity(filter_opt: select, type: select, query: text, [limit: integer], [offset: integer])` — Hunt Indicator
- `get_event_types()` — Get Event Types
- `get_file_list(id: text)` — Get Specific Filelist
- `get_group(group_guid: text)` — Get Specific Group
- `get_group_list([name: text], [limit: integer])` — Get Group List
- `get_item(list_guid: text, filehash: text)` — Get Item from Filelist
- `get_list_of_items(list_guid: text, [limit: integer], [offset: integer])` — Get Items from Filelist
- `get_simple_custom_detection_list([name: text], [limit: integer])` — Get Simple Custom Detection Filelist
- `get_specific_policy(policy_guid: text)` — Get Specific Policy
- `list_endpoints()` — Get All Computers
- `move_computer_to_group(connector_guid: text, group_guid: text)` — Move Computer to Group
- `search_endpoints([hostname: text], [group_guid: text], [internal_ip: text], [external_ip: text], [limit: integer])` — Search Computers
- `search_event([connector_guid: text], [group_guid: text], [event_type: text], [detection_sha256: text], [application_sha256: text], [start_date: datetime], [limit: integer], [offset: integer])` — Search Events
- `update_group(group_guid: text, [windows_policy_guid: text], [mac_policy_guid: text], [linux_policy_guid: text], [android_policy_guid: text])` — Update Group


### `crowd-strike-falcon` v3.1.0 _(installed, ingestion)_
_CrowdStrike Falcon_

The CrowdStrike Falcon® platform is pioneering cloud-delivered endpoint protection. It both delivers and unifies IT Hygiene, next-generation antivirus, endpoint detection and response (EDR), managed threat hunting, and threat intelligence — all delivered via a single lightweight agent.

**55 operation(s)**:

_investigation_
- `add_host_to_host_group(host_group_id: text, host_ids: text)` — Add Host To Host Group
- `admin_cmd_result(cloud_request_id: text, sequence_id: integer)` — Get Admin Command Result
- `admin_cmd_run(device_id: text, command: text, [command_args: text], [queue_offline: checkbox], [auto_refresh: checkbox])` — Run Admin Command
- `alert_aggregates(name: text, type: select, field: text, [interval: select], [filter: text], [q: text], [ranges: text], [date_ranges: text], [missing: text], [min_doc_count: integer], [max_doc_count: integer], [include: text], [exclude: text], [time_zone: text], [from: integer], [size: integer], [sort: text], [sub_aggregates: text])` — Alert Aggregates
- `alert_search([severity_name: multiselect], [behaviors.tactic: text], [behaviors.technique: text], [created_timestamp: multiselect], [status: multiselect], [confidence: integer], [sort: text], [filename.raw: text], [assigned_to_name: text], [q: text], [filter_str: text], [record_number: select])` — Alert Search
- `apply_action_on_quarantine_files_by_file_id([ids: text], [action: text], [comment: text])` — Apply Action On Quarantine Files By File ID
- `apply_action_on_quarantine_files_by_query([action: text], [q: text], [filter: text], [comment: text])` — Apply Action On Quarantine Files By Query
- `create_on_demand_scan(oDSPayload: object)` — Create On Demand Scan
- `detection_aggregates(name: text, type: select, field: text, [interval: select], [filter: text], [q: text], [ranges: text], [date_ranges: text], [missing: text], [min_doc_count: integer], [size: integer], [sort: text], [sub_aggregates: text])` — Detection Aggregates
- `detection_search([max_severity_displayname: multiselect], [behaviors.tactic: text], [behaviors.technique: text], [last_behavior: multiselect], [status: multiselect], [max_confidence: integer], [sort: select], [filename.raw: text], [assigned_to_name: text], [q: text], [filter_str: text], [record_number: select])` — Detection Search
- `device_details(ids: text)` — Get Device Details
- `execute_an_api_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_alert_details(ids: text)` — Get Alert Details
- `get_custom_ioa_rule_name(ruleInstanceID: text)` — Get Custom IOA Rule Name
- `get_cve_list_by_vulnerability(cve: text, [after: text], [limit: integer])` — Spotlight: Get CVE List by Vulnerability
- `get_detection_details(ids: text)` — Get Detection Details
- `get_device_online_status(deviceID: text)` — Get Device Online Status
- `get_host_group_list([filter: text], [sort: text], [offset: integer], [limit: integer])` — Get Host Group List
- `get_host_list_by_vulnerability(cve_ids: text, [after: text], [limit: integer])` — Spotlight: Get Host List by Vulnerability
- `get_ioc(ids: text)` — Get IOC Details
- `get_list_of_processes(type: select, value: text, device_id: text, [limit: integer], [offset: integer])` — Get Processes Related to IOC
- `get_quarantine_files([filter: text], [q: text], [sort: text], [offset: integer], [limit: integer])` — Get Quarantine Files List
- `get_quarantine_files_aggregates(type: select, name: text, [date_ranges: text], [exclude: text], [extended_bounds: text], [field: text], [filter: text], [include: text], [interval: select], [min_doc_count: integer], [max_doc_count: integer], [missing: text], [q: text], [ranges: text], [from: integer], [size: integer], [sort: text], [sub_aggregates: text], [time_zone: text])` — Get Quarantine Files Aggregates
- `get_quarantine_files_count(filter: text)` — Get Quarantine Files Count
- `get_quarantine_files_metadata(ids: text)` — Get Quarantine Files Metadata
- `get_scan_by_id(oDSID: text)` — Get Scan By ID
- `get_uid(uid: text)` — Get User ID
- `get_user_details(ids: text)` — Get User Details
- `hunt_domain(domain_value: text, [count_only: checkbox], [record_number: select])` — Hunt Domain
- `hunt_file(hash_type: select, hash_value: text, [count_only: checkbox], [record_number: select])` — Hunt File
- `incidents_get_crowdscores([filter: text], [sort: text], [limit: integer], [offset: integer])` — Get Incidents Crowdstrike Score
- `incidents_get_details([ids: text])` — Get Incident Details
- `incidents_query([status: multiselect], [assigned_to: text], [tags: multiselect], [start: select], [filter_str: text], [sort: text], [limit: integer], [offset: integer])` — Search Incidents
- `list_endpoint([filter_str: text], [offset: integer], [limit: integer])` — Get Endpoint List
- `list_ioc([filter: text], [record_number: select], [sort: text], [from_parent: checkbox])` — Get IOCs
- `list_user_id()` — Get User IDs List
- `list_usernames()` — Get Usernames List
- `process_details(ids: text)` — Get Process Details
- `put_files_get(file_ids: text)` — Get Executables Details by IDs
- `put_files_list([filter: text], [offset: integer], [limit: integer], [sort: text])` — Get Executable List
- `quarantine_device(ids: text)` — Contain the Host
- `remove_containment(ids: text)` — Remove Containment
- `remove_host_from_host_group(host_group_id: text, host_ids: text)` — Remove Host From Host Group
- `scripts_get(file_ids: text)` — Get Scripts Details by IDs
- `scripts_list([filter: text], [offset: integer], [limit: integer], [sort: text])` — Get Scripts List
- `search_devices([device_id: text], [hostname: text], [system_manufacturer: text], [last_seen: multiselect], [offset: integer], [limit: integer], [filter: text])` — Search Devices
- `search_vulnerabilities(filter: text, [facet: multiselect], [sort: checkbox], [after: text], [limit: integer])` — Spotlight: Search Vulnerabilities
- `session_file_download(device_id: text, sha256: text, file_name: text, [extra_params: json], [auto_refresh: checkbox])` — Download Session File
- `session_file_list(device_id: text, [auto_refresh: checkbox])` — Download Session File List
- `update_alert(ids: text, [action_parameters: json])` — Update Alert
- `update_detection(ids: text, [status: select], [uid: text], [comment: text], [show_in_ui: checkbox])` — Update Detection
- `update_incidents(ids: text, status: select)` — Update Incidents Status
- `update_ioc(number_of_indicators_to_update: select, [retrodetects: checkbox], [ignore_warnings: checkbox], [comment: text])` — Update IOC
- `upload_ioc(number_of_indicators_to_create: select, [retrodetects: checkbox], [ignore_warnings: checkbox], [comment: text])` — Create IOC

_remediation_
- `delete_ioc(search-ioc-by: select, [comment: text], [from_parent: checkbox])` — Delete IOC


### `cybereason` v1.0.0 _(installed)_
_Cybereason_

The Cybereason Defense Platform combines endpoint prevention, detection, and response all in one lightweight agent.

**14 operation(s)**:

_investigation_
- `get_malops([start_time: datetime], [end_time: datetime])` — Get Incidents
- `get_sensors([limit: integer], [offset: integer], [sortDirection: select], [filter.machineName: text], [filter.guid: text], [filter.externalIpAddress: text], [filter.internalIpAddress: text], [filter.customTags: text], [filter.department: text], [raw_filters: text])` — Query Sensors
- `query_file(filter.filehash: text)` — Query File by its Hash
- `query_user([filter.username: text])` — Query User

_remediation_
- `blacklist_file(keys: text, [remove: checkbox], [prevent: checkbox])` — Blacklist File
- `blacklist_ip_or_domain(keys: text, [remove: checkbox])` — Blacklist IP or Domain
- `isolate_sensor_by_ip(ip_addresses: text)` — Isolate Malop Machine by IP Address
- `isolate_sensor_by_pylum_id(pylumIds: text)` — Isolate Malop Machine by Pylum ID
- `kill_process(process_guid: text, machine_guid: text)` — Kill Process On Endpoint
- `query_process([filter.elementDisplayName: text], [filter.calculatedUser: text], [filter.execedBy: text], [filter.ownerMachine: text], [filter.parentProcess: text], [filter.hasOutgoingConnection: checkbox], [filter.hasModuleFromTempEvidence: checkbox], [raw_filters: text])` — Get Process On Endpoint
- `unisolate_sensor_by_ip(ip_addresses: text)` — Un-Isolate Malop Machine by IP Address
- `unisolate_sensor_by_pylum_id(pylumIds: text)` — Un-Isolate Malop Machine by Pylum ID
- `whitelist_file(keys: text, [remove: checkbox])` — Whitelist File
- `whitelist_ip_or_domain(keys: text, [remove: checkbox])` — Whitelist IP or Domain


### `cylance-protect` v1.1.1 _(installed)_
_CylancePROTECT_

CylancePROTECT connector predicts, prevents, and protects threat in device

**14 operation(s)**:

_containment_
- `block_hash(filehash: text, list_type: select, reason: text, [category: select], [filename: text])` — Block Hash

_investigation_
- `get_device_info(device_id: text)` — Get Device Information
- `get_device_threats(device_id: text, [page_no: integer], [record_limit: integer])` — Get Device Threats
- `get_device_zones(device_id: text, [page_no: integer], [record_limit: integer])` — Get Device Zones
- `get_devices([page_no: integer], [record_limit: integer])` — Get Devices
- `get_global_list(list_type: select, [page_no: integer], [record_limit: integer])` — Get Global List
- `get_policies([page_no: integer], [record_limit: integer])` — Get Policies
- `get_threat_details(filehash: text)` — Get Threat Details
- `get_threat_devices(filehash: text, [page_no: integer], [record_limit: integer])` — Get Threat Devices
- `get_threats([found_after: datetime], [page_no: integer], [record_limit: integer])` — Get Threats

_miscellaneous_
- `update_device_info(device_id: text, device_schema: json)` — Update Device Information
- `update_device_threat(device_id: text, filehash: text, event: select)` — Update Device Threat

_remediation_
- `unblock_hash(filehash: text, list_type: select)` — Unblock Hash

- `get_zones([page_no: integer], [record_limit: integer])` — Get Zones


### `cymulate-endpoint-security` v1.0.0 _(installed)_
_Cymulate Endpoint Security - BAS_

Cymulate’s Endpoint Security vector allows organizations to deploy and run simulations of full attack scenario’s e.g. ransomware or implementation of MITRE ATT&CK TTPs on a dedicated endpoint in a controlled and safe manner, comprehensive testing that covers all aspects of endpoint security.

**14 operation(s)**:

_investigation_
- `create_assessment(agentName: text, agentProfileName: text, templateID: text, worm_ipRange_exclude: json, scheduleLoop: text, integrationsSelected: json, [schedule: datetime])` — Create Assessment
- `get_assessment_history([fromDate: datetime], [toDate: datetime], [env: text])` — Get Assessment History
- `get_assessment_status([id: text])` — Get Assessment Status
- `get_attack_navigator_results([env: text])` — Get Attack Navigator Results
- `get_attack_navigator_results_by_assessment_id(id: text)` — Get Attack Navigator Results By Assessment ID
- `get_detection_results_by_payload_id(id: text)` — Get Detection Results By Payload ID
- `get_executive_report_results_by_assessment_id(id: text)` — Get Executive Report Results By Assessment ID
- `get_latest_report_results([env: text])` — Get Latest Report Results
- `get_latest_siem_detection_results([env: text])` — Get Latest SIEM Detection Results
- `get_latest_technical_report_results([skip: integer], [limit: integer], [env: text])` — Get Latest Technical Report Results
- `get_technical_report_results_by_assessment_id(id: text, [skip: integer], [limit: integer])` — Get Technical Report Results By Assessment ID
- `get_template_by_id(id: text)` — Get Template By ID
- `get_template_list()` — Get Template List
- `stop_assessment([env: text])` — Stop Assessment


### `endgame` v1.0.0 _(installed)_
_Endgame_

This connector interfaces with the Endgame Endpoint Protection Platform to allow users to perform actions such as quarantining hosts

**14 operation(s)**:

_investigate_
- `get_alert_details(alert_id: text)` — Get Alert Details
- `get_alert_timeline(alert_id: text)` — Get Alert Timeline
- `get_alerts()` — Get Alerts
- `get_endpoints()` — Get Endpoints
- `get_investigation_details(investigation_id: text)` — Get Investigation Details
- `get_investigations()` — Get Investigations
- `update_investigation(investigation_id: text, changes: textarea)` — Update Investigation

_miscellaneous_
- `get_devices()` — Get Devices
- `get_policies()` — Get policies
- `get_task_descriptions()` — Get Task Descriptions
- `get_users()` — Get Users

_remediation_
- `kill_process(endpoint: text, pid: integer)` — Kill Process

_utilities_
- `execute_file(endpoint: text, filepath: text, argv: textarea)` — Execute File
- `upload_file(endpoint: text, filepath: text, filedata: textarea)` — Upload File


### `eset-protect-enterprise` v1.0.0 _(installed)_
_ESET Protect Enterprise_

ESET Protect Enterprise extended detection and response (XDR) that delivers enterprise-grade visibility, threat hunting and response options.

**11 operation(s)**:

_containment_
- `block_executables(server_url: text, [executableUuid: text], [json_data: json])` — Block Executables
- `create_device_tasks(server_url: text, task_payload: json)` — Create Device Task
- `end_computer_isolation_from_network(server_url: text, device_uuid: text, device_group_uuid: text, task_expire_time: text, [task_display_name: text], [task_description: text])` — End Computer Isolation From Network
- `isolate_computer_from_network(server_url: text, device_uuid: text, device_group_uuid: text, task_expire_time: text, [task_display_name: text], [task_description: text])` — Isolate Computer From Network

_investigation_
- `get_detection_groups(server_url: text, [detectionGroupUuid: text], [deviceUuid: text], [start_time: text], [end_time: text], [pageSize: text], [pageToken: text])` — Get Detection Groups List
- `get_detections(server_url: text, [detectionUuid: text], [deviceUuid: text], [start_time: text], [end_time: text], [pageSize: text], [pageToken: text])` — Get Detections List
- `get_device(server_url: text, deviceUuid: text)` — Get Device by UUID
- `get_device_groups(server_url: text, [groupUuid: text], [pageSize: text], [pageToken: text])` — Get Device Groups List
- `get_device_tasks(server_url: text, [task_uuid: text], [pageSize: text], [pageToken: text])` — Get Device Tasks List
- `get_executables(server_url: text, [executableUuid: text], [pageSize: text], [pageToken: text])` — Get Executables List

_remediation_
- `unblock_executables(server_url: text, [executableUuid: text], [json_data: json])` — Unblock Executables


### `fireeye-hx` v1.3.0 _(installed)_
_Trellix Endpoint Security (HX)_

Trellix Endpoint Security (HX) brings advanced protection to endpoints. Its comprehensive endpoint visibility and threat intelligence enables analysts to adapt their defense based on real-time details to deploy informed, tailored responses to threat activity. This connector facilitates automated operations related to host, alerts, acquisition, quarantines, scripts etc.

**34 operation(s)** (+1 hidden):

_containment_
- `approve_containment(agent_id: text)` — Approve Host Containment
- `full_containment(agent_id: text)` — Contain a Host as an Admin
- `release_containment(agent_id: text)` — Release Host from Containment
- `request_containment(agent_id: text)` — Request Host Containment

_investigation_
- `create_indicator_in_category(display_name: text, description: text, category: select, created_by: text, [signature: text], [meta: json], [platforms: text])` — Create Indicator in Specified Category
- `data_acquisition_request(hostname: text, script_name: text, script_type: select)` — Data Acquisition using Script
- `data_acquisition_status(acq_id: integer)` — Get Data Acquisition Status
- `delete_indicator(indicator_uri_name: text, category: select)` — Delete Indicator
- `get_alert_details(alert_id: integer)` — Get Alert Details
- `get_all_scripts()` — Get All Scripts
- `get_category_indicator(ind_uri_name: text, category: select)` — Get Indicator from Category
- `get_data_acquisition_package(acq_id: integer)` — Fetch a Data Acquisition Package
- `get_file_acquisition_package(acq_id: integer)` — Fetch a File Acquisition Package
- `get_file_acquisition_status(acq_id: integer)` — Get File Acquisition Information
- `get_host(agent_id: text)` — Get Host
- `get_quarantine_file_acquisition_status(acq_id: integer)` — Get Quarantine File Acquisition Information
- `get_quarantined_files_package(acq_id: text)` — Get Quarantine File
- `get_script_by_id(script_id: text)` — Fetch a Script by ID
- `get_triage_acquisition_status(triage_id: integer)` — Get Triage Acquisition Information
- `get_triage_collection(triage_id: integer)` — Fetch a Triage Collection
- `list_alerts(offset: integer)` — List Alerts
- `list_data_acquisitions(hostname: text, [offset: integer], [limit: integer], [sort: text], [filter_field: text])` — List Host Data Acquisitions
- `list_host_alerts(agent_id: text, offset: integer, [limit: integer])` — List Host Alerts
- `list_hosts([filter: select], [search: text], [limit: integer], [offset: integer])` — List Hosts
- `list_script_for_all_host([search_term: text], [offset: integer], [limit: integer], [sort: select], [filter_field: text])` — List All Scripts Details
- `list_triage_acquisitions([filter_field: text], [filter_value: text])` — List Triage Acquisitions
- `new_file_acquisition(agent_id: text, filepath: text, filename: text, [ext_id: text])` — Create a File Acquisition for a Host
- `new_quarantined_file_acquisition(quarantined_id: text)` — Request Quarantined File Acquisition
- `new_triage_acquisition(agent_id: text, [ext_id: text])` — Create a Triage Acquisition for a Host
- `parse_mans_file(reference_id: text)` — Parse Mandiant Analysis File
- `quarantine_list_by_host_id(hostname: text)` — Get Quarantine List
- `search_ind_all_category(search: text, [offset: integer], [limit: integer])` — Search Indicator in All Categories
- `start_search(agentsIds: text, host_set: text, [exhaustive: checkbox], [ip_address: text], [ip_address_operator: select], [file_MD5_hash: text], [file_MD5_hash_operator: select], [file_full_path: text], [file_full_path_operator: select], [dns_hostname: text], [dns_hostname_operator: select], [limit: integer], [stop_search: select])` — Perform Generic Search


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


### `harfanglab-edr` v1.1.0 _(installed, ingestion)_
_HarfangLab EDR_

The connector allows FortiSOAR users to fetch data and take actions on Hurukai HarfangLab EDR platform

**7 operation(s)**:

_incident_management_
- `change_security_event_status(param@security_event_id: text, param@status: select)` — Change Security Event Status
- `search_multiple_iocs_in_telemetry(param@iocs: json, param@search_types: multiselect, param@format: select, param@limit: integer)` — Search Multiple IoCs

_investigation_
- `fetch_security_events([param@first_fetch: integer], [param@alert_status: select], [param@alert_type: text], [param@min_severity: select], [param@max_fetch: integer], [param@delay: integer])` — Fetch Security Events
- `get_event_by_id(param@event_id: text)` — Get Event By ID
- `search_endpoint([param@hostname: text], [param@ostype: text], [param@status: select], [param@fields: json], [param@offset: integer], [param@limit: integer])` — Search Endpoints

_response_
- `isolate_endpoint(param@agent_id: text)` — Isolate an Endpoint
- `unisolate_endpoint(param@agent_id: text)` — Unisolate an Endpoint


### `ibm-security-qradar-edr` v1.0.0 _(installed, ingestion)_
_IBM Security QRadar EDR_

IBM Security QRadar EDR, formerly ReaQta, remediates known and unknown endpoint threats in near real time with easy-to-use intelligent automation that requires little-to-no human interaction.

**5 operation(s)**:

_investigation_
- `add_notes_to_alert(alert_id: text, notes: text)` — Add Notes To Alert
- `close_alert_by_id(alert_id: text, [malicious: checkbox])` — Close Alert By ID
- `get_alert_by_id(alert_id: text)` — Get Alert By ID
- `get_alert_list([id: text], [endpointId: text], [triggerCondition: multiselect], [tag: text], [activityState: select], [severity: multiselect], [status: multiselect], [happenedAfter: datetime], [happenedBefore: datetime], [receivedAfter: datetime], [receivedBefore: datetime], [closedAfter: datetime], [closedBefore: datetime], [lastChangedAfter: datetime], [lastChangedBefore: datetime], [country: text], [gid: text], [count: integer], [lastSeenId: text], [get_all_records: checkbox])` — Get Alert List
- `get_events_related_to_alerts(alert_id: text, [processId: text], [processPid: text], [eventType: text], [severity: multiselect], [happenedAfter: datetime], [happenedBefore: datetime], [country: text], [mitreTechnique: text], [gid: text], [get_all_records: checkbox])` — Get Events Related To Alerts


### `kaspersky-security-center` v1.0.2 _(installed)_
_Kaspersky Security Center_

Kaspersky Security Center makes it easy to manage and secure both physical and virtual endpoints from a single, unified management console.

**12 operation(s)**:

_investigation_
- `add_group(parent_id: text, name: text)` — Add Group
- `add_policy_request(KLPOL_DN: text, KLPOL_PRODUCT: text, KLPOL_VERSION: text, KLPOL_GROUP_ID: integer)` — Add Policy
- `delete_group(group_id: text, flag: select)` — Delete Specific Group
- `get_groups()` — Get All Groups Details
- `get_host_details(host_id: text)` — Get Host Details
- `get_hosts_group_static_info()` — Get Host Group Static Info
- `get_listhost_group(group_id: text)` — Get Host List
- `get_policy_request(policy_id: text)` — Get Specific Policy
- `get_product_installed(host_id: text)` — Get Products Installed
- `get_software_installed(host_id: text)` — Get Software Installed on Specific Host
- `list_policies_request(group_id: text)` — Get All Policies on Specific Group
- `move_hosts(newgroup: text, pHostNames: text)` — Move Host to Specific Group


### `malwarebytes` v2.0.0 _(installed)_
_Malwarebytes_

Malwarebytes protects endpoints against malware, ransomware, and other advanced online threats, This connector facilitates automated operations like get endpoints, scan endpoints, get threats etc

**24 operation(s)**:

_investigation_
- `assign_group_to_endpoints(group_id: text, [endpoint_ids: text], [filter_query: json])` — Assign Group to Endpoints
- `create_group(name: text, policy_id: text, [parent_id: text])` — Create Group
- `create_policy(name: text, contents: json)` — Create Policy
- `delete_endpoints(endpoint_ids: text)` — Delete Endpoints
- `delete_group(id: text)` — Delete Group
- `delete_policy(policy_id: text)` — Delete Policy
- `get_endpoint_agent_info(endpoint_id: text)` — Get Endpoint Agent Info
- `get_endpoint_assets(endpoint_id: text)` — Get Endpoint Assets
- `get_endpoint_details(endpoint_id: text)` — Get Endpoint Details
- `get_endpoint_network_info(endpoint_id: text)` — Get Endpoint Network Info
- `get_endpoint_quarantined_items(endpoint_id: text)` — Get Endpoint Quarantined Items
- `get_endpoint_status(endpoint_id: text)` — Get Endpoint Status
- `get_endpoint_suspicious_activities(endpoint_id: text, [since: datetime], [per_page: integer], [next_cursor: text])` — Get Endpoint Suspicious Activities
- `get_endpoints([machine_id: text], [is_isolated: checkbox], [has_alerts: checkbox], [policy_id: text], [policy_name: text], [host_name: text], [os_info.os_platform: text], [domain_name: text], [group_name: text], [machine_ip: text], [page_size: text], [next_cursor: text], [extra_query_params: json])` — Get Endpoints
- `get_events([search_string: text], [machine_id: text], [start: datetime], [end: datetime], [severity_flags: select], [next_cursor: text])` — Get Events
- `get_groups([name: text], [parent_id: text], [next_cursor: text])` — Get Groups
- `get_policies([policy_id: text])` — Get Policies
- `get_scan_result(id: text, [since: datetime], [next_cursor: text])` — Get Scan Result
- `get_tasks([task_id: text], [endpoint: text], [machine_id: text], [status: select], [page_size: text], [next_cursor: text])` — Get Tasks
- `quarantine_endpoints(endpoint_ids: text)` — Quarantine Endpoints
- `remediate_endpoint_suspicious_activity(endpoint_id: text, sa_id: text)` — Remediate Endpoint Suspicious Activity
- `scan_endpoints(command: select, endpoint_ids: text)` — Scan Endpoints
- `unquarantine_endpoints(endpoint_ids: text)` — Unquarantine Endpoints
- `update_endpoint_suspicious_activity(endpoint_id: text, sa_id: text, status: select)` — Update Endpoint Suspicious Activity


### `mcafee-epo` v1.1.1 _(installed)_
_McAfee ePO_

McAfee ePolicy Orchestrator Connector can used to run client task, add tags, remove tags, search client task,search systems, check task status, wakeup agent, list tables, execute query etc

**11 operation(s)**:

_containment_
- `apply_tag(endpoint: text, tag_name: text)` — Apply Tag

_investigation_
- `check_task_status([task_name: text], [task_source: text], [count: text], [age: text], [unit: select])` — Check Task Status
- `execute_query(execute_by: select)` — Execute Query
- `list_databases()` — List Databases
- `list_queries()` — List Queries
- `list_tables([table: text])` — List Tables
- `run_client_task(system_names: text, product_id: text, task_id: text)` — Run Client Task
- `search_systems([search_text: text])` — Search Systems
- `search_text([search_text: text])` — Search Client Task

_remediation_
- `clear_tag(endpoint: text, tag_name: text)` — Clear Tag
- `wakeup_agent(system_names: text)` — Wakeup Agent


### `nexthink` v1.0.0 _(installed)_
_Nexthink_

Nexthink is an automation and remediation platform which delivers visibility across all environments so IT teams can continuously improve the digital workplace to optimize productivity and cost.

**1 operation(s)**:

_investigation_
- `nexthink_query_language(query: text, platform: text)` — Run Query


### `paloalto-cortex-xdr` v1.4.0 _(installed, ingestion)_
_Palo Alto Cortex XDR_

Cortex XDR applies machine learning at cloud scale to rich network, endpoint, and cloud data, so you can quickly find and stop targeted attacks, insider abuse, and compromised endpoints.

**32 operation(s)**:

_investigation_
- `blacklist_files(hash_list: text, [comment: text], [incident_id: integer])` — Blacklist Files
- `cancel_scan_endpoints([filter.in.endpoint_id_list: text], [filter.in.dist_name: text], [filter.in.group_name: text], [filter.in.alias: text], [filter.in.hostname: text], [filter.in.username: text], [filter.in.ip_list: text], [filter.in.platform: select], [filter.in.isolate: select], [filter.in.scan_status: select], [filter.gte.first_seen: datetime], [filter.lte.first_seen: datetime], [filter.gte.last_seen: datetime], [filter.lte.last_seen: datetime], [incident_id: text])` — Cancel Scan Endpoints
- `create_distributions(name: text, package_type: select, description: text)` — Create Distributions
- `delete_endpoints(endpoint_id_list: text)` — Delete Endpoints
- `fetch_incidents([filter.in.incident_id_list: text], [filter.gte.creation_time: datetime], [filter.lte.creation_time: datetime], [filter.gte.modification_time: datetime], [filter.lte.modification_time: datetime], [filter.in.alert_sources: text], [filter.eq.status: select], [filter.contains.description: text], [cursor.search_from: integer], [cursor.search_to: integer], [sort.field: select], [sort.keyword: select])` — Fetch Incidents
- `get_alerts([alert_id_list: text], [severity: multiselect], [alert_source: text], [creation_time_gte: datetime], [creation_time_lte: datetime], [sort_field: select], [sort_order: select], [search_from: integer], [search_to: integer])` — Get Alerts
- `get_all_endpoints()` — Get All Endpoints
- `get_audit_agent_report([filter.in.endpoint_id: text], [filter.in.endpoint_name: text], [filter.in.type: text], [filter.in.sub_type: text], [filter.in.result: text], [filter.in.domain: text], [filter.in.xdr_version: text], [filter.in.category: select], [filter.gte.timestamp: datetime], [filter.lte.timestamp: datetime], [cursor.search_from: integer], [cursor.search_to: integer], [sort.field: select], [sort.keyword: select])` — Get Audit Agent Report
- `get_audit_management_log([filter.in.email: text], [filter.in.type: text], [filter.in.sub_type: text], [filter.in.result: text], [filter.gte.timestamp: datetime], [filter.lte.timestamp: datetime], [cursor.search_from: integer], [cursor.search_to: integer], [sort.field: select], [sort.keyword: select])` — Get Audit Management Logs
- `get_device_violations([filter.in.endpoint_id_list: text], [filter.in.vendor: text], [filter.in.vendor_id: text], [filter.in.product: text], [filter.in.product_id: text], [filter.in.serial: text], [filter.in.hostname: text], [filter.in.username: text], [filter.in.type: select], [filter.in.ip_list: text], [filter.in.violation_id_list: integer], [filter.gte.timestamp: datetime], [filter.lte.timestamp: datetime], [cursor.search_from: integer], [cursor.search_to: integer], [sort.field: select], [sort.keyword: select])` — Get Device Violations
- `get_distribution_status(distribution_id: text)` — Get Distribution Status
- `get_distribution_url(distribution_id: text, package_type: select)` — Get Distribution URL
- `get_distribution_version()` — Get Distribution Version
- `get_endpoints([filter.in.endpoint_id_list: text], [filter.in.dist_name: text], [filter.in.group_name: text], [filter.in.alias: text], [filter.in.hostname: text], [filter.in.username: text], [filter.in.endpoint_status: select], [filter.in.ip_list: text], [filter.in.platform: select], [filter.in.isolate: select], [filter.in.scan_status: select], [filter.gte.first_seen: datetime], [filter.lte.first_seen: datetime], [filter.gte.last_seen: datetime], [filter.lte.last_seen: datetime], [cursor.search_from: integer], [cursor.search_to: integer], [sort.field: select], [sort.keyword: select])` — Get Endpoints
- `get_incident_details(incident_id: text, [alerts_limit: integer])` — Get Incident Details
- `get_policy(endpoint_id: text)` — Get Policy
- `get_quarantine_status(endpoint_id: text, file_hash: text, file_path: text)` — Get Quarantine Status
- `get_query_result_by_query_id(query_id: text, [pending_flag: select], [limit: integer])` — Get Query Results By Query ID
- `insert_cef_alerts(alerts: text)` — Insert CEF Alerts
- `insert_parsed_alerts(alert_name: text, product: text, vendor: text, local_port: integer, remote_ip: text, remote_port: integer, [local_ip: text], [event_timestamp: datetime], [severity: select], [alert_description: text], [action_status: text])` — Insert Parsed Alerts
- `insert_simple_indicators(indicator: text, type: select, severity: select, [expiry: select], [class: text], [comment: text], [reputation: select], [reliability: select], [vendors: json], [validate: checkbox])` — Insert Simple Indicators
- `isolate_endpoints(isolate_endpoint: text, [incident_id: text])` — Isolate Endpoints
- `quarantine_files(filter.in.endpoint_id_list: text, file_path: text, file_hash: text)` — Quarantine Files
- `restore_file(file_hash: text, [endpoint_id: text], [incident_id: integer])` — Restore File
- `retrieve_file(filter.in.endpoint_id_list: text, files: select, file_path: text, [filter.in.dist_name: text], [filter.in.group_name: text], [filter.in.alias: text], [filter.in.hostname: text], [filter.in.ip_list: text], [filter.in.platform: select], [filter.in.isolate: select], [filter.gte.first_seen: datetime], [filter.gte.last_seen: datetime], [filter.lte.first_seen: datetime], [filter.lte.last_seen: datetime])` — Retrieve File
- `retrieve_file_details(group_action_id: text)` — Retrieve File Details
- `scan_endpoints([filter.in.endpoint_id_list: text], [filter.in.dist_name: text], [filter.in.group_name: text], [filter.in.alias: text], [filter.in.hostname: text], [filter.in.username: text], [filter.in.ip_list: text], [filter.in.platform: select], [filter.in.isolate: select], [filter.in.scan_status: select], [filter.gte.first_seen: datetime], [filter.lte.first_seen: datetime], [filter.gte.last_seen: datetime], [filter.lte.last_seen: datetime], [incident_id: text])` — Scan Endpoints
- `unisolate_endpoints([endpoint_ids: text], [incident_id: text])` — Unisolate Endpoints
- `update_alerts(alert_ids: text, [severity: select], [status: select], [comment: text])` — Update Alerts
- `update_incident(incident_id: text, [assigned_user_mail: text], [assigned_user_pretty_name: text], [manual_severity: select], [status: select], [comment: checkbox], [resolve_comment: textarea])` — Update Incident
- `whitelist_files(hash_list: text, [comment: text], [incident_id: integer])` — Whitelist Files
- `xql_query(query: text, [tenants: text], [from: datetime], [to: datetime])` — Execute XQL Query


### `rapid7-velociraptor` v1.0.0 _(installed)_
_Rapid7 Velociraptor_

Rapid7 Velociraptor is a unique, advanced open-source endpoint monitoring, digital forensic and cyber response platform. It provides you with the ability to more effectively respond to a wide range of digital forensic and cyber incident response investigations and data breaches.

**11 operation(s)**:

_investigation_
- `create_flow_download(client_id: text, flow_id: text, [wait: checkbox], [password: text], [format: text], [name: text], [expand_sparse: checkbox])` — Create Flow Download
- `create_hunt(artifacts: text, [description: text], [expires: text], [spec: text], [timeout: integer], [ops_per_sec: integer], [cpu_limit: integer], [iops_limit: integer], [max_rows: integer], [max_bytes: integer], [pause: checkbox], [include_labels: text], [exclude_labels: text], [os: text], [org_id: text])` — Create Hunt
- `create_hunt_download(hunt_id: text, [only_combined: checkbox], [wait: checkbox], [format: text], [base: text], [password: text], [expand_sparse: checkbox])` — Create Hunt Download
- `dump_artifact_definitions([names: text], [deps: checkbox], [sanitize: checkbox])` — Dump Artifact Definitions
- `get_flow_results(flow_id: text, client_id: text, [artifact: text], [source: text])` — Get Flow Results
- `get_hunt_results(hunt_id: text, [artifact: text], [source: text], [brief: checkbox])` — Get Hunt Results
- `list_clients([search: text], [client_id: text], [count: integer], [start: integer])` — Get Clients List
- `list_flows(client_id: text, [flow_id: text])` — Get Flows List
- `list_hunts([hunt_id: text], [count: integer], [offset: integer])` — Get Hunts List
- `run_artifacts_collection(client_id: text, artifacts: text, [env: text], [spec: text], [timeout: integer], [ops_per_sec: integer], [cpu_limit: integer], [iops_limit: integer], [max_rows: integer], [max_bytes: integer], [urgent: checkbox], [org_id: text])` — Run Artifacts Collection
- `run_vql_query(query: text)` — Run VQL Query


### `sophos-central` v4.2.0 _(installed, ingestion)_
_Sophos Central_

Sophos Central is a unified console for managing your Sophos products Sophos Central lets you administer protection for endpoints, mobile devices, encryption, web, email, servers, etc. This connector facilitates automated operations related to endpoints, email, etc.

**34 operation(s)**:

_investigation_
- `alerts_action(id: text, action: select, [message: text])` — Perform Alert Action
- `create_allowed_items(fileName: text, type: select, comment: text, [originPersonId: text], [originEndpointId: text])` — Create Allowed Item
- `create_blocked_items(fileName: text, type: select, comment: text)` — Create Blocked Item
- `create_exclusion_scanning(value: text, type: select, [scanMode: select], [comment: text])` — Create Exclusion Scanning
- `create_exploit_mitigation_application(paths: text)` — Create Exploit Mitigation Application
- `delete_allowed_items(id: text)` — Delete Allowed Item
- `delete_blocked_items(id: text)` — Delete Blocked Item
- `delete_endpoints(id: text)` — Delete Endpoint
- `delete_exclusion_scanning(id: text)` — Delete Exclusion Scanning
- `delete_exploit_mitigation_application(id: text)` — Delete Exploit Mitigation
- `get_alerts(id: text)` — Get Alert by ID
- `get_allowed_items(id: text)` — Get Allowed Item by ID
- `get_blocked_items(id: text)` — Get Blocked Item by ID
- `get_detected_exploits(id: text)` — Get Specific Detected Exploit
- `get_endpoint_tamper_protection(id: text)` — Get Endpoint Tamper Protection
- `get_endpoints(id: text, [fields: text], [view: select])` — Get Endpoint by ID
- `get_endpoints_isolation(id: text)` — Get Endpoint Isolations
- `get_exclusion_scanning(id: text)` — Get Exclusion Scanning by ID
- `get_exploit_mitigation_application(id: text)` — Get Exploit Mitigation by ID
- `isolate_endpoints(id: text, [comment: text])` — Isolate Endpoint
- `list_alerts([groupKey: text], [from: datetime], [to: datetime], [sort: text], [product: multiselect], [category: multiselect], [severity: select], [ids: text], [fields: text], [pageSize: integer], [pageTotal: checkbox])` — Get Alert List
- `list_allowed_items([page: integer], [pageSize: integer], [pageTotal: checkbox])` — Get Allowed Items
- `list_blocked_items([page: integer], [pageSize: integer], [pageTotal: checkbox])` — Get Blocked Items
- `list_detected_exploits([thumbprintNotIn: text], [page: integer], [pageSize: integer], [pageTotal: checkbox])` — Get Detected Exploits
- `list_endpoints([lastSeenAfter: datetime], [lastSeenBefore: datetime], [sort: text], [healthStatus: multiselect], [type: multiselect], [tamperProtectionEnabled: select], [lockdownStatus: multiselect], [ids: text], [isolationStatus: select], [hostnameContains: text], [associatedPersonContains: text], [groupNameContains: text], [searchFields: multiselect], [search: text], [ipAddresses: text], [cloud: text], [fields: text], [pageSize: integer], [pageFromKey: string], [pageTotal: checkbox], [view: select])` — Get Endpoints
- `list_exclusion_scanning(type: select, [page: integer], [pageSize: integer], [pageTotal: checkbox])` — Get Exclusion Scanning
- `list_exploit_mitigation_application([type: select], [modified: select], [page: integer], [pageSize: integer], [pageTotal: checkbox])` — Get Exploit Mitigation Application
- `scan_endpoints(id: text)` — Scan Endpoint
- `search_alerts([groupKey: text], [from: datetime], [to: datetime], [sort: text], [product: multiselect], [category: multiselect], [severity: multiselect], [ids: text], [fields: text], [pageSize: integer], [pageFromKey: string], [pageTotal: checkbox])` — Search Alerts
- `unisolate_endpoints(id: text, [comment: text])` — Unisolate Endpoint
- `update_allowed_items(id: text, comment: text)` — Update Allowed Item
- `update_endpoint_tamper_protection(id: text, [enabled: select], [regeneratePassword: select])` — Update Endpoint Tamper Protection
- `update_exclusion_scanning(id: text, [value: text], [scanMode: select], [comment: text])` — Update Exclusion Scanning
- `update_exploit_mitigation_application(id: text, paths: text)` — Update Exploit Mitigation Application


### `symantec-edr-cloud` v2.0.0 _(installed, ingestion)_
_Symantec EDR Cloud_

Symantec Endpoint Detection and Response Cloud helps in keeping attacks from turning into breaches and eliminate intrusions across all endpoints

**5 operation(s)**:

_containment_
- `delete_whitelist([id: text], [hash: text])` — Delete SHA256 from Whitelist

_investigation_
- `get_alerts([duration: select], [status: select], [alert_status: select], [read_status: select], [Category: multiselect], [sort_status: select], [sort_order: select], [fetch_count: integer])` — Get Alerts
- `get_report(alert_id: text)` — Get Alert Details
- `list_whitelist()` — Get Whitelist

_remediation_
- `add_whitelist(sha256: text, description: text)` — Add SHA256 to Whitelist


### `tehtris-edr` v1.0.0 _(installed, ingestion)_
_TEHTRIS EDR_

TEHTRIS EDR (Endpoint Detection and Response) is designed to detect, analyze, and respond to security incidents on endpoints (such as computers, servers, and mobile devices) in real time.

**41 operation(s)**:

_investigation_
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request

_utilities_
- `create_filter(name: text, lvlmin: integer, lvlmax: integer, description: text, module: text)` — Create Filter
- `create_new_global_policies(position: select, policyData: json)` — Create New Global Policies
- `delete_filter(filterId: text)` — Delete Filter
- `fetch_events(fromDate: datetime, [toDate: datetime], [eventId: integer], [countOnly: checkbox], [byTag: checkbox], [filterID: text], [createdOrModified: select], [offset: integer], [limit: integer])` — Fetch Events
- `fetch_info_about_endpoint(edrUuid: text, applianceId: integer)` — Fetch Endpoint Details
- `get_accesslogs(edrUuid: text, applianceId: integer, [hostname: text], [admin: checkbox], [logonEventTimeFrom: datetime], [logonEventTimeTo: datetime], limit: integer, [offset: integer])` — Get Access Logs
- `get_all_endpoints([hostname: text], [hostnameRegex: text], [domain: text], [domainRegex: text], [network: text], [firstSeenFrom: datetime], [firstSeenTo: datetime], [lastSeenFrom: datetime], [lastSeenTo: datetime], [offset: integer], [tags: json], [versions: json], [configUuid: json], [uuids: json], [applianceIds: json], [os: json])` — Get All Endpoints
- `get_all_global_policies()` — Get All Global Policies
- `get_browser_security(edrUuid: text, applianceId: integer, [hostname: text])` — Get Browser Security
- `get_current_scan_status(edrUuid: text, applianceId: integer)` — Get Current Scan Status
- `get_disk_scan_status(edrUuid: text, applianceId: integer, [scanId: text])` — Get Disk Scan Status
- `get_filter_by_id(filterId: text, [withHistory: checkbox])` — Get Filter by ID
- `get_history_of_processes(edrUuid: text, applianceId: integer, [userIdentifier: text], [username: text], [domainName: text], [localTime: checkbox], [timeFilter: select], [timeFrom: datetime], [timeTo: datetime], [sha256: text], [sha1: text], [md5: text], [path: text], [cmdline: text], limit: integer, [offset: integer], [pids: object], [ppids: object], [logonIds: object])` — Get Processes History
- `get_isolation_status(applianceId: integer, edrUuid: text)` — Get Isolation Status
- `get_last_offline_forensic_report(edrUuid: text, applianceId: integer)` — Get Last Offline Forensic Report
- `get_network_infos(edrUuid: text, applianceId: integer, [hostname: text])` — Get Network Information
- `get_offline_forensic_status(edrUuid: text, applianceId: integer)` — Get Offline Forensic Status
- `get_persistence_entries(edrUuid: text, applianceId: integer, [localTime: checkbox], [t: datetime], [persistence_path: text], [persistence_type: text], [name: text], [sha256: text], [sha1: text], [md5: text], [path: text], [cmdline: text], limit: integer, [offset: integer])` — Get Persistence Entries
- `get_process_tree(edrUuid: text, applianceId: integer, pid: integer, createTime: datetime, nbParents: integer, limit: integer, [offset: integer])` — Get Process Tree
- `get_software_list(edrUuid: text, applianceId: integer, [persist: checkbox])` — Get Software List
- `get_tags()` — Get Tags
- `get_unmanaged_hosts(applianceId: integer, [lastSeenFrom: datetime], [lastSeenTo: datetime], [limit: integer], [offset: integer])` — Get Unmanaged Hosts
- `get_usb_history(edrUuid: text, applianceId: integer, [hostname: text])` — Get USB History
- `get_users_connected(edrUuid: text, applianceId: integer, [hostname: text], limit: integer, [offset: integer])` — Get Users Connected
- `launch_disk_scan(edrUuid: text, applianceId: integer, [persist: checkbox], [scanADS: checkbox], [scanWhitelistPaths: object], [startFolders: object])` — Launch Disk Scan
- `list_folders_and_filters([name: text], [module: text], [oldFilterId: integer], [filtersOnly: checkbox], [presetFilters: checkbox])` — List Folders and Filters
- `list_quarantine_files(edrUuid: text, applianceId: integer)` — Get All Quarantine Files
- `quarantine_file(edrUuid: text, applianceId: integer, path: text, [persist: checkbox], [notification: text])` — Quarantine a File
- `restore_file_from_quarantine(edrUuid: text, applianceId: integer, path: text, [persist: checkbox])` — Restore File from Quarantine
- `search_binaries(applianceId: integer, [hostname: text], [hostnameRegex: text], [sha256: text], [sha1: text], [md5: text], [path: text], [pathRegex: text], [signatureCn: text], [signatureCnRegex: text], [lastSeenFrom: datetime], [lastSeenTo: datetime], [offset: text])` — Search Binaries
- `search_persistent_entries(applianceId: integer, [hostname: text], [hostnameRegex: text], [path: text], [pathRegex: text], [cmdline: text], [cmdlineRegex: text], [signatureCn: text], [signatureCnRegex: text], [persistencePath: text], [persistencePathRegex: text], [persistenceType: text], [persistenceTypeRegex: text], [name: text], [nameRegex: text], [sha256: text], [sha1: text], [md5: text], [createdFrom: datetime], [createdTo: datetime], [deletedFrom: datetime], [deletedTo: datetime], limit: integer, [offset: integer])` — Search Persistent Entries
- `search_persistent_entries_category(category: select, applianceId: integer, [hostname: text], [hostnameRegex: text], [pathRegex: text], [cmdlineRegex: text], [signatureCn: text], [signatureCnRegex: text], [persistencePath: text], [persistencePathRegex: text], [persistenceType: text], [persistenceTypeRegex: text], [name: text], [nameRegex: text], [sha256: text], [sha1: text], [md5: text], [path: text], [cmdline: text], [createdFrom: datetime], [createdTo: datetime], [deletedFrom: datetime], [deletedTo: text], limit: integer, [offset: integer])` — Search Persistent Entries by Category
- `search_user_accesslogs(applianceId: integer, [username: text], [usernameRegex: text], [logonEventTimeFrom: datetime], [logonEventTimeTo: datetime], [logoffEventTimeFrom: datetime], [logoffEventTimeTo: datetime], limit: integer, [offset: integer])` — Search User Access Logs
- `send_isolation_action(applianceId: integer, edrUuid: text, isolationAction: select, [toWhitelist: text], [power: select], [persist: checkbox])` — Send Isolation Action
- `set_event_status(id: integer, status: select, [oldStatus: text])` — Set an event status
- `start_offline_forensic(edrUuid: text, applianceId: integer, [persist: checkbox], [processes: checkbox], [startup: checkbox], [disk: checkbox], [privacy: checkbox], [advanced: checkbox], [commands: checkbox], [yara: checkbox], [forensic: checkbox], [diskPaths: object], [extensions: object])` — Start Offline Forensic
- `stop_current_scan(edrUuid: text, applianceId: integer)` — Stop Current Scan
- `stop_offline_forensic(edrUuid: text, applianceId: integer)` — Stop Offline Forensic
- `update_endpoints_tags(edrUuidList: object, tags: text)` — Update Endpoints Tags
- `update_filter(filterId: text, name: text, lvlmin: integer, lvlmax: integer, description: text, [tag: text], [deviceName: text], [path: text], [cmdline: text], [sha256: text], [eventName: text], [egKBId: text], [module: select])` — Update Filter


### `windows-defender-atp` v3.0.0 _(installed, ingestion)_
_Microsoft Defender For Endpoints_

Microsoft Defender For Endpoints is a unified platform for preventative protection, post-breach detection, automated investigation, and response. This connector facilitates the automated operations related to files, machines, IP, Domain, actor etc.

**35 operation(s)**:

_investigation_
- `advanced_hunting(Query: text)` — Run Advanced Hunting Query
- `collect_investigation_package(id: text, Comment: text)` — Collect Investigation Package
- `collect_investigation_package_link(id: text)` — Get Investigation Package SAS URI
- `delete_indicator(id: text)` — Delete Indicator
- `get_alert_by_id(id: text)` — Get Alert by ID
- `get_alert_list([status: select], [severity: select], [category: select], [incidentId: integer], [alertCreationTime: datetime], [$filter: text], [$top: integer], [expand_properties: checkbox])` — Get Alert List
- `get_alert_related_domain(id: text)` — Get Domains by Alert
- `get_alert_related_file(id: text)` — Get Files by Alert
- `get_alert_related_ip(id: text)` — Get IPs by Alert
- `get_alert_related_machine(id: text)` — Get Machines by Alert
- `get_domain_related_alerts(id: text)` — Get Domain Related Alerts
- `get_domain_related_machines(id: text)` — Get Domain Related Machines
- `get_domain_statistics(id: text)` — Get Domain Statistics
- `get_file_info(id: text)` — Get File Information
- `get_file_related_alerts(id: text)` — Get File Related Alerts
- `get_file_related_machines(id: text)` — Get File Related Machines
- `get_file_statistics(id: text)` — Get File Statistics
- `get_indicator_list([$filter: text], [$top: integer])` — Get Indicator List
- `get_ip_related_alerts(id: text)` — Get IP Related Alerts
- `get_ip_statistics(id: text)` — Get IP Statistics
- `get_machine_action(id: text)` — Get Machine Action
- `get_machine_action_collection_list([$filter: text], [$top: integer])` — Get Machine Action List
- `get_machine_alerts(id: text)` — Get Machine Alerts
- `get_machine_by_id(id: text)` — Get Machine By ID
- `get_machine_info_ip(timestamp: datetime, key: text)` — Find Machine Information by IP
- `get_machine_list([$filter: text], [$top: integer])` — Get Machines List
- `get_machine_logged_user(id: text)` — Get Machine Logged on Users
- `isolate_machine(id: text, Comment: text, [IsolationType: select])` — Isolate Machine
- `offboard_machine(id: text, Comment: text)` — Offboard Machine
- `remove_app_restriction(id: text, Comment: text)` — Remove Application Restriction
- `remove_isolation(id: text, Comment: text)` — Remove Isolation
- `restrict_app(id: text, Comment: text)` — Restrict Application Execution
- `run_antivirus_scan(id: text, Comment: text, ScanType: select)` — Run Antivirus Scan
- `submit_indicator(indicatorValue: text, indicatorType: select, action: select, [expirationTime: datetime], title: text, [severity: select], description: text, [generateAlert: checkbox], [recommendedActions: text])` — Submit Indicator
- `update_alert(id: text, classification: select, status: select, [comment: text], [assignedTo: text])` — Update Alert


---

## Enrichment

### `dnstools` v1.0.0 _(installed)_
_DNSTools_

Perform investigative actions like DNS Lookup and Reverse DNS Lookup

**2 operation(s)**:

_investigation_
- `dns_lookup(domain: text, [qtype: select])` — DNS Lookup
- `reverse_dns_lookup(ip: text)` — Reverse DNS Lookup


### `domain-analysis` v1.0.0 _(installed)_
_Domain Analysis_

Whois for IPs, Domains and ASNs in addition to DGA detection and domain popularity lookup

**4 operation(s)**:

- `analyze_domain(domain: text)` — Analyze Domain
- `get_domain_popularity(domain: text, [list_date: datetime])` — Get Domain Popularity
- `get_domain_report(domain: text)` — Get Domain Report
- `whois(input_value: text)` — Whois


---

## Exploitation

### `empire` v1.0.0 _(installed)_
_Empire_

Empire is a pure PowerShell post-exploitation agent built on cryptologically-secure communications and a flexible architecture. This connector facilitates automated operations like get listeners, get agents, execute modules, get stagers etc.

**16 operation(s)**:

_investigation_
- `create_listener(type: text, name: text, [additional: json])` — Create Listener
- `create_stager(stager_name: text, listener: text, [additional: json])` — Create Stager
- `execute_module(module_name: text, [agent: text], [additional: json])` — Execute Modules
- `get_agent_results([agent_name: text])` — Get Agent Results
- `get_agents(option: select, [value: text])` — Get Agents
- `get_credentials()` — Get Credentials
- `get_listener_options([listener_type: text])` — Get Listener Options
- `get_listeners(option: select, [value: text])` — Get Listeners
- `get_stagers(option: select, [value: text])` — Get Stagers
- `get_stale_agents()` — Get Stale Agents
- `remove_agent_results([agent_name: text], [all_agent: checkbox])` — Remove Agent Results
- `run_shell_command_on_agent([agent_name: text], [command: text], [all_agents: checkbox])` — Execute Shell Command
- `search_module(option: select, [value: text])` — Get/Search Modules

_remediation_
- `remove_agent([remove_option: select])` — Remove Agent
- `terminate_agent([agent_name: text], [all_agents: checkbox])` — Terminate Agent
- `terminate_listener([listener_name: text], [all_listener: checkbox])` — Terminate Listener


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


### `cisco-catalyst` v1.0.0 _(installed)_
_Cisco Catalyst_

Get information about the configuration, version and perform action like configure system VLAN on a Cisco Catalyst switch

**3 operation(s)**:

_containment_
- `configure_vlan(ip_macaddress: text, vlan_id: integer, override_trunk: checkbox, [ping_ip: checkbox])` — Configure VLAN

_investigation_
- `get_config()` — Get Configuration
- `get_version()` — Get Version


### `cisco-firepower` v3.0.2 _(installed)_
_Cisco Firepower_

Cisco Firepower is your administrative nerve center for managing critical Cisco network security solutions. It provides a complete and unified management of firewalls, application control, intrusion prevention, URL filtering, and advanced malware protection.

**6 operation(s)**:

_containment_
- `assign_policy_to_device([domain_name: text], policy_name: text, policy_id: text, device_id: text)` — Assign Policy To Device
- `block_ip([domain_name: text], network_group_object: text, ip: text)` — Block IP

_investigation_
- `delete_access_policy([domain_name: text], objectId: text)` — Delete Access Policy
- `get_policy([domain_name: text], [limit: integer], [offset: integer])` — List Access Policy
- `list_device([domain_name: text], [limit: integer], [offset: integer])` — List Device

_remediation_
- `unblock_ip(domain_name: text, network_group_object: text, ip: text)` — Unblock IP


### `cisco-meraki-mx-l3` v1.0.0 _(installed)_
_Cisco Meraki MX L3 Firewall_

Cisco Meraki MX L3 Firewall gives administrators complete control over the users, content, and applications on their network. This connector facilitates automated operations to fetch firewall rules, update the firewall rules etc.

**2 operation(s)**:

_investigation_
- `get_network_appliance_firewall_rules(networkId: text)` — Get Network Appliance Firewall L3 Firewall Rules
- `update_network_appliance_firewall_rules(networkId: text, policy: text, protocol: text, srcCidr: text, destCidr: text, [srcPort: text], [destPort: text], [comment: text], [syslogEnabled: checkbox])` — Update Network Appliance Firewall L3 Firewall Rules


### `cisco-meraki-mx-l7-firewall` v1.1.0 _(installed)_
_Cisco Meraki MX L7 Firewall_

Cisco Meraki MX L7 Firewall gives administrators complete control over the users, content, and applications on their network. This connector facilitates automated operations to fetch firewall rules, update the firewall rules etc.

**3 operation(s)**:

_investigation_
- `get_network_firewall_rules(networkId: text)` — Get Network L7 Firewall Rules
- `get_network_firewall_rules_application_categories(networkId: text)` — Get Network L7 Firewall Rules Application Categories
- `update_network_firewall_rules(networkId: text, rules: json)` — Update Network L7 Firewall Rules


### `cisco-meraki-mx-vpn-firewall` v1.0.0 _(installed)_
_Cisco Meraki MX VPN Firewall_

Cisco Meraki MX VPN Firewall gives administrators the ability to add firewall rules to restrict the traffic flow through the VPN tunnel for a Cisco Meraki MX Security Appliance. This connector facilitates automated operations to fetch firewall rules, update the firewall rules etc.

**2 operation(s)**:

_investigation_
- `get_vpn_firewall_rules(organizationId: text)` — Get Organization VPN Firewall Rules
- `update_organization_firewall_rules(organizationId: text, rules: json)` — Update Organization VPN Firewall Rules


### `fortinet-fortios` v3.0.0 _(installed)_
_Fortinet FortiOS_

FortiOS connector uses rest apis to perform automated operations such as Block IP, Unblock IP, List Blocked IP, Clear IP Block List etc

**16 operation(s)**:

_containment_
- `block_ip(dst_loc: select, inbound_outbound_method: multiselect, src: select, [vdom: text])` — Block IP Address
- `block_url(url: text, web_profile_name: text)` — Block URL
- `quarantine_host(macs: text, [vdom: text])` — Quarantine Host
- `unquarantine_host(macs: text, [vdom: text])` — Unquarantine Host

_investigation_
- `ban_ip(src: select, time_to_live: select, [vdom: text])` — Ban IPs
- `get_address_group(ip_type: select, [address_groups_name: text], [vdom: text])` — Get Address Group
- `get_banned_ips([vdom: text])` — Get Banned IP Addresses
- `get_blocked_ip(policy_index: integer, [format: text], [vdom: text])` — Get Blocked IP Addresses
- `get_blocked_urls(web_profile_name: text, [vdom: text])` — Get Blocked URLs
- `get_policy([policy_index: integer], [vdom: text])` — Get Policy
- `get_quarantine_hosts([vdom: text])` — Get Quarantine Hosts
- `get_url_profiles([web_profile_name: text], [vdom: text])` — Get Web Filter Profiles
- `remove_banned_ips(src: select, [vdom: text])` — Remove Banned IPs

_remediation_
- `purge_ip_block_list(policy_index: integer, [inbound_outbound_method: multiselect], [vdom: text])` — Purge IP Block List
- `unblock_ip(dst_loc: select, inbound_outbound_method: multiselect, src: select, [vdom: text])` — Unblock IP Address
- `unblock_url(url: text, web_profile_name: text)` — Unblock URL


### `fortinet-fortiweb` v1.0.0 _(installed)_
_Fortinet FortiWeb_

Fortinet’s Web Application Firewall, protects your business-critical web applications from attacks that target known and unknown vulnerabilities

**14 operation(s)**:

_investigation_
- `delete_active_users(policy: text, [profile: text], [rule: text], [username: text], [type: select])` — Delete Active Users
- `delete_client_info(client_id: text)` — Delete Client Information
- `get_active_users([type: select], [policy_id: text])` — Get Active Users
- `get_all_physical_servers()` — Get All Physical Servers
- `get_all_virtual_servers()` — Get All Virtual Servers
- `get_anomaly_policy_info(policy_name: text)` — Get Anomaly Policy Information
- `get_blocked_ips()` — Get Blocked IPs
- `get_blocked_users([type: select], [policy_name: text])` — Get Blocked Users
- `get_client_info([search_type: select], [cur_page: integer], [day: select])` — Get Client Information
- `get_server_policy_status()` — Get Server Policy Status
- `get_server_policy_traffic(policy_name: select)` — Get Server Policy Traffic
- `restore_threat_score(client_id: text)` — Restore Client Threat Score
- `unblock_ips(policy_name: text, [ip_list: text], [release_all: checkbox])` — Unblock IPs
- `unblock_users([type: select], [policy_name: text], [release_all: checkbox], [blocked_users: json])` — Unblock Users


### `imperva-incapsula` v1.0.0 _(installed)_
_Imperva Incapsula_

Imperva Incapsula provide web application security, DDoS mitigation. This connector facilitates automated operations like get site status, get site report, list site, modify site (security & ACL) config, delete site and etc.

**19 operation(s)**:

_investigation_
- `get_client_app_info()` — Get Client Applications Info
- `get_domain_approver_email(domain: text)` — Get Domain Approver E-mail IDs
- `get_incapsula_ip_ranges()` — Get IP Ranges
- `get_login_protect_users(account_id: integer)` — Get Login Protect Users
- `get_site_report(site_id: integer, format: select, time_range: select)` — Get Site Report
- `get_site_status(site_id: integer)` — Get Site Status
- `get_stats(site_id: text, time_range: select, stats: multiselect, [account_id: integer])` — Get Statistics
- `get_visits(site_id: integer, [time_range: select], [page_num: integer], [page_size: integer], [ips: text])` — Get Visits
- `list_sites([account_id: integer], [page_size: integer], [page_num: integer])` — List Sites
- `purge_hostname(host_name: text)` — Purge Hostname
- `purge_resource(site_id: integer, [should_purge_all_site_resources: checkbox])` — Purge Resource
- `purge_site_cache(site_id: integer)` — Purge Site Cache

_miscellaneous_
- `add_site(domain: text, [send_site_setup_emails: checkbox], [force_ssl: checkbox])` — Add Site
- `delete_site(site_id: integer)` — Delete Site
- `modify_site_acl_config(site_id: integer, acl_rule_id: select)` — Modify Site ACL Configuration
- `modify_site_config(site_id: integer, param: select)` — Modify Site Configuration
- `modify_site_logs_level(site_id: integer, [log_level: select])` — Modify Site Logs Level
- `modify_site_security_config(site_id: integer, rule_id: select)` — Modify Site Security Configuration
- `modify_whitelist_config(site_id: integer, rule_id: select, [urls: text], [ips: text], [countries: text], [whitelist_id: integer], [delete_whitelist: checkbox])` — Modify or Create Whitelists Configuration


### `palo-alto-networks-panorama` v3.2.0 _(installed)_
_Palo Alto Networks Panorama_

This app integrates with the Palo Alto Networks Firewall to support containment actions like 'block url', 'block application', 'block ip', 'unblock url', 'unblock application' and 'unblock ip'

**11 operation(s)**:

_containment_
- `block_app(app: text, [type_of_commit: select])` — Block Application
- `block_ip(ip: text, [type_of_commit: select])` — Block IP
- `block_url(url: text, [type_of_commit: select])` — Block URL

_investigation_
- `add_host_id_to_quarantine_list(vsys: text, hostid: text, reason: text, source: text, [serialno: text])` — Add Host ID To Quarantine List
- `delete_host_id_from_quarantine_list(hostid: text)` — Delete Host ID From Quarantine List
- `firewall_list()` — Get Connected Firewalls
- `get_application_groups([application_group: text])` — Get Application Groups
- `get_device_groups([device_group: text])` — Get Device Groups

_remediation_
- `unblock_app(app: text, [type_of_commit: select])` — Unblock Application
- `unblock_ip(ip: text, [type_of_commit: select])` — Unblock IP
- `unblock_url(url: text, [type_of_commit: select])` — Unblock URL


### `sophos-xg` v1.0.0 _(installed)_
_Sophos XG Firewall_

Sophos XG Firewall

**10 operation(s)**:

_containment_
- `block_applications(app_list: text)` — Block Applications
- `block_ips(ip_addresses: text)` — Block IP Addresses
- `block_urls(urls: text)` — Block URLs

_investigation_
- `check_policies()` — Check Policies
- `get_blocked_applications()` — Get List of Blocked Application Names
- `get_blocked_ips()` — Get List of Blocked IPs
- `get_blocked_urls()` — Get List of Blocked URLs

_remediation_
- `unblock_applications(app_list: text)` — Unblock Applications
- `unblock_ips(ip_addresses: text)` — Unblock IP Addresses
- `unblock_urls(urls: text)` — Unblock URLs


---

## Firewall and Network Protection

### `akamai-waf` v1.0.2 _(installed)_
_Akamai WAF_

Akamai Web Application Firewall (WAF) is a cloud-based security solution designed to protect web applications from various cyber threats. It acts as a shield between internet traffic and web servers, inspecting incoming requests to detect and block malicious activities

**9 operation(s)**:

_investigation_
- `activate_network_list(networkListId: text, environment: select, [comments: text], [notificationRecipients: text], [siebelTicketId: text])` — Activate Network List
- `append_elements_to_network_list(networkListId: text, list: text)` — Append Elements to Network List
- `create_network_list(name: text, type: select, list: text, [description: text], [contractId: text], [groupId: integer])` — Create Network List
- `delete_element_from_network_list(networkListId: text, element: text)` — Delete an Element from Network List
- `delete_network_by_id(networkListId: text)` — Delete Network by ID
- `get_activation_status_of_network_list(networkListId: text, environment: select)` — Get Activation Status of Network List
- `get_network_by_id(networkListId: text, [extended: checkbox], [includeElements: checkbox])` — Get Network by ID
- `get_network_list([search: text], [listType: select], [extended: checkbox], [includeElements: checkbox])` — Get Network List
- `update_network_list(networkListId: text, name: text, type: select, list: text, syncPoint: integer, [description: text], [extended: checkbox], [includeElements: checkbox])` — Update Network List


### `azure-firewall` v2.0.1 _(installed)_
_Azure Firewall_

Azure Firewall connector helps to protect your Azure Virtual Network resources. It is a fully stateful firewall as a service with built-in high availability and unrestricted cloud scalability.

**18 operation(s)**:

_containment_
- `block_ip(ip_group_name: text, ips: text)` — Block IP

_investigation_
- `delete_firewall(firewall_name: text)` — Delete Firewall
- `delete_firewall_policy(firewall_policy_name: text)` — Delete Firewall Policy
- `delete_firewall_policy_rule_collection(firewall_policy_name: text, rule_collection_group_name: text)` — Delete Firewall Policy Rule Collection Group
- `delete_ip_group(ip_group_name: text)` — Delete Firewall IP Group
- `get_all_ip_group(fetch_using: select)` — Get IP Groups List
- `get_firewall(firewall_name: text)` — Get Firewall
- `get_firewall_policies(fetch_using: select)` — Get Firewall Policies List
- `get_firewall_policy(firewall_policy_name: text)` — Get Firewall Policy
- `get_firewall_policy_rule_collection(firewall_policy_name: text, rule_collection_group_name: text)` — Get Firewall Policy Rule Collection Group
- `get_firewall_policy_rule_collection_groups(firewall_policy_name: text)` — Get Firewall Policy Rule Collection Groups List
- `get_firewalls_list(fetch_using: select)` — Get Firewalls List
- `get_ip_group(ip_group_name: text)` — Get Firewall IP Group
- `get_service_tag(location: text)` — Get Service Tag
- `list_learned_prefixes(firewall_name: text)` — List Learned Prefixes
- `update_firewall_policy_tags(firewall_policy_name: text, tags: json)` — Update Firewall Policy Tags
- `update_firewall_tags(firewall_name: text, tags: json)` — Update Firewall Tags

_remediation_
- `unblock_ip(ip_group_name: text, ips: text)` — Unblock IP


### `azure-front-door-waf` v1.0.0 _(installed)_
_Azure Front Door WAF_

Azure Front Door Service enables you to define, manage, and monitor the global routing for your web traffic by optimizing for best performance and instant global failover for high availability. With Front Door, you can transform your global (multi-region) consumer and enterprise applications into robust, high-performance personalized modern applications, APIs, and content that reach a global audience with Azure.

**6 operation(s)**:

_containment_
- `block_ip(policyName: text, location: text, rule_name: text, rule_priority: integer, ip_address: text, [sku: text])` — Block IP

_investigation_
- `create_or_update_policy(policyName: text, location: text, [customRules: json], [managedRules: json], [policySettings: json], [sku: text], [tags: json])` — Create or Update Policy
- `delete_policy(policyName: text)` — Delete Policy
- `get_policies_list()` — Get Policies List
- `get_policy_details(policyName: text)` — Get Policy Details

_remediation_
- `unblock_ip(policyName: text, rule_name: text, ip_address: text)` — Unblock IP


### `azure-web-application-firewall` v1.0.0 _(installed)_
_Azure Web Application Firewall_

The Azure WAF (Web Application Firewall) integration provides centralized protection of your web applications from common exploits and vulnerabilities. It enables you to control policies that are configured in the Azure Firewall management platform, and allows you to add, delete, or update policies, and also to get details of a specific policy or a list of policies.

**4 operation(s)**:

_investigation_
- `create_or_update_policy(policy_name: text, managedRules: json, [id: text], [location: text], [tags: json], [customRules: json], [policySettings: json])` — Create Or Update Policy
- `delete_policy(policy_name: text)` — Delete Policy
- `get_policy(policy_name: text)` — Get Policy
- `list_policies(option: select)` — Get Policy List


### `checkpoint-management-console` v1.0.0 _(installed)_
_CheckPoint Management Console_

CheckPoint Management Console helps you to configure and view the security policy and objects in a Security Management Server or Multi Domain Server using CLI tools and web-services.

**5 operation(s)**:

_investigation_
- `add_host(name: text, [ip-address: text], [ipv4-address: text], [ipv6-address: text], [interfaces: json], [nat-settings: json], [tags: text], [host-servers: json], [set-if-exists: checkbox], [color: text], [comments: text], [details-level: select], [groups: text], [ignore-warnings: checkbox], [ignore-errors: checkbox])` — Create Host
- `delete_host(params_type: select)` — Delete Host
- `get_host_details(params_type: select)` — Get Host Details
- `get_hosts_list([filter: text], [limit: integer], [offset: integer], [order: text], [show-membership: checkbox], [details-level: select])` — Get Hosts List
- `update_host(params_type: select, [interfaces: json], [ip-address: text], [ipv4-address: text], [ipv6-address: text], [nat-settings: json], [new-name: text], [tags: text], [host-servers: json], [color: text], [comments: text], [details-level: select], [groups: text], [ignore-warnings: boolean], [ignore-errors: boolean])` — Update Host


### `cloudflare-waf` v1.0.0 _(installed)_
_Cloudflare WAF_

Cloudflare Web Application Firewall (WAF) integration allows customers to manage firewall rules, filters, and IP Lists. It also allows to retrieve zones list for each account.

**16 operation(s)**:

_investigation_
- `create_filter([zone_id: text], [description: text], [expression: text], [ref: text], [paused: checkbox])` — Create Filter
- `create_firewall_rule(description: text, [action: select], [products: multiselect], [paused: checkbox], [priority: text], [ref: text], [filter_id: text], [filter_expression: text])` — Create Firewall Rule
- `create_ip_items_list(list_id: text, ip_address: text)` — Create IP Items List
- `create_ip_list(name: text, [description: text])` — Create IP List
- `delete_filter(id: text)` — Delete Filter
- `delete_firewall_rule(id: text)` — Delete Firewall Rule
- `delete_ip_list(list_id: text)` — Delete IP List
- `delete_ip_list_item(list_id: text, items_id: text)` — Delete IP List Items
- `get_ip_list_item(list_id: text, [page: text], [per_page: text])` — Get IP List Items
- `get_ip_lists([page: text], [per_page: text])` — Get IP Lists
- `list_filters([id: text], [description: text], [expression: text], [ref: text], [page: text], [per_page: text])` — List Filters
- `list_firewall_rules([action: text], [description: text], [id: text], [paused: checkbox], [page: text], [per_page: text])` — List Firewall Rules
- `list_zones([match: text], [name: text], [account_name: text], [order: text], [status: text], [direction: text], [page: text], [per_page: text])` — List Zones
- `update_filter(id: text, [zone_id: text], [description: text], [expression: text], [ref: text], [paused: checkbox])` — Update Filter
- `update_firewall_rule(id: text, [description: text], [action: select], [products: multiselect], [paused: checkbox], [priority: text], [ref: text], [filter_id: text])` — Update Firewall Rule
- `update_ip_list_item(list_id: text, ip_address: text)` — Update IP List Items


### `cymulate-web-application-firewall` v1.0.0 _(installed)_
_Cymulate Web Application Firewall - BAS_

The Cymulate Web Application Firewall will validate the configuration, implementation, and efficacy, to ensure that the Web Application Firewall blocks malicious payloads before they get to your Web Application. Technical reports provide analysis of the attacks and actionable mitigation guidance that help security teams to shore up their defenses against web application attacks.

**14 operation(s)**:

_investigation_
- `get_executive_report_results_by_id(id: text)` — Get Executive Report Results By Assessment ID
- `get_technical_report_results(SiteID: text, [skip: integer], [limit: integer])` — Get Technical Report Results
- `get_technical_report_results_by_id(id: text, [skip: integer], [limit: integer])` — Get Technical Report Results By Assessment ID
- `get_waf_assessment_history([fromDate: datetime], [toDate: datetime], [env: text])` — Get WAF Assessment History
- `get_waf_assessment_status([id: text])` — Get WAF Assessment Status
- `get_waf_payload_response(id: text)` — Get WAF Payload Response
- `get_waf_report_results([env: text])` — Get WAF Report Results
- `get_waf_site_ids()` — Get WAF Site IDs
- `get_waf_site_results([env: text])` — Get WAF Site Results
- `get_waf_sites()` — Get WAF Sites
- `get_waf_template_by_id(id: text)` — Get WAF Template By ID
- `get_waf_templates()` — Get WAF Templates
- `launch_waf_assessment(sites: text, templateID: text, [schedule: datetime], scheduleLoop: text)` — Launch WAF Assessment
- `stop_waf_assessment([env: text])` — Stop WAF Assessment


### `fastly-next-gen-waf` v1.0.0 _(installed)_
_Fastly Next-Gen WAF_

Fastly Next-Gen WAF offers advanced web application protection with automated security measures, real-time monitoring, and rapid incident response. It provides robust defense by managing security policies, detecting threats, and enforcing rule sets to protect web applications.

**16 operation(s)**:

_investigation_
- `add_ip_to_allow_list(corporation: text, site_name: text, source: text, [note: text], [expires: datetime])` — Add IP Address to Allow List
- `add_ip_to_block_list(corporation: text, site_name: text, source: text, [note: text], [expires: datetime])` — Add IP Address to Block List
- `get_alert_details(corporation: text, site_name: text, id: text)` — Get Alert Details
- `get_all_site_lists(corporation: text, site_name: text)` — Get All Site Lists
- `get_event_details(corporation: text, site_name: text, id: text)` — Get Event Details
- `get_site_allow_list(corporation: text, site_name: text)` — Get Site Allow List
- `get_site_block_list(corporation: text, site_name: text)` — Get Site Block List
- `get_site_list_by_id(corporation: text, site_name: text, id: text)` — Get Site List Details
- `list_alerts(corporation: text, site_name: text)` — List Alerts
- `list_corps()` — List Corporations
- `list_events(corporation: text, site_name: text, [status: select], [action: select], [ip: text], [tag: text], [since_id: text], [max_id: text], [from: datetime], [until: datetime], [sort: select], [page: integer], [limit: integer])` — List Events
- `list_sites_in_corp(corporation: text, [name: text], [agent_level: select], [page: integer], [limit: integer])` — List Sites in Corporation
- `remove_ip_from_allow_list(corporation: text, site_name: text, id: text)` — Remove IP Address from Allow List
- `remove_ip_from_block_list(corporation: text, site_name: text, id: text)` — Remove IP Address from Block List
- `update_alert(corporation: text, site_name: text, id: text, [long_name: text], [tag_name: text], [interval: integer], [threshold: integer], [block_duration_seconds: integer], [enabled: select], [action: select])` — Update Alert

_management_
- `expire_event_by_id(corporation: text, site_name: text, id: text)` — Expire Event By ID


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

_Configuration_
- `add_to_address_set(address_set: text, object_type: select, object_to_add: text)` — Add an Object to Global Address Set
- `add_to_prefix_list(prefix_list: text, address_to_add: text)` — Add Address(es) to a Prefix List
- `config_action(request_payload: textarea)` — Run Configuration Command
- `delete_from_address_set(address_set: text, object_type: select, object_to_delete: text)` — Delete Object from Global Address Set
- `delete_from_prefix_list(prefix_list: text, address_to_delete: text)` — Delete Address(es) from a Prefix List
- `get_address_set(address_set: text, [get_count: checkbox])` — Get Address Set
- `get_prefix_list(prefix_list: text, [get_count: checkbox])` — Get Prefix List

_information_
- `op_action(command_to_run: select, [method_params: json])` — Run Command


### `netscaler-adc` v1.0.1 _(installed)_
_NetScaler ADC_

The NetScaler appliance is an application switch which performs application-specific traffic analysis to intelligently distribute, optimize, and secure Layer 4-Layer 7 (L4–L7) network traffic for web applications.

**4 operation(s)**:

_investigation_
- `change_acl_resource_state(acl_type: select, aclname: text, action: select)` — Change NetScaler ACL Resource State
- `create_acl_resource(acl_type: select, aclname: text, srcip: text, [destip: text], [aclaction: select], [other_fields: json])` — Create NetScaler ACL Resource
- `delete_acl_resource(acl_type: select, aclname: text)` — Delete NetScaler ACL Resource
- `get_acl_resource(acl_type: select, [aclname: text], [pagesize: integer], [pageno: integer], [other_fields: json])` — Get NetScaler ACL Resource


### `paloalto-firewall` v3.3.0 _(installed)_
_Palo Alto Firewall_

Palo Alto Firewall is serving as a Security Operating Platform for a long time and has been a pioneer in offering cybersecurity services. The Palo Alto Security Operating Platform makes your system and network secured from successful cyber attacks in a highly efficient and automatic way.

**30 operation(s)**:

_Containment_
- `block_app(app: text)` — Block Application
- `block_ip(ip: text)` — Block IP
- `block_url(url: text)` — Block URL

_Remediation_
- `unblock_app(app: text)` — Unblock Application
- `unblock_ip(ip: text)` — Unblock IP
- `unblock_url(url: text)` — Unblock URL

_investigation_
- `add_address_to_specific_group(name: text, ip: text)` — Add IP Address to Address Group
- `create_address(name: text, address_type: select, [description: text])` — Create IP Address Object
- `create_address_group(name: text, address_group: select, [tag: text], [description: text])` — Create Address Group
- `create_external_dynamic_list(name: text, type: select, url: text, [member: text], [description: text])` — Create External Dynamic List
- `create_security_rule(name: text, from: text, to: text, source: text, destination: text, service: text, application: text, action: select, [category: text], [source-user: text], [rule-type: select], [disable: select], [attributes: json])` — Create Security Policy Rule
- `delete_address(name: text)` — Delete IP Address Object
- `delete_address_group(name: text)` — Delete Address Group
- `delete_external_dynamic_list(name: text)` — Delete External Dynamic List
- `delete_security_rule(name: text)` — Delete Security Policy Rule
- `edit_address(name: text, address_type: select, [tag: text], [description: text])` — Update IP Address Object
- `edit_security_rule(name: text, from: text, to: text, source: text, destination: text, service: text, application: text, action: select, [category: text], [source-user: text], [rule-type: select], [disable: select], [attributes: json])` — Update Security Policy Rule
- `get_address_details(name: text)` — Get Specific IP Address Object Details
- `get_address_group(name: text)` — Get Address Group Details
- `get_address_group_list()` — Get All Address Group List
- `get_address_list()` — Get All Address List
- `get_external_dynamic_list()` — Get External Dynamic List
- `list_security_rule([name: text])` — Get All Security Policy Rules List
- `move_security_rule(name: text, where: select)` — Move Security Policy Rule
- `remove_address_from_specific_group(name: text, ip: text)` — Remove IP Address from Address Group
- `rename_address(name: text, newname: text)` — Rename IP Address Object Name
- `rename_address_group(name: text, newname: text)` — Rename Specific Address Group
- `rename_external_dynamic_list(name: text, newname: text)` — Rename External Dynamic List
- `rename_security_rule(name: text, newname: text)` — Rename Security Policy Rule
- `update_external_dynamic_list(name: text, type: select, url: text, [member: text], [description: text])` — Update External Dynamic List


### `sonicwall-firewall` v1.1.0 _(installed)_
_SonicWall Firewall_

SonicWall's advanced firewall appliances with various network and security systems. This connector facilitates seamless communication and data exchange between the SonicWall Firewall and other network elements, providing enhanced security, management, and monitoring capabilities

**10 operation(s)**:

_investigation_
- `add_address_object_to_group(object_type: select, [filter_object_by: select], address_object_name: text)` — Add Address Object to Group
- `create_address_group(object_type: select, address_group_name: text, address_object_name: text)` — Create Address Group
- `create_address_object_configuration(name: text, zone: text, object_type: select)` — Create Address Object
- `delete_address_group(object_type: select, delete_object_by: select)` — Delete Address From Group
- `delete_address_object_configuration(object_type: select, delete_object_by: select)` — Delete Address Object
- `get_address_group(object_type: select, [filter_object_by: select])` — Get Address Group
- `get_address_object_configuration(object_type: select, [filter_object_by: select])` — Get Address Object
- `remove_address_object_from_group(object_type: select, [filter_object_by: select], address_object_name: text)` — Remove Address Object from Group
- `update_address_group(update_type: select, object_type: select, zone: text)` — Update Address in Group
- `update_address_object_configuration(update_type: select, update_object_by: select, object_type: select, zone: text)` — Update Address Object


---

## Forensics and Malware Analysis

### `fireeye-detection-on-demand` v1.0.1 _(installed)_
_FireEye Detection On Demand_

FireEye Detection On Demand is a threat detection service that uncovers harmful objects in the cloud. It delivers flexible file and content scanning capabilities to identify file-borne threats in your cloud, SOC, SIEM or files uploaded to web applications. This connector facilitates the automated operations related to submit files / urls , reports, artifacts.

**6 operation(s)**:

_investigation_
- `get_artifacts(report_id: text, artifacts_type: text, artifacts_uuid: text)` — Get Artifacts
- `get_hashes([hash: text])` — Get File Reputation
- `get_report_url([report_id: text], [report_id: text])` — Get Report URL
- `get_reports([report_id: text], [extended: checkbox])` — Get Report
- `submit_file(attachment_iri: text, [password: text], [parameters: text], [file_extraction: checkbox], [memory_dump: checkbox], [pcap: checkbox])` — Submit File
- `submit_urls([urls: text])` — Submit URLs


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

## Google service

### `google-cloud-translate` v1.0.0 _(installed)_
_Google Cloud Translate_

Google Cloud translation technology to instantly translate texts into more than one hundred languages

**2 operation(s)**:

_investigation_
- `get_supported_languages()` — Get Languages
- `translate_text(input_text: text, target: select, [format: select], [source: select], [model: text])` — Translate Text


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

## IOT

### `berryio` v1.0.1 _(installed)_
_BerryIO_

This Connector allows for GPIO status commands to be sent to BerryIO, a controller for Raspberry Pi

**3 operation(s)**:

_investigation_
- `get_gpio()` — Get GPIO Pin Status

_miscellaneous_
- `set_gpio_mode(pin: integer, mode: text)` — Set GPIO Pin Mode
- `set_gpio_value(pin: integer, value: text)` — Set GPIO Pin Value


---

## IP Information

### `ipinfo` v1.0.0 _(installed)_
_ipinfo.io_

IpInfo.io is used to search the owner, internet provider and location of any website, domain or IP address

**2 operation(s)**:

_investigation_
- `get_geolocation_information(ip_address: text)` — Get Geolocation Information

_miscellaneous_
- `lookup_ip([ip_address: text])` — Lookup IP Address


---

## IT Service

### `google-drive` v1.0.0 _(installed)_
_Google Drive_

Google drive connector can be used to list, add, remove, download and upload files from google drive using playbook.

**5 operation(s)**:

_containment_
- `delete_file(fileId: text)` — Delete File
- `download_file(file_id: text)` — Download File
- `empty_trash()` — Empty Trash
- `upload_file(fileIRI: text, [new_file_name: text])` — Upload File

_investigation_
- `get_all_files([pageSize: integer])` — Get File List


---

## IT Service Management

### `atlassian-confluence-server` v1.0.0 _(installed)_
_Atlassian Confluence Server_

Atlassian Confluence is a team workspace where knowledge and collaboration meet. Create, collaborate, and organize all your work in one place.

**7 operation(s)**:

_investigation_
- `create_content(type: text, space: text, title: text, body: text)` — Create Content
- `create_space(key: text, name: text, description: text)` — Create Space
- `delete_content(contentId: integer)` — Delete Content
- `get_content_list(spaceKey: text, title: text, [expand: text], [limit: integer])` — Get Content List
- `get_content_list_using_cql(cql: text, [cqlcontext: text], [expand: text], [limit: integer])` — Get Content List Using CQL
- `get_spaces_list([type: select], [status: select], [limit: integer])` — Get Spaces List
- `update_content(contentId: integer, version: integer, type: text, [space: text], [title: text], [body: text])` — Update Content


### `axios-assyst` v1.0.0 _(installed)_
_Axios Assyst_

Axios assyst is a comprehensive ITSM platform that supports all ITIL® processes and combines ITSM best practices with modern collaboration features. This connector provides an automated way to create, search, update, and close tickets in Axios Assyst.

**5 operation(s)**:

_investigation_
- `close_ticket(id: text, [archive: checkbox])` — Close Ticket
- `create_ticket(remarks: text, affected_user: json, items: json, category: json)` — Create Ticket
- `get_ticket_details(id: text)` — Get Ticket Details
- `search_tickets(eventStatus: select, [start_time: datetime], [end_time: datetime])` — Search Tickets
- `update_ticket(id: text, eventStatus: select)` — Update Ticket


### `azure-resource-health` v1.0.0 _(installed)_
_Azure Resource Health_

Azure Resource Health helps you diagnose and get support for service problems that affect your Azure resources, it reports on the current and past health of your resources. This connector supports actions related to availability status and events.

**7 operation(s)**:

_investigation_
- `get_availability_status(subscription_id: text, resource_group_name: text, resource_provider_name: text, resource_type: text, resource_name: text, [filter: text])` — Get Availability Status
- `get_availability_status_by_resource_group(subscription_id: text, resource_group_name: text, [filter: text])` — Get Current Availability Status by Resource Group
- `get_availability_status_by_subscription_id(subscription_id: text, [filter: text])` — Get Current Availability Status by Subscription ID
- `get_availability_status_list(subscription_id: text, resource_group_name: text, resource_provider_name: text, resource_type: text, resource_name: text, [filter: text])` — Get Availability Transitions List
- `get_event_list_for_resource(subscription_id: text, resource_group_name: text, resource_provider_name: text, resource_type: text, resource_name: text, [filter: text])` — Get Event List for Resource
- `get_event_list_for_subscription_id(subscription_id: text, [query_start_time: text], [filter: text])` — Get Event List for Subscription ID
- `get_event_list_for_tenant_id([query_start_time: text], [filter: text])` — Get Event List for Tenant ID


### `micro-focus-service-manager` v1.4.0 _(installed)_
_Micro Focus Service Manager_

Micro Focus service manager connector helps you to create incident, update incident, list incidents, get incident, get device list and get device

**16 operation(s)**:

_investigation_
- `create_change(Title: text, Description: richtext, Category: text, Subcategory: text, InitiatedBy: text, Service: text, [AffectedCI: text], ChangeOriginator: text, ChangeCoordinator: text, ReasonForChange: text, [PlannedStart: datetime], [PlannedEnd: datetime], [json_input: json])` — Create Change
- `create_incident(title: text, description: richtext, impact: select, urgency: select, category: text, service: text, [affected_ci: text], [subcategory: text], [area: text], [assignment_group: text], [source: select], [contact_person: text], [outage_start_time: text], [outage_end_time: text], [assignee: text], [service_recipient: text], [location: text], [solution: text], [json_input: json])` — Create Incident
- `create_rf(BriefDescription: text, Description: text, Category: text, Subcategory: text, AssignedTo: text, AssignedGroup: text, Impact: text, Priority: text, Urgency: text, ProductType: text, RequestorName: text)` — Create RF - Request Fulfillment Ticket
- `delete_an_attachment(incident_id: text, attachment_id: text)` — Delete Attachment
- `download_an_attachment(incident_id: text, attachment_id: text)` — Download Attachment
- `get_change_request(change_request_id: text)` — Get Change Request
- `get_device(config_item: text)` — Get Device
- `get_device_list([query: text], [sort: text], [start: integer], [count: integer], [view: select])` — Get Device List
- `get_incident(incident_id: text)` — Get Incident
- `get_rf(rf_id: text)` — Get RF - Request Fulfillment Ticket
- `list_changes([query: text], [sort: text], [start: integer], [count: integer], [view: select])` — Get Change List
- `list_incidents([query: text], [sort: text], [start: integer], [count: integer], [view: select])` — Get Incident List
- `retrieve_attachment_information(incident_id: text)` — Retrieve Attachment Information
- `update_change(change_id: text, ClosureCode: integer, SubClosureCode: text, ClosingComments: text, Phase: text, [PlannedStart: datetime], [PlannedEnd: datetime])` — Update Change
- `update_incident(incident_id: text, [title: text], [description: richtext], [impact: select], [urgency: select], [category: text], [service: text], [affected_ci: text], [subcategory: text], [area: text], [assignment_group: text], [source: select], [contact_person: text], [outage_start_time: text], [outage_end_time: text], [assignee: text], [service_recipient: text], [location: text], [solution: text], [json_input: text])` — Update Incident
- `update_rf_attachment(rf_id: text, attachment_name: text, msg_body: textarea)` — Update RF - Request Fulfillment Ticket for an attachment


### `middesk` v1.0.0 _(installed)_
_Middesk_

Middesk is an identity platform that automates business verification and underwrites decisions. It also provides data on businesses and notifies service providers of changes to its customer base allowing them to form an accurate picture of their customers and offer the critical products their customers need to establish,operate, and maintain their businesses.

**4 operation(s)**:

_investigation_
- `create_business(name: text, [tin: text], [website: text], [phone_numbers: text], [external_id: text], [orders: text], [tags: text], [formation: text], [names: json], addresses: json, [people: json])` — Create Business
- `get_business(id: text)` — Get Business
- `get_businesses_list([page: text], [per_page: text])` — Get Businesses List
- `update_business(id: text, [name: text], [status: select], [assignee_id: text], [website: text], [external_id: text], [phone_numbers: text], [addresses: json], [people: json])` — Update Business


### `solarwinds-pingdom` v1.0.0 _(installed, ingestion)_
_Solarwinds Pingdom_

Solarwinds Pingdom makes your websites faster and more reliable with easy-to-use web performance and digital experience monitoring.

**5 operation(s)**:

_investigation_
- `get_alerts_list([checkids: text], [from: datetime], [to: datetime], [status: text], [userids: text], [via: text], [limit: integer], [offset: integer], [fetch_all_records: checkbox])` — Get Alerts List
- `get_checks_list([include_severity: checkbox], [include_tags: checkbox], [showencryption: checkbox], [tags: text], [limit: integer], [offset: integer])` — Get Checks List
- `get_raw_test_results_list(checkid: text, [from: datetime], [to: datetime], [maxresponse: integer], [minresponse: integer], [probes: text], [status: text], [limit: integer], [offset: integer])` — Get Raw Test Results List
- `get_result_of_analysis(analysisid: text, checkid: text)` — Get Result of Analysis
- `get_root_cause_analysis(checkid: text, [from: datetime], [to: datetime], [limit: integer], [offset: integer])` — Get Root Cause Analysis


### `ssp-portal` v1.0.0 _(installed)_
_SSP Portal_

Connector for the ExxonMobil Self-Service Portal (SSP) to manage On-Premises Port Opening Requests (PORs).

**3 operation(s)**:

_investigation_
- `get_por(por_id: integer)` — Get POR
- `get_pors(porsType: text)` — Get PORs
- `make_http_request(method: select, endpoint: text, [payload: json])` — Make HTTP Request


---

## IT Service Management,Network Security,Compliance and Reporting

### `tcp-wave` v1.0.0 _(installed)_
_TCP Wave_

TCPWave offers automated DDI (DNS, DHCP, IPAM) workflow management, providing significant benefits to large-scale organizations. It reduces manual tasks, enhances IT productivity, and enables a focus on strategic initiatives that drive business growth. By standardizing network management processes, TCPWave enforces best practices and facilitates rapid, scalable service delivery.

**3 operation(s)**:

_investigation_
- `check_object_exists(ip_address: text, organization_name: text)` — Check Object Exists
- `get_network_details_by_ipaddress(ip_address: text)` — Get Network Details by IP Address
- `get_object_details_by_ipaddress(ip_address: text)` — Get Object Details By IP Address


---

## IT Services

### `aws-commands` v1.1.0 _(installed)_
_AWS Commands_

AWS Commands are used to run AWS native commands for AWS resources configurations directly from FortiSOAR.

**34 operation(s)**:

_containment_
- `add_network_acl_rule([assume_role: checkbox], network_acl_id: text, egress_rule: select, ip_address: text, rule_action: select, rule_number: text)` — Add Network ACL Rule
- `add_security_group_to_instance([assume_role: checkbox], instance_id: text, group_list: text)` — Add Security Group To Instance
- `authorize_egress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Authorize Egress
- `authorize_ingress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Authorize Ingress
- `create_network_acl([assume_role: checkbox], vpc_id: text)` — Create Network ACL
- `create_security_group([assume_role: checkbox], group_name: text, description: text)` — Create Security Groups
- `delete_network_acl([assume_role: checkbox], network_acl_id: text)` — Delete Network ACL
- `delete_network_acl_rule([assume_role: checkbox], network_acl_id: text, egress_rule: select, rule_number: text)` — Delete Network ACL Rule
- `revoke_egress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Revoke Egress
- `revoke_ingress([assume_role: checkbox], security_group_id: text, ip_permissions: text)` — Revoke Ingress

_investigation_
- `describe_instance([assume_role: checkbox], instance_id: text)` — Get Instance Details
- `describe_network_acls([assume_role: checkbox], [network_acl_ids: text], [filters: text])` — Get Details of Network ACLs
- `describe_user([assume_role: checkbox], username: text)` — Get User Details
- `generic_command(command: text, [optional_parameters: text])` — Execute AWS Command
- `get_details_for_all_images([assume_role: checkbox], [image_ids: text], [executable_users: text], [owners: text], [filters: text])` — Get AMIs Detail
- `get_details_of_security_group([assume_role: checkbox], security_group_id: text)` — Get Details of Security Group
- `get_security_groups([assume_role: checkbox])` — Get Security Groups

_miscellaneous_
- `add_tag_to_instance([assume_role: checkbox], instance_id: text, tag_key: text, tag_value: text)` — Add Instance Tag
- `attach_instance_to_auto_scaling_group([assume_role: checkbox], autoscaling_group_name: text, instance_id: text)` — Attach Instance To Auto Scaling Group
- `attach_volume([assume_role: checkbox], volume_id: text, device_name: text, instance_id: text)` — Attach Volume
- `deregister_instance_from_elb([assume_role: checkbox], elb_name: text, instance_id: text)` — Deregister Instance from ELB
- `detach_instance_from_autoscaling_group([assume_role: checkbox], autoscaling_group_name: text, instance_id: text)` — Detach Instance From Auto Scaling Group
- `launch_instance([assume_role: checkbox], image_id: text, instance_type: select, maxcount: integer, mincount: integer, [subnetid: text], device_name: text, delete_on_termination: checkbox, [security_groups_list: text], [purpose: text], [customer_name: text], [terminate_by_date: text])` — Launch Instance
- `reboot_instance([assume_role: checkbox], instance_id: text)` — Reboot Instance
- `register_instance_to_elb([assume_role: checkbox], elb_name: text, instance_id: text)` — Register Instance To ELB
- `snapshot_volume([assume_role: checkbox], volume_id: text, description: text)` — Capture Volume Snapshot
- `start_instance([assume_role: checkbox], instance_id: text, [description: text])` — Start Instance
- `stop_instance([assume_role: checkbox], instance_id: text)` — Stop Instance
- `terminate_instance([assume_role: checkbox], instance_id: text)` — Terminate Instance

_remediation_
- `delete_security_group([assume_role: checkbox], security_group_id: text)` — Delete Security Groups
- `delete_volume([assume_role: checkbox], volume_id: text)` — Delete Volume
- `detach_volume([assume_role: checkbox], volume_id: text, device_name: text, instance_id: text, force: checkbox)` — Detach Volume
- `revoke_all_active_sessions(roleName: text)` — Revoke All Active Sessions

- `instance_api_termination([assume_role: checkbox], instance_id: text, operation: select)` — Instance API Termination 


### `azure-blob-storage` v1.1.0 _(installed)_
_Azure Blob Storage_

Azure Blob Storage is Microsoft's object storage solution for the cloud. Blob Storage is optimized for storing massive amounts of unstructured data. Azure Blob Storage stores text and binary data as objects in the cloud. This connector helps you to perform REST operations for working with blobs in the Blob service.

**9 operation(s)**:

_investigation_
- `abort_copy_blob([container_name: text], blob_name: text, copy_id: text)` — Abort Copy Blob
- `copy_blob(source_container_name: text, blob_name: text, destination_container_name: text)` — Copy Blob
- `create_blob([container_name: text], blob_name: text, input: select, [timeout: text])` — Create Blob
- `delete_blob([container_name: text], blob_name: text)` — Delete Blob
- `get_blob([container_name: text], blob_name: text)` — Get Blob
- `get_blob_metadata([container_name: text], blob_name: text)` — Get Blob Metadata
- `get_blob_properties([container_name: text], blob_name: text)` — Get Blob Properties
- `get_blob_tags([container_name: text], blob_name: text)` — Get Blob Tags
- `list_blob([container_name: text])` — List Blobs


### `azure-kubernetes-services` v1.0.0 _(installed)_
_Azure Kubernetes Services_

Deploy and manage containerized applications with a fully managed Kubernetes. This connector facilitates the automated operations related to managed cluster.

**8 operation(s)**:

_investigation_
- `create_managed_cluster(resourceGroupName: text, subscriptionId: text, resourceName: text, location: text, [additional_fields: json])` — Create Managed Cluster
- `delete_managed_cluster(resourceGroupName: text, subscriptionId: text, resourceName: text)` — Delete Managed Cluster
- `get_command_details(commandId: text, resourceGroupName: text, subscriptionId: text, resourceName: text)` — Get Command Details
- `get_managed_cluster(resourceGroupName: text, subscriptionId: text, resourceName: text)` — Get Managed Cluster
- `managed_cluster_actions(action: select, resourceGroupName: text, subscriptionId: text, resourceName: text)` — Managed Cluster Actions
- `run_command(resourceGroupName: text, subscriptionId: text, resourceName: text, command: text, [additional_fields: json])` — Run Command
- `update_managed_cluster(resourceGroupName: text, subscriptionId: text, resourceName: text, location: text, [additional_fields: json])` — Update Managed Cluster

_investigation _
- `get_managed_clusters_list(subscriptionId: text)` — Get Managed Clusters List


### `azure-notification-hub` v1.0.0 _(installed)_
_Azure Notification Hub_

Azure Notification Hubs provide an easy-to-use and scaled-out push engine that allows you to send notifications to any platform (iOS, Android, Windows, Kindle, Baidu, etc.) from any backend (cloud or on-premises).

**4 operation(s)**:

_investigation_
- `create_notification_hub(subscription_id: text, resource_group_name: text, namespace_name: text, name: text, location: text, [tags: json])` — Create Notification Hub
- `delete_notification_hub(subscription_id: text, resource_group_name: text, namespace_name: text, name: text)` — Delete Notification Hub
- `list_notification_hubs(subscription_id: text, resource_group_name: text, namespace_name: text)` — Get Notification Hubs List
- `update_notification_hub(subscription_id: text, resource_group_name: text, namespace_name: text, name: text, [location: text], [tags: json])` — Update Notification Hub


### `azure-storage` v1.0.0 _(installed)_
_Azure Storage_

Deploy and manage storage accounts and blob services. This connector facilitates the automated operations related to storage account, blob services and blob containers.

**12 operation(s)**:

_investigation_
- `create_blob_container(accountName: text, containerName: text, resourceGroupName: text, subscriptionId: text, [additional_fields: json])` — Create Blob Container
- `delete_blob_container(accountName: text, containerName: text, resourceGroupName: text, subscriptionId: text)` — Delete Blob Container
- `delete_storage_account(accountName: text, resourceGroupName: text, subscriptionId: text)` — Delete Storage Account
- `get_blob_container(accountName: text, containerName: text, resourceGroupName: text, subscriptionId: text)` — Get Blob Container
- `get_blob_service_properties(accountName: text, resourceGroupName: text, subscriptionId: text)` — Get Blob Service Properties
- `get_storage_account(accountName: text, resourceGroupName: text, subscriptionId: text)` — Get Storage Account
- `set_blob_service_properties(accountName: text, resourceGroupName: text, subscriptionId: text, [additional_fields: json])` — Set Blob Service Properties
- `update_blob_container(accountName: text, containerName: text, resourceGroupName: text, subscriptionId: text, [additional_fields: json])` — Update Blob Container
- `update_storage_account(accountName: text, resourceGroupName: text, subscriptionId: text, [additional_fields: json])` — Update Storage Account

_investigation _
- `list_blob_containers(accountName: text, resourceGroupName: text, subscriptionId: text, [$filter: text], [$include: text], [$maxpagesize: text])` — List Blob Containers
- `list_blob_services(accountName: text, resourceGroupName: text, subscriptionId: text)` — List Blob Services
- `list_storage_accounts(subscriptionId: text)` — List Storage Accounts


### `azure-storage-table` v1.0.0 _(installed)_
_Azure Storage Table_

Azure Table storage is a service that stores non-relational structured data (also known as structured NoSQL data) in the cloud, providing a key/attribute store with a schemaless design. this connector helps you to create, update, delete, query on azure storage table.

**7 operation(s)**:

_investigation_
- `create_table(table_name: text)` — Create Table
- `delete_entity_table(table_name: text, partition_key: text, row_key: text)` — Delete Entity Into Table
- `delete_table(table_name: text)` — Delete Table
- `insert_entity_table(table_name: text, partition_key: text, row_key: text, entity_fields: json)` — Insert Entity Into Table
- `query_entity_table(table_name: text, [partition_key: text], [row_key: text], [query_filter: text], [property_names: text])` — Query Entity Into Table
- `query_table([query_filter: text], [records_limit: text])` — Query Table
- `update_entity_table(table_name: text, partition_key: text, row_key: text, entity_fields: json)` — Update Entity Into Table


### `bmcremedy` v1.5.0 _(installed)_
_BMC Remedy AR System_

BMC Remedy Action Request System (BMC Remedy AR System) enables you to automate a broad range of business solutions, from service desk call tracking to inventory management to integrated systems management.

**14 operation(s)**:

_investigation_
- `add_work_info([management: select], work_log_type: text, detailed_description: text)` — Add Work Info
- `create_change_request(first_name: text, last_name: text, description: text, impact: text, urgency: text, status: text, risk_level: text, change_type: text, location_company: text, [additional_fields: json])` — Create Change Management Request
- `create_incident(first_name: text, last_name: text, description: text, impact: text, urgency: text, status: text, reported_source: text, service_type: text, [additional_fields: json])` — Create Incident
- `create_task(TaskName: text, Summary: text, TaskType: select, Status: select, Priority: select, [impact: text], [urgency: text], [RootRequestID: text], [RootRequestName: text], [RootRequestFormName: text], [RootRequestMode: select], [Location Company: text], [Support Company: text], [Assignee Organization: text], [Assignee Group: text], [Assignee: text], [Notes: text], [additional_fields: json])` — Create Task
- `create_work_order(First Name: text, Last Name: text, Customer Company: text, Customer Person ID: text, [Customer First Name: text], [Customer Last Name: text], [Summary: text], [Detailed Description: text], [Status: select], [Priority: select], [Work Order Type: select], [Location Company: text], [additional_fields: json])` — Create Work Order
- `get_all_change_mgmt_requests([offset: integer], [limit: integer], [sort: text])` — Get All Change Management Requests
- `get_all_incidents([limit: integer], [offset: integer], [sort: text])` — Get All Incidents
- `get_change_request(infrastructure_change_id: text)` — Get Change Management Request
- `get_incident_details(incident_number: text)` — Get Incident Details
- `query_change_request(filter_string: select, [limit: integer], [offset: integer], [sort: text], [return_fields: text])` — Query Change Request
- `query_remedy_incident([filter_string: select], [limit: integer], [offset: integer], [sort: text], [return_fields: text])` — Query Remedy Incident
- `update_change_request(chng_req_id: text, [first_name: text], [last_name: text], [description: text], [impact: text], [urgency: text], [status: text], [change_type: text], [location_company: text], [additional_fields: json])` — Update Change Management Request
- `update_incident(inc_request_id: text, [first_name: text], [last_name: text], [description: text], [impact: text], [urgency: text], [status: text], [reported_source: text], [service_type: text], [additional_fields: json])` — Update Incident
- `upload_attachment_to_incident(incident_id: text, file_iri: file, [z1D_Details: text], [z1D_WorklogDetails: text], [z1D_View_Access: text], [Detailed Description: text])` — Upload Attachment to Incident


### `box` v1.0.0 _(installed)_
_Box_

Box is an enterprise content management platform that solves simple and complex challenges, from sharing and accessing files

**13 operation(s)**:

_investigation_
- `create_folder(name: text, parent_id: text, [other_fields: multiselect])` — Create Folder
- `create_group(name: text, [description: text], [provenance: text], [external_sync_identifier: text], [invitability_level: text], [member_viewability_level: text])` — Create Group
- `create_user(name: text, login: text, [job_title: text], [phone: text], [address: text], [status: text], [other_fields: multiselect])` — Create User
- `delete_user(user_id: text, [notify: checkbox], [force: checkbox])` — Delete User
- `download_file(file_id: text)` — Download File
- `get_current_user()` — Get Current User
- `get_file_information(file_id: text)` — Get File Information
- `get_folder_information(folder_id: text, [other_fields: multiselect])` — Get Folder Information
- `get_group(id: text)` — Get Group
- `get_user(user_id: text, [other_fields: multiselect])` — Get User
- `move_folder(folder_id: text, parent_id: text)` — Move Folder
- `update_user(user_id: text, [name: text], [language: text], [job_title: text], [phone: text], [address: text], [status: text], [other_fields: multiselect])` — Update User
- `upload_file(name: text, iri: text, parent_id: text)` — Upload File


### `easyvista` v1.0.0 _(installed)_
_EasyVista_

EasyVista Service Manager manages the entire process of designing, managing and delivering IT services. This connector facilitates operations like get employee list, get asset list

**7 operation(s)**:

_investigation_
- `get_asset(asset_id: integer)` — Get Asset
- `get_employee(employee_id: integer)` — Get Employee
- `get_manufacturer(manufacturer_id: integer)` — Get Manufacturer
- `list_assets([max_rows: integer], [sort: text], [fields: text])` — Get Asset List
- `list_employees([max_rows: integer], [sort: text], [fields: text])` — Get Employee List
- `list_manufacturers([max_rows: integer], [sort: text])` — Get Manufacturer List
- `search_query(resource: select, search_by: select)` — Search Query


### `goanywhere` v1.0.0 _(installed)_
_GoAnywhere_

GoAnywhere MFT is a secure file transfer solution that organizations use to exchange their data safely. The solution helps organizations automate their data transfers, centralize file transfer activity, monitor file transfers and user access. This connector facilitates automated operation related to File Transfer Summary, Active Sessions Details, and Completed Jobs Summary.

**3 operation(s)**:

_investigation_
- `get_active_sessions_details([services: select], [max_rows: integer])` — Get Active Sessions Details
- `get_completed_jobs_summary([date_range: select], [group_by: select], [status: select])` — Get Completed Jobs Summary
- `get_file_transfer_summary([module: select], [date_range: select], [group_by: select])` — Get File Transfer Summary


### `google-cloud-storage` v1.0.0 _(installed)_
_Google Cloud Storage_

Google Cloud Storage is a RESTful online file storage web service for storing and accessing data on Google Cloud Platform infrastructure. This connector facilitates the automated operations related to bucket, bucket objects and bucket policies.

**14 operation(s)**:

_investigation_
- `create_bucket(project: text, bucket: text, [predefinedAcl: select], [predefinedDefaultObjectAcl: select], [projection: select], [additional_fields: json])` — Create Bucket
- `create_bucket_object_policy(bucket: text, bucket: text, entity: text, role: select, [generation: integer])` — Create Bucket Object Policy
- `create_bucket_policy(bucket: text, entity: text, role: select, [additional_fields: json])` — Create Bucket Policy
- `delete_bucket(bucket: text, [ifMetagenerationMatch: integer], [ifMetagenerationNotMatch: integer])` — Delete Bucket
- `delete_bucket_object_policy(bucket: text, bucket: text, entity: text, [generation: integer])` — Delete Bucket Object Policy
- `delete_bucket_policy(bucket: text, entity: text)` — Delete Bucket Policy
- `get_bucket_details(bucket: text, [ifMetagenerationMatch: integer], [ifMetagenerationNotMatch: integer], [projection: select])` — Get Bucket Details
- `get_bucket_object_policy_details(bucket: text, bucket: text, entity: text, [generation: integer])` — Get Bucket Policy Object Details
- `get_bucket_policy_details(bucket: text, entity: text)` — Get Bucket Policy Details
- `get_buckets_list(project: text, [maxResults: integer], [pageToken: text], [prefix: text], [projection: select])` — Get Buckets List
- `get_buckets_list_object_policy(bucket: text, bucket: text, [generation: integer])` — Get Bucket's List Object Policy
- `get_buckets_list_policy(bucket: text)` — Get Bucket's List Policy
- `update_bucket_object_policy(bucket: text, bucket: text, entity: text, [role: select], [generation: integer], [additional_fields: json])` — Update Bucket Object Policy
- `update_bucket_policy(bucket: text, entity: text, [role: select], [additional_fields: json])` — Update Bucket Policy


### `google-resource-manager` v1.0.0 _(installed)_
_Google Cloud Resource Manager_

Google Cloud Resource Manager is a service provided by Google Cloud Platform (GCP) that helps you manage your GCP resources across projects. It provides a unified interface for organizing, viewing, and controlling access to your cloud resources.

**8 operation(s)**:

_investigation_
- `create_project(projectId: text, [displayName: text], [labels: json], [tags: json], [additional_parameters: json])` — Create Project
- `delete_project(project_name: text)` — Delete Project
- `get_organization_details(organization_name: text)` — Get organization Details
- `get_project_details(project_name: text)` — Get Project Details
- `restore_project(project_name: text)` — Restore Project
- `search_organizations([query: text], [pageSize: integer], [pageToken: text])` — Search Organizations
- `search_projects([query: text], [pageSize: integer], [pageToken: text])` — Search Projects
- `update_project(project_name: text, [displayName: text], [labels: json], [tags: json], [additional_parameters: json])` — Update Project


### `itglue` v1.0.0 _(installed)_
_ITGlue_

ITGlue is IT documentation software designed to help you maximize the efficiency, transparency and consistency of your team. This connector facilitates automated operations such as organizations, locations, configurations, domains, and flexible assets

**5 operation(s)**:

_investigation_
- `get_configurations(org_id: integer, [config_id: integer], [config_name: text], [config_type_id: integer], [config_status_id: integer], [page_size: integer], [page_number: integer], [additional_fields: json])` — Get Configurations
- `get_domains(org_id: integer, [domain_id: integer], [page_size: integer], [page_number: integer], [additional_fields: json])` — Get Domains
- `get_flexible_asset(flex_type_id: integer, [flexible_asset_name: text], [org_id: integer], [page_size: integer], [page_number: integer], [additional_fields: json])` — Get Flexible Asset
- `get_locations(org_id: integer, [loc_id: integer], [loc_name: text], [country_id: integer], [region_id: integer], [page_size: integer], [page_number: integer], [additional_fields: json])` — Get Locations
- `get_organizations([org_id: integer], [org_name: text], [org_type_id: integer], [org_status_id: integer], [created_at: datetime], [updated_at: datetime], [page_size: integer], [page_number: integer], [additional_fields: json])` — Get Organizations


### `qualys-fim` v1.0.0 _(installed)_
_Qualys File Integrity Monitoring(FIM)_

Qualys File Integrity Monitoring (FIM) is a highly scalable cloud app that enables a simple way to monitor critical files, directories, and registry paths for changes in real time, and helps adhere to compliance mandates such as PCI-DSS, FedRAMP, HIPAA, GDPR and others. This connector facilitates automated interactions with a Qualys File Integrity Monitoring (FIM) server using FortiSOAR™ playbooks.

**7 operation(s)**:

_investigation_
- `approve_incident (incidentId: text, approvalStatus: select, changeType: select, comment: text, dispositionCategory: select)` — Approve Incident
- `create_manual_incident (filter: text, name: text, [comment: text], [reviewers: text], [userInfo: checkbox])` — Create Manual Incident
- `fetch_incident_events(incidentId: text, [filter: text], [sort: text], [attributes: text], [pageNumber: text], [pageSize: text])` — Fetch Incident Events
- `get_assets([attributes: text], [filter: text], [includeTagData: checkbox], [searchAfter: text], [notSentEventsForHours: integer], [sort: text], [pageNumber: text], [pageSize: text])` — Get Assets
- `get_event_details(eventId: text)` — Get Event Details
- `get_events([filter: text], [sort: text], [incidentContext: checkbox], [incidentIds: text], [pageNumber: text], [pageSize: text])` — Get Events
- `get_incidents([filter: text], [sort: text], [attributes: text], [searchAfter: text], [pageNumber: text], [pageSize: text])` — Get Incidents


### `servicenow-cmdb` v1.0.0 _(installed)_
_ServiceNow CMDB_

ServiceNow Configuration Management Database (CMDB) is a centralized source that gives you full visibility into your IT environment. By storing information about your organization's infrastructure and how it is configured, this system allows you to monitor your network and ensure stability and best performance.

**9 operation(s)**:

_investigation_
- `add_relation_to_configuration_item(class_name: text, sys_id: text, source: select, [inbound_relations: json], [outbound_relations: json])` — Add Relation to Configuration Item
- `create_configuration_item(class_name: text, source: select, name: text, [short_description: text], [attributes: json], [inbound_relations: json], [outbound_relations: json])` — Create Configuration Item
- `delete_relation_for_configuration_item(class_name: text, sys_id: text, rel_sys_id: text)` — Delete Relation for Configuration Item
- `get_cmdb_rel_type([sysparm_limit: integer], [sysparm_offset: integer])` — Get CMDB Relation Type
- `get_cmdb_rel_type_by_sys_id(sys_id: text)` — Get CMDB Relation Type by System ID
- `get_configuration_item_details(class_name: text, sys_id: text)` — Get Configuration Item Details
- `get_configuration_items(class_name: text, [sysparm_query: text], [sysparm_limit: integer], [sysparm_offset: integer])` — Get Configuration Items
- `update_configuration_item(class_name: text, sys_id: text, source: select, [name: text], [short_description: text], [attributes: json])` — Update Configuration Item

_query_
- `custom_endpoint(endpoint: text, [method: select], [body: json])` — Custom API Endpoint


### `vmware-tanzu-service-mesh` v1.0.0 _(installed)_
_VMware Tanzu Service Mesh_

VMware Tanzu® Service Mesh™ is VMware's enterprise-class service mesh solution that provides consistent control and security for microservices, end users, and data—across all your clusters and clouds—in the most demanding multicluster and multicloud environments.

**24 operation(s)**:

_investigation_
- `create_cluster(cluster_id: text, displayName: text, autoInstallServiceMesh: checkbox, [description: text], [enableNamespaceInclusions: checkbox], [namespaceInclusions[]: json])` — Create Cluster
- `create_global_namespace(name: text, domain_name: text, match_conditions: json, [display_name: text], [description: text], [color: text], [mtls_enforced: checkbox], [ca_type: text])` — Create Global Namespace
- `delete_global_namespace(global_namespace_id: text)` — Delete Global Namespace
- `delete_job(job_id: text)` — Delete Job
- `download_job(job_id: text)` — Download Job
- `generate_security_token_for_cluster(cluster_id: text)` — Generate Security Token for Cluster
- `get_capabilities_enabled_for_global_namespace(global_namespace_id: text)` — Get Capabilities Enabled for Global Namespace
- `get_cluster_details(cluster_id: text)` — Get Clusters Details
- `get_cluster_logs(cluster_id: text, type: text, [namespace: text])` — Get Cluster Logs
- `get_cluster_onboard_url()` — Get Cluster Onboard URL
- `get_clusters()` — Get Clusters List
- `get_global_namespace_details(global_namespace_id: text)` — Get Global Namespace Details
- `get_global_namespaces()` — Get Global Namespaces
- `get_job_details(job_id: text)` — Get Job Details
- `get_jobs()` — Get Jobs List
- `get_member_services_in_global_namespace(global_namespace_id: text)` — Get Member Services in Global Namespace
- `get_resource_groups(type: text, [from: text], [limit: integer])` — Get Resource Groups
- `get_status_for_capability_enabled_for_global_namespace(global_namespace_id: text, capability: text)` — Get Status for Capability Enabled for Global Namespace
- `get_tanzu_service_mesh_version(cluster_id: text)` — Get Tanzu Service Mesh Version
- `remove_cluster_from_tanzu_service_mesh(cluster_id: text)` — Remove Cluster from Tanzu Service Mesh
- `uninstall_tanzu_service_mesh_from_cluster(cluster_id: text)` — Uninstall Tanzu Service Mesh from Cluster
- `update_cluster(cluster_id: text, displayName: text, autoInstallServiceMesh: checkbox, [description: text], [enableNamespaceInclusions: checkbox], [namespaceInclusions[]: json])` — Update Cluster
- `update_global_namespace(global_namespace_id: text, match_conditions: json, [display_name: text], [description: text], [color: text], [mtls_enforced: checkbox], [ca_type: text])` — Update Global Namespace
- `upgrade_tanzu_service_mesh_version_on_cluster(cluster_id: text, [version: text])` — Install/Upgrade Tanzu Service Mesh Version on Cluster


---

## Identity Management

### `manage-engine-admanager-plus` v1.0.0 _(installed)_
_ManageEngine ADManager Plus_

ManageEngine ADManager Plus is an Active Directory (AD) management and reporting solution that allows IT administrators and technicians to manage AD objects easily and generate instant reports.

**5 operation(s)**:

_investigation_
- `add_users_to_group(PRODUCT_NAME: text, domainName: text, [sAMAccountName: text], [userPrincipalName: text], [distinguishedName: text], [mail: email], [employeeID: text], [objectGUID: text], [objectSID: text], [addGroup: text], [primaryGroup: text])` — Add Users To Group
- `disable_user(PRODUCT_NAME: text, domainName: text, [sAMAccountName: text], [userPrincipalName: text], [distinguishedName: text], [mail: email], [employeeID: text], [objectGUID: text], [objectSID: text])` — Disable Users
- `enable_user(PRODUCT_NAME: text, domainName: text, [accountExpires: select], [sAMAccountName: text], [userPrincipalName: text], [distinguishedName: text], [mail: email], [employeeID: text], [objectGUID: text], [objectSID: text])` — Enable Users
- `remove_users_from_group(PRODUCT_NAME: text, domainName: text, [sAMAccountName: text], [userPrincipalName: text], [distinguishedName: text], [mail: email], [employeeID: text], [objectGUID: text], [objectSID: text], [isRemoveFromAllGroup: checkbox], [removeGroup: text])` — Remove Users From Group
- `unlock_user(PRODUCT_NAME: text, domainName: text, [sAMAccountName: text], [userPrincipalName: text], [distinguishedName: text], [mail: email], [employeeID: text], [objectGUID: text], [objectSID: text])` — Unlock Users


### `okta` v1.1.0 _(installed)_
_OKTA_

Okta is a cloud-based identity and access management (IAM) platform that helps organizations securely manage and connect users to applications, devices, and data. It provides authentication, authorization, and user lifecycle management for employees, partners, and customers.

**11 operation(s)**:

_investigation_
- `activate_user(user_id: text)` — Activate User
- `create_user(firstName: text, lastName: text, login: text, password: password, [mobilePhone: text])` — Create User
- `deactivate_user(user_id: text)` — Deactivate User
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_groups_details([limit: text])` — Get Groups
- `get_list_of_users([query: text])` — Get List of Users
- `get_user_details(get_user_by: select, user_id: text)` — Get User
- `revoke_all_user_sessions(user_id: text, [oauthTokens: checkbox], [forgetDevices: checkbox])` — Revoke All User Sessions
- `set_password(user_id: text, new_password: password)` — Set Password
- `unlock_user(user_id: text)` — Unlock User
- `update_user(user_id: text, [firstName: text], [lastName: text], [nickName: text], [displayName: text], [email: text], [secondEmail: text], [department: text], [mobilePhone: text], [primaryPhone: text], [streetAddress: text], [city: text], [state: text], [zipCode: text], [countryCode: text])` — Update User


---

## Identity and Access Management

### `aws-access-analyzer` v1.1.0 _(installed)_
_AWS Access Analyzer_

AWS Access Analyzer helps you identify the resources in your organization and accounts, such as Amazon S3 buckets or IAM roles, shared with an external entity, enabling you to identify unintended access to your resources and data, which is a security risk.

**8 operation(s)**:

_investigation_
- `get_analyzed_resources([assume_role: checkbox], analyzer_arn: text, resource_arn: text)` — Details of an Analyzed Resources
- `get_analyzers([assume_role: checkbox], analyzer_name: text)` — Get analyzer details
- `get_findings([assume_role: checkbox], analyzer_arn: text, id: text)` — Get Finding Details
- `list_analyzed_resources([assume_role: checkbox], analyzer_arn: text, [resource_type: select], [size: integer], [next_token: text])` — List of Analyzed Resources
- `list_analyzers([assume_role: checkbox], type: select, size: integer, [next_token: text])` — List Analyzers
- `list_findings([assume_role: checkbox], analyzer_arn: text, [size: integer], [filter: json], [sort: json], [next_token: text])` — List of Findings
- `start_resource_scan([assume_role: checkbox], analyzer_arn: text, resource_arn: text)` — Start Resource Scan
- `update_findings([assume_role: checkbox], analyzer_arn: text, update_by: select, status: select, [client_token: text])` — Update Findings Status


### `azure-active-directory` v2.2.1 _(installed)_
_Microsoft Entra ID_

Microsoft Entra ID, formerly known as Azure Active Directory (Azure AD), is a cloud-based identity and access management (IAM) service that secures access to Microsoft cloud services and other applications for users. It manages user identities, enforces access policies, and supports single sign-on (SSO) to help organizations protect cloud and on-premises resources

**24 operation(s)**:

_containment_
- `disable_user(based_on: select)` — Disable User
- `enable_user(based_on: select)` — Enable User
- `reset_password(based_on: select, password: password, [force_change: checkbox])` — Reset Password

_enrichment_
- `get_managers(user_id: text)` — Get Managers
- `get_people(user_id: text, [$filter: text], [$select: text], [$top: integer], [$skip: integer])` — Get People
- `get_user_membership(user_id: text, membership_type: select)` — Get User Membership
- `list_user_owned_devices(user_id: text)` — List User Owned Devices
- `list_user_owned_objects(user_id: text)` — List User Owned Objects

_investigation_
- `add_user(displayName: text, mailNickname: text, userPrincipalName: text, password: password, [force_change: checkbox], [accountEnabled: checkbox], [additional_fields: json])` — Add User
- `delete_user(based_on: select)` — Delete User
- `get_registered_owners(device_id: text)` — List Registered Owners
- `get_registered_users(device_id: text)` — List Registered Users
- `get_user_details(based_on: select, [additional_info: checkbox])` — Get User Details
- `list_devices([$filter: text], [$select: text], [$top: integer], [get_all_pages: checkbox], [$skipToken: text])` — List Devices
- `list_direct_reports(user_id: text)` — List Direct Reports
- `rest_api_call(endpoint: text, [method: select], [params: json], [body: json])` — Generic REST API Call

_investigation _
- `add_member(id: text, dir_object_id: text)` — Add Member
- `get_group_details(id: text)` — Get Group Details
- `list_group_members(id: text, [$filter: text], [$select: text], [$top: integer], [get_all_pages: checkbox], [$skipToken: text])` — List Group Members
- `list_groups([$filter: text], [$select: text], [$top: integer], [get_all_pages: checkbox], [$skipToken: text])` — List Groups
- `list_sign_ins([$filter: text], [$top: integer], [get_all_pages: checkbox], [$skipToken: text])` — List SignIns Events
- `list_users([$filter: text], [$select: text], [$top: integer], [get_all_pages: checkbox], [$skipToken: text])` — List Users
- `remove_member(id: text, dir_object_id: text)` — Remove Member

_response_
- `revoke_sign_in_sessions(user_id: text)` — Revoke SignIn Sessions


### `azure-key-vault` v2.0.0 _(installed)_
_Azure Key Vault_

Azure Key Vault is a cloud based key management and security service that enables in securing cryptographic keys, password and other secret services used by cloud applications and services.This connector provides automated actions to list, get and delete vaults, keys, secrets and certificates

**18 operation(s)** (+2 hidden):

_investigation_
- `delete_certificate(vault_name: text, certificate_name: text)` — Delete Certificate
- `delete_key(vault_name: text, key_name: text)` — Delete Key
- `delete_key_vault(vault_name: text, resource_group_name: text)` — Delete Key Vault
- `delete_secret(vault_name: text, secret_name: text)` — Delete Secret
- `get_certificate(vault_name: text, certificate_name: text, [certificate-version: text])` — Get Certificate Details
- `get_certificate_policy(vault_name: text, certificate_name: text)` — Get Certificate Policy
- `get_credentials()` — Get Credentials
- `get_key(vault_name: text, key_name: text, [key-version: text])` — Get Key Details
- `get_key_vault(vault_name: text, resource_group_name: text)` — Get Key Vault
- `get_secret(vault_name: text, secret_name: text, [secret_version: text])` — Get Secret Details
- `get_versions(vault_name: text, object: select, [skip_token: text], [size: integer])` — Get Versions
- `list_certificate(vault_name: text, [includePending: checkbox], [skip_token: text], [size: integer])` — Get All Certificates
- `list_key_vault([skip_token: text], [size: integer])` — List Key Vaults
- `list_keys(vault_name: text, [skip_token: text], [size: integer])` — Get All Keys
- `list_secret(vault_name: text, [size: integer], [skip_token: text])` — Get All Secrets
- `update_vault_access_policy(vault_name: text, resource_group_name: text, operation_kind: select, accessPolicies: json)` — Update Vault's Access Policies


### `beyondtrust-privileged-remote-access` v1.0.0 _(installed)_
_BeyondTrust Privileged Remote Access_

BeyondTrust Privileged Remote Access controls, manages, and audits privileged accounts and credentials. This enables just-in-time, zero trust access to on-premises and cloud resources by internal, external, and third-party users.

**18 operation(s)**:

_investigation_
- `checkin_or_checkout_private_key_or_password(operation: select, account_id: integer)` — Checkin or Checkout Credentials From Vault
- `create_account_in_vault(name: text, username: text, type: select, [description: text], [account_group_id: text])` — Create Account in Vault
- `create_user_in_vendor_group(group_id: text, username: text, public_display_name: text, password: password, email_address: email, [password_never_expire: checkbox], [password_reset_next_login: checkbox], [account_disabled: checkbox], [preferred_email_language: text])` — Create User in Vendor Group
- `create_vendor_group(name: text, default_policy: integer, administrator_id: integer, [account_expiration: integer], [user_added_notification_enabled: checkbox], [user_expired_notification_enabled: checkbox], [user_approval_enabled: checkbox], [network_restrictions: text])` — Create Vendor Group
- `delete_account_in_vault(account_id: integer)` — Delete Account From Vault
- `delete_vendor_group(group_id: integer)` — Delete Vendor Group
- `get_all_accounts_in_vault([name: text], [include_personal: checkbox], [type: select], [account_group_id: text], [current_page: integer], [per_page: integer])` — Get Account List From Vault
- `get_all_group_policies([name: text], [current_page: integer], [per_page: integer])` — Get Group Policy List
- `get_all_users([username: text], [email_address: email], [security_provider_id: text], [current_page: integer], [per_page: integer])` — Get User List
- `get_all_users_in_vendor_groups(group_id: text, [current_page: integer], [per_page: integer])` — Get User List in Vendor Group
- `get_all_vault_account_groups([name: text], [current_page: integer], [per_page: integer])` — Get Vault Account Group List
- `get_all_vault_account_policies([name: text], [code_name: text], [current_page: integer], [per_page: integer])` — Get Vault Account Policy List
- `get_all_vault_endpoints([name: text], [hostname: text], [domain_name: text], [description: text], [current_page: integer], [per_page: integer])` — Get Vault Endpoint List
- `get_all_vendor_groups([name: text], [current_page: integer], [per_page: integer])` — Get Vendor Group List
- `get_user_in_vendor_groups(group_id: text, user_id: text)` — Get User Details in Vendor Group
- `get_vendor_group_by_id(group_id: integer)` — Get Vendor Group Details
- `remove_user_from_vendor_groups(group_id: text, user_id: text)` — Remove User from Vendor Group
- `update_vendor_group(group_id: integer, [name: text], [default_policy: integer], [account_expiration: integer], [user_added_notification_enabled: checkbox], [user_expired_notification_enabled: checkbox], [user_approval_enabled: checkbox], [administrator_id: integer], [network_restrictions: text])` — Update Vendor Group


### `crowdstrike-identity-platform` v1.0.0 _(installed)_
_CrowdStrike Identity Platform_

CrowdStrike Falcon® Identity Protection is a comprehensive identity security solution designed to protect organizations from modern identity-based threats across hybrid environments.

**10 operation(s)**:

_investigation_
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_alert_details_by_ids(ids: text, [include_hidden: checkbox])` — Get Alert Details by IDs
- `get_alert_ids([filter: select], [include_hidden: checkbox], [offset: integer], [limit: integer])` — Get Alert IDs
- `get_alert_list([filter: text], [include_hidden: checkbox], [sort: text], [limit: integer], [after: text])` — Get Alert List
- `get_incident_details_by_ids(ids: text)` — Get Incident Details by IDs
- `get_incident_ids([filter: text], [sort: text], [offset: integer], [limit: integer])` — Get Incident IDs
- `update_alert(ids: text, status: select, [assign_to_name: text], [assign_to_user_id: text], [assign_to_uuid: text], [add_tag: text], [remove_tag: text], [remove_tags_by_prefix: text], [unassign: checkbox], [show_in_ui: checkbox])` — Update Alert
- `update_alert_status(ids: text, status: select)` — Update Alert Status
- `update_incident(ids: text, status: select, [update_name: text], [update_description: text], [add_tag: text], [delete_tag: text], [unassign: checkbox], [update_assigned_to_v2: text])` — Update Incident
- `update_incident_status(ids: text, status: select)` — Update Incident Status


### `cyolo` v1.0.0 _(installed)_
_Cyolo_

Cyolo helps enterprises provide their global workforce with convenient and secure access to applications, resources, workstations, servers, and files, regardless of location or device used.

**18 operation(s)**:

_investigation_
- `create_policy(name: text, [enabled: checkbox], [dynamic_groups: text], [simple_groups: text], [mappings: text], [mapping_categories: text], [supervisors: text], [users: text], [webhooks: text], [timed_access_status: checkbox], [start: datetime], [end: datetime], [days: multiselect], [trusted_certificates: text], [device_posture_profiles: text], [capabilities: json], [constraints: json])` — Create Policy
- `delete_user_by_id_or_name(id: text)` — Delete User By ID Or Name
- `delete_user_from_policy(id: text, users: text)` — Delete User From Policy
- `get_policy_by_id_or_name(id: text)` — Get Policy By ID Or Name
- `get_user_by_id_or_name(id: text)` — Get User By ID Or Name
- `list_capabilities()` — Get Capabilities List
- `list_certificates()` — Get Certificates List
- `list_constraints()` — Get Constraints List
- `list_device_posture_profiles()` — Get Device Posture Profiles List
- `list_dynamic_groups()` — Get Dynamic Group List
- `list_mapping_categories()` — Get Mapping Categories List
- `list_mappings()` — Get Mappings List
- `list_policies()` — Get Policy List
- `list_simple_groups()` — Get Simple Group List
- `list_user_policies(id: text)` — Get User Policies
- `list_users()` — Get Users List
- `list_webhooks()` — Get Webhooks List
- `update_policy(id: text, [name: text], [enabled: checkbox], [dynamic_groups: text], [simple_groups: text], [mappings: text], [mapping_categories: text], [supervisors: text], [users: text], [webhooks: text], [timed_access_status: checkbox], [start: datetime], [end: datetime], [days: multiselect], [trusted_certificates: text], [device_posture_profiles: text], [capabilities: json], [constraints: json])` — Update Policy


### `fortinet-fortipam` v1.0.0 _(installed)_
_Fortinet FortiPAM_

FortiPAM provides privileged access management, control and monitoring of elevated accounts, processes and critical systems across the entire IT environment.

**5 operation(s)**:

_investigation_
- `delete_user(name: text)` — Delete User
- `execute_an_api_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_all_users([datasource: checkbox], [with_meta: checkbox], [with_contents_hash: checkbox], [skip: checkbox], [exclude-default-values: checkbox], [start: integer], [count: integer], [skip_to: integer], [format: text], [custom_attributes: json])` — Get All Users
- `get_user_details(name: text, [datasource: checkbox], [with_meta: checkbox], [custom_attributes: json])` — Get User Details
- `update_user(name: text, status: select, [display-name: text], [custom_attributes: json])` — Update User


### `ibm-iam` v1.0.0 _(installed)_
_IBM IAM_

The IBM IAM Identity Service API is used to manage service IDs, API key identities, trusted profiles, account security settings and to create IAM access tokens for a user or service ID.

**21 operation(s)**:

_investigation_
- `create_a_service_id(account_id: text, name: text, [description: text], [unique_instance_crns: text])` — Create A Service ID
- `create_an_api_key([account_id: text], name: text, iam_id: text, [description: text])` — Create An API Key
- `delete_api_key(api_key_unique_id: text)` — Delete API Key
- `delete_service_id_and_associated_api_keys(service_id: text)` — Delete Service ID and Associated API keys
- `disable_the_api_key(api_key_unique_id: text)` — Disable the API key
- `enable_the_api_key(api_key_unique_id: text)` — Enable the API key
- `get_account_configurations(account_id: text)` — Get Account Configurations
- `get_activity_report_for_the_account(account_id: text, reference: text)` — Get Activity Report
- `get_api_key_details(api_key_unique_id: text, [include_history: checkbox], [include_activity: select])` — Get API Key Details
- `get_api_key_details_by_value(iam_apiKey: text, [include_history: checkbox])` — Get API Key Details By Value
- `get_api_keys(account_id: text, iam_id: text, [pagesize: integer], [pagetoken: text], [scope: select], [type_value: select], [sort: select], [order: select], [include_history: checkbox])` — Get API Keys
- `list_service_id_by_account_id(account_id: text)` — List Service IDs
- `list_service_id_by_name(account_id: text, name: text, [pagesize: integer], [pagetoken: integer], [sort: select], [order: select], [include_history: checkbox])` — List Service IDs By Name
- `lock_api_key(api_key_unique_id: text)` — Lock API Key
- `lock_service_id(service_id: text)` — Lock The Service ID
- `trigger_activity_report_for_the_account(account_id: text, [type: text], [duration: text])` — Trigger Activity Report
- `unlock_api_key(api_key_unique_id: text)` — UnLock API Key
- `unlock_service_id(service_id: text)` — Unlock The Service ID
- `update_account_configurations(entity_tag: text, account_id: text, restrict_create_service_id: select, restrict_create_platform_apikey: select, [allowed_ip_addresses: text], mfa: select, [user_mfa: text], session_expiration_in_seconds: text, session_invalidation_in_seconds: text, max_sessions_per_identity: text, system_access_token_expiration_in_seconds: text, system_refresh_token_expiration_in_seconds.: text)` — Update Account Configurations
- `update_api_key(entity_tag: text, api_key_unique_id: text, name: text, [description: text], [support_sessions: select], [action_when_leaked: select])` — Update API Key
- `update_service_id(service_id: text, name: text, [description: text], [unique_instance_crns: text], entity_tag: text)` — Update Service ID


### `manage-engine-key-manager-plus` v1.0.0 _(installed)_
_ManageEngine Key Manager Plus_

ManageEngine Key Manager Plus connector provides a 'key management' solution that helps you consolidate, control, manage, monitor, and audit the entire life cycle of SSH (Secure Shell) keys and SSL (Secure Sockets Layer) certificates.

**3 operation(s)**:

_investigation_
- `get_ssh_keys()` — Get SSH Keys
- `get_ssl_certificates(search_type: select, time_out: integer, port: integer)` — Get SSL Certificates
- `update_credentials(resource_name: text, user_name: text, password: password, [is_admin: checkbox])` — Update Credentials


### `oracle-access-manager` v1.0.0 _(installed)_
_Oracle Access Manager_

Oracle Access Manager (OAM) is a robust identity and access management solution that provides secure authentication, single sign-on, and authorization control for web applications and resources within organizations. It ensures only authorized users can access specific data, enhancing security and user experience.

**4 operation(s)**:

_investigation_
- `change_user_status_by_user_id(userId: text, [enabled: select], [forcepwdchange: select], [unlocked: select])` — Change User Status By User ID
- `delete_sessions(based_on: select)` — Delete Session
- `get_user_status_by_user_id(userId: text)` — Get User Status by User ID
- `retrieve_sessions([clientIp: text], [sessionId: text], [userId: text], [idStoreName: text], [isImpersonating: select], [lastAccessTime: datetime], [updateTime: datetime], [expiryTime: datetime], [userAttributes: json], [fromIndex: integer], [pageSize: integer])` — Get Sessions List


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

_investigation_
- `create_group(name: text, displayName: text, [description: text], [externalId: text], [members: text])` — Create Group
- `create_user(email: text, [userName: text], [givenName: text], [familyName: text], [userType: select], [userDetails: json])` — Create User
- `delete_group(group_id: text)` — Delete Group
- `delete_user(userUUID: text)` — Delete User
- `get_group_list([displayName: text], [urn:sap:cloud:scim:schemas:extension:custom:2.0:Group:name: text], [filter: text], [start_id: text], [count: integer])` — Get Group List
- `get_user_list([id: text], [userName: text], [userType: select], [filter: text], [start_id: text], [count: integer])` — Get User List
- `update_group_members(group_id: text, operation: select)` — Update Group Members
- `update_user_details(userUUID: text, [status: select], [operations: select], [add_operations: json])` — Update User Details


### `silverfort` v1.0.0 _(installed)_
_Silverfort_

Silverfort delivers adaptive authentication across all corporate networks and cloud environments from a unified platform. This integration is used to gather and update risk associated with a user or resource from Silverfort.

**4 operation(s)**:

_investigation_
- `get_resource_risk(resource_name: text, domain: text)` — Get Resource Risk
- `get_user_risk(user_identification: select)` — Get User Risk
- `update_resource_risk(resource_name: text, domain: text, risk_name: text, severity: text, valid_for: integer, description: text)` — Update Resource Risk
- `update_user_risk(user_identification: select, risk_name: text, severity: text, valid_for: integer, description: text)` — Update User Risk


---

## Information

### `cisco-meraki-dashboard` v1.0.0 _(installed)_
_Cisco Meraki Dashboard_

The Cisco Meraki provide cloud managed devices.

**1 operation(s)**:

- `locate_device(attributes: select, value: text, timespan: select)` — Locate Device


### `cisco-spark` v1.0.0 _(installed)_
_Cisco Spark_

Pulls lists of users and rooms, and allows for sending of messages

**3 operation(s)**:

_investigation_
- `get_rooms()` — List Rooms
- `get_users([email: text], [displayNamePrefix: text])` — Get Users

_miscellaneous_
- `send_message(roomId: text, [recipientEmail: text], message: text, [markdown: checkbox])` — Send a Message


### `cisco-umbrella-investigate` v2.0.0 _(installed)_
_Cisco Umbrella Investigate_

Cisco Umbrella Investigate provides the most complete view of the relationships and evolution of domains, IPs, autonomous systems (ASNs), and file hashes. Investigate is accessible using a web console and an API and its rich threat intelligence adds the security context needed to uncover and predict threats.

**3 operation(s)**:

_investigation_
- `domain_information(domain: text)` — Get Information About a Domain
- `latest_malicious_domains(ipaddr: text)` — Fetch Latest Malicious Domains of an IP
- `whois(domain: text)` — Fetch WHOIS Information


### `cloudpassage-halo` v1.0.0 _(installed)_
_CloudPassage Halo_

Provide investigative actions like list process, list user and list vulnerabilities

**7 operation(s)**:

_investigation_
- `get_cve_details(cve: text)` — Get CVE Details
- `get_system_info(server_id: text)` — Get System Information
- `get_user(server_id: text, username: text)` — Get Local User Account Details
- `list_server_processes(server_id: text)` — List Server Processes
- `list_servers()` — List Server
- `list_users()` — List All Local User Accounts
- `list_vulnerabilities(server_id: text)` — List Server Vulnerabilities


### `cyber-triage` v1.0.0 _(installed)_
_Cyber Triage_

Provide investigative action to scan an endpoint using Cyber Triage

**1 operation(s)**:

_investigation_
- `scan_endpoint(ip_hostname: select, ip_hostname: text, [malware_scan: checkbox], [file_upload: checkbox], [full_scan: checkbox])` — Scan Endpoint


### `dns` v1.0.0 _(installed)_
_DNS_

This connector allows for DNS lookups of both FQDN/Domain and IP address

**2 operation(s)**:

_investigation_
- `lookup_domain(domain: text, [qtype: select])` — Lookup FQDN/Domain
- `lookup_ip(ipaddr: text)` — Lookup IP


### `dshield` v1.0.0 _(installed)_
_DShield_

Provide investigative actions like lookup ip and get threat feeds details from DShield

**2 operation(s)**:

_investigation_
- `get_threat_feeds()` — Get Threat Feeds
- `lookup_ip(ip: text)` — Lookup IP


### `farsight-dnsdb` v1.0.0 _(installed)_
_Farsight Security DNSDB_

Perform actions like search ip, search domain and search name server to get information from the Farsight Security DNSDB.

**3 operation(s)**:

_investigation_
- `search_domain(wildcard: select, wildcard_value: text, [seen_after: datetime], [seen_before: datetime], [type: select], [limit: integer])` — Search Domain
- `search_ip(ip: text, [seen_after: datetime], [seen_before: datetime], [network_prefix: integer], [limit: integer])` — Search IP
- `search_name_server(name_server: text, [seen_after: datetime], [seen_before: datetime], [type: select], [limit: integer])` — Search Name Server


### `google-bigquery` v1.0.0 _(installed)_
_Google BigQuery_

Google BigQuery is a service user allows to run super-fast queries of large datasets.

**2 operation(s)**:

_investigation_
- `run_query(query: text)` — Run a Query

_miscellaneous_
- `list_tables()` — List Tables


### `honeydb` v1.0.0 _(installed)_
_HoneyDB_

Provide investigative actions like lookup ip and get bad hosts from HoneyDB

**2 operation(s)**:

_investigation_
- `get_bad_hosts()` — Get Bad Hosts
- `lookup_ip(ip: text)` — Lookup IP


### `isitphishing` v1.0.0 _(installed)_
_isitPhishing_

Provide investigative action to get url reputation from isitPhishing

**1 operation(s)**:

_investigation_
- `url_reputation(url: text)` — Get URL Reputation


### `jask-asoc` v1.0.0 _(installed)_
_JASK ASOC_

Pull data from Alerts, Signals, and Assets within JASK's ASOC platform

**9 operation(s)**:

_investigation_
- `get_alert_details(alertId: text)` — Get Alert Details
- `get_asset_details(assetId: text)` — Get Asset Details
- `get_asset_details_by_ip(assetIp: text)` — Get Asset Details By IP
- `get_intel_sources()` — Get Intel Sources
- `get_sensor_details(sensorId: text)` — Get Sensor Details
- `get_sensors_list()` — Get Sensor List
- `get_signal_details(signalId: text)` — Get Signal Details
- `post_threat_intel(intelValue: text, intelConfidence: text, intelSource: text, intelTags: text)` — Post Threat Intel
- `search(searchContext: select, searchQuery: text, [searchOffset: integer], [timeWindow: checkbox])` — Search


### `knowthycustomer` v1.0.0 _(installed)_
_Know Thy Customer_

Searches Know Thy Customer for data about people, phone numbers, etc

**4 operation(s)**:

_investigation_
- `lookup_email(email_address: email)` — Lookup Email
- `lookup_person(first_name: text, last_name: text, [phone: phone], [address: text])` — Lookup Person
- `lookup_phone(phone_number: phone)` — Lookup Phone Number
- `lookup_property(property_address: text)` — Lookup Address


### `macvendors` v1.0.0 _(installed)_
_MACVendors_

MACVendors Connector provides vendor name given MAC Address

**1 operation(s)**:

_investigation_
- `mac_lookup(mac_add: text)` — MAC Address Lookup


### `mitre-attack` v2.0.2 _(installed, ingestion)_
_MITRE ATT&CK_

The MITRE ATT&CK knowledge base is used as a foundation for the development of specific threat models and methodologies. Connector helps to replicate knowledge base of adversary tactics and techniques based on real-world observations

**2 operation(s)**:

- `get_mitre_data(modules: multiselect, [force_ingestion: checkbox])` — Get MITRE Data
- `get_mitre_data_sample()` — Get MITRE Sample Data


### `mnemonic` v1.0.0 _(installed)_
_Mnemonic_

Provides DNS information from the Mnemonic public DNS API

**1 operation(s)**:

_investigation_
- `lookup_domain(domain: text)` — Lookup Domain


### `mxtoolbox` v2.0.0 _(installed)_
_MxToolbox_

MxToolbox offers monitoring solutions and lookup tools. Connector supports automated operations for Lookup, Monitor and Usage

**1 operation(s)**:

_investigation_
- `api_call(api_method: select)` — Get MxToolbox Records


### `myipms` v1.0.0 _(installed)_
_MYIP.MS_

Get information about IP address/domain.

**1 operation(s)**:

_investigation_
- `lookup(query: text)` — Whois Lookup


### `neutrinoapi` v1.0.0 _(installed)_
_NeutrinoAPI_

NeutrinoAPI connector to pull information about potentially malicious or dangerous IP addresses. Connector supports the automated operations like Analyze IP Address, Get IP Information and Get IP Address Blocklist Status

**3 operation(s)**:

_investigation_
- `ip_blocklist(ip: text)` — Get IP Address Blocklist Status
- `ip_info(ip: text)` — Get IP Address Information
- `ip_probe(ip: text)` — Analyze IP Address


### `passivetotal` v1.0.0 _(installed)_
_PassiveTotal_

Provide investigative action to get reputation of IP and Domain and get WHOIS information of IP and Domain

**9 operation(s)**:

_investigation_
- `domain_reputation(query: text)` — Get Domain Reputation
- `get_account_info()` — Get Account Information
- `get_domain_classification(query: text)` — Get Domain Classification
- `get_malware_data(query: text)` — Get Malware Data
- `get_subdomains(query: text)` — Get Sub Domains
- `ip_reputation(query: text)` — Get IP Reputation
- `search_whois(field: select, query: text)` — Search WHOIS
- `whois_domain(query: text)` — WHOIS Domain
- `whois_ip(query: text)` — WHOIS IP


### `phishtank` v1.0.1 _(installed)_
_PhishTank_

PhishTank Connector which utilizes retrieving a URL's reputation from PhishTank

**1 operation(s)**:

_investigation_
- `url_reputation(url: text)` — URL Reputation


### `proofpoint-tap` v1.0.2 _(installed)_
_Proofpoint TAP_

Perform actions like get events, get campaign details and get forensic information using Proofpoint TAP

**8 operation(s)**:

_investigation_
- `get_all_events(interval: select, [format: select], [threat_type: multiselect], [threat_status: multiselect])` — Get All Events
- `get_clicks_blocked_event(interval: select, [format: select], [threat_type: multiselect], [threat_status: multiselect])` — Get Blocked Malicious URL Events
- `get_clicks_delivered_event(interval: select, [format: select], [threat_type: multiselect], [threat_status: multiselect])` — Get Delivered Threat Message Events
- `get_clicks_permitted_event(interval: select, [format: select], [threat_type: multiselect], [threat_status: multiselect])` — Get Permitted Malicious URL Events
- `get_issues_event(interval: select, [format: select], [threat_type: multiselect], [threat_status: multiselect])` — Get Events for All Issues
- `get_messages_blocked_event(interval: select, [format: select], [threat_type: multiselect], [threat_status: multiselect])` — Get Blocked Threat Message Events

- `get_campaign_details(campaign_id: text)` — Get Campaign Details
- `get_forensic(id: select, value: text, [include_campaign_forensics: checkbox])` — Get Forensic Details


### `ripestat` v1.0.0 _(installed)_
_RIPEstat_

Pulls information about an IP address from multiple endpoints provided by RIPEstat

**1 operation(s)**:

_investigation_
- `lookup_ip(ip_address: text, [reverse_dns: checkbox], [dns_chain: checkbox], [iana_registry: checkbox], [looking_glass: checkbox], [mlab_activity_count: checkbox], [mlab_bandwidth: checkbox], [mlab_clients: checkbox], [network_info: checkbox], [routing_history: checkbox], [routing_status: checkbox])` — Lookup IP


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


### `unshortenme` v1.0.0 _(installed)_
_Unshorten.me_

Unshorten.me connector can un-shorten URLs created by different services

**1 operation(s)**:

_investigation_
- `unshorten_url(url: text)` — Unshorten URL


---

## Insider Threat

### `insider-security-ueba` v1.0.0 _(installed)_
_InsiderSecurity UEBA_

InsiderSecurity UEBA (User and Entity Behaviour Analytics) detects malicious user activity early in your on-premise or cloud infrastructure, allowing you to take action early and avoid data loss.

**3 operation(s)**:

_investigation_
- `get_alerts_by_id(id: text)` — Get Alerts by ID
- `search_alerts(risk_entity: text, threat_name: text, time_end: datetime)` — Search Alerts
- `search_data_enrichment(index: text, [entity_ip: text], [entity_name: text], [query: text], [time_start: datetime], [time_end: datetime], [limit: text])` — Search Data Enrichment


---

## Investigation

### `exabeam` v1.0.0 _(installed)_
_Exabeam_

The Exabeam Security Management Platform provides end-to-end detection, User Event Behavioral Analytics.

**8 operation(s)**:

_investigation_
- `delete_watchlist(watchlistId: text)` — Delete Watchlist
- `get_asset_data(assetId: text)` — Get Asset Data
- `get_notable_users(unit: text, num: integer, numberOfResults: integer)` — Get Notable Users
- `get_peer_groups()` — Get Peer Groups
- `get_user_info(username: text)` — Get User Information
- `get_user_labels()` — Get User Labels
- `get_user_sessions(username: text, [startTime: datetime], [endTime: datetime])` — Get User Sessions
- `get_watchlists()` — Get Watchlists


### `fortinet-forticnp` v2.0.0 _(installed)_
_Fortinet FortiCNP_

Fortinet FortiCNP integrates with APIs provided by cloud vendors including AWS, Azure, and Google Cloud Platform to monitor and track all security components, including configurations, user activity, and traffic flow logs. This Connector automated operations such as retrieving the get alerts from Fortinet FortiCNP, etc

**4 operation(s)**:

_investigation_
- `get_finding_list(objectId: text, startTime: datetime, endTime: datetime, [skip: integer], [limit: integer])` — Get Finding List
- `get_resource_details(resourceid: text)` — Get Resource Details
- `get_resource_list(filter: json, [skip: integer], [limit: integer], [orderBy: select], [orderDirection: select])` — Get Resource List
- `get_resource_map()` — Get Resource Map


### `fortinet-fortimonitor` v1.0.1 _(installed, ingestion)_
_Fortinet FortiMonitor_

FortiMonitor is a cloud-based monitoring SAAS service with full-stack visibility of hybrid IT infrastructure.

**11 operation(s)**:

_investigation_
- `acknowledge_incident(input_type: select, who: text, [should_broadcast: checkbox], [delay_in_seconds: integer])` — Acknowledge Incident
- `create_incident_logs(input_type: select, user: text, entry: text, [log_start_timestamp: datetime], [public: checkbox])` — Create Incident Log
- `escalate_incident(input_type: select, who: text)` — Escalate Incident
- `get_contact([name: text], [sort_by: checkbox], [full: checkbox], [limit: integer], [offset: integer])` — Get Contacts
- `get_incident_logs(input_type: select, [log_start_timestamp: datetime], [full: checkbox], [sort_by: checkbox], [limit: integer], [offset: integer])` — Get Incident Logs
- `get_incidents([server: integer], [start_time: datetime], [end_time: datetime], [severity: select], [status: select], [sort_by: checkbox], [full: checkbox], [limit: integer], [offset: integer])` — Get Incidents
- `get_maintenance_schedule([name: text], [sort_by: checkbox], [full: checkbox], [limit: integer], [offset: integer])` — Get Maintenance Schedule
- `get_rotating_contact([name: text], [full: checkbox], [sort_by: checkbox], [limit: integer], [offset: integer])` — Get Rotating Contact
- `get_servers([fqdn: text], [server_group: text], [name: text], [partner_server_id: text], [server_key: text], [status: select], [full: checkbox], [tag_filter_mode: select], [tags: text], [sort_by: checkbox], [limit: integer], [offset: integer], [attributes: json])` — Get Servers
- `get_users([username: text], [full: checkbox], [limit: integer], [offset: integer])` — Get All Customer Users
- `send_broadcast(input_type: select, who: text, message: text)` — Send Broadcast Message


### `microsoft-casb` v2.0.0 _(installed)_
_Microsoft Defender for Cloud Apps_

Microsoft Cloud App Security is a Cloud Access Security Broker (CASB) that operates on multiple clouds. It provides rich visibility, control over data travel, and sophisticated analytics to identify and combat cyberthreats across all your cloud services.

**13 operation(s)**:

_investigation_
- `close_benign([id: text], [comment: text], [reasonId: select], [sendFeedback: checkbox])` — Close Benign
- `close_false_positive([id: text], [comment: text], [reasonId: select], [sendFeedback: checkbox])` — Close False Positive
- `close_true_positive([id: text], [comment: text], [sendFeedback: checkbox])` — Close True Positive
- `fetch_activity(activity_id: text)` — Fetch Activity
- `fetch_alert(alertId: text)` — Fetch Alert
- `fetch_entity(id: text, saas: text, inst: text)` — Fetch Entity
- `fetch_file(file_id: text)` — Fetch File
- `list_activities([alertId: text], [administrative_activity: checkbox], [impersonated_activity: checkbox], [malware_activity: checkbox], [sortField: select], [sortDirection: select], [limit: integer], [skip: integer], [custom_filter: json])` — List Activities
- `list_alerts([read: checkbox], [sortField: select], [sortDirection: select], [limit: integer], [skip: integer], [custom_filter: json])` — List Alerts
- `list_entities([isExternal: select], [status: select], [type: select], [sortField: select], [sortDirection: select], [limit: integer], [skip: integer], [custom_filter: json])` — List Entities
- `list_files([fileType: select], [trashed: checkbox], [quarantined: checkbox], [limit: integer], [skip: integer], [custom_filter: json])` — List Files
- `mark_alert_as_read(alertId: text)` — Mark Alert as Read
- `mark_alert_as_unread(alertId: text)` — Mark Alert as Unread


### `protectwise` v1.0.0 _(installed)_
_ProtectWise_

This connector integrate with ProtectWise and perform investigative actions

**4 operation(s)**:

_investigation_
- `domain_reputation(domain: text, sources: text, [start: datetime], [end: datetime], [details: text], [include: select])` — Domain Reputation
- `file_reputation(filehash: text, [start: datetime], [end: datetime], [sources: text])` — File Reputation
- `get_pcap(packet_type: select, object_id: text, sensor_id: text)` — Get PCAP
- `ip_reputation(ip: text, sources: text, [start: datetime], [end: datetime], [details: text], [include: select])` — IP Reputation


### `url-expander` v1.0.0 _(installed)_
_URL Expander_

URL Expander allows to retrieve original URL from shortened provided by various shortening services

**1 operation(s)**:

_investigation_
- `expand_url(url: text)` — Expand URL


---

## Logging

### `coralogix` v1.0.0 _(installed)_
_Coralogix_

Coralogix is a modern log analytics platform that provides real-time insights and monitoring for your log data. It offers advanced indexing, querying, and visualization capabilities, enabling users to efficiently manage and analyze log data from various sources. With features such as anomaly detection, alerting, and machine learning-powered insights, Coralogix helps organizations enhance their observability, troubleshoot issues faster, and improve overall system performance and security.

**1 operation(s)**:

_investigation_
- `search_archived_logs([query: text], [start_date: datetime], [end_date: datetime], [metadata: json])` — Search Archived Logs


### `google-cloud-logging` v1.0.0 _(installed)_
_Google Cloud Logging_

Cloud Logging is a fully managed service that allows you to store, search, analyze, monitor, and alert on logging data and events from Google Cloud.

**3 operation(s)**:

_investigation_
- `get_exclusions_list(resourceNames: text, [pageSize: integer], [pageToken: text])` — Get Exclusions List
- `get_log_entries_list(resourceNames: text, [filter: text], [orderBy: select], [pageSize: integer], [pageToken: text])` — Get Log Entries List
- `get_sinks_list(resourceNames: text, [filter: text], [pageSize: integer], [pageToken: text])` — Get Sinks List


---

## ML Service

### `anything-llm` v1.0.0 _(installed)_
_Anything LLM_

This connector is providing automation actions for Anything LLM that supports using Retrieval Augmented Generation (RAG) with an LLM and user documents embedded in a vector DB. The LLM and vector DB can be fully local for maximum data privacy or configured to use cloud-based services such as OpenAI. A variety of LLMs and vector DBs are supported. Anything LLM itself can be installed on customer infrastructure or accessed as a cloud service.

**15 operation(s)**:

_investigation_
- `add_workspace_embedding(workspace_name: text, folder_name: text, doc_name: text)` — Add Workspace Embedding
- `create_document_folder(folder_name: text)` — Create Folder in Documents
- `create_workspace(workspace_name: text)` — Create Workspace
- `delete_document(folder_name: text, doc_name: text)` — Delete Document
- `delete_workspace_embedding(workspace_name: text, folder_name: text, doc_name: text)` — Remove Workspace Embedding
- `get_document(doc_name: text)` — Get Document by Name
- `get_documents()` — Get Documents List
- `get_workspace(workspace_name: text)` — Get Workspace by Slug
- `get_workspace_list()` — Get Workspace List
- `move_document(src_folder_name: text, dest_folder_name: text, doc_name: text)` — Move Document
- `update_workspace_settings(workspace_name: text, settings_data: json)` — Update Workspace Settings
- `upload_document(file_type: select)` — Upload Document
- `upload_document_link(web_link: text)` — Upload Document Link
- `upload_document_text(plain_text: text, doc_title: text, description: text, author: text, source: text)` — Upload Document Text
- `workspace_chat(workspace_name: text, message: text, mode: select)` — Workspace Chat


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

### `anyrun` v1.1.0 _(installed)_
_ANY.RUN_

ANY.RUN connector performs actions like get history, get report, and run new analysis.

**6 operation(s)**:

_investigation_
- `get_available_environments()` — Get Available Environments
- `get_history([team: checkbox], [skip: text], [limit: text])` — Get History
- `get_report(task_uuid: text)` — Get Report
- `get_report_attachments(task_uuid: text)` — Get Report Attachments
- `get_user_limits()` — Get User Limits
- `run_analysis(run_by: multiselect)` — Run Analysis


### `crowdstrike-falcon-x` v1.1.1 _(installed)_
_CrowdStrike Falcon X_

FALCON X Automatically investigate incidents and accelerate alert triage and response. This connector facilitates the automated operations to Submit Files , URLs and to fetch the reports.

**8 operation(s)**:

_investigation_
- `get_analysis_status(report_ids: text)` — Get Analysis Status
- `get_full_report(report_ids: text)` — Get Full Report
- `get_report_summary(report_ids: text)` — Get Report Summary
- `search_reports([filter: text], [offset: integer], [limit: integer])` — Search Reports
- `search_submission_id([filter: text], [offset: integer], [limit: integer])` — Search Submission ID
- `submit_uploaded_file(Interactivity: checkbox, sha256: text, environment_id: select, [action_script: text], [command_line: text], [document_password: text], [enable_tor: checkbox], [submit_name: text], [system_date: datetime])` — Submit Uploaded File
- `submit_url(Interactivity: checkbox, url: text, environment_id: select, [action_script: text], [command_line: text], [document_password: text], [enable_tor: checkbox], [submit_name: text], [system_date: datetime])` — Submit URL
- `upload_file(file_name: text, comment: text, is_confidential: checkbox)` — Upload File


### `cuckoo` v1.1.0 _(installed)_
_Cuckoo_

Cuckoo sandbox is an open source software for automating analysis of suspicious files. To do so it makes use of custom components that monitor the behavior of the malicious processes while running in an isolated environment.

**3 operation(s)**:

_investigation_
- `get_report(taskid: text)` — Get Report
- `submit_file(file: text)` — Submit File
- `submit_url(url: text)` — Submit URL


### `ddan` v1.0.2 _(installed)_
_Trend Micro DDAN_

Trend Micro-Deep Discovery Analyzer for Network

**3 operation(s)**:

_investigation_
- `get_open_ioc_by_sha1(sha1: text)` — Get OpenIOC of Submitted Sample using SHA1
- `get_report_by_sha1(sha1: text, [report_json_format_sha1: checkbox])` — Get Sample Report using SHA1
- `submit_sample(filename: text, file_iri: text)` — Submit Sample to Trend Micro DDAN


### `hatching-triage` v1.0.0 _(installed)_
_Hatching Triage_

A state-of-the-art malware analysis sandbox, with all the features you need. High-volume sample submission in a customizable environment with detections and configuration extraction for many malware families.

**12 operation(s)**:

_investigation_
- `create_profile(name: text, tags: text, timeout: integer, [network: select])` — Create Profile
- `delete_profile(profile_id: text)` — Delete Profile
- `get_profiles()` — Get Profiles
- `get_report_triage(sample_id: text, task_id: text)` — Get Triage Report
- `get_sample(sample_id: text)` — Get Sample by ID
- `get_sample_summary(sample_id: text)` — Get Sample Summary
- `get_static_report(sample_id: text)` — Get Static Report
- `query_samples([subset: select])` — Query Samples
- `search_by_query(query: text)` — Search By Query
- `set_sample_profile(sample_id: text, [auto: checkbox], [pick: text], [profiles: text])` — Set Sample Profile
- `submit_sample(kind: select, [target: text], [interactive: checkbox], [password: text], [profiles: text], [user_tags: text], [timeout: integer], [network: select])` — Submit Sample
- `update_profile(profile_id: text, name: text, tags: text, timeout: integer, [network: select])` — Update Profile


### `hybrid-analysis` v2.1.0 _(installed)_
_Hybrid Analysis_

Hybrid Analysis provides a malware analysis service that allows users to automate the analysis of files and URLs for potential threats. This connector facilitates automated operations such as retrieving analysis reports, environment details, submitting files, submitting URLs, etc.

**13 operation(s)**:

_investigation_
- `conditional_search([filename: text], [filetype: text], [filetype_desc: text], [env_id: text], [verdict: select], [av_detect: text], [vx_family: text], [tag: text], [port: integer], [host: text], [domain: text], [url: text], [similar_to: text], [context: text], [date_from: datetime], [date_to: datetime], [imp_hash: text], [ssdeep: text], [authentihash: text], [uses_tactic: text], [uses_technique: text])` — Advanced Search
- `get_api_quota()` — Get API Quota
- `get_environment()` — Get Environment
- `get_feed()` — Get Latest Analysis Reports
- `get_report([job_id: text], [file_hash: text], [environmentId: integer])` — Get Analysis Report
- `get_sample_dropped_file([job_id: text], [file_hash: text], [environmentId: integer])` — Get Files Dropped by Sample
- `get_sample_screenshots([job_id: text], [file_hash: text], [environmentId: integer], [is_attach: checkbox])` — Get Sample Screenshot
- `get_submitted_sample_state([job_id: text], [file_hash: text], [environmentId: integer])` — Get Submission State
- `hashes_search(hashcodes: text)` — Get Analysis Report for Hashcode
- `quick_scan_by_id(id: text)` — Quick Scan by ID
- `submit_file(value: text, environment_id: integer, [priority: integer], [action_script: select], [network_settings: select], [hybrid_analysis: checkbox], [experimental_anti_evasion: checkbox], [script_logging: checkbox], [input_sample_tampering: checkbox], [email: text], [comment: text], [custom_date_time: datetime], [custom_cmd_line: text], [custom_run_time: integer], [submit_name: text], [document_password: password], [environment_variable: text])` — Submit File
- `submit_url(url: text, environment_id: integer, [priority: integer], [action_script: select], [hybrid_analysis: checkbox], [experimental_anti_evasion: checkbox], [script_logging: checkbox], [input_sample_tampering: checkbox], [network_settings: select], [email: text], [comment: text], [custom_date_time: datetime], [custom_cmd_line: text], [custom_run_time: integer], [submit_name: text], [document_password: password], [environment_variable: text])` — Submit URL
- `url_quick_scan(url_to_scan: text, [comment: text], [submit_name: text])` — Quick Scan URL


### `opswat-metadefender-core` v1.0.0 _(installed)_
_OPSWAT MetaDefender Core_

OPSWAT MetaDefender Core prevents malicious file uploads on web applications that bypass sandboxes and other detection-based security solutions. This connector facilitates operations to Submit File, Get Hashcode Reputation, Download Sanitized Files.

**3 operation(s)**:

_investigation_
- `download_sanitized_files(data_id: text)` — Download Sanitized Files
- `get_hashcode_reputation(hashcode: text)` — Get Hashcode Reputation
- `submit_file(submit_type: select)` — Submit File


### `reversinglabs-a1000` v1.0.0 _(installed)_
_ReversingLabsA1000_

ReversingLabs A1000 Malware Analysis

**3 operation(s)**:

- `get_report(file_hash: text)` — Get Report using File Hash
- `re_analyze_sample(file_hash: text)` — Re-analyze Sample using File Hash
- `upload_sample(file_iri: text)` — Upload Sample


### `wildfire` v1.1.1 _(installed)_
_PaloAlto WildFire_

This Connector supports executing investigative actions like verdict, detonate file and detonate url to analyze executables and URLs on the PaloAlto Wildfire sandbox.

**6 operation(s)**:

_investigation_
- `get_file_hash_report(hash: text)` — Get File Hash Report
- `get_file_hash_verdict(hash: text)` — Get File Hash Verdict
- `get_url_report(url: text)` — Get URL Report
- `get_url_verdict(url: text)` — Get URL Verdict
- `submit_file(value: text)` — Submit File
- `submit_url(url: text)` — Submit URL


---

## Managed Security Services

### `symantec-mss` v1.0.0 _(installed)_
_Symantec MSS_

Symantec MSS connector provides actions like, list of incident/tickets, create request, query incident/tickets etc.

**20 operation(s)** (+8 hidden):

_investigation_
- `get_incident_organization()` — Get Organizations and Person List
- `incident_add_attachment(IncidentNumber: integer, input_value: text, [AttachmentComment: text], [file_details: checkbox])` — Incident Add Attachment
- `incident_get_attachment(IncidentNumber: integer, AttachmentNumber: integer)` — Get Incident Attachment
- `incident_get_list([Severity: multiselect], [SourceOrganization: text], [DestinationOrganization: text], [MaxIncidents: integer], [SourceIP: text], [Category: multiselect], [ExcludeCategory: multiselect], [incident_recent_list: checkbox], [EndTimeStampGMT: datetime])` — Get List of Incident
- `incident_query(IncidentNumber: integer, [MaxSignatures: integer], [incident_workflow_query: checkbox])` — Query Incident
- `ticket_get_attachment_contents(TicketID: text, AttachmentItemOID: text, IsAllAttachmentsRequried: checkbox)` — Get Ticket Attachment
- `ticket_get_attachment_list(TicketID: text)` — Get List of Ticket Attachment
- `ticket_get_list(StartTimeStampGMT: datetime, [EndTimeStampGMT: datetime], [Status: multiselect], [TicketCategory: multiselect], [Urgency: multiselect], [TicketID: text], [ClientReference: text], [Device: text], [RequestedByOrganization: multiselect], [AssignedToOrganization: multiselect], [MaxTickets: integer], [ticket_recent_list: checkbox])` — Get Ticket List
- `ticket_query(TicketID: text, [ClientReference: text])` — Query Ticket
- `update_incident_workflow(IncidentNumber: integer, Status: select, Resolution: select, Severity: select, isGroupUpdate: checkbox, [AssignedToOrganiztion: text], [AssignedToPerson: text], [Comments: text], [Reference: text])` — Update Incident Workflow
- `user_get_devices()` — Get User Devices

- `ticket_delete_attachments(ticketID: text, attachmentOIDList: text, [updateComment: text], [retryAttempts: integer])` — Delete Ticket Attachments


---

## Messaging

### `bandwidth` v1.0.0 _(installed)_
_Bandwidth_

Bandwidth is the only API platform provider that owns a Tier 1 network, giving you better quality, rates, and control.

**1 operation(s)**:

_investigation_
- `send_message(from: phone, to: text, text: text, send_message_by_version: select)` — Send Message


### `google-cloud-pub-sub` v1.0.0 _(installed, ingestion)_
_Google Cloud Pub/Sub_

Google Cloud Pub/Sub is a fully-managed real-time messaging service
  that enables you to send and receive messages between independent applications.

**20 operation(s)**:

_investigation_
- `acknowledge_messages_from_subscriptions(subscription: text, ackIds: text)` — Acknowledge Messages from Subscriptions
- `create_snapshots(project_id: text, snap: text, subscription: text, [labels: json])` — Create Snapshots
- `create_subscription(project_id: text, subscription: text, topic: text, [messageRetentionDuration: integer], [retainAckedMessages: checkbox], [enableMessageOrdering: checkbox], [labels: json])` — Create Subscription
- `create_topic(project_id: text, topic: text, [labels: json], [allowedPersistenceRegions: text], [kmsKeyName: text])` — Create Topic
- `delete_snapshots(snapshot: text)` — Delete Snapshots
- `delete_subscription(subscription: text)` — Delete Subscription
- `delete_topic(topic: text)` — Delete Topic
- `get_subscription_details(subscription: text)` — Get Subscription Details
- `get_topic_details(topic: text)` — Get Topic Details
- `list_all_snapshots(project_id: text, [pageSize: integer], [pageToken: text])` — List All Snapshots
- `list_all_subscriptions(project_id: text, [pageSize: integer], [pageToken: text])` — List All Subscriptions
- `list_all_topic_snapshots(topic: text, [pageSize: integer], [pageToken: text])` — List All Topic Snapshots
- `list_all_topic_subscriptions(topic: text, [pageSize: integer], [pageToken: text])` — List All Topic Subscriptions
- `list_all_topics(project_id: text, [pageSize: integer], [pageToken: text])` — List All Topics
- `publish_messages_to_topic(topic: text, messages: json)` — Publish Messages to Topic
- `pull_messages_from_subscriptions(subscription: text, maxMessages: integer)` — Pull Messages from Subscriptions
- `seeks_subscriptions(subscription: text, [time: datetime], [snapshot: text])` — Seeks Subscriptions
- `update_snapshots(snapshot_name: text, topic: text, updateMask: text, [labels: json])` — Update Snapshots
- `update_subscription(subscription: text, topic: text, updateMask: text, [messageRetentionDuration: integer], [retainAckedMessages: checkbox], [labels: json])` — Update Subscription
- `update_topic(topic: text, updateMask: text, [labels: json], [allowedPersistenceRegions: text], [kmsKeyName: text])` — Update Topic


---

## Miscellaneous

### `chatsonic` v1.0.0 _(installed)_
_Writesonic Chatsonic_

This integration supports Writesonic's Chatsonic generative AI. A powerful language model with real time data

**2 operation(s)**:

_miscellaneous_
- `chat_completions(param@input_text: text, [param@google_enabled: checkbox], [param@language: select])` — Ask a Question
- `chat_conversation(param@input_text: text, param@history_data: json, [param@google_enabled: checkbox], [param@language: select])` — Converse With Chatsonic


### `google-bard` v2.0.0 _(installed)_
_Google Gemini_

Google Gemini is a conversational AI chatbot, based initially on the LaMDA family of large language models and later the PaLM LLM.

**6 operation(s)**:

_investigation_
- `count_message_token(name: text, messages: json, [context: text], [examples: json])` — Count Message Token
- `generate_embeddings(name: text, text: text)` — Generate Embedding
- `generate_message(name: text, messages: json, [context: text], [examples: json], [temperature: text], [candidate_count: integer], [topP: text], [topK: integer])` — Generate Message
- `generate_text(name: text, text: text, [safetySettings: json], [stopSequences: text], [temperature: text], [candidate_count: integer], [maxOutputTokens: integer], [topP: text], [topK: integer])` — Generate Text
- `get_model_details(name: text)` — Get Model Details
- `list_models([pageSize: integer], [pageToken: text])` — Get All Model List


### `microsoft-bing` v1.0.0 _(installed)_
_Microsoft Bing_

Microsoft Bing is a web search engine it provides a standard web search, as well as specialized searches for images, videos, shopping, news, maps, and other categories.

**1 operation(s)**:

_investigation_
- `web_search(q: text, [freshness: text], [responseFilter: multiselect], [answerCount: integer], [promote: multiselect], [safeSearch: select], [textDecorations: checkbox], [setLang: select], [cc: multiselect], [count: integer], [offset: integer], [additional_fields: json])` — Web Search


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

### `atlassian-status-page` v1.0.0 _(installed)_
_Atlassian Status Page_

This connector enables automated operations such as creating incidents, retrieving incident lists, managing active maintenances, and more.

**11 operation(s)**:

_investigation_
- `create_incident(page_id: text, name: text, [status: select], [impact_override: select], [body: textarea], [deliver_notifications: checkbox], [components: json], [component_ids: text], [metadata: json], [additional_fields: json])` — Create Incident
- `delete_incident(page_id: text, incident_id: text)` — Delete Incident
- `get_active_maintenance(page_id: text, [per_page: integer], [page: integer])` — Get Active Maintenance Incidents
- `get_incident(page_id: text, incident_id: text)` — Get Incident
- `get_list_incidents(page_id: text, [q: text], [limit: integer], [page: integer])` — Get Incident List
- `get_list_status_pages()` — Get Status Pages
- `get_scheduled_incidents(page_id: text, [per_page: integer], [page: integer])` — Get Scheduled Incidents
- `get_unresolved_incidents(page_id: text, [per_page: integer], [page: integer])` — Get Unresolved Incidents
- `get_upcoming_incidents(page_id: text, [per_page: integer], [page: integer])` — Get Upcoming Incidents
- `update_incident(page_id: text, incident_id: text, [name: text], [status: select], [impact_override: select], [body: textarea], [deliver_notifications: checkbox], [components: json], [component_ids: text], [metadata: json], [additional_fields: json])` — Update Incident

_utilities_
- `execute_api_request(endpoint: text, method: select, [query_params: json], [payload: json])` — Execute an API Request


### `aws-cloudwatch-log` v1.0.0 _(installed)_
_AWS CloudWatch Log_

AWS CloudWatch Log helps you monitor, store, and access your system, application, and custom log files. This connector facilitates the automate operations related to the log group, log streams and metrics.

**13 operation(s)**:

_investigation_
- `get_list_log_groups([assume_role: checkbox], [logGroupNamePrefix: text], [nextToken: text], [limit: integer])` — Get Log Groups List
- `get_list_log_streams([assume_role: checkbox], logGroupName: text, [orderBy: select], [nextToken: text], [limit: integer])` — Get Log Streams List
- `get_log_events([assume_role: checkbox], logGroupName: text, logStreamName: text, [startTime: datetime], [endTime: datetime], [nextToken: text], [limit: integer], [startFromHead: checkbox])` — Get Log Events
- `get_log_insight_query_result([assume_role: checkbox], queryId: text)` — Get Log Insight Query Result
- `run_log_insight_query([assume_role: checkbox], logGroupNames: text, startTime: datetime, endTime: datetime, queryString: text, [limit: integer])` — Run Log Insight Query

_miscellaneous_
- `create_log_group([assume_role: checkbox], logGroupName: text, [kmsKeyId: text], [tags: json])` — Create Log Group
- `create_log_stream([assume_role: checkbox], logGroupName: text, logStreamName: text)` — Create Log Stream
- `delete_log_group([assume_role: checkbox], logGroupName: text)` — Delete Log Group
- `delete_log_stream([assume_role: checkbox], logGroupName: text, logStreamName: text)` — Delete Log Stream
- `revert_log_retention_policy([assume_role: checkbox], logGroupName: text)` — Revert Log Retention Policy
- `stop_log_insight_query([assume_role: checkbox], queryId: text)` — Stop Log Insight Query
- `update_log_retention_policy([assume_role: checkbox], logGroupName: text, retentionInDays: select)` — Update Log Retention Policy
- `upload_log_event([assume_role: checkbox], logGroupName: text, logStreamName: text, timestamp: datetime, message: text, [sequenceToken: text])` — Upload Log Event


### `ibm-security-guardium-insights` v1.0.0 _(installed)_
_IBM Security Guardium Insights_

IBM Security Guardium Insights is a data security platform that provides real-time monitoring, analysis, and protection for sensitive information across hybrid cloud environments. It helps organizations identify and prioritize potential threats, ensuring data privacy and compliance by detecting unusual activities and vulnerabilities. With its advanced analytics and machine learning capabilities, Guardium Insights helps businesses safeguard critical data assets from unauthorized access, ensuring data integrity and reducing the risk of data breaches.

**15 operation(s)**:

_investigation_
- `get_cases_list([case_id: text], [limit: integer], [offset: integer])` — Get Cases List
- `get_compliance_data()` — Get Compliance Data
- `get_connections_list([account_id: text], [access_key: text])` — Get Connections List
- `get_dataset_data(dataset_name: text, [limit: integer], [offset: integer])` — Get Dataset Data
- `get_datasets_list([filter.start_time: datetime], [filter.end_time: datetime], [limit: integer], [offset: integer])` — Get Datasets List
- `get_group_members_list(group_id: text)` — Get Group Members List
- `get_groups_list()` — Get Groups List
- `get_notifications_list([filter.start_time: datetime], [filter.end_time: datetime], [filter.state: select], [limit: integer], [offset: integer])` — Get Notifications List
- `get_policies_list()` — Get Policies List
- `get_policy_details(policy_id: text)` — Get Policy Details
- `get_report_categories_list([report_id: text])` — Get Report Categories List
- `get_reports_list([category_id: text])` — Get Reports List
- `get_scheduled_job_details(schedule_id: text)` — Get Scheduled Job Details
- `get_schedules_list([Limit: integer], [Offset: integer])` — Get Schedules List
- `get_tasks_list(case_id: text, [task_id: text])` — Get Tasks List


### `kaseya` v1.0.0 _(installed)_
_Kaseya_

Kaseya is IT management and monitoring tool used to perform operations for agent procedure, audit and patch scan.

**11 operation(s)**:

_investigation_
- `cancel_agent_procedure(agentId: text, agentProcId: text)` — Cancel Agent Procedure
- `get_addremoveprograms(agentId: text)` — Get List of All Add/Remove Programs
- `get_agent_procedures()` — Get Agent Procedures
- `get_agents()` — Get Agents
- `get_audit_summary(agentId: text)` — Get Audit Summary
- `get_patch_status(agentId: text)` — Get Patch Status
- `run_agent_procedure(agentId: text, agentProcId: text)` — Run Agent Procedure
- `run_latest_audit(agentId: text)` — Run Latest Audit
- `run_patch_scan([agentId: text])` — Run Patch Scan
- `schedule_agent_procedure(agentId: text, agentProcId: text, Recurrence_Repeat: select, Distribution_Interval: select, Distribution_Magnitude: integer, Recurrence_DaysOfWeek: multiselect, Start_StartOn: datetime, Recurrence_EndOn: datetime, [Recurrence_Times: integer], [ServerTimeZone: checkbox], [SkipIfOffLine: checkbox], [PowerUpIfOffLine: checkbox])` — Schedule Agent Procedure
- `schedule_latest_audit(agentId: text, Recurrence_Repeat: select, Distribution_Interval: select, Distribution_Magnitude: integer, Recurrence_DaysOfWeek: multiselect, Start_StartOn: datetime, Recurrence_EndOn: datetime, [Recurrence_Times: integer], [ServerTimeZone: checkbox], [SkipIfOffLine: checkbox], [PowerUpIfOffLine: checkbox])` — Schedule Latest Audit


### `logicmonitor` v1.0.0 _(installed)_
_LogicMonitor_

LogicMonitor is a SaaS-based performance monitoring platform that provides full visibility into complex, hybrid infrastructures, offering granular performance monitoring and actionable data and insights. This connector enables automated operations such as Get Alert List, Get Device Group List, Get Device List, Get Device Alerts, Get Report List, and Get Report by ID.

**6 operation(s)**:

_investigation_
- `get_alert_list([filter: text], [fields: text], [size: integer], [offset: integer])` — Get Alert List
- `get_device_alerts(id: integer, [start: integer], [end: integer], [netflowFilter: text], [needMessage: checkbox], [customColumns: text], [bound: text], [filter: text], [fields: text], [size: integer], [offset: integer])` — Get Device Alerts
- `get_device_group_list([filter: text], [fields: text], [size: integer], [offset: integer])` — Get Device Group List
- `get_device_list([start: integer], [end: integer], [netflowFilter: text], [filter: text], [includeDeletedResources: checkbox], [fields: text], [size: integer], [offset: integer])` — Get Device List
- `get_report_by_id(id: integer, [fields: text])` — Get Report by ID
- `get_report_list([filter: text], [fields: text], [size: integer], [offset: integer])` — Get Report List


### `sumo-logic` v1.1.1 _(installed)_
_Sumo Logic_

Sumo Logic provides best-in-class cloud monitoring, log management, Cloud SIEM tools, and real-time insights for web and SaaS based apps.

**8 operation(s)**:

_investigation_
- `create_search_job(query: text, from: datetime, to: datetime, timeZone: text)` — Create Search Job
- `delete_search_job(searchJobId: text, cookies: text)` — Delete Search Job
- `get_details_by_insights_id(insights_id: text)` — Get Details By Insights ID
- `get_list_of_all_insights()` — Get the List of All Insights
- `get_list_of_insights_by_query([query: text], [offset: integer], [limit: integer], recordSummaryFields: text)` — Get the List of Insights By Query
- `get_messages_founded_by_search_job(searchJobId: text, offset: integer, limit: integer, cookies: text)` — Get Messages Founded by Search Job
- `get_records_founded_by_search_job(searchJobId: text, offset: integer, limit: integer, cookies: text)` — Get Records Founded by Search Job
- `get_search_job_status(searchJobId: text, cookies: text)` — Get Search Job Status


### `zabbix` v1.0.0 _(installed, ingestion)_
_Zabbix_

Zabbix is an open-source, enterprise-grade monitoring platform that provides real-time visibility into the performance and availability of IT infrastructure, including servers, networks, applications, services, and cloud environments.

**4 operation(s)**:

_investigation_
- `execute_generic_rest_api_call()` — Execute Generic JSON RPC Request
- `get_alerts([start_date: datetime], [end_date: datetime], [alert_ids: text], [action_ids: text], [event_ids: text], [group_ids: text], [host_ids: text], [user_ids: text], [object_ids: text], [event_object_type: select], [event_source: select], [sort_field: multiselect], [sortorder: select], [limit: integer], [search: json], [search_any: checkbox], [search_wildcards_enabled: checkbox], [filter: json], [additional_fields: json])` — Get Alerts
- `get_events([start_date: datetime], [end_date: datetime], [event_ids: text], [group_ids: text], [host_ids: text], [object_ids: text], [event_object_type: select], [source: select], [acknowledged: checkbox], [suppressed: checkbox], [severities: text], [event_id_from: text], [event_id_till: text], [sort_field: multiselect], [sortorder: select], [limit: integer], [search: json], [filter: json], [additional_fields: json])` — Get Events
- `get_problems([start_date: datetime], [end_date: datetime], [fetch_alert: checkbox], [severities: multiselect], [event_ids: text], [group_ids: text], [host_ids: text], [object_ids: text], [object: select], [source: select], [acknowledged: checkbox], [suppressed: checkbox], [event_id_from: text], [event_id_till: text], [sort_field: select], [sortorder: select], [limit: integer], [filter: json], [search: json], [additional_fields: json])` — Get Problems


---

## Network Access Control

### `cisco-ise` v2.1.1 _(installed)_
_Cisco ISE_

Cisco ISE connector provides actions like, list all active sessions, quarantine IP/Mac address, un-quarantine IP/Mac address etc.

**21 operation(s)**:

_containment_
- `assign_policy(policyName: text, apply_to: select)` — Assign ANC Policy
- `create_anc_policy(name: text, actions: multiselect)` — Create ANC Policy
- `disable_internal_user(filter.name: text)` — Disable Internal User
- `enable_internal_user(filter.name: text)` — Enable Internal User
- `quarantine_ip(target_ipaddr: text)` — EPS: Quarantine IP Address
- `quarantine_mac(target_mac: text)` — EPS: Quarantine MAC Address
- `reinstate_guest_user(filter.name: text)` — Reinstate Guest User
- `suspend_guest_user(filter.name: text)` — Suspend Guest User
- `unquarantine_ip(target_ipaddr: text)` — EPS: Un-Quarantine IP Address
- `unquarantine_mac(target_mac: text)` — EPS: Un-Quarantine MAC Address

_investigation_
- `get_anc_endpoint([id: text], [size: integer], [page: integer])` — Get ANC Endpoint
- `get_anc_policy([get_policy_by: select], [size: integer], [page: integer])` — Get ANC Policy
- `get_guest_user_details(userid: text)` — Get Guest User Details
- `get_internal_user_details(userid: text)` — Get Internal User Details
- `get_ise_endpoint([get_endpoint_by: select], [size: integer], [page: integer])` — Get Endpoints
- `list_active_sessions()` — List All Active Sessions
- `list_guest_users([filter.name: text], [filter.firstName: text], [filter.lastName: text], [filter.emailAddress: text], [filter.sponsorUserName: text], [filter.company: text], [filter.phoneNumber: text], [size: integer], [page: integer])` — List Guest Users
- `list_internal_users([filter.name: text], [filter.firstName: text], [filter.lastName: text], [filter.email: text], [size: integer], [page: integer])` — List Internal Users

_miscellaneous_
- `end_session(target_mac: text)` — End a Target MAC Address Session
- `log_system_off(target_mac: text, target_server: text)` — MAC Address Logout

_remediation_
- `revoke_policy(policyName: text, revoke_from: select)` — Revoke ANC Policy


### `fortinet-fortinac` v1.0.0 _(installed)_
_Fortinet FortiNAC_

FortiNAC is the Fortinet network access control solution. It enhances the overall Fortinet Security Fabric with visibility, control, and automated response.

**5 operation(s)**:

_contentment_
- `isolate_device(action: select)` — Isolate Device

_investigation_
- `get_active_hosts([query: text])` — Get Active Hosts
- `get_host_information(filter_attribute: select, value: text)` — Get Host Information
- `get_policies(policy_type: select, [id: text])` — Get Policies
- `update_host_properties(host_id: text, fields: json)` — Update Host Properties


---

## Network Analysis and Monitoring

### `pcap-tools` v1.0.0 _(installed)_
_PCAP Tools_

PCAP Tools decodes a pcap file and converts it to human readable format

**1 operation(s)**:

_investigation_
- `pcap_to_json(file_iri: text)` — PCAP To JSON


---

## Network Monitoring

### `centreon` v1.0.0 _(installed)_
_Centreon_

Centreon is a user-friendly and powerful monitoring platform. This connector allows you to actions related to hosts host like get host, add host, delete host and get host parent

**26 operation(s)**:

_investigation_
- `add_contact(hostname: text, contact_name: text)` — Add Contact
- `add_host(hostname: text, host_alias: text, ip: text, [poller: text], [template: text])` — Add Host
- `add_host_group(host_name: text, host_group_name: text)` — Add Host Group
- `add_parent(hostname: text, parent_name: text)` — Add Parent
- `add_template(hostname: text, template_name: text)` — Add Template
- `delete_contact(hostname: text, contact_name: text)` — Delete Contact
- `delete_host(hostname: text)` — Delete Host
- `delete_host_group(host_name: text, host_group_name: text)` — Delete Host Group
- `delete_macro(hostname: text, macro_name: text)` — Delete Macro
- `delete_parent(hostname: text, parent_name: text)` — Delete Parent
- `delete_template(hostname: text, template_name: text)` — Delete Template
- `disable_host(host_name: text)` — Disable Host
- `enable_host(host_name: text)` — Enable Host
- `get_contacts(hostname: text)` — Get Contacts
- `get_host()` — Get Hosts
- `get_host_group(host_name: text)` — Get Host Groups
- `get_host_status([sortType: select], [viewType: select], [limit: integer])` — Get Hosts Status
- `get_macro(hostname: text)` — Get Macro
- `get_parent(hostname: text)` — Get Parent
- `get_service_status([sortType: select], [viewType: select], [limit: integer])` — Get Service Status
- `get_templates(hostname: text)` — Get Templates
- `set_contact(hostname: text, contact_name: text)` — Set Contact
- `set_host_group(host_name: text, host_group_name: text)` — Set Host Group
- `set_macro(hostname: text, macro_name: text, macro_value: text)` — Set Macro
- `set_parent(hostname: text, parent_name: text)` — Set Parent
- `set_template(hostname: text, template_name: text)` — Set Template


### `prtg` v1.1.0 _(installed)_
_PRTG_

PRTG is a powerful monitoring solution that analyzes your entire IT infrastructure, monitors your network, performance, hardware, cloud, databases, applications etc.

**8 operation(s)**:

_investigation_
- `acknowledge_alarm(id: text, [ackmsg: text], [duration: select])` — Acknowledge Alarm
- `get_sensor_status(id: text)` — Get Sensor Status
- `list_object_detail(content: select, [response_fields: multiselect], [open_filter: text], [start: integer], [count: integer], [sortby: text])` — List Object Details
- `pause_sensor(id: text, [duration: integer], [pausemsg: text])` — Pause Sensor
- `resume_sensor(id: text)` — Resume Sensor
- `run_auto_discovery(discovery: select, id: text)` — Run Auto Discovery
- `scan_sensor(id: text)` — Scan Sensor

_remediation_
- `delete_object(object: select, id: text)` — Delete Object


---

## Network Protection

### `seclytics-augur-pxdr` v1.1.0 _(installed)_
_Seclytics Augur pXDR_

Seclytics Augur pXDR: This FortiSOAR connector interacts with Seclytics Augur pXDR API. It can perform IOC lookup for threat context enrichment for threat investigation. It can also download SecLytics' unique predictive threat intel for automated network security response.

**4 operation(s)**:

_investigation_
- `query_domain(domain: text)` — Get Domain Reputation
- `query_file(file_hash: text)` — Get File Reputation
- `query_host(host: text)` — Get Host Reputation

_miscellaneous_
- `download_predictions([file_name: text])` — Download Predictions


---

## Network Security

### `akamai` v1.0.0 _(installed)_
_Akamai Prolexic_

Akamai is an American content delivery network (CDN), cybersecurity, and cloud service company, providing web and Internet security services.

**4 operation(s)**:

_investigation_
- `get_an_attack_report(attackId: integer, contract: text)` — Get An Attack Report
- `list_attack_reports(start: datetime, end: datetime, contract: text)` — List Attack Reports
- `list_critical_events(contract: text)` — List Critical Events
- `list_events(contract: text)` — List Events


### `arbor-aed` v1.1.0 _(installed)_
_Netscout AED_

Netscout Arbor Edge Defense (AED) secures the internet data center edge from threats against availability — specifically from application-layer, distributed denial of service (DDoS) attacks.

**26 operation(s)**:

_investigation_
- `add_inbound_blacklist_countries(country: text, [cid_pgid: select], [annotation: text])` — Add Inbound Blacklist Countries
- `add_inbound_blacklist_domains(domain: text, [cid_pgid: select], [annotation: text])` — Add Inbound Blacklist Domains
- `add_inbound_blacklist_hosts(hostAddress: text, [cid_pgid: select], [annotation: text])` — Add Inbound Blacklist Hosts
- `add_inbound_blacklist_urls(url: text, [cid_pgid: select], [annotation: text])` — Add Inbound Blacklist URLs
- `add_inbound_whitelisted_hosts(hostAddress: text, [cid_pgid: select], [annotation: text])` — Add Inbound Whitelisted Hosts
- `add_outbound_blacklist_hosts(hostAddress: text, [cid_pgid: select], [annotation: text])` — Add Outbound Blacklist Hosts
- `add_outbound_whitelisted_hosts(hostAddress: text, [cid_pgid: select], [annotation: text])` — Add Outbound Whitelist Hosts
- `create_inbound_protection_groups(name: text, prefixes: text, serverType: integer, [description: text], [active: checkbox], [protectionLevel: select])` — Create Inbound Protection Groups
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_countries([q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Countries
- `get_inbound_blacklisted_countries([country: text], [cid_pgid: select], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Inbound Blacklisted Countries
- `get_inbound_blacklisted_domains([domain: text], [cid_pgid: select], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Inbound Blacklisted Domains
- `get_inbound_blacklisted_hosts([hostAddress: text], [cid_pgid: select], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Inbound Blacklisted Hosts
- `get_inbound_blacklisted_urls([url: text], [cid_pgid: select], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Inbound Blacklisted URLs
- `get_inbound_protection_groups([pgid: integer], [name: text], [description: text], [timeCreated: datetime], [active: select], [protectionLevel: select], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Inbound Protection Groups
- `get_inbound_whitelisted_hosts([hostAddress: text], [cid_pgid: select], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Inbound Whitelisted Hosts
- `get_outbound_blacklisted_hosts([hostAddress: text], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Outbound Blacklisted Hosts
- `get_outbound_whitelisted_hosts([hostAddress: text], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Outbound Whitelisted Hosts
- `remove_inbound_blacklisted_countries(country: text, [cid_pgid: select])` — Remove Inbound Blacklisted Countries
- `remove_inbound_blacklisted_domains(domain: text, [cid_pgid: select])` — Remove Inbound Blacklisted Domains
- `remove_inbound_blacklisted_hosts(hostAddress: text, [cid_pgid: select])` — Remove Inbound Blacklisted Hosts
- `remove_inbound_blacklisted_urls(url: text, [cid_pgid: select])` — Remove Inbound Blacklisted URLs
- `remove_inbound_whitelisted_hosts(hostAddress: text, [cid_pgid: select])` — Remove Inbound Whitelisted Hosts
- `remove_outbound_blacklisted_hosts(hostAddress: text, [cid_pgid: select])` — Remove Outbound Blacklisted Hosts
- `remove_outbound_whitelisted_hosts(hostAddress: text, [cid_pgid: select])` — Remove Outbound Whitelisted Hosts
- `update_inbound_protection_groups(pgid: text, [active: checkbox], [protectionLevel: select])` — Update Inbound Protection Groups


### `arbor-aps` v2.0.0 _(installed)_
_Arbor APS_

Arbor APS connector perform automated operations, such as retrieving all DDoS alerts or alerts based on the search criteria you have specified from Arbor APS, or retrieving network summary reports using various filters you have specified from Arbor APS.

**25 operation(s)**:

_investigation_
- `add_inbound_blacklist_countries(country: text, [cid_pgid: select])` — Add Inbound Blacklist Countries
- `add_inbound_blacklist_domains(domain: text, [cid_pgid: select])` — Add Inbound Blacklist Domains
- `add_inbound_blacklist_hosts(hostAddress: text, [cid_pgid: select])` — Add Inbound Blacklist Hosts
- `add_inbound_blacklist_urls(url: text, [cid_pgid: select])` — Add Inbound Blacklist URLs
- `add_inbound_whitelisted_hosts(hostAddress: text, [cid_pgid: select])` — Add Inbound Whitelisted Hosts
- `add_outbound_blacklist_hosts(hostAddress: text)` — Add Outbound Blacklist Hosts
- `add_outbound_whitelisted_hosts(hostAddress: text)` — Add Outbound Whitelist Hosts
- `create_inbound_protection_groups(name: text, prefixes: text, serverType: integer, [description: text], [active: checkbox], [protectionLevel: select])` — Create Inbound Protection Groups
- `get_countries([sort_param: text], [q: text], [select: text], [direction: select], [page: integer], [perPage: integer])` — Get Countries
- `get_inbound_blacklisted_countries([country: text], [cid_pgid: select], [updateTime: datetime], [sort_param: text], [q: text], [select: text], [direction: select], [page: integer], [perPage: integer])` — Get Inbound Blacklisted Countries
- `get_inbound_blacklisted_domains([domain: text], [cid_pgid: select], [updateTime: datetime], [sort_param: text], [q: text], [select: text], [direction: select], [page: integer], [perPage: integer])` — Get Inbound Blacklisted Domains
- `get_inbound_blacklisted_hosts([hostAddress: text], [cid_pgid: select], [updateTime: datetime], [sort_param: text], [q: text], [select: text], [direction: select], [page: integer], [perPage: integer])` — Get Inbound Blacklisted Hosts
- `get_inbound_blacklisted_urls([url: text], [cid_pgid: select], [updateTime: datetime], [sort_param: text], [q: text], [select: text], [direction: select], [page: integer], [perPage: integer])` — Get Inbound Blacklisted URLs
- `get_inbound_protection_groups([pgid: integer], [name: text], [description: text], [timeCreated: datetime], [active: select], [protectionLevel: select], [direction: select], [page: integer], [perPage: integer], [other_fields: json])` — Get Inbound Protection Groups
- `get_inbound_whitelisted_hosts([hostAddress: text], [cid_pgid: select], [updateTime: datetime], [sort_param: text], [q: text], [select: text], [direction: select], [page: integer], [perPage: integer])` — Get Inbound Whitelisted Hosts
- `get_outbound_blacklisted_hosts([hostAddress: text], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer])` — Get Outbound Blacklisted Hosts
- `get_outbound_whitelisted_hosts([hostAddress: text], [updateTime: datetime], [q: text], [select: text], [sort_param: text], [direction: select], [page: integer], [perPage: integer])` — Get Outbound Whitelisted Hosts
- `remove_inbound_blacklisted_countries(country: text, [cid_pgid: select])` — Remove Inbound Blacklisted Countries
- `remove_inbound_blacklisted_domains(domain: text, [cid_pgid: select])` — Remove Inbound Blacklisted Domains
- `remove_inbound_blacklisted_hosts(hostAddress: text, [cid_pgid: select])` — Remove Inbound Blacklisted Hosts
- `remove_inbound_blacklisted_urls(url: text, [cid_pgid: select])` — Remove Inbound Blacklisted URLs
- `remove_inbound_whitelisted_hosts(hostAddress: text, [cid_pgid: select])` — Remove Inbound Whitelisted Hosts
- `remove_outbound_blacklisted_hosts(hostAddress: text)` — Remove Outbound Blacklisted Hosts
- `remove_outbound_whitelisted_hosts(hostAddress: text)` — Remove Outbound Whitelisted Hosts
- `update_inbound_protection_groups(pgid: text, [active: checkbox], [protectionLevel: select])` — Update Inbound Protection Groups


### `arkime` v1.0.0 _(installed)_
_Arkime_

Arkime is an open-source, large-scale, full packet capture (FPC) and indexing system. It's designed for security professionals to store and analyze network traffic in detail.

**14 operation(s)**:

_investigation_
- `add_tags_to_sessions([ids: text], [tags: text], [segments: text], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Add Tags to Sessions
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_all_connections([srcField: text], [dstField: text], [baselineDate: select], [baselineVis: select], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All Connections
- `get_all_connections_csv([srcField: text], [dstField: text], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All Connections CSV
- `get_all_fields([array: checkbox])` — Get All Fields
- `get_all_multiple_unique_fields([counts: integer], [exp: text], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All Multiple Unique Fields
- `get_all_pcap_files([length: integer], [start: integer])` — Get All PCAP Files
- `get_all_sessions([date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All Sessions
- `get_all_sessions_csv([ids: text], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All Sessions CSV
- `get_all_sessions_pcap([ids: text], [segments: checkbox], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All Sessions PCAP
- `get_all_spi_graph([date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All SPI Graph
- `get_all_spi_view([spi: text], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All SPI View
- `get_all_unique_fields([counts: integer], [exp: text], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Get All Unique Fields
- `remove_tags_from_sessions([ids: text], [tags: text], [segments: text], [date: integer], [expression: text], [view: text], [facets: integer], [startTime: datetime], [stopTime: datetime], [order: text], [fields: multiselect], [bounding: select], [length: integer], [start: integer])` — Remove Tags from Sessions


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


### `cisco-umbrella-enforcement` v3.0.1 _(installed)_
_Cisco Umbrella Enforcement_

Cisco Umbrella is a cloud security platform that provides the first line of defense against threats on the internet wherever users go. Cisco Umbrella Enforcement API allows partners and customers who have their own SIEM/Threat Intelligence Platform (TIP) environments to inject events and/or threat intelligence into their Umbrella environment.

**4 operation(s)**:

_investigation_
- `add_destination(listId: text, destinations: text, [comment: text])` — Add Destinations to Destination List
- `delete_destinations_from_list(listId: text, id: text)` — Delete Destinations from Destination List
- `get_destination_lists()` — Get All Destination List
- `list_destinations(listId: text, [page: integer], [limit: integer])` — Get Destinations in Destination List


### `commvault` v1.0.0 _(installed)_
_Commvault_

Commvault is an Intelligent Data Services platform which helps you close the business integrity gap, keeping your data available and ready for business growth. This connector facilitates operations to get alerts, get and update the user details.

**4 operation(s)**:

_investigation_
- `alert_details(alert_id: text)` — Get Alert Details
- `list_of_alerts()` — Get Alerts List
- `list_of_users([level: select])` — Get Users List
- `update_user(user_id: text, [description: text], [associatedUserGroupsOperationType: integer], [agePasswordDays: integer], [password: password], [email: email], [fullName: text], [enableUser: checkbox], [userGroupNames: text], [userName: text])` — Update User Details


### `darktrace` v1.4.0 _(installed)_
_Darktrace_

Darktrace is enterprise immune system for threat detecation. This connector provided automated operations for Get Watch List, Update Watch List, Get Incidents, Search Query, etc

**24 operation(s)**:

_Containment_
- `add_to_list(add_domain_ip_host: text)` — Add To Watch List

_investigation_
- `acknowledge_breach(pbid: text)` — Acknowledge Breach
- `create_manual_antigena(did: integer, action: select, duration: integer, [reason: text])` — Create Manual Antigena
- `execute_api_request(endpoint: text, method: select, [query_params: json], [payload: json])` — Execute an API Request
- `get_antigena([fulldevicedetails: checkbox], [includecleared: checkbox], [includehistory: checkbox], [needconfirming: checkbox], [starttime: datetime], [endtime: datetime], [from: datetime], [to: datetime], [includeconnections: checkbox], [responsedata: text], [pbid: integer])` — Get Antigena List
- `get_antigena_summary([starttime: datetime], [endtime: datetime], [responsedata: text])` — Get Antigena Summary
- `get_breach_details(pbid: text)` — Get Breach Details
- `get_comments(incident_id: text)` — Get Incident Comments
- `get_components([cid: text])` — Get Components
- `get_device_information(did: integer, datatype: select, [externaldomain: text], [fulldevicedetails: checkbox], [showallgraphdata: checkbox], [similardevices: integer], [port: integer], [intervalhours: integer])` — Get Device Information
- `get_devices([did: integer], [ip: text], [seensince: text], [mac: text], [sid: integer], [count: integer], [includetags: checkbox])` — Get Devices
- `get_entity_details(did: integer, [applicationprotocol: text], [ddid: integer], [deduplicate: checkbox], [port: integer], [starttime: datetime], [endtime: datetime], [eventtype: text], [externalhostname: text], [fulldevicedetails: checkbox], [offset: integer], [count: integer])` — Get Entity Details
- `get_enums([country_type: checkbox])` — Get Enums
- `get_external_endpoint_details(get_endpoint_by: select, [score: checkbox], [devices: checkbox])` — Get External Endpoint Details
- `get_incidents([includeacknowledged: checkbox], [starttime: datetime], [endtime: datetime], [locale: select], [uuid: text], [mergeEvents: checkbox])` — Get Incidents
- `get_mb_comments([pbid: integer], [starttime: datetime], [endtime: datetime], [count: integer])` — Get Model Breach Comments
- `get_model_breaches([did: integer], [starttime: datetime], [endtime: datetime], [includeacknowledged: checkbox], [includebreachurl: checkbox], [pbid: text], [pid: integer], [uuid: text])` — Get Model Breaches
- `get_models([model_by: select])` — Get Models
- `get_similar_devices(did: integer, [count: integer], [fulldevicedetails: checkbox])` — Get Similar Devices
- `get_watch_list()` — Get Watch List
- `search_query([time_selection: select], [search: text], [offset: integer], [size: integer])` — Search Query
- `unacknowledge_breach(pbid: text)` — Unacknowledge Breach
- `update_antigena(codeid: integer, [activate: checkbox], [clear: checkbox], [reason: text], [duration: integer])` — Update Antigena

_remediation_
- `remove_from_list(remove_domain_ip_host: text)` — Remove From Watch List


### `fireeye-nx` v1.0.1 _(installed)_
_FireEye NX_

FireEye NX connector perform automated operations such as retrieving a list of all guest image profiles and applications details, retrieving artifacts metadata by alert UUID etc.

**18 operation(s)**:

_containment_
- `add_yara_rule(file_iri: text, file_type: text, [target_type: select])` — Add YARA Rule

_investigation_
- `add_event_filters([filters: json])` — Add Event Filters
- `delete_event_filters([filters: json])` — Delete Event Filters
- `get_alert_details(alert_id: integer)` — Get Alert Details
- `get_alert_updated_with_ati_info(start_time: datetime, [time_offset: text])` — Get Alerts Updated with ATI Information
- `get_alerts([alert_id: integer], [duration: select], [time_type: select], [info_level: select], [callback_domain: text], [dst_ip: text], [src_ip: text], [file_name: text], [file_type: text], [malware_name: text], [malware_type: select], [md5: text], [recipient_email: text], [sender_email: text], [url: text])` — Get Alerts
- `get_artifacts_metadata_by_uuid(alert_uuid: text)` — Get Artifacts Metadata By UUID
- `get_ati_details_of_alert(alert_id: integer)` — Get ATI Information of Alert
- `get_config()` — Get Configuration Information
- `get_event_filter_protocols()` — Get Event Filter Protocols
- `get_event_filters([type: text])` — Get Event Filters
- `get_events([duration: select], [end_time: datetime], [time_offset: text], [mvx_correlated_only: checkbox])` — Get Events
- `get_health_status()` — Get System Health Status
- `get_report_by_id(id_type: select)` — Get Report By ID
- `get_reports_by_time(report_type: select, time_frame: select)` — Get Reports By Time
- `get_statistics(start_time: datetime, end_time: datetime, [time_offset: text])` — Get Statistics
- `list_yara_rule()` — List YARA Rule

_miscellaneous_
- `delete_yara_rule(yara_type: text, yara_file: text, [target_type: select])` — Delete YARA Rule


### `forcepoint-dlp` v1.0.0 _(installed)_
_Forcepoint DLP_

Forcepoint DLP used to prevent data leakage, ensure regulatory compliance, protect intellectual property, manage employee productivity, mitigate risks, and respond to security incidents within organizations.

**10 operation(s)**:

_investigation_
- `get_incidents_by_action(type: select, from_date: datetime, to_date: datetime, action: select)` — Get Incidents by Action
- `get_incidents_by_date_range(type: select, from_date: datetime, to_date: datetime)` — Get Incidents by Date Range
- `get_incidents_by_ids(type: select, ids: text)` — Get Incidents by IDs
- `get_incidents_by_policy_name(type: select, from_date: datetime, to_date: datetime, policies: text)` — Get Incidents by Policy Name
- `get_incidents_by_severity(type: select, from_date: datetime, to_date: datetime, severity: select)` — Get Incidents by Severity
- `get_incidents_by_status(type: select, from_date: datetime, to_date: datetime, status: select)` — Get Incidents by Status
- `get_list_of_incidents_by_filter(type: select, [sort_by: text], from_date: datetime, to_date: datetime, [detected_by: text], [analyzed_by: text], [event_id: integer], [destination: text], [policies: text], [action: select], [source: text], [status: select], [severity: select], [endpoint_type: select], [channel: select], [assigned_to: text], [tag: text])` — Get List Of Incident By Filter
- `update_incident_status_by_event_ids(type: select, event_ids: text, action_type: select)` — Update Incident Status By Event IDs
- `update_incident_status_by_incident_id_and_partition_index(type: select, action_type: select)` — Update Incident Status By Incident ID And Partition Index
- `update_incident_status_by_scan_partitions(type: select, action_type: select, scan_partitions: select)` — Update Incident Status By Scan Partitions


### `forescout` v1.0.0 _(installed)_
_ForeScout_

ForeScout provides insight into the diverse types of devices connected to your heterogeneous network—from campus and data center to cloud and operational technology networks. Use this connector to get active hosts, get policies

**4 operation(s)**:

_investigation_
- `get_active_hosts([match_rule_id: text], [property_dict: json])` — Get Active Hosts
- `get_host(select_by: select, value: text)` — Get Host Information
- `get_host_properties()` — Get Host Properties
- `get_policies()` — Get Policies


### `fortinet-fortiddos` v1.0.0 _(installed)_
_Fortinet FortiDDoS_

FortiDDoS Protection Solution defends enterprise data centers against DDoS attacks by leveraging an extensive collection of known DDoS methodologies, creating a multi-layered approach to mitigate attacks.  It also analyzes the behavior of data to detect new attacks, allowing it to stop zero-day threats.

**24 operation(s)**:

_containment_
- `generate_bgp_flowspec(vendor: select, destination: text, threshold: integer)` — Generate BGP Flowspec

_investigation_
- `get_attack_information(spp_name: text, subtype: select, [dir: select], [period: select])` — Get Attack Information
- `get_bypass_mac()` — Get Bypass MAC
- `get_do_not_track_policy(resource_name: select)` — Get Do Not Track Policy
- `get_domain_reputation()` — Get Domain Reputation
- `get_global_acl(resource_name: select)` — Get Access Control List
- `get_global_settings()` — Get Global Settings
- `get_global_settings_address(resource_name: select)` — Get Global Settings Address
- `get_global_spp(resource_name: select)` — Get Global Service Protection Profiles
- `get_ip_reputation()` — Get IP Reputation
- `get_log_settings(resource_name: select)` — Get Log Settings
- `get_proxy_ip()` — Get Proxy IP
- `get_proxy_ip_policy()` — Get Proxy IP Policy
- `get_service_protection_profile_policy()` — Get Service Protection Profile Policy
- `get_settings(resource_name: select)` — Get Settings
- `get_spp_settings(spp: text, resource_name: select)` — Get Protection Profiles
- `get_system_settings(primary_resource_name: select)` — Get System Settings

_remediation_
- `add_distress_acl(mkey: text, [acl-enable: checkbox], destination: select, [destination-port: checkbox], [dscp: checkbox], [fragment: checkbox], [protocol: checkbox], [source-ip: checkbox], [source-port: checkbox], [tcp-control-flag: checkbox], [ttl: checkbox])` — Add Distress ACL
- `add_lq(query: text, type: text, class: text)` — Add Legitimate DNS Query
- `add_service_protection_profile_policy(spp: text, subnet-id: text, mkey: text, ip-version: select, alt-spp-enable: checkbox, [comment: text])` — Add Service Protection Profile Policy
- `delete_distress_acl(name: text)` — Delete Distress ACL
- `delete_lq(query: text, type: text, class: text)` — Delete Legitimate DNS Query
- `delete_service_protection_profile_policy(policy_name: text)` — Delete Service Protection Profile Policy
- `update_service_protection_profile_settings(spp: text, resource_name: select, parameter_name_val: json)` — Update Protection Profiles Settings


### `fortinet-fortideceptor` v1.0.0 _(installed)_
_Fortinet FortiDeceptor_

FortiDeceptor is a deception-based Breach Protection Deceive, Expose and Eliminate External and Internal Threats.

**9 operation(s)**:

_investigation_
- `decoy_delete([instance_ids: text], [instance_names: text])` — Delete Decoy
- `decoy_deploy(name: text, template_id: text, [hostname: text], [dns: text], interfaces: json)` — Deploy Decoy
- `decoy_start([instance_ids: text], [instance_names: text])` — Start Decoy
- `decoy_stop([instance_ids: text], [instance_names: text])` — Stop Decoy
- `deploy_nets()` — Get Deployment Networks
- `get_attack_events(incident_id: text, [take: integer])` — Get Attack Events
- `get_attack_incidents([take: integer], [protocol: text], [victim_port: integer], [decoy_name: text], [last_n_minutes: integer])` — Get Attack Incidents
- `get_decoy([instance_id: text], [instance_name: text])` — Get Decoy
- `get_templates()` — Get Templates


### `fortinet-fortidlp` v1.1.0 _(installed, ingestion)_
_Fortinet FortiDLP_

FortiDLP is a data loss prevention (DLP) solution from Fortinet that helps organizations prevent data leaks, detect insider risks, and educate employees on cyber hygiene.

**18 operation(s)**:

_investigation_
- `add_labels_to_agents(filter: text, labels: text)` — Add Labels to Agents
- `add_labels_to_users(filter: text, labels: text)` — Add Labels to Users
- `agent_action_request(uuid: text, trigger: json)` — Agent Action Request
- `get_agent_details(uuid: text, [include_actions: checkbox], [include_health: checkbox], [include_labels: checkbox], [include_users: checkbox])` — Get Agent Details
- `get_agents_list([filter: text], [include_actions: checkbox], [include_health: checkbox], [include_labels: checkbox], [include_users: checkbox], [sort_order: select], [sort: text], [results_per_page: integer], [cursor: text])` — Get Agents List
- `get_audit_logs([sort_order: select], [sort: text], [filter: text], [fetch_audit_logs_from: datetime], [fetch_audit_logs_till: datetime], [types: text], [results_per_page: integer], [cursor: text], [get_all_records: checkbox])` — Get Audit Logs
- `get_available_actions_list()` — Get Available Actions List
- `get_configured_streams_list()` — Get Configured Streams List
- `get_events_from_event_streaming(stream_id: text)` — Get Events from Event Streaming
- `get_incidents_by_id(id: text, [include_agents: checkbox], [include_cluster_data: checkbox], [include_labels: checkbox], [include_users: checkbox])` — Get Incidents By ID
- `get_incidents_list([status: multiselect], [filter: text], [sort_order: select], [sort: text], [include_agents: checkbox], [include_cluster_data: checkbox], [include_labels: checkbox], [include_users: checkbox], [results_per_page: integer], [cursor: text], [get_all_records: checkbox])` — Get Incidents List
- `get_label_details(id: text)` — Get Label Details
- `get_labels_list([filter: text], [sort_order: select], [sort: text], [results_per_page: integer], [cursor: text])` — Get Labels List
- `get_pending_in_flight_actions_list(uuid: text)` — Get Pending In-Flight Actions List
- `get_user_details(uuid: text, [include_agents: checkbox], [include_labels: checkbox])` — Get User Details
- `get_users_list([filter: text], [include_agents: checkbox], [include_labels: checkbox], [sort_order: select], [sort: text], [results_per_page: integer], [cursor: text])` — Get Users List
- `send_custom_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `update_incidents_by_id(update_scope: select, status: select, [reason: text])` — Update Incidents


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

_investigation_
- `create_cryptokey(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, [skipInitialVersionCreation: checkbox], [purpose: select], [nextRotationTime: datetime], [protectionLevel: select], [algorithm: select], [labels: json], [rotationPeriod: text])` — Create CryptoKey
- `create_cryptokey_version(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, [state: select], [externalKeyUri: text])` — Create CryptoKey Version
- `create_keyring(project_id: text, location_id: text, key_ring_id: text)` — Create KeyRing
- `decrypt_cryptokey_details(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, ciphertext: text, [additionalAuthenticatedData: text], [ciphertextCrc32c: text], [additionalAuthenticatedDataCrc32c: text])` — Decrypt CryptoKey Details
- `destroy_cryptokey_version(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, cryptoKeyVersionId: integer)` — Destroy CryptoKey Version
- `encrypt_cryptokey_details(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, plaintext: text, [additionalAuthenticatedData: text], [plaintextCrc32c: text], [additionalAuthenticatedDataCrc32c: text])` — Encrypt CryptoKey Details
- `get_cryptokey_details(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text)` — Get CryptoKey Details
- `get_cryptokey_list(project_id: text, location_id: text, key_ring_id: text, [pageSize: integer], [versionView: select], [pageToken: text], [filter: text], [orderBy: text])` — Get CryptoKey List
- `get_cryptokey_version_details(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, cryptoKeyVersionId: integer)` — Get CryptoKey Version Details
- `get_cryptokey_version_list(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, [pageSize: integer], [versionView: select], [pageToken: text], [filter: text], [orderBy: text])` — Get CryptoKey Version List
- `get_keyring_details(project_id: text, location_id: text, key_ring_id: text)` — Get KeyRing Details
- `get_keyring_list(project_id: text, location_id: text, [pageSize: integer], [pageToken: text], [filter: text], [orderBy: text])` — Get KeyRing List
- `get_locations_list(project_id: text, [pageSize: integer], [filter: text], [pageToken: text])` — Get Locations List
- `get_public_key_for_cryptokey_version(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, cryptoKeyVersionId: integer)` — Get Public key for CryptoText Version
- `restore_cryptokey_version(project_id: text, location_id: text, key_ring_id: text, cryptoKeyId: text, cryptoKeyVersionId: integer)` — Restore CryptoKey Version


### `mcafee-network-security-manager` v1.1.0 _(installed)_
_McAfee Network Security Manager_

McAfee Network Security Manager appliance delivers centralized, web-based management and unrivaled ease of use. This connector facilitates the automated operations like block and unblock IP, get domain details etc.

**15 operation(s)**:

_investigation_
- `add_domain(domainName: text, contactPerson: text, emailAddress: text, defaultIPSPolicy: text, defaultReconPolicy: text)` — Create Domain
- `block_ip(sensor_id: integer, ip: text, du_time: select, [remediate: checkbox])` — Block IP
- `delete_domain(domain_id: text)` — Delete Domain
- `delete_policy(policy_id: text)` — Delete Policy
- `get_blocked_ip_details(sensor_id: integer)` — Get Blocked IP Details
- `get_blocked_ip_list(sensor_id: integer)` — Get Blocked IP List
- `get_domain_details(domain_id: text)` — Get Domain Details
- `get_domain_sensors(domain_id: text)` — Get Domain Sensors
- `get_domains()` — Get All Domains
- `get_policy_details(policy_id: text)` — Get Policy Details
- `get_sensor_details(sensor_id: integer)` — Get Sensor Details
- `list_policies(domain_id: text)` — Get Domain Firewall Policies
- `unblock_ip(sensor_id: integer, ip: text)` — Unblock IP
- `update_block_ip_duration(sensor_id: integer, ip: text, du_time: select, [is_override: checkbox])` — Update Block IP Duration
- `update_domain(domain_id: text, domainName: text, contactPerson: text, emailAddress: text, defaultIPSPolicy: text, defaultReconPolicy: text)` — Update Domain


### `netskope` v2.0.0 _(installed)_
_Netskope_

Netskope provides smart cloud security which controls activities across any cloud service or website and provides 360-degree data and threat protection that works everywhere. This connector facilitates automated operations like get alerts list, get events list, and urls related operations.

**10 operation(s)**:

_investigation_
- `add_url_list(url_list_id: text, [type: text], [urls: text])` — Add URL List
- `create_url_list(name: text, type: text, urls: text)` — Create URL List
- `delete_url_list(url_list_id: text)` — Delete URL List
- `get_alerts_list([query: text], [type: select], [acked: checkbox], [starttime: datetime], [endtime: datetime], [insertionstarttime: datetime], [insertionendtime: datetime], [limit: integer], [offset: integer])` — Get Alerts List
- `get_client_list([filter: text], [count: integer], [startIndex: integer])` — Get Client List
- `get_events_list(type: select, [query: text], [starttime: datetime], [endtime: datetime], [insertionstarttime: datetime], [insertionendtime: datetime], [limit: integer], [offset: integer])` — Get Events List
- `get_url_list([pending: integer], [field: text])` — Get All URL List
- `get_url_list_details(url_list_id: text)` — Get URL List Details
- `send_custom_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `update_url_list(url_list_id: text, [name: text], [type: text], [urls: text])` — Update URL List


### `orca` v2.0.0 _(installed, ingestion)_
_Orca_

Orca Security provides Agentless, Workload-Deep, Context-Aware Cloud Infrastructure Security and Compliance for IaaS platforms AWS, Azure, and GCP. This connector facilitates automated operations related to fetch security alert and assert related data.

**5 operation(s)**:

_investigation_
- `get_alerts(filter_type: select)` — Get Alerts
- `get_assets([asset_id: text])` — Get Assets
- `run_query(query_type: select, [dsl_filter: json], [type: text], [severity: text], [risk_level: text], [limit: integer], [next_page_token: text])` — Run Query
- `update_alert_severity(alert_id: text, severity: text, score: text)` — Update Alert Severity
- `update_alert_status(operation_type: select)` — Update Alert Status


### `paloalto-enterprise-dlp` v1.0.1 _(installed)_
_Palo Alto Enterprise DLP_

Palo Alto Enterprise DLP discovers and protects company data across every data channel and repository.

**1 operation(s)**:

_investigation_
- `get_report_details(report_id: text, [fetchSnippets: checkbox])` — Get Report Details


### `paloalto-prisma-cloud` v1.0.1 _(installed)_
_Palo Alto Prisma Cloud_

Prisma Cloud is a cloud security posture management (CSPM) and cloud workload protection platform (CWPP) that provides comprehensive visibility and threat detection across an organization’s hybrid, multi-cloud infrastructure. This connector provides Get Alerts, Get Alert Details, Dismiss Alerts, Reopen Alert, Get Alert Remediation Commands, Get Policy Information, etc actions

**7 operation(s)**:

_investigation_
- `dismiss_alerts([alerts: text], [dismissalNote: text], [dismissalTimeRange: select], [detailed: checkbox], [fields: text], [filters: json], [groupBy: text], [limit: integer], [offset: integer], [pageToken: text], [sortBy: text], [timerange: select], [policies: text])` — Dismiss Alerts
- `get_alert_details(id: text, [detailed: checkbox])` — Get Alert Details
- `get_alert_filters()` — Get Alert Filters
- `get_alert_remediation_commands(timerange: select, [alerts: text], [policies: text])` — Get Alert Remediation Commands
- `get_alerts([detailed: checkbox], [fields: text], [filters: json], [groupBy: text], [limit: integer], [offset: integer], [pageToken: text], [sortBy: text], [timerange: select])` — Get Alerts
- `get_policy_info(id: text)` — Get Policy Information
- `reopen_alerts([alerts: text], [dismissalNote: text], [dismissalTimeRange: select], [detailed: checkbox], [fields: text], [filters: json], [groupBy: text], [limit: integer], [offset: integer], [pageToken: text], [sortBy: text], [timerange: select], [policies: text])` — Reopen Alerts


### `pensando-policy-servicemanager` v1.0.1 _(installed)_
_Pensando Policy Service Manager_

Pensando's Policy and Services Manager (PSM) is a distributed system that leverages an intent-based model to deliver network and security policy to Pensando Distributed Services Cards for services implementation at the edge.

**17 operation(s)** (+3 hidden):

_containment_
- `ioc_block_add_ip(ioc_ip: text)` — Add IOC IPs to Blocklist
- `isolate_host(host_source_ip: text)` — Isolate Host

_investigation_
- `delete_ipfix_export(host_source_ip: text, ipfix_collector_ip: text)` — Delete existing IPFIX Export for Host
- `delete_mirror_export(host_source_ip: text, erspan_collector_ip: text)` — Delete Existing Mirror Traffic Export for Host
- `enable_ipfix_export(host_source_ip: text, interval: text, template_interval: text, ipfix_collector_ip: text, [ipfix_collector_gw_ip: text], ipfix_collector_protocol: text, ipfix_collector_port: text)` — Enable IPFIX Export for Host
- `enable_mirror_export(host_source_ip: text, erspan_id: text, [packet_size: text], erspan_type: select, erspan_collector_ip: text, [erspan_collector_gw_ip: text], strip_vlan: checkbox, [erspan_match_dest_ip: text], [erspan_match_protocols: text])` — Enable Mirror Traffic Export for Host
- `get_alerts()` — Get Alerts
- `get_distributedservicecards()` — Get Distributed Service Cards
- `get_network_security_policies()` — Get Network Security Policies
- `get_networks()` — Get Networks
- `get_workloads()` — Get Workloads

_remediation_
- `ioc_block_remove_ip(ioc_ip: text)` — Remove IOC IPs from Blocklist
- `ioc_delete_list()` — Remove IOC Blocklist
- `unisolate_host(host_source_ip: text)` — Unisolate Host


### `polar-security` v1.0.0 _(installed)_
_Polar Security_

An agentless platform that connects within minutes, Polar Security can automatically find unknown and sensitive data across the cloud.

**7 operation(s)**:

_investigation_
- `apply_label(label: text, store_id: text)` — Apply Label
- `get_data_store(store_id: text)` — Get Data Store
- `get_data_stores([limit: integer], [page_size: integer], [next_token: integer])` — Get Data Stores
- `get_data_stores_summary()` — Get Data Stores Summary
- `get_linked_vendors()` — Get Linked Vendors
- `get_vendor_accessible_data_store()` — Get Vendor Accessible Data Store
- `get_vendors_data_stores(vendor_id: text, [limit: integer], [page_size: integer], [next_token: integer])` — Get Vendors Data Stores


### `progress-whatsup-gold` v1.0.0 _(installed)_
_Progress WhatsUp Gold_

WhatsUp Gold provides complete visibility into the status and performance of applications, network devices and servers in the cloud or on-premises.

**7 operation(s)**:

_investigation_
- `get_device_attributes(device_id: integer, [names: text], [limit: integer], [pageId: integer])` — Get Device Attributes
- `get_device_groups(device_id: integer, [view: select], [limit: integer], [pageId: integer])` — Get Device Groups
- `get_device_monitors(device_id: integer, [limit: integer], [pageId: integer])` — Get Device Monitors
- `get_device_overview(device_id: integer)` — Get Device Overview
- `get_device_polling_configuration(device_id: integer)` — Get Device Polling Configuration
- `get_device_report(report_type: select, device_id: integer, [range: select], [limit: integer], [pageId: integer])` — Get Device Report
- `get_device_summary(device_id: integer)` — Get Device Summary


### `shieldx` v1.0.0 _(installed, ingestion)_
_ShieldX_

ShieldX connector automates to pull security threat events and actions to isolate workloads, assign tags etc.

**12 operation(s)** (+2 hidden):

_investigation_
- `assign_tag(infraId: text, vm_id: text, type: select, tag_id: multiselect)` — Assign Tag
- `create_tag([name: text], [key: text], [value: text])` — Create Tag
- `get_tag([id: text])` — Get Tags
- `list_infrastructure([InfraId: text])` — List Infrastructure
- `list_security_policy([id: text])` — List Security Policies
- `list_workloads(InfraId: text)` — List Workloads
- `search_events_by_index(index: select, [size: text], [sort: multiselect], [order: select], [from: integer], [search_after: json], [gte: datetime], [lt: datetime])` — Fetch Threat Events
- `unassign_tag(infraId: text, vm_id: text, type: select, tag_id: multiselect)` — Unassign Tag
- `update_security_policy(id: text, [name: text], [isAnomalyDetection: select], [isDlpPolicy: select], [malwarePolicyId: text], [malwarePolicyName: text], [tenantId: text], [threatPreventionPolicyId: text], [threatPreventionPolicyName: text], [urlfilteringPolicyId: text], [urlfilteringPolicyName: text], [lastModified: datetime])` — Update Security Policy
- `workloads_details(vm_id: text)` — Get Workload Details


### `solarwinds` v1.0.0 _(installed)_
_SolarWinds_

The SolarWinds Orion Platform is a unified suite of network and system management products. This connector facilitates the automated operations to get the alert list, get the event list and to execute SWIS query.

**3 operation(s)**:

_investigation_
- `execute_swis_query(query: text)` — Execute SWIS Query
- `get_alert_list([alert_ids: text], [alert_type: text], [severity: multiselect], [sort_field: select], [sort_order: select], [page: integer], [limit: integer])` — Get Alert List
- `get_event_list([acknowledged: checkbox], [event_ids: text], [event_type: text], [node: text], [sort_field: select], [sort_order: select], [page: integer], [limit: integer])` — Get Event List


### `sonicwall-nsm` v1.0.0 _(installed)_
_SonicWall NSM_

SonicWall Network Security Manager (NSM) is a cloud-based (or on-prem) platform designed to centrally manage, monitor, and report on SonicWall firewalls and security policies across distributed environments.

**5 operation(s)**:

_investigation_
- `create_address_object(name: text, zone: text, object_type: select, [description: text], [serialnum: text])` — Create Address Object
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_access_rules(filterType: select, [serialnum: text], [ruleType: select], [limit: checkbox], [limitCount: integer], [childrenObjTypes: text])` — Get Access Rules
- `get_address_objects(name: text, [isuuid: checkbox], [serialnum: text])` — Get Address Object
- `update_address_object([uuid: text], name: text, zone: text, object_type: select, new_name: text, [serialnum: text])` — Update Address Object


### `symantec-management-center` v1.0.0 _(installed)_
_Symantec Management Center_

Symantec Management Center provides a unified management environment for the Symantec Security Platform portfolio of products. Management Center brings Symantec’s network, security, and cloud technologies to you under a single umbrella making it easier to deploy, manage, and monitor your security environment.

**8 operation(s)**:

_investigation_
- `add_policy_content(uuid: text, [changeDescription: text], [content: text], [contentType: text], [schemaVersion: text])` — Add or Update Policy Content
- `create_policy(name: text, contentType: text, [description: text], [referenceId: text], [tenant: text], [author: text], [shared: checkbox], [replaceVariables: text])` — Create Policy
- `delete_policy(uuid: text, [force: checkbox])` — Delete Policy
- `get_policies([author: text], [contentType: text], [description: text], [name: text], [referenceId: text], [shared: checkbox], [tenant: text])` — Get Policies
- `get_policy_content(uuid: text)` — Get Policy Content
- `get_policy_content_by_version(uuid: text, version: text)` — Get Policy Content By Version
- `get_policy_details(uuid: text)` — Get Policy Details
- `update_policy(uuid: text, [name: text], [description: text], [referenceId: text], [replaceVariables: text])` — Update Policy


### `threatx` v1.0.0 _(installed)_
_ThreatX_

Use the ThreatX integration to enrich intel and automate enforcement actions on the ThreatX Next Gen WAF.

**9 operation(s)**:

_investigation_
- `add_entity_note(id: text, content: text)` — Add Entity Notes
- `blacklist_ip(ip_address: text, [description: text])` — Blacklist IP Address
- `block_ip(ip_address: text, [description: text])` — Block IP Address
- `get_entities(first_seen: text, [ip_address: text], [entity_ids: text], [codenames: text], [actor_ids: text], [attack_ids: text])` — Get Entities
- `get_entity_notes(id: text)` — Get Entity Notes
- `unblacklist_ip(ip_address: text)` — Unblacklist IP Address
- `unblock_ip(ip_address: text)` — Unblock IP Address
- `unwhitelist_ip(ip_address: text)` — Unwhitelist IP Address
- `whitelist_ip(ip_address: text, [description: text])` — Whitelist IP Address


### `vmware-nsx-t` v1.2.0 _(installed)_
_VMware NSX-T_

VMware NSX-T Data Center focuses on providing networking, security, automation, and operational simplicity for emerging application frameworks and architectures that have heterogeneous endpoint environments and technology stacks. This Connector automated operations such as create, update and delete operation related to policy, rule, group etc.

**16 operation(s)**:

_investigation_
- `add_remove_ip_addresses(domain_id: text, group_id: text, expression_id: text, action: select, ip_addresses: text)` — Add/Remove IP Addresses
- `add_remove_mac_addresses(domain_id: text, group_id: text, expression_id: text, action: select, [mac_addresses: text])` — Add/Remove MAC Addresses
- `get_group_details(domain_id: text, group_id: text)` — Get Group Details
- `get_groups_list(domain_id: text, [include_mark_for_delete_objects: checkbox], [member_types: text], [page_size: integer], [sort_by: text], [sort_ascending: checkbox], [cursor: text])` — Get Groups List
- `get_rule_details(domain_id: text, policy_id: text, rule_id: text)` — Get Rule Details
- `get_rules_list(domain_id: text, policy_id: text, [include_mark_for_delete_objects: checkbox], [page_size: integer], [sort_by: text], [sort_ascending: checkbox], [cursor: text])` — Get Rules List
- `get_security_policies_list(domain_id: text, [include_mark_for_delete_objects: checkbox], [include_rule_count: checkbox], [page_size: integer], [sort_by: text], [sort_ascending: checkbox], [cursor: text])` — Get Security Policies List
- `get_security_policy_details(domain_id: text, policy_id: text)` — Get Security Policy Details

_miscellaneous_
- `delete_group(domain_id: text, group_id: text)` — Delete Group
- `delete_rule(domain_id: text, policy_id: text, rule_id: text)` — Delete Rule
- `delete_security_policy(domain_id: text, policy_id: text)` — Delete Security Policy
- `get_vm_externalID(vm_name: text)` — Get VM External ID
- `manage_vm_tag(external_id: text, vm_tag_update_action: select, vm_scope: text, vm_tag: text)` — Manage VM TAG
- `upsert_group(domain_id: text, group_id: text, [display_name: text], [description: text], [group_type: text], [state: select], [expression: json], [tags: json], [extended_expression: json], [additional_field: json])` — Upsert Group
- `upsert_rule(domain_id: text, policy_id: text, rule_id: text, [display_name: text], [description: text], [source_groups: text], [destination_groups: text], [logged: checkbox], [disabled: checkbox], [scope: text], [action: select], [notes: text], [tags: json], [additional_field: json])` — Upsert Rule
- `upsert_security_policy(domain_id: text, policy_id: text, [display_name: text], [description: text], [category: select], [comments: text], [rules: json], [additional_field: json])` — Upsert Security Policy


### `zscaler` v2.1.0 _(installed)_
_Zscaler_

Zscaler is revolutionizing cloud security by empowering organizations to embrace cloud efficiency, intelligence, and agility—securely. This connector integrate with Zscaler and Perform containment, investigation and remediation action.

**17 operation(s)**:

_containment_
- `block_url(urls: text)` — Block URLs

_investigation_
- `add_new_category(urls: text, other_fields: json)` — Add URL Category
- `delete_url_category(categoryId: text)` — Delete URL Category
- `get_blacklist_urls()` — Get Blacklist URLs
- `get_exempted_urls()` — Get Exempted URLs
- `get_lightweight_url_categories()` — Get Lightweight URL Categories
- `get_sandbox_report_md5_hash(md5Hash: text, [details: select])` — Get MD5 Cloud Sandbox Report
- `get_sandbox_report_quota()` — Get Cloud Sandbox Report Quota
- `get_url_categories([customOnly: checkbox], [includeOnlyUrlKeywordCounts: checkbox])` — Get URL Categories
- `get_url_categories_quota()` — Get URL Categories Quota
- `get_url_category_info(categoryId: text)` — Get URL Category Details
- `get_whitelist_urls()` — Get Whitelist URLs
- `url_lookup([urls: text])` — URL Lookup

_miscellaneous_
- `update_exempted_urls(action: select)` — Update exempted URLs
- `update_url_category(categoryId: text, action: select, urls: text, [configuredName: text], [superCategory: text], [other_fields: json])` — Update URL Category
- `update_whitelist_urls(urls: text, action: select)` — Update Whitelist URLs

_remediation_
- `unblock_url(urls: text)` — Unblock URLs


### `zscaler-client-connector` v1.0.0 _(installed)_
_Zscaler Client Connector_

Zscaler Client Connector™ is a lightweight agent for user endpoints, enabling hybrid work through secure, fast, reliable access to any app over any network.

**7 operation(s)**:

_investigation_
- `download_device_details([osTypes: multiselect], [registrationTypes: multiselect])` — Download Device Details
- `download_service_status_of_devices([osTypes: multiselect], [registrationTypes: multiselect])` — Download Service Status of Devices
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_device_app_profile_password([username: text], [osType: text])` — Get Device App Profile Password
- `get_device_otp(udid: text)` — Get Device OTP
- `get_enrolled_device_details(udid: text, [username: text])` — Get Enrolled Device Details
- `get_enrolled_device_list([username: text], [osType: text], [page: integer], [pageSize: integer])` — Get Enrolled Device List


### `zscaler-private-access` v1.0.0 _(installed)_
_Zscaler Private Access (ZPA)_

Zscaler Private Access (ZPA) is a cloud-delivered Zero Trust Network Access (ZTNA) solution that provides secure, identity-based access to internal applications without placing users on the network. It enables seamless integration with FortiSOAR for automated access control, threat response, and policy enforcement based on real-time user and application context. This connector enables automated operations such as Get All Configured Applications Segments, Get Specific Application Segment Details, Get Customer Certificates, Get All Issued Certificates, and Get Certificate Details.

**6 operation(s)**:

_investigation_
- `get_all_configured_applications_segments(customerId: text, [search: text], [page: integer], [pagesize: integer], [microtenantId: text])` — Get All Configured Applications Segments
- `get_all_issued_certificates(customerId: text, [search: text], [page: integer], [pagesize: integer])` — Get All Issued Certificates
- `get_certificate_details(customerId: text, certificateId: text)` — Get Certificate Details
- `get_customer_certificates(customerId: text)` — Get Customer Certificates
- `get_specific_application_segment_details(customerId: text, applicationId: text, [micro_tenant_id: text])` — Get Specific Application Segment Details

_utilities_
- `execute_api_request(endpoint: text, method: select, [query_params: json], [payload: json])` — Execute an API Request


---

## Network Security,Cloud Security,Endpoint Security

### `illumio-core` v1.0.0 _(installed)_
_Illumio Core_

Illumio that provides a platform designed to help organizations protect their critical applications and data by creating secure zones and controlling access between workloads, regardless of whether those workloads are on-premises or in the cloud. This connector facilitates automated operations related to workloads, IP list and labels.

**20 operation(s)**:

_investigation_
- `create_ip_list(org_id: integer, pversion: text, name: text, [ip_ranges: json], fqdns: json, [description: text], [additional_properties: json])` — Create IP List
- `create_label(org_id: integer, key: text, value: text, [external_data_set: text], [ external_data_reference: text])` — Create Label
- `create_workload(org_id: integer, name: text, [description: text], [hostname: text], [service_principal_name: text], [public_ip: text], [additional_properties: json])` — Create Workload
- `delete_ip_list(org_id: integer, pversion: text, ip_list_id: text)` — Delete IP List
- `delete_label(org_id: integer, label_id: text)` — Delete Label
- `delete_workload(org_id: integer, workload_id: text)` — Delete Workload
- `get_ip_list(org_id: integer, pversion: text, [description: text], [external_data_reference: text], [max_results: integer], [additional_properties: json])` — Get IP List
- `get_ip_list_by_id(org_id: integer, pversion: text, ip_list_id: text)` — Get IP List by ID
- `get_label_by_id(org_id: integer, label_id: text, [usage: checkbox])` — Get Label by ID
- `get_labels(org_id: integer, [include_deleted: checkbox], [external_data_reference: text], [max_results: integer], [additional_properties: json])` — Get Labels
- `get_pending_security_policy(org_id: integer, [max_results: integer])` — Get Pending Security Policy
- `get_ransomware_details(org_id: integer, workload_id: text)` — Get Ransomware Details
- `get_workload_by_id(org_id: integer, workload_id: text)` — Get Workload by ID
- `get_workloads(org_id: integer, [enforcement_mode: select], [include_deleted: checkbox], [security_policy_sync_state: select], [security_policy_update_mode: select], [visibility_level: select], [policy_health: select], [max_results: integer], [additional_properties: json])` — Get Workloads
- `restore_previous_security_policy(org_id: integer, pversion: text)` — Restore Previous Security Policy
- `revert_pending_uncommitted_security_policy_list(org_id: integer)` — Revert Pending Uncommitted Security Policy List
- `send_custom_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Call
- `update_ip_list(org_id: integer, pversion: text, ip_list_id: text, [ip_ranges: json], fqdns: json, [description: text], [additional_properties: json])` — Update IP List
- `update_label(org_id: integer, label_id: text, [value: text], [external_data_set: text], [external_data_reference: text])` — Update Label
- `update_workload(org_id: integer, workload_id: text, [name: text], [description: text], [service_provider: text], [enforcement_mode: select], [additional_properties: json])` — Update Workload


---

## Network Tool

### `amazon-alexa` v1.0.0 _(installed)_
_Amazon Alexa_

Amazon alexa provide automated operation for URL Lookup

**1 operation(s)**:

_investigation_
- `url_lookup(url: text)` — URL Lookup


### `hacker-target` v1.0.0 _(installed)_
_Hacker Target_

Hacker Target provide online IP Tools that can be used to quickly get information about IP Addresses, Web Pages and DNS records.

**9 operation(s)**:

_investigation_
- `dns_lookup(dns: text)` — DNS Lookup
- `geoip_lookup(ip: text)` — GeoIP Lookup
- `get_all_links_from_page(link: text)` — Get All Links from Page
- `get_http_header(link: text)` — Get HTTP Header
- `mtr_traceroute(ip: text)` — MTR Traceroute
- `reverse_dns_lookup(dns: text)` — Reverse DNS Lookup
- `reverse_ip_lookup(ip: text)` — Reverse IP Lookup
- `test_ping(ip: text)` — Test Ping
- `whois_lookup(ip: text)` — Whois Lookup


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

## Networking

### `check-host` v1.0.0 _(installed)_
_Check Host_

Check host offers various network-related tools and services. It also provides tools for checking the availability and response time of a website or server from different locations around the world.

**5 operation(s)**:

_investigation_
- `check_result_by_request_id(request_id: text)` — Check Result By Request ID
- `dns_address_check(host: text, max_nodes: integer)` — DNS Address Check
- `http_check(host: text, max_nodes: integer)` — HTTP Check
- `ping_check(host: text, max_nodes: integer)` — Ping Check
- `tcp_connection_check(host: text, max_nodes: integer)` — TCP Connection Check


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


### `claroty` v1.1.0 _(installed, ingestion)_
_Claroty_

Claroty CTD is a robust solution that delivers comprehensive cybersecurity controls for industrial environments. This connector provides automated actions like Get Assets, Get Alert, Get Alert Details, etc

**10 operation(s)**:

_investigation_
- `get_alert_details(resource_id: text)` — Get Alert Details
- `get_alerts([resolution__exact: multiselect], [category__exact: multiselect], [severity__exact: multiselect], [timestamp__gte: datetime], [timestamp__lte: datetime], [filters: json], [per_page: integer], [page: integer])` — Get Alerts
- `get_asset_details(resource_id: text)` — Get Asset Details
- `get_asset_risks_and_vulnerabilities(resource_id: text)` — Get Asset Risks And Vulnerabilities
- `get_assets([asset_type__in: multiselect], [protocol__exact: multiselect], [criticality__exact: multiselect], [timestamp__gte: datetime], [timestamp__lte: datetime], [filters: json], [per_page: integer], [page: integer], [format: select])` — Get Assets
- `get_events([site_id: text], [id__exact: text], [alert_id__exact: text], [timestamp__gte: datetime], [timestamp__lte: datetime], [description__contains: text], [description__icontains: text], [type__exact: select], [status__exact: select], [sort: select], [sort_order: select], [per_page: integer], [page: integer])` — Get Events
- `get_insight_details(insight_name: text, [format: text], [ghost__exact: checkbox], [special_hint__exact: select], [insight_status__exact: select], [site_id__exact: text], [per_page: integer], [page: integer])` — Get Insight Details
- `get_insights(format: text, sort: text, [sort_order: select], [ghost__exact: checkbox], [special_hint__exact: select], [insight_status__exact: select], [site_id__exact: text], [per_page: integer], [page: integer])` — Get Insights
- `get_queries([name__icontains: text], [site_id__exact: text], [sort: select], [sort_order: select], [per_page: integer], [page: integer])` — Get Queries
- `get_tasks([name__icontains: text], [site_id__exact: text], [per_page: integer], [page: integer], [sort: select], [sort_order: select])` — Get Tasks


### `claroty-xdome` v1.0.0 _(installed, ingestion)_
_Claroty XDOME_

Claroty xDome is a modular, SaaS-powered industrial cybersecurity platform that scales to protect your environment and fulfill your goals as they evolve

**5 operation(s)**:

_investigation_
- `execute_generic_claroty_api(endpoint: text, parameters: json)` — Execute Generic Claroty API
- `get_alerts(fields: json, [before_detected_time: datetime], [after_detected_time: datetime], [before_updated_time: datetime], [after_updated_time: datetime], [id: text], [category: text], [filter_by: json], [sort_by: json], [offset: integer], [limit: integer], [all_alerts: checkbox])` — Get Alerts
- `get_devices(fields: json, [device_type: text], [mac_oui_list: text], [model: text], [software_or_firmware_version: text], [device_category: multiselect], [device_subcategory: multiselect], [purdue_level: multiselect], [known_vulnerabilities: multiselect], [risk_score: multiselect], [filter_by: json], [sort_by: json], [offset: integer], [limit: integer])` — Get Devices
- `get_ot_events(fields: json, [event_id: text], [event_type: text], [dest_asset_id: text], [source_asset_id: text], [filter_by: json], [sort_by: json], [offset: integer], [limit: integer])` — Get OT Activity Events
- `get_vulnerabilities(fields: json, [id: text], [name: text], [vulnerability_type: text], [cve_ids: text], [cvss_v3_score: decimal], [filter_by: json], [sort_by: json], [offset: integer], [limit: integer])` — Get Vulnerabilities


### `everbridge` v1.0.0 _(installed, ingestion)_
_Everbridge_

Everbridge that provides enterprise software applications that automate and accelerate organizations operational response to critical events. This connector facilitates the automated operations related to incidents, assets, and organizations.

**7 operation(s)**:

_investigation_
- `get_asset_details(organizationId: integer, id: text)` — Get Asset Details
- `get_assets_list(organizationId: integer, [pageNumber: integer])` — Get Assets List
- `get_incident_details(organizationId: integer, incidentId: integer)` — Get Incident Details
- `get_incident_list(organizationId: integer, [dateType: select], [startTime: datetime], [endTime: datetime], [incidentType: select], [status: select], [onlyOpen: checkbox], [pageNumber: integer], [pageSize: integer])` — Get Incident List
- `get_organizations_list()` — Get Organizations List
- `update_asset(organizationId: integer, id: integer, [autoGeoCoding: checkbox], [name: text], [floorNo: text], [street: text], [city: text], [state: text], [country: text], [countryFullName: text], [postalCode: text])` — Update Asset
- `update_incident(organizationId: integer, incidentId: integer, incidentAction: select, [incidentStatus: select], [incidentType: select], [incidentMode: text], [name: text], [closeBy: text], [additional_fields: json])` — Update Incident


### `hikvision-nvr` v1.0.0 _(installed)_
_Hikvision NVR_

Hikvision's Network Video Recorders (NVRs) provide advanced artificial intelligence capabilities for any connected data stream, even those from conventional security cameras

**8 operation(s)**:

_investigation_
- `download_video(trackid: text, videoname: text, [create_fortisoar_attachment: checkbox])` — Download Videos Recording
- `get_channel()` — Get Channels
- `get_device_info()` — Get NVR Device Details
- `get_http_listening_servers()` — Get HTTP Listening Servers
- `get_interface()` — Get Management Interface
- `get_ntp_details()` — Get NVR Time
- `get_video_recording_details(trackid: text, start_date: datetime, enddate: datetime, [limit: text])` — Get Videos Recording Details
- `search_log(metaid: select, start_date: datetime, enddate: datetime, [limit: text])` — Search Log


### `nozomi-networks-central-management-console` v1.1.0 _(installed, ingestion)_
_Nozomi Networks Central Management Console_

The Nozomi Networks Central Management Console (CMC) consolidates OT and IoT risk monitoring and visibility from Guardian physical or virtual appliances across all of your distributed sites. It integrates with your IT security infrastructure for streamlined workflows and faster response to threats and anomalies.

**19 operation(s)**:

_investigation_
- `create_threat_intelligence_indicator(indicators: json)` — Create Indicator
- `delete_threat_intelligence_indicator(indicators: json)` — Delete Indicator
- `get_alert_ack_status(job_id: text)` — Get Alert Acknowledgement Status
- `get_alerts([appliance_ids: text], [start_time: datetime], [risk_level: text], [status: text], [alert_type: text], [is_incident: checkbox], [query: text], [max_alerts: integer])` — Get Alerts List
- `get_all_threat_intelligence_indicators()` — Get All Indicators
- `get_appliances([appliance_ids: text], [query: text])` — Get Appliances
- `get_assertions([query: text])` — Get Assertions
- `get_assets([appliance_ids: text], [level: multiselect], [asset_types: text], [query: text], [max_assets: integer])` — Get Assets List
- `get_captured_logs([appliance_ids: text], [query: text])` — Get Captured Logs
- `get_function_codes([query: text])` — Get Function Codes
- `get_health_log([appliance_ids: text], [query: text])` — Get Health Log
- `get_links([query: text])` — Get Links
- `get_node_cpe_changes([appliance_ids: text], [query: text])` — Get Node CPE Changes
- `get_node_cpes([appliance_ids: text], [query: text])` — Get Node CPEs
- `get_node_cves([appliance_ids: text], [query: text])` — Get Node CVEs
- `get_nodes([query: text])` — Get Nodes
- `import_asset(type: select)` — Import Asset
- `run_cli(command: text)` — Run CLI
- `set_alert_ack(alert_ids: text, [acknowledge: checkbox])` — Set Acknowledgment Status


### `nozomi-networks-guardian` v1.2.0 _(installed, ingestion)_
_Nozomi Networks Guardian_

The Nozomi Networks Guardian platform used to monitor OT/IoT/IT networks. It combines asset discovery, network visualization, vulnerability assessment, risk monitoring and threat detection in a single solution. This integration is used to gather alerts and assets information from Nozomi.

**26 operation(s)**:

_investigation_
- `create_threat_intelligence_indicator(indicators: json)` — Create Indicator
- `delete_threat_intelligence_indicator(indicators: json)` — Delete Indicator
- `get_alert_ack_status(job_id: text)` — Get Alert Acknowledgement Status
- `get_alert_details(alert_id: text)` — Get Alert Trace
- `get_alerts([appliance_id: text], [start_time: datetime], [risk_level: text], [max_alerts: integer], [status: text], [alert_type: text], [is_incident: select], [query: text])` — Get Alerts List
- `get_all_threat_intelligence_indicators()` — Get All Indicators
- `get_appliances([query: text])` — Get Appliances
- `get_assertions([query: text])` — Get Assertions
- `get_assets([appliance_id: text], [level: multiselect], [asset_type: text], [max_assets: text], [query: text])` — Get Assets
- `get_captured_logs([query: text])` — Get Captured Logs
- `get_captured_urls([query: text])` — Get Captured URLs
- `get_function_codes([query: text])` — Get Function Codes
- `get_health_log([query: text])` — Get Health Log
- `get_link_events([query: text])` — Get Link Events
- `get_links([query: text])` — Get Links
- `get_node_cpe_changes([query: text])` — Get Node CPE Changes
- `get_node_cpes([query: text])` — Get Node CPEs
- `get_node_cves([query: text])` — Get Node CVEs
- `get_nodes([query: text])` — Get Nodes
- `get_sessions([query: text])` — Get Sessions
- `get_sessions_history([query: text])` — Get Sessions History
- `get_variable_history([query: text])` — Get Variable History
- `get_variables([query: text])` — Get Variables
- `import_asset(type: select)` — Import Asset
- `run_cli(command: text)` — Run CLI
- `set_alert_ack(alert_ids: text, [acknowledge: checkbox])` — Set Acknowledgment Status


### `otbase-inventory` v1.1.0 _(installed, ingestion)_
_OTbase Inventory_

Enterprise-grade OT asset management software. OTbase is the gold standard for large scale OT asset inventories. It inventories OT devices from PLCs over network switches to sensors and actuators and integrates nicely with your existing tools and platforms.

**8 operation(s)**:

_investigation_
- `delete_device_details(device_id: text)` — Delete Device Details
- `get_data_flow([last_seen: datetime])` — Get Data Flow
- `get_device_details(device_id: text, [include: multiselect])` — Get Device Details
- `get_devices_list([name: text], [locationid: text], [otsystemid: text], [otsystem: text], [ipaddress: text], [include: multiselect], [networkid: text], [modified: datetime], [count: integer], [offset: integer])` — Get Devices List
- `get_network_details(network_id: text)` — Get Network Details
- `get_network_list([offset: integer])` — Get Network List
- `get_vulnerabilities_list([priority: multiselect], [locationid: text], [count: integer], [offset: integer])` — Get Vulnerabilities List
- `get_vulnerability_details(cve_id: text)` — Get Vulnerability Details


### `scadafence` v1.0.0 _(installed)_
_SCADAfence_

SCADAfence that provides full coverage of large-scale networks, offering best-in-class network monitoring, asset discovery, governance, remote access, and IoT device security. This connector facilitates the automated operations related to alerts, assets, and sites.

**6 operation(s)**:

_investigation_
- `create_alert(ip: text, [severity: select], details: text, active: checkbox, [remediation: text])` — Create Alert
- `get_alerts([number: text], [type: integer], [site_id: integer], [status: select], [severity: select], [ip: text], [from: datetime], [to: datetime], [from_last_seen: datetime], [to_last_seen: datetime], [order: select], [sort: select], [size: integer], [page: integer])` — Get Alert List
- `get_assets([site_id: integer], [ip: text], [HostName: text], [mac: text], [order: select], [sort: select], [size: integer], [page: integer])` — Get Asset List
- `get_sites_status([site_id: integer], [site_name: text])` — Get Sites Status
- `update_alert_status(id: text, status: select)` — Update Alert Status
- `update_asset(id: integer, ip: text, override: checkbox, [host: text], [device_type: text], [os: text], [vendor: text], [ou: text], [owner: text], [location: text], [comment: text], [criticality: select], [cve_product: text], [cve_version: text])` — Update Asset


---

## OT & IoT Security 

### `microsoft-defender-for-iot` v1.0.0 _(installed)_
_Microsoft Defender for IoT_

Microsoft Defender for IoT consolidates real-time asset discovery, vulnerability management, and cyberthreat protection for your Internet of Things (IoT) and industrial infrastructure, such as industrial control systems (ICS) and operational technology (OT). This connector facilitates automated interactions, with a Microsoft Defender for IoT server using FortiSOAR™ playbooks to effectively view, analyze, and respond to alerts generated by Defender for IoT

**8 operation(s)**:

_investigation_
- `get_device_vulnerability_report()` — Get Device Vulnerability Information
- `get_mitigation_assessment()` — Get Mitigation Steps
- `get_operational_assessment_report()` — Get Operational Vulnerabilities
- `get_vulnerability_assessment_report()` — Get Security Vulnerabilities
- `list_alerts([state: select], [type: select], [fromTime: datetime], [toTime: datetime])` — Get Alert List
- `list_device_cves([ipAddress: text], [top: integer])` — Get Device CVEs List
- `list_devices([authorized: select])` — Get Device List
- `list_timeline_events([type: select], [minutesTimeFrame: integer])` — Get Timeline Events


---

## Other

### `screenshot-machine` v1.0.0 _(installed)_
_ScreenShot Machine_

ScreenShot Machine Connector

**1 operation(s)**:

_investigation_
- `get_screenshot(url: text, [format: select], [device: select], [dimension: text], [timeout: text], [cache_limit: text], [size: select])` — Get Screenshot


---

## Reputation

### `cymon` v1.0.0 _(installed)_
_Cymon_

Cymon is the largest open tracker of malware, phishing, botnets, spam, and more. This connector pulls information about Domains, IP addresses, or file hashes from the Cymon v1 API

**3 operation(s)**:

_investigation_
- `lookup_domain(domain: text)` — Look Up Domain
- `lookup_hash(file_hash: text)` — Lookup File Hash
- `lookup_ip(ipaddr: text)` — IP Address Lookup


---

## Risk Scoring

### `symantec-ica` v1.0.0 _(installed)_
_Symantec ICA_

Integrate with Symantec ICA to retrieve entity risk scores for entities like users, IPs, and hosts.

**9 operation(s)**:

_investigation_
- `get_action_plans()` — Get Action Plans
- `get_host_risk(hostname: text)` — Get Host Risk
- `get_ip_risk(ipaddress: text)` — Get IP Risk
- `get_risk_model_details(riskModelInstanceID: text)` — Get Risk Model Instance Details
- `get_risk_model_instances([Limit: integer])` — Get Risk Model Instances
- `get_user_risk(username: text)` — Get User Risk
- `set_action_plan_comment(ActionPlanGUID: text, Comment: text)` — Create Comment on Action Plan
- `set_event_classifications([RiskModelInstanceID: text], [CardInstanceID: text], [FocusEntityID: text], Classification: text)` — Set Event Classifications
- `set_event_mitigations([RiskModelInstanceID: text], [CardInstanceID: text], [FocusEntityID: text], Mitigated: text)` — Set Event Mitigations


---

## SCIM

### `sailpoint-identityiq` v1.0.1 _(installed)_
_SailPoint IdentityIQ_

SailPoint IdentityIQ provides enterprise identity governance solutions with on-premises and cloud-based identity management software for the most complex challenges

**16 operation(s)**:

_investigation_
- `check_potential_policy_violations(identity: text, value: text, type: text, identity: text)` — Check Potential Policy Violations
- `get_account_details(account_id: text)` — Get Account Details
- `get_accounts()` — Get Accounts
- `get_application_details(application_id: text)` — Get Application Details
- `get_entitlement_details(entitlement_id: text)` — Get Entitlement Details
- `get_entitlements()` — Get Entitlements
- `get_launched_workflows()` — Get Launched Workflows
- `get_policy_violations()` — Get Policy Violations
- `get_role_details(role_id: text)` — Get Role Details
- `get_roles()` — Get Roles
- `get_task_result_details(task_result_id: text)` — Get Task Result Details
- `get_task_results()` — Get Task Results
- `get_user_details(user_id: text)` — Get User Details
- `get_users()` — Get Users
- `get_workflow_status(workflow_id: text)` — Get Workflow Status
- `get_workflows()` — Get Workflows


---

## SIEM

### `arcsight` v4.1.1 _(installed, ingestion)_
_Micro Focus ArcSight ESM_

Micro Focus ArcSight Enterprise Security Manager (ESM) is a threat detection, analysis, triage, and compliance management SIEM platform, This connector can be use to ingesting events from ArcSight, search and case management

**23 operation(s)** (+1 hidden):

_investigation_
- `add_case_event(case_id: text, event_ids: text)` — Add Events To Case
- `annotate_event(event_id: text, stage: select, user: text, [comment: text])` — Annotate Event
- `annotate_event_by_stage_id(event_id: text, stage_id: text, [user: text], [comment: text])` — Annotate Event By Stage ID
- `create_case(parent_id: text, case_name: text, [alias: text], [ticketType: select], [stage: select], [frequency: select], [operational_impact: select], [security_classification: select], [consequence_severity: select], [externalID: text], [description: text], [custom_field: json])` — Create Case
- `delete_active_list_entries([active_list_id: text], fields: text, entries: json)` — Delete Active List Entries
- `get_active_list_entries([active_list_id: text], [max_count: integer], [clear_entries: checkbox])` — Get Active List Entries
- `get_active_list_info([active_list_id: text])` — Get Active List Information
- `get_case_info(case_id: text)` — Get Case Information
- `get_event_details(event_id: text, [replace_null: checkbox], [ip_keys: text], [mac_keys: text], [field_list: text], [epoch_field_list: text], [date_format: text])` — Get Event Details Using XML API
- `get_event_info(event_id: text, start_time: datetime, end_time: datetime, [replace_null: checkbox], [ip_keys: text], [mac_keys: text])` — Get Event Details
- `get_events_list(start_time: datetime, end_time: datetime, [active_list_id: text], [max_count: integer], [clear_entries: checkbox], [replace_null: checkbox], [ip_keys: text], [mac_keys: text])` — Get Events List
- `get_fields()` — Get Event Fields
- `get_query_viewer_data(resource_id: text)` — Get Query Viewer Data
- `run_report(run_by: select)` — Run Report with Default Parameters
- `run_report_params(report_id: text, report_params: json)` — Run Report
- `run_search(query: text, [start_pos: text], [page_size: text])` — Search Query
- `update_active_list([active_list_id: text], fields: text, entries: json)` — Add Active List Entries
- `update_case_info(case_id: text, [case_name: text], [alias: text], [ticketType: select], [stage: select], [frequency: select], [operational_impact: select], [security_classification: select], [consequence_severity: select], [restore_time: datetime], [externalID: text], [description: text], [custom_field: json])` — Update Case
- `upload_report(download_id: text, [attachment_name: text])` — Download Report

_remediation_
- `clear_active_list_entries(active_list_id: text)` — Clear Active List Entries
- `delete_case_event(case_id: text, event_ids: text)` — Delete Case Events
- `delete_report(archive_report_id: text)` — Delete Archive Report


### `azure-sentinel` v1.1.0 _(installed, ingestion)_
_Azure Sentinel_

Azure Sentinel is Cloud-native SIEM for intelligent security analytics for your entire enterprise. These connector connects to azure sentinel using microsoft graph API to investigate on alerts, threats intelligence indicator, incidents and secure score.

**15 operation(s)**:

_investigation_
- `create_threat_intelligence_indicator(action: select, description: text, targetProduct: text, threatType: select, tlpLevel: select, object_class: select)` — Create Threat Intelligence Indicator
- `delete_threat_intelligence_indicator(id: text)` — Delete Threat Intelligence Indicator
- `fetch_alert_query(WorkspaceId: text, SystemAlertId: text)` — Fetch Alert Query
- `get_alert(alert_id: text)` — Get Alert
- `get_alert_events(WorkspaceId: text, Query: text)` — Get Alert Events
- `get_alert_list([$filter: text], [created_datetime: datetime], [$orderby: text], [$top: integer])` — Get Alert List
- `get_all_secure_score_control_profiles()` — Get All Secure Score Control Profiles
- `get_all_secure_scores(azureTenantId: text)` — Get All Secure Scores
- `get_all_threat_intelligence_indicators()` — Get All Threat Intelligence Indicators
- `get_incident(incidentId: text, WorkspaceSubscriptionId: text, WorkspaceResourceGroup: text, WorkspaceName: text)` — Get Incident
- `get_incident_list(WorkspaceSubscriptionId: text, WorkspaceResourceGroup: text, WorkspaceName: text, [$filter: text], [$orderby: text], [$top: integer], [$skipToken: integer])` — Get Incident List
- `get_threat_intelligence_indicator(id: text)` — Get Threat Intelligence Indicator
- `update_alert(alert_id: text, status: select, provider: text, vendor: text, [assignedTo: text], [closedDateTime: text], [comments: multiselect], [feedback: select], [tags: text], [providerVersion: text], [subProvider: text])` — Update Alert
- `update_incident(incidentId: text, WorkspaceSubscriptionId: text, WorkspaceResourceGroup: text, WorkspaceName: text, [etag: text], Severity: select, Status: select, Title: text, [Description: text])` — Update Incident
- `update_threat_intelligence_indicator(id: text, targetProduct: text, [action: select], [description: text], [severity: text], [tlpLevel: select], [isActive: checkbox], [confidence: integer], [diamondModel: select], [tags: text])` — Update Threat Intelligence Indicator


### `devo` v1.0.0 _(installed, ingestion)_
_Devo_

Devo connector performs actions like get alerts, run query etc.

**3 operation(s)**:

_investigation_
- `get_alert_definitions([nameFilter: text], [idFilter: integer], [page: integer], [size: integer])` — List Alert Definitions
- `get_alerts(time_range: select, [query_filter: text], [limit: integer], [offset: integer])` — Get Alerts
- `run_query(search_by: select, time_range: select, [limit: integer], [offset: integer])` — Run Query


### `fireeye-helix` v1.0.0 _(installed, ingestion)_
_FireEye Helix_

FireEye Helix is a security operations platform. FireEye Helix integrates security tools and augments them with next-generation SIEM, orchestration and threat intelligence tools such as alert management, search, analysis, investigations and reporting.

**23 operation(s)**:

_investigation_
- `add_list_item(list_id: text, type: select, value: text, [risk: select], [notes: text])` — Add List Item
- `create_an_alert_note(alert_id: text, note: text, [created_at: datetime], [updated_at: datetime])` — Create Alert Note
- `delete_alert_note(alert_id: text, note_id: text)` — Delete Alert Note
- `delete_list(list_id: text)` — Delete List
- `edit_rule(rule_id: text, [enabled: checkbox])` — Edit Rule
- `get_alert_details(alert_id: text)` — Get Alert Details
- `get_alert_notes(alert_id: text, [limit: integer], [offset: integer], [order_by: text])` — Get Alert Notes
- `get_alerts([limit: integer], [offset: integer], [alert_threat: text], [confidence: select], [created_at__gte: datetime], [risk: select], [severity: select], [state: select], [additional_fields: json])` — Get All Alert List
- `get_assets_by_alert(alert_id: text)` — Get Alert Assets
- `get_cases([limit: integer], [offset: integer], [priority: select], [status: select], [state: select], [additional_fields: json])` — Get All Case List
- `get_cases_by_alert(alert_id: text, [limit: integer], [offset: integer], [order_by: text])` — Get Alert Cases
- `get_cases_details(case_id: text)` — Get Cases Details
- `get_endpoints_by_alert(alert_id: text)` — Get Alert Endpoints
- `get_events([limit: integer], [offset: integer], [query: text], [sort: text], [includes: text])` — Get All Event List
- `get_events_by_alert(alert_id: text)` — Get Alert Events
- `get_list_details(list_id: text, [is_active: checkbox], [is_internal: checkbox], [is_protected: checkbox], [name: text], [short_name: text], [order_by: text], [usage: text], [additional_fields: json])` — Get List Details
- `get_list_items(list_id: text, [limit: text], [offset: integer], [risk: select], [type: select], [value: text], [usage: text], [order_by: text])` — Get List Items
- `get_lists([limit: text], [offset: integer], [is_active: checkbox], [is_internal: checkbox], [is_protected: checkbox], [name: text], [short_name: text], [usage: text], [additional_fields: json])` — Get Lists
- `get_rules_list([limit: integer], [offset: integer], [query: text], [sort: text], [fields: text], [includes: text])` — Get Rules List
- `get_sensors_list([limit: text], [offset: integer], [status: select], [hostname: text], [additional_fields: json])` — Get Sensors List
- `remove_list_item(list_id: text, item_id: text)` — Remove List Item
- `update_list(list_id: text, [name: text], [short_name: text], [is_active: checkbox], [usage: text], [type: text], [description: text])` — Update List
- `update_list_item(list_id: text, item_id: text, [type: select], [value: text], [risk: select], [notes: text])` — Update List Item


### `gigamon` v1.0.0 _(installed)_
_Gigamon_

Gigamon Connector

**5 operation(s)**:

_containment_
- `add_rule(map_alias: text, cluster_id: text, comment: text, type: text, value: text, rule_type: select)` — Add Rule
- `update_rule(rule_id: text, map_alias: text, cluster_id: text, comment: text, type: text, value: text, rule_type: select)` — Update Rule

_investigation_
- `get_map(map_alias: text, cluster_id: text)` — Get Map
- `get_maps(cluster_id: text)` — Get Maps

_remediation_
- `delete_rules(map_alias: text, [rule_id: text], cluster_id: text)` — Delete Rules


### `google-chronicle-backstory` v1.0.0 _(installed, ingestion)_
_Google Chronicle BackStory_

Google Chronicle BackStory is used to detect and investigate potential cyber threats.

**9 operation(s)**:

_investigation_
- `get_alerts(start_time: datetime, end_time: datetime, [limit: integer])` — Get Alerts
- `get_assets(indicator_type: select, indicator_value: text, start_time: datetime, end_time: datetime, [limit: integer])` — List All Assets
- `get_detection_details(rule_id: text, detection_id: text)` — Get Detection Details
- `get_detections(rule_id: text, [alertState: select], [start_time: datetime], [end_time: datetime], [limit: integer], [page_token: text])` — List All Detections
- `get_domain_reputation(domain_name: text)` — Get Domain Reputation
- `get_events(indicator_type: select, indicator_value: text, start_time: datetime, end_time: datetime, reference_time: datetime, [limit: integer])` — List All Events
- `get_iocs(start_time: datetime, [limit: integer])` — List All IOCs
- `get_ip_reputation(ip_address: text)` — Get IP Reputation
- `get_rules([limit: integer], [page_token: text])` — List All Rules


### `logpoint` v2.0.2 _(installed, ingestion)_
_LogPoint_

LogPoint enables organizations to convert data into actionable intelligence, improving their cybersecurity posture and creating immediate business value. LogPoint connector provides automated actions for collecting, analyzing, and monitoring your machine data.

**13 operation(s)** (+1 hidden):

_investigation_
- `get_devices()` — Get Devices
- `get_incident(incident_obj_id: text, incident_id: text, date: text)` — Get Incident
- `get_incident_states(start_time: datetime, end_time: datetime)` — Get Incident States
- `get_incident_users()` — Get Incident Users
- `get_live_search()` — Get Live Search
- `get_log_points()` — Get Log Points
- `get_repos()` — Get Repos
- `get_search_id(time_range: select, [query_options: select], [limit: integer], [repos: multiselect])` — Get Search ID
- `get_search_logs(search_id: text)` — Get Search Logs
- `get_timezone()` — Get Time Zone
- `list_incidents(start_time: datetime, end_time: datetime)` — Fetch Incidents
- `update_incident(incident_type: select)` — Update Incident


### `manage-engine-log360` v1.0.0 _(installed, ingestion)_
_ManageEngine Log360_

ManageEngine Log360 is a unified SIEM solution with integrated DLP and CASB capabilities that detects, prioritizes, investigates, and responds to security threats.

**3 operation(s)**:

_investigation_
- `get_alert_profiles([type: multiselect], [severity: multiselect], [status: multiselect])` — Get Alert Profiles List
- `get_alerts([from: datetime], [to: datetime], [query: text], [alert_profiles: text], [severity: multiselect], [status: multiselect])` — Get Alerts List
- `invoke_search([query: text], [from: datetime], [to: datetime], [hosts: text], [groups: text])` — Get Events List


### `mcafee-esm` v2.6.0 _(installed, ingestion)_
_McAfee ESM_

McAfee ESM(Enterprise Security Manager) connector can be used to automate actions related to cases, alarms, watchlist and data sources.

**20 operation(s)** (+1 hidden):

_investigation_
- `acknowledge_alarm(alarm_ids: text)` — Acknowledge Alarm
- `add_note_to_event(event_id: text, note: text)` — Add Note to event
- `add_watchlist_values(watchlist_id: select, values_list: text)` — Add WatchList Values
- `create_case(alarm_assignee: text, alarm_name: text, status: select, alarm_severity: text, [alarm_trigger_date: datetime], [event_id: text], [org_id: text])` — Create Case
- `delete_watchlist(watchlist_id: select)` — Delete WatchList
- `delete_watchlist_values(watchlist_id: select, values_list: text)` — Delete WatchList Values
- `get_alarm_detail(alarm_id: text)` — Get Alarm Detail
- `get_case_details(case_id: text)` — Get Case Details
- `get_cases()` — Get Cases
- `get_data_source_details(data_source_id: text)` — Get Data Source Details
- `get_data_source_list(device_id: text)` — Get Data Source List
- `get_device_tree()` — Get Device Tree
- `get_event_detail(event_id: text)` — Get Event Detail
- `get_watchlist_values(watchlist_id: select, [position: integer], [count: integer])` — Get WatchList Values
- `get_watchlists([version: checkbox])` — Get WatchLists
- `list_alarms([assigned_user: text], [time_range: select], [pageSize: integer], [pageNumber: integer])` — Get Alarms
- `unacknowledge_alarm(alarm_ids: text)` — Unacknowledge Alarm
- `update_case(case_id: text, [case_assignee: text], [status: select], [case_severity: text], [case_name: text], [note_added: text], [event_id: text])` — Update Case

_miscellaneous_
- `parse_uri()` — Parse URL


### `rsa-netwitness-siem` v1.2.1 _(installed, ingestion)_
_RSA Netwitness SIEM_

The RSA NetWitness Platform is an evolved SIEM and threat detection and response solution that allows security teams to rapidly detect and respond to any threat, anywhere. This connector facilitates the automated operations like Get Incident, Get Incidents by Date Range and Get Incident Related Alerts.

**6 operation(s)**:

_investigation_
- `get_alerts([meta_name: text], [meta_value: text], [includeFields: text], [numberOfRecords: integer])` — Get Alerts
- `get_hosts(serviceId: text, [criteria: json], [pageNumber: integer], [pageSize: integer])` — Get Hosts List
- `get_incident(id: text)` — Get Incident
- `get_incident_by_date_range([since: datetime], [until: datetime], [pageNumber: integer], [pageSize: integer])` — Get Incidents by Date Range
- `get_incidents_alerts(id: text, [pageNumber: integer], [pageSize: integer])` — Get Incident Related Alerts
- `get_service_id()` — Get Service IDs


### `syslog` v1.3.0 _(installed, ingestion)_
_Syslog_

FortiSOAR Syslog Connector

**4 operation(s)**:

_investigation_
- `parse(message: text, rfc: select)` — Parse Message
- `restart()` — Restart Listener
- `start()` — Start Listener
- `stop()` — Stop Listener


### `wazuh-siem` v1.0.0 _(installed, ingestion)_
_Wazuh SIEM_

Wazuh provides a security solution capable of monitoring your infrastructure, detecting threats, intrusion attempts, system anomalies, poorly configured applications and unauthorized user actions. This connector facilitates automated operations to Get Alerts by Lucene search, DSL search etc.

**4 operation(s)**:

_investigation_
- `get_alert_by_id(id: text)` — Get Alert Details
- `get_alerts_by_DSL_search(query: json, [size: integer])` — Execute DSL Search
- `get_alerts_by_lucene_search(q: text, [size: integer])` — Execute Lucene Search
- `get_all_alerts_in_last_x_minutes(minutes: integer)` — Get All Alerts in Last X Minutes


### `xmatters` v2.0.0 _(installed)_
_xMatters_

xMatters Connector can be used to automate actions like get events, update events, get groups and get device

**4 operation(s)**:

_investigation_
- `event_list([propertyName: text], [propertyValue: text], [status: select], [priority: select], [offset: integer], [limit: integer])` — Get Event List
- `event_update(eventID: text, status: select)` — Update Event
- `get_device(deviceID: text)` — Get Device
- `get_groups([query: text])` — Get Groups


---

## SOAR

### `ibm-security-qradar-soar` v1.1.0 _(installed)_
_IBM Security QRadar SOAR_

IBM Security QRadar SOAR is a software platform designed to help organizations manage and respond to security incidents effectively. It provides a comprehensive approach to incident response by integrating with various security tools and automating processes to streamline incident handling.

**12 operation(s)**:

_investigation_
- `close_incident(incident_id: text)` — Close Incident
- `create_incident(name: text, discovered_date: integer, [description: json], [want_full_data: checkbox], [want_tasks: checkbox], [dtm: json], [cm: json], [regulators: json], [hipaa: json], [artifacts: json], [findings: json], [comments: json], [additional_fields: json])` — Create Incident
- `get_all_incident_details(incidentID: text, [filters: json], [start: integer], [length: integer])` — Get All Incident Details
- `get_incident_artifacts(incident_id: text, [filters: json], [include_records_total: checkbox], [return_level: select], [field_handle: text], [start: integer], [length: integer], [recordsTotal: integer], [sorts: json], [logic_type: select])` — Get Incident Artifacts
- `get_incident_attachment_details(incidentID: text)` — Get Incident Attachment Details
- `get_incident_attachments(incident_id: text)` — Get Incident Attachments
- `get_incident_details(incident_id: text, [vers: integer], [want_findings: checkbox])` — Get Incident Details
- `get_incident_notes(incident_id: text)` — Get Incident Notes
- `get_incident_simulations([want_closed: checkbox])` — Get Incidents Simulations
- `get_incident_tasks(incident_id: text, [want_layouts: checkbox], [want_notes: checkbox])` — Get Incident Tasks
- `search_incidents([filters: json], [include_records_total: checkbox], [return_level: select], [field_handle: text], [length: integer], [start: integer], [recordsTotal: integer], [sorts: json], [logic_type: select])` — Search Incidents
- `update_incident(incident_id: text, [changes: json], [version: integer])` — Update Incident


---

## SandBox

### `lastline` v1.0.0 _(installed)_
_Lastline_

LastLine connector

**5 operation(s)**:

_investigation_
- `check_filehash_is_blocked(hash_type: select, hash_val: text)` — Check Filehash is Blocked
- `get_report(task_uuid: text)` — Get Report
- `search_report_using_filehash(hash_type: select, hash_val: text)` — Search Report using Filehash
- `submit_file(file: text)` — Submit File
- `submit_url(url: text)` — Submit URL


### `secondwrite` v1.0.1 _(installed)_
_SecondWrite_

SecondWrite Connector

**3 operation(s)**:

_investigation_
- `get_report(uuid: text)` — Get Report
- `submit_file(file: text)` — Submit Sample
- `submit_url(url: text)` — Submit URL


### `urlvoid` v1.1.0 _(installed)_
_URLVoid_

URLVoid Connector

**1 operation(s)**:

_investigation_
- `domain_reputation(domain: text, [rescan: checkbox])` — Get Website Reputation 


---

## Sandbox

### `checkpoint-sandblast-appliance` v1.0.0 _(installed)_
_Check Point Sandblast Appliance_

Checkpoint Sandblast Appliance connector submits file samples for sandboxing and fetches scan verdicts and reports

**3 operation(s)**:

_investigation_
- `download(file_id: text)` — Download Report
- `query(file_hash: text, [file_name: text])` — Get File Reputation
- `upload(file_iri: text, file_name: text)` — Submit File


### `checkpoint-sandblast-cloud` v1.0.0 _(installed)_
_Check Point Sandblast Cloud_

Check Point Sandblast Threat Emulation Cloud connector submits file samples for sandboxing and fetches reputation verdicts

**4 operation(s)**:

_investigation_
- `download(file_id: text, [te_cookie: text])` — Download Report
- `query(file_hash: text, [te_cookie: text], [file_name: text])` — Get File Reputation
- `quota()` — Get Sandblast Cloud Quota
- `upload(file_iri: text, file_name: text)` — Submit File


### `cisco-threatgrid` v1.3.0 _(installed)_
_Cisco Threat Grid_

Cisco Threat Grid Connector is a malware analysis and threat intelligence platform, this connector allows you to submit the sample for analysis and fetch reports.

**13 operation(s)** (+3 hidden):

_investigation_
- `download_report(sample_id: text, download: select)` — Download Report
- `get_IOC_json(sample_id: text)` — Get IOCs
- `get_all_reports([after: datetime], [before: datetime])` — Get All Reports
- `get_curated_feeds(search_type: select, [date: datetime])` — Search Report by Feeds
- `get_json_report(id: text)` — Get JSON Report
- `get_rate_limit_info()` — Get Rate Limit Information
- `get_status(sample_id: text)` — Get Status
- `get_summary(sample_id: text)` — Get Summary
- `search_report(search_type: text, [filter_by: select], [before: datetime], [after: datetime], [state: select], [limit: integer])` — Search Report
- `submit_sample(submission_type: select, [tags: text], [vm: select], [playbook_name: select], [location_name: select], [private: checkbox], [email_notification: checkbox], [classify: checkbox], [sample_password: password], [callback_url: text])` — Submit Sample


### `crowd-strike-falcon-sandbox` v2.1.0 _(installed)_
_CrowdStrike Falcon Sandbox_

Falcon Sandbox can be used submit files/URLs for analysis, pull report data, but also perform advanced search queries

**14 operation(s)** (+1 hidden):

_investigation_
- `download_report(download_type: select)` — Download Report
- `get_analysis_overview(sha256: text, [refresh: checkbox])` — Get Analysis Overview
- `get_analysis_summary(sha256: text)` — Get Analysis Summary
- `get_environments()` — Get Environments
- `get_report_summary(id: text)` — Get Report Summary
- `get_scanners_list()` — Get Scanners
- `get_submission_state(id: text)` — Get Submission State
- `quick_scan_file(input: select, scan_type: text, [no_share_third_party: checkbox], [allow_community_access: checkbox], [comment: text], [submit_name: text])` — Quick Scan File
- `quick_scan_url(url: text, scan_type: text, [no_share_third_party: checkbox], [allow_community_access: checkbox], [comment: text], [submit_name: text])` — Quick Scan URL
- `search_query(search_by: select)` — Search Query
- `submit_file_to_sandbox(input: select, environment_id: select, [no_share_third_party: checkbox], [allow_community_access: checkbox], [no_hash_lookup: checkbox], [action_script: select], [hybrid_analysis: checkbox], [script_logging: checkbox], [input_sample_tampering: checkbox], [offline_analysis: checkbox], [email: email], [comment: text], [submit_name: text])` — Submit File To Sandbox
- `submit_url_hash_to_sandbox(url: text)` — Submit URL For Hash
- `submit_url_to_sandbox(url: text, environment_id: select, [no_share_third_party: checkbox], [allow_community_access: checkbox], [no_hash_lookup: checkbox], [action_script: select], [hybrid_analysis: checkbox], [script_logging: checkbox], [input_sample_tampering: checkbox], [offline_analysis: checkbox], [email: email], [comment: text], [submit_name: text])` — Submit URL To Sandbox


### `fireeye-ax` v1.0.1 _(installed)_
_FireEye AX_

FireEye AX connector perform automated operations such as retrieving a list of all guest image profiles and applications details, submitting files or URLs for analysis and retrieving data for artifacts.

**14 operation(s)**:

_containment_
- `add_custom_feeds(feedName: text, feedType: select, feedAction: text, feedSource: text, content: text, [overwrite: checkbox])` — Add or Update Custom Feeds
- `add_yara_rule(file_iri: text, file_type: text)` — Add YARA Rule

_investigation_
- `download_custom_feeds(feed_name: text, feed_path: text)` — Download a Custom IOC File Request
- `get_alert_details(alert_id: text)` — Get Alert Details
- `get_alerts([alert_id: text], [info_level: select], [url: text], [file_name: text], [file_type: text], [malware_name: text], [malware_type: text], [start_time: datetime], [end_time: datetime])` — Get Alerts
- `get_artifacts_metadata_by_uuid(alert_uuid: text)` — Get Artifacts Metadata By UUID
- `get_config()` — Get Config
- `get_submission_result([info_level: select], [object_id: text])` — Get Submission Result
- `list_custom_feeds()` — List Custom Feeds
- `submit_file(file_iri: text, timeout: integer, application: text, priority: select, profiles: text, analysistype: select, prefetch: select, [force: checkbox])` — Submit File
- `submit_url(urls: text, timeout: text, application: text, priority: select, profiles: text, analysistype: select, prefetch: select, [force: checkbox])` — Submit URL

_miscellaneous_
- `delete_yara_rule(yara_type: text, yara_file: text)` — Delete YARA Rule
- `get_submission_status(info_level: select, [object_id: text])` — Get Submission Status

_remediation_
- `delete_custom_feeds(feed_name: text)` — Delete Custom Feeds


### `fortinet-fortiai` v1.3.0 _(installed)_
_Fortinet FortiNDR_

The FortiNDR is a leading-edge product which utilizes machine learning technology for malware detection, intrusion detection and network anomalies.. This connector provides action to submits file samples for analysis and potentially fetches scan verdicts

**3 operation(s)**:

_investigation_
- `get_events(ip_hostname_mac: select, type: select, start_time: datetime, end_time: datetime, [start: integer], [size: integer])` — Get Events
- `get_file_verdict_results(get_result_by: select)` — Get File Verdict Result
- `submit_file(input: select, [password: password])` — Submit File


### `fortinet-fortisandbox` v2.1.0 _(installed)_
_Fortinet FortiSandbox_

FortiSandbox utilizes advanced detection, dynamic antivirus scanning, and threat scanning technology to detect viruses and APTs. FortiSandbox executes suspicious files in the VM host module to determine if the file is High, Medium, or Low Risk based on the behaviour observed in the VM sandbox module. Implemented actions like submit file, get scan stats, get file verdict, get job behaviour and get pdf report etc.

**17 operation(s)**:

_investigation_
- `download_hashes_url_from_mwpkg(type: select, lazy: checkbox)` — List Filehash or URL From Malware Package or URL Package
- `get_avrescan(stime: datetime, etime: datetime, [need_av_ver: checkbox])` — Get AV-Rescan Result
- `get_file_rating(hash_type: select, file_hash: text)` — Get File Rating
- `get_file_verdict(hash_type: select, file_hash: text)` — Get File Verdict
- `get_installed_vm()` — Get All Installed VM
- `get_job_behaviour(hash_type: select, file_hash: text, [decode_file_string: checkbox])` — Get Job Behaviour
- `get_pdf_report(qtype: text, qval: text)` — Get PDF Report
- `get_scan_result_job(jid: text)` — Get Job Verdict Detail
- `get_scan_stats()` — Get Scan Stats
- `get_submission_job_list(sid: text)` — Get Submission Job List
- `get_system_status()` — Get System Status
- `get_url_rating(url: text)` — Get URL Rating
- `submit_file(input_type: select, [overwrite_vm_list: text], [un_zip_file: checkbox])` — Submit File
- `submit_urlfile(url: text, [overwrite_vm_list: text], [timeout: integer], [depth: checkbox])` — Submit URL

_miscellaneous_
- `handle_allow_block_list(list_type: select, indicator_type: select, action: select)` — Update Allow or Block List
- `handle_white_black_list(list_type: select, indicator_type: select, action: select)` — Update White or Black List
- `mark_sample_fp_fn(jid: text, comments: text)` — Toggle FPN State


### `intezer-analyze` v1.0.0 _(installed)_
_Intezer Analyze_

Intezer Analyze enables you to perform malware analysis of suspicious files and a variety of automated investigation process operations. This connector facilitates automated operations like Submit File, Submit Hash, Get Analysis, Generate Vaccine

**6 operation(s)**:

_investigation_
- `analyse_file(selected_option: select, file_path: text)` — Submit File
- `analyse_hash(hash: text)` — Submit Hash
- `generate_vaccine(analysis_id: text, sub_analysis_id: text, vaccine_format: select)` — Generate Vaccine
- `get_analysis(sub_id: text)` — Get Analysis
- `get_sub_analysis(analysis_id: text)` — Get Sub Analysis
- `hash_reputation(hash: text)` — Get Hash Reputation


### `joe-sandbox-cloud` v1.2.0 _(installed)_
_Joe Sandbox Cloud_

Joe sandbox is cloud base malware analysis service, It is a multi technology platform which uses instrumentation, simulation, hardware virtualization, hybrid and graph - static and dynamic analysis

**8 operation(s)**:

_investigation_
- `get_account_info()` — Get Account Information
- `get_all_analysed_sample_details()` — Get All Analysed Sample Details
- `get_all_system_information()` — Get All System Information
- `get_report(web_id: integer)` — Get Report
- `get_submitted_sample_state(web_id: integer)` — Get Submission Status
- `search_report(query: text)` — Search Report
- `submit_file(file_id: text, [systems: text], [comments: text], [analysis-time: integer], [office-files-password: password], [internet-access: checkbox], [hybrid-code-analysis: checkbox], [hybrid-decompilation: checkbox], [report-cache: checkbox], [static-only: checkbox], [ssl-inspection: checkbox], [vba-instrumentation: checkbox], [js-instrumentation: checkbox], [java-jar-tracing: checkbox], [email-notification: checkbox])` — Submit File
- `submit_url(url: text, [systems: text], [comments: text], [analysis-time: integer], [office-files-password: password], [internet-access: checkbox], [hybrid-code-analysis: checkbox], [hybrid-decompilation: checkbox], [report-cache: checkbox], [static-only: checkbox], [ssl-inspection: checkbox], [vba-instrumentation: checkbox], [js-instrumentation: checkbox], [java-jar-tracing: checkbox], [email-notification: checkbox])` — Submit URL


### `koodous` v1.0.0 _(installed)_
_Koodous_

Koodous is a collaborative platform that combines the power of online analysis tools with social interactions between the analysts over a vast APKs repository.

**3 operation(s)**:

_investigation_
- `get_report(apk_sha256: text)` — Get Report
- `search_apk([name: text])` — Search APK
- `upload_apk([apk_id: text], [attachment_iri: text], sha256: text)` — Submit APK


### `malshare` v1.0.0 _(installed)_
_MalShare_

A free Malware repository providing researchers access to samples, malicous feeds, and Yara results.

**5 operation(s)**:

_investigation_
- `get_file_details(hash: select, value: text)` — Get File Information
- `list_hash([type: select], [size: integer])` — List Hash
- `list_url([size: integer])` — List URL
- `search_query(query: text)` — Search Query
- `submit_sample(file_iri: text)` — Submit Sample


### `malwr` v1.0.0 _(installed)_
_Malwr_

Malwr Connector

**2 operation(s)**:

_investigation_
- `get_report(task_id: text)` — Get Report
- `submit_sample(file_iri: text, [private: checkbox])` — Submit File


### `threatstop` v1.0.0 _(installed)_
_ThreatSTOP_

ThreatSTOP is a cloud-based automated threat intelligence platform that converts the latest threat data into enforcement policies, and automatically updates your firewalls, routers, DNS servers and endpoints to stop attacks before they become breaches.

**14 operation(s)**:

_investigation_
- `add_domain_to_domain_udl(object_id: text, list_name: text, shared: select, value: text, [comments: text])` — Add Domain to Domain UDL
- `add_ip_to_ip_udl(object_id: text, list_name: text, list_type: select, value: text, [comments: text])` — Add IP to IP UDL
- `check_ioc(ioc: text)` — Check IOC
- `create_domain_udl(list_name: text, shared: select, value: text, [comments: text], [description: text])` — Create Domain UDL
- `create_ioc(ioc: text, [strategy: select], [targets: text], [last_seen: datetime])` — Create IOC
- `create_ip_udl(list_name: text, list_type: select, value: text, [comments: text], [description: text])` — Create IP UDL
- `delete_domain_from_domain_udl(object_id: text)` — Delete Domain from Domain UDL
- `delete_ip_from_ip_udl(object_id: text)` — Delete IP from IP UDL
- `get_devices([object_id: text])` — Get Devices Details
- `get_domain_policies([object_id: text])` — Get Domain Policies
- `get_domain_udls([object_id: text])` — Get Domain UDLs
- `get_ip_policies([object_id: text])` — Get IP Policies 
- `get_ip_udls([object_id: text])` — Get IP UDLs
- `get_log_details([object_id: text], [limit: text])` — Get Log Details


### `vmray` v1.1.0 _(installed)_
_VMRAY_

VMRay is a malware analysis platform that uses dynamic analysis to detect and analyze advanced threats by executing suspicious files in a controlled environment and monitoring their behavior.

**23 operation(s)**:

_investigation_
- `add_tag(input_type: select, tag: text)` — Add Tag
- `delete_job(action_name: select, value: text)` — Delete Job
- `delete_submission(action_name: select, value: text)` — Delete Submission
- `delete_tag(input_type: select, tag: text)` — Delete Tag
- `get_analysis(action_name: select, [value: text])` — Get Analysis
- `get_iocs(sample_id: text, [all_artifacts: checkbox])` — Get IOCs
- `get_job(action_name: select, [value: text])` — Get Job Analysis
- `get_md_analysis(action_name: select, [value: text])` — Get Metadefender Analysis
- `get_md_job(action_name: select, [value: text])` — Get Metadefender Jobs
- `get_prescript(action_name: select, [value: text])` — Get Prescripts
- `get_reputation_job(action_name: select, [value: text])` — Get Reputation Jobs
- `get_reputation_lookup(action_name: select, [value: text])` — Get Reputation Lookups
- `get_samples(action_name: select, [value: text])` — Get Samples
- `get_screenshots(analysis_id: text)` — Get Screenshots
- `get_submission(action_name: select, [value: text])` — Get Submissions
- `get_system_info()` — Get System Information
- `get_tags(action_name: select, [value: text])` — Get Tags
- `get_threat_indicators(sample_id: text)` — Get Threat Indicators
- `get_vt_analysis(action_name: select, [value: text])` — Get VirusTotal Analysis
- `get_vt_job(action_name: select, [value: text])` — Get VirusTotal Jobs
- `submit_cyops_attachment(file_iri: text, [sample_type: select], [shareable: checkbox], [jobrule_entries: text], [reanalyze: checkbox], [max_jobs: integer], [tags: text])` — Submit Sample
- `submit_sample_by_url(sample_file: text, [sample_type: select], [shareable: checkbox], [jobrule_entries: text], [reanalyze: checkbox], [max_jobs: integer], [tags: text])` — Submit Sample Url
- `submit_url(sample_url: text)` — Submit URL


---

## Security Policy Automation

### `tufin` v1.0.0 _(installed)_
_Tufin_

Search for and enforce network security policies, perform network topology searches, and query network device information across managed firewalls, SDNs and cloud environments.

**10 operation(s)**:

- `tufin_get_change_info(ticket_id: integer)` — Get Change Info
- `tufin_get_zone_for_ip(ip: text)` — Get Zone for IP
- `tufin_policy_search(search: text)` — Policy Search
- `tufin_resolve_object(ip: text)` — Resolve Object
- `tufin_search_application_connections(app_id: integer)` — Search Application Connections
- `tufin_search_applications([name: text])` — Search Applications
- `tufin_search_devices([name: text], [ip: text], [vendor: text], [model: text])` — Search Devices
- `tufin_search_topology(source: text, destination: text, [service: text])` — Search Topology
- `tufin_search_topology_image(source: text, destination: text, [service: text])` — Search Topology Image
- `tufin_submit_change_request(request_type: select, request_priority: select, source: text, [destination: text], [protocol: select], [port: integer], [action: select], [comment: text], subject: text)` — Submit Change Request


---

## Security Posture Management

### `cymulate-phishing-awareness` v1.0.0 _(installed)_
_Cymulate Phishing Awareness - BAS_

Cymulate's Phishing Awareness campaigns evaluate employees' security awareness levels by simulating phishing attacks.

**8 operation(s)**:

_investigation_
- `create_phishing_awareness_contact_group([groupName: text])` — Create Phishing Awareness Contact Group
- `get_phishing_awareness_assessment_history([fromDate: datetime], [toDate: datetime], [env: text])` — Get Phishing Awareness Assessment History
- `get_phishing_awareness_assessment_id([env: text])` — Get Phishing Awareness assessment IDs
- `get_phishing_awareness_campaign_report_for_specific_assessment(id: text, [skip: integer], [limit: integer])` — Get Phishing Awareness Campaign Report for Specific Assessment
- `get_phishing_awareness_contact_groups()` — Get Phishing Awareness Contact Groups
- `get_phishing_awareness_contacts([groupId: text])` — Get Phishing Awareness Contacts
- `get_phishing_awareness_report([env: text])` — Get Phishing Awareness Report
- `get_phishing_awareness_report_for_specific_assessment(id: text)` — Get Phishing Awareness Report for Specific Assessment


---

## Server Virtualization

### `vmware-vsphere` v1.1.0 _(installed)_
_VMware vSphere_

VMware vSphere connector handle virtual machine actions like start and stop VM, snapshot VM etc.

**14 operation(s)** (+6 hidden):

_investigation_
- `get_vm_info(search_type: select, search_value: text)` — Get VM Information
- `list_vms()` — Get Registered VMs List

_miscellaneous_
- `create_vm(vm_name: text, [vm_compatibility: select], [os_type: select], datastore: select, cpu: text, memory_size: text, disk_size: text, disk_type: select, network: select, iso_path: text)` — Create VM
- `revert_snapshot(vm_name: text, snapshot_name: text)` — Revert Snapshot
- `snapshot_vm(vm_name: text, snapshot_name: text, [description: text], [memory: checkbox], [quiesce: checkbox])` — Snapshot VM
- `start_vm(vm_name: text)` — Start VM
- `stop_vm(vm_name: text)` — Stop VM
- `suspend_vm(vm_name: text)` — Suspend VM


---

## Service Management/Ticketing System

### `otrs` v1.0.3 _(installed)_
_OTRS_

OTRS is a service management suite. OTRS connector provides functionality to create, modify, and search tickets.

**4 operation(s)**:

_miscellaneous_
- `create_ticket(title: text, queue: text, state: select, priority: select, customer: text, article_subject: text, [article_body: text], [dynamicField: json], [newTicketType: select], [articleSenderType: text], [newDynamicField: object])` — Create Ticket
- `get_ticket(ticket_id: text)` — Get Ticket
- `search_tickets(state: multiselect, [ticket_title: text], [tickettype: multiselect], [timeSpanMinutes: integer])` — List Tickets
- `update_ticket(ticket_id: text, [title: text], [queue: text], [state: select], [priority: select], [customer: text], [article_subject: text], [article_body: text], [newTicketType: select], [newDynamicField: object], [oTRSArticle: object])` — Update Ticket


---

## Service Manager

### `bmc-remedyforce` v1.2.0 _(installed)_
_BMC Remedyforce_

BMC Remedyforce connector performs actions around creation and updation of incidents, interacts with knowledge base, service and approval requests.

**21 operation(s)** (+1 hidden):

_investigation_
- `add_client_note(incident_id: text, note: text, [summary: text])` — Add Client Note to a Service Request
- `all_knowledge_articles()` — Get All Knowledge Articles
- `all_service_requests([query: select], [record_count: text])` — Get All Service Requests
- `approve_pending_request(context_id: text, [next_approver_id: text], [comment: text])` — Approve Pending Approval Request
- `create_incident(client_id: text, [description: textarea])` — Create Incident
- `download_file(incident_id: text)` — Download file
- `get_categories()` — Get Categories
- `get_cmdb_attributes(type: select, class_name: text)` — Get CMDB Attributes
- `get_incident_details([incident_id: text])` — Get Incident Details
- `get_pending_approval_request()` — Get Pending Approval Request
- `get_queue_details(queue_id: text)` — Get Queue Details
- `get_queues(sobject_name: select)` — Get Sobject's Queue
- `knowledge_search(search_value: text)` — Knowledge Search
- `list_client_ids()` — Get List of Remedyforce Users
- `query_service_request_by_id(salesforce_id: text)` — Get Service Request Detail By IDs
- `reassign_pending_request(salesforce_id: text, actor_id: text)` — Reassign Pending Approval Request
- `reject_pending_request(context_id: text, [next_approver_id: text], [comment: text])` — Reject Pending Approval Request
- `run_query(query: text, query_type: select)` — Run Query
- `search_kb_article(salesforce_id: text)` — Get Knowledge Article Details
- `update_incident(incident_id: text, json_fields: json)` — Update Incident


---

## Software Based ADC

### `netscaler` v1.0.0 _(installed)_
_Netscaler VPX_

Citrix NetScaler VPX Connector

**5 operation(s)**:

_containment_
- `create_responder_policy(policy_name: text, rule: text, action: text)` — Create Responder Policy
- `ip_reputation(policy_name: text, rule: select, [threat_category: select], action: text)` — Create IP Reputation Policy
- `update_policy(policy_name: text, rule: text, option: select)` — Update Application Firewall Policy Expression

_investigation_
- `get_fwpolicy_details(policy_name: text)` — Get App FW Policy

- `create_responder_action(action_name: text, type: text, html_page_name: text, url: text, [response_code: text], [reason_phrase: text])` — Create Responder Action


---

## Source Code Management

### `azure-devops` v2.0.0 _(installed)_
_Azure DevOps_

Azure DevOps is a cloud-based service for managing software development projects. The Azure DevOps FortiSOAR connector integrates with Azure DevOps to automate the management of repositories, pipelines, work items, and more within FortiSOAR, enabling streamlined DevOps workflows and incident response.

**30 operation(s)**:

_investigation_
- `add_pull_request_reviewer(project: text, repositoryId: text, pullRequestId: text, reviewerId: text, [isRequired: checkbox])` — Add Pull Request Reviewer
- `create_branch(project: text, repositoryId: text, branch: text, commit_message: text, [previousCommitSha: text])` — Create Branch
- `create_merge_request(project: text, repositoryNameOrId: text, parents: text, comment: text)` — Create Merge Request
- `create_new_file_in_repository(project: text, repo_name: text, branch: text, previousCommitSha: text, file_path: text, content: textarea, commit_message: text)` — Create File
- `create_pull_request(project: text, repositoryId: text, title: text, sourceRefName: text, targetRefName: text, [description: textarea], [reviewers: text], [supportsIterations: checkbox], [additional_input: json])` — Create Pull Request
- `create_pull_request_comment(repositoryId: text, pullRequestId: integer, content: text, [threadId: integer], [parentCommentId: integer])` — Create Pull Request Comment
- `create_repository(project: text, repository: text, [parentRepository: text], [sourceRef: text])` — Create Repository
- `delete_branch(project: text, repositoryId: text, branch: text, previousCommitSha: text)` — Delete Branch
- `delete_existing_file_in_repository(project: text, repo_name: text, branch: text, previousCommitSha: text, file_path: text, commit_message: text)` — Delete File
- `execute_an_api_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_commit(project: text, repositoryId: text, commitId: text, [changeCount: integer])` — Get Commit Details
- `get_file_from_repository(repositoryId: text, versionDescriptor.version: text, path: text, [includeContent: checkbox], [includeContentMetadata: checkbox])` — Get File
- `get_pipeline_run(project: text, pipelineId: integer, runId: text)` — Get Pipeline Run Details
- `get_pull_requests_by_id(project: text, pullRequestId: integer)` — Get Pull Request Details
- `list_branches(project: text, repository: text, [filterContains: text], [filter: text], [includeMyBranches: checkbox], [includeStatuses: checkbox], [includeLinks: checkbox], [latestStatusesOnly: checkbox], [peelTags: checkbox], [continuationToken: text], [$top: text])` — Get Branch List
- `list_commits(project: text, repositoryId: text, [type: select])` — Get Commit List
- `list_pipeline_runs(project: text, pipelineId: integer)` — Get Pipeline Run List
- `list_pipelines(project: text, [field: text], [order: select], [continuationToken: text], [$top: integer])` — Get Pipeline List
- `list_projects([stateFilter: select], [continuationToken: text], [$skip: integer], [$top: integer])` — Get Project List
- `list_pull_request_comment(repositoryId: text, pullRequestId: integer, [threadId: integer])` — Get Pull Request Comment List
- `list_pull_request_commits(project: text, repositoryId: text, pullRequestId: text, [$top: integer], [continuationToken: text])` — Get Pull Request Commit List
- `list_pull_request_reviewers(project: text, repositoryId: text, pullRequestId: text)` — Get Pull Request Reviewer List
- `list_pull_requests(project: text, repositoryId: text, [searchCriteria.status: select], [searchCriteria: json], [$skip: integer], [$top: integer])` — Get Pull Request List
- `list_repositories(project: text, [includeHidden: checkbox], [includeAllUrls: checkbox], [includeLinks: checkbox])` — Get Repository List
- `list_users([scopeDescriptor: text], [continuationToken: text], [subjectTypes: text])` — Get User List
- `push_repository(project: text, repositoryId: text, branch: text, previousCommitSha: text, commit_message: text, clone_path: text)` — Push Changes
- `run_pipeline(project: text, pipelineId: integer, [stagesToSkip: text], [pipelineVersion: integer], [previewRun: checkbox], [resources: json])` — Run Pipeline
- `update_file_in_repository(project: text, repo_name: text, branch: text, previousCommitSha: text, file_path: text, content: textarea, operation: select, commit_message: text)` — Update File
- `update_pull_request(project: text, repositoryId: text, pullRequestId: text, [title: text], [description: textarea], [status: select], [targetRefName: text], [additional_input: json])` — Update Pull Request
- `update_repository(repositoryId: text, [name: text], [defaultBranch: text], [isDisabled: select])` — Update Repository


### `bitbucket` v1.0.0 _(installed)_
_Bitbucket_

Bitbucket is a comprehensive platform designed to streamline the software development process. It encompasses all aspects of the development lifecycle, offering seamless integration and efficiency throughout the journey from initial project planning to deployment and beyond. With Bitbucket, teams can seamlessly manage their source code, facilitate collaboration, and ensure the quality and security of their software.

**19 operation(s)**:

_investigation_
- `clone_repository(repo_type: select, repo_name: text, branch_name: text, [clone_zip: checkbox])` — Clone Repository
- `create_pull_request(repo_type: select, repo_name: text, fromRef: text, toRef: text, title: text, [description: richtext], [reviewers: text], [draft: checkbox], [additional_fields: json])` — Create Pull Request
- `create_pull_request_comment(repo_type: select, repo_name: text, id: integer, text: richtext, [severity: select], [state: select], [other_fields: json])` — Create Pull Request Comment
- `create_repository(repo_type: select, name: text, display_name: text, [links: json])` — Create Repository
- `create_repository_branch(repo_type: select, repo_name: text, name: text, startPoint: text)` — Create Repository Branch
- `create_tag(repo_type: select, repo_name: text, name: text, startPoint: text, [message: text], [type: select], [force: checkbox])` — Create Tag
- `create_update_file_contents(repo_type: select, repo_name: text, file_path: text, branch: text, content: textarea, message: text, [sourceBranch: text], [sourceCommitId: text])` — Create or Update File Contents
- `delete_repository(repo_type: select, repo_name: text)` — Delete Repository
- `delete_repository_branch(repo_type: select, repo_name: text, name: text, [endPoint: text], [dryRun: checkbox])` — Delete Repository Branch
- `find_repository_branches(repo_type: select, repo_name: text, [filterText: text], [boostMatches: checkbox], [details: checkbox], [order: select], [start: integer], [limit: integer])` — Get Repository Branch List
- `get_file_from_repository(repo_type: select, repo_name: text, at: text, file_path: text, [size: checkbox])` — Get File Details
- `get_users_with_repository_permission(repo_type: select, repo_name: text, [filter: text], [start: integer], [limit: integer])` — Get Member List of Repository
- `get_web_url()` — Get Server URL
- `list_pull_request(repo_type: select, repo_name: text, [pull_number: text], [filterText: text], [state: select], [direction: select], [withAttributes: checkbox], [withProperties: checkbox], [draft: select], [order: select], [start: integer], [limit: integer])` — Get Pull Request List
- `list_pull_requests_comments(repo_type: select, repo_name: text, id: integer, [fromId: text], [fromType: select], [start: integer], [limit: integer])` — Get Pull Request Comments
- `list_tags(repo_type: select, repo_name: text, [filterText: text], [orderBy: select], [start: integer], [limit: integer])` — Get Tag List
- `merge_pull_request(repo_type: select, repo_name: text, pullRequestId: text, [message: text], [strategyId: select], [version: integer], [autoSubject: checkbox], [autoMerge: checkbox])` — Merge Pull Request
- `update_clone_repository(file_iri: text, clone_path: text)` — Update Remote Repository
- `update_user_repository_permission(repo_type: select, repo_name: text, name: text, permission: select)` — Update User Repository Permission


### `github` v2.0.0 _(installed)_
_GitHub_

GitHub is a code hosting platform for collaboration and version control. This connector facilitates automated interactions with Github, such as to create and manage repositories, branches, issues, pull requests, and many more.

**45 operation(s)**:

_investigation_
- `add_pr_review(repo_type: select, repo: text, pull_number: integer, [commit_id: text], [body: text], [event: select])` — Add Pull Request Review
- `add_repository_collaborator(repo_type: select, repo: text, username: text, [permission: select])` — Add Repository Collaborator
- `add_reviewers(repo_type: select, repo: text, pull_number: integer, [reviewers: text], [team_reviewers: text])` — Add Reviewers for a Pull Request
- `clone_repository(repo_type: select, name: text, [branch: text], clone_zip: checkbox)` — Clone Repository
- `compare_commit(repo_type: select, repo: text, base: text, head: text, [per_page: integer], [page: integer])` — Get Commit Comparison
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
- `get_commit(repo_type: select, repo: text, ref: text, [per_page: integer], [page: integer])` — Get Commit
- `get_file_from_repository(repo_type: select, name: text, path: text, [branch: text], [decode_content: checkbox])` — Get File
- `get_repository(repo_type: select, repo: text)` — Get Repository
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


### `gitlab` v2.1.0 _(installed)_
_GitLab_

GitLab is a single application for the entire software development lifecycle. From project planning and source code management to CI/CD, monitoring, and security.

**45 operation(s)**:

_investigation_
- `add_member_to_project_or_group(to: select, username: text, access_level: select, [other_fields: json])` — Add Member to Repository
- `clone_repository(repo_type: select, repo_name: text, branch_name: text, [clone_zip: checkbox])` — Clone Repository
- `compare_commit(repo_type: select, repo_name: text, base: text, head: text)` — Get Commit Comparison
- `create_issue(repo_type: select, repo_name: text, title: text, [description: text], [assignee_name: text], [assignee_names: text], [labels: text], [other_fields: json])` — Create Issue
- `create_issue_comment(repo_type: select, repo_name: text, issue_iid: text, body: richtext, [confidential: checkbox], [other_fields: json])` — Create Issue Comment
- `create_merge_request(repo_type: select, repo_name: text, source_branch: text, target_branch: text, title: text, [description: richtext], [target_project_id: text], [remove_source_branch: checkbox], [other_fields: json])` — Create Merge Request
- `create_merge_request_comment(repo_type: select, repo_name: text, merge_request_iid: integer, body: richtext, [other_fields: json])` — Create Merge Request Comment
- `create_new_file_in_repository(repo_type: select, repo_name: text, branch: text, file_path: text, content: textarea, commit_message: text, [author_email: text], [author_name: text])` — Create File
- `create_project(repo_type: select, name: text, [description: text], [visibility: select], [issues_access_level: select], [wiki_access_level: select], [other_fields: json])` — Create Repository
- `create_project_using_templates(repo_type: select, name: text, use_custom_template: checkbox, create_by: select, [description: text], [visibility: select], [issues_access_level: select], [wiki_access_level: select], [other_fields: json])` — Create Repository Using Templates
- `create_release(repo_type: select, repo_name: text, tag_name: text, [ref: text], [tag_message: text], [release_name: text], [description: richtext], [other_fields: json])` — Create Release
- `create_repository_branch(repo_type: select, repo_name: text, branch: text, ref: text)` — Create Repository Branch
- `delete_existing_file_in_repository(repo_type: select, repo_name: text, branch: text, file_path: text, commit_message: text, [author_email: text], [author_name: text])` — Delete File
- `delete_project(repo_type: select, repo_name: text)` — Delete Repository
- `delete_repository_branch(repo_type: select, repo_name: text, branch: text)` — Delete Repository Branch
- `edit_project(repo_type: select, repo_name: text, [name: text], [description: text], [visibility: select], [issues_access_level: select], [wiki_access_level: select], [other_fields: json])` — Update Repository
- `fetch_upstream(repo_type: select, repo_name: text, title: text, source_branch: text, target_branch: text, [description: richtext])` — Fetch Upstream
- `fork_project(repo_type: select, repo_name: text, [name: text], [description: text], [visibility: select], [other_fields: json])` — Fork Repository
- `get_commit(repo_type: select, repo_name: text, ref: text)` — Get Commit
- `get_file_from_repository(repo_type: select, repo_name: text, ref: text, file_path: text, [decode_content: checkbox])` — Get File
- `get_member_list_of_project(repo_type: select, repo_name: text, [page: integer], [per_page: integer], [other_fields: json])` — Get Member List of Repository
- `get_merge_request_approval_state(repo_type: select, repo_name: text, merge_request_iid: integer)` — Get Approval State of Merge Request
- `get_project(repo_type: select, name: text)` — Get Repository
- `get_single_repository_branch(repo_type: select, repo_name: text, branch: text)` — Get Repository Branch
- `get_web_url()` — Get Server URL
- `list_authenticated_user_projects([min_access_level: select], [visibility: select], [order_by: select], [sort: select], [page: integer], [per_page: integer], [other_fields: json])` — List Authenticated User Repositories
- `list_fork_projects(repo_type: select, repo_name: text, [order_by: select], [sort: select], [page: integer], [per_page: integer], [other_fields: json])` — List Fork Repositories
- `list_group_projects(org: text, [visibility: select], [order_by: select], [sort: select], [page: integer], [per_page: integer], [other_fields: json])` — List Group Repositories
- `list_merge_requests_comments(repo_type: select, repo_name: text, merge_request_iid: integer, [order_by: select], [sort: select])` — List Merge Request Comments
- `list_merge_requests_reviewers(repo_type: select, repo_name: text, merge_request_iid: integer)` — List Merge Request Reviewers
- `list_project_issues(repo_type: select, repo_name: text, [assignee_id: text], [state: select], [created_after: datetime], [updated_after: datetime], [order_by: select], [sort: select], [page: integer], [per_page: integer], [other_fields: json])` — List Repository Issues
- `list_project_merge_requests(repo_type: select, repo_name: text, [iids: integer], [state: select], [source_branch: text], [target_branch: text], [order_by: select], [sort: select], [page: integer], [per_page: integer], [other_fields: json])` — List Repository Merge Requests
- `list_releases(repo_type: select, repo_name: text, [order_by: select], [sort: select], [page: integer], [per_page: integer], [other_fields: json])` — List Releases
- `list_repository_branches(repo_type: select, repo_name: text, [regex: text])` — List Repository Branches
- `list_starrers(repo_type: select, repo_name: text, [search: text])` — List Starrers
- `list_user_projects(user_id: text, [owned: checkbox], [visibility: select], [order_by: select], [sort: select], [page: integer], [per_page: integer], [other_fields: json])` — List User Repositories
- `merge_merge_request(repo_type: select, repo_name: text, merge_request_iid: integer, [merge_commit_message: text], [should_remove_source_branch: checkbox], [other_fields: json])` — Merge a Merge Request
- `push_repository(repo_type: select, project_name: text, clone_path: text, branch: text, commit_message: text, [commit_description: textarea])` — Push Changes
- `review_merge_request(repo_type: select, repo_name: text, merge_request_iid: integer, action: select)` — Review Merge Request
- `set_project_notification_level(repo_type: select, repo_name: text, level: select, [other_fields: json])` — Update Repository Notification Level
- `star_project(repo_type: select, repo_name: text)` — Star Repository
- `update_clone_repository(file_iri: text, clone_path: text)` — Update Remote Repository
- `update_file_in_repository(repo_type: select, repo_name: text, branch: text, file_path: text, content: textarea, operation: select, commit_message: text)` — Update File
- `update_issue(repo_type: select, repo_name: text, issue_iid: text, [title: text], [description: richtext], [assignee_names: text], [confidential: select], [issue_type: select], [state_event: select], [labels: text], [due_date: date], [other_fields: json])` — Update Issue
- `update_merge_request(repo_type: select, repo_name: text, merge_request_iid: integer, [title: text], [assignee_names: text], [reviewer_names: text], [target_branch: text], [state_event: select], [description: text], [remove_source_branch: select], [other_fields: json])` — Update Merge Request


---

## Storage

### `pure-storage-flasharray` v1.0.0 _(installed)_
_Pure Storage FlashArray_

Pure Storage is a leading provider of enterprise data storage solutions. It is specialize in all-flash storage arrays, delivering high-performance, reliable, and scalable storage solutions for businesses. With Pure Storage FlashArray, organizations can accelerate applications, improve productivity, and make data-driven decisions. Experience the power of next-generation storage technology with Pure Storage FlashArray.

**9 operation(s)**:

_investigation_
- `get_alerts([based_on: select], [filter: text], [sort: text], [flagged: select], [total_item_count: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Alert List
- `get_arrays([based_on: select], [filter: text], [fqdns: text], [sort: text], [total_item_count: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Array List
- `get_audits([based_on: select], [filter: text], [sort: text], [total_item_count: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Audit List
- `get_controllers([names: text], [filter: text], [sort: text], [total_item_count: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Controller List
- `get_directories([based_on: select], [filesystem_filter: select], [filter: text], [sort: text], [destroyed: select], [total_item_count: checkbox], [total_only: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Directory List
- `get_drives([names: text], [filter: text], [sort: text], [total_item_count: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Drive List
- `get_protection_groups([names: text], [filter: text], [sort: text], [destroyed: select], [total_item_count: checkbox], [total_only: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Protection Group List
- `get_sessions([based_on: select], [filter: text], [sort: text], [total_item_count: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Session List
- `get_volumes([based_on: select], [filter: text], [sort: text], [destroyed: select], [total_item_count: checkbox], [total_only: checkbox], [continuation_token: text], [offset: integer], [limit: integer])` — Get Volume List


### `veeam-backup-replication` v1.0.0 _(installed)_
_Veeam Backup & Replication_

Veeam Backup & Replication is a data protection and disaster recovery solution that enables backup, recovery, and replication for virtual, physical, and cloud-based workloads.

**16 operation(s)**:

_investigation_
- `create_malware_event(detectionTimeUtc: datetime, machine: json, details: text, engine: text)` — Create Malware Event
- `execute_an_api_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_backup_list([nameFilter: text], [createdAfterFilter: datetime], [createdBeforeFilter: datetime], [platformIdFilter: text], [jobIdFilter: text], [policyTagFilter: text], [orderColumn: select], [orderAsc: checkbox], [skip: integer], [limit: integer])` — Get Backup List
- `get_malware_event_list([detectedAfterTimeUtcFilter: datetime], [detectedBeforeTimeUtcFilter: datetime], [typeFilter: select], [stateFilter: select], [severityFilter: select], [sourceFilter: select], [backupObjectIdFilter: text], [createdByFilter: text], [engineFilter: text], [orderColumn: select], [orderAsc: checkbox], [skip: integer], [limit: integer])` — Get Malware Event List
- `get_managed_server_list([nameFilter: text], [typeFilter: select], [viTypeFilter: select], [orderColumn: select], [orderAsc: checkbox], [skip: integer], [limit: integer])` — Get Managed Server List
- `get_microsoft_entra_id_tenant_list([nameFilter: text], [orderColumn: select], [orderAsc: checkbox], [skip: integer], [limit: integer])` — Get Microsoft Entra ID Tenant List
- `get_repository_state_list([idFilter: text], [nameFilter: text], [typeFilter: select], [capacityFilter: decimal], [freeSpaceFilter: decimal], [usedSpaceFilter: decimal], [isOnlineFilter: checkbox], [orderColumn: select], [orderAsc: checkbox], [skip: integer], [limit: integer])` — Get Repository State List
- `get_restore_point_list([nameFilter: text], [createdAfterFilter: datetime], [createdBeforeFilter: datetime], [platformIdFilter: text], [backupIdFilter: text], [backupObjectIdFilter: text], [platformNameFilter: select], [malwareStatusFilter: select], [orderColumn: select], [orderAsc: checkbox], [skip: integer], [limit: integer])` — Get Restore Point List
- `get_security_compliance_analyzer_results()` — Get Security & Compliance Analyzer Results
- `get_server_list([filter_mode: select], [sort_by: select], [skip: integer], [limit: integer])` — Get Server List
- `get_unstructured_data_server_list([nameFilter: text], [orderColumn: select], [orderAsc: checkbox], [skip: integer], [limit: integer])` — Get Unstructured Data Server List
- `scan_backup(backupId: text, backupObjectId: text, scanMode: select, scanEngine: multiselect, [scanRange: checkbox], [continueScan: checkbox])` — Scan Backups with Antivirus or YARA Rules
- `start_configuration_backup()` — Start Configuration Backup
- `start_instant_recovery(restorePointId: text, type: select, [antivirusScanEnabled: checkbox], [vmTagsRestoreEnabled: checkbox], [nicsEnabled: checkbox], [powerUp: checkbox], [reason: text])` — Start Instant Recovery
- `start_quick_backup(platform: select, [size: text], [urn: text])` — Start Quick Backup
- `start_security_compliance_analyzer()` — Start Security & Compliance Analyzer


---

## System Management

### `jumpcloud` v1.1.0 _(installed)_
_JumpCloud_

JumpCloud is Directory-as-a-Service (DaaS) is the single point of authority to authenticate, authorize, and manage the identities of a business's employees and the systems and IT resources they need access to.

**7 operation(s)**:

_investigation_
- `create_command(command: text, name: text, id: text, commandType: select, launchType: select, [timeout: text])` — Create Command
- `get_commands([CommandID: text])` — Get Commands
- `get_organizations([OrganizationID: text])` — Get Organizations
- `get_systems([SystemID: text])` — Get Systems
- `get_users([UserID: text])` — Get Users
- `manage_associations_of_command(Command_ID: text, op: select, type: select, id: text)` — Manage Command Associations
- `trigger_command(triggername: text)` — Trigger Command


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

## TIP

### `bluvector` v1.0.0 _(installed)_
_BluVector_

BluVector Connector is network security tool responding to the world's most sophisticated threats in real time

**2 operation(s)**:

_investigation_
- `get_all_events([limit: integer], [days_back: select], [from: datetime], [to: datetime])` — Get All Events
- `get_event_information(event_id: text)` — Get Complete Event Information


---

## Threat Awareness & Response

### `illuminate` v1.0.0 _(installed)_
_Illuminate_

Illuminate Connector

**8 operation(s)**:

_investigation_
- `query_domain_indicator(indicator: text)` — Query Domain Indicator
- `query_email_indicator(indicator: text)` — Query Email Address Indicator
- `query_hash_indicator(indicator: text)` — Query Hash Indicator
- `query_http_request_indicator(indicator: text)` — Query HTTP Request Indicator
- `query_ipv4_indicator(indicator: text)` — Query IPv4 Indicator
- `query_ipv6_indicator(indicator: text)` — Query IPv6 Indicator
- `query_mutex_indicator(indicator: text)` — Query Mutex Indicator
- `query_string_indicator(indicator: text)` — Query String Indicator


---

## Threat Detection

### `alienvault-usm-anywhere` v1.2.0 _(installed, ingestion)_
_AlienVault USM Anywhere_

AlienVault USM Anywhere Connector can be used to automate actions like get events, get event details, get alarm details, get alarms, get alarm labels, add alarm labels and delete alarm labels

**7 operation(s)**:

_investigation_
- `add_alarm_label(alarmId: text, labelId: text)` — Add Alarm Label
- `delete_alarm_label(alarmId: text, labelId: text)` — Delete Alarm Label
- `get_alarm_details(alarmId: text)` — Get Alarm Details
- `get_alarm_labels(alarmId: text)` — Get Alarm Labels
- `get_alarms([page: integer], [size: integer], [sort: select], [sort_order: select], [status: select], [suppressed: checkbox], [rule_intent: text], [rule_method: text], [rule_strategy: text], [priority_label: text], [alarm_sensor_sources: text], [timestamp_occured_gte: datetime], [timestamp_occured_lte: datetime])` — Get Alarms
- `get_event_details(eventId: text)` — Get Event Details
- `get_events([accountName: text], [page: integer], [size: integer], [sort: select], [sort_order: select], [suppressed: checkbox], [plugin: text], [eventName: text], [sourceName: text], [sensorUUID: text], [sourceUsername: text], [timestamp_occured_gte: datetime], [timestamp_occured_lte: datetime])` — Get Events


### `alphamountain` v1.0.0 _(installed)_
_alphaMountain_

alphaMountain Threat Response integrates investigations informed by reputation scores of target hosts, domains, and IP addresses. It fetches indicators with risk scores and relevant content categorization.

**4 operation(s)**:

_investigation_
- `get_domain_popularity(domain: text)` — Get Popularity of Domain
- `get_threat_score(input_type: select)` — Get Threat Score
- `get_url_categories(input_type: select)` — Get URL Categories
- `identify_impersonation_detection(url: text, limit: text)` — Get Likely Impersonated Domain for a URL


### `attivo-botsink` v1.0.1 _(installed)_
_Attivo BOTsink_

Attivo Botsink connector is network-based threat deception for post-compromise threat detection.

**21 operation(s)**:

_investigation_
- `add_domain_to_whitelist(domain: text)` — Add Domain to Whitelist
- `check_host(hostname: text)` — Check Host
- `check_user(user: text)` — Check User
- `deploy_decoy(vulnerable_ip: text, [decoy_number: integer])` — Deploy Decoy
- `get_MITM_configuration()` — Get MITM Configuration
- `get_MITM_events()` — Get MITM Events
- `get_access_control_rules()` — Get Access Control Rules
- `get_all_faults()` — Get All Faults
- `get_all_vm_status()` — Get All VM Status
- `get_all_vulnerabilities()` — Get All Vulnerabilities
- `get_details_of_object(object_type: select, object_id: text)` — Get Details of Object
- `get_events(attacker_ip: text, [severity: select], alerts_start_date: datetime, alerts_end_date: datetime)` — Get Events
- `get_manager_users()` — Get Manager Users
- `get_network_data()` — Get Network Data
- `get_summary_of_objects(object_type: select)` — Get Summary of Objects
- `get_vm_status(vm_id: text)` — Get VM Status
- `get_whitelisted_domains()` — Get Whitelisted Domains
- `list_hosts()` — Get Host List
- `list_playbooks()` — List Playbooks
- `run_endpoint_forensics(ip_address: text)` — Run Forensics
- `run_playbook(playbook_name: text, attacker_ip: text)` — Run Playbook


### `lumu` v1.0.0 _(installed, ingestion)_
_LUMU_

LUMU provides Real-time detection, analysis, and response to network threats.

**5 operation(s)**:

_investigation_
- `close_incident(incident_uuid: text, [comment: text])` — Close Incident
- `get_incident_by_uuid(incident_uuid: text)` — Get Incident by UUID
- `get_incident_context(incident_uuid: text, hash: text)` — Get Incident Context
- `get_incident_endpoints(incident_uuid: text, [endpoints: text], [labels: text], [page: integer], [items: integer])` — Get Incident Endpoints
- `get_incidents([fromDate: datetime], [toDate: datetime], [status: multiselect], [adversary-types: multiselect], [labels: text], [page: integer], [items: integer])` — Get Incidents


### `microsoft-advanced-threat-analytics` v1.0.0 _(installed)_
_Microsoft Advanced Threat Analytics_

Microsoft Advanced Threat Analytics (ATA) is an on-premises platform that helps protect your enterprise from multiple types of advanced targeted cyber attacks and insider threats.

**4 operation(s)**:

_investigation_
- `get_entity(entity_id: text)` — Get Entity
- `get_monitoring_alerts_list()` — Get Monitoring Alerts List
- `get_suspicious_activities_list(activity_id: text)` — Get Suspicious Activities List
- `set_suspicious_activity_status(activity_id: text, status: text)` — Set Suspicious Activity Status


### `robtex` v1.0.0 _(installed)_
_Robtex_

Robtex uses various sources to gather public information about IP numbers, domain names, host names, autonomous systems, routes, etc., doing data forensics, investigating competitors, tracking spammers, hackers, or hackers or a virus.This connector facilitates automated operations to pull forward and reverse of an IP number and an AS number together with GEO-location data and network data.

**2 operation(s)**:

_investigation_
- `get_autonomous_system_query_details(autonomous_system_number: text)` — Get Autonomous System Query Details
- `get_ip_query_details(ip_address: text)` — Get IP Query Details


### `sap-etd` v1.1.0 _(installed, ingestion)_
_SAP Enterprise Threat Detection_

SAP Enterprise Threat Detection (ETD) helps you to identify the real attacks as they are happening and analyze the threats quickly enough to neutralize them before serious damage occurs. SAP Enterprise Threat Detection connector performs action like get alerts.

**1 operation(s)**:

_investigation_
- `get_alert([$query: text], [$format: select], [$batchSize: integer], [$patternFilter: text], [$includeEvents: checkbox], [$includeTestAlerts: checkbox], [$autoConfirm: checkbox])` — Get Alerts


### `sap-etd-cloud` v1.0.0 _(installed, ingestion)_
_SAP Enterprise Threat Detection Cloud_

SAP Enterprise Threat Detection (ETD), Cloud Edition helps you to identify the real attacks as they are happening and analyze the threats quickly enough to neutralize them before serious damage occurs. SAP Enterprise Threat Detection Cloud Edition connector performs action like get and ingest Events, Alerts and Investigations.

**3 operation(s)**:

_investigation_
- `get_alert_by_id(alertID: integer)` — Get Alert Details
- `get_alerts([limit: integer], startTime: datetime, endTime: datetime)` — Get Alerts
- `get_investigations(alertID: integer, [limit: integer])` — Get Investigations


### `taegis-xdr` v1.2.0 _(installed)_
_Taegis XDR_

SecureWorks Taegis™ XDR offers superior detection, unmatched response and an open platform built from the ground up to integrate market-leading technologies and deliver the highest ROI.

**16 operation(s)**:

_investigation_
- `add_alerts_to_investigation(investigation_id: text, alerts: text)` — Add Alerts to Investigation
- `add_events_to_investigation(investigation_id: text, events: text)` — Add Events to Investigation
- `create_comment(investigationId: text, comment: text)` — Create Comment
- `create_investigation(description: text, [key_findings: text], [priority: integer], [status: select], [assignee_id: text], [alerts: text])` — Create Investigation
- `execute_playbook([playbookInstanceId: text], [parameters: json])` — Execute Playbook
- `get_alerts(cql_query: text, [limit: integer], [offset: integer])` — Get Alerts
- `get_assets([filter_asset_state: select], [order_by: select], [orderDirection: select], [only_most_recent: checkbox], [limit: integer], [offset: integer])` — Get Assets
- `get_endpoint(id: text)` — Get Endpoint
- `get_investigations([query: text], [orderByField: select], [orderDirection: select], [page: integer], [perPage: integer])` — Get Investigations
- `get_investigations_alerts(investigation_id: text, [page: integer], [perPage: integer])` — Get Investigations Alerts
- `get_playbook_execution(playbookExecutionId: text)` — Get Playbook Execution
- `get_user_by_id(id: text, tenant_id: text)` — Get User by ID
- `isolate_assets(id: text, reason: text)` — Isolate Assets
- `unarchive_investigation(investigation_id: text)` — Unarchive Investigation
- `update_alert_status(alert_ids: text, resolution_status: select, reason: text)` — Update Alert Status
- `update_investigation(investigation_id: text, [description: text], [key_findings: text], [priority: integer], [status: select], [assignee_id: text])` — Update Investigation


---

## Threat Detector

### `stealthwatch` v2.1.0 _(installed)_
_Cisco Stealthwatch_

Stealthwatch is the solution that detects threats across your private network, public clouds, and even in encrypted traffic.

**14 operation(s)**:

_investigation_
- `application_traffic_domainid(domain_id: text, [start: datetime], [end: datetime])` — Get Application Traffic by Domain ID
- `application_traffic_hostgroupid(domain_id: text, hostgroupid: text, [start: datetime], [end: datetime])` — Get Application Traffic by Host Group ID
- `application_traffic_ip(domain_id: text, flowcollectordeviceid: text, exporterip: text, interface: text, [start: datetime], [end: datetime])` — Get Application Traffic by Exporter IP
- `get_domain_details()` — Get Domain Details
- `get_flow_search_results(tenant_id: text, query_id: text)` — Get Flow Search Results
- `get_flow_search_status(tenant_id: text, query_id: text)` — Get Flow Search Status
- `get_host_details(tenant_id: text, host_type: select, [hostGroupId: text])` — Get Host Group Details
- `get_top_conversation_result(tenant_id: text, query_id: text)` — Get Top Conversation Flow Search Result
- `get_top_conversation_status(tenant_id: text, query_id: text)` — Get Top Conversation Flow Search Status
- `initiate_flow_analysis(tenantID: text, [flowAnalysis: json])` — Initiate Flow Analysis
- `initiate_flow_search(tenant_id: text, [searchName: text], startDateTime: datetime, endDateTime: datetime, [recordLimit: text], [subject: json], [peer: json], [flow: json])` — Initiate Flow Search
- `list_host_groups(tenant_id: text, host_type: select, [hierarchy_view: checkbox])` — Get Host Groups List
- `threats_top_alarms(tenantId: text, tagId: text)` — Get External Threats Top Alarm Host
- `top_conversation_flow(tenant_id: text, startTime: datetime, endTime: datetime, [searchName: text], [maxRows: text], [orientation: select], [orderBy: select], [standardOptions: checkbox], [excludeBpsPps: checkbox], [excludeOthers: checkbox], [excludeCounts: checkbox], [flowCollectors: text], [subject: json], [peer: json], [connection: json])` — Initiate Top Conversation Flow Search


---

## Threat Hunting

### `infocyte` v1.1.0 _(installed)_
_Infocyte_

Infocyte connector provides automated actions to get hosts details, run a scan on hosts and get a scan result

**16 operation(s)**:

_investigation_
- `get_accounts([target_id: text], [duration: select], [scan_id_with_target: text], [privilege_admin: checkbox], [privilege_user: checkbox], [privilege_guest: checkbox], [order: select], [types: select], [offset: integer], [limit: integer], [open_query: json])` — Get Accounts
- `get_address([filter_by: select], [filter_value: text], [offset: integer], [limit: integer], [open_query: json])` — Get Host Addresses
- `get_artifacts([target_id: text], [duration: select], [scan_id_with_target: text], [flag_verified_good: checkbox], [flag_probably_good: checkbox], [flag_probably_bad: checkbox], [flag_verified_bad: checkbox], [threat_whitelist: checkbox], [threat_notMalicious: checkbox], [threat_malicious: checkbox], [threat_suspicious: checkbox], [threat_unknown: checkbox], [threat_localWhitelist: checkbox], [threat_localBlacklist: checkbox], [score: select], [score_value: integer], [count: select], [count_value: integer], [status_signed: checkbox], [status_no_signed: checkbox], [status_managed: checkbox], [status_no_managed: checkbox], [status_hasAvScan: checkbox], [status_no_hasAvScan: checkbox], [status_staticAnalysis: checkbox], [status_no_staticAnalysis: checkbox], [status_dynamicAnalysis: checkbox], [status_no_dynamicAnalysis: checkbox], [failed: checkbox], [order: select], [types: select], [offset: integer], [limit: integer], [open_query: json])` — Get Artifacts
- `get_artifacts_details([id: text], [offset: integer], [limit: integer])` — Get Artifact Details
- `get_artifacts_for_hosts([open_query: json])` — Get Hosts Artifacts
- `get_drivers([target_id: text], [duration: select], [scan_id_with_target: text], [flag_verified_good: checkbox], [flag_probably_good: checkbox], [flag_probably_bad: checkbox], [flag_verified_bad: checkbox], [threat_whitelist: checkbox], [threat_notMalicious: checkbox], [threat_malicious: checkbox], [threat_suspicious: checkbox], [threat_unknown: checkbox], [threat_localWhitelist: checkbox], [threat_localBlacklist: checkbox], [score: select], [score_value: integer], [count: select], [count_value: integer], [status_signed: checkbox], [status_no_signed: checkbox], [status_managed: checkbox], [status_no_managed: checkbox], [status_hasAvScan: checkbox], [status_no_hasAvScan: checkbox], [status_staticAnalysis: checkbox], [status_no_staticAnalysis: checkbox], [status_dynamicAnalysis: checkbox], [status_no_dynamicAnalysis: checkbox], [failed: checkbox], [order: select], [types: select], [offset: integer], [limit: integer], [open_query: json])` — Get Drivers
- `get_drivers_details([id: text], [offset: integer], [limit: integer])` — Get Driver Details
- `get_modules([target_id: text], [duration: select], [scan_id_with_target: text], [flag_verified_good: checkbox], [flag_probably_good: checkbox], [flag_probably_bad: checkbox], [flag_verified_bad: checkbox], [threat_whitelist: checkbox], [threat_notMalicious: checkbox], [threat_malicious: checkbox], [threat_suspicious: checkbox], [threat_unknown: checkbox], [threat_localWhitelist: checkbox], [threat_localBlacklist: checkbox], [score: select], [score_value: integer], [count: select], [count_value: integer], [status_signed: checkbox], [status_no_signed: checkbox], [status_managed: checkbox], [status_no_managed: checkbox], [status_hasAvScan: checkbox], [status_no_hasAvScan: checkbox], [status_staticAnalysis: checkbox], [status_no_staticAnalysis: checkbox], [status_dynamicAnalysis: checkbox], [status_no_dynamicAnalysis: checkbox], [failed: checkbox], [order: select], [types: select], [offset: integer], [limit: integer], [open_query: json])` — Get Modules
- `get_modules_details([id: text], [offset: integer], [limit: integer])` — Get Module Details
- `get_processes([target_id: text], [duration: select], [scan_id_with_target: text], [flag_verified_good: checkbox], [flag_probably_good: checkbox], [flag_probably_bad: checkbox], [flag_verified_bad: checkbox], [threat_whitelist: checkbox], [threat_notMalicious: checkbox], [threat_malicious: checkbox], [threat_suspicious: checkbox], [threat_unknown: checkbox], [threat_localWhitelist: checkbox], [threat_localBlacklist: checkbox], [score: select], [score_value: integer], [count: select], [count_value: integer], [status_signed: checkbox], [status_no_signed: checkbox], [status_managed: checkbox], [status_no_managed: checkbox], [status_hasAvScan: checkbox], [status_no_hasAvScan: checkbox], [status_staticAnalysis: checkbox], [status_no_staticAnalysis: checkbox], [status_dynamicAnalysis: checkbox], [status_no_dynamicAnalysis: checkbox], [failed: checkbox], [order: select], [types: select], [offset: integer], [limit: integer], [open_query: json])` — Get Processes
- `get_processes_details([id: text], [offset: integer], [limit: integer])` — Get Process Details
- `get_scan([offset: integer], [limit: integer], [open_query: json])` — Get Scans
- `get_scan_status([id: text])` — Get Scan Status By User Task ID
- `get_scans_with_target([target_id: text])` — Get Scans Of Target
- `get_target_group([id: text], [offset: integer], [limit: integer], [open_query: json])` — Get Target Group Details
- `run_scan(targetId: text, [hostId: text], [EnableDriver: checkbox], [EnableMemory: checkbox], [EnableArtifact: checkbox], [EnableAutostart: checkbox], [EnableHook: checkbox], [EnableNetwork: checkbox], [EnableApplication: checkbox], [EnableSurveyDelete: checkbox], [EnableLogDelete: checkbox])` — Run Scan


---

## Threat Hunting and Intelligence

### `vectra` v4.0.0 _(installed)_
_Vectra_

Vectra provides automated threat detection, empowers threat hunting and exposes hidden attackers

**15 operation(s)**:

_investigation_
- `get_accounts_list([min_id: integer], [max_id: integer], [min_threat: integer], [max_threat: integer], [min_certainty: integer], [max_certainty: integer], [state: select], [search_query: text], [search_query_only: text], [min_privilege_level: integer], [max_privilege_level: integer], [privilege_category: select], [tags: string], [query_parameter: json])` — Get Accounts List
- `get_assignments_by_id([assignments_id: integer])` — Get Assignments By ID
- `get_assignments_list([account_ids: integer], [assignee_ids: integer], [host_ids: integer], [outcome_ids: integer], [resolved: checkbox], [query_parameter: json])` — Get Assignments List
- `get_audit_log_events_associated_with_a_user_id([user_id: integer])` — Get Audit Log Events Associated with a User ID
- `get_detection_by_id([detection_id: integer])` — Get Detection By ID
- `get_detections_list([min_id: integer], [max_id: integer], [min_threat: integer], [max_threat: integer], [min_certainty: integer], [max_certainty: integer], [state: select], [search_query: text], [search_query_only: text], [query_parameter: json])` — Get Detections
- `get_groups_list([group_type: select], [account_names: text], [domains: text], [host_ids: text], [host_names: text], [importance: select], [ips: text], [description: text], [last_modified_timestamp: datetime], [last_modified_by: text], [group_name: text], [query_parameter: json])` — Get Groups List
- `get_host_by_id([host_id: integer])` — Get Host By ID
- `get_hosts_list([min_id: integer], [max_id: integer], [min_threat: integer], [max_threat: integer], [min_certainty: integer], [max_certainty: integer], [state: select], [search_query: text], [search_query_only: text], [query_parameter: json])` — Get Hosts
- `get_outcome_by_id([outcome_id: integer])` — Get Outcome By ID
- `get_outcomes_list()` — Get Outcomes List
- `get_threat_feeds([query_parameter: json])` — Get Threat Feeds
- `get_users_list([username: text], [role: text], [type: text], [last_login_datetime: datetime], [query_parameter: json])` — Get Users List
- `get_vectra_match_rules([query_parameter: json])` — Get Vectra Match Rules
- `send_custom_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request


---

## Threat Hunting and Search

### `mobile-security-framework` v1.0.0 _(installed)_
_Mobile Security Framework_

Mobile Security Framework (MobSF) is an automated, all-in-one mobile application (Android/iOS/Windows) pen-testing, malware analysis and security assessment framework capable of performing static and dynamic analysis. MobSF support mobile app binaries (APK, XAPK, IPA & APPX) along with zipped source code and provides REST APIs for seamless integration with your CI/CD or DevSecOps pipeline.

**13 operation(s)** (+1 hidden):

_investigation_
- `compare_scan_results(hash1: text, hash2: text)` — Compare Scan Results
- `delete_scan(hash: text)` — Delete Scan Result
- `delete_suppressions(hash: text, type: select, rule: text, kind: select)` — Delete Suppressions
- `display_recent_scans([page: integer], [page_size: text])` — List Recent Scans
- `generate_json_report(hash: text)` — Generate JSON Report
- `generate_pdf_report(hash: text, file_name: text)` — Generate PDF Report
- `get_app_scorecard(hash: text)` — Get App Scorecard
- `scan_file(scan_type: select, file_name: text, hash: text, [re_scan: checkbox])` — Scan File
- `suppress_by_rule(hash: text, type: select, rule: text)` — Suppress by Rule
- `upload_file(input: select, value: text)` — Upload File
- `view_source_files(file: text, hash: text, type: select)` — View Source Files
- `view_suppressions(hash: text)` — List Suppressions


---

## Threat Intel

### `malwaredomainlist` v1.0.0 _(installed)_
_Malware Domain List_

Get information for specified ip address or domain from Malware Domain List

**2 operation(s)**:

_investigation_
- `domain_lookup([domain: text], [limit: select])` — Domain Lookup
- `ip_lookup([ip: text], [limit: select])` — IP Lookup


---

## Threat Intelligence

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

_investigation_
- `get_alarm_details(alarmId: text)` — Get Alarm Details
- `get_deployments()` — Get Deployments
- `search_alarms([timestamp_occured_gte: datetime], [timestamp_occured_lte: datetime], [priority_label: text], [status: text], [suppressed: checkbox], [additional_filters: json], [sort: checkbox], [page: integer], [size: integer])` — Search Alarms
- `search_assets([timestamp_occured_gte: datetime], [timestamp_occured_lte: datetime], [sort: checkbox], [page: integer], [size: integer])` — Search Assets


### `alphamountain-feed` v1.0.0 _(installed, ingestion)_
_alphaMountain Feed_

The AlphaMountain feed connector facilitates seamless integration with AlphaMountain's data sources, providing access to real-time and historical data on domain popularity, cybersecurity insights, risk scores and relevant content categorization and more.

**2 operation(s)** (+1 hidden):

_investigation_
- `get_indicators([start: datetime], [flags: multiselect], [risk_min: integer], [risk_min: integer], [include_categories: checkbox], [include_popularity: checkbox], [limit: integer])` — Get Indicators


### `anomali-limo-threat-intel-feed` v2.0.0 _(installed, ingestion)_
_Anomali Limo Threat Intel Feed_

Anomali Limo is a preconfigured set of intelligence feeds that STAXX users can access immediately upon download, and which offers indicators and insights spanning threat categories you need to secure your business. This connector facilitates automated interactions, such as returning the list of public, private, and shared collection resources to which the user has access, returning general information for a specific object of a specific collection, etc. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**6 operation(s)** (+1 hidden):

_investigation_
- `get_api_root_information()` — Get API Root Information
- `get_collections([collectionID: text])` — Get Collections
- `get_manifest_by_collection_id(collectionID: text, [added_after: datetime])` — Get Manifest By Collection ID
- `get_objects_by_collection_id(collectionID: text, [added_after: datetime], [output_mode: select], offset: text, [limit: text])` — Get Objects By Collection ID
- `get_objects_by_object_id(collectionID: text, objectID: text)` — Get Object By Object ID


### `apivoid` v2.0.0 _(installed)_
_APIVoid_

Apivoid connector provides several threat intelligence services ranging from IP/URL/Domain reputation to domain age and website screenshots

**12 operation(s)**:

_investigation_
- `dnspropagation(req_value: text, dns_record_type: select)` — Get DNS Propagation
- `domainage(req_value: text)` — Get Domain Age
- `domainbl(req_value: text)` — Get Domain Reputation
- `emailverify(req_value: text)` — Get Email Reputation
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `iprep(req_value: text)` — Get IP Reputation
- `parkeddomain(req_value: text)` — Get Domain Parked Status
- `screenshot(req_value: text)` — Get URL Screenshot
- `sitetrust(req_value: text)` — Get Domain Trustworthiness
- `sslinfo(req_value: text)` — Get SSL Info
- `urlrep(req_value: text)` — Get URL Reputation
- `urlstatus(req_value: text)` — Get URL Status


### `arcanna-ai` v1.2.0 _(installed)_
_Arcanna.ai_

Arcanna.ai is a platform for delivering decision intelligence. It augments Security Operation Center analysts in dealing with incoming threats by increasing analyst efficiency in decision-making. More information is available at https://arcanna.ai

**10 operation(s)**:

_investigation_
- `export_event(jobId: text, eventId: text)` — Get Event
- `get_arcanna_response(jobId: text, eventId: text, retryCount: integer, waitTime: integer)` — Get Decision on Event
- `get_decision_set(jobId: text)` — Get Job Decision Set
- `send_feedback(jobId: text, eventId: text, feedback: select, [user: text])` — Send Feedback
- `send_to_arcanna(jobId: text, body: json, [caseId: text])` — Send Event

_utilities_
- `get_job_by_name(jobName: text)` — Get Job By Name
- `get_jobs()` — Get Jobs
- `start_job(jobId: text, [username: text])` — Start Job
- `stop_job(jobId: text, [username: text])` — Stop Job
- `trigger_training(jobId: text, [username: text])` — Trigger Job Training


### `aws-feed` v1.0.0 _(installed, ingestion)_
_AWS Feed_

Amazon Web Services (AWS) publishes its current IP address ranges in JSON format. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators([last_pull_time: datetime])` — Get Indicators


### `bambenek-feed` v1.0.0 _(installed, ingestion)_
_Bambenek Feed_

Bambenek Consulting is an IT consulting firm focused on cybersecurity and cybercrime. This connector facilitates automated operations related to fetching the list of IP addresses/domains of feed families and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `fetch_indicators(high_confidence: checkbox, [output_mode: select], [create_pb_params: json])` — Fetch Indicators


### `barracuda-reputation-block-list` v1.0.0 _(installed)_
_Barracuda Reputation Block List_

Barracuda Reputation System is a real-time database of IP addresses that have a poor reputation for sending valid emails. Barracuda Central maintains and manually verifies all IP addresses marked as "poor" on the Barracuda Reputation System.

**1 operation(s)**:

_investigation_
- `get_ip_reputation(iplookup: text)` — Get IP Reputation


### `binaryedge` v1.0.0 _(installed)_
_BinaryEdge_

Binaryedge helps to automatically scan the entire public internet, create real-time threat intelligence feeds or security reports that show the exposure of what is connected to the internet.

**5 operation(s)**:

_investigation_
- `get_dns_details(domain: text)` — Get DNS Details
- `get_host_details(ip_address: text)` — Get Host Details
- `get_ip_risk_score_details(ip_address: text)` — Get IP Risk Score Details
- `get_list_of_affect_cve_details(ip_address: text)` — Get CVEs List
- `get_subdomain_details(domain: text)` — Get Subdomain Details


### `blocklist_de-feed` v1.0.0 _(installed, ingestion)_
_Blocklist.de Feed_

Blocklist.de is a free and voluntary service provided by a Fraud/Abuse-specialist, whose servers are often attacked via SSH-, Mail-Login-, FTP-, Webserver- and other services. This connector facilitates automated operations related to fetching the list of blocklisted IP addresses of services and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

_investigation_
- `fetch_indicators([time: datetime], [service: select], [output_mode: select])` — Fetch Indicators
- `get_ips_by_service(service: select, [output_mode: select])` — Fetch All Blocklist IPs


### `botvrij-misp-osint-feed` v1.0.0 _(installed, ingestion)_
_Botvrij.eu MISP OSINT Feed_

Botvrij.eu MISP OSINT Feed Integration.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

_investigation_
- `get_collections([modified_after: datetime])` — Get Collections
- `get_objects_by_collection_id(collectionID: text, [modified_after: datetime])` — Get Objects By Collection ID


### `brute-force-blocker-feed` v1.0.0 _(installed, ingestion)_
_BruteForceBlocker Feed_

BruteForceBlocker Feed it's main purpose is to block SSH bruteforce attacks via firewall.This connector facilitates automated operations related to fetching the list of IPs blocklist.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `fetch_indicators([last_pull_time: text])` — Fetch Indicators


### `censys` v2.0.0 _(installed)_
_Censys_

Censys is a search engine that focuses on providing comprehensive information about devices and systems connected to the Internet. It is specifically designed to help researchers, security professionals, and organizations gain insights into various aspects of the global Internet infrastructure. Censys employs a variety of techniques to continuously scan and analyze the Internet, collecting data on IP addresses, websites, certificates, open ports, and other network-related information. This extensive dataset allows users to search for specific devices, services, or vulnerabilities, helping them understand the security posture of different entities on the Internet.

**3 operation(s)**:

_investigation_
- `get_host_details(ip: text, [at_time: datetime])` — Get Host Details Using IP Address
- `lookup_certificate(fingerprint: text)` — Lookup Certificate
- `search_hosts(q: text, [per_page: text], [virtual_hosts: select], [cursor: text], [fields: text])` — Search Hosts


### `check-phish` v1.0.0 _(installed)_
_Check Phish_

Check Phish is free scanner to detect phishing & fraudulent sites in real-time. This connector facilitates automated interactions, such as retrieving information for the specific URL from Check Phish.

**1 operation(s)**:

_investigation_
- `get_url_info(url: text, scanType: select, insights: checkbox)` — Get URL Information


### `cins-army-feed` v1.0.0 _(installed, ingestion)_
_CINS Army Feed_

CINS Army List is a subset of the CINS Active Threat Intelligence ruleset provided to our Sentinel IPS customers, and consists of IP addresses. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators([output_mode: select])` — Get Indicators


### `cisco-talos-feed` v1.0.0 _(installed, ingestion)_
_Cisco Talos Feed_

Cisco Talos Reputation Center provides access to expansive threat data and related information. This connector facilitates automated operations related to fetching the list of blacklisted IP addresses and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `fetch_indicators([output_mode: select])` — Fetch Indicators


### `cisco-talos-threat-intelligence` v1.0.0 _(installed)_
_Cisco Talos Threat Intelligence_

Talos Threat Intelligence connector enables seamless integration with Cisco Talos Threat Intelligence using CIsco SecureX APIs to retrieve reputation data for IPs, domains, URLs, and file hashes. This helps security teams automate threat intelligence gathering and enhance incident response workflows.

**4 operation(s)**:

_investigation_
- `get_domain_reputation(domain: text)` — Get Domain Reputation
- `get_file_hash_reputation(file_hash: text)` — Get File Hash Reputation
- `get_ip_reputation(ip_address: text)` — Get IP Reputation
- `get_url_reputation(url: text)` — Get URL Reputation


### `cloudflare` v1.0.0 _(installed)_
_Cloudflare_

Cloudflare helps to automatically scan the entire public internet,  including DDoS protection, web application firewall, bot management, encryption, DNS security, access control, and rate limiting, to safeguard websites and online applications from various cyber threats.

**5 operation(s)**:

_containment_
- `block_ip(ruleset_id: text, ip_address: text, description: text)` — Block IP

_investigation_
- `get_firewall_rule_set()` — Get Firewall Rule Sets
- `get_firewall_rules()` — Get Firewall Rules
- `get_rule_id_by_rule_name(ruleset_name: text)` — Get Rule ID By Rule Name

_remediation_
- `unblock_ip(ip_address: text)` — Unblock IP


### `cofense-triage` v2.0.0 _(installed)_
_Cofense Triage_

Cofense Triage is a phishing response workbench that allows analysts to automate and respond to phishing threats.

**13 operation(s)**:

_investigation_
- `download_attachment(id: text)` — Download Attachment
- `download_report(id: text)` — Download Report
- `get_attachment_details(attachment_id: text)` — Get Attachment Details
- `get_cluster_details(cluster_id: text)` — Get Cluster Details
- `get_clusters([match_priority: integer], [created_at: datetime], [updated_at: datetime], [page_number: integer], [page_size: integer], [sort_by: text], [filter_by: json], [fields_to_retrieve: text], [total_reports_count: integer], [tags: text])` — Get Clusters
- `get_domain_details(domain_id: text)` — Get Domain Details
- `get_hostname_details(hostname_id: text)` — Get Hostname Details
- `get_inbox_reports([match_priority: integer], [created_at: datetime], [updated_at: datetime], [page_number: integer], [page_size: integer], [sort_by: text], [filter_by: json], [fields_to_retrieve: text], [tags: text], [categorization_tags: text])` — Get Inbox Reports
- `get_report_details(report_id: text)` — Get Report Details
- `get_report_reporters_details([created_at: datetime], [updated_at: datetime], [page_number: integer], [page_size: integer], [sort_by: text], [filter_by: json], [fields_to_retrieve: text], [vip: checkbox], [reputation_score: integer], [email: text])` — Get Report Reporters Details
- `get_reports([match_priority: integer], [created_at: datetime], [updated_at: datetime], [page_number: integer], [page_size: integer], [sort_by: text], [filter_by: json], [fields_to_retrieve: text], [report_location: text], [tags: text], [categorization_tags: text])` — Get Reports
- `get_triage_threat_indicators([threat_type: select], [threat_level: select], [threat_value: text], [threat_source: text], [created_at: datetime], [updated_at: datetime], [sort_by: text], [filter_by: json], [fields_to_retrieve: text], [page_number: integer], [page_size: integer])` — Get Triage Threat Indicators

_query_
- `get_url_details(endpoint: text, [method: select], [body: json])` — Get URL Details


### `criminal-ip` v1.0.0 _(installed)_
_Criminal IP_

Criminal IP provides cyber threat intelligence search engine through which you can scan IP, domain, urls.

**3 operation(s)**:

_investigation_
- `get_domain_reputation(query: text)` — Get Domain Reputation
- `get_ip_reputation(query: text)` — Get IP Reputation
- `get_url_reputation(query: text)` — Get URL Reputation


### `crowdsec-cyber-threat-intelligence` v1.0.0 _(installed)_
_CrowdSec Cyber Threat Intelligence_

CrowdSec Cyber Threat Intelligence & Service APIs provide a unified, real-time threat intelligence and automation platform that enables organizations to detect, enrich, and respond to cyber threats at scale.

**26 operation(s)**:

_containment_
- `add_ips_to_blocklist(blocklist_id: text, ips: textarea, expiration: text)` — Add IPs to Blocklist
- `bulk_overwrite_blocklist_ips(blocklist_id: text, ips: textarea, expiration: text)` — Bulk Overwrite Blocklist IPs
- `create_blocklist(name: text, [description: textarea])` — Create New Blocklist
- `delete_blocklist(blocklist_id: text)` — Delete Blocklist
- `delete_ips_from_blocklist(blocklist_id: text, ips: textarea)` — Delete IPs from Blocklist
- `update_blocklist(blocklist_id: text, label: text, description: textarea, references: textarea, tags: text, from_cti_query: text, since: text)` — Update Blocklist

_investigation_
- `batch_get_ip_reputation(ips: textarea)` — Batch Get IP Reputation
- `get_allowlist_items(allowlist_id: text)` — Get Items in Allowlist
- `get_blocklist(blocklist_id: text)` — Get Specific Blocklist
- `get_blocklist_ips(blocklist_id: text)` — Get Blocklist IPs
- `get_integration(integration_id: text)` — Get Integration
- `get_ip_reputation(ip_address: text)` — Get IP Reputation
- `get_malevolent_ips([page: integer], [limit: integer], [since: text])` — Get Fire IPs
- `get_specific_allowlist_item(allowlist_id: text, item_id: text)` — Get Specific Allowlist Item
- `list_allowlists()` — List All Allowlists
- `list_blocklists()` — List All Blocklists
- `list_integrations()` — List Integrations
- `search_ip_reputation(query: text, [since: text], [page: integer], [limit: integer])` — Search IP Reputation

_remediation_
- `add_items_to_allowlist(allowlist_id: text, items: textarea, [description: text], [expiration: text])` — Add IPs to Allowlist
- `create_allowlist(name: text, [description: textarea])` — Create New Allowlist
- `create_integration(name: text, [description: textarea], entity_type: text, output_format: text)` — Create Integration
- `delete_allowlist(allowlist_id: text, [force: text])` — Delete Allowlist
- `delete_allowlist_item(allowlist_id: text, item_id: text)` — Delete Item from Allowlist
- `delete_integration(integration_id: text)` — Delete Integration
- `update_allowlist(allowlist_id: text, [name: text], [description: text])` — Update Allowlist
- `update_integration(integration_id: text, [name: text], [description: textarea], [output_format: text], [regenerate_credentials: text])` — Update Integration


### `crowdstrike-falcon-intelligence` v1.1.0 _(installed)_
_CrowdStrike Falcon Intelligence_

CrowdStrike Falcon Intelligence service helps organizations by delivering relevant, timely and actionable threat intelligence to defend from bad actors. This connector which facilitates automated way to fetch IP reputation, domain reputation, file reputation, CrowdStrike actors, CrowdStrike indicators and CrowdStrike reports.

**7 operation(s)**:

_investigation_
- `get_cs_actors([filter: text], [q: text], [fields: text], [sort: text], [limit: integer], [offset: integer])` — Get CS Actors
- `get_cs_indicators([filter: text], [q: text], [sort: text], [limit: integer], [offset: integer], [include_deleted: checkbox])` — Get CS Indicators
- `get_cs_reports([filter: text], [q: text], [fields: text], [sort: text], [limit: integer], [offset: integer])` — Get CS Reports
- `get_domain_reputation(domain: text)` — Get Domain Reputation
- `get_file_reputation(file: text)` — Get File Reputation
- `get_ip_reputation(ip: text)` — Get IP Reputation
- `get_url_reputation(url: text)` — Get URL Reputation


### `crowdstrike-intel-indicators` v1.0.1 _(installed, ingestion)_
_CrowdStrike Intel Indicators_

CrowdStrike Intel Indicator retrieve Indicators data. This connector facilitates automated operations related to fetching the list indicators and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

_investigation_
- `download_indicators([published_date: datetime])` — Download Indicators
- `fetch_indicators([filter: text], [q: text], [offset: integer], [limit: integer], [sort: checkbox], [include_deleted: checkbox], [include_relations: checkbox], [output_mode: select])` — Fetch Indicators


### `ctm360-cyberblindspot` v1.0.0 _(installed)_
_CTM360 CyberBlindspot_

CyberBlindspot is CTM360's Digital Risk Protection platform which combines surface, deep, and dark web monitoring, including brand protection, anti-phishing, and takedowns. This connector allows you to ingest the details from the platform and take response actions.

**8 operation(s)**:

_investigation_
- `add_comment(ticket_id: text, comment: text)` — Add Comment
- `get_breached_credentials(date_from: text, date_to: text, [size: integer])` — Get Breached Credentials
- `get_card_leaks(date_from: text, date_to: text, [size: integer])` — Get Card Leaks
- `get_domain_protection(date_from: text, date_to: text, type: text, [risk_score_min: integer], [risk_score_max: integer], [finding_status: text], [size: integer])` — Get Domain Protection
- `get_malware_logs(date_from: text, date_to: text, [size: integer])` — Get Malware Logs
- `request_takedown(ticket_id: text)` — Request Takedown

- `close_incident(ticket_id: text)` — Close Incident
- `get_incidents([date_field: select], [date_from: text], [date_to: text])` — Get Incidents


### `ctm360-cyna` v1.0.0 _(installed)_
_CTM360 CYNA_

This connector allows FortiSOAR to pull cyber news from the CTM360 platform to keep security teams informed of the latest threat intelligence.

**1 operation(s)**:

- `get_cyber_news([search_after: text], [fields: text], [start_date: datetime], [end_date: datetime], [size: integer], [search_after: text])` — Get Cyber News


### `ctm360-hackerview` v1.0.0 _(installed)_
_CTM360 HackerView_

HackerView is CTM360’s External Attack Surface Management platform, offering automated asset discovery, issue identification, security ratings, and third-party risk management. This collector lets you pull the issues and assets found on attack surface.

**5 operation(s)**:

- `get_domains()` — Get Domains
- `get_hosts()` — Get Hosts
- `get_ip_addresses()` — Get IP Addresses
- `get_issues(first_seen: text)` — Get Issues
- `get_resolved_issues([from_date: text], [to_date: text])` — Get Resolved Issues


### `cybereason-threat-intel` v1.0.0 _(installed)_
_Cybereason Threat Intel_

Access the Cybereason global threat intelligence database on file hashes, IP addresses, and domains.

**3 operation(s)**:

_enrichment_
- `domain_batch(keys: text)` — Get Domain Reputation
- `file_batch(keys: text)` — Get File Reputation
- `ip_batch(keys: text)` — Get IP Reputation


### `cyberint` v1.1.0 _(installed)_
_Cyberint_

Cyberint provides Intelligence-Driven Digital Risk Protection.

**11 operation(s)**:

_investigation_
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `fetch_vulnerabilities(technology_name: text, technology_version: text, sort_field: text, sort_order: checkbox, page_size: integer, page_number: integer, [last_updated_from: datetime], [cve_id: text], [cvss_min: integer])` — Fetch Vulnerabilities
- `get_alert_analysis_report(alert_ref_id: text, report_name: text)` — Get Alert Analysis Report
- `get_alert_attachment(alert_ref_id: text, attachment_id: text, attachment_name: text)` — Get Alert Attachment
- `get_alerts([filter: checkbox], [page: integer], [size: integer])` — Get Alerts
- `get_domain_reputation(domain: text)` — Get Domain Reputation
- `get_file_reputation(file_hash: text)` — Get File Reputation
- `get_ip_reputation(ip_address: text)` — Get IP Reputation
- `get_url_reputation(url: text)` — Get URL Reputation
- `get_vulnerability_details_by_cve_id(cve_id: text)` — Get Vulnerability Details by CVE ID
- `update_alerts_status(alert_ref_ids: text, status: select)` — Update Alerts Status


### `cybersixgill` v1.0.0 _(installed, ingestion)_
_Cybersixgill_

Cybersixgill captures, processes and alerts teams to emerging threats, TTPs, IOCs and their exposure to risk as it surfaces on the clear, deep and dark web. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**2 operation(s)**:

_investigation_
- `get_dark_feed(channel_id: text, [limit: text])` — Get Dark Feed
- `get_ioc_dark_feed(channel_id: text, [limit: text], [ack_iocs: checkbox], [fetch_all_records: checkbox])` — Get IOC Dark Feed


### `cyble-vision` v2.0.0 _(installed, ingestion)_
_Cyble Vision_

Cyble Threat Intel that enables users to access and enrich Indicators of Compromise (IOCs) from Cyble's TAXII Feed service within their environment.

**8 operation(s)**:

_investigation_
- `fetch_alerts(companyID: text, [begin: datetime], [end: datetime], [severity: multiselect], [status: multiselect], [service: select], [sortBy: select], [limit: integer])` — Fetch Alerts
- `fetch_companies()` — Fetch All Users for a Company
- `fetch_cve_details(cve: text)` — Fetch CVE Details
- `fetch_indicators([ioc: text], [type: select], [begin: datetime], [end: datetime], [order: select], [sortBy: select], [limit: integer])` — Fetch Indicators
- `fetch_ip_details(companyId: text, addressIP: text)` — Fetch IP Details
- `get_advisory_details(advisoryID: text)` — Get Advisory Details
- `list_advisories([from: datetime], [to: datetime], [sortBy: text], [order: select], [limit: integer], [page: integer], [customTags: text], [countries: text], [vulnerabilities: text])` — List Advisories

_utilities_
- `add_comment_to_alert(alertID: text, [comment: text])` — Add Comment to Alert


### `cyren` v1.0.0 _(installed)_
_Cyren_

Cyren is leading a revolution in internet security by utilizing extensive cloud intelligence to provide the fastest protection available. This connector sends the URL Submitted by the End User to Cyren for web threats like phishing and malware.

**1 operation(s)**:

_investigation_
- `get_url_lookup(input_type: select, value: text)` — Get URL Lookup


### `cyware-ctix` v2.0.0 _(installed)_
_Cyware CTIX_

Allows user to search for URL, Domain and IP,Hash and CVE ID, chooses the matching element, and displays relevant details.

**33 operation(s)**:

_containment_
- `delete_allowed_indicator(indicator_id: text)` — Delete Allowed Indicator

_investigation_
- `add_note_to_threat_data_object(object_id: text, text: text, type: text, [meta_data: object], is_json: checkbox)` — Add Note to Threat Data Object
- `bulk_add_relation(object_ids: text, object_type: text, data: object)` — Bulk Add Relation
- `bulk_deprecate_undeprecate_objects(object_ids: text, object_type: text, action_type: select)` — Bulk Deprecate/Undeprecate Objects
- `bulk_ioc_lookup_advanced(object_type: text, value: text, [objectID: text], [enrichment_data: checkbox], [relation_data: checkbox], [enrichment_tools: text], [fields: text])` — Bulk IOC Lookup (Advanced)
- `bulk_ioc_lookup_and_create_intel(ioc_values: text, [source: text], [collection: text], [metadata: object], [create: checkbox], [enrichment: checkbox])` — Bulk IOC Lookup and Create Intel
- `bulk_lookup_and_create(ioc_values: text, [create: checkbox], [enrichment: checkbox], [metadata: json], [source: text], [collection: text])` — Bulk Lookup and Create (Deprecated)
- `create_intel_via_open_api(title: text, allSDOS: object, [source: text], [collection: text], [metadata: object])` — Create Intel via Open API
- `create_threat_bulletin(title: text, [description: text], status: text, [tlp: text], [server_collections: object], [tags: object], [attachments: object])` — Create Threat Bulletin
- `enrichment_tools(action_name: text, [component: text], [full_list: checkbox])` — Get Enrichment Tool List
- `get_enriched_threat_data(app_slug: text, value: text, action_slug: text, objectID: text, object_type: text)` — Get Enriched Threat Data
- `get_enrichment_object_details(object_type: text, objectID: text, toolID: text)` — Get Enrichment Object Details
- `get_supported_allowed_indicator_types_list([q: text])` — Get Supported Allowed Indicator Types List
- `list_allowed_indicators([type: text], [page: integer], [page_size: integer], [created_by_id: text], [modified_by_id: text], [created_from: text], [created_to: text], [last_active_from: text], [last_active_to: text], [sort: text])` — List Allowed Indicators
- `list_relations_of_threat_data_object(objectID: text, objectType: text, [sources: text], [page: integer], [page_size: integer])` — Get Relations List of Threat Data Object
- `list_rules([page: integer], [pageSize: integer], [source: text], [createdByID: text], [status: text], [lastActiveTo: datetime], [lastActiveFrom: datetime], [createdFrom: datetime], [createdTo: text], [isManualRun: checkbox])` — List Rules
- `list_threat_data(query: text, [page: integer], [page_size: integer], [page_limit: integer], [enrichment: checkbox], [sort: text])` — Get Threat Data
- `list_threat_data_object_details(object_type: text, objectID: text)` — Get Threat Data Object Details List
- `run_rule(rule: text, startTime: text, endTime: text)` — Run Rule
- `search_cve_id(cve_id: text, [page_size: integer])` — Search CVE ID
- `search_domain(domain: text, [page_size: integer])` — Search Domain
- `search_hash(hash: text, [page_size: integer])` — Search Hash
- `search_ip(ip: text, [page_size: integer])` — Search IP
- `search_url(url: text, [page_size: integer])` — Search URL
- `threat_data_object_advanced_details(object_type: text, object_id: text)` — Get Threat Data Object Additional Details
- `update_threat_bulletin(threat_bulletin_id: text, title: text, [description: text], status: text, [server_collections: object], [tags: object])` — Update Threat Bulletin

_remediation_
- `bulk_mark_unmark_false_positive(object_ids: text, object_type: text, action_type: select)` — Bulk Mark/Unmark False Positive
- `run_report(report_id: text, type: text, start_time: text, end_time: text, [file_types: text], [internal_recipients: object], [external_recipients: object])` — Run Report

_utilities_
- `create_custom_attribute(name: text, [description: text], type: select, [choices: text], [is_actionable: checkbox], [status: integer], [sdo_objects: text])` — Create Custom Attribute
- `create_report(name: text, [type: text], [basic_report_type: text], shared_type: select, saved_search: object, schedule: object, file_types: text, columns: object, [internal_recipients: object], [query_key: text], [external_recipients: object])` — Create Report
- `create_tag(name: text, colour_code: select)` — Create Tag
- `delete_tag(tag_id: text)` — Delete Tag

- `list_reports([type: text], [page: integer], [page_size: integer], [repeat_type: text], [shared_type: text], [created_by: text], [modified_by: text], [created_to: text], [created_from: text], [modified_from: text], [modified_to: text], [date_last_run_from: text], [date_last_run_to: text])` — List Reports


### `digital-shadows-searchlight` v1.0.0 _(installed, ingestion)_
_Digital Shadows SearchLight_

Digital Shadows SearchLight monitors and manages an organization's digital risk across the widest range of data sources within the open, deep, and dark web.

**14 operation(s)**:

_investigation_
- `add_asset_labels(id: text, labels: text)` — Add Asset Labels
- `get_alert(id: text)` — Get Alert Details
- `get_asset(id: text)` — Get Asset Details
- `get_exposed_credential_alert(id: text)` — Get Exposed Credential Alert Details
- `get_incident(id: text)` — Get Incident Details
- `get_triage_item(id: text)` — Get Triage Item Details
- `list_alerts([ids: text], [offset: integer], [limit: integer])` — Get Alert List
- `list_assets([ids: text], [labels: text], [offset: integer], [limit: integer])` — Get Asset List
- `list_exposed_credential_alerts([ids: text], [emails: text], [offset: integer], [limit: integer])` — Get Exposed Credential Alert List
- `list_incidents([ids: text], [offset: integer], [limit: integer])` — Get Incident List
- `list_triage_item_events([triage-state: multiselect], [risk-type: multiselect], [risk-type-exclusion: checkbox], [event-created-after: datetime], [event-created-before: datetime], [event-num-after: integer], [fetch_all: checkbox])` — Get Triage Item Event List
- `list_triage_items([ids: text], [portal-shortcodes: text], [offset: integer], [limit: integer])` — Get Triage Item List
- `remove_asset_labels(id: text, labels: text)` — Remove Asset Labels
- `replace_asset_labels(id: text, labels: text)` — Replace Asset Labels


### `dnstwist` v1.0.0 _(installed)_
_DNSTwist_

DNSTwist is a python script used for detecting phishing attacks, typo squatters, and attack domains.

**1 operation(s)**:

_investigation_
- `search(domain: text)` — Search Registered Domains


### `doppel` v1.1.0 _(installed)_
_Doppel_

Doppel is a next-generation AI security company that specializes in protecting organizations from social engineering attacks, impersonation, malicious ads, fake domains, and phishing campaigns.

**4 operation(s)**:

_investigation_
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_alert_details([id: text], [entity: text])` — Get Alert Details
- `get_all_alerts([search_key: text], [queue_state: select], [product: select], [created_after: datetime], [created_before: datetime], [last_activity_timestamp: datetime], [sort_type: select], [sort_order: select], [page: integer], [tags: text])` — Get All Alerts
- `update_alert([id: text], [entity: text], [queue_state: select], [entity_state: select], [comment: text], [tag_action: select], [tag_name: text])` — Update Alert


### `dragos-worldview-threat-intelligence` v1.1.0 _(installed, ingestion)_
_Dragos WorldView Threat Intelligence_

Dragos WorldView industrial threat intelligence provides actionable information and recommendations on threats to operations technology (OT) environments. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**6 operation(s)**:

_investigation_
- `get_all_indicators([value: text], [type: select], [updated_after: datetime], [serial: text], [tags: text], record_number: select)` — Get All Indicators
- `get_all_indicators_in_stix2([value: text], [type: select], [page_size: integer], [page: integer], [updated_after: datetime], [serial: text], [tags: text])` — Get All Indicators In Stix2
- `get_all_reports([sort_by: select], [sort_order: select], [page: integer], [page_size: integer], [updated_after: datetime], [serials: text], [indicator: text])` — Get All Reports
- `get_all_tags([page: integer], [page_size: integer], [tag_type: text])` — Get All Tags
- `get_indicators_of_report(process_response_as: select, report_serial_number: text)` — Get Indicators Of Report
- `get_report_metadata(report_serial_number: text)` — Get Report Metadata


### `eclecticiq` v1.2.0 _(installed)_
_EclecticIQ_

EclecticIQ is a global threat intelligence, hunting and response technology provider. This connector facilitates the automated operations like get IP reputation, get domain reputation, get file reputation etc.

**7 operation(s)**:

_investigation_
- `create_sighting(sighting_title: text, [sighting_description: text], observable_value: text, observable_type: select, observable_maliciousness: select, confidence_value: select, impact_value: select, tags: text)` — Create Sighting
- `get_domain_reputation(observable: text, [is_parsed_response: checkbox])` — Get Domain Reputation
- `get_email_reputation(observable: text, [is_parsed_response: checkbox])` — Get Email Reputation
- `get_file_reputation(observable: text, [is_parsed_response: checkbox])` — Get Filename or Hash Reputation
- `get_ip_reputation(observable: text, [is_parsed_response: checkbox])` — Get IP Reputation
- `get_uri_reputation(observable: text, [is_parsed_response: checkbox])` — Get URL Reputation
- `query_entities([query: text], [entity_value: text], entity_type: select, [size: integer], [from: integer])` — Query Entities


### `focsec` v1.0.0 _(installed)_
_Focsec_

Focsec help to real-time threat intelligence API, powered by proprietary Artificial Intelligence algorithms,for detecting VPNs,Proxys,Bots, and TOR requests,enabling prompt identification of suspicious logins,fraud, and abuse.

**1 operation(s)**:

_investigation_
- `get_ip_details(ip_address: text)` — Get IP Details


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

_investigation_
- `url_review(sample_url: text)` — Check Category of Domain or URL


### `google-cloud-platform-whitelist-feed` v1.0.0 _(installed, ingestion)_
_Google Cloud Platform Whitelist Feed_

Google Cloud Platform publishes its current IP address ranges in JSON format. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `ip_ranges(file_value: multiselect)` — Get IP Ranges


### `google-dorking` v1.0.0 _(installed)_
_Google Dorking_

Google Dorking refers to the practice of using advanced search operators in Google's search engine to discover information that may not be readily accessible through conventional search queries.

**1 operation(s)**:

_investigation_
- `custom_search(cx: text, q: text, [exactTerms: text], [excludeTerms: text], [safe: checkbox], [num: integer], [start: integer], [additional_fields: json])` — Custom Search


### `google-threat-intelligence` v1.0.0 _(installed)_
_Google Threat Intelligence_

Google Threat Intelligence is a cloud-based threat intelligence service provided by Google (via Google Cloud) that helps organizations gain visibility into threat actors, attacks, and indicators of compromise (IOCs). This connector facilitates the automated operations related to analyze retro hunts, search intelligence, livehunt notifications, livehunt rulesets, and download files from Google Threat Intelligence.

**34 operation(s)** (+4 hidden):

_investigation_
- `abort_retrohunt_job(id: text)` — Abort Retrohunt Job
- `analysis_file([type: select], analysis_id: text)` — Get File Or URL Analysis Report
- `create_livehunt_ruleset(name: text, rules: text, [enabled: checkbox], [limit: integer], [notification_emails: text])` — Create Livehunt Ruleset
- `create_retrohunt_job(rules: text, [notification_emails: text], [corpus: select], [start_time: datetime], [end_time: datetime])` — Create Retrohunt Job
- `create_zip_file(hashes: text, [password: password])` — Create ZIP File
- `delete_livehunt_ruleset(id: text)` — Delete Livehunt Ruleset
- `delete_retrohunt_job(id: text)` — Delete Retrohunt Job
- `download_file(id: text)` — Download File
- `download_zip_file(id: text)` — Download ZIP File
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_domain_reputation(domain: text, [relationships: multiselect])` — Get Domain Reputation
- `get_entities_details(id: text)` — Get Entities Details
- `get_entities_list([collection_type: select], [creation_date: datetime], [origin: select], [limit: integer], [cursor: text])` — Get Entities List
- `get_file_reputation(file_hash: text, [relationships: multiselect])` — Get File Reputation
- `get_ip_reputation(ip: text, [relationships: multiselect])` — Get IP Reputation
- `get_livehunt_ruleset_details(id: text)` — Get Livehunt Ruleset Details
- `get_livehunt_rulesets_list([filter: text], [order: text], [limit: integer], [cursor: text])` — Get Livehunt Rulesets List
- `get_mitre_tactics_and_techniques(id: text)` — Get Mitre Tactics and Techniques
- `get_pcap_file_behaviour(sandbox_id: text)` — Get PCAP File Behaviour
- `get_retrohunt_job_details(id: text)` — Get Retrohunt Job Details
- `get_retrohunt_job_matching_files(id: text, [limit: integer], [cursor: text])` — Get Retrohunt Job Matching Files
- `get_retrohunt_jobs_list([filter: text], [limit: integer], [cursor: text])` — Get Retrohunt Jobs List
- `get_url_reputation(url: text, [relationships: multiselect])` — Get URL Reputation
- `get_widget_rendering_url(query: text, [theme: select], [fg1: text], [fg2: text], [fg3: text], [bg1: text], [bg2: text], [bg3: text], [acc: text])` — Get Widget Rendering URL
- `get_zip_file_status(id: text)` — Get ZIP File Status
- `get_zip_file_url(id: text)` — Get ZIP File URL
- `scan_url(url: text)` — Submit URL for Scanning
- `search_intelligence(query: text, [order: text], [limit: integer], [descriptors_only: checkbox], [cursor: text])` — Search Intelligence
- `submit_sample(input: select, value: text)` — Submit File
- `update_livehunt_ruleset(id: text, name: text, rules: text, [enabled: checkbox], [limit: integer], [notification_emails: text])` — Update Livehunt Ruleset


### `google-vision-ai` v1.0.0 _(installed)_
_Google Vision AI_

Google Vision AI allows you to Integrates Google Vision features, including image labeling, face, logo, and landmark detection, optical character recognition (OCR), and detection of explicit content, into applications. This connector facilitates the automated operations related to detect images, and operations.

**3 operation(s)**:

_investigation_
- `get_locations_operations(location_id: text, operation_id: text)` — Get Locations Operations
- `get_operations(operation_id: text)` — Get Operations
- `submit_images(value: text, type: select, maxResults: integer)` — Submit Images


### `greensnow-feed` v1.0.0 _(installed, ingestion)_
_GreenSnow Feed_

GreenSnow is a team consisting of the best specialists in computer security, we harvest a large number of IPs from different computers located around the world. This connector facilitates automated operations such as indicators.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators()` — Get Indicators


### `group-ib-threat-intelligence-attribution-feed` v1.2.0 _(installed)_
_Group IB Threat Intelligence & Attribution Feed_

Use Group-IB Threat Intelligence & Attribution Feed integration to fetch IOCs from various Group-IB collections.

**2 operation(s)**:

_investigation_
- `get_indicators(collection: select, [id: text], [limit: select])` — Get Indicators
- `search_indicator(q: text, [limit: integer])` — Search Indicator


### `have-i-been-pwned` v2.1.0 _(installed)_
_Have I Been Pwned_

Have I Been Pwned connector to get data breaches information,get data classes,lookup email, lookup domain, lookup for pwned password an dsearch for passwords

**13 operation(s)**:

_investigation_
- `check_pwned_password(password: password)` — Lookup for Pwned Password
- `check_pwned_passwords_by_range(hash: text)` — Search for Passwords
- `execute_api_request(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `get_a_single_breached_site_by_name([breachName: text])` — Get Breached Site by Name
- `get_all_breached_email_addresses_for_a_domain(domainName: text)` — Get Breached Email Address List
- `get_all_breached_sites()` — Get Breached Sites List
- `get_all_breaches_for_an_account(accountEmail: text)` — Get Breaches List
- `get_all_subscribed_domains()` — Get Subscribed Domains List
- `get_data_classes()` — Get Data Classes
- `get_pastes(email: email)` — Get Pastes
- `get_the_most_recently_added_breach()` — Get Most Recent Breach
- `lookup_domain(domain: text)` — Lookup Domain
- `lookup_email(email: email, [domain: text], [truncateResponse: checkbox], [includeUnverified: checkbox])` — Lookup Email


### `host_io` v1.0.0 _(installed)_
_host.io_

host.io helps to get comprehensive domain name data, uncover new domains and the relationships between them, get DNS details, scraped website content, outbound links, backlinks, and other hosting details for any domain. This connector facilitates automated operation related to various domains.

**5 operation(s)**:

_investigation_
- `get_all_domains(field: text, value: text, [limit: integer], [page: integer])` — Get All Domains
- `get_dns_domain_details(dns_domain: text)` — Get DNS Domain Details
- `get_full_domains_data(domain_name: text)` — Get Full Domains Data
- `get_related_domains(domain_name: text)` — Get Related Domains
- `get_web_domain_details(web_domain: text)` — Get Web Domain Details


### `ibm-xforce-threat-intel-feed` v2.1.0 _(installed, ingestion)_
_IBM X-Force Threat Intelligence Feed_

IBM X-Force Threat Intelligence Feed is a preconfigured set of intelligence feeds that STAXX users can access immediately upon download, and which offers indicators and insights spanning threat categories you need to secure your business. This connector facilitates automated interactions, such as returning the list of public, private, and shared collection resources to which the user has access, returning general information for a specific object of a specific collection, etc. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**7 operation(s)** (+1 hidden):

_investigation_
- `download_indicators([added_after: datetime])` — Download Indicators
- `get_api_root_information()` — Get API Root Information
- `get_collections([collectionID: text])` — Get Collections
- `get_manifest_by_collection_id(collectionID: text, [added_after: datetime], [added_before: datetime])` — Get Manifest By Collection ID
- `get_objects_by_collection_id(collectionID: text, [added_after: datetime], [added_before: datetime], [output_mode: select])` — Get Objects By Collection ID
- `get_objects_by_object_id(collectionID: text, objectID: text)` — Get Object By Object ID


### `intel471` v1.0.0 _(installed)_
_Intel471_

Connector to perform various Intel471 CTI operations.

**10 operation(s)**:

_investigation_
- `fetch_iocs([from: datetime], [until: datetime], [days: select], [sort: select])` — Get IOCs
- `global_search(global_search: text, [from: datetime], [until: datetime], [days: select], [sort: select], interested: multiselect)` — Global Search
- `search_email(email: email, [from: datetime], [until: datetime], [days: select], [sort: select], interested: multiselect)` — Get Email Reputation
- `search_ip_address(ip_address: text, [from: datetime], [until: datetime], [days: select], [sort: select], interested: multiselect)` — Get IP Reputation
- `search_report([from: datetime], [until: datetime], [days: select], [sort: select])` — Get Reports
- `search_url(url: text, [from: datetime], [until: datetime], [days: select], [sort: select], interested: multiselect)` — Get URL Reputation

- `search_actor(actor_name: text, [from: datetime], [until: datetime], [days: select], [sort: select])` — Search for Actor
- `search_actors_on_forum(actor_name: text, forum_name: text, [from: datetime], [until: datetime], [days: select], [sort: select], interested: multiselect)` — Search for Actor with Forum
- `search_report_by_tag(tag: text, [from: datetime], [until: datetime], [days: select], [sort: select])` — Search Report by Tag
- `search_report_by_uid(uid: text, sort: select)` — Get Report using UID


### `ip-api` v1.0.0 _(installed)_
_IP-API_

IP-API helps to get the following information for any IP address: city, region (name & code), country (name & code), continent, postal code / zip code, latitude, longitude, time zone,  utc offset, european union (EU) membership, country calling code, country capital, country tld (top-level domain), currency (name & code), area & population of the country, languages spoken, asn, organization and hostname. This connector facilitates automated operation related to ip-api.

**2 operation(s)**:

_investigation_
- `execute_batch_api(list_of_ip_addr: text)` — Get IP Geolocation
- `execute_dns_api()` — Get DNS Geolocation


### `ip-quality-score` v1.0.1 _(installed)_
_IP Quality Score_

The IPQualityScore (IPQS) Threat Intelligence application provides threat intelligence for IP addresses, email addresses, URLs, and domains. This connector facilitates automated interactions with a IP Quality Score server using FortiSOAR™ playbooks.

**3 operation(s)**:

_investigation_
- `get_email_reputation(email_address: text, [fast: checkbox], [timeout: integer], [suggest_domain: checkbox], [strictness: select], [abuse_strictness: select])` — Get Email Reputation
- `get_ip_reputation(ip_address: text, [strictness: select], [user_agent: text], [user_language: text], [fast: checkbox], [mobile: checkbox], [allow_public_access_points: checkbox], [lighter_penalties: checkbox], [transaction_strictness: select])` — Get IP Reputation
- `get_url_reputation(url: text, [strictness: select], [fast: checkbox])` — Get URL Reputation


### `ipstack` v1.0.1 _(installed)_
_IPStack_

IPStack provides geolocation facility for IP Address or Domain.

**2 operation(s)**:

_investigation_
- `domain_locate(query: text, [fields: text], [enable_hostname: checkbox], [enable_security: checkbox])` — Geolocate Domain
- `ip_locate(query: text, [fields: text], [enable_hostname: checkbox], [enable_security: checkbox])` — Geolocate IP


### `ipsum-threat-intelligence-feed` v1.0.0 _(installed, ingestion)_
_IPsum Threat Intelligence Feed_

IPsum is a threat intelligence feed based on 30+ different publicly available lists of suspicious and/or malicious IP addresses. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators([output_mode: select])` — Get Indicators


### `kaspersky-threat-intel` v1.0.0 _(installed)_
_Kaspersky Threat Intelligence_

Kaspersky Threat Intelligence provides threat intelligence services. This connector facilitates automated operations such as Lookup IP, Lookup URL, Lookup FileHash, and Lookup Domain.

**4 operation(s)**:

_investigation_
- `lookup_IP(ipAdd: text)` — Lookup IP Address

_verification_
- `lookup_Domain(domain: text)` — Lookup Domain
- `lookup_FileHash(fileHash: text)` — Lookup File Hash
- `lookup_URL(url: text)` — Lookup URL


### `majestic-million-feed` v1.0.0 _(installed, ingestion)_
_Majestic Million Feed_

Majestic crawls the web and analyzes the data to create a huge Link Intelligence dataset describing how the world wide web links together. Use the Majestic Million connector to ingest the top known websites as 'good' indicators. This connector facilitates automated operations related to fetching the list indicators and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_domain_records(process_response_as: select)` — Get Domain Records


### `maltiverse` v1.0.0 _(installed)_
_Maltiverse_

Maltiverse Threat Intelligence Feeds can be integrated with your security stack to provide improvement in terms of detections and protection capabilities from different points of view. You can also upload an deploy your own Threat Intelligence!

**4 operation(s)**:

_investigation_
- `get_domain_reputation(domain: text)` — Get Domain Reputation
- `get_file_reputation(filehash_type: select, filehash: text)` — Get File Reputation
- `get_ip_reputation(ip: text)` — Get IP Reputation
- `get_url_reputation(url: text)` — Get URL Reputation


### `malwarebazaar` v1.0.0 _(installed)_
_MalwareBazaar_

MalwareBazaar is a project from abuse.ch with the goal of sharing malware samples with the InfoSec community, AV vendors and threat intelligence providers.

**3 operation(s)**:

_investigation_
- `add_comment_to_malware_sample(sha256_hash: text, comment: text)` — Add a Comment to Malware Sample
- `get_filehash_reputation(hash: text)` — Get File Hash Reputation
- `get_malware_samples(sha256_hash: text)` — Get Malware Samples


### `malwarebazaar-feed` v1.0.0 _(installed, ingestion)_
_MalwareBazaar Feed_

MalwareBazaar is a project from abuse.ch with the goal of sharing malware samples with the InfoSec community, AV vendors and threat intelligence providers. This connector facilitates automated operations such as indicators.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators(selector_type: select)` — Get Indicators


### `mandiant-advantage-threat-intelligence` v1.0.0 _(installed)_
_Mandiant Advantage Threat Intelligence_

Mandiant Advantage Threat Intelligence provides automated access to indicators of compromise (IOCs) IP addresses, domain names, URLs threat actors are using, via the indicators, allows access to full length finished intelligence in the reports, allows for notificaiton of threats to brand and keyword monitoring via the alerts, and finally allows searching for intelligence on the adversary with the search. This connector facilitates automated operations such as indicators, actors, malware, reports, campaigns, and vulnerabilities.

**11 operation(s)**:

_investigation_
- `get_actor_details(id: text)` — Get Threat Actor Details
- `get_actors([limit: integer], [offset: integer])` — Get Threat Actors List
- `get_campaign([start_date: datetime], [end_date: datetime], [limit: integer], [offset: integer])` — Get Campaigns List
- `get_campaign_details(id: text)` — Get Campaign Details
- `get_indicator_details(value: text)` — Get Indicator Details
- `get_indicators(start_epoch: datetime, [end_epoch: datetime], [gte_mscore: integer], [exclude_osint: checkbox], [include_reports: checkbox], [report_limit: integer], [include_campaigns: checkbox], [sort_by: text], [sort_order: select], [limit: integer], [next: text])` — Get Indicators List
- `get_malware([limit: integer], [offset: integer])` — Get Malware Families List
- `get_malware_details(id: text)` — Get Malware Family Details
- `get_report_details(id: text)` — Get Report Details
- `get_reports([start_epoch: datetime], [end_epoch: datetime], [limit: integer], [offset: integer], [next: text])` — Get Reports List
- `get_vulnerability([start_epoch: datetime], [end_epoch: datetime], [rating_types: multiselect], [risk_ratings: multiselect], [sort_by: text], [sort_order: select], [limit: integer], [next: text])` — Get Vulnerabilities List


### `mandiant-feed` v1.0.0 _(installed)_
_Mandiant Feed_

Mandiant Threat Intelligence provides automated access to indicators of compromise (IOCs) — IP addresses, domain names, URLs threat actors are using, via the indicators. <br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators([added_after: datetime], [length: integer], [id: text], [status: select])` — Get Indicators


### `mandiant-threat-intel` v1.2.0 _(installed, ingestion)_
_Mandiant Threat Intelligence_

Mandiant Threat Intelligence provides automated access to indicators of compromise (IOCs) — IP addresses, domain names, URLs threat actors are using, via the indicators, allows access to full length finished intelligence in the reports, allows for notificaton of threats to brand and keyword monitoring via the alerts, and finally allows searching for intelligence on the adversary with the search. This connector facilitates automated operations such as indicators, reports, alerts, and search collections.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**7 operation(s)**:

_investigation_
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `fetch_indicators([added_after: datetime], [length: integer], [id: text], [status: select])` — Fetch Indicators
- `get_alerts([added_after: datetime], [length: integer], [id: text], [alert_type: select], [alert_status: select], [alert_categories: select], [alert_severity: select])` — Get Alerts
- `get_indicators([added_after: datetime], [length: integer], [id: text], [status: select])` — Get Indicators
- `get_reports(added_after: datetime, [length: integer], [report_id: text], [document_id: text], [status: select], [subscription: select], [report_type: multiselect], [actor_name: text], [malware_name: text])` — Get Reports
- `get_reputation_of_indicators(indicatorValue: text)` — Get Indicator Reputation
- `search_collections(queries: json, [include_connected_objects: checkbox], [connected_objects: json], [sort_by: text], [sort_order: text])` — Search Collections


### `maxmind` v1.1.0 _(installed)_
_Maxmind_

Maxmind GeoIP2 offer industry-leading IP intelligence data. Get detailed information about an IP address, such as the geographical location, organization, and other related data, with varying levels of precision.

**5 operation(s)**:

_investigation_
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `ip_all_details(ip: text)` — Get All Details of IP
- `ip_city_details(ip: text)` — Get City Details of IP
- `ip_country_details(ip: text)` — Get Country Details of IP
- `ip_insights_details(ip: text)` — Get Insights Details of IP


### `maxmind-geoip2` v1.0.0 _(installed)_
_MaxMind GeoIP2_

GeoIP2 IP Intelligence provides an extensive breadth of data on IP addresses for content customization, geofencing, user analysis, research, and more. This connector facilitates automated interactions with a MaxMind GeoIP2 server using FortiSOAR™ playbooks.

**3 operation(s)**:

_investigation_
- `get_city(ip_address: text)` — Get City
- `get_country(ip_address: text)` — Get Country
- `get_insights(ip_address: text)` — Get Insights


### `mcafee-mvision-insights` v1.1.0 _(installed)_
_McAfee Mvision Insights_

MVISION Insights APIs provide intelligence about Campaigns, associated IOCs and Events. They also provide classification information on file-hashes. This connector facilitates the automated operations related to Campaigns, Events, or IOCs.

**16 operation(s)**:

_investigation_
- `get_artefacts(hashtype: text, hashvalue: text)` — Get Artefacts
- `get_campaign_details(id: text, [include: select], [fields: select])` — Get Campaign Details
- `get_campaign_galaxies(id: text)` — Get Campaign Galaxies
- `get_campaign_iocs(id: text)` — Get Campaign IOCs
- `get_campaigns_detected([offset: integer], [limit: integer], [filter_by: select], [campaign_name: text], [sector: text], [last_detected_on: text], [include: select], [fields: select])` — Get All Campaigns Detected
- `get_campaigns_list([offset: integer], [limit: integer], [filter_by: select], [campaign_name: text], [sector: text], [include: select], [fields: select])` — Get All Campaigns List
- `get_campaigns_relationship_galaxies(id: text)` — Get Campaign Relationship Galaxies
- `get_campaigns_relationship_iocs(id: text)` — Get Campaign Relationship IOCs
- `get_events_list([offset: integer], [limit: integer], [artefact_type: text], [artefact_value: text], [agent_guid: text], [id: text], [from_date: text], [to_time: text], [fields: select])` — Get All Events List
- `get_galaxies_list([offset: integer], [limit: integer], [category: select], [id: text], [fields: select])` — Get All Galaxies List
- `get_insights_events_list([artefact_type: text], [artefact_value: text], [agent_guid: text], [id: text], [from_date: datetime], [to_date: datetime], [offset: integer], [limit: integer])` — Get Insights Events List
- `get_ioc_campaigns(id: text)` — Get IOC Campaigns
- `get_ioc_details(id: text, [fields: select])` — Get IOC Details
- `get_ioc_list([offset: integer], [limit: integer], [id: text], [type: text], [fields: select])` — Get All IOC List
- `get_ioc_relationship_campaigns(id: text)` — Get IOC Relationship Campaigns
- `get_related_samples(samplemd5: text, sfvecmd5: text, version: integer, [lastseen: integer], [offset: integer], [limit: integer])` — Get Related Samples


### `mcafee-tie` v1.1.0 _(installed)_
_McAfee Threat Intelligence Exchange_

McAfee Threat Intelligence Exchange, Can used to get file reputation,get file references and set file reputation

**3 operation(s)**:

_investigation_
- `get_file_references(hash_type: select, hash: text)` — Get File References
- `get_file_reputation(hash_type: select, hash: text)` — Get File Reputation
- `set_file_reputation(hash_type: select, hash: text, trust_level: select, [file_name: text], [comment: text])` — Set File Reputation


### `microsoft-defender-threat-intelligence` v1.0.0 _(installed)_
_Microsoft Defender Threat Intelligence_

The Microsoft Defender Threat Intelligence FortiSOAR Connector enables automated threat intelligence gathering, enrichment, and response within FortiSOAR

**11 operation(s)**:

_containment_
- `get_host_component(hostComponentId: text)` — Get Host Component
- `get_host_details(hostId: text)` — Get Host Details
- `get_host_reputation(hostId: text)` — Get Host Reputation
- `get_host_ssl_certificate(hostSslCertificateId: text)` — Get Host SSL Certificate
- `get_whoisrecord(type: select)` — Get Whois Record
- `list_components(hostId: text)` — Get Components List
- `list_hostPorts(hostId: text)` — Get Host Ports List
- `list_host_ssl_certificates(hostId: text)` — Get Host SSL Certificates List
- `list_indicators(intelligenceProfileId: text)` — Get Indicators List
- `list_passiveDns(hostId: text)` — Get Passive DNS List
- `list_passiveDns_reverse(hostId: text)` — Get Passive DNS Reverse List


### `microsoft-office-365-feed` v1.0.0 _(installed, ingestion)_
_Microsoft Office 365 Feed_

Ingest the IP, URLs used by Office 365 using the web service provided by Microsoft. The fetched indicators can be used to create a whitelist, blacklist etc. for your SIEM or firewall services.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `fetch_indicator(indicator_type: select, [last_pull_time: datetime], [limit: integer])` — Fetch Indicators


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


### `nsfocus-feed` v1.0.1 _(installed, ingestion)_
_NSFOCUS Threat Intelligence Feed_

NSFOCUS platform can provide accurate and comprehensive threat intelligence data and services in real-time by incorporating intelligence collection, analysis, sharing, and consumption. <br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators(indicator_type: select)` — Get Indicators


### `nsfocus-threat-intel` v1.0.0 _(installed)_
_NSFOCUS Threat Intelligence_

NTI is a threat intelligence analysis and sharing platform launched by NSFOCUS after years of security practices and the accumulation of intelligence data. The platform can provide accurate and comprehensive threat intelligence data and services in real-time by incorporating intelligence collection, analysis, sharing, and consumption.

**8 operation(s)**:

_investigation_
- `get_domain_reputation(urls: text)` — Get Domain or URL Reputation
- `get_domain_security_index(query: text)` — Get Domain or URL Security Index
- `get_domains_details(query: text, [type: select])` — Get Domain or URL Details
- `get_file_details(query: text, [type: select])` — Get File Details
- `get_file_reputation(files: text)` — Get File Reputation
- `get_ip_address_details(query: text, [type: select])` — Get IP Address Details
- `get_ip_reputation(ips: text)` — Get IP Reputation
- `get_ip_security_index(query: text)` — Get IP Security Index


### `opencti` v1.0.2 _(installed)_
_OpenCTI_

OpenCTI is an open threat intelligence platform where you can store, organize, visualize and share knowledge about cyber threats.

**13 operation(s)**:

_investigation_
- `add_indicator_field(indicator_id: text, field: select, field_id: text)` — Add Indicator Field
- `create_external_reference(url: text, name: text)` — Create External Reference
- `create_indicator(type: select, value: text, [x_opencti_create_indicator: checkbox], [description: text], [score: integer], [created_by: text], [marking_id: text], [label_id: text], [external_reference_id: text])` — Create Indicator
- `create_label(name: text)` — Create Label
- `create_organization(name: text, [description: text], [reliability: select])` — Create Organization
- `delete_indicator(indicator_id: text)` — Delete Indicator
- `get_external_references([limit: integer], [end_cursor_id: text])` — Get External References
- `get_indicators([search_value: text], [limit: integer], [end_cursor_id: text], [type: multiselect], [min_score: integer], [max_score: integer])` — Get Indicators
- `get_labels([limit: integer], [end_cursor_id: text])` — Get Labels
- `get_marking_definition([limit: integer], [end_cursor_id: text])` — Get Marking Definition
- `get_organizations([limit: integer], [end_cursor_id: text])` — Get Organizations
- `remove_indicator_field(indicator_id: text, field: select, field_id: text)` — Remove Indicator Field
- `update_indicator_field(indicator_id: text, field: select, field_value: text)` — Update Indicator Field


### `openphish` v1.0.0 _(installed)_
_OpenPhish_

OpenPhish helps to automatically identify zero-day phishing sites and provide comprehensive, actionable, real-time threat intelligence by using proprietary Artificial Intelligence algorithms.

**2 operation(s)**:

_investigation_
- `get_indicators_for_24h_feed()` — Get Indicators For 24 Hr Feed 
- `get_indicators_for_latest_feed()` — Get Indicators For Latest Feed 


### `paloalto-autofocus` v2.0.0 _(installed)_
_PaloAlto AutoFocus_

Palo Alto Networks AutoFocus™ is a threat intelligence service that provides an interactive, graphical interface for analyzing and contextualizing the threats your network faces.

**11 operation(s)**:

_investigation_
- `get_domain_reputation(indicatorValue: text, includeTags: checkbox)` — Get Domain Reputation
- `get_file_reputation(indicatorValue: text, includeTags: checkbox)` — Get File Reputation
- `get_ip_reputation(indicatorValue: text, includeTags: checkbox)` — Get IP Reputation
- `get_sample_details(public_tag_name: text)` — Get Sample Details
- `get_session_details(session_id: text)` — Get Session Details
- `get_tag_details(public_tag_name: text)` — Get Tag Details
- `get_tags_list([scope: select], [query: json], [sortBy: select], [order: select], [pageSize: integer], [pageNum: integer])` — Get Tags List
- `get_threat_indicator_feed()` — Get Threat Indicator Feed
- `get_url_reputation(indicatorValue: text, includeTags: checkbox)` — Get URL Reputation
- `samples_search(scope: select, [query: json], [operator: select], [sort_field: select], [sort_order: select], [size: integer], [from: integer], [type: select])` — Samples Searches
- `top_tags_search(scope: select, query: json, [operator: select], [tagScopes: multiselect], [size: integer])` — Top Tags Search


### `phishing-initiative` v2.0.0 _(installed)_
_Phishing Initiative_

Phishing Initiative connector allows you to get URL reputation

**1 operation(s)**:

_investigation_
- `url_reputation(url: text)` — Get URL Reputation


### `phishme-intelligence` v1.0.0 _(installed)_
_Phishme Intelligence_

Provide various hunting operation like hunt file,hunt IP,hunt URL,hunt domain and reporting operation like get report integrate with Phishme Intelligence

**5 operation(s)**:

_investigation_
- `get_report(threat_id: integer)` — Get Report
- `hunt_domain(domain: text, [max_threats: integer])` — Hunt Domain
- `hunt_file(filehash: text, [max_threats: integer])` — Hunt File
- `hunt_ip(ip: text, [max_threats: integer])` — Hunt IP
- `hunt_url(url: text, [max_threats: integer])` — Hunt URL


### `plain-text-feed` v1.0.0 _(installed, ingestion)_
_Plain Text Feed_

Plain Text Feed can be used to fetch IP addresses from a text file from any publicly hosted url. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators()` — Get Indicators


### `polyswarm` v1.0.0 _(installed)_
_PolySwarm_

PolySwarm is a real-time threat intelligence from a crowdsourced network of security experts and antivirus companies. This connector facilitates the automated operations to get the URL, IP, File, Domain reputation.

**6 operation(s)**:

_investigation_
- `file_rescan(hash: text)` — File Rescan
- `file_scan(input: select, value: text)` — File Scan
- `get_domain_reputation(artifact: text)` — Get Domain Reputation
- `get_file_reputation(hash: text)` — Get File Reputation
- `get_ip_reputation(artifact: text)` — Get IP Reputation
- `get_url_reputation(artifact: text)` — Get URL Reputation


### `pulsedive` v1.0.0 _(installed)_
_Pulsedive_

Pulsedive is a free threat intelligence platform that allows users to search, scan, and enrich IP addresses, URLs, domains, and other Indicators of Compromise (IOCs) using data from open-source intelligence (OSINT) feeds. Users can also submit their own IOCs for analysis and enrichment.

**3 operation(s)**:

_investigation_
- `get_domain_reputation(indicator: text)` — Get Domain Reputation
- `get_ip_reputation(indicator: text)` — Get IP Reputation
- `get_links_of_indicator(indicator: text)` — Get Links of Indicator


### `qianxin-threat-intel` v1.1.0 _(installed)_
_QiAnxin Threat Intelligence_

QiAnxin Threat Intelligence Center provides automate processing and the manual operation of top security research teams to provide users with accurate threat intelligence based on multi-dimensional and global data collection capabilities. QiAnxin Threat Intelligence connector performs actions like IP reputation, file reputation etc.

**3 operation(s)**:

_investigation_
- `file_reputation([advance: checkbox], reputation_of: select)` — Get File Reputation
- `get_loss_detection_data(request_of: select, [ignore_url: checkbox], [ignore_port: checkbox], [ignore_top: checkbox])` — Get Loss Detection Data
- `ip_reputation(reputation_of: select)` — Get IP Reputation


### `quttera` v1.0.0 _(installed)_
_Quttera_

Quttera helps to scan website/domain for malware, ssl and open ports. This connector facilitates automated operations like scan website, get status of scan and get reports of scan etc.

**14 operation(s)**:

_investigation_
- `get_blacklist_report(domain_name: text, [response_format: select])` — Get Blacklist Report
- `get_blacklist_status(domain_name: text, [response_format: select])` — Get Blacklist Status
- `get_report_of_integrity_scan(domain_name: text, [response_format: select])` — Get Report of Integrity Scan
- `get_report_of_port_scan(domain_name: text, [response_format: select])` — Get Report of Port Scan
- `get_report_of_ssl_scan(domain_name: text, [response_format: select])` — Get Report of SSL Scan
- `get_report_of_url_scan(domain_name: text, [response_format: select])` — Get Report of URL Scan
- `get_status_of_integrity_scan(domain_name: text, [response_format: select])` — Get Status of Integrity Scan
- `get_status_of_port_scan(domain_name: text, [response_format: select])` — Get Status of Port Scan
- `get_status_of_ssl_scan(domain_name: text, [response_format: select])` — Get Status of SSL Scan
- `get_status_of_url_scan(domain_name: text, [response_format: select])` — Get Status of URL Scan
- `start_integrity_scan(domain_name: text, [response_format: select])` — Start Integrity Scan
- `start_port_scan(domain_name: text, [response_format: select])` — Start Port Scan
- `start_ssl_scan(domain_name: text, [response_format: select])` — Start SSL Scan
- `start_url_scan(domain_name: text, [response_format: select])` — Start URL Scan


### `rapid7-threat-command-cloud` v1.1.1 _(installed)_
_Rapid7 Threat Command Cloud_

Rapid7 Threat Command Cloud is a digital risk protection and external threat intelligence platform that helps organizations monitor, detect, and mitigate threats originating outside their perimeters (web, deep web, dark web).

**10 operation(s)**:

_investigation_
- `add_iocs_to_source(sourceID: text, iocs: object)` — Add IOCs to Source
- `change_ioc_severity(iocValue: text, severity: select)` — Change IOC Severity
- `generic_api_call(method: select, api_endpoint: text, [params: object], [json_data: object])` — Execute an API Request
- `get_alert_by_id(alertID: text)` — Get Alert Details
- `get_alerts_list([alertType: multiselect], [severity: multiselect], [sourceType: multiselect], [networkType: multiselect], [matchedAssetValue: text], [tags: text], [remediationStatus: multiselect], [sourceDateFrom: datetime], [sourceDateTo: datetime], [foundDateFrom: datetime], [foundDateTo: datetime])` — Get Alerts List
- `get_cves_by_ids(cveList: object)` — Get CVEs by IDs
- `get_cves_list_from_account([publishDateFrom: datetime])` — Get CVEs List from Account
- `get_ioc_by_value(iocValue: text)` — Get IOC by Value
- `get_ioc_sources()` — Get IOC Sources
- `get_iocs_by_filter(lastUpdatedFrom: datetime, [offset: integer], [limit: integer])` — Get IOCs by Filter


### `recorded-future` v2.0.0 _(installed)_
_Recorded Future_

Recorded Future is a threat intelligence product that automatically collects and analyzes threat intelligence from technical, open, and dark web sources to provide invaluable context for faster human analysis and real-time integration with your existing security systems.

**41 operation(s)**:

_investigation_
- `add_entity_to_user_list(listId: text, id: text, [context: json])` — Add Entity To User List
- `add_ioc_to_recorded_future_intelligence_cloud([options: json], [organization_ids: text], [timestamp: datetime], [ioc: json], [incident: json], [detection: json], [mitre_codes: text], [malwares: text])` — Add IOC To Recorded Future Intelligence Cloud
- `create_user_list([name: text], [type: text])` — Create User List
- `domain_reputation(domain: text, [fields: multiselect], [metadata: checkbox])` — Get Domain Reputation
- `domain_risklist([risk_rule_list: select])` — Get Domain Risk List
- `file_reputation(hash: text, [fields: multiselect], [metadata: checkbox])` — Get File Reputation
- `file_risklist([risk_rule_list: select])` — Get File Risk List
- `get_alert(alert_ID: text)` — Get Alert
- `get_bulk_identity_novel_exposures_alerts([playbook_alert_ids: text], [panels: text])` — Get Bulk Identity Novel Exposures Alerts
- `get_bulk_third_party_risk_alerts([playbook_alert_ids: text], [panels: text])` — Get Bulk Third Party Risk Alerts
- `get_entities_by_list_id(listId: text)` — Get Entities By List ID
- `get_identity_novel_exposures_alert_by_alert_id(playbook_alert_id: text, [panels: text])` — Get Identity Novel Exposures Alert By Alert ID
- `get_malware_categories()` — Get Malware Categories
- `get_malware_threat_map([malware: text], [categories: text], [watchlists: text])` — Get Malware Threat Map
- `get_malware_threat_map_by_org_id(orgId: text, [malware: text], [categories: text], [watchlists: text])` — Get Malware Threat Map By Org ID
- `get_maps_list()` — Get Maps List
- `get_third_party_risk_alert_by_alert_id(playbook_alert_id: text, [panels: text])` — Get Third Party Risk Alert By Alert ID
- `get_threat_actors_categories()` — Get Threat Actors Categories
- `get_threat_actors_list([name: text], [limit: integer], [offset: text])` — Get Threat Actors List
- `get_threat_map([actors: text], [categories: text], [watchlists: text])` — Get Threat Map
- `get_threat_map_by_org_id(orgId: text, [actors: text], [categories: text], [watchlists: text])` — Get Threat Map By Org ID
- `get_user_list_by_list_id(listId: text)` — Get User List By List ID
- `get_user_list_status_by_list_id(listId: text)` — Get User List Status By List ID
- `get_user_lists([name: text], [type: text], [limit: integer])` — Get User Lists
- `ip_reputation(ip: text, [fields: multiselect], [metadata: checkbox])` — Get IP Reputation
- `ip_risklist([risk_rule_list: select])` — Get IP Risk List
- `lookup_url(url: text, [fields: multiselect], [metadata: checkbox])` — Lookup URL
- `lookup_vulnerability(cve_id: text, [fields: multiselect], [metadata: checkbox])` — Lookup Vulnerability
- `remove_entity_from_user_list(listId: text, id: text)` — Remove Entity From User List
- `search_domain([fields: multiselect], [metadata: checkbox], [limit: integer], [from: integer], [riskScore: text], [firstSeen: text], [lastSeen: text], [list: text], [riskRule: select], [parent: text], [orderby: select], [direction: select])` — Search Domain
- `search_file([fields: multiselect], [metadata: checkbox], [limit: integer], [from: integer], [riskScore: text], [algorithm: select], [firstSeen: text], [lastSeen: text], [list: text], [riskRule: select], [orderby: select], [direction: select])` — Search Filehash
- `search_ip([fields: multiselect], [metadata: checkbox], [limit: integer], [from: integer], [range: text], [riskScore: text], [firstSeen: text], [lastSeen: text], [list: text], [riskRule: select], [orderby: select], [direction: select])` — Search IP
- `search_url([fields: multiselect], [metadata: checkbox], [limit: integer], [from: integer], [riskScore: text], [firstSeen: text], [lastSeen: text], [list: text], [riskRule: select], [orderby: select], [direction: select])` — Search URL
- `search_vulnerability([freetext: text], [fields: multiselect], [metadata: checkbox], [limit: integer], [from: integer], [riskScore: text], [cvssScore: text], [firstSeen: text], [lastSeen: text], [list: text], [riskRule: select], [orderby: select], [direction: select])` — Search Vulnerabilities
- `url_risklist([risk_rule_list: select])` — Get URL Risk List
- `vulnerability_risklist([risk_rule_list: select])` — Get vulnerability Risk List

- `get_riskrules(type: select)` — Get Risk Rules
- `lookup_malware(malware_id: text, [fields: multiselect], [metadata: checkbox])` — Lookup Malware
- `search_alert_rule([freetext: text], [limit: integer])` — Search Alert Rules
- `search_alerts([triggered: text], [assignee: text], [status: select], [alertRule: text], [freetext: text], [limit: integer], [from: integer], [orderby: select], [direction: select])` — Search Alerts
- `search_malware([freetext: text], [fields: multiselect], [metadata: checkbox], [limit: integer], [from: integer], [firstSeen: text], [lastSeen: text], [list: text], [orderby: select], [direction: select])` — Search Malware


### `riskiq-digital-footprint` v1.0.0 _(installed)_
_RiskIQ Digital Footprint_

RiskIQ Digital Footprint gives complete visibility beyond the firewall. Unlike scanners and IP-dependent data vendors, RiskIQ Digital Footprint is the only solution with composite intelligence, code-level discovery and automated threat detection and exposure monitoring—security intelligence mapped to your attack surface. This connector facilitates automated interactions, with a RiskIQ Digital Footprint server using FortiSOAR™ playbooks.

**8 operation(s)**:

_investigation_
- `add_assets(request: json, [failOnError: checkbox])` — Add Assets
- `get_assets_by_type(type: select, name: text, [global: checkbox], [size: integer], [recent: checkbox])` — Get Assets By Type
- `get_assets_by_uuid(uuid: text, [global: checkbox], [recent: checkbox])` — Get Assets By UUID
- `get_changed_asset([type: select], [date: datetime], [range: select], [measure: select], [brand: text], [organization: text], [tag: text], [page: integer], [size: integer])` — Get Changed Asset
- `get_changed_asset_summary([date: datetime], [range: select], [brand: text], [organization: text], [tag: text])` — Get Changed Asset Summary
- `get_connected_asset(type: select, name: text, [global: checkbox], [page: integer], [size: integer])` — Get Connected Assets
- `get_task_status(id: text)` — Get Task Status
- `update_assets(request: json, [failOnError: checkbox])` — Update Assets


### `riskiq-passivetotal` v1.0.0 _(installed)_
_RiskIQ PassiveTotal_

RiskIQ PassiveTotal used to map threat actor infrastructure, profile hostnames & IP addresses, discover web technologies on Internet hosts. This connector provides actions for Get Reputation, Get Components, Get Trackers, Get Alerts, Get Enrichment Data, etc

**10 operation(s)**:

_investigation_
- `get_alerts([project: text], [artifact: text], [start: datetime], [end: datetime], [page: integer], [size: integer])` — Get Alerts
- `get_components(search_by: select, name: text, [version: text], [category: text], [page: integer], [sort: text], [order: text])` — Get Components
- `get_cookies(query: text, [start: datetime], [end: datetime], [page: integer])` — Get Cookies
- `get_enrichment_data(query: text, [query_for: select])` — Get Enrichment Data
- `get_passive_dns(query: text, [start: datetime], [end: datetime], [timeout: integer])` — Get Passive DNS
- `get_reputation(query: text)` — Get Reputation
- `get_services(query: text)` — Get Services
- `get_trackers(query: text, [start: datetime], [end: datetime], [page: integer])` — Get Trackers
- `get_whois_data(query: text, [compact_record: checkbox], [history: checkbox])` — Get Whois Data
- `search_whois_data(query: text, field: select)` — Search Whois Data


### `riskiq-whoisiq` v1.0.0 _(installed)_
_RiskIQ WHOISIQ_

The WHOISIQ™ allow you to search for WHOISIQ™ records by the various attributes on those records. Currently, the API supports searching by (physical) address, domain, IP Address, email, (registrant) name, nameserver, (registrant) organization, and (registrant) phone number. This connector facilitates automated interactions, with a RiskIQ WHOISIQ server using FortiSOAR™ playbooks.

**7 operation(s)**:

_investigation_
- `get_address(address: text, [exact: checkbox], [maxResults: text])` — Get Address
- `get_domain(domain: text, [exact: checkbox], [maxResults: text])` — Get Domain
- `get_email(email: text, [exact: checkbox], [maxResults: text])` — Get Email Address
- `get_name(name: text, [exact: checkbox], [maxResults: text])` — Get Name
- `get_name_server(nameserver: text, [exact: checkbox], [maxResults: integer])` — Get Name Server
- `get_org(org: text, [exact: checkbox], [maxResults: text])` — Get Organization
- `get_phone(phone: text, [exact: checkbox], [maxResults: text])` — Get Phone Number


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

_investigation_
- `get_url_reputation(url: text)` — Get URL Reputation


### `security-scorecard` v1.0.0 _(installed)_
_SecurityScorecard_

Security Scorecard Platform combines several threat intelligence sources to provide in-depth insights on threat hosts and attack infrastructure.This connector facilitates automated operations to pull off real-time host configuration analysis to come up with actionable threat intelligence that is vital in detection, mitigation, and remediation.

**8 operation(s)**:

_investigation_
- `get_alert_list(email_id: text)` — Get Alert List
- `get_all_companies_portfolio(portfolio_id: text)` — Get All Companies Portfolio
- `get_company_factor_score(domain: text)` — Get Company Factor Score
- `get_company_history_factor_score(domain: text)` — Get Company History Factor Score
- `get_company_history_score(domain: text)` — Get Company History Score
- `get_company_score(domain: text)` — Get Company Score
- `get_list_of_portfolio()` — Get List of Portfolio
- `get_ransomware_details(ransomware_id: text)` — Get Ransomware Details  


### `security-trails` v1.0.0 _(installed)_
_SecurityTrails_

SecurityTrails is a cybersecurity platform that provides domain and IP intelligence services. It offers tools for reconnaissance, asset discovery, and monitoring of digital footprints to enhance security assessments and investigations. Users can access information such as historical DNS records, WHOIS details, and other data related to domains and IP addresses.

**9 operation(s)**:

_investigation_
- `get_associated_domains(host: text)` — Get Associated Domains
- `get_associated_ips(domain: text)` — Get Associated IPs
- `get_domain_details(host: text)` — Get Domain Details
- `get_domain_tags_details(host: text)` — Get Domain Tags Details
- `get_domain_whois_details(host: text)` — Get Domain WHOIS Details
- `get_ips_neighbors(ip_address: text)` — Get IPs Neighbors
- `get_subdomain_details(host: text, [children_only: checkbox], [include_inactive: checkbox])` — Get Subdomain Details
- `get_whois_history(host: text)` — Get WHOIS History
- `get_whois_ips(ip_address: text)` — Get Whois IPs


### `securitybridge` v1.0.0 _(installed, ingestion)_
_SecurityBridge_

SecurityBridge is an SAP native solution for Security and Event monitoring for SAP.

**1 operation(s)**:

_investigation_
- `fetch_events(qFrom: datetime, qTo: datetime, [response_format: select])` — Fetch Events


### `snort-ip-blocklist-feed` v2.0.0 _(installed, ingestion)_
_Snort IP Blocklist Feed_

Snort is an open-source, free and lightweight network intrusion detection system (NIDS) software for Linux and Windows to detect emerging threats. This connector facilitates automated operations related to fetching the list indicators and ingestion of daily threat feeds.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators()` — Get Indicators


### `spamhaus` v1.0.1 _(installed)_
_Spamhaus_

The Spamhaus Project is responsible for compiling several widely used anti-spam lists. This connector helps to check IP/Domain/URL is present in Spamhaus blocklists or not.

**3 operation(s)**:

_investigation_
- `check_domain(domain: text)` — Lookup Domain
- `check_ip(ip_address: text)` — Lookup IP
- `check_url(url: text)` — Lookup URL


### `spamhaus-feed` v1.0.0 _(installed, ingestion)_
_Spamhaus Feed_

Spamhaus Feed provides access to expansive threat data and related information. This connector facilitates automated operations related to fetching the list of IPs blocklist.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `fetch_indicators([output_mode: select])` — Fetch Indicators


### `ssl-blacklist-feed` v1.0.0 _(installed, ingestion)_
_SSL Blacklist Feed_

The SSL Blacklist (SSLBL) is a project of abuse.ch with the goal of detecting malicious SSL connections, by identifying and blacklisting SSL certificates used by botnet C&C servers. In addition, SSLBL identifies JA3 fingerprints that helps you to detect & block malware botnet C&C communication on the TCP layer. This connector facilitates automated operations related to fetching the list of IPs blacklist.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `fetch_indicators([last_pull_time: text], [output_mode: select])` — Fetch Indicators


### `stix` v1.0.0 _(installed)_
_STIX_

Structured Threat Information Expression, is a language and serialization format for exchanging threat information in cyberspace. Using this connector we can be used to extract indicators from the submitted STIX file and also export selected indicators from FortiSOAR in a valid STIX specification.<br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>.

**4 operation(s)** (+2 hidden):

_investigation_
- `create_indicators(indicator_list: text, tlp: select, [file_response: checkbox])` — Export Indicators In STIX Spec Format
- `extract_indicators(file_id: text, [output_mode: select], [confidence: integer], [reputation: select], [tlp: select], [expiry: integer])` — Extract Indicators From STIX File


### `symantec-deepsight-intelligence` v1.0.2 _(installed)_
_Symantec DeepSight Intelligence_

Symantec DeepSight™ Intelligence is a cloud-hosted cyber threat intelligence platform that provides an edge against cyber threats. This connector facilitates automated operations like get Filehash , URL, Domain , IP reputation

**4 operation(s)**:

_investigation_
- `domain_reputation(domain: text)` — Get Domain Reputation
- `filehash_reputation(filehash: text)` — Get File Reputation
- `ip_reputation(ip: text)` — Get IP Reputation
- `url_reputation(url: text)` — Get URL Reputation


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

_investigation_
- `get_connected_domains_details(domain_name: text)` — Get Connected Domains Details
- `get_domain_infrastructure_analysis_details(domain_name: text)` — Get Domain Infrastructure Analysis Details
- `get_domain_malware_check_details(domain_name: text)` — Get Domain Malware Check Details
- `get_domain_reputation_details(domain_name: text, mode: select, query_type: select)` — Get Domain Reputation  Details
- `get_ssl_certificate_chain_details(domain_name: text)` — Get SSL Certificate Chain Details
- `get_ssl_configuration_analysis_details(domain_name: text)` — Get SSL Configuration Analysis Details


### `threat-miner` v1.0.0 _(installed)_
_ThreatMiner_

ThreatMiner is a threat intelligence portale that aggregates data from multiple open-source platforms like: VirusTotal, CIRCL etc... and enable analysts to research under a single interface. This connector enables users to create automated solutions to query against ThreatMiner's database.

**6 operation(s)**:

_investigation_
- `get_domain_details(domain_name: text, query_type: select)` — Get Domain Details
- `get_email_details(email: text)` — Get Email Details
- `get_file_hash_details(file_hash: text, query_type: select)` — Get File Hash Details
- `get_import_hash_details(imphash: text)` — Get Import Hash Details
- `get_ip_details(ip_address: text, query_type: select)` — Get IP Details
- `get_ssdeep_details(ssdeep: text)` — Get SSDeep Details


### `threatbook` v1.0.0 _(installed)_
_ThreatBook_

ThreatBook is China’s first security threat intelligence company, dedicated to providing real-time, accurate and actionable threat intelligence to block, detect and prevent attacks.

**13 operation(s)**:

_investigation_
- `domain_analysis(resource: text, [exclude: multiselect], [lang: select])` — Submit Domain for Analysis
- `file_detection_report(hash_type: select, hash_value: text)` — Get File Detection Report
- `get_domain_name_context(resource: text, [lang: select])` — Get Domain Name Context
- `get_file_reputation(hash_type: select, hash_value: text, [sandbox_type: select], [query_fields: select])` — Get File Reputation
- `get_ip_reputation(resource: text, [lang: select])` — Get IP Reputation
- `get_url_reputations(url: text)` — Get URL Reputations
- `loss_detection(resource: text, [lang: select])` — Get Loss Detection Data
- `run_domain_advance_query(resource: text, [exclude: select], [lang: select])` — Run Domain Advanced Query
- `run_ip_advance_query(resource: text, exclude: multiselect, [lang: select])` — Run IP Advance Query
- `run_sub_domain_query(resource: text, [lang: select])` — Run Sub Domain Query
- `scan_url(url: text)` — Submit URL for Scanning
- `submit_file(input: select, value: text, [sandbox_type: select], [run_time: integer])` — Submit File
- `submit_ip(resource: text, [exclude: multiselect], [lang: select])` — Submit IP for Analysis


### `threatconnect` v2.0.0 _(installed)_
_ThreatConnect_

ThreatConnect connector which utilizes the ThreatConnect API and allows threat intelligence actions such as get reputation of IP address, URL, File Hash or Email address etc.

**7 operation(s)**:

_investigation_
- `hunt_email(indicator: text, [owner: text], [includeAdditional: checkbox])` — Get Email Reputation
- `hunt_file(indicator: text, [owner: text], [includeAdditional: checkbox])` — Get File Reputation
- `hunt_host(indicator: text, [owner: text], [includeAdditional: checkbox])` — Get Host Reputation
- `hunt_ip(indicator: text, [owner: text], [includeAdditional: checkbox])` — Get IP Reputation
- `hunt_url(indicator: text, [owner: text], [includeAdditional: checkbox])` — Get URL Reputation
- `invoke_api(endpoint: text)` — Invoke ThreatConnect REST API
- `list_indicator([includeAdditional: checkbox], [resultLimit: integer], [resultStart: integer])` — List Indicator


### `threatq` v2.1.0 _(installed)_
_ThreatQ_

ThreatQuotient is a threat intelligence platform that centrally manages and correlates unlimited external sources. This connector facilitates automated operation such as collects and interprets intelligence data from open sources and manages indicators.

**28 operation(s)**:

_investigation_
- `add_attribute(object_type: select, obj_id: text, name: text, value: text)` — Add Attribute
- `add_source(object_type: select, obj_id: text, name: text)` — Add Source
- `create_adversary(name: text, source: text, [description: textarea])` — Create Adversary
- `create_event(event_type: select, title: text, [source: text], [description: textarea])` — Create Event
- `create_ioc(indicator_type: select, indicator_value: text, indicator_status: select, source: text)` — Create IOC
- `get_domain_reputation(indicator: text)` — Get Domain Reputation
- `get_event_types()` — Get Event Types
- `get_file_reputation(indicator_type: select, indicator: text)` — Get File Reputation
- `get_indicator_reputation([indicator_type: select], indicator: text)` — Get Reputation
- `get_indicator_statuses()` — Get Indicator Statuses
- `get_indicator_types()` — Get Indicator Types
- `get_ip_reputation(indicator: text)` — Get IP Reputation
- `get_list_of_adversaries([offset: integer], [limit: integer])` — Get List of Adversaries
- `get_list_of_events([offset: integer], [limit: integer], [event_type: select], [sources: text])` — Get List of Events
- `get_list_of_indicators([limit: integer], [sort: select], [indicator_class: select])` — Get List of Indicators
- `get_related_ioc(indicator: text)` — Get Related IOCs
- `get_related_objects(obj_type: select, obj_id: text, related_obj_type: select)` — Get Related Objects
- `get_saved_searches([limit: integer], [offset: integer], [sort: text])` — Get Saved Searches
- `get_url_reputation(indicator_type: select, indicator: text)` — Get URL Reputation
- `link_ioc(indicator: text, link_indicator: text)` — Link IOCs
- `link_two_objects(obj1_type: select, obj1_id: text, obj2_type: select, obj2_id: text)` — Link Two Objects
- `remove_attribute(object_type: select, obj_id: text, id: text)` — Remove Attribute
- `remove_source(object_type: select, obj_id: text, id: text)` — Remove Source
- `run_search_query([object: select], [query: json], [limit: integer], [offset: integer], [sort: text])` — Run Search Query
- `search_event(event: text)` — Search Event
- `search_indicator(indicator: text)` — Search Indicator
- `unlink_two_objects(obj1_type: select, obj1_id: text, obj2_type: select, obj2_id: text)` — Unlink Two Objects
- `update_indicator(indicator: text, indicator_status: select, [indicator_class: select])` — Update Indicator


### `threatstream` v2.5.1 _(installed, ingestion)_
_Anomali ThreatStream_

Anomali ThreatStream offers the most comprehensive Threat Intelligence Platform, allowing organizations to access all intelligence feeds and integrate it seamlessly with internal security and IT systems. This connector facilitates automated operations to to pull threat intelligence from the ThreatStream platform, import observables into ThreatStream from any source, manage threat model entities and investigations, and so on.

**35 operation(s)** (+2 hidden):

_investigation_
- `advance_query(value: text, [record_number: select])` — Run Advanced Search
- `approve_import_job(value: text)` — Approve IOC By Import ID
- `create_incident(name: text, [is_public: checkbox], [tags: text], [intelligence: text], [tlp: select], [fields: json])` — Create Incident
- `create_investigation(name: text, [status: select], [priority: select], [tlp: select], [description: html], [additional_attributes: json])` — Create Investigation
- `create_threat_bulletin(name: text, [body_content_type: select], [body: textarea], [is_public: checkbox], [tlp: select], [reference_id: text], [fields: json])` — Create Threat Bulletin
- `delete_incident(value: integer)` — Delete Incident
- `domain_reputation(value: text, filter_option: select, [record_number: select])` — Get Domain Reputation
- `email_reputation(value: text, filter_option: select, [record_number: select])` — Get Email ID Reputation
- `fetch_incidents([value: text], [limit: integer], [offset: integer])` — Get Incident List
- `file_reputation(value: text, filter_option: select, [record_number: select])` — Get File Reputation
- `filter_language_query(value: text, [record_number: select])` — Run Filter Language Query
- `get_import_job_status(value: text)` — Get Import Job Status
- `get_import_jobs(value: text, [record_number: select])` — Get Import Job Details
- `get_incident(value: integer)` — Get Incident
- `get_submit_url_status(value: integer)` — Get Sandbox Status of Submitted URL/File
- `get_submitted_url_report(value: integer)` — Get Sandbox Report of Submitted URL/File
- `intelligence_enrichments(services: select)` — Get Intelligence Enrichments
- `ip_reputation(value: text, filter_option: select, [record_number: select])` — Get IP Reputation
- `list_incidents_by_indicator(value: text, [limit: integer], [offset: integer])` — Get Incident List By Indicator
- `list_investigation_elements([investigation_id: text], [add_related_indicators: select], [record_number: select])` — List Investigation Elements
- `list_investigations([investigation_id: text], [name: text], [status: select], [add_related_indicators: select], [remote_api: checkbox], [created_ts__gte: datetime], [created_ts__lte: datetime], [record_number: select])` — List Investigations
- `list_observables_associated_threat_bulletin(value: integer, [record_number: select])` — Get Threat Bulletin Observables
- `list_threat_bulletins([query: text], [record_number: select])` — Get Threat Bulletin List
- `list_threat_model_entity(id: integer, entity_type: select, [record_number: select])` — Get Threat Bulletin Entities
- `reject_import_job(value: text)` — Reject IOC By Import ID
- `submit_observables([reference_id: text], [data: text], confidence: integer, [source_confidence_weight: integer], severity: select, classification: select, [expiration_ts: select], [notes: text], [ip_mapping: text], [domain_mapping: text], [url_mapping: text], [email_mapping: text], [md5_mapping: text], [trusted_circles: text], [threat_type: text], [require_approval: checkbox], [reject_benign: checkbox])` — Submit Observables
- `submit_urls_files(classification: select, sandbox_type: select, sample_type: select, detail: text, [use_premium_sandbox: checkbox], [trusted_circles: text])` — Submit URLs or Files to Sandbox
- `update_incident(value: integer, [name: text], [status: select], [status_desc: text], [fields: json])` — Update Incident
- `update_investigation(investigation_id: text, [name: text], [status: select], [priority: select], [tlp: select], [description: html], [additional_attributes: json])` — Update Investigation
- `update_threat_bulletin(tb_id: integer, [name: text], [status: select], [reference_id: text], [fields: json])` — Update Threat Bulletin
- `url_reputation(value: text, filter_option: select, [record_number: select])` — Get URL Reputation
- `whois_domain(value: text)` — Get Whois Domain Information
- `whois_ip(value: text)` — Get Whois IP Information


### `tor` v2.0.0 _(installed)_
_Tor_

Tor Connector facilitates to query information of Tor network

**1 operation(s)**:

_miscellaneous_
- `lookup_ip(ip: text)` — Check Tor Exit Node


### `tor-exit-address-feed` v1.0.0 _(installed, ingestion)_
_Tor Exit Address Feed_

The Tor Exit List service maintains lists of IP addresses used by all exit relays in the Tor network. Service providers may find it useful to know if users are coming from the Tor network, as they may wish to provide their users with an onion service.

**1 operation(s)**:

_investigation_
- `get_indicators()` — Get Indicators


### `trend-micro-sms` v1.1.0 _(installed)_
_Trend Micro SMS_

Trend Micro SMS(Security Management System) Provides global vision and security policy control for threat intelligence and enables comprehensive analysis and corrections. You can configure it to automatically check for, download, and distribute filter updates to TrendMicro SMS system as well as to take immediate action on events based on yer security policy.

**7 operation(s)**:

_investigation_
- `add_reputation_entry(address_type: select, address_value: text, [tag_data: text])` — Add Reputation Entry
- `delete_reputation_bulk(input_file: file, [address_type: select])` — Delete Reputation
- `delete_reputation_entry([ip_list: text], [dns_list: text], [url_list: text], [criteria: select])` — Delete Reputation Entries
- `import_reputation_bulk(input_file: file, [address_type: select])` — Import Reputation
- `quarantine_ip(ip: text, policy_name: text, [timeout: integer])` — Quarantine IP Address
- `query_reputation_entry(address_type: select, address_value: text)` — Query Reputation Entries
- `unquarantine_ip(ip: text, policy_name: text, [timeout: integer])` — Unquarantine IP Address


### `trend-micro-vision-one` v1.0.0 _(installed)_
_Trend Micro Vision One_

Trend Micro Vision One providing deep and broad extended detection and response (XDR) capabilities that collect and automatically correlate data across multiple security layers—email, endpoints, servers, cloud workloads, and networks—Trend Micro Vision One prevents the majority of attacks with automated protection. This connector facilitates automated operation such as retrieving information about workbench alerts in Trend Micro Vision One, adding indicators such as email addresses, domains, etc. to the 'Suspicious Object List' in Trend Micro Vision One, terminates a process that is running on one or more endpoints, etc.

**17 operation(s)**:

_containment_
- `add_to_block_list(indicator_type: select, indicator_value: text, [description: text])` — Add to Block List
- `add_to_suspicious_object_list(indicator_type: select, indicator_value: text, [scanAction: select], [riskLevel: select], [daysToExpiration: integer], [description: text])` — Add to Suspicious Object List
- `isolate_endpoint(isolate_by: select, [description: text])` — Isolate Endpoints
- `terminates_process(terminates_by: select, fileSha1: text, [fileName: text], [description: text])` — Terminates Process

_investigation_
- `collect_file(collect_by: select, filePath: text, [description: text])` — Collect File
- `get_alert_details(id: text)` — Get Alert Details
- `get_detection_data(query: text, [startDateTime: datetime], [endDateTime: datetime], [top: integer], [select: text])` — Get Detection Data
- `get_endpoint_details(query: text, [top: integer])` — Get Endpoint Details
- `get_list_alerts([query: text], [startDateTime: datetime], [endDateTime: datetime], [dateTimeTarget: select], [orderBy: text], [offset: text])` — Search Alerts
- `get_task_details(task_id: text)` — Get Task Details

_remediation_
- `add_to_exception_list(indicator_type: select, indicator_value: text, [description: text])` — Add to Exception List
- `delete_email_message(delete_by: select, [description: text])` — Delete Email Message
- `quarantine_email_message(quarantine_by: select, [description: text])` — Quarantine Email Message
- `remove_from_block_list(indicator_type: select, indicator_value: text, [description: text])` — Remove from Block List
- `remove_from_exception_list(indicator_type: select, indicator_value: text)` — Remove from Exception List
- `remove_from_suspicious_object_list(indicator_type: select, indicator_value: text)` — Remove from Suspicious Object List
- `restore_endpoint(restore_by: select, [description: text])` — Restore Endpoints


### `twitter-feed` v1.0.0 _(installed, ingestion)_
_Twitter Feed_

Twitter feed connector fetches threat intelligence from tweettioc.com.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators([feed_type: select])` — Get Indicators


### `unit-42-intel-objects-feed` v1.0.0 _(installed, ingestion)_
_Unit 42 Intel Objects Feed_

Unit 42 Intel provides threat intelligence from multiple Palo Alto Networks services. Using Unit 42 Intel data, you can investigate indicators and their behaviors, and use that knowledge to better safeguard your network from malicious activity.<br></br> This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `fetch_indicators([last_pull_time: datetime], [limit: integer])` — Fetch Indicators


### `urlhaus` v1.1.0 _(installed)_
_URLhaus_

URLhaus is a project operated by abuse.ch. The purpose of the project is to collect, track and share malware URLs, helping network administrators and security analysts to protect their network and customers from cyber threats.

**8 operation(s)**:

_investigation_
- `get_hash_details(hash: text)` — Get Hash Details 
- `get_host_details(host: text)` — Get Host Details
- `get_recent_payload(limit: text)` — Get Recent Payloads
- `get_recent_urls(limit: text)` — Get Recent URLs
- `get_signature(signature: text)` — Query Signature Information
- `get_tag(tag: text)` — Query Tag Information
- `get_url_details(URL: text)` — Get URL Details
- `get_url_details_by_id(urlid: text)` — Get URLs Details by ID


### `urlscan-io` v1.1.2 _(installed)_
_URLScan.io_

URLScan.io provides a service that analyzes websites and the resources they request. URLScan.io provides actions like search domain, ip, hash scan URL and retrieve report of scanned url.

**6 operation(s)**:

_investigation_
- `custom_search(query: text, [size: integer])` — Custom Search
- `get_report(scan_id: text)` — Get Report
- `search_domain(domain: text, [size: integer])` — Search Domain
- `search_hash(hash: text, [size: integer])` — Search Hash
- `search_ip(ip: text, [size: integer])` — Search IP
- `submit_url(url: text, [private: checkbox])` — Submit URL


### `usom` v1.0.0 _(installed, ingestion)_
_USOM Feed_

USOM has URL's and it is lookup connector. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_feed([modified_after: datetime])` — Fetch Indicators


### `viriback-c2-tracker-feed` v1.0.0 _(installed, ingestion)_
_ViriBack C2 Tracker Feed_

ViriBack C2 Tracker is a C2 Tracker platform that instantly monitors current cyber threats. ViriBack C2 Tracker tracks malware activity and provides the URLs of the most recently detected Command and Control (C2) panels and the malware used on these panels. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators([output_mode: select])` — Get Indicators


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

_investigation_
- `abort_retrohunt_job(id: text)` — Abort Retrohunt Job
- `analysis_file([type: select], analysis_id: text)` — Get File Or URL Analysis Report
- `create_livehunt_ruleset(name: text, rules: text, [enabled: checkbox], [limit: integer], [notification_emails: text])` — Create Livehunt Ruleset
- `create_retrohunt_job(rules: text, [notification_emails: text], [corpus: select], [start_time: datetime], [end_time: datetime])` — Create Retrohunt Job
- `create_zip_file(hashes: text, [password: password])` — Create ZIP File
- `delete_livehunt_ruleset(id: text)` — Delete Livehunt Ruleset
- `delete_retrohunt_job(id: text)` — Delete Retrohunt Job
- `download_file(id: text)` — Download File
- `download_zip_file(id: text)` — Download ZIP File
- `get_domain_reputation(domain: text, [relationships: multiselect])` — Get Domain Reputation
- `get_file_reputation(file_hash: text, [relationships: multiselect])` — Get File Reputation
- `get_ip_reputation(ip: text, [relationships: multiselect])` — Get IP Reputation
- `get_livehunt_notifications_details(id: text)` — Get Livehunt Notifications Details
- `get_livehunt_notifications_files_list([filter: text], [limit: integer], [cursor: text], [count_limit: integer])` — Get Livehunt Notifications Files List
- `get_livehunt_notifications_list([filter: text], [order: text], [limit: integer], [cursor: text], [count_limit: integer])` — Get Livehunt Notifications List
- `get_livehunt_rule_files_list(id: text, [limit: integer], [cursor: text])` — Get Livehunt Rule Files List
- `get_livehunt_ruleset_details(id: text)` — Get Livehunt Ruleset Details
- `get_livehunt_rulesets_list([filter: text], [order: text], [limit: integer], [cursor: text])` — Get Livehunt Rulesets List
- `get_pcap_file_behaviour(sandbox_id: text)` — Get PCAP File Behaviour
- `get_retrohunt_job_details(id: text)` — Get Retrohunt Job Details
- `get_retrohunt_job_matching_files(id: text, [limit: integer], [cursor: text])` — Get Retrohunt Job Matching Files
- `get_retrohunt_jobs_list([filter: text], [limit: integer], [cursor: text])` — Get Retrohunt Jobs List
- `get_url_reputation(url: text, [relationships: multiselect])` — Get URL Reputation
- `get_widget_html_content(token: text)` — Get Widget HTML Content
- `get_widget_rendering_url(query: text, [fg1: text], [bg1: text], [bg2: text], [bd1: text])` — Get Widget Rendering URL
- `get_zip_file_status(id: text)` — Get ZIP File Status
- `get_zip_file_url(id: text)` — Get ZIP File URL
- `scan_url(url: text)` — Submit URL for Scanning
- `search_intelligence(query: text, [order: text], [limit: integer], [descriptors_only: checkbox], [cursor: text])` — Search Intelligence
- `submit_sample(input: select, value: text)` — Submit File
- `update_livehunt_ruleset(id: text, name: text, rules: text, [enabled: checkbox], [limit: integer], [notification_emails: text])` — Update Livehunt Ruleset


### `vx-vault-feed` v1.0.0 _(installed, ingestion)_
_VX Vault Feed_

VX Vault is a platform that serves as a repository for malware samples and related research. This connector facilitates automated operations related to fetching the list indicators. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators([output_mode: select], [limit: integer])` — Get Indicators


### `webroot-brightcloud-threat-intelligence` v1.1.0 _(installed)_
_Webroot BrightCloud Threat Intelligence_

BrightCloud Threat Intelligence Connector for collecting reputation details of IP and URL addresses, and files via BrightCloud API

**3 operation(s)**:

_investigation_
- `file_reputation(md5: text)` — Check File Reputation
- `ip_reputation(ip: text)` — Check IP Address Reputation
- `url_reputation(url: text)` — Check URL Reputation


### `whats-my-browser` v1.0.0 _(installed)_
_WhatIsMyBrowser_

WhatIsMyBrowser parses user agent strings and gives insight into known user agents. This Connector supports executing investigative action like parse user agent on the WhatIsMyBrowser.

**1 operation(s)**:

_investigation_
- `user_agent_parse(user_agent: text)` — Parse User Agent


### `whois-freaks` v1.0.0 _(installed)_
_WhoisFreaks_

WhoisFreaks provide well-parsed and structured domain WHOIS data for all domain names, registrars, countries and TLDs since the birth of internet. The carefully crawled current and historical domain data is available in the form of REST APIs, lookup tools, and downloadable database

**3 operation(s)**:

_investigation_
- `dns_lookup([domainName: text], type: multiselect)` — Get DNS Lookup
- `ssl_certificates(domainName: text, [chain: checkbox], [SSLRaw: checkbox])` — Get SSL Certificates
- `whois_lookup(domainName: text, whois: select)` — Get Whois Lookup


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

_investigation_
- `brand_monitor(include_domain_search_terms: text, [exclude_domain_search_terms: text], [sinceDate: date], [mode: select], [withTypos: checkbox])` — Brand Monitor
- `dns_lookup([domainName: text], type: multiselect)` — Get DNS Lookup
- `domain_subdomain_discovery(include_domain: text, [include_subdomain: text], [exclude_domains: text], [exclude_subdomains: text], [sinceDate: date])` — Domain or Subdomain Discovery
- `reverse_dns_search(reverse_dns_type: select, [from: text])` — Get Reverse DNS Search
- `reverse_whois_search(include_domain_search_terms: text, [exclude_domain_search_terms: text], [include_audit_dates: checkbox], [search_type: select], [mode: select], [createdDateFrom: date], [createdDateTo: date], [updatedDateFrom: date], [updatedDateTo: date], [expiredDateFrom: date], [expiredDateTo: date], [search_after: text])` — Get Reverse WHOIS Search
- `ssl_certificates(domainName: text, [withChain: checkbox], [hardRefresh: checkbox])` — Get SSL Certificates
- `whois_history_search(domainName: text, [sinceDate: date], [createdDateFrom: date], [createdDateTo: date], [updatedDateFrom: date], [updatedDateTo: date], [expiredDateFrom: date], [expiredDateTo: date])` — Get WHOIS History Search
- `whois_search(domainName: text, [preferFresh: checkbox], [da: select], [ip: checkbox], [ipWhois: checkbox], [checkProxyData: checkbox], [other_fields: json])` — Get WHOIS Search


### `xforce` v1.0.2 _(installed)_
_IBM XForce_

IBM XForce connector

**15 operation(s)**:

_investigation_
- `get_dns_record(query: text)` — Get DNS Record
- `get_file_reputation_using_filehash(filehash: text)` — Get File Reputation
- `get_ip_behaviour(ip: text)` — Get IP Behaviour
- `get_ip_registrant(host: text)` — Get IP Registrant
- `get_ip_report(ip: text)` — Get IP Report
- `get_ip_reputation(ip: text)` — Get IP Reputation
- `get_relative_malware(family: text)` — Get Relative Malware
- `get_url_behaviour(url: text)` — Get URL Behaviour
- `get_url_report(url: text)` — Get URL Report
- `get_vulnerability(query: text, [start_date: datetime], [end_date: datetime], [bookmark: text])` — Get Vulnerability
- `get_vulnerability_from_stdcode(stdcode: text)` — Get Vulnerability from STDCODE
- `get_vulnerability_from_xfid(xfid: text)` — Get Vulnerability from XFID
- `search_signature(query_string: text)` — Search Signature
- `search_signature_by_pamid(pamId: text)` — Search Signature by PAMID
- `search_signature_by_xpu(xpu: text)` — Search Signature by XPU


### `zerofox` v1.0.1 _(installed)_
_ZeroFox_

ZeroFox Platform combines advanced AI-driven analysis to detect complex threats on the surface, deep and dark web, fully managed services with threat analysts that become an extension of your team, and automated remediation to effectively disrupt threats.

**19 operation(s)**:

_investigation_
- `alert_cancel_takedown(alert_id: text)` — Cancel Alert Takedown
- `alert_request_takedown(alert_id: text)` — Request Alert Takedown
- `assign_alert_to_user(alert_id: text, username: text)` — Assign Alert to User
- `close_alert(alert_id: text)` — Close Alert
- `create_entity(name: text, [policy: text], [strict_name_matching: checkbox], [tags: text], [organization: text])` — Create Entity
- `get_alert_details(alert_id: text)` — Get Alert Details
- `get_alerts_list([account: text], [alert_type: select], [assignee: text], [entity: text], [entity_term: text], [min_timestamp: datetime], [max_timestamp: datetime], [last_modified: integer], [network: text], [risk_rating: select], [sort_direction: select], [sort_field: select], [status: select], [escalated: checkbox], [limit: integer], [offset: integer], [additional_fields: json])` — Get Alerts List
- `get_domain_lookup(domain: text)` — Get Domain Lookup
- `get_email_lookup(email: text)` — Get Email Lookup
- `get_entity_list([email_address: text], [group: text], [label: text], [network: text], [networks: text], [policy: text], [type: text], [page: text])` — Get Entity List
- `get_entity_types()` — Get Entity Types List
- `get_exploits_lookup(created_after: datetime)` — Get Exploits Lookup
- `get_filehash_lookup(hash: text)` — Get FileHash Lookup
- `get_ip_lookup(ip: text)` — Get IP Lookup
- `get_policy_types()` — Get Policy Types List
- `modify_alert_notes(alert_id: text, notes: text)` — Modify Alert Notes
- `modify_alert_tags(alert_id: text, action: select, tags_list: text)` — Modify Alert Tags
- `open_alert(alert_id: text)` — Open Alert
- `submit_threat(entity_id: text, source: text, alert_type: select, violation: select, [notes: text])` — Submit Threat


### `zoom-feed` v1.0.0 _(installed, ingestion)_
_Zoom Feed_

Zoom publishes its current IP address ranges in txt files. This connector facilitates automated operations to fetch these indicators and ingestion of daily threat feeds. This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**1 operation(s)**:

_investigation_
- `get_indicators(services: multiselect, [last_pull_time: datetime])` — Get Indicators


---

## Threat Intelligence Exchange

### `cyware` v1.0.0 _(installed)_
_Cyware_

Perform actions like list reported incidents, get incident details from Cyware

**15 operation(s)**:

_investigation_
- `get_alert_categories()` — Get Alert Categories
- `get_executive_protection()` — Get Executive Protection Details
- `get_incident_detail(incident_id: text)` — Get Incident Details
- `get_recipient_groups()` — Get Recipient Groups
- `get_user_by_email(email: text)` — Get User by Email
- `get_user_cyware_index(email: text)` — Get User Cyware Index
- `get_user_keywords(email: text)` — Get User Personalized Keywords
- `list_incident_reported(start_time: datetime, end_time: datetime, [pagesize: integer])` — List Reported Incidents
- `list_incident_type()` — List Incident Types
- `list_info_source()` — Get Info Source
- `list_intel_reported([pagesize: integer])` — List Reported Intel
- `list_severity()` — List Severity
- `list_threat_method()` — List Threat Methods
- `list_users()` — List Users
- `report_incident(title: text, description: text, attachments: text, [incident_type: multiselect], [threat_methods: multiselect], [severity: select])` — Report an Incident


### `cyware-ctix-feed` v1.0.0 _(installed, ingestion)_
_Cyware CTIX Feed_

An automated Threat Intelligence Platform (TIP) for ingestion, enrichment, analysis, prioritization, actioning, and bidirectional sharing of threat data.

**2 operation(s)**:

_investigation_
- `get_save_result_set_data([label_name: text], [from_timestamp: datetime], [to_timestamp: datetime], page_size: integer, page: integer)` — Get Save Result Set Data
- `get_save_result_set_indicators([label_name: text], [from_timestamp: datetime], [to_timestamp: datetime], record_number: select)` — Get Save Result Set Indicators


---

## Threat Protection

### `microsoft-defender-office-365` v1.1.0 _(installed, ingestion)_
_Microsoft Defender For Office 365_

Microsoft Defender for Office 365 safeguards your organization against malicious threats posed by email messages, links (URLs), and collaboration tools. This connector facilitates automated operations related to alerts.

**3 operation(s)**:

_investigation_
- `get_alert(id: text)` — Get Alert
- `list_alerts([status: select], [severity: select], [classification: select], [determination: select], [start_date: datetime], [query: text], [$top: integer], [$skip: text])` — List Alerts
- `update_alert(id: text, [status: select], [classification: select], [determination: select], [assignedTo: text])` — Update Alert


### `symantec-edr` v2.0.0 _(installed, ingestion)_
_Symantec EDR_

Symantec Endpoint Detection and Response(EDR) performs the critical security tasks that detect, protect and respond to threats to your network.

**32 operation(s)**:

_Containment_
- `isolate_endpoint(targets: text)` — Isolate Endpoint

_containment_
- `add_incident_comment(incident_uuid: text, comment: text)` — Add Comment to Incident
- `close_incident(incident_uuid: text)` — Close Incident

_investigation_
- `cancel_command(command_id: text)` — Cancel Command
- `command_result(command_id: text, [query: text], [limit: integer], [next: text])` — Get Command Result
- `create_blacklist_policies(type: select, target_value: text, [comment: text])` — Create Blacklist Policy
- `delete_blacklist_policy(policy_id: text)` — Delete Blacklist Policy
- `endpoint_eoc_search(device_uuids: text, device_hostname: text, sepm_group: text, ipv4_address: text, query: text)` — Search EOC on Endpoint
- `endpoint_recorder_search(device_uuids: text, device_hostname: text, sepm_group: text, ipv4_address: text, [start_time: datetime], [end_time: datetime], query: text)` — Search Artifact on Endpoint
- `execute_sandbox_commands(sha256: text)` — Execute Sandbox Commands
- `get_appliance_information()` — Get Appliance Information
- `get_blacklist_policies([type: select], [value: text], [limit: integer], [next: text])` — Get Blacklist Policies
- `get_command_status(command_id: text, [limit: integer], [next: text])` — Get Command State
- `get_domain_entities([limit: integer], [next: text])` — Get Domain Entities
- `get_domain_instance([limit: integer], [next: text])` — Get Domain Instances
- `get_domain_instance_by_domain_name(domain_name: text, [limit: integer], [next: text])` — Get Domain Instance by Domain Name
- `get_endpoint_entities([limit: integer], [next: text])` — Get Endpoint Entities
- `get_endpoint_instances([limit: integer], [next: text])` — Get Endpoint Instances
- `get_entities([limit: integer], [next: text])` — Get Entities
- `get_events([start_time: datetime], [end_time: datetime], [query: text], [limit: integer], [next: text])` — Get Events
- `get_file_entities([query: text], [limit: integer], [next: text])` — Get File Entities
- `get_file_entity_by_sha2(sha2: text, [limit: integer], [next: text])` — Get File Entity by SHA256
- `get_file_from_endpoint(hash: text, device_uid: text)` — Get File from Endpoint
- `get_file_instances([query: text], [limit: integer], [next: text])` — Get File Instances
- `get_incident_comment(incident_uuid: text)` — Get Incident Comments
- `get_incidentevents([start_time: datetime], [end_time: datetime], [incident_uuid: text], [query: text], [limit: integer], [next: text])` — Get Incident Related Events
- `get_incidents([start_time: datetime], [end_time: datetime], [query: text], [limit: integer], [next: text])` — Get Incidents
- `get_sandbox_command_status(sandbox_cmd_id: text)` — Get Sandbox Commands Status
- `get_specific_endpoint_instances(uuid: text, [limit: integer], [next: text])` — Get Specific Endpoint Instances
- `rejoin_endpoint(targets: text)` — Rejoin Endpoint
- `update_blacklist_policy_comment(policy_id: text, [comment: text])` — Update Blacklist Policy Comment

_remediation_
- `delete_endpoint_file(hash: text, device_uid: text)` — Delete File from Endpoint


---

## Threat Response

### `proofpoint-threat-response` v1.0.0 _(installed)_
_Proofpoint Threat Response_

Proofpoint Threat Response is a solution designed to help organizations manage and respond to cybersecurity threats. It provides tools and features to identify, investigate, and remediate security incidents.

**16 operation(s)**:

_containment_
- `block_domain(indicator: text, list_id: text, [expiration: datetime])` — Block Domain
- `block_hash(indicator: text, list_id: text, [expiration: datetime])` — Block File Hash
- `block_ip(indicator: text, list_id: text, [expiration: datetime])` — Block IP Addresses
- `block_url(indicator: text, list_id: text, [expiration: datetime])` — Block URL

_investigation_
- `add_comment_to_incident(incident_id: text, comment: text, [description: text])` — Add Comment To Incident
- `add_to_list(list_id: text, indicator: text, [description: text], [expiration: datetime])` — Add Indicators
- `add_user_to_incident(incident_id: text, targets: text, attackers: text)` — Add User To Incident
- `close_incident(incident_id: text, comment: text, description: text)` — Close Incident
- `delete_indicator(list_id: text, indicator_id: text)` — Delete Indicator
- `get_incident(incident_id: text, expand_events: checkbox)` — Get Incident By ID
- `get_incidents([state: select], [created_after: datetime], [created_before: datetime], [closed_after: datetime], [closed_before: datetime], [expand_events: checkbox], [limit: text])` — Get Incidents List
- `get_list(list_id: text)` — Get Indicators List
- `ingest_alert(json_version: text, [post_url_id: text], [attacker: json], [classification: select], [cnc_hosts: json], [detector: json], [email: json], [forensics_hosts: json], [link_attribute: select], [severity: select], [summary: text], [target: json], [threat_info: json], [custom_fields: json])` — Ingest Alert
- `search_indicator([filter: text], list_id: text)` — Search Indicator
- `update_comment_to_incident(incident_id: text, [comment: text], [description: text])` — Update Comment To Incident
- `verify_quarantine(message_id: text, time: text, recipient: text)` — Verify Quarantine


---

## ThreatHunt

### `threatcrowd` v1.0.0 _(installed)_
_ThreatCrowd_

ThreatCrowd is a system for finding and researching artifacts relating to Cyber Threats. Provide actions like hunt IP, Email, MD5 and Hostname in ThreatCrowd system.

**4 operation(s)**:

_investigation_
- `hunt_domain(domain: text)` — Hunt Domain
- `hunt_email(email: text)` — Hunt Email Address
- `hunt_file(hash: text)` — Hunt MD5
- `hunt_ip(ip: text)` — Hunt IP


---

## ThreatIntel

### `emailrep` v1.0.0 _(installed)_
_EmailRep_

EmailRep is an API service provided by Sublime Security. EmailRep uses hundreds of data points from social media profiles, professional networking sites, dark web credential leaks, data breaches, phishing kits, phishing emails, spam lists, open mail relays, domain age and reputation, deliverability, and more to predict the risk of an email address.

**1 operation(s)**:

_investigation_
- `email_reputation(emailaddress: text, [summary: checkbox])` — Get Email Address Reputation


### `feodotracker` v1.0.0 _(installed, ingestion)_
_FeodoTracker_

Feodo Tracker is a project of abuse.ch with the goal of sharing botnet C&C servers associated with the Feodo malware family (Dridex, Emotet/Heodo). It offers various blocklists, helping network owners to protect their users from Dridex and Emotet/Heodo.

**1 operation(s)**:

_investigate_
- `get_blocklist_feed()` — Get IPv4 Feeds


### `malsilo` v2.0.1 _(installed, ingestion)_
_MalSilo_

Ingest Threat Intel Feeds from MalSilo Gitlab. <br/><br/>This connector has a dependency on the <a href="/content-hub/all-content/?contentType=solutionpack&amp;tag=ThreatIntelManagement" target="_blank" rel="noopener">Threat Intel Management Solution Pack</a>. Install the Solution Pack before enabling ingestion of Threat Feeds from this source.

**3 operation(s)**:

_get_feed_
- `get_domain_feed([last_pull_time: text])` — Get Domain Feeds
- `get_ipv4_feed([last_pull_time: text])` — Get IPv4 Feeds
- `get_url_feed([last_pull_time: text])` — Get URL Feeds


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


### `microfocus_smax` v1.0.0 _(installed)_
_Micro Focus SMAX_

Micro Focus SMAX connector is used for fetch SMAX incidents, requests and automate different SMAX case management actions.

**8 operation(s)**:

_investigation_
- `create_entities(entities: json)` — Create Entities
- `create_incident(incident_name: text, incident_description: text, impacted_service_id: text, [requested_by_user_id: text], [incident_urgency: select], [impact_scope: select], [service_desk_group_id: text], [other_properties: json])` — Create Incident
- `create_request(request_name: text, request_description: text, requested_for_user_id: text, [requested_by_user_id: text], [request_urgency: select], [impact_scope: select], [other_properties: json])` — Create Request
- `get_entity_details(entity_type: text, entity_id: text, [entity_fields: text])` — Get Entity Details
- `query_entities(entity_type: text, [entity_fields: text], [query_filter: text], [order_by: text], [size: text], [skip: text])` — Query Entities
- `update_entities(entities: json)` — Update Entities
- `update_incident(incident_id: text, incident_description: text, [incident_urgency: select], [impact_scope: select], incident_status: select, incident_closure_category_id: text, [incident_completion_code: text], [incident_solution: text], [other_properties: json])` — Update Incident
- `update_request(request_id: text, request_description: text, [request_urgency: select], [impact_scope: select], request_status: select, [other_properties: json])` — Update Request


### `zendesk` v2.0.0 _(installed)_
_Zendesk_

This connector provides an automated way to create, read, update, mark spam, restore and delete tickets in Zendesk.

**12 operation(s)**:

_investigation_
- `delete_bulk_tickets(ids: text)` — Delete Bulk Tickets
- `delete_bulk_tickets_permanently(ids: text)` — Delete Bulk Of Tickets Permanently
- `ticket_create([id: text], [subject: text], comment: text, [priority: select], [type: select], [tags: text])` — Create Ticket
- `ticket_delete(id: text)` — Delete Ticket
- `ticket_deleted_list(count: text, [sort_by: select], [sort_order: select])` — Get Deleted Ticket List
- `ticket_deleted_permanently(id: text)` — Delete Ticket Permanently
- `ticket_deleted_restore(id: text)` — Restore Ticket
- `ticket_details(id: text)` — Get Ticket Details
- `ticket_list(count: text, [sort_by: select], [sort_order: select])` — Get Ticket List
- `ticket_mark_spam(id: text)` — Mark Ticket as Spam
- `ticket_related_details(id: text)` — Get Ticket Related Details
- `ticket_update(id: text, [assignee_id: text], [comment: text], [priority: select], [type: select], [tags: text])` — Update Ticket


---

## Ticket Management

### `alloy-itsm` v1.0.0 _(installed)_
_Alloy ITSM_

Alloy ITSM is an IT Service Management (ITSM) solution designed to help organizations manage and streamline their IT services and operations. This connector is designed to manage and automate ticket-based operations.

**17 operation(s)**:

_investigation_
- `add_attachments(oid: text, path: select)` — Add Attachments
- `check_step_action_availability(oid: text, action_id: integer)` — Check Step Action Availability
- `create_object(action_id: integer, [summary: text], [description: textarea], [category: text], [requester: text], [urgency: select], [impact: select], [fields: json])` — Create Object
- `download_attachment(oid: text, attachment_id: text, [attachment_name: text], [attachment_description: text], [skip_fortisoar_upload: checkbox])` — Download Attachment
- `get_attachment_content(oid: text, attachment_id: text)` — Get Attachment Content
- `get_classification_values(par_objectClass: text, par_refField: text, [filters: json], [par_fields: text], [sort_by: select], [par_limit: integer], [par_offset: integer])` — Get Classification Values
- `get_classification_values_advanced(objectClass: text, refField: text, [fields: text], [filters: json], [sort: json], [limit: integer], [offset: integer])` — Advanced Search for Classification Values
- `get_current_user_profile()` — Get Current User Profile
- `get_object_activities(oid: text, [par_fields: text], [filters: json], [sort_by: select], [par_limit: integer], [par_offset: integer])` — Get Object Activities
- `get_object_activities_advanced(oid: text, [fields: text], [filters: json], [sort: json], [limit: integer], [offset: integer])` — Advanced Search for Object Activities
- `get_object_by_id(oid: text)` — Get Object By ID
- `get_objects(object_class: text, [par_fields: text], [par_search_text: text], [filters: json], [sort_by: select], [par_limit: integer], [par_offset: integer])` — Get Objects
- `get_objects_advanced(object_class: text, [fields: text], [filters: json], [searchText: text], [sort: json], [limit: integer], [offset: integer])` — Get Objects Advanced Search
- `list_object_attachments(oid: text, [par_fields: text], [filters: json], [sort_by: select], [par_limit: integer], [par_offset: integer])` — List Object Attachments
- `remove_attachment(oid: text, attachment_id: text)` — Remove Attachment
- `run_step_action(oid: text, action_id: integer, [summary: text], [description: textarea], [category: text], [requester: text], [urgency: select], [impact: select], [fields: json])` — Update Object
- `update_attachment_description(oid: text, attachment_id: text, description: text)` — Update Attachment Description


### `fresh-service-desk-msp` v1.1.0 _(installed)_
_Fresh Service Desk MSP_

Fresh Service Desk MSP is a cloud-based service desk and IT service management (ITSM) platform designed to streamline service management for businesses. It offers a range of features including incident management, problem management, change management, asset management, and more. Freshservice provides a user-friendly interface for managing service requests, automating workflows, tracking assets, and generating reports. Its multi-tenant architecture ensures data segregation and security for different clients. The connector for Freshservice enables automated actions such as creating, updating, deleting, and closing tickets, enhancing the efficiency of service delivery for managed service providers.

**6 operation(s)**:

_investigation_
- `create_ticket(subject: text, email: email, [cc_emails: text], status: select, priorities: select, description: textarea)` — Create Ticket
- `delete_ticket_by_id(ticket_id: text)` — Delete Ticket By ID
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `filter_tickets_by_query(query: text)` — Filter Tickets By Query
- `get_ticket_by_id(ticket_id: text)` — Get Ticket By ID
- `update_ticket(ticket_id: text, [subject: text], [description: textarea], [email: email], [status: select], [priorities: select], [path: select])` — Update Ticket


### `hubspot` v1.0.0 _(installed)_
_HubSpot_

HubSpot is a CRM platform with all the software, integrations, and resources you need to connect marketing, sales, content management, and customer service. This integration is used to get, create, update or delete a ticket.

**8 operation(s)**:

_investigation_
- `create_tickets(create: select)` — Create Tickets
- `delete_tickets(ticket_ids: text)` — Delete Tickets
- `get_all_tickets([properties: text], [propertiesWithHistory: text], [offset: integer])` — Get All Tickets
- `get_owners_list()` — Get Owners List
- `get_ticket_pipelines()` — Get Ticket Pipelines
- `get_tickets_by_id(ticket_ids: text, [properties: text], [propertiesWithHistory: text], [includeDeletes: checkbox])` — Get Tickets By ID
- `get_tickets_changes_log([timestamp: text], [change_type: text], [object_id: integer])` — Get Tickets Changes Log
- `update_tickets(update: select)` — Update Tickets


### `jira-insight-db` v1.1.0 _(installed)_
_Jira Insight DB_

Jira Insight gives teams a simple and quick way to tie assets and configuration items to service requests, incidents, problems, changes, and other issues to gain valuable context.

**8 operation(s)**:

_investigation_
- `create_object([objectTypeId: text], [objectTypeAttributeId: text], [object_attribute_value: text], [other_fields: json])` — Create Object
- `get_asset_attributes(asset_id: text)` — Get Asset Attributes
- `get_asset_connected_tickets(asset_id: text)` — Get Asset Connected Tickets
- `get_asset_details(asset_id: text)` — Get Asset Details
- `get_asset_history(asset_id: text, [asc: checkbox], [abbreviate: checkbox])` — Get Asset History
- `get_asset_reference_info(asset_id: text)` — Get Asset Reference Information
- `get_assets([iql: text], [page: integer], [resultPerPage: integer], [includeAttributes: checkbox], [includeAttributesDeep: integer], [includeTypeAttributes: checkbox], [includeExtendedInfo: checkbox])` — Get Assets List
- `update_object([object_id: text], [objectTypeId: text], [objectTypeAttributeId: text], [object_attribute_value: text], [other_fields: json])` — Update Object


### `manage-engine-service-desk-plus` v3.0.0 _(installed)_
_ManageEngine ServiceDesk Plus_

ManageEngine ServiceDesk Plus is used in turning IT teams from daily fire-fighting to delivering awesome customer service. It provides great visibility and central control in dealing with IT issues to ensure that businesses suffer no downtime. This connector provides automated actions to create, update, delete and close tickets

**10 operation(s)**:

_investigation_
- `add_note(request_id: text, description: text, [show_to_requester: checkbox], [mark_first_response: checkbox], [add_to_linked_requests: checkbox], [notify_technician: checkbox])` — Add Note
- `add_request(subject: text, [description: text], [request_type: text], [status: select], [priority: select], [urgency: select], [group: text], requester: json, [other_fields: json])` — Create Ticket
- `add_resolution(request_id: text, resolution: text)` — Add Resolution
- `close_request(request_id: text, is_fcr: checkbox, requester_ack_resolution: checkbox, [requester_ack_comments: text], [closure_code: select], [closure_comments: text])` — Close Ticket
- `delete_request(request_id: text)` — Delete Ticket
- `delete_request_from_trash(request_id: text)` — Delete Ticket From Trash
- `get_all_open_requests([id: text], [subject: text], [priority.name: select], [requester.name: text], [other_fields: json], [sort_field: text], [sort_order: select], [from: text], [limit: text])` — Get All Open Tickets
- `get_all_requester([id: text], [name: text], [employee_id: text], [email_id: text], [type: select], [other_fields: json], [fields_required: text], [sort_field: text], [sort_order: select], [start_index: integer], [size: integer])` — Get All Requesters
- `get_request(request_id: text)` — Get Ticket Details
- `update_request(request_id: text, [subject: text], [description: text], [status: select], [urgency: select], [priority: select], [other_fields: json])` — Update Ticket


### `manage-engine-service-desk-plus-msp` v1.0.0 _(installed)_
_ManageEngine ServiceDesk Plus MSP_

ServiceDesk Plus MSP is a web based, full-fledged ITSM suite designed specifically for managed service providers. This all-in-one ITSM solution delivers comprehensive help desk, service desk, account management, asset management, remote controls and advanced reporting in a multi-tenant architecture with robust data segregation. It empowers service providers to offer services and support to multiple clients with centralized controls.This connector provides automated actions to create, update, delete and close tickets

**16 operation(s)** (+4 hidden):

_investigation_
- `add_note(request_id: text, description: text, [show_to_requester: checkbox], [mark_first_response: checkbox], [add_to_linked_requests: checkbox], [notify_technician: checkbox])` — Add Note
- `add_request(subject: text, requester: json, [description: text], [request_type: text], [status: select], [priority: select], [urgency: select], [group: text], [site: json], [account: json], [other_fields: json])` — Create Ticket
- `add_resolution(request_id: text, resolution: text)` — Add Resolution
- `close_request(request_id: text, is_fcr: checkbox, requester_ack_resolution: checkbox, [requester_ack_comments: text], [closure_code: select], [closure_comments: text])` — Close Ticket
- `delete_request(request_id: text)` — Delete Ticket
- `delete_request_from_trash(request_id: text)` — Delete Ticket From Trash
- `get_all_accounts()` — Get All Accounts
- `get_all_requests([id: text], [subject: text], [status.name: select], [priority.name: select], [requester.name: text], [other_fields: json], [filter_by: json], [sort_field: text], [sort_order: select], [from: integer], [size: integer])` — Get All Tickets
- `get_all_sites([from: integer], [size: integer])` — Get All Sites
- `get_all_user([id: text], [name: text], [employee_id: text], [email_id: text], [type: select], [other_fields: json], [fields_required: text], [sort_field: text], [sort_order: select], [start_index: integer], [size: integer])` — Get All Users
- `get_request(request_id: text)` — Get Ticket Details
- `update_request(request_id: text, [subject: text], [description: text], [status: select], [urgency: select], [priority: select], [site: json], [other_fields: json])` — Update Ticket


---

## Ticketing

### `connectwise-manage` v2.1.1 _(installed)_
_ConnectWise Manage_

ConnectWise has a CRM, ticketing system, help desk, and tools for project management, billing, and procurement.

**7 operation(s)**:

_investigation_
- `create_service_note(ticket_id: integer, [text: textarea], [dateCreated: datetime], [createdBy: text], [all_fields: json])` — Create Service Note
- `create_ticket(summary: textarea, [impact: text], [recordType: select], [severity: text], [board: select], [identifier: text], [all_fields: json])` — Create Ticket
- `get_boards()` — Get Boards
- `get_companies([identifier: text], [conditions: text], [fields: text], [pagesize: integer], [page: integer], [all_fields: json])` — Get Companies
- `get_ticket([ticket_id: integer], [conditions: text], [order_by: text], [page: integer], [pagesize: integer])` — Get Ticket
- `update_ticket(ticket_id: integer, [op: select], [summary: textarea], [severity: text], [impact: text], [all_fields: json])` — Update Ticket

_remediation_
- `delete_ticket(ticket_id: integer)` — Delete Ticket


### `request-tracker` v2.1.0 _(installed)_
_Request Tracker_

Provide ticket management on Request Tracker by implementing actions such as create ticket, search ticket and update ticket

**15 operation(s)**:

_investigation_
- `comment_ticket(ticket_id: text, comment_text: text)` — Comment Ticket
- `create_queue(Name: text, SubjectTag: text, Description: text, [customfields: json])` — Create Queue
- `create_ticket(queue_id: text, Subject: text, From: email, To: email, Content: text, [customfields: json])` — Create Ticket
- `delete_queue(queue_id: text)` — Delete Queue
- `delete_ticket(ticket_id: text)` — Delete Ticket
- `get_attachment_details(ticket_id: text, attachment_id: text, [attachments: checkbox])` — Get Attachment Details
- `get_queue_info(queue_id: text)` — Get Queue Properties
- `get_record_history([record_type: select], id: text, [page_size: integer], [page_num: integer])` — Get Ticket/Queue History
- `get_ticket_info(ticket_id: text, [transactions: checkbox], [attachments: checkbox])` — Get Ticket Properties
- `get_transaction_attachments(transaction_id: text, [page_size: integer], [page_num: integer])` — Get Transaction Attachments
- `get_transaction_details(transaction_id: text)` — Get Transaction Details
- `list_queue([page_size: integer], [page_num: integer])` — List Queue
- `search_ticket(query: text, [page_size: integer], [page_num: integer])` — Search Ticket
- `update_queue(queue_id: text, SubjectTag: text, [Description: text], [customfields: json])` — Update Queue
- `update_ticket(ticket_id: text, Content: text, [Subject: text], [From: email], [To: email], [customfields: json])` — Update Ticket


### `rsa-archer` v2.0.0 _(installed)_
_RSA Archer_

RSA Archer connector provide automated operations for Audit Management, Issue Management, Operational Risk Management.

**11 operation(s)**:

_investigation_
- `create_record(module_id: text, field_values: text)` — Create Record
- `get_all_groups([attachment: checkbox])` — Get All Groups Details
- `get_all_modules([attachment: checkbox])` — Get Details For All Modules
- `get_all_users([attachment: checkbox])` — Get All Users Details
- `get_fields_ids(module_id: text, [attachment: checkbox])` — Get Fields Details of Module
- `get_record_by_id(record_id: text)` — Get Record
- `get_records_by_report(report_id: text, [page_no: text])` — Get Records By Report
- `get_reports([attachment: checkbox])` — Get Details For All Reports
- `get_reports_by_module_id(module_id: text)` — Get Reports Details of Module
- `get_values_list_value(value_list_id: text)` — Get Values List Item
- `update_record(module_id: text, record_id: text, field_values: text)` — Update Record


### `salesforce` v1.0.1 _(installed)_
_Salesforce_

Salesforce connector provides actions like, create record, update record, get details of salesforce objects/records, run SOQL query etc.

**8 operation(s)** (+1 hidden):

_investigation_
- `create_record(object_name: select, json_fields: json)` — Create Record
- `get_record_details(object_name: select, [object_id: text])` — Get Salesforce Object Record Details
- `list_objects(object_name: select, [list_view_name: text])` — List Objects
- `run_query(query: text, query_type: select)` — Run Query
- `update_record(object_name: select, object_id: text, json_fields: json)` — Update Record

_remediation_
- `delete_record(object_name: select, object_id: text)` — Delete Record

- `get_object_fields(object_name: select)` — Get Salesforce Object Fields


---

## Ticketing System

### `foresight` v1.1.0 _(installed)_
_Foresight_

Foresight connector performs actions like create, update, search, close, cancel and add comment to ticket.

**12 operation(s)**:

_investigation_
- `comment_ticket(ticketId: text, requestingSystem: text, comment: text)` — Add Comment
- `create_ticket(name: text, type: text, category: text, subCategory: text, severity: text, priority: text, [description: text], domain: text, subDomain: text, assigneeType: select, eventDate: datetime, serviceType: text, requestingSystem: text, [externalLink: text])` — Create Ticket
- `get_comment_ticket(ticketId: text)` — Get Comment
- `search_ticket([ticketId: text], [name: text], [type: text], [category: text], [subCategory: text], [severity: text], [status: text], [modifiedTime: datetime], [pagination : checkbox])` — Search Ticket
- `ticket_action_acquire(ticketId: text, requestingSystem: text, userEmail: text)` — Acquire Ticket
- `ticket_action_cancel(ticketId: text, verificationNote: text, requestingSystem: text)` — Cancel Ticket
- `ticket_action_close(ticketId: text, requestingSystem: text, verificationNote: text)` — Close Ticket
- `ticket_action_negotiate(ticketId: text, requestingSystem: text, negotiateReason: text, negotiateType: select)` — Negotiate Ticket
- `ticket_action_reassign(ticketId: text, requestingSystem: text, userEmail: text, reassignRemark: text)` — Reassign Ticket
- `ticket_action_resolved(ticketId: text, requestingSystem: text, cause: text, resolution: text, causeOfAlarm: text, resolutionDetails: text, solutionType: text, solutionDetails: text)` — Resolved Ticket
- `ticket_action_start(ticketId: text, requestingSystem: text)` — Start Ticket
- `update_ticket(ticketId: text, severity: text, priority: text, requestingSystem: text, eventDate: datetime, [description: text], [externalLink: text])` — Update Ticket


---

## Translator

### `ibm-watson` v1.0.0 _(installed)_
_IBM Watson_

IBM Watson - language translator

**4 operation(s)**:

_investigation_
- `get_language(text: text)` — Get Language
- `list_languages()` — List Languages
- `list_translations()` — List Translations
- `translate_text(text: text, source_language: text, target_language: text)` — Translate Text


---

## UEBA

### `micro-focus-interset` v1.0.0 _(installed, ingestion)_
_Micro Focus Interset_

Interset is powerful investigation and hunting interface. This connector can be use to get entity related information, risky user details, get or delete workflows etc

**26 operation(s)**:

_investigation_
- `add_tag_to_elements(tag: text, tagElementType: select, entityHash: text, [retries: integer])` — Add Tag To Elements
- `create_tag(tag_name: text, [tag_desc: text])` — Create Tag
- `delete_rule()` — Delete Rule
- `delete_tag(tag: text)` — Delete Tag
- `get_anomalies_alerts_aggregates(rollupLevel: select, [rollupId: text], [count: integer], [sort: select], [sortOrder: select], [risksort: select], [minRisk: integer], [maxRisk: integer], [q: text], [markup: checkbox], [scrollId: text], [keepAlive: text], [ts: datetime], [te: datetime])` — Get Anomalies/Alerts/Aggregates
- `get_anomaly_weights([for_who: select])` — Get Anomaly Weights
- `get_associated_entities(entityType: select, entityHash: text, [count: integer], [riskSort: select], [ts: datetime], [te: datetime])` — Get Associated Entities
- `get_authentication_attempts([q: text], [ts: datetime], [te: datetime])` — Get Authentication Attempts
- `get_bot_users([count: integer])` — Get Bot Users
- `get_context(rollupLevel: select, rollupId: text)` — Get Context
- `get_entities(entityType: select, [count: integer], [sortOrder: select], [scrollId: text], [keepAlive: text])` — Get Entities
- `get_entities_by_tags(entities_for: select, [count: integer], [scrollId: text])` — Get Entities By Tags
- `get_entity_details(entityType: select, entityHash: text)` — Get Entity Details
- `get_entity_risk_distribution(entityType: select, [q: text], [ts: datetime], [te: datetime])` — Get Entity Risk Distribution
- `get_entity_risk_graph(entityType: select, entityHash: text, [count: integer], [interval: text], [tz: text], [ts: datetime], [te: datetime])` — Get Entity Risk Graph
- `get_entity_risk_score(entityType: select, entityHash: text, [sort: select], [format: text], [markup: checkbox], [tz: text], [ts: datetime], [te: datetime])` — Get Entity Risk Score
- `get_raw_events([q: text], [category: select], [count: integer], [tz: text], [ts: datetime], [te: datetime], [response_format: select])` — Get Raw Events
- `get_session_info()` — Get Session
- `get_tags([source: select], [q: text], [typeahead: text])` — Get Tags
- `get_top_accessed_entities_by_entitytype(entityType: select, [count: integer], [q: text], [ts: datetime], [te: datetime])` — Get Top Accessed Entities
- `get_top_risky_entities_by_entitytype(entityType: select, [sort: select], [format: text], [q: text], [markup: checkbox], [tz: text], [count: integer], [scrollId: text], [keepAlive: text], [ts: datetime], [te: datetime])` — Get Top Risky Entities
- `get_workflows()` — Get Rules
- `get_working_hours(for_who: select)` — Get Working Hours
- `remove_tag_from_elements(tag: text, tagElementType: select, entityHash: text, [retries: integer])` — Remove Tag From Elements
- `search_users(search_for: select, [count: text], [q: text], [ts: datetime], [te: datetime])` — Search Users
- `set_anomaly_weight(did: integer, anomalyType: integer, weight: text)` — Set Anomaly Weight


---

## Uncategorized

### `aiassistant-utils` v4.0.1 _(installed)_

**15 operation(s)** (+6 hidden):

_investigation_
- `clear_assistant_data(genai_type: select)` — Clear Assistant Data
- `clear_conversation([genai_type: select], [genai_arguments: json])` — Clear Conversation
- `configure_assistant([genai_type: select], [genai_arguments: json])` — Configure Assistant
- `generate_playbook_steps([genai_type: select], [genai_arguments: json])` — Generate Playbook steps
- `get_llm_response([genai_type: select], [genai_arguments: json])` — Get LLM Response
- `get_past_conversation([genai_type: select], [genai_arguments: json])` — Get Past Conversation
- `get_similar_documents(task: text, task_type: select, n_results: integer, document_threshold: decimal)` — Find Similar Documents
- `refresh_collection(export_file_iri: text)` — Refresh Training Data

_utilities_
- `generate_playbook_block(flowchart_json: json)` — Utility to connect steps into a Playbook Block


### `bpmn-to-playbooks` v1.0.3 _(installed)_
_BPMN_

Convert BPMN XML to FortiSoar Playbooks

**1 operation(s)**:

- `bpmntoplaybooks(bpmnOutput: textarea, bpmnTool: select, bpmnFormat: select)` — Import BPMN Playbook


### `crits` v1.0.0 _(installed)_
_CRITs_

Collaborative Research Into Threats (CRITs) is an open source malware and threat repository

**4 operation(s)**:

_investigation_
- `create_resource(resource_type: select, source: text, [confidence: select], [payload: text])` — Create Resource
- `get_resource(resource_id: text, resource_type: select)` — Get Resource Details
- `run_query([resource_type: select], [query: text], [limit: integer], [offset: integer], [next_page: text])` — Run Query
- `update_resource(resource_id: text, resource_type: select, payload: text)` — Update Resource


### `csv-data-management` v1.2.0 _(installed)_
_CSV Data Management_

CSV Data management can perform different operations on CSV files like read file, perform deduplication, merge two CSV files, join two CSV files, concat two CSV files and return well formatted dataset

**5 operation(s)**:

_investigation_
- `concat_two_csv_and_extract_data(input: select, file_one_value: text, [file1_column_names: text], [numberOfRowsToSkipFirst: integer], input: select, file_two_value: text, [file2_column_names: text], [numberOfRowsToSkipSecond: integer], [deDupValuesOn: text], [filterInput: select], [recordBatch: checkbox], [saveAsAttachment: checkbox])` — Concat and Extract Data from two CSV
- `convert_json_to_csv_file(input: select)` — Convert JSON to CSV File
- `extract_data_from_csv(input: select, value: text, [columnNames: text], [deDupValuesOn: text], [numberOfRowsToSkip: integer], [filterInput: select], [recordBatch: checkbox], [saveAsAttachment: checkbox])` — Extract Data from Single CSV
- `join_two_csv_and_extract_data(input: select, file_one_value: text, [file1_column_names: text], [numberOfRowsToSkipFirst: integer], input: select, file_two_value: text, [file2_column_names: text], [numberOfRowsToSkipSecond: integer], [deDupValuesOn: text], [filterInput: select], [recordBatch: checkbox], [saveAsAttachment: checkbox])` — Join and Extract Data from two CSV
- `merge_two_csv_and_extract_data(input: select, file_one_value: text, [file1_column_names: text], [numberOfRowsToSkipFirst: integer], input: select, file_two_value: text, [file2_column_names: text], [numberOfRowsToSkipSecond: integer], mergeColumnNames: text, [deDupValuesOn: text], [filterInput: select], [recordBatch: checkbox], [saveAsAttachment: checkbox])` — Merge and Extract Data from two CSV


### `sophos-utm-9` v1.0.0 _(installed)_
_Sophos UTM_

Sophos UTM - 9 Firewall

**10 operation(s)**:

_containment_
- `block_applications(app_list: text)` — Block Applications
- `block_ips(ip_addresses: text)` — Block IP Addresses
- `block_urls(url_list: text)` — Block URLs

_investigation_
- `check_policies()` — Check Policies
- `get_blocked_application_names()` — Get Blocked Application Names
- `get_blocked_ips()` — Get Blocked IPs
- `get_blocked_urls()` — Get Blocked URLs

_remediation_
- `unblock_applications(app_list: text)` — Unblock Applications
- `unblock_ips(ip_addresses: text)` — Unblock IP Addresses
- `unblock_urls(url_list: text)` — Unblock URLs


### `verodin` v1.0.0 _(installed)_
_Verodin_

Verodin’s Instrumented Security platform is a foundational technology. It is a new approach to managing your cyber-security lifecycle

**12 operation(s)**:

_investigation_
- `cancel_job(job_id: integer)` — Cancel Job
- `delete_simulation(sim_id: integer)` — Delete Simulation
- `delete_zone(zone_id: integer)` — Delete Zone
- `get_job([job_id: integer])` — Get Job
- `get_job_actions(job_id: integer)` — Get Job Actions
- `get_map()` — Get Map
- `get_nodes()` — Get Nodes
- `get_simulation([sim_id: integer], [sim_type: text])` — Get Simulation
- `get_simulations_actions()` — Get Simulations Actions
- `get_zone([zone_id: integer])` — Get Zone
- `run_job(job_id: integer)` — Run Job
- `run_simulation(sim_id: integer)` — Run Simulation


---

## Utilities

### `atlassian-confluence-cloud` v1.0.0 _(installed)_
_Atlassian Confluence Cloud_

Atlassian Confluence is a collaborative workspace where teams create, organize, and share project documents, ideas, and knowledge in one central place.

**13 operation(s)**:

_investigation_
- `create_custom_content(type: text, title: text, representation: select, value: text, [status: select], [spaceId: text], [pageId: text], [blogPostId: text], [customContentId: text])` — Create Custom Content
- `create_footer_comment([blogPostId: text], [pageId: text], [parentCommentId: text], [attachmentId: text], [customContentId: text], representation: text, value: text)` — Create Footer Comment
- `create_space(name: text, [alias: text], [key: text], [representation: text], [value: text], [roleAssignments: json], [copySpaceAccessConfiguration: text], [createPrivateSpace: checkbox], [templateKey: text])` — Create Space
- `delete_custom_content(id: integer, [purge: checkbox])` — Delete Custom Content
- `get_attachments([sort: text], [cursor: text], [status: text], [mediaType: text], [filename: text], [limit: text])` — Get Attachments
- `get_audit_records([startDate: datetime], [endDate: datetime], [searchString: text], [start: text], [limit: text])` — Get Audit Records
- `get_custom_contents(type: text, [id: text], [space-id: text], [body-format: text], [sort: text], [cursor: text], [limit: integer])` — Get Custom Contents
- `get_groups([start: text], [limit: text], [accessType: select])` — Get Groups
- `get_spaces([ids: text], [keys: text], [type: select], [status: select], [labels: text], [favorited-by: text], [not-favorited-by: text], [sort: text], [description-format: select], [include-icon: checkbox], [limit: integer])` — Get Spaces
- `get_specific_custom_content(id: text, [version: integer], [body-format: select], [include-labels: checkbox], [include-properties: checkbox], [include-operations: checkbox], [include-version: text], [include-collaborators: checkbox])` — Get Specific Custom Content
- `get_specific_space_details([id: text], [description-format: select], [include-icon: checkbox], [include-operations: checkbox], [include-properties: checkbox], [include-permissions: checkbox], [include-role-assignments: checkbox], [include-labels: checkbox])` — Get Specific Spaces Details
- `get_users(accountId: text, [expand: mutiselect])` — Get Users
- `update_custom_content([id : text], type: text, [title: text], [status: select], representation: select, value: text, [number: text], [message: text], [spaceId: text], [pageId: text], [blogPostId: text], [customContentId: text])` — Update Custom Content


### `cicd-utils` v1.2.0 _(installed)_
_CICD Utils_

CICD Utils provides out of the box actions for CICD solution pack

**5 operation(s)**:

_utilities_
- `export_fortisoar_template(export_template_name: text, export_file_name: text, [ignore_keys: json])` — Export FortiSOAR Template
- `import_fortisoar_template(filename: text, file_path: text)` — Import FortiSOAR Template
- `review_import_fortisoar_template(filename: text, file_path: text)` — Review & Import FortiSOAR Template
- `split_export_templates(prod_content_filepath: text, prod_content_json: text, prod_settings_filepath: text, prod_settings_json: text, dev_settings_filepath: text, dev_settings_json: text, unzip_filepath: text, zip_filename: text)` — Split Export Template
- `unzip_export_template(filepath: text)` — Unzip Export Template


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


### `debug_utils` v1.1.0 _(installed)_
_Debug Utils_

Debug Utils connector can be used to debug connector issues. In production environment is difficult to find the reason for the issue, whether it is with the connector setup or the connector code. To enable faster resolution of issues, the user can use this connector to generate the curl for an API request that can then be shared with the development team.

_(no operations cataloged)_

### `excel-tools` v1.0.0 _(installed)_
_Excel Tools_

Utility to manage excel files

**5 operation(s)**:

- `list_sheets(file_iri: text)` — List Sheets
- `read_column_by_name(file_iri: text, sheet_name: text, column_name: text)` — Read Column By Name
- `read_sheet(file_iri: text, sheet_name: text, [use_column_title: checkbox])` — Read Sheet
- `update_cell(file_iri: text, sheet_name: text, cell_id: text, cell_value: text)` — Update Cell
- `update_column(file_iri: text, sheet_name: text, select_column: select)` — Update Column


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

_investigation_
- `filter_json_by_key_value(inputJSON: object, targetKeyValue: object, similarityThreshold: integer, [fuzzyMatch: checkbox])` — Filter JSON by Key Value
- `search_keyword_in_text(inputText: textarea, keywordToSearch: text, limit: integer, cutoff: integer)` — Search Keyword In Text


### `gcp-ca-service` v1.0.1 _(installed)_
_GCP Certificate Authority Service_

Certificate Authority Service is a highly available and scalable Google Cloud service that enables you to simplify, automate, and customize the deployment, management, and security of private certificate authorities (CA)

**4 operation(s)**:

_investigation_
- `csr(location: text, ca_pool_name: text, ca_name: text, certificate_name: text, certificate_lifetime: integer, pem_csr: textarea)` — Submit CSR
- `get_ca_crl(location: text, ca_name: text, ca_pool_name: text)` — Get CA and CRL
- `list_certificate_authorities(location: text, ca_pool_name: text)` — Get Certificate Authorities
- `revoke_certificate(location: text, ca_pool_name: text, certificate_name: text)` — Revoke Certificate


### `google-calendar` v1.0.0 _(installed)_
_Google Calendar_

Google Calendar is a web-based calendar service developed by Google, allowing users to organize their schedules, appointments, and events seamlessly. It offers a range of features designed to help users manage their time effectively, collaborate with others, and stay organized across various devices.

**8 operation(s)**:

_investigation_
- `delete_access_control_rule(calendar_id: text, rule_id: text)` — Delete Access Control Rule
- `delete_calendar_list(calendar_id: text)` — Delete Calendar List
- `get_access_control_rule_details(calendar_id: text, rule_id: text)` — Get Access Control Rule Details
- `get_calendar_access_control_list(calendar_id: text, [showDeleted: checkbox], [maxResults: integer], [pageToken: text], [syncToken: text])` — Get Calendar Access Control List
- `get_calendar_list([minAccessRole: select], [showDeleted: checkbox], [showHidden: checkbox], [maxResults: integer], [pageToken: text], [syncToken: text])` — Get All Calendar List
- `get_calendar_list_details(calendar_id: text)` — Get Calendar List Details
- `get_event_details(calendar_id: text, event_id: text, [maxAttendees: integer], [timeZone: text])` — Get Event Details
- `get_events_list(calendar_id: text, [eventTypes: multiselect], [timeMax: datetime], [timeMin: datetime], [updatedMin: datetime], [orderBy: text], [maxAttendees: integer], [maxResults: integer], [pageToken: text], [additional_parameters: json])` — Get Events List


### `google-cloud-functions` v1.0.0 _(installed)_
_Google Cloud Functions_

Google Cloud Functions is a serverless execution environment for building and connecting cloud services.

**5 operation(s)**:

_investigation_
- `get_access_control_policy(project_name: text, location_name: text, function_name: text, [requestedPolicyVersion: integer])` — Get Access Control Policy
- `get_function_details(project_name: text, location_name: text, function_name: text)` — Get Function Details
- `get_functions_list(project_name: text, location_name: text, [filter: text], [orderBy: text])` — Get Functions List
- `get_locations_list(project_name: text, [filter: text], [pageSize: integer], [pageToken: text])` — Get Locations List
- `set_access_control_policy(project_name: text, location_name: text, function_name: text, auditConfigs: json, bindings: json, etag: text, version: integer, [updateMask: text])` — Set Access Control Policy


### `google-docs` v1.0.0 _(installed)_
_Google Docs_

Google Docs is a cloud-based word processing application developed by Google. It allows users to create, edit, and collaborate on documents in real-time over the internet.

**3 operation(s)**:

_investigation_
- `create_document(title: text)` — Create Document
- `get_document_details(document_id: text, [suggestionsViewMode: select])` — Get Document Details
- `update_documents(document_id: text, additional_parameters: json)` — Update Documents


### `google-maps` v1.0.0 _(installed)_
_Google Maps_

Google Maps is use for the process of converting addresses into geographic coordinates, which you can use to place markers on a map, or position the map.

**1 operation(s)**:

_investigation_
- `get_maps_geocode(address: text)` — Get Maps Geocode


### `google-sheets` v1.0.0 _(installed)_
_Google Sheets_

Google Sheets is a web-based application that enables users to create, update and modify spreadsheets and share the data online in real time.

**10 operation(s)**:

_investigation_
- `add_row_to_spreadsheet(spreadsheetId: text, range: text, valueInputOption: select, [insertDataOption: select], [includeValuesInResponse: checkbox], [responseValueRenderOption: select], [responseDateTimeRenderOption: select], [majorDimension: select], [data: json])` — Add Row to a Spreadsheet
- `clear_rows_from_spreadsheet(spreadsheetId: text, [ranges: text])` — Clear Rows from a Spreadsheet
- `clear_rows_of_spreadsheet_by_filter(spreadsheetId: text, [data: json])` — Clear Rows of Spreadsheet by Filter
- `create_spreadsheet([title: text], [locale: text], [autoRecalc: select], [timeZone: text], [maxIterations: integer], [convergenceThreshold: integer], [primaryFontFamily: text], [themeColors: json], [sheets: json], [namedRanges: json], [developerMetadata: json], [dataSources: json])` — Create Spreadsheet
- `filter_spreadsheet(spreadsheetId: text, [dataFilters: json], [includeGridData: checkbox])` — Filter Spreadsheet
- `get_spreadsheet_details(spreadsheetId: text, [ranges: text], [includeGridData: checkbox])` — Get Spreadsheet Details
- `get_spreadsheet_rows(spreadsheetId: text, range: text, [majorDimension: select], [valueRenderOption: select], [dateTimeRenderOption: select])` — Get Spreadsheet Rows
- `move_sheet(spreadsheetId: text, sheetId: integer, destinationSpreadsheetId: text)` — Move Sheet
- `update_rows_in_spreadsheet(spreadsheetId: text, valueInputOption: select, [data: json], [includeValuesInResponse: checkbox], [responseValueRenderOption: select], [responseDateTimeRenderOption: select])` — Updates Rows in a Spreadsheet
- `update_rows_of_spreadsheet_by_filter(spreadsheetId: text, valueInputOption: select, [data: json], [includeValuesInResponse: checkbox], [responseValueRenderOption: select], [responseDateTimeRenderOption: select])` — Update Rows of Spreadsheet by Filter


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

- `run_js_code(js_code: textarea)` — Execute JavaScript Code


### `json-convert` v1.0.0 _(installed)_
_JC - Parse Command Output_

Convert the output of many commands and file-types to structured objects using the open-source JSON Convert (JC) library. The JC project details can be found at https://github.com/kellyjonbrazil/jc

**2 operation(s)** (+1 hidden):

_miscellenous_
- `convert(parser: select, command_output: textarea, [raw: checkbox])` — Convert


### `microsoft-graph` v2.2.0 _(installed)_
_Microsoft Graph API_

Microsoft Graph API is a powerful and unified programming interface provided by Microsoft that allows developers to access a wide range of data and services from Microsoft 365 and Azure Active Directory (Azure AD). It provides a single endpoint and a consistent set of RESTful web APIs, making it easier for developers to integrate and interact with Microsoft's cloud services and applications.

**16 operation(s)**:

_containment_
- `block_new_ips(namedLocationUuid: text, [ipv4_ips: text], [ipv6_ips: text])` — Block New IP Ranges

_investigation_
- `add_comment_on_security_alert(alert_id: text, comment: text)` — Add Comment on Security Alert
- `create_ip_range_location(name: text, [is_trusted: checkbox], [ipv4_ips: text], [ipv6_ips: text])` — Create IP Named Location
- `del_message(user_id: text, message_id: text)` — Delete Message
- `del_message_bulk(user_list: json)` — Delete Message Bulk
- `get_all_named_locations([name: text], [select: multiselect], [order_by: select], [count: checkbox], [size: integer], [skip: integer])` — Get All Named Locations
- `get_all_security_alerts([api_version: select], [assigned_to: text], [top: integer], [skip: integer])` — Get All Security Alerts
- `get_group_users(group_id: text)` — Get Users Within A Group
- `get_groups()` — Get Groups
- `get_risky_user_details(risk_id: text)` — Get Risky User Details
- `get_risky_users_list()` — Get Risky Users List
- `get_security_alert([api_version: select], alert_id: text)` — Get Security Alert
- `search_message(subject: text, user_list: textarea, [size: integer], [skip: integer])` — Search Message in Users Mailbox
- `update_security_alert(alert_id: text, [api_version: select], [assigned_to: text])` — Update Security Alert

_remediation_
- `revoke_user_sessions(user: text)` — Revoke User Session
- `unblock_new_ips(namedLocationUuid: text, [ipv4_ips: text], [ipv6_ips: text])` — Unblock IP Ranges


### `pagerduty` v2.1.0 _(installed)_
_PagerDuty_

PagerDuty connects to monitoring systems so that you can collect events, surface what's important, and resolve critical issues to proactively manage your uptime. This Connector a facilitates automated operations to create incident, list notification, list teams, list users, send event, update event get user and notification details

**13 operation(s)**:

_investigation_
- `create_incident(from: text, title: text, description: text, priority: select, [urgency: select], [incident_key: text])` — Create Incident
- `get_escalation_policies_list([query: text], [include: select], [ids: text], [user_ids: text], [sort_by: text], [limit: integer], [offset: integer], [total: checkbox])` — Get All Escalation Policies
- `get_incident_alerts_list(incident_id: text, [include: select], [statuses: select], [alert_key: text], [sort_by: text], [limit: integer], [offset: integer], [total: checkbox])` — Get Incident Alerts List
- `get_incident_details(incident_id: text, [include: select])` — Get Incident Details
- `get_incidents([since: datetime], [until: datetime], [ids: text], [user_ids: text], [service_ids: text], [incident_key: text], [include: select], [urgencies: select], [statuses: multiselect], [sort_by: text], [limit: integer], [offset: integer], [total: checkbox])` — Get All Incidents List
- `get_services_list([name: text], [query: text], [include: select], [ids: text], [time_zone: text], [sort_by: text], [limit: integer], [offset: integer], [total: checkbox])` — Get All Services List
- `get_user_details(user_id: text, [include: select])` — Get User Details
- `get_user_notification_rules(user_id: text, rule_id: text, [include: select])` — Get User Notification Rules
- `list_notifications(since: datetime, until: datetime, [notification_type: select], [include: select], [time_zone: text], [limit: integer], [offset: integer], [total: checkbox])` — List Notifications
- `list_teams([query: text], [limit: integer], [offset: integer], [total: checkbox])` — List Teams
- `list_users([limit: integer], [offset: integer], [query: text], [total: checkbox], [include: select], [ids: text])` — List Users
- `send_event(summary: text, source: text, severity: select, [timestamp: datetime], [component: text], [group: text], [class: text], [attributes: json])` — Send Event
- `update_event(dedup_key: text, event_action: select)` — Update Event


### `qrcode-tools` v1.0.2 _(installed)_
_QR Code Tools_

QR Code Tools helps users working with QR and Bar codes

**1 operation(s)**:

_investigation_
- `read_qr_code(type: select)` — Read QR Code


### `remote-fortisoar` v2.0.0 _(installed)_
_Remote FortiSOAR_

This connector facilitates automated interactions, with a FortiSOAR endpoint using FortiSOAR playbooks. Add the Remote FortiSOAR connector as a step in FortiSOAR playbooks and run REST API operations on FortiSOAR environments other than your own FortiSOAR environment

**2 operation(s)**:

_Utilities_
- `upload_file(file_iri: text, [create_attachment: checkbox])` — Upload file to FortiSOAR

_investigation_
- `make_api_call(iri: text, method: select)` — Make an API call


### `screenshot` v1.0.1 _(installed)_
_Remote Screenshot_

Screenshot connector provide you functionality to take screenshot of URLs, Emails, MSG Files, and EML Files.

**3 operation(s)**:

_investigation_
- `screenshot_eml_or_msg_file(file_type: select, [screenshot_name: text], screenshot_size: select, [create_attachment: checkbox])` — Screenshot EML OR MSG File Content
- `screenshot_mail(mail_html_body: text, [screenshot_name: text], screenshot_size: select, [create_attachment: checkbox])` — Screenshot Email Content
- `screenshot_url(url: text, [screenshot_name: text], screenshot_size: select, [create_attachment: checkbox])` — Screenshot URL


### `time-series-chart-utilities` v1.0.0 _(installed)_
_Time Series Chart Utilities_

When using the Time Series Chart Solution Pack, this connector is used by the included playbooks to facilitate the creation of data-over-time or time series charts. The included functions include building a list of datetime-buckets, as well as various utilities to process the output of dataset queries for use by the Time Series Widget.

**4 operation(s)**:

_utilities_
- `assemble_query_time_windows(relativeDate: object, time_period: select, dateFormatString: text, [existing_times: object], [query_modified: checkbox])` — Assemble Query Time Windows
- `combine_query_results_into_data_columns([playbookMode: text], [firstIndexToKeep: integer], [queriedTimeBuckets: object], queryResults: object, [existingDataColumns: object])` — Combine Query Results into Data Columns
- `flatten_data_sets_and_groups(dataSets: object)` — Flatten Data Sets and Groups
- `format_data_set_output_with_fieldgrouped(queryOutput: object, timeBucketsQueried: object, dataSetConfiguration: object)` — Format Data Set Output with Field-Grouped


### `web-screenshot` v1.0.0 _(installed)_
_Web Screenshot_

Web Screenshot provides a service to take screenshot or thumbnail of any online web page in a couple of second.

**1 operation(s)**:

_investigation_
- `take_screenshot(url: text)` — Take Screenshot


---

## Utility

### `text-utility` v1.1.0 _(installed)_
_Text Utility_

Utilities to process text with features like sentences similarity, OCR and macro extractions from MS Office documents

**3 operation(s)**:

_utility_
- `extract_macros(file_iri: text)` — Extract Macros
- `image_to_text(image_iri: text)` — Image to Text OCR
- `sentence_similarity(sentence: text, sentences_to_compare_with: json)` — Get Sentences Similarity


---

## Vault

### `cyberark` v2.1.0 _(installed)_
_CyberArk_

CyberArk provide secure and manage password and other credentials for applications. This connector facilitates automated crud operations for Account Group, User, Safe and Credentials.

**31 operation(s)** (+7 hidden):

_investigation_
- `delete_account_group_members(GroupID: text, AccountID: text)` — Delete Member from Account Group
- `delete_safe_member(Safe: text, MemberName: text)` — Delete Safe Member
- `get_account([filter: text], [savedfilter: text], [search: text], [searchType: select], [sort: text], [offset: integer], [limit: integer])` — Get Accounts
- `get_account_group_members(GroupID: text)` — Get Account Group Members
- `get_groups()` — Get Groups
- `get_recording_details(recording_id: text)` — Get Recording Details by ID
- `get_recordings([safe: text], [from_time: integer], [to_time: integer], [activities: text], [search: text], [sort: text], [offset: integer], [limit: integer])` — Get Recordings
- `get_safe_account_groups(SafeName: text)` — Get Safe Account Groups
- `get_safe_details(Safe: text)` — Get Safe Details
- `get_user_details(userID: integer)` — Get User Details
- `list_safe_members(SafeName: text)` — List Safe Members
- `list_safes([limit: text])` — List Safes
- `logged_on_user_details()` — Logged on User Details
- `play_recording(recording_id: text)` — Get Data Stream of Recorded Session
- `reconcile_credentials(account_id: text)` — Reconcile Credentials
- `reset_user_password(userID: integer, newPassword: password)` — Reset User Password
- `search_safe(query: text)` — Search Safe
- `update_safe_member(SafeName: text, MemberName: text, IsExpiredMembershipEnable: checkbox, UseAccounts: checkbox, RetrieveAccounts: checkbox, ListAccounts: checkbox, AddAccounts: checkbox, UpdateAccountContent: checkbox, UpdateAccountProperties: checkbox, InitiateCPMAccountManagementOperations: checkbox, SpecifyNextAccountContent: checkbox, RenameAccounts: checkbox, DeleteAccounts: checkbox, UnlockAccounts: checkbox, ManageSafe: checkbox, ManageSafeMembers: checkbox, BackupSafe: checkbox, ViewAuditLog: checkbox, ViewSafeMembers: checkbox, AccessWithoutConfirmation: checkbox, CreateFolders: checkbox, DeleteFolders: checkbox, MoveAccountsAndFolders: checkbox, RequestsAuthorizationLevel1: checkbox, RequestsAuthorizationLevel2: checkbox)` — Update Safe Member

_miscellaneous_
- `add_account_group(AccountID: text, GroupID: text)` — Add Account Group
- `add_safe(SafeName: text, retention: select, [Description: text], [ManagingCPM: text], [OLACEnabled: checkbox])` — Add Safe
- `add_safe_member(SafeName: text, MemberName: text, IsExpiredMembershipEnable: checkbox, UseAccounts: checkbox, RetrieveAccounts: checkbox, ListAccounts: checkbox, AddAccounts: checkbox, UpdateAccountContent: checkbox, UpdateAccountProperties: checkbox, InitiateCPMAccountManagementOperations: checkbox, SpecifyNextAccountContent: checkbox, RenameAccounts: checkbox, DeleteAccounts: checkbox, UnlockAccounts: checkbox, ManageSafe: checkbox, ManageSafeMembers: checkbox, BackupSafe: checkbox, ViewAuditLog: checkbox, ViewSafeMembers: checkbox, AccessWithoutConfirmation: checkbox, CreateFolders: checkbox, DeleteFolders: checkbox, MoveAccountsAndFolders: checkbox, RequestsAuthorizationLevel1: checkbox, RequestsAuthorizationLevel2: checkbox)` — Add Safe Member
- `add_user_to_group(memberId: text, GroupID: integer)` — Add User to Group
- `delete_safe(SafeName: text)` — Delete Safe
- `update_safe(SafeName: text, Location: text, OLACEnabled: checkbox, retention: select, [Description: text], [ManagingCPM: text])` — Update Safe


### `cyberark-aim` v1.1.0 _(installed)_
_CyberArk AIM_

CyberArk Application Identity Manager (AIM) is a key component in CyberArk's Privileged Access Security suite. It helps manage and secure credentials used by applications and services by providing secure retrieval of passwords and other sensitive data.

**4 operation(s)** (+3 hidden):

_investigation_
- `get_password([Folder: text], [UserName: text], [Address: text], [PolicyID: text], [additional_attributes: json])` — Get Password


### `hashicorp-vault` v2.0.0 _(installed)_
_HashiCorp Vault_

HashiCorp Vault is an identity-based secret and encryption management system. A secret is anything over which you want to control access, such as API encryption keys, passwords, and certificates.

**3 operation(s)** (+3 hidden):

_investigation_
- `get_credential(secret_id: text, attribute_name: text)` — Get Credential
- `get_credentials()` — Get Credentials
- `get_credentials_details(secret_id: text)` — Get Credentials Details


### `keeper-secrets-manager` v1.0.0 _(installed)_
_Keeper Secrets Manager_

Keeper Secrets Manager is a tool designed to securely manage sensitive information, such as passwords, API keys, and other credentials, within an organization. It provides a centralized platform for storing, accessing, and sharing these secrets while maintaining strong encryption and access controls to protect sensitive data.

**3 operation(s)** (+3 hidden):

_investigation_
- `get_credential(secret_id: text, attribute_name: text)` — Get Credential
- `get_credentials()` — Get Credentials
- `get_credentials_details(secret_id: text)` — Get Credentials Details


### `openbao-vault` v1.0.0 _(installed)_
_OpenBao Vault_

OpenBao Vault is an identity-based system for securely managing and distributing secrets such as API keys, passwords, and certificates.

**3 operation(s)** (+3 hidden):

_investigation_
- `get_credential(secret_id: text, attribute_name: text)` — Get Credential
- `get_credentials()` — Get Credentials
- `get_credentials_details(secret_id: text)` — Get Credentials Details


### `thycotic-secret-server` v2.0.0 _(installed)_
_Delinea Secret Server_

Delinea Secret Server is an external vault that protects your privileged accounts with enterprise-grade privileged access management (PAM) solutions available both on-premise or in the cloud.

**3 operation(s)** (+3 hidden):

_investigation_
- `get_credential(secret_id: text, attribute_name: text)` — Get Credential
- `get_credentials([search_text: text], [search_template_id: text], [folder_id: text], [include_sub_folders: checkbox], [include_restricted: checkbox])` — Get Credentials
- `get_credentials_details(secret_id: text)` — Get Credentials Details


---

## Vulnerability Control

### `skybox-security` v1.0.0 _(installed)_
_Skybox Security_

Skybox Security arms security professionals with the broadest platform of solutions for security operations, analytics, and reporting. This connector facilitates automated operations like Lookup IP, get assets

**2 operation(s)**:

_investigation_
- `get_assets_by_names(asset_name: text)` — Get Assets
- `lookup_ip_address(ip: text)` — Lookup IP


---

## Vulnerability Management

### `blueliv-threatcompass` v1.0.0 _(installed)_
_Blueliv ThreatCompass_

Blueliv ThreatCompass systematically looks for information about companies,products, people, brands, logos, assets, technology and other information, depending on your needs. Blueliv ThreatCompass allows you to monitor and track all this information to keep your data, your organization and its employees safe

**9 operation(s)**:

_investigation_
- `get_module_labels(org_id: text, module_id: text, module_type: select, [other_fields: json])` — Get Module Labels
- `get_resource_by_id(org_id: text, module_id: text, resource_id: text, [other_fields: json])` — Get Resource by ID
- `get_resource_list(org_id: text, module_id: text, [to: integer], [since: integer], [page: integer], [maxRows: integer], [other_fields: json])` — Get Resource List
- `update_resource_fav(org_id: text, module_id: text, module_type: select, resources: text, status: select, [other_fields: json])` — Update Resource FAV
- `update_resource_label(org_id: text, module_id: text, module_type: select, resources: text, label: text, [other_fields: json])` — Update Resource Label
- `update_resource_rating(org_id: text, module_id: text, module_type: select, resources: text, rate: text, [other_fields: json])` — Update Resource Rating
- `update_resource_read_status(org_id: text, module_id: text, module_type: select, resources: text, read: checkbox, [other_fields: json])` — Update Resource Read Status
- `update_resource_status(org_id: text, module_id: text, module_type: select, resource_id: text, status: select, [other_fields: json])` — Update Resource Status
- `update_resource_tlp(org_id: text, module_id: text, module_type: select, resource_id: text, tlp_status: select, [other_fields: json])` — Update Resource TLP


### `kenna` v1.0.0 _(installed)_
_Kenna_

Kenna is risk-based intelligent vulnerability management platform that enables InfoSec teams to prioritize and remediate vulnerabilities faster. This connector facilitates the automated operations around vulnerabilities, connectors, assets and users

**17 operation(s)**:

_investigation_
- `create_asset(locator_information: select, value: text, [priority: select], [notes: text], [operating_system: text], [other_fields: json])` — Create Asset
- `create_user(firstname: text, lastname: text, email: text, role: text, [phone: text])` — Create User
- `create_vulnerability(identifier: select, id_value: text, primary_locator: select, primary_locator_value: text, [other_fields: json])` — Create Vulnerability
- `delete_user(identifier: text)` — Delete User
- `delete_vulnerability(identifier: text)` — Delete Vulnerability
- `get_connectors()` — Get Connectors
- `list_assets([page: integer])` — List Assets
- `list_fixes([page: integer], [per_page: integer])` — List Fixes
- `list_users()` — List Users
- `list_vulnerabilities([page: integer])` — List Vulnerabilities
- `run_connector(identifier: text)` — Run Connector
- `search_asset([asset_id: text], [status: multiselect], [port: text], [min_priority: select], [max_priority: select], [other_fields: json])` — Search Asset
- `search_fixes([identifier: text], [status: text], [port: text], [other_fields: json])` — Search Fixes
- `search_vulnerabilities([identifier: text], [status: multiselect], [port: text], [min_severity: select], [max_severity: select], [min_threat: select], [max_threat: select], [other_fields: json])` — Search Vulnerabilities
- `update_asset(asset_id: text, [hostname: text], [priority: select], [notes: text], [operating_system: text], [other_fields: json])` — Update Asset
- `update_user(user_id: text, [firstname: text], [lastname: text], [email: text], [other_fields: json])` — Update User
- `update_vulnerability(asset_id: text, [notes: text], [status: select], [override_score: integer], [prioritized: checkbox], [other_fields: json])` — Update Vulnerability


### `nessus` v1.0.0 _(installed)_
_Nessus_

Nessus provide actions like get all scans, trigger scan, scan specific assets and asset specific vulnerabilities

**6 operation(s)**:

_investigation_
- `get_asset_vulnerabilities(scan_id: integer, host_id: integer)` — List Asset's Vulnerabilities
- `get_plugin_details(plugin_id: integer)` — Get Plugin Information
- `get_scan_assets(scan_id: integer)` — List Scan's Assets
- `get_scans([days: select])` — List Scans
- `get_vuln_details(scan_id: integer, host_id: integer, plugin_id: integer)` — Get Vulnerability Information
- `trigger_scan(scan_id: integer, [alt_targets: text])` — Trigger Scan


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


### `qualys` v1.1.0 _(installed)_
_Qualys_

Qualys provides cloud security, compliance and protection of IT assets and web applications. This connector facilitates the automated operations for vulnerability management, policy compliance, asset management

**47 operation(s)**:

_investigation_
- `add_ip(ips: text, enable_vm: checkbox, enable_pc: checkbox, [tracking_method: select], [owner: text], [ud1: text], [ud2: text], [ud3: text], [comment: text], [ag_title: text])` — Add Assets
- `create_asset_group(title: text, [network_id: text], [additional_parameter: json])` — Create Asset Group
- `create_static_search_list(title: text, qids: text, [global: checkbox], [comments: text])` — Create Static Search List
- `create_vm_option_profile(title: text, scan_tcp_ports: select, scan_udp_ports: select, vulnerability_detection: select, basic_information_gathering: select, [additional_parameter: json])` — Create VM Option Profile
- `delete_asset_group(id: text)` — Delete Asset Group
- `delete_report(id: integer)` — Delete Report
- `delete_static_search_list(id: integer)` — Delete Static Search List
- `delete_vm_option_profile(id: integer)` — Delete VM Option Profile
- `edit_asset_group(id: text, [additional_parameter: json])` — Edit Asset Group
- `fetch_pc_scan([scan_ref: text], [add_vuln_as_attachment: checkbox])` — PC - Fetch Scan
- `fetch_report(id: integer)` — Download Saved Report
- `fetch_vm_scan([scan_ref: text], [ips: text], [mode: select], [add_vuln_as_attachment: checkbox])` — VM - Fetch Scan
- `get_asset_search_report(output_format: select, [additional_parameter: json], [add_vuln_as_attachment: checkbox])` — Get Asset Search Report
- `launch_compliance_policy_report(template_id: text, [report_title: text], output_format: select, policy_id: text, [host_id: text], [instance_string: text], [use_tags: select])` — Launch Compliance Policy Report
- `launch_compliance_report(template_id: text, [report_title: text], output_format: select, [report_refs: text], [ips: text], [asset_group_ids: text])` — Launch Compliance Report
- `launch_host_based_findings_report(template_id: text, [report_title: text], output_format: select, [ips_network_id: text], [use_tags: select])` — Launch Host Based Findings Report
- `launch_patch_report(template_id: text, [report_title: text], output_format: select, [use_tags: select])` — Launch Patch Report
- `launch_pc_scan([scan_title: text], opt_pro: select, [scan_app: select], [default_scanner: checkbox], [target_from: select], [runtime_http_header: text], [ip_network_id: text])` — PC - Launch Scan
- `launch_remediation_report(template_id: text, [report_title: text], output_format: select, assignee_type: select, [use_tags: select])` — Launch Remediation Report
- `launch_scan_based_findings_report(template_id: text, [report_title: text], report_refs: text, output_format: select, [ip_restriction: text], [use_tags: select])` — Launch Scan Based Findings Report
- `launch_scheduled_report(id: integer)` — Launch Scheduled Report
- `launch_score_card(sc_type: select, [report_title: text], output_format: select, [source: select], [patch_qids: text], [missing_qids: text])` — Launch Scorecard Report
- `launch_vm_scan([scan_title: text], opt_pro: select, [priority: select], [scan_app: select], [default_scanner: checkbox], [target_from: select], [runtime_http_header: text], [ip_network_id: text], [client_id: integer])` — VM - Launch Scan
- `list_excluded_host([ips: text], [network_id: text])` — Get Excluded Host List
- `list_group([ids: text], [id_min: text], [id_max: text], [unit_id: integer], [user_id: integer], [title: text], [network_ids: text], [truncation_limit: text], [show_attributes: multiselect])` — Get Asset Group List
- `list_host([details: select], [ips: text], [ids: text], [ag_ids: text], [ag_titles: text], [id_min: integer], [id_max: integer], [network_ids: text], [no_vm_scan_since: datetime], [no_compliance_scan_since: datetime], [vm_scan_since: datetime], [compliance_scan_since: datetime], [vm_processed_before: datetime], [vm_processed_after: datetime], [vm_scan_date_before: datetime], [vm_scan_date_after: datetime], [os_pattern: text], [truncation_limit: text])` — Get Scanned Host List
- `list_host_detection([ids: text], [id_min: integer], [id_max: integer], [use_tags: select], [network_ids: text], [vm_scan_since: datetime], [no_vm_scan_since: datetime], [max_days_since_last_vm_scan: integer], [vm_processed_before: datetime], [vm_processed_after: datetime], [vm_scan_date_before: datetime], [vm_scan_date_after: datetime], [vm_auth_scan_date_before: datetime], [vm_auth_scan_date_after: datetime], [status: multiselect], [compliance_enabled: select], [os_pattern: text], [qids: text], [severities: multiselect], [show_igs: select], [search_list: select], [show_results: checkbox], [show_tags: checkbox], [show_reopened_info: checkbox], [arf_kernel_filter: select], [arf_service_filter: select], [arf_config_filter: select], [output_format: select], [suppress_duplicated_data_from_csv: checkbox], [truncation_limit: text], [max_days_since_detection_updated: integer], [detection_updated_since: datetime], [detection_updated_before: datetime], [detection_processed_before: datetime], [detection_processed_after: datetime], [add_vuln_as_attachment: checkbox])` — Get Host Detection List
- `list_ip([ips: text], [tracking_method: select], [network_id: text], [compliance_enabled: checkbox])` — Get Asset List
- `list_option_profile()` — Get Option Profiles
- `list_pc_scan([scan_id: text], [scan_ref: text], [state: multiselect], [type: select], [target: text], [user_login: text], [launched_after_datetime: datetime], [launched_before_datetime: datetime], [processed: select], [show_ags: checkbox], [show_op: checkbox], [show_status: checkbox], [show_last: checkbox])` — PC - Get Scan List
- `list_report([id: integer], [state: select], [user_login: text], [expires_before_datetime: datetime])` — Get Report List
- `list_report_template()` — Get Report Template List
- `list_scanner_appliance([scan_ref: text], [name: text], [ids: text], [busy: select], [scan_detail: checkbox], [output_mode: select], [include_license_info: checkbox])` — Get Scanner Appliance
- `list_schedule_scan([id: text], [active: select])` — Get Schedule Scan List
- `list_scheduled_report([id: integer], [is_active: select])` — Get Scheduled Report List
- `list_static_search([ids: text])` — Get Static Search List
- `list_virtual_host([port: text], [ip: text])` — Get Virtual Host List
- `list_vm_option_profile([additional_parameter: json])` — Get VM Option Profile List
- `list_vm_scan([scan_ref: text], [state: multiselect], [type: select], [target: text], [user_login: text], [launched_after_datetime: datetime], [launched_before_datetime: datetime], [processed: select], [show_ags: checkbox], [show_op: checkbox], [show_status: checkbox], [show_last: checkbox])` — VM - Get Scan List
- `list_vulnerability([cve: text], [details: select], [ids: text], [id_min: integer], [id_max: integer], [is_patchable: select], [last_modified_after: datetime], [last_modified_before: datetime], [last_modified_by_user_after: datetime], [last_modified_by_user_before: datetime], [last_modified_by_service_after: datetime], [last_modified_by_service_before: datetime], [published_after: datetime], [published_before: datetime], [discovery_method: select], [discovery_auth_types: multiselect], [show_pci_reasons: checkbox], [show_supported_modules_info: checkbox], [show_disabled_flag: checkbox], [show_qid_change_log: checkbox], [add_vuln_as_attachment: checkbox])` — Get Vulnerability List
- `manage_excluded_host(action: select)` — Manage Excluded Host
- `manage_pc_scan(action: select, scan_ref: text)` — PC - Manage Scan
- `manage_virtual_host(action: select, ip: text, port: text, [fqdn: text])` — Manage Virtual Host
- `update_ip(ips: text, [tracking_method: select], [host_dns: text], [host_netbios: text], [owner: text], [ud1: text], [ud2: text], [ud3: text], [comment: text])` — Update Asset
- `update_static_search_list(id: text, [title: text], [global: select], [operation_to_perform_on_QIDs: select], [comments: text])` — Update Static Search List
- `update_vm_option_profile(id: integer, [additional_parameter: json])` — Update VM Option Profile
- `vm_scan_action(action: select, scan_ref: text)` — VM - Manage Scan


### `rapid7-insightvm` v1.2.0 _(installed)_
_Rapid7 InsightVM_

The Rapid7 InsightVM platform integrates Rapid7’s library of Nexpose vulnerability research, Metasploit exploit knowledge, global attacker behavior, internet-wide scanning data, and threat exposure analytics. InsightVM takes advantage of this powerful analytics platform to automatically collect, monitor, and analyze your network for new and existing risks. This connector facilitates automated operations to fetch information about Asset, Site, Scan, Exploits and Vulnerability

**19 operation(s)**:

_investigation_
- `create_site_scan_schedules(site_id: integer, [assets : json], enabled: checkbox, [scan_name: text], start: datetime, [scan_engine_id: text], [scan_template_id: text], [duration: text], [scan_schedule_id: integer], repeat_scan: select, [repeat: json])` — Create Site Scan Schedules
- `delete_site_scan_schedule(site_id: integer, scheduleId: integer)` — Delete Site Scan Schedule
- `get_asset([match: select], [ip-address: select], [host-name: select], [host-name_value: text], [operating-system: select], [operating-system_value: text], [site-id: select], [site-id_value: integer], [open-ports: select], [custom-tag: select], [custom-tag_value: text], [vulnerability-category: select], [vulnerability-category_value: text], [vulnerability-title: select], [vulnerability-title_value: text], [cve: select], [cve_value: text], [location-tag: select], [location-tag_value: text], [criticality-tag: select], [criticality-tag_value: select], [owner-tag: select], [owner-tag_value: text], [page: integer], [size: integer])` — Get Asset(s)
- `get_asset_groups([type: text], [name: text], [page: integer], [size: integer])` — Get Asset Groups
- `get_asset_vuln(asset_id: integer, [detailed_report: checkbox], [page: integer], [size: integer])` — Get Asset Vulnerability
- `get_exploit_details(exploit_id: integer)` — Get Exploit Details
- `get_exploitable_vuln(exploit_id: integer)` — Get Exploitable Vulnerabilities
- `get_exploits(page: integer, size: integer)` — Get Exploits
- `get_scan([scan_id: integer], [active: checkbox], [page: integer], [size: integer])` — Get Scan
- `get_scan_engines([id: integer])` — Get Scan Engines
- `get_scan_templates([id: text])` — Get Scan Templates
- `get_site([site_id: integer], [page: integer], [size: integer])` — Get Site
- `get_site_scan_engines(site_id: integer)` — Get Site Scan Engines
- `get_site_scan_schedule(site_id: integer, schedule_id: integer)` — Get Specified Scan Schedule
- `get_site_scan_schedules([site_id: integer])` — Get Scan Schedules
- `get_site_scan_templates(site_id: integer)` — Get Site Scan Templates
- `get_software(asset_id: integer)` — Get Softwares on Asset
- `get_vulns([vuln_id: text], [page: integer], [size: integer])` — Get Vulnerability
- `launch_site_scan(id: integer, engine_id: integer, template_id: text, [asset_group_ids: text], [hosts: text], [name: text])` — Launch Site Scan


### `rapid7-nexpose` v1.3.0 _(installed)_
_Rapid7 Nexpose_

Rapid7 Nexpose is a vulnerability assessment tool which aims to support the entire vulnerability management lifecycle, including discovery, detection, verification, risk classification, impact analysis, reporting, and mitigation. It integrates with Rapid7's Metasploit for vulnerability exploitation.

**20 operation(s)**:

_investigation_
- `create_tags(name: text, type: text, [color: text], [risk_modifier: integer], [created: datetime], [other_fields: json])` — Create Tag
- `get_asset([match: select], [ip-address: select], [host-name: select], [host-name_value: text], [operating-system: select], [operating-system_value: text], [site-id: select], [site-id_value: integer], [open-ports: select], [custom-tag: select], [custom-tag_value: text], [vulnerability-category: select], [vulnerability-category_value: text], [vulnerability-title: select], [vulnerability-title_value: text], [cve: select], [cve_value: text], [location-tag: select], [location-tag_value: text], [criticality-tag: select], [criticality-tag_value: select], [owner-tag: select], [owner-tag_value: text], [page: integer], [size: integer])` — Get Asset(s)
- `get_asset_groups([type: text], [name: text], [page: integer], [size: integer])` — Get Asset Groups
- `get_asset_tags([asset_id: integer])` — Get Asset Tags
- `get_asset_vuln(asset_id: integer, [detailed_report: checkbox], [page: integer], [size: integer])` — Get Asset Vulnerability
- `get_exploit_details(exploit_id: integer)` — Get Exploit Details
- `get_exploitable_vuln(exploit_id: integer)` — Get Exploitable Vulnerabilities
- `get_exploits(page: integer, size: integer)` — Get Exploits
- `get_reference_link(href: text)` — Execute Reference link
- `get_scan([scan_id: integer], [active: checkbox], [page: integer], [size: integer])` — Get Scan
- `get_scan_engines([id: integer])` — Get Scan Engines
- `get_scan_templates([id: text])` — Get Scan Templates
- `get_site([site_id: integer], [page: integer], [size: integer])` — Get Site
- `get_site_scan_schedule(site_id: integer, [schedule_id: integer])` — Get Site Scan Schedule(s)
- `get_software(asset_id: integer)` — Get Softwares on Asset
- `get_tag_assets([tag_id: integer])` — Get Assets Associated with Tag
- `get_tags([name: text], [type: text], [page: integer], [size: integer])` — Get Tags
- `get_vulns([vuln_id: text], [page: integer], [size: integer])` — Get Vulnerability
- `launch_site_scan(id: integer, engine_id: integer, template_id: text, [asset_group_ids: text], [hosts: text], [name: text])` — Launch Site Scan
- `tag_asset(id: text, assetId: text)` — Tag Asset


### `security-center` v1.1.0 _(installed, ingestion)_
_Tenable Security Center_

Tenable Security Center provide actions like get all completed scans, scan specific assets and asset specific vulnerabilities

**3 operation(s)**:

_investigation_
- `get_all_assets(scan_details: text)` — List Assets
- `get_all_scans(days: select)` — List Completed Scans
- `get_asset_vulns(asset_info: text, [scan_id: text], [scan_name: text])` — List Asset Vulnerabilities


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


### `threadfix` v1.1.0 _(installed)_
_ThreadFix_

ThreadFix is a software vulnerability aggregation and management system. Threadfix connector facilitates automated operation related to policies, vulnearabilities, scans with threadfix server.

**21 operation(s)**:

_Remediation_
- `close_vulns(vuln_id: text)` — Close Vulnerabilities

_investigation_
- `add_application_to_policy(policy_id: text, application_id: text)` — Add Application To a Policy
- `add_comment_vulns(vuln_id: text, comment: textarea, [comment_tag_id: text])` — Add Comment To Vulnerability
- `check_pending_scan_status(application_id: integer, pending_scan_id: integer)` — Check Pending Scan Status
- `create_application(team_id: integer, name: text, [url: text])` — Create Application
- `create_dynamic_finding(application_id: integer, vulnerability_type: text, description: text, severity: select, [parameter: text], [native_id: integer], [full_url: text], [path: text])` — Create Dynamic Finding
- `create_static_finding(application_id: integer, vulnerability_type: text, description: text, severity: select, [parameter: text], [file_path: text], [native_id: integer], [column: integer], [line_text: text], [line_number: integer])` — Create Static Finding
- `create_team(team_name: text)` — Create Team
- `get_all_policies()` — Get All Policy
- `get_all_tags()` — Get All Tags
- `get_all_teams()` — Get All Teams
- `get_application_by_id(app_id: integer)` — Get Application By ID
- `get_application_by_name(team_name: text, app_name: text)` — Get Application By Name
- `get_application_policy_status(application_id: text)` — Get Application Policy Status
- `get_policy(policy_id: text)` — Get Policy Details
- `get_scan_details(scan_id: text)` — Get Scan Details
- `get_team(option: select, value: text)` — Get Team Details
- `list_scan(application_id: text)` — Get Scan List
- `list_severities()` — Get Severity List
- `vulnerability_search(severity: multiselect, [generic_vulnerabilities: text], [teams: text], [applications: text], [channel_types: text], [path: text], [parameter: text], [startDate: datetime], [endDate: datetime], [numberMerged: text], [numberVulnerabilities: integer], [page: integer], [showOpen: checkbox], [showClosed: checkbox], [showDefectOpen: checkbox], [showDefectClosed: checkbox], [showDefectPresent: checkbox], [showDefectNotPresent: checkbox], [showFalsePositive: checkbox], [showHidden: checkbox], [showInconsistentClosedDefectNeedsScan: checkbox], [showInconsistentClosedDefectOpenInScan: checkbox], [showInconsistentOpenDefect: checkbox], [includeCustomText: checkbox])` — Search Vulnerabilities

_miscellaneous_
- `update_vuln_severity(vuln_id: text, severity_name: text)` — Update Vulnerability Severity


### `tripwire-ip360` v1.0.0 _(installed)_
_Tripwire IP360_

Tripwire IP360 Connector provides an enterprise-class vulnerability management solution, this connector used to do actions related to scanning

**25 operation(s)** (+4 hidden):

_investigation_
- `add_new_scan_config(name: text, [status: checkbox], profile: select, network: select, appliance_pool: select, [on_demand: select])` — Configure New Scan
- `cancel_scan(name: select)` — Cancel Scan
- `create_network(name: text, [owner: text], [status: checkbox], include_ip_list: text, [exclude_ip_list: text], [asset_value: integer])` — Create Network
- `create_scan_profile(name: text, [status: checkbox], [agent_only: checkbox], [credentials: multiselect], [app_scan: checkbox], [vuln_scan: checkbox], [webapp_scan: checkbox], [webapp_recursion_limit: integer], [webapp_page_limit: integer], [discovery_scan: multiselect], [discovery_tcp_ports: text], [discovery_udp_ports: text], [tcp_scan_ports_only: text], [tcp_scan_ports_include: text], [tcp_scan_ports_exclude: text], [udp_scan_ports_only: text], [udp_scan_ports_include: text], [udp_scan_ports_exclude: text], [background_port_scan: checkbox], [background_port_scan_rate: integer], [scap_scan: checkbox], [scap_scan_policies: text], [app_scan_limited: checkbox], [traversal_random: select], [host_config_check: checkbox], [app_scan_extensive: checkbox], [rules_verified: select], [rules_intrusive: select], [rules_custom: select], [rules_auth_attempt: select], [rate_limit: integer], [vuln_scan_adjusted: select])` — Create Scan Profile
- `delete_network(name: select)` — Delete Network
- `delete_scan_profile(name: select)` — Delete Scan Profile
- `get_agents([search_text: text], [limit: text], [offset: text])` — Get Agents
- `get_assets([search_text: text], [limit: text], [offset: text])` — Get Assets
- `get_audits([search_text: text], [limit: text], [offset: text])` — Get Audits
- `get_networks()` — Get Networks
- `get_scan_configs([search_text: text])` — Get Scan Configurations
- `get_scan_profiles([search_text: text])` — Get Scan Profiles
- `get_vulnerabilities([search_text: text], [limit: text], [offset: text])` — Get Vulnerabilities
- `pause_scan(name: select)` — Pause Scan
- `resume_scan(name: select)` — Resume Scan
- `run_agent([name: text])` — Run Agent
- `start_scan(name: select)` — Start Scan
- `update_network(name: select, [new_name: text], [owner: text], [status: checkbox], [include_ip_list: text], [exclude_ip_list: text], [asset_value: integer])` — Update Network
- `update_scan_config(name: select, [new_name: text], [status: checkbox], [profile: select], [network: select], [appliance_pool: select], [on_demand: checkbox], [schedule_start: select])` — Update Scan Configuration
- `update_scan_profile(name: select, [new_name: text], [status: checkbox], [agent_only: checkbox], [credentials: multiselect], [app_scan: checkbox], [vuln_scan: checkbox], [webapp_scan: checkbox], [webapp_recursion_limit: integer], [webapp_page_limit: integer], [discovery_scan: multiselect], [discovery_tcp_ports: text], [discovery_udp_ports: text], [tcp_scan_ports_only: text], [tcp_scan_ports_include: text], [tcp_scan_ports_exclude: text], [udp_scan_ports_only: text], [udp_scan_ports_include: text], [udp_scan_ports_exclude: text], [background_port_scan: checkbox], [background_port_scan_rate: integer], [scap_scan: checkbox], [scap_scan_policies: text], [app_scan_limited: checkbox], [traversal_random: select], [host_config_check: checkbox], [app_scan_extensive: checkbox], [rules_verified: select], [rules_intrusive: select], [rules_custom: select], [rules_auth_attempt: select], [rate_limit: integer], [vuln_scan_adjusted: checkbox], [vuln_scan_adjusted_type: select], [vuln_scan_adjusted_vulns: text])` — Update Scan Profile

_remediation_
- `delete_scan_config(name: select)` — Delete Scan Configuration


---

## Vulnerability Manager

### `symantec-ccsvm` v1.0.0 _(installed)_
_Symantec CCSVM_

Symantec Control Compliance Suite Vulnerability Manager (CCS-VM) is the vulnerability management software solution designed from the ground up to provide organizations with context-aware vulnerability assessment and risk analysis.

**13 operation(s)**:

_investigation_
- `add_group(group: select)` — Create Group
- `execute_command(commands: text)` — Execute Command on PowerShell
- `get_asset_by_id(asset_id: integer)` — Get Asset By ID
- `get_assets_by_workgroup(work_group_id: text)` — Get Assets by Workgroup
- `get_retina_scan_result([scan_name: text], [output_as_attachment: checkbox], output_format: select)` — Get Scan Result
- `get_retina_scan_status([scan_name: text])` — Get Scan Status
- `get_vulnerabilities_by_asset_id(asset_id: integer)` — Get Vulnerabilities by Asset ID
- `get_vulnerabilities_by_vulnerability_ids(vulnerabilities_id: text)` — Get Vulnerabilities by Vulnerability IDs
- `search_assets([dns_name: text], [domain_name: text], [ip_addr: text], [mac_addr: text], [asset_type: text], [limit: text], [offset: text])` — Search Assets
- `start_new_retina_scan([scan_name: text], [DatabaseFileName: text], [ports: text], [port_groups: text], [audit_groups: text], [address_groups: text], [hosts: text])` — Configure and Run Scan
- `start_retina_scan([scan_name: text], [DatabaseFileName: text])` — Run Scan

_remediation_
- `delete_asset(asset_id: integer)` — Delete Asset
- `remove_group(group: select)` — Remove Group


---

## Vulnerability and Risk Management

### `bitcoin-abuse-db` v1.0.0 _(installed)_
_Bitcoin Abuse DB_

BitcoinAbuse.com is a public database of bitcoin addresses used by scammers, hackers, and criminals. This connector lets you tracking bitcoin addresses used by ransomware, blackmailers, fraudsters, etc.

**4 operation(s)**:

_investigation_
- `check_given_address(address: text)` — Check Address
- `get_all_reports(time_period: text)` — Get Complete Download
- `get_lookup_abuse_types()` — Get Lookup Abuse Types
- `get_lookup_distinct_reports([page: integer], [reverse: checkbox])` — Get Lookup Distinct Reports


### `circl-cve-search` v1.0.0 _(installed)_
_Circl CVE Search_

This app searches publicly known information from security vulnerabilities in software and hardware along with their corresponding exposures on CIRCL CVE database and returns the findings.

**6 operation(s)**:

_investigation_
- `browse_products(vendor: text)` — Get Products
- `browse_vendors()` — Get Vendors
- `current_cve_dbinfo()` — Get CVE DB Info
- `last_updated_cves()` — Get Last Updated CVEs
- `search_per_id(cve-id: text)` — Get CVE Details
- `search_per_product(vendor: text, product: text)` — Search Specific Product


### `fullhunt` v1.0.0 _(installed)_
_FullHunt_

FullHunt enables companies to discover all of their attack surfaces, monitor them for exposure and continuously scan them for the latest security vulnerabilities.

**3 operation(s)**:

_investigation_
- `get_domain_details(domain: text)` — Get Domain Details
- `get_specific_host_details(host: text)` — Get Details of a Specific Host
- `get_subdomain_of_domain(domain: text)` — Get Subdomains of a Domain


### `git-guardian` v1.0.0 _(installed)_
_GitGuardian_

GitGuardian is a cybersecurity platform that specializes in detecting and preventing the exposure of sensitive information in source code repositories, specifically Git repositories. It is designed to help organizations and developers protect their code and prevent the accidental or unauthorized exposure of credentials, API keys, tokens, and other sensitive data that may be present in code repositories.

**10 operation(s)**:

_investigation_
- `assign_a_secret_incident(incident_id: integer, [email: text], [member_id: integer])` — Assign Secret Incident 
- `content_scan(input: select, value: text, filename: text)` — Scan Documents Content
- `get_members_list([per_page: integer], [role: select], [search: text], [ordering: select], [cursor: text])` — Get Members List
- `list_secret_incidents([per_page: integer], [date_after: datetime], [date_before: datetime], [status: select], [severity: select], [validity: select], [tags: multiselect], [ordering: select], [assignee_email: text], [assignee_id: integer], [detector_group_name: text], [ignorer_id: integer], [resolver_id: integer], [cursor: text])` — Get Secret Incidents List
- `list_secret_occurrences([per_page: integer], [source_id: integer], [source_name: text], [incident_id: integer], [date_after: datetime], [date_before: datetime], [presence: text], [author_name: text], [author_info: text], [sha: text], [filepath: text], [ordering: text], [cursor: text], [tags: multiselect])` — Get Secret Occurrences List
- `list_sources([per_page: integer], [search: text], [last_scan_status: select], [health: select], [type: select], [ordering: select], [visibility: select], [cursor: text], [external_id: integer])` — Get Sources List
- `resolve_a_secret_incident(secret_revoked: checkbox, incident_id: integer)` — Resolve Secret Incident 
- `retrieve_a_secret_incident(incident_id: integer, [with_occurrences: integer])` — Get Secret Incident Details
- `unassign_a_secret_incident(incident_id: integer)` — Unassign Secret Incident 
- `update_a_secret_incident(incident_id: integer, severity: select)` — Update Secret Incident


### `git-guardian-enterprise` v1.0.0 _(installed)_
_GitGuardian Enterprise_

GitGuardian Enterprise is a security platform designed to detect, monitor, and remediate secrets (like API keys, passwords, and tokens) and sensitive data exposed in source code, CI/CD pipelines, containers, and developer environments.

**23 operation(s)**:

_investigation_
- `create_incident_secret_shared_link([id: text])` — Create Incident Secret Shared Link
- `create_keyword(id: integer, name: text, keyword: text, categories: multiselect, status: select, type: select, labels: text, created_at: datetime)` — Create Keyword
- `delete_incident_secret_shared_link([id: text])` — Delete Incident Secret Shared Link
- `delete_keyword(keyword_type: select)` — Delete Keyword
- `execute_an_api_call(method: select, endpoint: text, [query_params: json], [payload: json])` — Execute an API Request
- `export_keywords()` — Export Keywords
- `get_all_audit_logs([actor__in: text], [actor__nin: text], [actor_email: text], [ordering: text], [search: text], [type: text], [type__in: text], [type__nin: text], [page: integer], [per_page: integer])` — Get All Audit Logs
- `get_all_git_users(git_type: select, [page: integer], [per_page: integer])` — Get All Git Users
- `get_all_incident_keywords([page: integer], [per_page: integer])` — Get All Incident Keywords
- `get_all_incident_secrets([search: text], [severity: text], [status: text], [created_at__current: select], [created_at__from: datetime], [created_at__to: datetime], [ordering: text], [page: integer], [per_page: integer], [additional_fields: json])` — Get All Incident Secrets
- `get_all_keywords(keyword_type: select, [categories: select], [status: select], [type: select], [ordering: text], [search: text], [labels__in: text], [labels__nin: text], [status__in: text], [status__nin: text], [type__in: text], [type__nin: text], [page: integer], [per_page: integer])` — Get All Keywords
- `get_audit_log_actors_types(audit_log_metadata: select, [page: integer], [per_page: integer])` — Get Audit Log Actors/Types
- `get_audit_log_details([id: text])` — Get Audit Log Details
- `get_git_user_details(git_type: select)` — Get Git User Details
- `get_incident_keyword_details(id: text)` — Get Incident Keyword Details
- `get_incident_keyword_note(id: text)` — Get Incident Keyword Note
- `get_incident_secret_details([id: text])` — Get Incident Secret Details
- `get_incident_secret_note([id: text])` — Get Incident Secret Note
- `get_keyword_details(keyword_type: select)` — Get Keyword Details
- `rotate_incident_secret_shared_link([id: text])` — Rotate Incident Secret Shared Link
- `update_incident_keyword_status([id: text], action: select)` — Update Incident Keyword Status
- `update_incident_secret_status([id: text], action: select)` — Update Incident Secret Status
- `update_keyword_details(keyword_type: select, labels: text, name: text)` — Update Keyword Details


### `microsoft-defender-vulnerability-management` v1.0.0 _(installed)_
_Microsoft Defender Vulnerability Management_

Microsoft's Defender Vulnerability Management is a built-in module in Microsoft Defender for Endpoint that can discover vulnerabilities and misconfigurations in near real time, prioritize vulnerabilities based on the threat landscape and detections in your organization.

**5 operation(s)**:

_investigation_
- `get_specific_cve_details(cveId: text)` — Get Specific CVE ID Details
- `get_vulnerability_by_id(id: text)` — Get Vulnerability By CVE ID
- `list_devices_by_vulnerability(id: text)` — Get Devices By Vulnerability
- `list_vulnerabilities([id: text], [publishedOn: datetime], [severity: select], [$filter: text], [$skip: text], [$top: integer])` — Get All Vulnerabilities
- `list_vulnerabilities_by_machine_and_software([id: text], [cveId: text], [machineId: text], [severity: select], [$filter: text], [$skip: text], [$top: integer])` — Get Vulnerabilities By Machine And Software


### `qualys-web-application-scanner` v2.0.0 _(installed)_
_Qualys Web Application Scanning(WAS)_

Qualys Web Application Scanning (WAS) is a robust cloud-based application security product that continuously discovers, detects, and catalogs web applications and APIs.

**22 operation(s)**:

_investigation_
- `count_webapp([id: text], [name: text], [url: text], [tags.id: text], [tags.name: text], [createdDate: datetime], [updatedDate: datetime], [isScheduled: checkbox], [isScanned: checkbox], [lastScan.status: multiselect], [lastScan.date: datetime])` — Get Web Applications Count
- `create_tag(name: text, [criticalityScore: text], [ruleType: select], [ruleText: text], [provider: select], [color: text], [children: text])` — Create Tag
- `create_web_app(name: text, url: text, [id: integer])` — Create Web Application
- `delete_scan(scan_id: integer)` — Delete Scan
- `delete_tag(tag_id: integer)` — Delete Tag
- `delete_webapp(app_id: integer)` — Delete Web Applications
- `download_report(report_id: integer)` — Download Report
- `get_scan_details(scan_id: text)` — Get Scan Details
- `get_schedule_details(schedule_id: text)` — Get Schedule Details
- `get_webapp_details(id: text)` — Get Web Application Details
- `launch_scans(scan_name: text, scan_type: multiselect, web_app_id: integer, web_app_auth_record: checkbox, scanner_appliance: multiselect, profile_id: integer)` — Launch Scans
- `retrieve_scan_results(scan_id: text)` — Get Scan Results
- `retrieve_scan_status(scan_id: text)` — Get Scan Status
- `scan_count([id: text], [name: text], [webApp.name: text], [webApp.id: text], [webApp.tags.id: text], [reference: text], [launchedDate: datetime], [type: multiselect], [mode: multiselect], [status: multiselect], [authStatus: multiselect], [resultsStatus: multiselect])` — Get Scan Count
- `search_option_profiles([id: text], [name: text], [tags.id: text], [tags.name: text], [createdDate: datetime], [updatedDate: datetime], [usedByWebApps: checkbox], [usedBySchedules: checkbox], [owner.id: text], [owner.name: text], [owner.username: text], [limitResults: integer], [startFromOffset: integer])` — Search Option Profiles
- `search_reports([id: text], [name: text], [tags.id: text], [tags.name: text], [creationDate: datetime], [type: multiselect], [format: multiselect], [status: multiselect], [limitResults: integer], [startFromOffset: integer])` — Search Reports
- `search_scans([id: text], [name: text], [webApp.name: text], [webApp.id: text], [webApp.tags.id: text], [reference: text], [launchedDate: datetime], [type: multiselect], [mode: multiselect], [status: multiselect], [authStatus: multiselect], [resultsStatus: multiselect], [limitResults: integer], [startFromOffset: integer])` — Search Scans
- `search_schedule([id: text], [name: text], [owner.id: text], [createdDate: datetime], [updatedDate: datetime], [active: checkbox], [type: multiselect], [webApp.name: text], [webApp.id: text], [webApp.tags.id: text], [lastScan.status: multiselect], [lastScan.launchedDate: datetime], [multi: checkbox], [limitResults: integer], [startFromOffset: integer])` — Search Schedule
- `search_tags([id: text], [name: text], [parent: text], [criticalityScore: text], [ruleType: multiselect], [provider: multiselect], [color: text], [limitResults: integer], [startFromOffset: integer])` — Search Tags
- `search_users([id: text], [username: text], [limitResults: integer], [startFromOffset: integer])` — Search Users
- `search_webapp([id: text], [name: text], [url: text], [tags.id: text], [tags.name: text], [createdDate: datetime], [updatedDate: datetime], [isScheduled: checkbox], [isScanned: checkbox], [lastScan.status: multiselect], [lastScan.date: datetime], [limitResults: integer], [startFromOffset: integer], [verbose: checkbox])` — Search Web Applications
- `update_tag(id: text, [name: text], [criticalityScore: text], [ruleType: select], [ruleText: text], [color: text])` — Update Tag


### `shadowserver` v1.0.0 _(installed)_
_Shadowserver_

Shadowserver provides you with access to the most timely, critical Internet security like data collection,network reporting,investigation support ,reveal security vulnerabilities, expose malicious activity and help remediate victims.

**6 operation(s)**:

_investigation_
- `get_asn_query(query: text)` — Get ASN Query
- `get_malware_query(md5: text)` — Get Malware Query
- `get_origin_query(ip_address: text)` — Get Origin Query
- `get_peer_query(ip_address: text)` — Get Peer Query
- `get_prefix_query(query: text)` — Get Prefix Query
- `get_programs_query(query: text)` — Get Programs Query


### `vuln-db` v1.0.0 _(installed)_
_VulnDB_

VulnDB is the most comprehensive and timely vulnerability intelligence available and provides actionable information about the latest in security vulnerabilities. This connector facilitates the automated operations related to vulnerabilities, products, and vendors.

**6 operation(s)**:

_investigation_
- `get_product_details([vendor: select], [limit: integer])` — Get Product Details
- `get_product_version(product: select, [limit: integer])` — Get Product Version
- `get_vendor_details([vendor: select], [limit: integer])` — Get Vendor Details
- `get_vuln_by_vendor_and_product(vendor_id: text, product_id: text, [limit: integer])` — Get Vulnerability By Vendor and Product
- `get_vuln_details(filter_by: select, [limit: integer])` — Get Vulnerability Details
- `get_vuln_list([start_date: datetime], [end_date: datetime], [limit: integer])` — Get Vulnerability List


---

## WAF

### `f5-big-ip-waf` v1.0.0 _(installed)_
_F5 BIG-IP WAF_

F5 BIG-IP WAF connector block/unblock IP address or range, create network firewall policy and associated rules, list out network policies and corresponding rules etc.

**14 operation(s)** (+5 hidden):

_investigation_
- `apply_policy(virtual_server: text, partition: text, [enforcement: select], [staging: select])` — Apply Network Firewall Policy to Virtual Server
- `list_policies([partition: text])` — Get List of Network Firewall Policies
- `list_policy_rules(policy_name: text, partition: text)` — Get List of Policy Rules
- `list_virtual_servers()` — Get List of Virtual Servers
- `update_policy_rule(policy_name: text, partition: text, name: text, [status: select], [ipProtocol: select], [action: select], [entry_action: select], [irule: select], [iruleSampleRate: text], [virtualServer: select], [servicePolicy: select], [protocolInspectionProfile: select], [classificationPolicy: text], [log: checkbox])` — Update Network Firewall Policy Rule

_miscellaneous_
- `create_policy(name: text, partition: text, [description: text])` — Create Network Firewall Policy
- `create_policy_rule(policy_name: text, partition: text, name: text, status: select, ipProtocol: select, add_rule: select, action: select, [source: text], [destination: text], [irule: select], [iruleSampleRate: text], [virtualServer: select], [servicePolicy: select], [protocolInspectionProfile: select], [classificationPolicy: text], [log: checkbox])` — Create Network Firewall Policy Rule
- `delete_policy(policy_name: text, partition: text)` — Delete Network Firewall Policy
- `delete_policy_rule(policy_name: text, partition: text, rule_name: text)` — Delete Network Firewall Policy Rule


### `imperva-securesphere-waf` v1.0.0 _(installed)_
_Imperva SecureSphere WAF_

Imperva SecureSphere WAF connector block/unblock IP address and network

**6 operation(s)**:

_containment_
- `policy_block_ip(policy_action: select)` — Policy to Block IP

_investigation_
- `get_all_custom_policies()` — Get All Web Service Custom Policies
- `get_custom_policy(policy_name: text)` — Get Web Service Custom Policy Details
- `get_ip_group(ip_group: text)` — Get IP Group
- `update_ip_group(ip_group_name: text, ip: text, action: select)` — Update IP Group

_remediation_
- `policy_unblock_ip(policy_name: text, [severity: select], [ip_group_name: text], [ip: text])` — Update Policy to Unblock IP


---

## Web Application

### `fortinet-fortiproxy` v1.0.1 _(installed)_
_Fortinet FortiProxy_

FortiProxy provides a secure web gateway, which protects against web attacks with URL filtering, visibility and control of encrypted web traffic through SSL and SSH inspection, and application of granular web application policies. This connector facilitates automated operation related to firwall policy, firewall address, firewall address group, firewall service group, and banned users.

**26 operation(s)**:

_investigation_
- `add_users_to_banned_list(ip_addresses: text, expiry: integer)` — Add Users to Banned List
- `clear_all_banned_users_list()` — Clear All Banned Users List
- `clear_banned_users_list_by_ip(ip_addresses: text)` — Clear Banned Users List by IP
- `create_firewall_address(name: text, [type: select], [interface: text], [vdom: text], [action: text], [nkey: text], [custom_attributes: json])` — Create Firewall Address
- `create_firewall_address_group(name: text, member: json, [type: select], [comment: text], [exclude: select], [color: integer], [allow-routing: select], [fabric-object: select], [vdom: text], [action: text], [nkey: text], [custom_attributes: json])` — Create Firewall Address Group
- `create_firewall_policy(name: text, schedule: text, [type: select], [srcaddr: json], [dstaddr: json], [srcaddr6: json], [dstaddr6: json], [policyid: integer], [policy_action: select], [status: select], [vdom: text], [action: text], [nkey: text], [custom_attributes: json])` — Create Firewall Policy
- `create_firewall_service_group(name: text, [proxy: select], [member: json], [color: integer], [comment: text], [fabric-object: select], [vdom: text], [action: text], [nkey: text])` — Create Firewall Service Group
- `deauthenticate_firewall_users(user_type: text, id: integer, ip: text, [ip_version: text], [method: text], [all: checkbox], [users: json])` — DeAuthenticate Firewall Users
- `delete_firewall_address(name: text, [vdom: text])` — Delete Firewall Address
- `delete_firewall_address_group(name: text, [vdom: text])` — Delete Firewall Address Group
- `delete_firewall_policy(policyid: integer, [vdom: text])` — Delete Firewall Policy
- `delete_firewall_service_group(name: text, [vdom: text])` — Delete Firewall Service Group
- `get_all_banned_users_list()` — Get All Banned Users List
- `get_authenticated_firewall_users_list([start: integer], [count: integer], [ipv4: checkbox], [ipv6: checkbox])` — Get Authenticated Firewall Users List
- `get_firewall_address([datasource: checkbox], [start: integer], [count: integer], [with_meta: checkbox], [with_contents_hash: checkbox], [skip: checkbox], [format: text], [filter: text], [key: text], [pattern: text], [scope: text], [exclude-default-values: checkbox], [meta_only: checkbox], [action: select], [vdom: text])` — Get Firewall Address
- `get_firewall_address_details(name: text, [datasource: checkbox], [with_meta: checkbox], [skip: checkbox], [format: text], [action: select], [vdom: text])` — Get Firewall Address Details
- `get_firewall_address_group([datasource: checkbox], [start: integer], [count: integer], [with_meta: checkbox], [with_contents_hash: checkbox], [skip: checkbox], [format: text], [filter: text], [key: text], [pattern: text], [scope: text], [exclude-default-values: checkbox], [meta_only: checkbox], [action: select], [vdom: text])` — Get Firewall Address Group
- `get_firewall_address_group_details(name: text, [datasource: checkbox], [with_meta: checkbox], [skip: checkbox], [format: text], [action: select], [vdom: text])` — Get Firewall Address Group Details
- `get_firewall_policy([datasource: checkbox], [start: integer], [count: integer], [with_meta: checkbox], [with_contents_hash: checkbox], [skip: checkbox], [format: text], [filter: text], [key: text], [pattern: text], [scope: text], [exclude-default-values: checkbox], [meta_only: checkbox], [action: select], [vdom: text])` — Get Firewall Policy
- `get_firewall_policy_details(policyid: integer, [datasource: checkbox], [with_meta: checkbox], [skip: checkbox], [format: text], [action: select], [vdom: text])` — Get Firewall Policy Details
- `get_firewall_service_group([datasource: checkbox], [start: integer], [count: integer], [with_meta: checkbox], [with_contents_hash: checkbox], [skip: checkbox], [format: text], [filter: text], [key: text], [pattern: text], [scope: text], [exclude-default-values: checkbox], [meta_only: checkbox], [action: select], [vdom: text])` — Get Firewall Service Group
- `get_firewall_service_group_details(name: text, [datasource: checkbox], [with_meta: checkbox], [skip: checkbox], [format: text], [action: select], [vdom: text])` — Get Firewall Service Group Details
- `update_firewall_address(name: text, [type: select], [interface: text], [vdom: text], [action: text], [nkey: text], [before: text], [after: text], [custom_attributes: json])` — Update Firewall Address
- `update_firewall_address_group(name: text, [member: json], [comment: text], [exclude: select], [color: integer], [allow-routing: select], [fabric-object: select], [vdom: text], [action: text], [before: text], [after: text], [custom_attributes: json])` — Update Firewall Address Group
- `update_firewall_policy(policyid: integer, [name: text], [schedule: text], [type: select], [srcaddr: json], [dstaddr: json], [srcaddr6: json], [dstaddr6: json], [policy_action: select], [status: select], [vdom: text], [action: text], [nkey: text], [before: text], [after: text], [custom_attributes: json])` — Update Firewall Policy
- `update_firewall_service_group(name: text, [member: json], [color: integer], [comment: text], [fabric-object: select], [vdom: text], [action: text], [before: text], [after: text])` — Update Firewall Service Group


---

## Web Application Security

### `tcell` v1.0.0 _(installed)_
_TCell_

TCell is a web application security platform which protects web apps deployed in the cloud using web server and app server agents that integrate easily with your deployment process. This connector facilitates the automated operations like get applications,agents,routes,inline scripts,packages,events and configs

**7 operation(s)**:

_investigation_
- `get_agents(app_id: text, [agent_id: text])` — Get Agents
- `get_apps([app_id: text])` — Get Applications
- `get_configs(app_id: text, [config_id: text])` — Get Configurations
- `get_events(app_id: text, sources: text, [event_id: text])` — Get Events
- `get_inline_scripts(app_id: text, [inline_script_id: text])` — Get Inline Scripts
- `get_packages(app_id: text, [package_id: text])` — Get Packages
- `get_routes(app_id: text, [route_id: text])` — Get Routes


---

## Web Gateway

### `mcafee-web-gateway` v1.0.0 _(installed)_
_McAfee Web Gateway_

A McAfee Web Gateway connects your network to the web and filters the traffic that goes out from your network and comes into your network. This connector provides automated actions for list and rules sets on McAfee Web Gateway used for Filtering.

**10 operation(s)**:

_investigation_
- `create_empty_list(name: text, type: select)` — Create Empty List
- `delete_list(list_name: text)` — Delete List
- `delete_list_entry(list_name: text, entry_number: integer)` — Delete List Entry
- `get_all_list_entries(list_name: text)` — Get All List Entries
- `get_details_of_list_entry(list_name: text, entry_number: integer)` — Get Details of List Entry
- `get_list_details(list_name: text)` — Get List Details
- `get_lists([filters: select], [page_size: integer], [page: integer])` — Get Lists
- `get_rule_set_details(rule_id: integer)` — Get Rule Set Details
- `get_rule_sets()` — Get Rule Sets
- `insert_list_entry(list_type: select, list_name: text, entry: text, [description: text], [entry_number: integer])` — Insert List Entry in Simple List


---

## Web Security

### `forcepoint-websense` v1.0.0 _(installed)_
_Forcepoint Websense_

Forcepoint Websense connector provides actions like, create/delete API-managed categories, list out all or API-managed categories, update API-managed categories.

**6 operation(s)**:

_containment_
- `add_category(category_name: text, parent_category_id: text, [category_description: text], [urls: text], [ip_addresses: text])` — Create API-managed Category
- `update_category(refer_by: select, category_value: text, [urls: text], [ip_addresses: text])` — Update API-managed Category

_investigation_
- `get_category_details(refer_by: select, category_value: text)` — Get API-managed Category Details
- `list_categories([api_managed_category: checkbox])` — Get All Categories

_remediation_
- `delete_address_from_category(refer_by: select, category_value: text, [urls: text], [ip_addresses: text])` — Delete URLs and IP addresses
- `delete_categories(refer_by: select, category_value: text)` — Delete API-managed Categories


---

## Windows Endpoint Management

### `microsoft-sccm` v1.0.0 _(installed)_
_Microsoft SCCM_

Microsoft SCCM Connector

**3 operation(s)**:

_investigation_
- `get_device_collections()` — Get All Device Collections
- `get_patches()` — Get All Software Updates

_remediation_
- `deploy_patch(patch_name: text, collection_name: text, [additional_params: textarea])` — Deploy Patch


### `microsoft-wmi` v1.1.0 _(installed)_
_Microsoft WMI_

Microsoft WMI provides investigative actions like, get system services, get processes, get system information etc. that are executed on a Windows endpoint.

**5 operation(s)**:

_investigation_
- `get_processes(endpoint: text)` — Get Processes
- `get_services(endpoint: text)` — Get Services
- `get_system_information(endpoint: text)` — Get System Information
- `get_users(endpoint: text)` — Get Users
- `run_Query(endpoint: text, query: text)` — Run Query


---

## Wireless Network Mapping

### `wigle` v1.0.0 _(installed)_
_WiGLE_

Wireless Geographic Logging Engine for collecting information about the different wireless hotspots around the world. WiGLE connector for network lookup, network details, cell search and getting statistics

**9 operation(s)**:

_investigation_
- `cell_search(onlymine: checkbox, showGsm: checkbox, showCdma: checkbox, [ssid: text], [notmine: checkbox], [ssidlike: text], [latrange1: text], [latrange2: text], [longrange1: text], [longrange2: text], [lastupdt: datetime], [startTransID: text], [endTransID: text], [cell_op: text], [cell_net: text], [cell_id: text], [qos: text], [searchAfter: integer], [resultsPerPage: integer])` — Cell Search
- `get_network_details(netid: text, [operator: integer], [lac: integer], [cid: integer], [system: integer], [network: integer], [basestation: integer])` — Get Network Details
- `get_statistics_by_countries()` — Get Country Statistics
- `get_statistics_by_general()` — Get General Statistics
- `get_statistics_by_group()` — Get Group Statistics
- `get_statistics_by_regions([country: text])` — Get Region Statistics
- `get_statistics_by_site()` — Get Site Statistics
- `get_statistics_by_user()` — Get User Statistics
- `lookup_network(onlymine: checkbox, freenet: checkbox, paynet: checkbox, [notmine: checkbox], [latrange1: text], [latrange2: text], [longrange1: text], [longrange2: text], [lastupdt: datetime], [startTransID: text], [endTransID: text], [encryption: text], [netid: text], [ssid: text], [ssidlike: text], [qos: text], [searchAfter: integer], [resultsPerPage: integer])` — Lookup Network


---

## breach_analysis

### `anomali-enterprise` v1.0.0 _(installed)_
_Anomali Enterprise_

Anomali Enterprise is a threat and breach analytics platform that applies correlation rules and advanced security analysis to cross-correlate data from SIEMs (ArcSight ESM and Splunk) and other event sources deployed in your network to threat intelligence available from ThreatStream. This connector facilitates automated operations to search all Anomali data, Run retrospective search, Download search result etc.

**6 operation(s)**:

_investigation_
- `download_search_results(filepath: text)` — Download the Search Results
- `get_search_status(job_id: text)` — Get Retrospective Search Status
- `identify_dga_domain(domains: text)` — Identify DGA Domains
- `run_retrospective_search(time_range: select, intelligence: text)` —  Run a Retrospective/Forensic Search
- `search_in_anomali(index_name: select, query: text, time_range: select)` — Search in Anomali Enterprise Data
- `upload_asset_information(selected_option: select)` — Upload Asset Information


---

## darkweb

### `darkowl` v1.0.0 _(installed)_
_DarkOwl_

DarkOwl allows you to access the world's largest database of darknet content to monitor for the presence of your data on the darknet and shorten the timeframe to its detection. DarkOwl Connector provides automated actions to get documents, Scores and perform search.

**6 operation(s)**:

_investigation_
- `get_document(document_id: text)` — Get Document
- `get_score_request_result(request_id: text)` — Get Score Request Result
- `get_score_request_status(request_id: text)` — Get Score Request Status
- `get_usage_status()` — Get Usage Status
- `search_resource(q: text, [from: datetime], [to: datetime], [req: checkbox], [simliar: checkbox], [highlight: checkbox], [sort: select], [detail: select], [has: multiselect], [email_domain: text], [loc: text], [lang: text], [domain: text], [ip: text], [leak: text], [offset: integer], [count: integer], [cccn: text], [cssn: text], [cemail: text], [hack: text])` — Search Resource
- `submit_score_request(domains: text, email_domains: text)` — Submit Score Request


---

## firewall

### `checkpoint-firewall` v2.1.0 _(installed)_
_Check Point Firewall_

Check Point Firewall that can use for block/unblock IP, Application, URL

**14 operation(s)**:

_containment_
- `block_applications(app_list: text)` — Block Applications
- `block_ip(ip_address_list: text)` — Block IP Address
- `block_urls(url_list: text)` — Block URLs

_investigation_
- `check_policies()` — Validate Configuration Policies
- `get_blocked_application_names()` — Get Blocked Application Names
- `get_blocked_ip_addresses()` — Get Blocked IP Addresses
- `get_blocked_urls()` — Get Blocked URLs
- `get_list_of_applications(start_index: integer, limit: integer)` — Get Applications Detail
- `get_session(session_id: text)` — Get Session
- `show_sessions()` — Get Sessions

_remediation_
- `discard_session(session_uid: text)` — Terminate Session
- `unblock_applications(app_list: text)` — Unblock Applications
- `unblock_ip(ip_address_list: text)` — Unblock IP Address
- `unblock_urls(url_list: text)` — Unblock URLs


### `f5-big-ip` v1.0.0 _(installed)_
_F5 BIG IP_

This connector supports containment and remediation Actions like block IP or unblock IP

**2 operation(s)**:

_containment_
- `block_ip(source_address: text, policy: text, partition: text, rule_name: text, action: select)` — Block IP

_remediation_
- `unblock_ip(policy: text, policy_path: text, rule_name: text)` — Unblock IP


### `pfsense` v1.0.0 _(installed)_
_PfSense_

PfSense Connector capable of adding/deleting firewall rules on PfSense platform

**3 operation(s)**:

_containment_
- `add_rule(rule_id: integer, rule: select, interface: text, ipprotocol: select, protocol: select, [source: text], [destination: text], [description: text])` — Add Rule

_investigation_
- `get_rules()` — Get All Rules

_remediation_
- `delete_rule(rule_id: integer)` — Delete Rule


---

## information

### `abuseipdb` v2.0.0 _(installed)_
_AbuseIPDB_

AbuseIPDB Connector helps to report and identify IP addresses that have been associated with malicious activity online

**3 operation(s)**:

_investigation_
- `get_ip_blacklist([confidenceMinimum: text], [limit: integer])` — Get IP Blacklist
- `ip_lookup(ip: text, [days: integer])` — IP Lookup

_miscellaneous_
- `report_ip(ip: text, categories: multiselect, [comment: text])` — Report IP


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


### `stellar-cyber` v1.0.0 _(installed)_
_Stellar Cyber_

Connector facilitates automated operations to perform ElasticSearch DSL query of the index on your Stellar Cyber(Starlight) server.

**2 operation(s)** (+1 hidden):

_investigation_
- `search_query([index: text], [query: text])` — Search Query


### `symantec-icdx` v1.0.0 _(installed)_
_Symantec ICDX_

Unifying cloud and on-premises security to provide advanced threat protection and information protection across all endpoints, networks, email, and cloud applications.

**1 operation(s)**:

_investigation_
- `search(attribute: select, [attribute_value: text], [search_criteria: select], [event_attribute: select], [event_attribute_value: text], time_span: select, [limit: integer], [next: text], [open_query: text])` — Search Events


### `symantec-security-analytics` v2.0.0 _(installed)_
_Symantec Security Analytics_

Symantec Security Analytics connector provides automated operations for advanced network forensics, and real-time content inspection for all network traffic.

**15 operation(s)**:

_investigation_
- `get_alerts_list([filter_key: text], [filter_operator: select], [filter_value: text], [sensor_id: text], startDate: datetime, endDate: datetime, [direction: select], [page: integer], [limit: integer], [advance_filter: text])` — Get Alerts
- `get_alerts_timeline_data([filter_key: text], [filter_operator: select], [filter_value: text], startDate: datetime, endDate: datetime, [sensor_id: text], [advance_filter: text])` — Get Alerts Timeline Data
- `get_all_providers()` — List All Enrichment Providers
- `get_artifact_reputation([sensor_id: text], artifact_id: integer, [provider: text], [artifactField: text])` — Get Artifact Reputation
- `get_artifact_rootcause([sensor_id: text], id: integer, artifactSearchId: integer)` — Get Artifact Rootcause
- `get_details_extractions([sensor_id: text], artifact_id: integer, search_id: text)` — Search for Artifacts in Extraction
- `get_sensor_list([sort: select], [direction: select], [page: integer], [limit: integer])` — Get Sensor List
- `get_sensor_status([sensor_id: text])` — Get Sensors Status
- `start_extractions([sensor_id: text], extracted_by: select, finish_count: integer)` — Start Artifact Extractions
- `start_extractions_for_ip_address([sensor_id: text], extracted_by: select, finish_count: integer)` — Start Extractions for IP Address
- `start_extractions_for_md5([sensor_id: text], extracted_by: select, finish_count: integer)` — Start Extractions for MD5
- `start_extractions_for_port([sensor_id: text], extracted_by: select, finish_count: integer)` — Start Extractions for Port
- `start_extractions_for_protocol([sensor_id: text], extracted_by: select, finish_count: integer)` — Start Extractions for Protocol
- `start_extractions_for_sha1([sensor_id: text], extracted_by: select, finish_count: integer)` — Start Extractions for SHA1
- `start_extractions_for_sha256([sensor_id: text], extracted_by: select, finish_count: integer)` — Start Extractions for SHA256


---

## netbios

### `netbios` v1.0.1 _(installed)_
_NetBIOS_

This connector provides various investigation actions over the NetBIOS protocol.

**1 operation(s)**:

_investigation_
- `ip_lookup(ip: text, [port: integer], [timeout: integer])` — Get Hostname


---

## network_security

### `infoblox-bloxone-threat-defense` v1.2.0 _(installed)_
_Infoblox BloxOne Threat Defense_

Infoblox BloxOne Threat Defense provides foundational security that improves the efficiency of security operations centers by streamlining and automating threat response, reducing complexity, and enhancing the capabilities and performance of existing security investments.

**15 operation(s)** (+3 hidden):

_investigation_
- `create_dossier_source_lookup_job(indicator_type: select, value: text, [source: multiselect], [wait: checkbox])` — Create a Dossier Source Lookup Job
- `dossier_reputation(indicatorType: select, indicatorValue: text, [waitForTaskCompletion: checkbox])` — Get Dossier Reputation of Indicator
- `get_all_dossier_source()` — Get All Dossier Sources
- `get_dossier_lookup_job_status(job_id: text)` — Get Dossier Lookup Job Status
- `get_dossier_sources_by_indicator_type(indicator_type: select)` — Get Dossier Sources By Indicator Type
- `get_named_lists([_filter: text], [_fields: text], [_offset: integer], [_limit: integer], [_page_token: text])` — Get Named Lists
- `get_specific_named_list(id: text, [_fields: text])` — Get Specific Named List
- `get_task_details_for_lookup_job(job_id: text, task_id: text)` — Get Specific Task Details of Dossier Lookup Job
- `get_task_results_of_dossier_lookup_job(job_id: text)` — Get the Task Results of a Dossier Lookup Job
- `get_valid_indicator_types_for_source(source_id: select)` — Get Valid Indicator Types for Source
- `lookalike_domain_search()` — Search Lookalike Domain
- `lookalike_domain_search_with_classification()` — Search Lookalike Domain With Classification


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

## networking

### `netwitness` v1.0.1 _(installed)_
_NetWitness_

RSA NetWitness connector

**5 operation(s)**:

_investigation_
- `get_meta_from_type(type: select, value: text, [start_time: text], [end_time: text])` — Get Meta
- `get_pcap(session_id: text)` — Get PCAP for Session Ids
- `get_pcap_from_type(type: select, value: text, [start_time: text], [end_time: text])` — Get PCAP
- `get_raw_query(query: text)` — Make Raw NetWitness Query
- `get_session_ids_from_where_stmnt(query: text)` — Get Session Ids from a where statement


### `rsa-netwitness-logs-and-packets` v1.0.2 _(installed)_
_RSA Netwitness Logs and Packets_

RSA Netwitness Logs and Packets collects real-time network data from sessions. This connector facilitates the automated operations like get PCAP data and metadata from IP Address, Domain and Username, query Netwitness

**5 operation(s)**:

_investigation_
- `get_meta_from_type(type: select, keys: text, value: text, [start_time: datetime], [end_time: datetime], [size: integer])` — Get Metadata
- `get_pcap(session_id: text)` — Get PCAP Data for Session IDs
- `get_pcap_from_type(type: select, keys: text, value: text, [start_time: datetime], [end_time: datetime], [size: integer])` — Get PCAP Data
- `get_raw_query(query: text, [size: integer])` — Netwitness Search
- `get_session_ids_from_where_stmnt(query: text, [size: integer])` — Get Session IDs


---

## protection

### `juniper-sky-atp` v1.0.0 _(installed)_
_Juniper Sky ATP_

Juniper Sky Advanced Threat Protection Connector

**3 operation(s)**:

_containment_
- `add_infected_host(infected_ip: text, list_type: select)` — Add Infected Host
- `delete_infected_host(ip_to_delete: text, list_type: select)` — Delete Infected Host
- `get_infected_hosts()` — Get All Infected Hosts


---

## sandbox

### `symantec-cas` v1.0.0 _(installed)_
_Symantec CAS_

Symantec MAS(Malware Analysis Service) is a part of Symantec CAS(Content Analysis Service), provides protectsion against advanced threats through file reputation, multiple antimalware techniques, and sophisticated sandbox detonation. This connector facilitates automated operations like submit file/URL, create task, get status, get report and detonate file

**8 operation(s)**:

_investigation_
- `create_task(sample_id: integer, [environment: select], [priority: select], [profile: text], [primary_resource: text])` — Create Task
- `detonate_file(file_reference: select, reference_id: text, [owner: text], environment: select, priority: select, timeout: integer, [profile: text], [source: text], [label: text], [description: text])` — Detonate File
- `get_report(task_id: integer)` — Get Report
- `get_risk_score(task_id: integer)` — Get Risk Score
- `get_sample_task(sample_id: integer)` — Get Sample's Task
- `get_task_statistics(task_id: integer)` — Get Task Statistics
- `submit_file([file_reference: select], [reference_id: text], owner: text, [source: text], [label: text], [target_name: text], [description: text], [extension: text], [resource_id: integer], [exec_arguments: text])` — Submit Sample
- `submit_url(sample_url: text, owner: text, [source: text], [exec_arguments: text], [label: text], [description: text])` — Submit URL


---

## threat_intel

### `anomali-staxx` v1.0.0 _(installed)_
_Anomali STAXX_

Anomali STAXX gives you an easy way to access any STIX/TAXII feed. This connector facilitates automated operations like import indicators and get indicators.

**2 operation(s)**:

_investigation_
- `get_indicators(query: text, file_type: select, [size: text], [add_as_attachment: checkbox])` — Get Indicators
- `import_indicators([file_name: text], [reference_id: text], [intelligence: text], threat_type: select, confidence: integer, severity: select, tlp: select, [tags: text], [approval: checkbox])` — Import Indicators


### `soltra-edge` v1.0.0 _(installed)_
_Soltra Edge_

Soltra Edge leverages the open industry standards of STIX and TAXII to collect threat intelligence from various sources and convert it into the industry-standard language. This connector facilitates automated operations like get STIX object, upload STIX etc.

**3 operation(s)**:

_investigation_
- `get_stix_object(id: text)` — Get STIX object
- `search_stix([query: text], [type: text], [subtype: text], [tlp: select], [namespace: text], [year: intger], [month: intger], [day: intger])` — Search STIX objects
- `upload_stix([file_ref: select], [reference_id: text])` — Upload STIX Package


---

## ticketing

### `serviceaide` v1.0.0 _(installed)_
_Service Aide_

Searches and submits tickets to the ServiceAide Service Desk

**3 operation(s)**:

_miscellaneous_
- `get_ticket(ticket_id: text)` — Get Ticket
- `list_tickets()` — List Tickets
- `report_incident([requester: text], [description: textarea], [impact: select], [urgency: select], [priority: select])` — Report an Incident Ticket


---

## utilities

### `airwatch` v1.0.0 _(installed)_
_AirWatch_

AirWatch Connector which enables profile and product settings to be manipulated within the platform

**7 operation(s)**:

_investigation_
- `get_device_information(search_parameter: text, [search_by: select])` — Get Device Information
- `get_product(product_id: text)` — Get Product
- `get_profile(profile_id: text)` — Get Profile

_miscellaneous_
- `activate_product(product_id: text)` — Activate Product
- `activate_profile(profile_id: text)` — Activate Profile
- `deactivate_product(product_id: text)` — Deactivate Product
- `deactivate_profile(profile_id: text)` — Deactivate Profile


### `code-snippet` v2.1.4 _(installed, system)_
_Code Snippet_

Execute code snippets as part of your Playbooks.

**2 operation(s)**:

- `python_inline(python_function: textarea)` — Execute Python Code (Deprecated)
- `python_inline_code_editor(python_function: codeEditor)` — Execute Python Code


### `database` v2.2.1 _(installed)_
_Database_

Database connector can be used to connect to a database and then query the database and retrieve data. You can connect to multiple databases by setting up multiple configurations.

**1 operation(s)**:

- `db_query(query_string: text)` — Query DB


### `floodlight` v1.0.0 _(installed)_
_Floodlight_

Floodlight Connector which utilizes Java OpenFlow controller

**4 operation(s)**:

_containment_
- `block_ip(protocol: text, src: text, dst: text, port: text)` — Block IP
- `block_mac(switchid: text, src: text, dst: text, priority: text)` — Block MAC Address
- `unblock_ip(ip_id: text)` — Unblock IP
- `unblock_mac(mac_id: text)` — Unblock MAC Address


### `imap` v3.5.8 _(installed, system, ingestion)_
_IMAP_

Steps related to fetching and parsing email

**2 operation(s)** (+1 hidden):

- `fetch_email_new([limit_count: integer], [parse_inline_image: checkbox])` — Fetch Email(s)


### `ocr-space` v1.0.0 _(installed)_
_OCRSpace_

The OCR API provides a simple way of parsing images and multi-page PDF documents (PDF OCR) and extract text results. This connector facilitates automated operations related to extracting data from image or document.

**1 operation(s)**:

_investigation_
- `parse_image(image_source: select)` — Parse Image


### `samba` v2.0.0 _(installed)_
_SAMBA_

Performs samba operations such as file transfer or authentication over SMB protocol

**5 operation(s)**:

_investigation_
- `create_directory(smb_path: text)` — Create Directory
- `delete_directory(smb_path: text)` — Remove Directory Content
- `file_download(path: text, file_name: text)` — Download File
- `list_content(smb_path: text)` — Get Directory Content
- `upload_file(ref_id: text, path: text, action_exists: select)` — Upload File


### `scp` v1.0.1 _(installed)_
_SCP_

SCP connector to send and receive files and directories to/from a remote machine.

**2 operation(s)**:

_miscellaneous_
- `receive_file(hostname: text, username: text, password: password, local_path: text, remote_path: text, [recursive: checkbox], [preserve_times: checkbox])` — Receive File
- `send_file(hostname: text, username: text, password: password, filename: text, remote_path: text, [recursive: checkbox], [preserve_times: checkbox])` — Send File


### `smtp` v2.6.0 _(installed, system)_
_SMTP_

Steps related to sending email

**6 operation(s)** (+4 hidden):

- `send_email([to_recipients: text], [cc_recipients: text], [bcc_recipients: text], [body: richtext], [subject: text], [iri_list: text], [to: text], [cc: text], [bcc: text], [from: text], [content: text], [content_type: text], [file_path: text], [file_name: text])` — Send Email
- `send_email_new(type: select, [from: text], body_type: select, [file_path: text], [file_name: text], [iri_list: text])` — Send Email (Advanced)


### `soap` v2.4.1 _(installed)_
_SOAP_

Steps related to making SOAP requests

**4 operation(s)** (+2 hidden):

- `soap_call(func_name: text, [func_params: text], [extra_headers: text])` — SOAP Call (Generic)
- `soap_client(service_name: select, [extra_headers: text])` — SOAP Call


### `ssh` v2.1.2 _(installed)_
_SSH_

Steps that use an ssh connection. Including sftp and remote code execution

**2 operation(s)**:

- `run_remote_command(cmd: text, [allowed_exit: text], [is_super_user: checkbox])` — Execute remote command
- `run_remote_python(script: text, [version: text])` — Execute a python script


### `symantec-webpulse-site-review` v1.0.0 _(installed)_
_Symantec WebPulse Site Review_

Site Review allows users to check and dispute the current WebPulse categorization for any URL

**1 operation(s)**:

_investigation_
- `url_review(site_url: text)` — Check Category of Domain or URL


### `trendmicro-endpoint-sensor` v1.0.0 _(installed)_
_Trend Micro Endpoint Sensor_

Connector for Trend Micro Endpoint Sensor which can be used to automate retro scans and retrieve their results

**5 operation(s)**:

_investigation_
- `check_task_status(task_guid: text)` — Check Task Status
- `get_endpoints_for_task(task_guid: text)` — Get Endpoints for Task
- `get_report_summary(task_guid: text, endpoint_guid: text)` — Get Report Summary
- `retro_scan([endpoint_guid: text], [name: text], [tag: text], investigation_criteria: multiselect)` — Retro Scan
- `search_endpoint_by_ip(src_ip: text)` — Search Endpoint By IP


### `ultipro` v1.0.0 _(installed)_
_Ultipro_

This connector is capable of querying Ultipro for Employee, Job, and Phone details.

**5 operation(s)**:

- `findEmployeePhone(pageNumber: text, pageSize: integer)` — Find Employee Phones
- `getAllCompanyEmployees(pageNumber: text, pageSize: text)` — Get All Employees
- `getEmploymentDetails([companyId: text])` — Get Employment Details
- `getPersonDetails([companyId: text])` — Get Person Details
- `getPhoneInformationByEmployeeIdentifier(employeeId: text)` — Get Employee Phone Information


### `web-scraper` v1.0.0 _(installed)_
_Web Scraper_

Web scraping is data scraping used for extracting data from websites. This connector facilitates automated operations related to extracting data from websites.

**2 operation(s)**:

- `get_screenshot(url: text)` — Get Web Page Screenshot
- `get_web_page_source(url: text)` — Get Web Page Source


---

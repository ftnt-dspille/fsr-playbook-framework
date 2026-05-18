# Real-world playbook prompts — evaluation corpus

Diverse user-spoken prompts covering SOC / NOC / ITOps / DevOps. Each
exercises a primary playbook-building capability plus secondary skills
the orchestrator must compose.

These are reference prompts. A subset is wired as eval tasks under
`python/evals/tasks/`. Add or evolve prompts here first, then promote
the highest-signal ones into tasks.

## Matrix coverage

| Capability | Covered by prompts |
|---|---|
| Trigger types: `start`, `start_on_create`, `start_on_update`, designer manual, scheduled | 1–14 collectively |
| Connector op invocation + picklist params | 1, 3, 7, 8, 11 |
| Picklist-valued returns + decisions on them | 1, 7 |
| `decision` binary / 3-way / nested | 1 (binary), 7 (3-way), 11 (nested) |
| `manual_input` — approval-only | 1, 11 |
| `manual_input` — typed inputs | 4, 6 |
| `find_record` correlation / module joins | 3, 6, 9, 12 |
| `find_record` date-bounded / filtered | 12, 14 |
| `for_each` over collections | 4, 6, 12 |
| `workflow_reference` with param passing | 2, 4, 11 |
| `delay` + re-poll | 5, 9, 12 |
| `set_variable` for audit / aggregation | 1, 6, 14 |
| `code_snippet` (genuine Python escape hatch) | 14 |
| HTTP-fallback path (no native op) | 13 |
| Error / early-exit branching | 4, 11 |
| Multi-connector hand-off | 1, 3, 4, 11 |
| Long-running / wait states | 5, 6, 9, 12 |
| Comment / message posting back to triggering record | 1, 10, 11 |
| `vars.steps.<slug>.<key>` cross-step references | every multi-step prompt |
| Jinja templating / formatting | 14 (markdown table) |

## Prompts

### 1. SOC — phishing IP block with approval

> When a phishing alert comes in, look up every sender IP in VirusTotal.
> If any score above 50, ask an analyst to approve a block; if approved,
> block on the firewall and add a comment to the alert with what we did.

**Gauges**: picklist resolution, decision threshold, manual_input approval
flow, multi-connector chain, comment posting.

---

### 2. DevOps — failed-deploy rollback

> Watch our Deployments module. If a deploy status flips to `failed` and
> the environment is `prod`, automatically call our `rollback_release`
> playbook with the release id, then post the failure summary to our
> `#deploys` Slack channel.

**Gauges**: `start_on_update` with `op: changed` filter,
workflow_reference with parameter passing, conditional execution by
field.

---

### 3. ITOps — disk-full auto-clean + escalation

> When a host triggers a disk-full alert, find the host's owner from the
> CMDB, run our `clean_tmp` Ansible job on it via the SSH connector, and
> if free space is still under 10% after, escalate to on-call with a
> PagerDuty page.

**Gauges**: find_record correlated lookup, connector op with structured
output, decision on connector return value, post-action re-check
pattern.

---

### 4. ITOps — new-hire access provisioning

> When IT-Service-Request status flips to `Approved` and the request
> type is `New Hire Access`, provision the user in Okta with the role's
> group, create their Jira + Confluence accounts, add them to the right
> Slack channels for their team, then post a checklist back to the
> ticket. If any step fails, stop and assign the ticket to the IT lead.

**Gauges**: for_each over an asset list, fail-fast vs continue,
multi-connector orchestration, summary collection in set_variable.

---

### 5. NOC — SLA breach escalation

> If a NOC ticket's response-SLA timer crosses 80% and severity is High
> or Critical, page the queue's primary on-call. Wait 15 minutes. If the
> ticket still isn't acknowledged, page their manager and escalate
> severity by one notch.

**Gauges**: delay + re-poll pattern, escalation chain, time-based
decisions, two-level paging.

---

### 6. SOC — quarterly privileged-access review

> Once a quarter, generate a list of everyone with admin access to our
> prod Linux fleet, email each person's manager with the privileges
> their report holds, and require the manager to click Approve or
> Revoke. Log every choice to the audit module.

**Gauges**: designer-only manual trigger, batch-processing pattern,
manual_input wait that loops over recipients, audit-record writeback.

---

### 7. SOC — UEBA impossible-travel triage

> When a user login event tagged `impossible_travel` lands, score the
> user via our internal risk service. If the score is over 80 lock the
> account immediately; 50–80, send to a tier-2 analyst for a decision;
> below 50, just tag and continue. Either way, write the outcome to the
> case.

**Gauges**: three-way decision with non-equal branches, picklist
auto-resolve on case status, score-based routing, tag application.

---

### 8. NOC — new-device monitoring onboarding

> Whenever a new device record is created in our Inventory module from
> the network discovery feed, enrich it via the SNMP connector to fill
> in OS / firmware / location, then route to the right monitoring
> config: if `device_role` is `core_switch` send to the high-priority
> polling profile, otherwise the standard one.

**Gauges**: module-bound creation trigger, enrichment chain, role-based
routing decision, picklist write on a foreign module.

---

### 9. NOC — fiber-cut tech dispatch

> If a fiber-cut alarm fires, find the nearest on-call field tech by
> region, text them via Twilio with the splice-point coordinates, wait
> an hour for ack. If no ack, text the next tech in the rotation and
> notify the first tech's manager.

**Gauges**: geographic / proximity find_record, SMS connector,
time-bounded wait, rotation iteration, manager escalation.

---

### 10. DevOps — PR security gate

> When a pull request hits our `merge_queue` module with status
> `awaiting_checks`, kick off SonarQube + Snyk scans. If either fails or
> finds an issue above `medium`, post the report as a PR comment and
> block the merge. Otherwise mark it green and proceed.

**Gauges**: parallel-ish connector calls, threshold decision on
multi-source output, two divergent terminal paths, PR comment
writeback.

---

### 11. DevOps — prod change approval chain

> For a prod change request: route it to the platform team lead, then
> the database SRE if it touches data, then the on-call engineering
> manager. Each one approves or rejects with a comment. If any reject,
> stop and notify the requester with the reason. If all approve,
> schedule the change window in ServiceNow and update the CR record to
> `Scheduled`.

**Gauges**: sequential multi-stage approval (2–3 manual_inputs),
conditional stage skip, early-exit on reject, comment passing, terminal
state writeback.

---

### 12. ITOps — TLS cert expiration chase

> On the first of every month, find all TLS certs expiring within 60
> days. For each one, email the service owner with renewal instructions
> and start a 30-day timer. If they haven't renewed by then, raise a P3
> ticket and notify the platform-security distribution list.

**Gauges**: designer scheduled trigger, batch find_record with date
filter, per-record sub-workflow, long-running wait state.

---

### 13. SOC — HTTP fallback when no native op

> We use Akamai but the connector doesn't have a `block_url` operation.
> I need to block this URL via their Network Lists API anyway — figure
> out the request shape and build me a playbook that uses an HTTP step.

**Gauges**: `propose_http_fallback` decision path
(`CONNECTOR_INTEGRATION_PLAN.md` Phase 0.5), catalog grounding,
auth-wiring hint, working playbook from no native op.

---

### 14. SOC — weekly metrics digest

> Every Monday at 8am, count how many incidents we closed last week
> broken down by severity, render that as a markdown table, and post it
> to our `#soc-metrics` Teams channel. Also save the raw counts to a
> Reporting module record.

**Gauges**: scheduled trigger, find_record with grouping intent,
code_snippet for aggregation (genuine Python need), markdown formatting
in Jinja, dual-target write.

---

## Promotion to eval tasks

A prompt graduates from this doc into `python/evals/tasks/*.json` when:

1. The capability mix isn't already covered by an existing task.
2. The expected gold YAML is hand-author-able (we know what "right"
   looks like).
3. A failure mode is reproducible enough to write a structural
   assertion against.

Current promoted set (top 5 by signal):

| # | Task file | Prompt above |
|---|---|---|
| 17 | `17_soc_phish_block_with_approval.json` | #1 |
| 18 | `18_itops_disk_full_recheck.json` | #3 |
| 19 | `19_noc_sla_breach_repoll.json` | #5 |
| 20 | `20_soc_ueba_three_way_decision.json` | #7 |
| 21 | `21_soc_http_fallback_no_native_op.json` | #13 |

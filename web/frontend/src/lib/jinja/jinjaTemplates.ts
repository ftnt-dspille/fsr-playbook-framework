export interface JinjaTemplateExample {
  id: string;
  label: string;
  description: string;
  template: string;
  input: unknown;
}

export const templateExamples: JinjaTemplateExample[] = [
  {
    id: 'greeting',
    label: 'Greeting — simple variable',
    description: 'Interpolate a single field with a fallback.',
    template: "Hello, {{ vars.input.records[0].name | default('stranger') }}!",
    input: { vars: { input: { records: [{ name: 'Ada' }] } } }
  },
  {
    id: 'record-summary',
    label: 'Record summary — multi-line',
    description: 'Print several fields from the current record.',
    template:
      'Name:    {{ vars.input.records[0].name }}\n' +
      "Email:   {{ vars.input.records[0].email | default('n/a') }}\n" +
      'Status:  {{ vars.input.records[0].status | upper }}',
    input: {
      vars: {
        input: {
          records: [{ name: 'Ada Lovelace', email: 'ada@example.com', status: 'active' }]
        }
      }
    }
  },
  {
    id: 'loop-table',
    label: 'Loop — render a table of alerts',
    description: 'Iterate over records with loop.index and conditional rows.',
    template:
      '{% for alert in vars.input.records %}\n' +
      '{{ loop.index }}. [{{ alert.severity | upper }}] {{ alert.name }}' +
      '{% if alert.assigned_to %} → {{ alert.assigned_to }}{% endif %}\n' +
      '{% else %}\n' +
      'No alerts to show.\n' +
      '{% endfor %}',
    input: {
      vars: {
        input: {
          records: [
            { name: 'Suspicious login', severity: 'high', assigned_to: 'soc' },
            { name: 'Port scan', severity: 'medium' }
          ]
        }
      }
    }
  },
  {
    id: 'conditional',
    label: 'Conditional — if / elif / else',
    description: 'Branch on a numeric score.',
    template:
      '{% set score = vars.input.records[0].risk_score %}\n' +
      '{% if score >= 80 %}\n' +
      'CRITICAL — immediate response required ({{ score }}).\n' +
      '{% elif score >= 50 %}\n' +
      'Elevated — review within the hour ({{ score }}).\n' +
      '{% else %}\n' +
      'Low — routine handling ({{ score }}).\n' +
      '{% endif %}',
    input: { vars: { input: { records: [{ risk_score: 72 }] } } }
  },
  {
    id: 'macro',
    label: 'Macro — reusable row renderer',
    description: 'Define a macro and call it inside a loop.',
    template:
      '{% macro row(item) %}' +
      '- {{ item.name }} ({{ item.count | default(0) }})' +
      '{% endmacro %}\n' +
      '{% for item in vars.input.records %}\n' +
      '{{ row(item) }}\n' +
      '{% endfor %}',
    input: {
      vars: {
        input: {
          records: [
            { name: 'phishing', count: 12 },
            { name: 'malware', count: 3 },
            { name: 'policy' }
          ]
        }
      }
    }
  },
  {
    id: 'filter-chain',
    label: 'Filter chain — normalize strings',
    description: 'Demonstrates trim, lower, replace, title filters.',
    template:
      '{{ vars.input.records[0].title ' +
      "| default('untitled') " +
      '| trim ' +
      '| lower ' +
      "| replace('_', ' ') " +
      '| title }}',
    input: { vars: { input: { records: [{ title: '  incident_response_runbook  ' }] } } }
  },
  {
    id: 'json-extract',
    label: 'Extract — unique list join',
    description: 'Collect one field across records and join the unique values.',
    template:
      'Affected hosts: ' +
      "{{ vars.input.records | map(attribute='host') | unique | list | join(', ') }}",
    input: {
      vars: {
        input: {
          records: [
            { host: 'web-01' },
            { host: 'web-02' },
            { host: 'web-01' },
            { host: 'db-07' }
          ]
        }
      }
    }
  },
  {
    id: 'api-response',
    label: 'API response — summarize a result block',
    description: 'Typical vars.steps.<step>.data shape from FortiSOAR.',
    template:
      'Fetched {{ vars.steps.getUsers.data.hydra_totalItems }} user(s):\n' +
      "{% for user in vars.steps.getUsers.data['hydra_member'] %}\n" +
      "- {{ user.userName }} <{{ user.email | default('no-email') }}>\n" +
      '{% endfor %}',
    input: {
      vars: {
        steps: {
          getUsers: {
            data: {
              hydra_totalItems: 2,
              hydra_member: [
                { userName: 'alice', email: 'alice@example.com' },
                { userName: 'bob' }
              ]
            }
          }
        }
      }
    }
  }
];

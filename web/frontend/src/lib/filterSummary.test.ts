import { describe, it, expect } from 'vitest';
import { summarizeTrigger, summarizeFind } from './filterSummary';

describe('summarizeTrigger', () => {
  it('renders the empty case as "On create of all <module>"', () => {
    expect(summarizeTrigger('start_on_create', 'alerts', { logic: 'AND', filters: [] }))
      .toBe('On create of all alerts.');
  });

  it('falls back to "records" when no module is set', () => {
    expect(summarizeTrigger('start_on_create', null, { logic: 'AND', filters: [] }))
      .toBe('On create of all records.');
  });

  it('reads picklist display labels from the _value hint', () => {
    const out = summarizeTrigger('start_on_create', 'alerts', {
      logic: 'AND',
      filters: [
        {
          field: 'severity', operator: 'eq', value: '/api/3/picklists/abc',
          _value: { display: 'High', itemValue: 'High' }
        }
      ]
    });
    expect(out).toBe('On create of alerts where severity is High.');
  });

  it('humanizes camelCase + snake_case field names', () => {
    const out = summarizeTrigger('start_on_update', 'incidents', {
      logic: 'AND',
      filters: [
        { field: 'sourceRecordId', operator: 'isnull', value: 'true' },
        { field: 'incident_status', operator: 'neq', value: 'Closed' }
      ]
    });
    expect(out).toBe('On update of incidents where source record id is empty and incident status is not Closed.');
  });

  it('uses or for OR groups and parenthesizes nested groups', () => {
    const out = summarizeTrigger('start_on_create', 'indicators', {
      logic: 'AND',
      filters: [
        {
          logic: 'OR',
          filters: [
            { field: 'typeofindicator', operator: 'eq', value: 'Domain' },
            { field: 'typeofindicator', operator: 'eq', value: 'URL' }
          ]
        },
        { field: 'indicatorStatus', operator: 'neq', value: 'Excluded' }
      ]
    } as any);
    expect(out).toBe(
      'On create of indicators where (typeofindicator is Domain or typeofindicator is URL) and indicator status is not Excluded.'
    );
  });

  it('renders manual_action / api_call / start verbs', () => {
    expect(summarizeTrigger('manual_action', 'tasks', { logic: 'AND', filters: [] }))
      .toBe('When an analyst runs an action on all tasks.');
    expect(summarizeTrigger('api_call', 'incidents', { logic: 'AND', filters: [] }))
      .toBe('When the API endpoint is called for all incidents.');
    expect(summarizeTrigger('start', 'alerts', { logic: 'AND', filters: [] }))
      .toBe('On manual run against all alerts.');
  });
});

describe('summarizeFind', () => {
  it('renders an empty find as "Find all <module>"', () => {
    expect(summarizeFind('tasks', { logic: 'AND', filters: [] }))
      .toBe('Find all tasks.');
  });

  it('renders a single-leaf find', () => {
    const out = summarizeFind('tasks', {
      logic: 'AND',
      filters: [{ field: 'name', operator: 'eq', value: '{{ vars.input.records[0].uuid }}' }]
    });
    expect(out).toBe('Find tasks where name is vars.input.records[0].uuid.');
  });
});

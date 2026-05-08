import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/svelte';
import StepPalette from './StepPalette.svelte';

describe('StepPalette', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === '/api/ref/step-types') {
        return new Response(JSON.stringify([
          { name: 'set_variable', detail: 'store a value into vars' },
          { name: 'decision', detail: 'branch on conditions' }
        ]), { status: 200 });
      }
      if (url.startsWith('/api/ref/connectors?')) {
        return new Response(JSON.stringify([
          { name: 'jira', label: 'Jira', category: 'Ticket Creation', description: null },
          { name: 'crowd-strike-falcon', label: 'CrowdStrike Falcon', category: 'EDR', description: null }
        ]), { status: 200 });
      }
      if (url.includes('/api/ref/connectors/jira/operations')) {
        return new Response(JSON.stringify([
          { op_name: 'get_ticket_details', title: 'Get Ticket Details', category: null, description: null }
        ]), { status: 200 });
      }
      if (url === '/api/ref/recipes') {
        return new Response(JSON.stringify([
          { name: 'trigger:cybersponse.action', kind: 'trigger_pattern', when_to_use: '823 playbook(s) trigger via stepType=cybersponse.action' }
        ]), { status: 200 });
      }
      return new Response('not found', { status: 404 });
    }) as any;
  });

  afterEach(() => {
    cleanup();
    globalThis.fetch = originalFetch;
  });

  it('renders step types from /api/ref/step-types by default', async () => {
    render(StepPalette);
    await waitFor(() => screen.getByText('set_variable'));
    expect(screen.getByText('set_variable')).toBeTruthy();
    expect(screen.getByText('decision')).toBeTruthy();
  });

  it('switches to connectors tab and lists connectors', async () => {
    render(StepPalette);
    await waitFor(() => screen.getByText('set_variable'));
    await fireEvent.click(screen.getByRole('button', { name: 'connectors' }));
    await waitFor(() => screen.getByText('jira'));
    expect(screen.getByText('jira')).toBeTruthy();
    expect(screen.getByText('crowd-strike-falcon')).toBeTruthy();
  });

  it('filters connectors by query', async () => {
    render(StepPalette);
    await waitFor(() => screen.getByText('set_variable'));
    await fireEvent.click(screen.getByRole('button', { name: 'connectors' }));
    await waitFor(() => screen.getByText('jira'));
    const filter = screen.getByPlaceholderText('filter connectors…') as HTMLInputElement;
    await fireEvent.input(filter, { target: { value: 'jira' } });
    expect(screen.queryByText('crowd-strike-falcon')).toBeNull();
    expect(screen.getByText('jira')).toBeTruthy();
  });

  it('expands a connector to reveal its operations', async () => {
    render(StepPalette);
    await waitFor(() => screen.getByText('set_variable'));
    await fireEvent.click(screen.getByRole('button', { name: 'connectors' }));
    const jira = await waitFor(() => screen.getByText('jira'));
    await fireEvent.click(jira);
    await waitFor(() => screen.getByText('get_ticket_details'));
    expect(screen.getByText('get_ticket_details')).toBeTruthy();
  });

  it('switches to recipes tab and renders recipe rows', async () => {
    render(StepPalette);
    await waitFor(() => screen.getByText('set_variable'));
    await fireEvent.click(screen.getByRole('button', { name: 'recipes' }));
    await waitFor(() => screen.getByText('trigger:cybersponse.action'));
    expect(screen.getByText('trigger:cybersponse.action')).toBeTruthy();
    expect(screen.getByText('trigger_pattern')).toBeTruthy();
  });

  it('fires onPick with the right payload when a row is clicked', async () => {
    const onPick = vi.fn();
    render(StepPalette, { props: { onPick } });
    await waitFor(() => screen.getByText('set_variable'));
    await fireEvent.click(screen.getByText('set_variable'));
    expect(onPick).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'step_type', type: 'set_variable' })
    );
  });
});

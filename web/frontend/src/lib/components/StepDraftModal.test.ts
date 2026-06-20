import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/svelte';
import StepDraftModal from './StepDraftModal.svelte';
import type { VisualNode } from '../api';

const decisionNode: VisualNode = {
  id: 'br', type: 'decision', family: 'decision', name: 'Branch',
  arguments: { conditions: [] }, for_each: null, comment: null, position: null,
};

let originalFetch: typeof fetch;
let lastBody: any = null;

beforeEach(() => {
  originalFetch = globalThis.fetch;
  lastBody = null;
});

afterEach(() => {
  globalThis.fetch = originalFetch;
  cleanup();
});

function mockDraft(response: any) {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) === '/api/visual/draft-step' && init?.body) {
      lastBody = JSON.parse(init.body as string);
    }
    return new Response(JSON.stringify(response), { status: 200 });
  }) as any;
}

describe('StepDraftModal', () => {
  it('renders a step-type-specific placeholder hint', () => {
    mockDraft({ ok: true, proposed_args: {}, diagnostics: [] });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply: vi.fn(), onClose: vi.fn() }
    });
    const ta = screen.getByPlaceholderText(/branch on whether/i);
    expect(ta).toBeTruthy();
  });

  it('disables the submit button until the user types', async () => {
    mockDraft({ ok: true, proposed_args: {}, diagnostics: [] });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply: vi.fn(), onClose: vi.fn() }
    });
    const btn = screen.getByRole('button', { name: 'Draft step' });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    const ta = screen.getByRole('textbox');
    await fireEvent.input(ta, { target: { value: 'do a thing' } });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it('posts the intent + step_type to /api/visual/draft-step on submit', async () => {
    mockDraft({
      ok: true,
      proposed_args: { conditions: [{ option: 'Yes', condition: '{{ x }}' }] },
      diagnostics: []
    });
    render(StepDraftModal, {
      props: { node: decisionNode, module: null, onApply: vi.fn(), onClose: vi.fn() }
    });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'branch on x' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Draft step' }));
    await waitFor(() => expect(lastBody).not.toBeNull());
    expect(lastBody.step_type).toBe('decision');
    expect(lastBody.intent).toBe('branch on x');
  });

  it('renders the diff and a green ✓ badge when validation is clean', async () => {
    mockDraft({
      ok: true,
      proposed_args: { conditions: [{ option: 'Yes' }] },
      diagnostics: []
    });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply: vi.fn(), onClose: vi.fn() }
    });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'go' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Draft step' }));
    await waitFor(() => expect(screen.getByText('proposed')).toBeTruthy());
    expect(screen.getByText(/validated cleanly/)).toBeTruthy();
  });

  it('surfaces compiler errors in a red panel', async () => {
    mockDraft({
      ok: true,
      proposed_args: { conditions: [] },
      diagnostics: [
        { severity: 'error', code: 'no_conditions',
          path: 'playbooks[0].steps[0].arguments.conditions',
          message: 'decision needs at least one condition', suggestion: 'add a branch' }
      ]
    });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply: vi.fn(), onClose: vi.fn() }
    });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'go' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Draft step' }));
    await waitFor(() => expect(screen.getByText(/compiler error/)).toBeTruthy());
    expect(screen.getByText(/decision needs at least one condition/)).toBeTruthy();
    expect(screen.getByText(/add a branch/)).toBeTruthy();
  });

  it('surfaces compiler warnings in an amber panel without the "still write" warning', async () => {
    mockDraft({
      ok: true,
      proposed_args: { conditions: [{ option: 'A' }] },
      diagnostics: [
        { severity: 'warning', code: 'no_default',
          path: 'steps[0].arguments.conditions',
          message: 'no default branch — orphan when no condition matches',
          suggestion: '' }
      ]
    });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply: vi.fn(), onClose: vi.fn() }
    });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'go' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Draft step' }));
    await waitFor(() => expect(screen.getByText(/1 warning/)).toBeTruthy());
    expect(screen.queryByText(/Apply will still write/)).toBeNull();
  });

  it('calls onApply with the proposed args when Apply is clicked', async () => {
    const onApply = vi.fn();
    const proposed = { conditions: [{ option: 'Yes', condition: '{{ x }}' }] };
    mockDraft({ ok: true, proposed_args: proposed, diagnostics: [] });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply, onClose: vi.fn() }
    });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'go' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Draft step' }));
    await waitFor(() => expect(screen.getByText('Apply to step')).toBeTruthy());
    await fireEvent.click(screen.getByText('Apply to step'));
    expect(onApply).toHaveBeenCalledExactlyOnceWith(proposed);
  });

  it('shows the model output details on parse failure', async () => {
    mockDraft({
      ok: false,
      error: 'model did not return parseable JSON',
      raw_text: "I'm sorry, but I cannot write valid JSON today."
    });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply: vi.fn(), onClose: vi.fn() }
    });
    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'go' } });
    await fireEvent.click(screen.getByRole('button', { name: 'Draft step' }));
    await waitFor(() => expect(screen.getByText(/parseable JSON/)).toBeTruthy());
    // Click the disclosure to reveal the raw model output.
    await fireEvent.click(screen.getByText(/model output/));
    expect(screen.getByText(/sorry, but I cannot write valid JSON/)).toBeTruthy();
  });

  it('Esc closes the modal', async () => {
    const onClose = vi.fn();
    mockDraft({ ok: true, proposed_args: {}, diagnostics: [] });
    render(StepDraftModal, {
      props: { node: decisionNode, onApply: vi.fn(), onClose }
    });
    await fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });
});

import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/svelte';
import PlaybookGuards from './PlaybookGuards.svelte';
import type { VisualPlaybook, VisualNode } from '../api';

afterEach(cleanup);

function trigger(id: string, type = 'start_on_create'): VisualNode {
  return {
    id, type, family: 'trigger', name: id,
    arguments: {}, for_each: null, comment: null, position: null,
  };
}

function nonTrigger(id: string): VisualNode {
  return {
    id, type: 'set_variable', family: 'utility', name: id,
    arguments: {}, for_each: null, comment: null, position: null,
  };
}

function pb(nodes: VisualNode[], opts: { is_active?: boolean } = {}): VisualPlaybook {
  return {
    name: 'demo', description: '', parameters: [],
    trigger: 'start_on_create', trigger_step_id: null,
    is_active: opts.is_active,
    nodes, edges: [],
  };
}

describe('PlaybookGuards', () => {
  it('renders nothing when there is exactly one trigger and the playbook is active', () => {
    const { container } = render(PlaybookGuards, {
      props: { playbook: pb([trigger('t1'), nonTrigger('a')], { is_active: true }) }
    });
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
    // The wrapper div is also conditional — should be absent.
    expect(container.querySelector('div.space-y-1')).toBeNull();
  });

  it('renders nothing when the playbook is null', () => {
    const { container } = render(PlaybookGuards, { props: { playbook: null } });
    expect(container.querySelector('div')).toBeNull();
  });

  it('flags multi-trigger playbooks with the offending step names', () => {
    render(PlaybookGuards, {
      props: { playbook: pb([
        trigger('On Manual', 'start'),
        trigger('On Create', 'start_on_create'),
        nonTrigger('a'),
      ], { is_active: true }) }
    });
    const banner = screen.getByRole('alert');
    expect(banner.textContent).toMatch(/Multiple triggers \(2\)/);
    expect(banner.textContent).toMatch(/On Manual/);
    expect(banner.textContent).toMatch(/On Create/);
  });

  it('flags inactive trigger playbooks', () => {
    render(PlaybookGuards, {
      props: { playbook: pb([trigger('t1'), nonTrigger('a')], { is_active: false }) }
    });
    const banner = screen.getByRole('status');
    expect(banner.textContent).toMatch(/inactive/i);
    expect(banner.textContent).toMatch(/will not fire/i);
    expect(banner.textContent).toMatch(/is_active: true/);
  });

  it('treats missing is_active the same as false', () => {
    // Shape the backend produces when the source YAML omits the
    // key — `is_active` is undefined in the JSON. Default IR value
    // is False, so this should still flag.
    render(PlaybookGuards, {
      props: { playbook: pb([trigger('t1'), nonTrigger('a')]) }
    });
    // `is_active === undefined` shouldn't trigger the inactive guard
    // (we explicitly check `=== false` to avoid noise on legacy
    // graphs from older backends that didn't surface the flag).
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('does not flag inactive on playbooks without any trigger', () => {
    // A manual collection of utility-only playbooks (e.g. shared
    // "library" playbooks called via workflow_reference) doesn't
    // need to be active in FSR's sense — flagging them would be noise.
    render(PlaybookGuards, {
      props: { playbook: pb([nonTrigger('a'), nonTrigger('b')], { is_active: false }) }
    });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('renders both banners when a playbook is multi-trigger AND inactive', () => {
    render(PlaybookGuards, {
      props: { playbook: pb([
        trigger('t1'), trigger('t2'),
      ], { is_active: false }) }
    });
    expect(screen.getByRole('alert')).toBeTruthy();
    expect(screen.getByRole('status')).toBeTruthy();
  });
});

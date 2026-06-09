import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { recordPick, scoreFor } from './opPickerPrefs';

describe('opPickerPrefs', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns 0 for an op never picked', () => {
    const s = scoreFor('jira');
    expect(s('create_ticket')).toBe(0);
  });

  it('scores a freshly picked op above never-picked', () => {
    recordPick('jira', 'create_ticket');
    const s = scoreFor('jira');
    expect(s('create_ticket')).toBeGreaterThan(0);
    expect(s('assign_issue')).toBe(0);
  });

  it('caps repeated picks at the frequency ceiling', () => {
    for (let i = 0; i < 50; i++) recordPick('jira', 'create_ticket');
    const s = scoreFor('jira');
    // FREQ_CAP=10, no time elapsed → score ≤ 10
    expect(s('create_ticket')).toBeLessThanOrEqual(10);
    expect(s('create_ticket')).toBeGreaterThan(0);
  });

  it('decays score with age (half-life ~14 days)', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));
    recordPick('jira', 'create_ticket');
    const freshScore = scoreFor('jira')('create_ticket');

    // Advance ~14 days; score should roughly halve.
    vi.setSystemTime(new Date('2026-01-15T00:00:00Z'));
    const agedScore = scoreFor('jira')('create_ticket');
    expect(agedScore).toBeLessThan(freshScore);
    expect(agedScore).toBeGreaterThan(freshScore * 0.4);
    expect(agedScore).toBeLessThan(freshScore * 0.6);
  });

  it('keeps separate scores per connector', () => {
    recordPick('jira', 'create_ticket');
    recordPick('fortigate', 'block_ip');
    expect(scoreFor('jira')('create_ticket')).toBeGreaterThan(0);
    expect(scoreFor('jira')('block_ip')).toBe(0);
    expect(scoreFor('fortigate')('block_ip')).toBeGreaterThan(0);
  });
});

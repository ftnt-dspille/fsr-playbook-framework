/**
 * Behavior tests for the Monaco editor buffer.
 *
 * The store is a module-level singleton, so we reset its state between
 * tests rather than re-importing. localStorage is jsdom-provided.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { yamlStore } from './yamlStore.svelte';

beforeEach(() => {
  yamlStore.text = '';
  localStorage.clear();
});

describe('yamlStore', () => {
  it('setText replaces the buffer', () => {
    yamlStore.text = 'before';
    yamlStore.setText('after');
    expect(yamlStore.text).toBe('after');
  });

  it('setText accepts an optional reason (legacy call-site parity)', () => {
    yamlStore.setText('x', 'switched modes');
    expect(yamlStore.text).toBe('x');
  });
});

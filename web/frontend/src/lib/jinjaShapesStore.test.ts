/**
 * jinjaShapesStore — small reactive container for per-step Jinja
 * output Shapes. Verify the public API: shapes/setShapes/shapesFor +
 * the null-fallback when a step hasn't been verified yet.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { jinjaShapesStore } from './jinjaShapesStore.svelte';
import type { Shape } from './shapeStubs';

const sampleShape: Shape = {
  kind: 'object',
  keys: {
    data: { kind: 'object', keys: { severity: { kind: 'scalar', type: 'string' } } }
  }
};

describe('jinjaShapesStore', () => {
  beforeEach(() => jinjaShapesStore.setShapes({}));

  it('starts empty', () => {
    expect(jinjaShapesStore.shapes).toEqual({});
    expect(jinjaShapesStore.shapesFor('anything')).toBeNull();
  });

  it('publishes a shape map and reads it back per-key', () => {
    jinjaShapesStore.setShapes({ Get_Alert: sampleShape });
    expect(jinjaShapesStore.shapesFor('Get_Alert')).toEqual(sampleShape);
    expect(jinjaShapesStore.shapesFor('Missing')).toBeNull();
  });

  it('setShapes(undefined-ish) clears to {}', () => {
    jinjaShapesStore.setShapes({ Get_Alert: sampleShape });
    jinjaShapesStore.setShapes(null as any);
    expect(jinjaShapesStore.shapes).toEqual({});
  });

  it('setShapes replaces (does not merge)', () => {
    jinjaShapesStore.setShapes({ A: sampleShape });
    jinjaShapesStore.setShapes({ B: sampleShape });
    expect(jinjaShapesStore.shapesFor('A')).toBeNull();
    expect(jinjaShapesStore.shapesFor('B')).toEqual(sampleShape);
  });
});

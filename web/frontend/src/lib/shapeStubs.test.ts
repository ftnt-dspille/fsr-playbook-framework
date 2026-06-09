import { describe, expect, it } from 'vitest';
import { buildJinjaContext, shapeToStub, type Shape } from './shapeStubs';

describe('shapeToStub', () => {
  it('renders scalar shapes by type', () => {
    expect(shapeToStub({ kind: 'scalar', type: 'string' })).toBe('_stub_text_');
    expect(shapeToStub({ kind: 'scalar', type: 'integer' })).toBe(0);
    expect(shapeToStub({ kind: 'scalar', type: 'boolean' })).toBe(false);
  });

  it('renders an object shape and includes FSR universal keys', () => {
    const stub = shapeToStub({
      kind: 'object',
      keys: { name: { kind: 'scalar', type: 'string' } }
    }) as Record<string, unknown>;
    expect(stub.name).toBe('_stub_text_');
    expect(stub.status).toBeDefined();
    expect(stub['@id']).toBeDefined();
  });

  it('renders a list of records', () => {
    const stub = shapeToStub({
      kind: 'list',
      item: {
        kind: 'object',
        keys: { id: { kind: 'scalar', type: 'string' } }
      }
    }) as unknown[];
    expect(Array.isArray(stub)).toBe(true);
    expect(stub.length).toBe(1);
    expect((stub[0] as Record<string, unknown>).id).toBe('_stub_text_');
  });

  it('renders unknown shape as empty object so attr access does not throw', () => {
    expect(shapeToStub({ kind: 'unknown', reason: 'destructive op' })).toEqual({});
  });

  it('renders none shape as null', () => {
    expect(shapeToStub({ kind: 'none' })).toBeNull();
  });
});

describe('buildJinjaContext', () => {
  it('wraps shapes under vars.steps keyed by jkey', () => {
    const ctx = buildJinjaContext({
      Find_Alerts: {
        kind: 'list',
        item: {
          kind: 'object',
          keys: { severity: { kind: 'scalar', type: 'string' } }
        }
      } as Shape
    });
    const steps = ((ctx.vars as Record<string, unknown>).steps as Record<string, unknown>);
    expect(steps.Find_Alerts).toBeDefined();
    const first = (steps.Find_Alerts as unknown[])[0] as Record<string, unknown>;
    expect(first.severity).toBe('_stub_text_');
  });

  it('includes vars.input.params from the simulated input arg', () => {
    const ctx = buildJinjaContext({}, { ip: '1.2.3.4' });
    const params = (((ctx.vars as Record<string, unknown>).input as Record<string, unknown>).params) as Record<string, unknown>;
    expect(params.ip).toBe('1.2.3.4');
  });
});

/**
 * Tests for YAML step-type completion snippets.
 *
 * Monaco's autoIndent:'full' (the default) re-indents each newline to match
 * the surrounding context, so snippets must NOT include an explicit base-pad
 * prefix — they should only carry relative child indentation.
 *
 * Key invariant: buildSnippet(name, pad) must return the same string for any
 * value of `pad`, because Monaco provides the base indentation automatically.
 * If a snippet still embeds the pad, it will double-indent at runtime.
 */
import { describe, it, expect } from 'vitest';
import { buildSnippet, SNIPPET_NAMES } from './yamlCompletions';

/** Strip Monaco tab-stop markers like ${1:foo}, ${0}, ${2}. */
function stripTabStops(text: string): string {
  return text.replace(/\$\{?\d+(?::([^}]*))?\}?/g, '$1').replace(/\$\{?\d+\}?/g, '');
}

describe('buildSnippet — pad-independent output (no double-indentation)', () => {
  const PADS = ['', '  ', '    ', '      ', '        ', '\t', '\t\t'];

  for (const name of SNIPPET_NAMES) {
    it(`${name}: output is identical for all pad values`, () => {
      const baseline = buildSnippet(name, '');
      for (const pad of PADS) {
        expect(buildSnippet(name, pad)).toBe(
          baseline,
          `snippet "${name}" differs when pad="${pad}" — it embeds the pad (double-indent bug)`
        );
      }
    });
  }

  it('connector snippet structure (base indent = 0)', () => {
    const filled = stripTabStops(buildSnippet('connector', ''));
    expect(filled).toMatch(/^arguments:/m);
    expect(filled).toMatch(/^  connector:/m);
    expect(filled).toMatch(/^  operation:/m);
    expect(filled).toMatch(/^  params:/m);
  });

  it('decision snippet: branches: and next: at top level, conditions: one level in', () => {
    const filled = stripTabStops(buildSnippet('decision', ''));
    expect(filled).toMatch(/^branches:/m);
    expect(filled).toMatch(/^next:/m);
    expect(filled).toMatch(/^  conditions:/m);
  });

  it('set_variable snippet has arg_list under arguments', () => {
    const filled = stripTabStops(buildSnippet('set_variable', ''));
    expect(filled).toMatch(/^arguments:/m);
    expect(filled).toMatch(/^  arg_list:/m);
  });

  it('manual_input snippet has inputs list at correct depth', () => {
    const filled = stripTabStops(buildSnippet('manual_input', ''));
    expect(filled).toMatch(/^arguments:/m);
    expect(filled).toMatch(/^  record:/m);
    expect(filled).toMatch(/^  input:/m);
    expect(filled).toMatch(/^    options:/m);
  });

  it('decision snippet uses quoted yes to avoid Norway problem', () => {
    const raw = buildSnippet('decision', '');
    // Unquoted bare 'yes' in YAML 1.1 parses as boolean true, breaking FSR route lookup.
    expect(raw).not.toMatch(/option: yes(?!\})/);
  });
});

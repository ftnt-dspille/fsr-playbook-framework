#!/usr/bin/env python
"""Per advertised tool: docstring length, sent length, percent lost, and the
text that is cut. `--cuts DIR` writes each tool's cut text to DIR/<tool>.txt."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fsr_playbooks.tests._tool_audit import advertised_chars, audit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cuts", help="directory to write each tool's cut text to")
    a = ap.parse_args()
    rows = sorted(audit(), key=lambda r: -r.lost_pct)
    print(f"{'tool':<32}{'full':>7}{'sent':>7}{'lost%':>7}{'schema':>8}")
    for r in rows:
        print(f"{r.name:<32}{r.full:>7}{r.sent:>7}{r.lost_pct:>6.0f}%{r.schema_chars:>8}")
        if a.cuts and r.cut_text:
            d = Path(a.cuts)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{r.name}.txt").write_text(r.cut_text + "\n")
    print(f"\nadvertised chars per turn (descriptions + schemas): {advertised_chars()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""`make test-effect-probes` -- run the write-through probes and report.

    python tooling/probes/effect/runner.py              # every probe
    python tooling/probes/effect/runner.py --only A5    # one
    python tooling/probes/effect/runner.py --runs 2     # a defect twice is a defect

Exit 0 iff every probe that actually ran came back PASS. A BLOCKED run is a
non-zero exit too: it means the write path under test was never exercised, and
a suite that greens on "we never got there" is the failure this whole plan
exists to stop. ENV-SKIP alone exits 0 -- an unreachable box is not a product
signal.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "tooling") not in sys.path:
    sys.path.insert(0, str(ROOT / "tooling"))

import json  # noqa: E402

from probes._env import get_config  # noqa: E402
from probes.effect import drive  # noqa: E402
from probes.effect.probes import ALL, Result  # noqa: E402


def _run(pid: str, fn, runs: int) -> list[Result]:
    out = []
    for r in range(runs):
        try:
            out.append(fn())
        except Exception as exc:  # noqa: BLE001 -- a drive failure is a result
            msg = f"{type(exc).__name__}: {exc}"
            # An unreachable/unauthenticatable box is not a product signal
            # (live on .159: the auth service hung mid-session and a probe
            # FAILED on 'Authentication failed (400)' -- a verdict about the
            # box, not the write path).
            _env_tokens = ("not configured", "SeedError", "Authentication failed",
                           "ConnectError", "ConnectionError", "ReadTimeout",
                           "ConnectTimeout", "Max retries exceeded")
            verdict = "ENV-SKIP" if any(t in msg for t in _env_tokens) else "FAIL"
            out.append(Result(pid, fn.__doc__.splitlines()[0] if fn.__doc__ else pid,
                              verdict, msg))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated probe ids (A5,A2,A3)")
    ap.add_argument("--dump", default="",
                    help="directory for raw turn/resume payloads (re-grade offline)")
    ap.add_argument("--runs", type=int, default=1,
                    help="repeat each probe; 2 is the house default for LLM-driven runs")
    args = ap.parse_args(argv)

    cfg = get_config()
    if not cfg.is_live():
        print("[[EFFECT-ENV-SKIP]] no FSR_BASE_URL / auth -- "
              "point FSR_ENV_FILE at a box .env")
        return 0
    print(f"box: {cfg.base_url}")

    wanted = [p.strip().upper() for p in args.only.split(",") if p.strip()] or list(ALL)
    unknown = [p for p in wanted if p not in ALL]
    if unknown:
        print(f"unknown probe id(s): {unknown}; known: {list(ALL)}", file=sys.stderr)
        return 2

    results: list[Result] = []
    for pid in wanted:
        print(f"\n── {pid} ──")
        drive.reset_log()
        for res in _run(pid, ALL[pid], args.runs):
            if args.dump:
                d = Path(args.dump)
                d.mkdir(parents=True, exist_ok=True)
                out = d / f"{pid.lower()}.json"
                out.write_text(json.dumps(drive.LOG, indent=2, default=str))
                print(f"            dump: {out}")
            results.append(res)
            print(f"  {res.verdict:9} {res.id}  {res.title}")
            print(f"            {res.detail}")
            if res.before or res.after:
                print(f"            box before: {res.before}")
                print(f"            box after : {res.after}")
            if res.reply:
                print(f"            resume   : {res.reply}")
            if res.tools:
                print(f"            tools: {', '.join(res.tools)}")

    bad = [r for r in results if r.verdict in ("FAIL", "BLOCKED")]
    passed = [r for r in results if r.verdict == "PASS"]
    skipped = [r for r in results if r.verdict == "ENV-SKIP"]
    print(f"\n{len(passed)} pass · {len([r for r in bad if r.verdict == 'FAIL'])} fail · "
          f"{len([r for r in bad if r.verdict == 'BLOCKED'])} blocked · {len(skipped)} env-skip")
    if bad:
        print("[[EFFECT-FAIL]] " + "; ".join(f"{r.id} {r.verdict}: {r.detail}" for r in bad))
        return 1
    if not passed:
        print("[[EFFECT-ENV-SKIP]] nothing graded")
        return 0
    print("[[EFFECT-VERIFIED]] every graded write reached the box")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# =============================================================================
# compare.py — Compare multiple saved evaluation runs side by side.
#
# Usage:
#   python compare.py                              # all runs in results/
#   python compare.py results/run_a.json results/run_b.json
# =============================================================================

import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def print_run(run: dict):
    r, s = run["run"], run["summary"]
    print(f"\n  ── {r['label']}  ({r['timestamp']})")
    print(f"     model={r['model']}  schema={r['schema']}  benchmark={r['benchmark']}  threshold={r['threshold']}")
    print(f"     match={s['match_rate']:.1%} ({s['matches']}/{s['scored']})  "
          f"P={s['avg_precision']:.4f}  R={s['avg_recall']:.4f}  F1={s['avg_f1']:.4f}")

    print(f"     by op:")
    for op, v in s["by_op"].items():
        print(f"       {op:<12}  match={v['match_rate']:.1%}  f1={v['avg_f1']:.4f}  (n={v['n']})")

    if any(k != "uncategorized" for k in s.get("by_category", {})):
        print(f"     by category:")
        for cat, v in s["by_category"].items():
            print(f"       {cat:<20}  match={v['match_rate']:.1%}  f1={v['avg_f1']:.4f}  (n={v['n']})")

    if s["errors"]["total"]:
        print(f"     errors: {s['errors']}")


def compare_questions(runs: list[dict]):
    """Show per-question F1 across all runs for easy side-by-side comparison."""
    print(f"\n{'='*80}")
    print("  Per-question comparison")
    print(f"{'='*80}")

    labels = [r["run"]["label"] for r in runs]
    index  = {
        q["id"]: {r["run"]["label"]: q for q in r["questions"]}
        for r in runs
        for q in r["questions"]
    }
    # Collect all question ids in order
    all_ids = sorted({q["id"] for r in runs for q in r["questions"]}, key=lambda x: str(x))

    header = f"  {'ID':<5} {'Question':<45} " + "  ".join(f"{l[:14]:<14}" for l in labels)
    print(header)
    print(f"  {'-'*5} {'-'*45} " + "  ".join("-"*14 for _ in labels))

    for qid in all_ids:
        q_text = ""
        cols   = []
        for label in labels:
            q = index.get(qid, {}).get(label)
            if q:
                q_text = q["question"][:44]
                s      = q["scores"]
                tag    = "✓" if q["match"] else "✗"
                cols.append(f"{tag} F1={s['f1']:.2f}        ")
            else:
                cols.append("N/A           ")
        print(f"  {str(qid):<5} {q_text:<45} " + "  ".join(cols))


def main():
    paths = sys.argv[1:] if len(sys.argv) > 1 else sorted(Path("results").glob("*.json"))

    if not paths:
        print("No result files found.")
        return

    runs = [load(str(p)) for p in paths]

    print(f"\n{'='*60}")
    print(f"  Evaluation Comparison — {len(runs)} run(s)")
    print(f"{'='*60}")

    for run in runs:
        print_run(run)

    if len(runs) > 1:
        compare_questions(runs)


if __name__ == "__main__":
    main()
# =============================================================================
# test_gold.py — Run all gold queries from a benchmark file against MongoDB.
#
# Usage:
#   python test_gold.py                                  # default: benchmarks/flat.json
#   python test_gold.py --benchmark benchmarks/flat.json
#   python test_gold.py --benchmark benchmarks/flat.json --id 5
#   python test_gold.py --benchmark benchmarks/flat.json --collection selskap
# =============================================================================

import argparse
import json

from pymongo import MongoClient
import config


# ── MongoDB ───────────────────────────────────────────────────────────────────

def get_db():
    return MongoClient(config.MONGO_URI)[config.DATABASE_NAME]


# ── Query execution ───────────────────────────────────────────────────────────

def run_gold(db, gold: dict) -> dict:
    col = db[gold["collection"]]
    op  = gold.get("op", "find")

    try:
        if op == "find":
            proj    = gold.get("projection")
            cursor  = col.find(gold.get("filter", {}), proj) if proj else col.find(gold.get("filter", {}))
            results = list(cursor)
            _stringify_ids(results)

        elif op == "distinct":
            results = col.distinct(gold["field"], gold.get("filter", {}))

        elif op == "aggregate":
            results = list(col.aggregate(gold["pipeline"]))
            _stringify_ids(results)

        else:
            return {"results": None, "error": f"Unknown op: '{op}'"}

        return {"results": results, "error": None}

    except Exception as e:
        return {"results": None, "error": str(e)}


def _stringify_ids(docs: list) -> None:
    for doc in docs:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])


# ── Output ────────────────────────────────────────────────────────────────────

def print_result(entry: dict, run: dict):
    gold = entry["gold"]
    op   = gold.get("op", "find")

    print(f"\n{'─'*60}")
    print(f"  Q{entry.get('id', '?')} [{op}] — {entry['question']}")
    print(f"  Collection: {gold['collection']}")
    print(f"{'─'*60}")

    if run["error"]:
        print(f"  ✗ ERROR: {run['error']}")
        return

    results = run["results"]
    count   = len(results) if isinstance(results, list) else "N/A"
    print(f"  ✓ {count} result(s)\n")
    print(json.dumps(results[:5], indent=4, ensure_ascii=False, default=str))
    if isinstance(results, list) and len(results) > 5:
        print(f"\n  ... and {len(results) - 5} more")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Run gold queries from a benchmark file")
    parser.add_argument("--benchmark",  default="benchmarks/flat.json", help="Path to benchmark JSON")
    parser.add_argument("--id",         type=int, default=None, help="Run only the question with this id")
    parser.add_argument("--collection", default=None,            help="Run only questions for this collection")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    with open(args.benchmark, encoding="utf-8") as f:
        benchmark = json.load(f)

    # Apply filters
    if args.id:
        benchmark = [e for e in benchmark if e.get("id") == args.id]
    if args.collection:
        benchmark = [e for e in benchmark if e.get("gold", {}).get("collection") == args.collection]

    if not benchmark:
        print("No matching questions found.")
        exit(1)

    db = get_db()
    errors = 0

    print(f"\nRunning {len(benchmark)} gold query/queries against '{config.DATABASE_NAME}'")
    print(f"Benchmark: {args.benchmark}\n")

    for entry in benchmark:
        run = run_gold(db, entry["gold"])
        print_result(entry, run)
        if run["error"]:
            errors += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"  Ran {len(benchmark)} queries — {len(benchmark) - errors} OK, {errors} failed")
    print(f"{'='*60}\n")
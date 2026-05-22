import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient

import config


def load_benchmark(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def run_gold_query(database, query: dict[str, Any]) -> dict[str, Any]:
    try:
        collection = database[query["collection"]]
        operation = query.get("op", "find")

        if operation == "find":
            projection = query.get("projection")
            cursor = collection.find(query.get("filter", {}), projection) if projection else collection.find(query.get("filter", {}))
            results = list(cursor)
        elif operation == "distinct":
            results = collection.distinct(query["field"], query.get("filter", {}))
        elif operation == "aggregate":
            results = list(collection.aggregate(query["pipeline"]))
        else:
            return {"results": [], "error": f"Unknown operation: {operation}"}

        stringify_object_ids(results)
        return {"results": results, "error": None}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


def stringify_object_ids(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            stringify_object_ids(item)
    elif isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "_id":
                value[key] = str(item)
            else:
                stringify_object_ids(item)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run only the gold queries from a benchmark file")
    parser.add_argument("--benchmark", required=True, help="Path to benchmark JSON")
    parser.add_argument("--database", required=True, help="MongoDB database name")
    parser.add_argument("--id", type=int, default=None, help="Only run one benchmark question id")
    parser.add_argument("--limit", type=int, default=3, help="Number of example results to print per query")
    parser.add_argument("--show-results", action="store_true", help="Print example results in the terminal")
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent / "gold_results"),
        help="Folder where gold-query result files are saved",
    )
    parser.add_argument(
        "--save-full",
        action="store_true",
        help="Save full query results instead of only examples. This can create large files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    benchmark_path = Path(args.benchmark)
    benchmark = load_benchmark(benchmark_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.id is not None:
        benchmark = [entry for entry in benchmark if entry.get("id") == args.id]

    if not benchmark:
        print("No matching benchmark questions.")
        return

    database = MongoClient(config.MONGO_URI)[args.database]
    errors = 0
    question_results = []

    print(f"Benchmark: {benchmark_path}")
    print(f"Database:  {args.database}")
    print(f"Queries:   {len(benchmark)}")
    print()

    for entry in benchmark:
        query = entry["gold"]
        operation = query.get("op", "find")
        collection = query["collection"]
        result = run_gold_query(database, query)

        print(f"Q{entry['id']}: {operation} {collection}")
        print(f"  {entry['question']}")

        if result["error"]:
            errors += 1
            question_results.append(
                {
                    "id": entry["id"],
                    "question": entry["question"],
                    "operation": operation,
                    "collection": collection,
                    "status": "error",
                    "error": result["error"],
                    "gold_query": query,
                    "result_count": 0,
                    "examples": [],
                }
            )
            print(f"  ERROR: {result['error']}")
            print()
            continue

        results = result["results"]
        examples = results[: args.limit] if args.limit > 0 else []
        saved_question = {
            "id": entry["id"],
            "question": entry["question"],
            "operation": operation,
            "collection": collection,
            "status": "ok",
            "error": None,
            "gold_query": query,
            "result_count": len(results),
            "examples": examples,
        }
        if args.save_full:
            saved_question["results"] = results
        question_results.append(saved_question)

        print(f"  Results: {len(results)}")
        if args.show_results and examples:
            print(json.dumps(examples, indent=2, ensure_ascii=False, default=str))
        print()

    report = {
        "run": {
            "timestamp": timestamp,
            "benchmark": str(benchmark_path),
            "database": args.database,
            "saved_results": "full" if args.save_full else f"examples only, limit {args.limit}",
        },
        "summary": {
            "total_queries": len(benchmark),
            "successful_queries": len(benchmark) - errors,
            "failed_queries": errors,
        },
        "questions": question_results,
    }

    output_dir = Path(args.output_dir) / benchmark_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{timestamp}_{args.database}_gold_queries.json"
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False, default=str)

    print(f"Finished: {len(benchmark) - errors} OK, {errors} failed")
    print(f"Saved gold-query results to {output_path}")


if __name__ == "__main__":
    main()

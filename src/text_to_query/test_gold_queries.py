import argparse
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient

import config
from gold_cache import load_gold_cache, save_gold_cache

DEFAULT_GOLD_RUNS = {
    "flat": {
        "benchmarks": {
            "main": "src/text_to_query/benchmarks/flat.json",
            "complex": "src/text_to_query/benchmarks/flat_complex.json",
        },
        "database": "groundtruth",
    },
    "structured": {
        "benchmarks": {
            "main": "src/text_to_query/benchmarks/structured.json",
            "complex": "src/text_to_query/benchmarks/structured_complex.json",
        },
        "database": "groundtruthStructured",
    },
}


def load_benchmark(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def run_gold_query(database, query: dict[str, Any], max_time_ms: int | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        collection = database[query["collection"]]
        operation = query.get("op", "find")
        query_max_time_ms = config.QUERY_MAX_TIME_MS if max_time_ms is None else max_time_ms

        if operation == "find":
            projection = query.get("projection")
            cursor = collection.find(query.get("filter", {}), projection) if projection else collection.find(query.get("filter", {}))
            if query_max_time_ms:
                cursor = cursor.max_time_ms(query_max_time_ms)
            results = list(cursor)
        elif operation == "distinct":
            kwargs = {"maxTimeMS": query_max_time_ms} if query_max_time_ms else {}
            results = [{"_value": value} for value in collection.distinct(query["field"], query.get("filter", {}), **kwargs)]
        elif operation == "aggregate":
            if query_max_time_ms:
                results = list(collection.aggregate(query["pipeline"], allowDiskUse=True, maxTimeMS=query_max_time_ms))
            else:
                results = list(collection.aggregate(query["pipeline"], allowDiskUse=True))
        else:
            return {"results": [], "error": f"Unknown operation: {operation}", "duration_ms": elapsed_ms(started), "result_count": 0}

        stringify_object_ids(results)
        return {"results": results, "error": None, "duration_ms": elapsed_ms(started), "result_count": len(results)}
    except Exception as exc:
        return {"results": [], "error": str(exc), "duration_ms": elapsed_ms(started), "result_count": 0}


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


def normalize_for_cross_structure(value: Any) -> Any:
    if isinstance(value, list):
        return sorted((normalize_for_cross_structure(item) for item in value), key=stable_json)
    if isinstance(value, dict):
        values = collect_leaf_values(value)
        return sorted(values, key=stable_json)
    return value


def collect_leaf_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [normalize_for_cross_structure(item) for item in value]
    if isinstance(value, dict):
        values = []
        for key, item in value.items():
            if key == "_id":
                continue
            values.extend(collect_leaf_values(item))
        return values
    return [value]


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def result_keys(results: list[Any]) -> list[str]:
    return sorted(stable_json(normalize_for_cross_structure(row)) for row in results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run only the gold queries from a benchmark file")
    parser.add_argument(
        "--structure",
        choices=["flat", "structured", "both"],
        default=None,
        help="Use built-in benchmark/database defaults. Use both to run flat and structured.",
    )
    parser.add_argument(
        "--benchmark-set",
        choices=["main", "complex"],
        default="main",
        help="Built-in benchmark set to use with --structure. Default: main.",
    )
    parser.add_argument("--benchmark", default=None, help="Path to benchmark JSON")
    parser.add_argument("--database", default=None, help="MongoDB database name")
    parser.add_argument("--id", type=int, default=None, help="Only run one benchmark question id")
    parser.add_argument("--limit", type=int, default=3, help="Number of example results to print per query")
    parser.add_argument("--show-results", action="store_true", help="Print example results in the terminal")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="When running --structure both, compare flat and structured gold-query results by benchmark id.",
    )
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
    parser.add_argument("--no-cache", action="store_true", help="Always execute gold queries instead of reading cached gold results.")
    parser.add_argument("--refresh-cache", action="store_true", help="Execute gold queries and overwrite cached gold results.")
    parser.add_argument("--cache-dir", default=config.GOLD_CACHE_DIR, help=f"Gold result cache directory. Default: {config.GOLD_CACHE_DIR}")
    parser.add_argument("--max-time-ms", type=int, default=config.QUERY_MAX_TIME_MS, help=f"MongoDB maxTimeMS per query. Default: {config.QUERY_MAX_TIME_MS}")
    return parser.parse_args()


def build_gold_jobs(args: argparse.Namespace) -> list[dict[str, str]]:
    if args.structure is None:
        if not args.benchmark or not args.database:
            raise SystemExit("Either use --structure, or provide both --benchmark and --database.")
        return [{"name": Path(args.benchmark).stem, "benchmark": args.benchmark, "database": args.database}]

    structures = ["flat", "structured"] if args.structure == "both" else [args.structure]
    return [
        {
            "name": structure,
            "benchmark": DEFAULT_GOLD_RUNS[structure]["benchmarks"][args.benchmark_set],
            "database": DEFAULT_GOLD_RUNS[structure]["database"],
        }
        for structure in structures
    ]


def run_gold_benchmark(args: argparse.Namespace, job: dict[str, str], timestamp: str) -> dict[str, Any]:
    benchmark_path = Path(job["benchmark"])
    benchmark = load_benchmark(benchmark_path)

    if args.id is not None:
        benchmark = [entry for entry in benchmark if entry.get("id") == args.id]

    if not benchmark:
        raise SystemExit("No matching benchmark questions.")

    database = MongoClient(config.MONGO_URI)[job["database"]]
    errors = 0
    question_results = []

    print(f"Benchmark: {benchmark_path}")
    print(f"Database:  {job['database']}")
    print(f"Queries:   {len(benchmark)}")
    print()

    for entry in benchmark:
        query = entry["gold"]
        operation = query.get("op", "find")
        collection = query["collection"]
        result = None
        if not args.no_cache and not args.refresh_cache:
            result = load_gold_cache(benchmark_path, job["database"], entry, args.cache_dir)

        if result is None:
            result = run_gold_query(database, query, args.max_time_ms)
            if not args.no_cache and not result["error"]:
                cache_path = save_gold_cache(benchmark_path, job["database"], entry, result, args.cache_dir)
                result["cache"] = {
                    "hit": False,
                    "path": str(cache_path) if cache_path else None,
                }

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
                    "duration_ms": result["duration_ms"],
                    "cache": result.get("cache"),
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
            "duration_ms": result["duration_ms"],
            "cache": result.get("cache"),
            "examples": examples,
            "comparison_keys": result_keys(results),
        }
        if args.save_full:
            saved_question["results"] = results
        question_results.append(saved_question)

        cache_label = " (cache hit)" if (result.get("cache") or {}).get("hit") else ""
        print(f"  Results: {len(results)} in {result['duration_ms']}ms{cache_label}")
        if args.show_results and examples:
            print(json.dumps(examples, indent=2, ensure_ascii=False, default=str))
        print()

    saved_questions = [
        {key: value for key, value in question.items() if key != "comparison_keys"}
        for question in question_results
    ]
    report = {
        "run": {
            "timestamp": timestamp,
            "benchmark": str(benchmark_path),
            "database": job["database"],
            "saved_results": "full" if args.save_full else f"examples only, limit {args.limit}",
            "gold_cache": {
                "enabled": not args.no_cache,
                "refresh": args.refresh_cache,
                "directory": args.cache_dir,
            },
        },
        "summary": {
            "total_queries": len(benchmark),
            "successful_queries": len(benchmark) - errors,
            "failed_queries": errors,
        },
        "questions": saved_questions,
    }

    output_dir = Path(args.output_dir) / benchmark_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{timestamp}_{job['database']}_gold_queries.json"
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False, default=str)

    print(f"Finished: {len(benchmark) - errors} OK, {errors} failed")
    print(f"Saved gold-query results to {output_path}")
    print()
    return {"job": job, "output_path": str(output_path), "report": report, "questions_for_compare": question_results}


def compare_gold_reports(run_results: list[dict[str, Any]], output_dir: str, timestamp: str) -> None:
    if len(run_results) != 2:
        print("Gold comparison requires exactly two runs.")
        return

    left, right = run_results
    left_questions = {item["id"]: item for item in left["questions_for_compare"]}
    right_questions = {item["id"]: item for item in right["questions_for_compare"]}
    ids = sorted(set(left_questions) & set(right_questions))
    comparisons = []

    for question_id in ids:
        left_item = left_questions[question_id]
        right_item = right_questions[question_id]
        if left_item["status"] != "ok" or right_item["status"] != "ok":
            status = "error"
            same = False
            missing_count = None
            extra_count = None
        else:
            left_keys = left_item["comparison_keys"]
            right_keys = right_item["comparison_keys"]
            left_counter = Counter(left_keys)
            right_counter = Counter(right_keys)
            same = left_keys == right_keys
            status = "same" if same else "different"
            missing_count = sum((left_counter - right_counter).values())
            extra_count = sum((right_counter - left_counter).values())

        comparisons.append(
            {
                "id": question_id,
                "question": left_item["question"],
                "status": status,
                "same": same,
                "left_result_count": left_item["result_count"],
                "right_result_count": right_item["result_count"],
                "left_error": left_item.get("error"),
                "right_error": right_item.get("error"),
                "missing_from_right": missing_count,
                "extra_in_right": extra_count,
            }
        )

    summary = {
        "total_compared": len(comparisons),
        "same": sum(1 for item in comparisons if item["same"]),
        "different": sum(1 for item in comparisons if not item["same"]),
    }
    comparison_report = {
        "run": {
            "timestamp": timestamp,
            "left": left["job"],
            "right": right["job"],
            "note": "Comparison normalizes result values across flat and structured projections.",
        },
        "summary": summary,
        "questions": comparisons,
    }

    output_path = Path(output_dir) / "comparison" / f"{timestamp}_flat_vs_structured_gold_comparison.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(comparison_report, file, indent=2, ensure_ascii=False, default=str)

    print("Gold comparison")
    print(f"  Same:      {summary['same']}/{summary['total_compared']}")
    print(f"  Different: {summary['different']}/{summary['total_compared']}")
    print(f"  Saved to:  {output_path}")


def main() -> None:
    args = parse_args()
    if args.compare and args.structure != "both":
        raise SystemExit("--compare requires --structure both.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jobs = build_gold_jobs(args)
    run_results = [run_gold_benchmark(args, job, timestamp) for job in jobs]

    if args.compare:
        compare_gold_reports(run_results, args.output_dir, timestamp)


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


if __name__ == "__main__":
    main()

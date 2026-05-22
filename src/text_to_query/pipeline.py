import json
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

import config

load_dotenv()

openai_client = OpenAI()
mongo_client: MongoClient | None = None


SYSTEM_PROMPT = """\
You translate Norwegian natural-language questions into MongoDB queries.

Return only one valid JSON object. Do not use markdown.

Supported operations:
- find: {"op": "find", "collection": "...", "filter": {...}, "projection": {...}}
- distinct: {"op": "distinct", "collection": "...", "field": "...", "filter": {...}}
- aggregate: {"op": "aggregate", "collection": "...", "pipeline": [...]}

Rules:
- Use exact collection names and field names from the schema.
- Use dot notation for nested fields.
- Use aggregate when the question asks for counts, averages, grouping, sorting by calculated values, or rows from embedded arrays.
- Use distinct when the question asks for unique/distinct values.
- Use {"_id": 0} in projections unless the question asks for _id.
"""


def get_database(database_name: str | None = None):
    global mongo_client
    if mongo_client is None:
        mongo_client = MongoClient(config.MONGO_URI)
    return mongo_client[database_name or config.DATABASE_NAME]


def load_schema(path: str) -> str:
    with open(path, encoding="utf-8") as file:
        schema = yaml.safe_load(file)
    return yaml.dump(schema, allow_unicode=True, sort_keys=False)


def load_benchmark(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def generate_query(schema_text: str, question: str) -> dict[str, Any]:
    prompt = f"Database schema:\n{schema_text}\n\nQuestion:\n{question}\n\nMongoDB query JSON:"
    started = time.perf_counter()

    try:
        response = openai_client.chat.completions.create(
            model=config.MODEL,
            temperature=config.TEMPERATURE,
            max_tokens=config.MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        raw_text = (response.choices[0].message.content or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text).strip()

        return {
            "query": json.loads(cleaned),
            "raw_text": raw_text,
            "error": None,
            "duration_ms": elapsed_ms(started),
        }
    except json.JSONDecodeError as exc:
        return {
            "query": None,
            "raw_text": locals().get("raw_text", ""),
            "error": f"JSON parse error: {exc}",
            "duration_ms": elapsed_ms(started),
        }
    except Exception as exc:
        return {
            "query": None,
            "raw_text": "",
            "error": f"LLM error: {exc}",
            "duration_ms": elapsed_ms(started),
        }


def run_query(query: dict[str, Any], database_name: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()

    try:
        collection = get_database(database_name)[query["collection"]]
        op = query.get("op", "find")

        if op == "find":
            projection = query.get("projection")
            cursor = collection.find(query.get("filter", {}), projection) if projection else collection.find(query.get("filter", {}))
            results = list(cursor)
        elif op == "distinct":
            values = collection.distinct(query["field"], query.get("filter", {}))
            results = [{"_value": value} for value in values]
        elif op == "aggregate":
            results = list(collection.aggregate(query["pipeline"]))
        else:
            return {
                "results": [],
                "error": f"Unknown op: {op}",
                "duration_ms": elapsed_ms(started),
                "result_count": 0,
            }

        stringify_object_ids(results)
        return {
            "results": results,
            "error": None,
            "duration_ms": elapsed_ms(started),
            "result_count": len(results),
        }
    except Exception as exc:
        return {
            "results": [],
            "error": str(exc),
            "duration_ms": elapsed_ms(started),
            "result_count": 0,
        }


def stringify_object_ids(value: Any) -> Any:
    if isinstance(value, list):
        for item in value:
            stringify_object_ids(item)
    elif isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "_id":
                value[key] = str(item)
            else:
                stringify_object_ids(item)
    return value


def score_results(gold_results: list[dict[str, Any]], generated_results: list[dict[str, Any]], gold_query: dict[str, Any]) -> dict[str, Any]:
    op = gold_query.get("op", "find")
    projection_fields = projected_fields(gold_query)

    gold_keys = result_counter(gold_results, op, projection_fields)
    generated_keys = result_counter(generated_results, op, projection_fields)

    true_positive = sum((gold_keys & generated_keys).values())
    gold_total = sum(gold_keys.values())
    generated_total = sum(generated_keys.values())

    precision = true_positive / generated_total if generated_total else (1.0 if gold_total == 0 else 0.0)
    recall = true_positive / gold_total if gold_total else (1.0 if generated_total == 0 else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    missing = list((gold_keys - generated_keys).elements())
    extra = list((generated_keys - gold_keys).elements())

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "true_positive": true_positive,
        "gold_count": gold_total,
        "generated_count": generated_total,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "missing_examples": decode_examples(missing[:5]),
        "extra_examples": decode_examples(extra[:5]),
        "comparison_mode": comparison_mode(op, projection_fields),
    }


def projected_fields(query: dict[str, Any]) -> set[str] | None:
    if query.get("op", "find") != "find":
        return None

    projection = query.get("projection") or {}
    fields = {field for field, include in projection.items() if field != "_id" and include}
    return fields or None


def result_counter(results: list[dict[str, Any]], op: str, projection_fields: set[str] | None) -> Counter:
    return Counter(result_key(row, op, projection_fields) for row in results)


def result_key(row: dict[str, Any], op: str, projection_fields: set[str] | None) -> str:
    if op == "distinct":
        return stable_json(normalize_value(row.get("_value")))

    if op == "aggregate":
        return stable_json(normalize_aggregate_row(row))

    if projection_fields:
        comparable = {field: get_path(row, field) for field in sorted(projection_fields)}
    else:
        comparable = {key: value for key, value in row.items() if key != "_id"}
    return stable_json(normalize_value(comparable))


def comparison_mode(op: str, projection_fields: set[str] | None) -> str:
    if op == "distinct":
        return "distinct scalar values"
    if op == "aggregate":
        return "aggregate row values, ignoring output alias names"
    if projection_fields:
        return "find documents using gold projection fields"
    return "find documents using all returned fields except _id"


def normalize_aggregate_row(row: dict[str, Any]) -> Any:
    values = [normalize_value(value) for key, value in row.items() if key != "_id"]
    id_value = normalize_value(row["_id"]) if "_id" in row and row["_id"] is not None else None
    if id_value is not None:
        values.insert(0, id_value)
    return sorted(values, key=stable_json)


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def get_path(document: dict[str, Any], path: str) -> Any:
    return get_parts(document, path.split("."))


def get_parts(value: Any, parts: list[str]) -> Any:
    if not parts:
        return value

    part = parts[0]
    rest = parts[1:]

    if isinstance(value, dict):
        return get_parts(value.get(part), rest)

    if isinstance(value, list):
        return [get_parts(item, parts) for item in value]

    return None


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def decode_examples(keys: list[str]) -> list[Any]:
    examples = []
    for key in keys:
        try:
            examples.append(json.loads(key))
        except json.JSONDecodeError:
            examples.append(key)
    return examples


def projection_score(gold_query: dict[str, Any], generated_query: dict[str, Any]) -> dict[str, Any] | None:
    if gold_query.get("op", "find") != "find":
        return None

    gold_fields = projected_fields(gold_query)
    if not gold_fields:
        return None

    generated_projection = generated_query.get("projection") or {}
    generated_fields = {field for field, include in generated_projection.items() if field != "_id" and include}

    if not generated_fields:
        return {
            "recall": 1.0,
            "precision": None,
            "note": "Generated query has no projection, so all gold fields are present but extra fields are unknown.",
        }

    overlap = gold_fields & generated_fields
    return {
        "recall": round(len(overlap) / len(gold_fields), 4),
        "precision": round(len(overlap) / len(generated_fields), 4),
        "missing_fields": sorted(gold_fields - generated_fields),
        "extra_fields": sorted(generated_fields - gold_fields),
    }


def is_success(score: dict[str, Any], projection: dict[str, Any] | None) -> bool:
    if score["recall"] < 1.0:
        return False
    if score["precision"] < 1.0:
        return False
    if projection and projection["recall"] < 1.0:
        return False
    return True


def explain_failure(score: dict[str, Any], projection: dict[str, Any] | None, status: str, error: str | None) -> str | None:
    if status != "ok":
        return error
    if score["recall"] < 1.0:
        return "Generated query missed one or more expected result documents or values."
    if score["precision"] < 1.0:
        return "Generated query returned extra result documents or values."
    if projection and projection["recall"] < 1.0:
        return "Generated query did not include all required projected fields."
    return None


def evaluate_question(entry: dict[str, Any], schema_text: str, database_name: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    gold_query = entry["gold"]

    result = {
        "id": entry.get("id"),
        "question": entry["question"],
        "category": entry.get("category"),
        "operation": gold_query.get("op", "find"),
        "status": "ok",
        "success": False,
        "failure_reason": None,
        "gold_query": gold_query,
        "generated_query": None,
        "generated_raw_text": None,
        "scores": None,
        "projection_score": None,
        "counts": None,
        "timing_ms": {},
        "examples": None,
    }

    llm = generate_query(schema_text, entry["question"])
    result["timing_ms"]["llm"] = llm["duration_ms"]
    result["generated_raw_text"] = llm.get("raw_text")

    if llm["error"]:
        result["status"] = "llm_error"
        result["failure_reason"] = llm["error"]
        result["timing_ms"]["total"] = elapsed_ms(started)
        return result

    result["generated_query"] = llm["query"]

    gold_run = run_query(gold_query, database_name)
    result["timing_ms"]["gold_query"] = gold_run["duration_ms"]
    if gold_run["error"]:
        result["status"] = "gold_query_error"
        result["failure_reason"] = gold_run["error"]
        result["timing_ms"]["total"] = elapsed_ms(started)
        return result

    generated_run = run_query(llm["query"], database_name)
    result["timing_ms"]["generated_query"] = generated_run["duration_ms"]
    if generated_run["error"]:
        result["status"] = "generated_query_error"
        result["failure_reason"] = generated_run["error"]
        result["timing_ms"]["total"] = elapsed_ms(started)
        return result

    score_started = time.perf_counter()
    scores = score_results(gold_run["results"], generated_run["results"], gold_query)
    projection = projection_score(gold_query, llm["query"])
    result["timing_ms"]["scoring"] = elapsed_ms(score_started)
    result["timing_ms"]["total"] = elapsed_ms(started)

    result["scores"] = scores
    result["projection_score"] = projection
    result["success"] = is_success(scores, projection)
    result["failure_reason"] = explain_failure(scores, projection, result["status"], None)
    result["counts"] = {
        "gold": gold_run["result_count"],
        "generated": generated_run["result_count"],
    }
    result["examples"] = {
        "gold_first_3": gold_run["results"][:3],
        "generated_first_3": generated_run["results"][:3],
        "missing": scores["missing_examples"],
        "extra": scores["extra_examples"],
    }
    return result


def run_evaluation(
    schema_path: str,
    benchmark_path: str,
    label: str,
    database: str | None = None,
    question_id: int | None = None,
) -> None:
    run_started = time.perf_counter()
    database_name = database or config.DATABASE_NAME

    print()
    print("=" * 72)
    print(f"Run: {label}")
    print(f"Model: {config.MODEL}")
    print(f"Database: {database_name}")
    print(f"Schema: {Path(schema_path).name}")
    print(f"Benchmark: {Path(benchmark_path).name}")
    if question_id is not None:
        print(f"Question id: {question_id}")
    print("=" * 72)

    schema_text = load_schema(schema_path)
    benchmark = load_benchmark(benchmark_path)
    if question_id is not None:
        benchmark = [entry for entry in benchmark if entry.get("id") == question_id]
        if not benchmark:
            print(f"No benchmark question found with id {question_id}.")
            return
    question_results = []

    for index, entry in enumerate(benchmark, start=1):
        op = entry.get("gold", {}).get("op", "find")
        print(f"[{index:>2}/{len(benchmark)}] {op:<9} Q{entry.get('id')}: {entry['question'][:70]}")
        result = evaluate_question(entry, schema_text, database_name)
        question_results.append(result)
        print_question_result(result)

    summary = summarize_results(question_results, elapsed_ms(run_started))
    print_summary(summary)
    save_results(label, schema_path, benchmark_path, database_name, question_results, summary, question_id)


def print_question_result(result: dict[str, Any]) -> None:
    if result["status"] != "ok":
        print(f"          ERROR {result['status']}: {result['failure_reason']}")
        return

    score = result["scores"]
    tag = "PASS" if result["success"] else "FAIL"
    timing = result["timing_ms"]
    print(
        f"          {tag} "
        f"P={score['precision']:.2f} R={score['recall']:.2f} F1={score['f1']:.2f} "
        f"gold={result['counts']['gold']} gen={result['counts']['generated']} "
        f"time={timing['total']}ms"
    )
    if result["failure_reason"]:
        print(f"          {result['failure_reason']}")


def summarize_results(results: list[dict[str, Any]], total_duration_ms: int) -> dict[str, Any]:
    scored = [result for result in results if result["scores"]]
    errors = [result for result in results if result["status"] != "ok"]
    failures = [result for result in results if result["status"] != "ok" or not result["success"]]

    def average(field: str) -> float:
        if not scored:
            return 0.0
        return round(sum(result["scores"][field] for result in scored) / len(scored), 4)

    return {
        "total_questions": len(results),
        "scored_questions": len(scored),
        "successful_questions": sum(1 for result in scored if result["success"]),
        "failed_questions": len(failures),
        "success_rate": round(sum(1 for result in scored if result["success"]) / len(scored), 4) if scored else 0.0,
        "avg_precision": average("precision"),
        "avg_recall": average("recall"),
        "avg_f1": average("f1"),
        "timing_ms": timing_summary(results, total_duration_ms),
        "errors": {
            "total": len(errors),
            "llm_error": sum(1 for result in errors if result["status"] == "llm_error"),
            "gold_query_error": sum(1 for result in errors if result["status"] == "gold_query_error"),
            "generated_query_error": sum(1 for result in errors if result["status"] == "generated_query_error"),
        },
        "by_operation": breakdown(results, "operation"),
        "by_category": breakdown(results, "category"),
        "worst_questions": worst_questions(results),
    }


def timing_summary(results: list[dict[str, Any]], total_duration_ms: int) -> dict[str, Any]:
    completed = [result for result in results if result["timing_ms"].get("total") is not None]

    def avg_time(name: str) -> int:
        values = [result["timing_ms"].get(name, 0) for result in completed]
        return round(sum(values) / len(values)) if values else 0

    return {
        "total_run": total_duration_ms,
        "avg_per_question": avg_time("total"),
        "avg_llm": avg_time("llm"),
        "avg_gold_query": avg_time("gold_query"),
        "avg_generated_query": avg_time("generated_query"),
        "avg_scoring": avg_time("scoring"),
    }


def breakdown(results: list[dict[str, Any]], field: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        if result["scores"]:
            groups.setdefault(str(result.get(field) or "uncategorized"), []).append(result)

    output = {}
    for name, items in groups.items():
        success_count = sum(1 for item in items if item["success"])
        output[name] = {
            "questions": len(items),
            "successful": success_count,
            "success_rate": round(success_count / len(items), 4),
            "avg_precision": round(sum(item["scores"]["precision"] for item in items) / len(items), 4),
            "avg_recall": round(sum(item["scores"]["recall"] for item in items) / len(items), 4),
            "avg_f1": round(sum(item["scores"]["f1"] for item in items) / len(items), 4),
        }
    return output


def worst_questions(results: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    scored = [result for result in results if result["scores"]]
    scored.sort(key=lambda result: (result["scores"]["f1"], result["scores"]["recall"], result["scores"]["precision"]))
    return [
        {
            "id": result["id"],
            "question": result["question"],
            "operation": result["operation"],
            "category": result["category"],
            "precision": result["scores"]["precision"],
            "recall": result["scores"]["recall"],
            "f1": result["scores"]["f1"],
            "failure_reason": result["failure_reason"],
        }
        for result in scored[:limit]
    ]


def print_summary(summary: dict[str, Any]) -> None:
    print()
    print("=" * 72)
    print("Summary")
    print(f"Success:   {summary['success_rate']:.1%} ({summary['successful_questions']}/{summary['scored_questions']})")
    print(f"Precision: {summary['avg_precision']:.4f}")
    print(f"Recall:    {summary['avg_recall']:.4f}")
    print(f"F1:        {summary['avg_f1']:.4f}")
    print(f"Time:      {summary['timing_ms']['total_run']}ms total, {summary['timing_ms']['avg_per_question']}ms/question")

    if summary["errors"]["total"]:
        print(f"Errors:    {summary['errors']}")

    print()
    print("Worst questions:")
    for item in summary["worst_questions"][:5]:
        print(f"  Q{item['id']}: F1={item['f1']:.2f} P={item['precision']:.2f} R={item['recall']:.2f} - {item['question'][:70]}")
    print()


def save_results(
    label: str,
    schema_path: str,
    benchmark_path: str,
    database_name: str,
    question_results: list[dict[str, Any]],
    summary: dict[str, Any],
    question_id: int | None = None,
) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    schema_name = Path(schema_path).stem
    benchmark_name = Path(benchmark_path).stem
    output_dir = Path(config.RESULTS_DIR) / benchmark_name / schema_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{timestamp}_{label}.json"

    failures = [
        compact_failure(result)
        for result in question_results
        if result["status"] != "ok" or not result["success"]
    ]

    run_info = {
        "label": label,
        "timestamp": timestamp,
        "model": config.MODEL,
        "database": database_name,
        "schema": Path(schema_path).name,
        "benchmark": Path(benchmark_path).name,
        "question_id": question_id,
        "metric": "Precision, recall and F1 are computed over returned values. Precision and recall are equally weighted.",
        "success_definition": "A question is marked successful only when precision and recall are both 1.0.",
    }

    if question_id is not None and len(question_results) == 1:
        report = {
            "run": run_info,
            "question": question_results[0],
            "failure": failures[0] if failures else None,
        }
    else:
        report = {
            "run": run_info,
            "summary": summary,
            "failures": failures,
            "questions": question_results,
        }

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False, default=str)

    print(f"Saved results to {output_path}")


def compact_failure(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result["id"],
        "question": result["question"],
        "operation": result["operation"],
        "category": result["category"],
        "status": result["status"],
        "success": result["success"],
        "failure_reason": result["failure_reason"],
        "scores": result["scores"],
        "counts": result["counts"],
        "timing_ms": result["timing_ms"],
        "gold_query": result["gold_query"],
        "generated_query": result["generated_query"],
        "missing_examples": (result.get("examples") or {}).get("missing"),
        "extra_examples": (result.get("examples") or {}).get("extra"),
    }


def elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
